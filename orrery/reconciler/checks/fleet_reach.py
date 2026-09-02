"""fleet-reach: the declared reach matrix as a live invariant.

The profile declares the edges FROM this box and what each should be. The check
probes reality and reports both directions of failure: a depended-on link that is
down (FAIL) and a deliberately-closed link that has reopened (DRIFT, a security
regression). A closed edge going quiet is the one nothing else watches for.
"""

from __future__ import annotations

import re

from ..box import Box
from ..model import Finding, Severity
from ..prober import Prober, SshProber

ID = "fleet-reach"
TITLE = "actual ssh reach matches the declared matrix"

_OK = "ok"
_DENIED = "denied"

# A host must be a plain ssh alias or user@host: never something that could be read
# as an ssh flag. Defense in depth with the `--` separator in the prober; this refuses
# to probe an unsafe value at all, so the "report-only, never executes" premise holds
# structurally, not by trusting the profile.
_SAFE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]*$")


class FleetReachCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"timeout", "edges"})
    required_keys: frozenset[str] = frozenset()

    def __init__(self, prober: Prober | None = None):
        self._prober = prober or SshProber()

    def run(self, options: dict, box: Box) -> list[Finding]:
        timeout = int(options.get("timeout", 5))
        edges = options.get("edges", [])
        if not edges:
            return [Finding(ID, Severity.WARN, ID, "no edges declared for fleet-reach")]

        findings: list[Finding] = []
        for edge in edges:
            host = edge.get("to")
            expect = str(edge.get("expect", "")).lower()
            if not host or expect not in (_OK, _DENIED):
                findings.append(
                    Finding(
                        ID,
                        Severity.WARN,
                        str(host),
                        "edge needs 'to' and expect of ok|denied",
                    )
                )
                continue
            if not _SAFE_HOST.match(host):
                findings.append(
                    Finding(
                        ID,
                        Severity.WARN,
                        host,
                        "unsafe host string, refusing to probe",
                    )
                )
                continue
            try:
                reachable = self._prober.can_reach(host, timeout)
            except Exception as exc:  # a prober bug must not sink the run
                findings.append(
                    Finding(
                        ID,
                        Severity.WARN,
                        host,
                        f"probe raised {exc.__class__.__name__}, could not verify",
                    )
                )
                continue
            findings.append(self._judge(host, expect, reachable))
        return findings

    def _judge(self, host: str, expect: str, reachable: bool) -> Finding:
        if expect == _OK:
            if reachable:
                return Finding(ID, Severity.OK, host, "reachable as declared")
            return Finding(
                ID,
                Severity.FAIL,
                host,
                "declared-reachable link is DOWN",
                expected="reachable",
                observed="unreachable",
            )
        # expect == denied
        if reachable:
            return Finding(
                ID,
                Severity.DRIFT,
                host,
                "a deliberately-denied edge is now OPEN (regression)",
                expected="denied",
                observed="reachable",
            )
        return Finding(ID, Severity.OK, host, "correctly denied")
