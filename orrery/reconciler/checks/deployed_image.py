"""deployed-image: the Kamal rail's running state matches the declared, secure shape.

Box shape checks say the filesystem looks right; this says the live deployment does. For a declared box
it read-only probes (over the prober's ssh read) and verifies the rail invariants:
  - a container is running the declared image at the declared tag (no silent drift);
  - kamal-proxy is present and LOOPBACK-only (nothing on public 0.0.0.0:80/443);
  - a cloudflared tunnel is present (systemd or container) as the sole ingress;
  - NO coolify-* containers (the dropped anti-pattern proxy is gone).
CF Access wildcard presence is a Cloudflare control-plane fact, not observable from a box probe, so it is
reported INFO (verify externally), never a false pass. If the box cannot be measured, that is a WARN, not
silent-clean. Read-only + never-raises: a bad host is refused, a prober error becomes a WARN.
"""

from __future__ import annotations

import re

from ..box import Box
from ..model import Finding, Severity
from ..prober import Prober, SshProber

ID = "deployed-image"
TITLE = "the box's running Kamal deployment matches the declared secure shape"

# Same discipline as fleet-reach: refuse to probe anything that could be read as an ssh flag.
_SAFE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")

# One read-only probe, labeled sections we parse. docker/systemctl only; no mutation.
_PROBE = (
    "echo '#PS'; docker ps --format '{{.Names}}||{{.Image}}||{{.Ports}}' 2>/dev/null; "
    "echo '#PSA'; docker ps -a --format '{{.Names}}' 2>/dev/null; "
    "echo '#CFD'; systemctl is-active cloudflared 2>/dev/null; "
    "docker ps --format '{{.Names}}' 2>/dev/null | grep -i cloudflared; "
    "echo '#END'"
)

_PUBLIC_PORT = re.compile(r"(?:0\.0\.0\.0|::):(?:80|443)->")


def _section(out: str, tag: str) -> list[str]:
    lines: list[str] = []
    grabbing = False
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("#"):
            grabbing = (s == tag)
            continue
        if grabbing and s:
            lines.append(s)
    return lines


class DeployedImageCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"host", "image", "tag", "service", "pattern", "timeout"})
    required_keys = frozenset({"host", "image"})

    def __init__(self, prober: Prober | None = None):
        self._prober = prober or SshProber()

    def run(self, options: dict, box: Box) -> list[Finding]:
        host = str(options.get("host", "") or "")
        image = str(options.get("image", "") or "")
        tag = str(options.get("tag", "") or "")
        timeout = int(options.get("timeout", 8))
        if not host or not image:
            return [Finding(ID, Severity.WARN, ID, "deployed-image needs host and image in the profile")]
        if not _SAFE_HOST.match(host):
            return [Finding(ID, Severity.WARN, host, "unsafe host string, refusing to probe")]

        try:
            rc, out = self._prober.read(host, _PROBE, timeout)
        except Exception as exc:  # a prober bug must not sink the run
            return [Finding(ID, Severity.WARN, host, f"probe raised {exc.__class__.__name__}, could not verify")]
        if rc != 0 or "#END" not in out:
            return [Finding(ID, Severity.WARN, host, "could not measure the box (unreachable or probe failed)",
                            expected="measurable", observed=f"rc={rc}")]

        ps = _section(out, "#PS")        # name||image||ports
        psa = _section(out, "#PSA")      # all container names
        cfd = _section(out, "#CFD")      # 'active' and/or cloudflared container names
        rows = [tuple((p.split("||") + ["", "", ""])[:3]) for p in ps]

        findings: list[Finding] = []

        # 1. app image + tag
        app = [(n, img, ports) for (n, img, ports) in rows if img.split(":")[0].endswith(image) or img.startswith(image)]
        if not app:
            findings.append(Finding(ID, Severity.FAIL, host, f"no running container on the declared image {image}",
                                    expected=image, observed="none"))
        elif not tag:
            findings.append(Finding(ID, Severity.WARN, host, f"{image} running but no declared tag to match",
                                    observed=app[0][1]))
        else:
            want = f"{image}:{tag}"
            if any(img == want for (_, img, _) in app):
                findings.append(Finding(ID, Severity.OK, host, f"running the declared tag {want}"))
            else:
                findings.append(Finding(ID, Severity.DRIFT, host, "running image tag != declared tag",
                                        expected=want, observed=app[0][1]))

        # 2/3. kamal-proxy present + loopback-only
        proxy = [(n, ports) for (n, _, ports) in rows if "kamal-proxy" in n]
        if not proxy:
            findings.append(Finding(ID, Severity.FAIL, host, "kamal-proxy is not running", expected="kamal-proxy", observed="absent"))
        else:
            ports = proxy[0][1]
            if _PUBLIC_PORT.search(ports):
                findings.append(Finding(ID, Severity.FAIL, host, "kamal-proxy publishes a PUBLIC port (must be loopback only)",
                                        expected="127.0.0.1 only", observed=ports))
            else:
                findings.append(Finding(ID, Severity.OK, host, "kamal-proxy present and loopback-only"))

        # 4. no public :80/:443 on ANY container
        public = [n for (n, _, ports) in rows if _PUBLIC_PORT.search(ports)]
        if public:
            findings.append(Finding(ID, Severity.FAIL, host, f"container(s) publish public :80/:443: {', '.join(public)}",
                                    expected="no public app ports", observed=", ".join(public)))
        else:
            findings.append(Finding(ID, Severity.OK, host, "nothing publishes public :80/:443"))

        # 5. cloudflared present (systemd active OR a container)
        if any(l == "active" for l in cfd) or any("cloudflared" in l for l in cfd):
            findings.append(Finding(ID, Severity.OK, host, "cloudflared tunnel present"))
        else:
            findings.append(Finding(ID, Severity.FAIL, host, "no cloudflared tunnel (systemd or container) found",
                                    expected="cloudflared present", observed="none"))

        # 6. NO coolify-* containers
        coolify = [n for n in psa if "coolify" in n.lower()]
        if coolify:
            findings.append(Finding(ID, Severity.FAIL, host, f"coolify container(s) still present: {', '.join(coolify)}",
                                    expected="no coolify", observed=", ".join(coolify)))
        else:
            findings.append(Finding(ID, Severity.OK, host, "no coolify containers"))

        # 7. CF Access wildcard: control-plane fact, not box-observable
        findings.append(Finding(ID, Severity.INFO, host, "CF Access wildcard gate must be verified externally (not observable from the box)"))
        return findings
