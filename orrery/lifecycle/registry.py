"""The local record of user-owned files to include in a backup.

A user's profiles and context configs live wherever they chose to put them. This registry
is how they opt a path into `ess-orrery backup` without the tool ever scanning their disk on
its own. Stored as `registry.toml` in the config home, hand-editable.
"""

from __future__ import annotations

from pathlib import Path

from ..home import read_registry, write_registry


def list_paths() -> list[str]:
    paths = read_registry().get("paths", [])
    return [str(p) for p in paths] if isinstance(paths, list) else []


def add_path(path: str) -> str:
    """Register an absolute, resolved path. Returns the stored path. Idempotent."""
    resolved = str(Path(path).expanduser().resolve())
    paths = list_paths()
    if resolved not in paths:
        paths.append(resolved)
        paths.sort()
        write_registry({"paths": paths})
    return resolved


def remove_path(path: str) -> bool:
    resolved = str(Path(path).expanduser().resolve())
    paths = list_paths()
    if resolved in paths:
        paths.remove(resolved)
        write_registry({"paths": paths})
        return True
    return False
