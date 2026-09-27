"""handoff-freshness: a declared digest carries a current session handoff.

Session continuity depends on the PICKUP block at a digest's head being present and recent, so a fresh
session (including after a context clear) wakes oriented rather than from stale or absent state. This is
the reconciler gate that replaces the mtime "nudge": for each declared digest, a missing PICKUP block is a
FAIL (nothing to wake from), and a block older than its max age is a WARN (drifting stale).

Options:
  [[checks.handoffs]]
  path = "/abs/path/to/.dev/DIGEST.md"
  max_age_days = 14        # optional, default 14
"""
from __future__ import annotations

import time

from ..model import Finding, Severity

try:
    from ...context.handoff import END, START
except Exception:  # keep the check usable even if context package moves
    START, END = "<!-- PICKUP:START -->", "<!-- PICKUP:END -->"

ID = "handoff-freshness"
TITLE = "declared digests carry a current PICKUP handoff"
_DEFAULT_MAX_AGE_DAYS = 14


class HandoffFreshnessCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"handoffs"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box) -> list[Finding]:
        findings: list[Finding] = []
        for entry in options.get("handoffs", []):
            path = entry.get("path")
            if not path:
                continue
            max_age = int(entry.get("max_age_days", _DEFAULT_MAX_AGE_DAYS))
            if not box.exists(path):
                findings.append(Finding(ID, Severity.FAIL, path, "no digest present",
                                        expected="a digest with a PICKUP block", observed="absent"))
                continue
            text = box.read_text(path) or ""
            if START not in text or END not in text:
                findings.append(Finding(ID, Severity.FAIL, path, "no PICKUP block (run /wrap to consolidate)",
                                        expected="a PICKUP block at the head", observed="none"))
                continue
            meta = box.file_meta(path)
            if not meta:
                findings.append(Finding(ID, Severity.WARN, path, "PICKUP present, age unknown"))
                continue
            age_days = (time.time() - meta[1]) / 86400.0
            if age_days > max_age:
                findings.append(Finding(ID, Severity.WARN, path,
                                        f"handoff is stale ({age_days:.0f}d > {max_age}d): re-run /wrap",
                                        expected=f"<= {max_age}d", observed=f"{age_days:.0f}d"))
            else:
                findings.append(Finding(ID, Severity.OK, path, f"fresh ({age_days:.0f}d)"))
        return findings
