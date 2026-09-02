"""floors: calibrated floors and ceilings, verified.

Each declared entry counts something (files under a dir, or lines in a file) and
compares it to bounds: below `min` is a breached FLOOR (data loss), above `max` is a
breached ceiling/budget, and far above `min` (by recalibrate_ratio) is a stale floor
worth resetting. Read-only and bounded; a missing path is DRIFT, never a false zero.
"""

from __future__ import annotations

from ..box import Box
from ..model import Finding, Severity

ID = "floors"
TITLE = "counts stay within declared floors and ceilings"

_COUNT_CAP = 100_000  # bound file_count so a huge tree cannot run away


class FloorsCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"floors"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        floors = options.get("floors", [])
        if not floors:
            return [Finding(ID, Severity.WARN, ID, "no floors declared")]
        findings: list[Finding] = []
        for entry in floors:
            findings.append(self._check_one(entry, box))
        return findings

    def _check_one(self, entry: dict, box: Box) -> Finding:
        name = entry.get("name") or entry.get("path") or "<floor>"
        path = entry.get("path")
        kind = entry.get("kind", "file_count")
        if not path:
            return Finding(ID, Severity.WARN, name, "floor entry missing 'path'")
        if not box.exists(path):
            return Finding(
                ID, Severity.DRIFT, name, "floor path is missing",
                expected="present", observed="absent",
            )
        actual = self._measure(box, path, kind)
        if actual is None:
            return Finding(ID, Severity.WARN, name, f"cannot measure kind '{kind}'")

        mn = entry.get("min")
        mx = entry.get("max")
        ratio = entry.get("recalibrate_ratio")
        detail = f"{actual}"
        if mn is not None and actual < mn:
            return Finding(
                ID, Severity.FAIL, name, "below the declared floor",
                expected=f">= {mn}", observed=detail,
            )
        if mx is not None and actual > mx:
            return Finding(
                ID, Severity.WARN, name, "above the declared ceiling",
                expected=f"<= {mx}", observed=detail,
            )
        if mn is not None and ratio and actual > mn * ratio:
            return Finding(
                ID, Severity.INFO, name, "floor is far below reality; recalibrate",
                expected=f"floor {mn}", observed=detail,
            )
        return Finding(ID, Severity.OK, name, f"within bounds ({detail})")

    def _measure(self, box: Box, path: str, kind: str) -> int | None:
        if kind == "file_count":
            lister = getattr(box, "list_files", None)
            files = lister(path, _COUNT_CAP) if lister else None
            return len(files) if files is not None else None
        if kind == "line_count":
            text = box.read_text(path)
            if text is None:
                return None
            return text.count("\n") + (0 if text.endswith("\n") or text == "" else 1)
        return None
