"""Build guard: one heavy build at a time, each inside its own memory ceiling.

Exists because of the work-box stall of 2026-08-20, where two concurrent Widget builds
(Android via Gradle, web via dart2js/dart2wasm) plus eight interactive sessions pinned
a shared slice against its MemoryHigh brake for 1h42m with `oom_kill` at 0 throughout.
See `orrery.reconciler.checks.memory_headroom` for why that state cannot self-recover.
"""

from .lock import BuildLock, Holder, LockBusy
from .probe import Headroom, HeavyProc, headroom, heavy_processes

__all__ = [
    "BuildLock", "Holder", "LockBusy",
    "Headroom", "HeavyProc", "headroom", "heavy_processes",
]
