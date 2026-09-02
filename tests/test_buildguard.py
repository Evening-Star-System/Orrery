import fcntl
import json
import os
import time

import pytest

from orrery.buildguard import lock as lockmod
from orrery.buildguard.lock import BuildLock, Holder, LockBusy
from orrery.buildguard.probe import headroom, human

GB = 1024 ** 3
MB = 1024 ** 2


@pytest.fixture
def lockpaths(tmp_path, monkeypatch):
    lp = str(tmp_path / "build.lock")
    hp = str(tmp_path / "build.holder.json")
    monkeypatch.setattr(lockmod, "LOCK_DIR", str(tmp_path))
    monkeypatch.setattr(lockmod, "LOCK_PATH", lp)
    monkeypatch.setattr(lockmod, "HOLDER_PATH", hp)
    return lp, hp


def _holder(label="test-build"):
    return Holder(pid=os.getpid(), label=label, command="make all",
                  session="proj-x", cwd="/tmp", started_at=time.time())


# -- inspection ---------------------------------------------------------------------

def test_no_lock_file_means_free(lockpaths):
    assert BuildLock.current_holder() is None


def test_held_lock_reports_its_holder(lockpaths):
    lp, _ = lockpaths
    with BuildLock(lp) as lk:
        lk.acquire(_holder("widget-web"))
        h = BuildLock.current_holder()
        assert h is not None
        assert h.label == "widget-web"
        assert h.session == "proj-x"


def test_stale_sidecar_over_a_free_lock_reads_as_free(lockpaths):
    """The property that keeps a SIGKILLed build from blocking the box forever.

    A build killed by the OOM killer leaves a perfectly plausible holder file behind.
    Truth is the flock probe, never the sidecar.
    """
    lp, hp = lockpaths
    open(lp, "w").close()
    with open(hp, "w") as fh:
        json.dump({"pid": 999999, "label": "ghost", "command": "gradle",
                   "session": "proj-dead", "cwd": "/", "started_at": time.time()}, fh)
    assert BuildLock.current_holder() is None


def test_held_lock_with_unreadable_sidecar_still_reads_as_held(lockpaths):
    """Losing the metadata must never downgrade a real hold to 'free'."""
    lp, hp = lockpaths
    fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with open(hp, "w") as fh:
            fh.write("{ this is not json")
        h = BuildLock.current_holder()
        assert h is not None
        assert h.label == "unknown"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# -- acquisition --------------------------------------------------------------------

def test_release_frees_the_lock_and_clears_the_sidecar(lockpaths):
    lp, hp = lockpaths
    lk = BuildLock(lp)
    lk.acquire(_holder())
    assert os.path.exists(hp)
    lk.release()
    assert not os.path.exists(hp)
    assert BuildLock.current_holder() is None


def test_acquire_times_out_when_another_holder_has_it(lockpaths):
    """flock is per open-file-description, so a second fd here really does contend."""
    lp, _ = lockpaths
    fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        lk = BuildLock(lp)
        with pytest.raises(LockBusy):
            lk.acquire(_holder(), timeout=1, poll=0.2)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_on_wait_is_called_while_blocked(lockpaths):
    lp, _ = lockpaths
    fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    calls = []
    try:
        lk = BuildLock(lp)
        with pytest.raises(LockBusy):
            lk.acquire(_holder(), timeout=1, poll=0.2,
                       on_wait=lambda h, w: calls.append(w))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert calls, "on_wait should report progress while blocked"


def test_a_failing_on_wait_does_not_break_the_wait_loop(lockpaths):
    """Reporting is a convenience; it must never be able to abort a build's wait."""
    lp, _ = lockpaths
    fd = os.open(lp, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)

    def boom(h, w):
        raise RuntimeError("reporting blew up")

    try:
        lk = BuildLock(lp)
        with pytest.raises(LockBusy):  # LockBusy, NOT RuntimeError
            lk.acquire(_holder(), timeout=1, poll=0.2, on_wait=boom)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_release_is_idempotent(lockpaths):
    lp, _ = lockpaths
    lk = BuildLock(lp)
    lk.acquire(_holder())
    lk.release()
    lk.release()  # must not raise


# -- probe --------------------------------------------------------------------------

def _write_slice(d, current, high, maximum, swap_cur, swap_max, file_cache, anon):
    def v(x):
        return "max\n" if x is None else f"{x}\n"

    (d / "memory.current").write_text(v(current))
    (d / "memory.high").write_text(v(high))
    (d / "memory.max").write_text(v(maximum))
    (d / "memory.swap.current").write_text(v(swap_cur))
    (d / "memory.swap.max").write_text(v(swap_max))
    (d / "memory.stat").write_text(f"anon {anon}\nfile {file_cache}\n")
    (d / "memory.swap.events").write_text("high 0\nmax 0\nfail 42\n")
    (d / "memory.pressure").write_text(
        "some avg10=2.0 avg60=3.0 avg300=4.0 total=1\n"
        "full avg10=1.5 avg60=2.5 avg300=3.5 total=1\n"
    )


def test_headroom_parses_a_slice(tmp_path):
    _write_slice(tmp_path, 3 * GB, 8 * GB, 10 * GB, 0, 1 * GB, 900 * MB, 2 * GB)
    h = headroom(str(tmp_path))
    assert h.current == 3 * GB
    assert h.high == 8 * GB
    # headroom = high - (current - reclaimable file cache) = 8 - (3 - 0.9)
    assert h.free_to_brake == 5 * GB + 900 * MB
    assert h.file_cache == 900 * MB
    assert h.psi_full_avg300 == 3.5
    assert h.swap_fail == 42


def test_reclaimable_cache_does_not_shrink_headroom(tmp_path):
    # The 2026-08-21 stall: a slice sitting near memory.high almost entirely on
    # page cache should still read as having room, because that cache is evicted
    # under pressure rather than pushing the slice into throttle.
    #   current 7G = 3G anon + 4G file cache, high 8G.
    # Naive high-current = 1G (would WAIT); cache-aware = 8 - (7 - 4) = 5G (GO).
    _write_slice(tmp_path, 7 * GB, 8 * GB, 10 * GB, 0, 1 * GB, 4 * GB, 3 * GB)
    h = headroom(str(tmp_path))
    assert h.free_to_brake == 5 * GB


def test_headroom_treats_max_as_no_limit(tmp_path):
    _write_slice(tmp_path, 3 * GB, None, None, 0, None, 900 * MB, 2 * GB)
    h = headroom(str(tmp_path))
    assert h.high is None
    assert h.free_to_brake is None  # no brake means no meaningful headroom figure


def test_headroom_on_a_missing_slice_reports_a_note_not_a_crash(tmp_path):
    h = headroom(str(tmp_path / "nope"))
    assert h.current is None
    assert h.notes


def test_human_formats_bytes_and_none():
    assert human(None) == "max"
    assert human(0) == "0B"
    assert human(2 * GB) == "2.00G"
