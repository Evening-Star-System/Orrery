"""content-address: a protected artifact stays byte-exact to its recorded content-address.

A file's correct identity is the hash of its correct bytes. Each declared artifact carries the
`path` to protect, the `hash` it must keep producing (its recorded content-address), and a human
`why`. The check hashes the current bytes and adjudicates against the recorded hash. It is
value-blind: it compares hashes, it never interprets the file.

SEVERITY.
  OK    the current bytes hash to the recorded content-address. Integrity intact.
  FAIL  the bytes changed (the exact integrity failure this exists for), OR the file is missing
        (data loss), OR the artifact is declared with no recorded hash yet (an unrecorded artifact
        protects nothing, so it blocks until recorded, forcing declare-and-record together).
  WARN  the file exists but could not be hashed (unreadable), so there is no observed value to
        judge. A skipped artifact is never a silent pass.

Recovering the correct bytes is a separate, gated apply step (the store holds them under their
hash); this check only proves whether they are right, never rewrites them.
"""

from __future__ import annotations

from ..box import Box
from ..model import Finding, Severity

ID = "content-address"
TITLE = "protected artifacts stay byte-exact to their recorded content-address"


class ContentAddressCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"artifacts"})
    required_keys = frozenset({"artifacts"})

    def run(self, options: dict, box: Box) -> list[Finding]:
        artifacts = options.get("artifacts") or []
        if not artifacts:
            return [Finding(ID, Severity.WARN, ID, "no artifacts declared")]
        return [self._check_one(entry, box) for entry in artifacts]

    def _check_one(self, entry: dict, box: Box) -> Finding:
        name = entry.get("name") or entry.get("path") or "<artifact>"
        path = entry.get("path")
        if not path:
            return Finding(ID, Severity.WARN, name, "artifact entry missing 'path'")

        recorded = entry.get("hash")
        if recorded is None or not str(recorded).strip():
            # Declared but never recorded: it protects nothing, so it blocks until a
            # content-address is recorded, forcing declare-and-record in the same change.
            return Finding(
                ID, Severity.FAIL, name,
                "artifact declared with no recorded content-address; record it before it can gate",
                expected="a recorded hash", observed="none",
            )

        if not box.exists(path):
            return Finding(
                ID, Severity.FAIL, name, "protected artifact is missing",
                expected="present", observed="absent",
            )

        current = box.content_hash(path)
        if current is None:
            # Exists but could not be hashed: loud and non-green, never a false OK. A statement
            # about the read, not about the bytes.
            return Finding(ID, Severity.WARN, name, "protected artifact could not be hashed")

        if _norm(current) == _norm(recorded):
            return Finding(ID, Severity.OK, name, "bytes match the recorded content-address")
        return Finding(
            ID, Severity.FAIL, name, "integrity failure: bytes changed",
            expected=_short(recorded), observed=_short(current),
        )


def _norm(value: str) -> str:
    """Compare hashes ignoring case and an optional algorithm prefix (`sha256:...`)."""
    s = str(value).strip().lower()
    return s.split(":", 1)[1] if s.startswith("sha256:") else s


def _short(value: str) -> str:
    h = _norm(value)
    return f"sha256:{h[:12]}..." if len(h) >= 12 else f"sha256:{h}"
