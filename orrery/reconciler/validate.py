"""Validate a profile against what the engine can actually run, before it runs.

A profile is the most hand-edited input, and the failures that hurt are the quiet
ones: a check id with a typo runs nothing and reports nothing, so a box looks clean
because it was never actually checked. This validates the profile's SHAPE (is the box
named, is every check id one the registry knows, are there duplicates) so those quiet
mistakes surface as their own finding instead of as false silence.

Value-blind by construction: an issue names a location and a check id or an option KEY,
never an option VALUE, so a profile that points a check at a secret path can be validated
without that path appearing in the output.
"""

from __future__ import annotations

import difflib
import tomllib
from dataclasses import dataclass
from pathlib import Path

# Ordered worst-first so a caller can decide the exit code from the first level seen.
ERROR = "error"  # the profile will not run as written, or runs less than it claims
WARN = "warn"  # the profile runs, but likely not what the author meant
INFO = "info"  # worth noticing, not a problem


@dataclass(frozen=True)
class ProfileIssue:
    level: str
    location: str
    message: str


# A check's option schema: (recognized top-level keys, required subset). Injected by the
# caller so this module stays decoupled from the registry.
Schemas = dict[str, tuple[frozenset[str], frozenset[str]]]


def validate_profile(
    path: str | Path, known_ids: list[str], schemas: Schemas | None = None
) -> list[ProfileIssue]:
    """Read, parse, and validate the profile at path. A parse or read failure is
    itself a single ERROR issue, so the caller never has to handle an exception."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return [ProfileIssue(ERROR, "file", f"cannot read the profile: {exc.strerror or exc}")]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [ProfileIssue(ERROR, "file", f"not valid TOML: {exc}")]
    return validate_profile_data(data, known_ids, schemas)


def validate_profile_data(
    data: dict, known_ids: list[str], schemas: Schemas | None = None
) -> list[ProfileIssue]:
    issues: list[ProfileIssue] = []

    box = data.get("box")
    if not isinstance(box, str) or not box.strip():
        issues.append(ProfileIssue(ERROR, "box", "required: name this box with a non-empty string"))

    raw_checks = data.get("checks")
    if raw_checks is None or raw_checks == []:
        issues.append(ProfileIssue(WARN, "checks", "no checks declared, so this profile does nothing"))
        return issues
    if not isinstance(raw_checks, list):
        issues.append(ProfileIssue(ERROR, "checks", "must be an array of tables ([[checks]])"))
        return issues

    seen: dict[str, int] = {}
    for i, raw in enumerate(raw_checks):
        loc = f"checks[{i}]"
        if not isinstance(raw, dict):
            issues.append(ProfileIssue(ERROR, loc, "must be a table ([[checks]])"))
            continue
        cid = raw.get("id")
        if not isinstance(cid, str) or not cid.strip():
            issues.append(ProfileIssue(ERROR, f"{loc}.id", "required: every check needs an id"))
            continue
        seen[cid] = seen.get(cid, 0) + 1
        if cid not in known_ids:
            hint = _suggest(cid, known_ids)
            msg = f"unknown check id '{cid}'" + (f"; did you mean '{hint}'?" if hint else "")
            issues.append(ProfileIssue(ERROR, f"{loc}.id", msg))
            continue

        provided = {k for k in raw if k != "id"}
        schema = schemas.get(cid) if schemas else None
        if schema is not None:
            recognized, required = schema
            for key in sorted(provided - recognized):
                hint = _suggest(key, sorted(recognized))
                msg = f"unknown option '{key}' for check '{cid}'"
                if hint:
                    msg += f"; did you mean '{hint}'?"
                issues.append(ProfileIssue(WARN, f"{loc}.{key}", msg))
            for key in sorted(required - provided):
                issues.append(ProfileIssue(ERROR, f"{loc}.{key}", f"required option for check '{cid}'"))

        # Only note "no options" when the check needed none; a missing required key already
        # reported the real problem above.
        if not provided and not (schema and schema[1]):
            issues.append(ProfileIssue(INFO, loc, f"check '{cid}' has no options set"))

    for cid, n in seen.items():
        if n > 1:
            issues.append(ProfileIssue(WARN, "checks", f"check id '{cid}' is declared {n} times"))

    return issues


def _suggest(cid: str, known_ids: list[str]) -> str | None:
    matches = difflib.get_close_matches(cid, known_ids, n=1, cutoff=0.6)
    return matches[0] if matches else None
