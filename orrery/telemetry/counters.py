"""Per-command counts, accumulated between runs, flushed on a successful send.

When consent is off (the default), `bump` returns immediately and touches nothing, so an
opted-out install does no telemetry work and writes nothing. When consent is on, counts
accumulate in the state home and are cleared once a send succeeds, so they never grow
unbounded.
"""

from __future__ import annotations

import json

from ..home import ensure_dir, state_home
from . import consent

_QUEUE = "telemetry-queue.json"


def _path():
    return state_home() / _QUEUE


def bump(command: str) -> None:
    if not consent.is_enabled():
        return
    counts = snapshot()
    counts[command] = counts.get(command, 0) + 1
    _save(counts)


def snapshot() -> dict:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}


def _save(counts: dict) -> None:
    try:
        ensure_dir(state_home())
        _path().write_text(json.dumps(counts, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def clear() -> None:
    try:
        _path().unlink()
    except OSError:
        pass
