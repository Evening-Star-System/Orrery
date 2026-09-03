"""Load the stack-profiles table, detect a project's stack, and resolve its commands.

The table is the single graft point: a new stack is one new block, detected first-match-wins by its
`detect` file. Everything downstream (the CI renderers, the scaffold, the backfill) reads from here,
so the trunk stays stack-agnostic.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

_DATA = Path(__file__).parent / "data"
_PROFILES = _DATA / "stack-profiles.toml"

# The prove-beats a profile may define, in run order. Any beat without a command is skipped.
BEATS = ("setup", "lint", "test", "checks")


def load_profiles(path: str | Path | None = None) -> dict:
    """The stack table as an ordered dict (declaration order is detection priority)."""
    p = Path(path) if path else _PROFILES
    return tomllib.loads(p.read_text(encoding="utf-8"))


def detect(project_dir: str | Path, profiles: dict | None = None) -> str:
    """The stack whose `detect` file is present, first match wins; 'generic' if none match."""
    profiles = profiles if profiles is not None else load_profiles()
    d = Path(project_dir)
    for name, cfg in profiles.items():
        det = cfg.get("detect")
        if det and (d / det).exists():
            return name
    return "generic"


def resolve(stack: str, profiles: dict | None = None) -> dict:
    """The command set for a stack, falling back to generic if the name is unknown."""
    profiles = profiles if profiles is not None else load_profiles()
    return profiles.get(stack) or profiles.get("generic", {})
