"""managed-settings: the enforcement layer must be root-owned and not editable by
anyone but its owner.

If the guards can be edited by a non-root operator, the below-the-model safety is not
really enforced (threat model T5). This check verifies each declared enforcement file
is present, owned by the expected uid, and no more permissive than allowed (no group or
other write). A file declared `planned` that is not yet in place reports INFO, so the
promotion path is visible without failing the run.
"""

from __future__ import annotations

from ..box import Box
from ..model import Finding, Severity

ID = "managed-settings"
TITLE = "enforcement files are present, root-owned, and not writable by non-owners"

_DEFAULT_MAX_MODE = 0o644


def _parse_mode(value: object) -> int | None:
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 8)
    except (ValueError, TypeError):
        return None


class ManagedSettingsCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"files"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        files = options.get("files", [])
        if not files:
            return [Finding(ID, Severity.WARN, ID, "no files declared for managed-settings")]
        return [self._check_one(f, box) for f in files]

    def _check_one(self, entry: dict, box: Box) -> Finding:
        path = entry.get("path")
        if not path:
            return Finding(ID, Severity.WARN, "<file>", "entry missing 'path'")
        planned = bool(entry.get("planned", False))

        getter = getattr(box, "file_meta", None)
        meta = getter(path) if getter else None
        if meta is None:
            if planned:
                return Finding(ID, Severity.INFO, path, "not yet in place (planned)")
            return Finding(
                ID, Severity.FAIL, path, "required enforcement file is missing",
                expected="present", observed="absent",
            )

        uid, mode = meta
        req_uid = entry.get("require_owner_uid")
        if req_uid is not None and uid != req_uid:
            return Finding(
                ID, Severity.DRIFT, path, "wrong owner",
                expected=f"uid {req_uid}", observed=f"uid {uid}",
            )

        max_mode = _parse_mode(entry.get("max_mode", _DEFAULT_MAX_MODE))
        if max_mode is None:
            return Finding(ID, Severity.WARN, path, "invalid max_mode in profile")
        extra = mode & ~max_mode
        if extra:
            return Finding(
                ID, Severity.FAIL, path,
                "more permissive than allowed (a non-owner could edit it)",
                expected=f"<= {oct(max_mode)}", observed=oct(mode),
            )
        return Finding(ID, Severity.OK, path, f"owner+perms ok ({oct(mode)})")
