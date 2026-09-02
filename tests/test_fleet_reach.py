from orrery.reconciler.checks.fleet_reach import FleetReachCheck
from orrery.reconciler.model import Severity


class FakeProber:
    """Answers from a dict, so tests never touch ssh."""

    def __init__(self, reachable: dict[str, bool], raise_on: set[str] | None = None):
        self._reachable = reachable
        self._raise_on = raise_on or set()

    def can_reach(self, host: str, timeout: int) -> bool:
        if host in self._raise_on:
            raise OSError("boom")
        return self._reachable.get(host, False)


def _run(edges, reachable, raise_on=None):
    check = FleetReachCheck(prober=FakeProber(reachable, raise_on))
    return check.run({"edges": edges, "timeout": 1}, box=None)


def test_ok_reachable_is_ok():
    (f,) = _run([{"to": "prod-box", "expect": "ok"}], {"prod-box": True})
    assert f.severity == Severity.OK


def test_ok_unreachable_is_fail():
    (f,) = _run([{"to": "prod-box", "expect": "ok"}], {"prod-box": False})
    assert f.severity == Severity.FAIL
    assert "DOWN" in f.message


def test_denied_unreachable_is_ok():
    (f,) = _run([{"to": "hub-box", "expect": "denied"}], {"hub-box": False})
    assert f.severity == Severity.OK


def test_denied_reachable_is_drift():
    # the security regression: a closed edge reopened
    (f,) = _run([{"to": "hub-box", "expect": "denied"}], {"hub-box": True})
    assert f.severity == Severity.DRIFT
    assert f.expected == "denied" and f.observed == "reachable"


def test_prober_error_warns_never_false_ok():
    (f,) = _run(
        [{"to": "app-box", "expect": "ok"}], {}, raise_on={"app-box"}
    )
    assert f.severity == Severity.WARN


def test_bad_edge_warns():
    (f,) = _run([{"to": "x", "expect": "maybe"}], {"x": True})
    assert f.severity == Severity.WARN


def test_no_edges_warns():
    findings = FleetReachCheck(prober=FakeProber({})).run({"edges": []}, box=None)
    assert findings and findings[0].severity == Severity.WARN
