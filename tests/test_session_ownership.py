from orrery.reconciler.box import LocalBox
from orrery.reconciler.checks.session_ownership import SessionOwnershipCheck
from orrery.reconciler.model import Severity


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


def _run(units, box=None):
    return SessionOwnershipCheck().run({"units": units}, box or LocalBox())


def _cg(unit, slice_name="system.slice"):
    return f"/sys/fs/cgroup/{slice_name}/{unit}/cgroup.procs"


def test_owns_expected_process_is_ok():
    box = FakeBox({
        _cg("tmux-sessions.service"): "100\n101\n",
        "/proc/100/comm": "tmux: server\n",
        "/proc/101/comm": "bash\n",
    })
    (f,) = _run([{"unit": "tmux-sessions.service", "expect_process": "tmux"}], box)
    assert f.severity == Severity.OK
    assert "tmux" in f.message


def test_empty_cgroup_is_fail():
    """The green-unit-over-empty-cgroup bug: active unit, zero owned processes."""
    box = FakeBox({_cg("tmux-sessions.service"): "\n"})
    (f,) = _run([{"unit": "tmux-sessions.service", "expect_process": "tmux"}], box)
    assert f.severity == Severity.FAIL
    assert "no-op" in f.message
    assert f.observed == "0"


def test_owns_processes_but_not_the_expected_one_is_drift():
    box = FakeBox({
        _cg("tmux-sessions.service"): "200\n",
        "/proc/200/comm": "sleep\n",
    })
    (f,) = _run([{"unit": "tmux-sessions.service", "expect_process": "tmux"}], box)
    assert f.severity == Severity.DRIFT
    assert "not the one it is supposed to own" in f.message


def test_missing_cgroup_is_drift():
    (f,) = _run([{"unit": "nope.service", "expect_process": "tmux"}], FakeBox({}))
    assert f.severity == Severity.DRIFT
    assert "not running" in f.message


def test_unreadable_cgroup_warns():
    class Unreadable(FakeBox):
        def exists(self, path):
            return True

        def read_text(self, path):
            return None

    (f,) = _run([{"unit": "x.service"}], Unreadable({}))
    assert f.severity == Severity.WARN


def test_no_expect_process_just_counts():
    box = FakeBox({_cg("x.service"): "1\n2\n3\n"})
    (f,) = _run([{"unit": "x.service"}], box)
    assert f.severity == Severity.OK and "3" in f.message


def test_min_procs_respected():
    box = FakeBox({_cg("x.service"): "1\n"})
    (f,) = _run([{"unit": "x.service", "min_procs": 5}], box)
    assert f.severity == Severity.FAIL


def test_custom_slice_is_used():
    box = FakeBox({
        _cg("session-1.scope", "user.slice/user-0.slice"): "9\n",
        "/proc/9/comm": "tmux: server\n",
    })
    (f,) = _run(
        [{
            "unit": "session-1.scope",
            "slice": "user.slice/user-0.slice",
            "expect_process": "tmux",
        }],
        box,
    )
    assert f.severity == Severity.OK


def test_entry_without_unit_warns():
    (f,) = _run([{"name": "bad"}], FakeBox({}))
    assert f.severity == Severity.WARN


def test_no_units_declared_warns():
    findings = SessionOwnershipCheck().run({"units": []}, LocalBox())
    assert findings and findings[0].severity == Severity.WARN


def test_comm_substring_match_handles_tmux_server():
    """comm is 'tmux: server', so exact matching would false-DRIFT a correct box."""
    box = FakeBox({
        _cg("tmux-sessions.service"): "42\n",
        "/proc/42/comm": "tmux: server\n",
    })
    (f,) = _run([{"unit": "tmux-sessions.service", "expect_process": "tmux"}], box)
    assert f.severity == Severity.OK
