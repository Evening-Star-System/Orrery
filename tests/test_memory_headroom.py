from orrery.reconciler.checks.memory_headroom import MemoryHeadroomCheck
from orrery.reconciler.model import Severity

SLICE = "/sys/fs/cgroup/user.slice/user-0.slice"
GB = 1024 ** 3
MB = 1024 ** 2


class FakeBox:
    """Files the check would read, without needing a real cgroup tree."""

    def __init__(self, files: dict):
        self.files = files

    def exists(self, path: str) -> bool:
        return path in self.files

    def read_text(self, path: str) -> str | None:
        return self.files.get(path)

    def list_files(self, root: str, max_files: int = 2000):
        return None

    def file_meta(self, path: str):
        return None


def _files(current, high, maximum, swap_cur, swap_max, file_cache, anon,
           psi_full_300=1.0, swap_fail=0):
    def v(x):
        return "max\n" if x is None else f"{x}\n"

    return {
        f"{SLICE}/memory.current": v(current),
        f"{SLICE}/memory.high": v(high),
        f"{SLICE}/memory.max": v(maximum),
        f"{SLICE}/memory.swap.current": v(swap_cur),
        f"{SLICE}/memory.swap.max": v(swap_max),
        f"{SLICE}/memory.stat": f"anon {anon}\nfile {file_cache}\nslab 1000\n",
        f"{SLICE}/memory.swap.events": f"high 0\nmax 0\nfail {swap_fail}\n",
        f"{SLICE}/memory.pressure": (
            "some avg10=1.0 avg60=1.0 avg300=1.0 total=1\n"
            f"full avg10=1.0 avg60=1.0 avg300={psi_full_300} total=1\n"
        ),
    }


def _run(files, **opts):
    entry = {"name": "root sessions", "path": SLICE}
    entry.update(opts)
    return MemoryHeadroomCheck().run({"slices": [entry]}, FakeBox(files))


def test_healthy_slice_is_ok():
    (f,) = _run(_files(3 * GB, 8 * GB, 10 * GB, 0, 1 * GB, 900 * MB, 2 * GB))
    assert f.severity == Severity.OK


def test_the_2026_08_20_composition_is_fail():
    """Brake below wall + swap at ceiling + collapsed cache = unrecoverable stall.

    These are the real numbers off work-box at 11:14 on 2026-08-20.
    """
    (f,) = _run(_files(
        current=8591085568, high=8589934592, maximum=10737418240,
        swap_cur=1148919808, swap_max=1073741824,
        file_cache=1904640, anon=8380723200,
        psi_full_300=73.56, swap_fail=57070433,
    ))
    assert f.severity == Severity.FAIL
    assert "OOM killer can never fire" in f.message
    assert "swap_fail=57070433" in f.observed


def test_collapsed_cache_while_stalled_is_fail_even_without_a_wall():
    """No MemoryMax at all, so the composition rule cannot apply. Still thrashing."""
    (f,) = _run(_files(
        current=8 * GB, high=8 * GB, maximum=None,
        swap_cur=0, swap_max=None,
        file_cache=2 * MB, anon=8 * GB, psi_full_300=70.0,
    ))
    assert f.severity == Severity.FAIL
    assert "re-reading from disk" in f.message


def test_brake_engaged_but_cache_intact_is_drift_not_fail():
    """Pinned at the brake is degraded, but reclaim still has somewhere to go."""
    (f,) = _run(_files(8 * GB, 8 * GB, 10 * GB, 0, 1 * GB, 2 * GB, 5 * GB))
    assert f.severity == Severity.DRIFT
    assert "pinned against its MemoryHigh brake" in f.message


def test_swap_at_ceiling_alone_is_drift():
    (f,) = _run(_files(4 * GB, 8 * GB, 10 * GB, 1 * GB, 1 * GB, 2 * GB, 3 * GB))
    assert f.severity == Severity.DRIFT
    assert "swap is at its ceiling" in f.message


def test_high_psi_alone_is_drift():
    (f,) = _run(_files(4 * GB, 8 * GB, 10 * GB, 0, 1 * GB, 2 * GB, 3 * GB,
                       psi_full_300=55.0))
    assert f.severity == Severity.DRIFT
    assert "stalling on memory" in f.message


def test_absent_slice_is_drift_not_crash():
    (f,) = _run({})
    assert f.severity == Severity.DRIFT
    assert "not present" in f.message


def test_no_slices_declared_is_warn():
    findings = MemoryHeadroomCheck().run({}, FakeBox({}))
    assert findings[0].severity == Severity.WARN


def test_unparseable_files_degrade_to_warn_not_exception():
    files = {f"{SLICE}/memory.current": "not-a-number\n"}
    (f,) = _run(files)
    assert f.severity == Severity.WARN


def test_thresholds_are_overridable_per_slice():
    """A box with a legitimately small cache must be able to raise the floor."""
    base = _files(4 * GB, 8 * GB, 10 * GB, 0, 1 * GB, 100 * MB, 3 * GB,
                  psi_full_300=1.0)
    (default,) = _run(base)
    assert default.severity == Severity.OK  # 100M cache, but PSI is fine
    (strict,) = _run(base, min_file_cache_mb=512, psi_full_avg300_max=0.5)
    assert strict.severity == Severity.FAIL
