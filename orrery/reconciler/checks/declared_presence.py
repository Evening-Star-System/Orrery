"""declared-presence: required members exist; planned-absent paths stay absent.

A required member that is missing is a FAIL (the declared shape is broken). A path
declared planned-absent (a hardening step not yet taken) is INFO while absent and
WARN if it appears, because its appearance means the profile is now stale.
"""

from __future__ import annotations

from ..box import Box
from ..model import Finding, Severity

ID = "declared-presence"
TITLE = "declared members present, planned-absent paths still absent"


class DeclaredPresenceCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"required", "planned_absent"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        findings: list[Finding] = []
        for path in options.get("required", []):
            if box.exists(path):
                findings.append(Finding(ID, Severity.OK, path, "present"))
            else:
                findings.append(
                    Finding(
                        ID,
                        Severity.FAIL,
                        path,
                        "required member is missing",
                        expected="present",
                        observed="absent",
                    )
                )
        for path in options.get("planned_absent", []):
            if box.exists(path):
                findings.append(
                    Finding(
                        ID,
                        Severity.WARN,
                        path,
                        "planned-absent path now exists; profile is stale",
                        expected="absent (planned)",
                        observed="present",
                    )
                )
            else:
                findings.append(
                    Finding(ID, Severity.INFO, path, "absent as planned")
                )
        return findings
