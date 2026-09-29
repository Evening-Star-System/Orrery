"""guard-wiring: a guard hook that exists but is not wired into settings.json does not run.

"Everything is guarded" is only true if each guard is BOTH present in the hooks dir AND referenced
by a hook command in settings.json. This check measures that instead of trusting it: for each declared
guard filename it reports OK (present + wired), FAIL (present but UNWIRED, so it never fires), or FAIL
(MISSING). A malformed settings.json is a WARN (could not verify), never a silent pass.
"""

from __future__ import annotations

import json

from ..box import Box
from ..model import Finding, Severity

ID = "guard-wiring"
TITLE = "each guard hook is present AND wired into settings.json"


def _wired_commands(settings_text: str) -> "set[str] | None":
    """All hook command strings declared in settings.json, or None if it cannot be parsed."""
    try:
        data = json.loads(settings_text)
    except Exception:
        return None
    cmds: set[str] = set()
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for entries in hooks.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                for h in (entry or {}).get("hooks", []) or []:
                    cmd = (h or {}).get("command")
                    if isinstance(cmd, str):
                        cmds.add(cmd)
    return cmds


class GuardWiringCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"hooks_dir", "settings", "guards"})
    required_keys = frozenset({"hooks_dir", "settings", "guards"})

    def run(self, options: dict, box: Box) -> list[Finding]:
        hooks_dir = str(options.get("hooks_dir", "")).rstrip("/")
        settings_path = str(options.get("settings", ""))
        guards = options.get("guards") or []
        if not hooks_dir or not settings_path or not guards:
            return [Finding(ID, Severity.WARN, ID, "guard-wiring needs hooks_dir, settings, and guards")]

        settings_text = box.read_text(settings_path)
        if settings_text is None:
            return [Finding(ID, Severity.WARN, settings_path, "settings.json unreadable; cannot verify wiring")]
        cmds = _wired_commands(settings_text)
        if cmds is None:
            return [Finding(ID, Severity.WARN, settings_path, "settings.json is not valid JSON; cannot verify wiring")]
        blob = "\n".join(cmds)

        findings: list[Finding] = []
        for guard in guards:
            name = str(guard)
            present = box.exists(f"{hooks_dir}/{name}")
            wired = name in blob
            if present and wired:
                findings.append(Finding(ID, Severity.OK, name, "present and wired"))
            elif present and not wired:
                findings.append(Finding(
                    ID, Severity.FAIL, name,
                    "guard present but NOT wired in settings.json (it never fires)",
                    expected="wired", observed="unwired",
                ))
            else:
                findings.append(Finding(
                    ID, Severity.FAIL, name,
                    "guard MISSING from the hooks dir",
                    expected="present", observed="absent",
                ))
        return findings
