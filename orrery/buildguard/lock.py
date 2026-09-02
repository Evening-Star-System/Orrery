"""A cross-session mutex for heavy builds.

One build at a time on this box. Not because two builds cannot run, they can, but
because two builds sized for a machine with headroom will, together, exceed the brake
on the slice they share, and the resulting stall is not self-terminating (see
`orrery.reconciler.checks.memory_headroom`). Serialising is strictly faster than
racing: two builds that thrash each other finish later than the same two run in turn.

`flock` is the primitive, deliberately:

  * The kernel releases it when the holding process dies, by ANY means, including
    SIGKILL and the OOM killer. A lock built from a pidfile or a mkdir sentinel leaks
    on exactly the failure this system exists to survive.
  * It is advisory but process-wide and inherited across exec, so the lock is held for
    the whole lifetime of the build command, not just the guard's own process.

The holder sidecar (`build.holder.json`) is human-readable metadata ONLY: who, what,
where, since when. It is never the source of truth about whether the lock is held.
Truth is a non-blocking flock attempt: if it succeeds, the lock was free and any
sidecar is stale. This split matters because a SIGKILLed build leaves a perfectly
plausible-looking sidecar behind, and believing it would block every future build.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import asdict, dataclass

LOCK_DIR = "/run/orrery"
LOCK_PATH = f"{LOCK_DIR}/build.lock"
HOLDER_PATH = f"{LOCK_DIR}/build.holder.json"


@dataclass
class Holder:
    pid: int
    label: str
    command: str
    session: str | None
    cwd: str
    started_at: float

    @property
    def held_for(self) -> str:
        secs = max(0, int(time.time() - self.started_at))
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


class LockBusy(Exception):
    """Raised when the lock could not be acquired within the timeout."""


class BuildLock:
    def __init__(self, path: str = LOCK_PATH):
        self.path = path
        self._fd: int | None = None

    # -- inspection ----------------------------------------------------------------

    @staticmethod
    def current_holder() -> Holder | None:
        """Who holds the lock right now, or None if it is free.

        Probes the lock itself first; the sidecar is only trusted once the probe has
        confirmed somebody really holds it.
        """
        if not os.path.exists(LOCK_PATH):
            return None
        try:
            fd = os.open(LOCK_PATH, os.O_RDONLY)
        except OSError:
            return None
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                pass  # held by someone: fall through and read the sidecar
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
                return None  # we got it, so it was free; any sidecar is stale
        finally:
            os.close(fd)

        try:
            with open(HOLDER_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return Holder(**data)
        except (OSError, ValueError, TypeError):
            # Held, but we cannot say by whom. Still a real hold.
            return Holder(pid=0, label="unknown", command="?", session=None,
                          cwd="?", started_at=time.time())

    # -- acquisition ---------------------------------------------------------------

    def acquire(self, holder: Holder, timeout: int | None = None,
                on_wait=None, poll: float = 5.0) -> None:
        """Take the lock, waiting up to `timeout` seconds (None = forever).

        `on_wait(holder, waited)` is called about every `poll` seconds while blocked,
        so a caller can show the operator who they are waiting behind instead of
        appearing hung.
        """
        os.makedirs(LOCK_DIR, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        started = time.monotonic()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                waited = time.monotonic() - started
                if timeout is not None and waited >= timeout:
                    os.close(fd)
                    raise LockBusy(f"still held after {int(waited)}s")
                if on_wait:
                    try:
                        on_wait(self.current_holder(), waited)
                    except Exception:
                        pass  # a reporting failure must never break the wait loop
                time.sleep(poll)
        self._fd = fd
        try:
            with open(HOLDER_PATH, "w", encoding="utf-8") as fh:
                json.dump(asdict(holder), fh)
        except OSError:
            pass  # metadata is a convenience; the lock itself is what matters

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            # Clear the sidecar BEFORE dropping the lock, so no one can observe a free
            # lock still advertising a holder.
            try:
                os.unlink(HOLDER_PATH)
            except OSError:
                pass
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False
