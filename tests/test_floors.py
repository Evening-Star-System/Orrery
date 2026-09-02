from orrery.reconciler.box import LocalBox
from orrery.reconciler.checks.floors import FloorsCheck
from orrery.reconciler.model import Severity


def _run(floors):
    return FloorsCheck().run({"floors": floors}, LocalBox())


def _mkfiles(tmp_path, n):
    d = tmp_path / "d"
    d.mkdir()
    for i in range(n):
        (d / f"f{i}.txt").write_text("x\n", encoding="utf-8")
    return d


def test_file_count_within_bounds_is_ok(tmp_path):
    d = _mkfiles(tmp_path, 5)
    (f,) = _run([{"name": "c", "path": str(d), "kind": "file_count", "min": 3}])
    assert f.severity == Severity.OK


def test_below_floor_is_fail(tmp_path):
    d = _mkfiles(tmp_path, 2)
    (f,) = _run([{"name": "c", "path": str(d), "kind": "file_count", "min": 10}])
    assert f.severity == Severity.FAIL
    assert f.observed == "2" and f.expected == ">= 10"


def test_above_ceiling_is_warn(tmp_path):
    big = tmp_path / "digest.md"
    big.write_text("\n".join(str(i) for i in range(300)), encoding="utf-8")
    (f,) = _run([{"name": "budget", "path": str(big), "kind": "line_count", "max": 250}])
    assert f.severity == Severity.WARN
    assert "ceiling" in f.message


def test_stale_floor_recalibrate_is_info(tmp_path):
    d = _mkfiles(tmp_path, 50)
    (f,) = _run(
        [{"name": "c", "path": str(d), "kind": "file_count", "min": 5, "recalibrate_ratio": 3.0}]
    )
    assert f.severity == Severity.INFO
    assert "recalibrate" in f.message


def test_missing_path_is_drift(tmp_path):
    (f,) = _run([{"name": "gone", "path": str(tmp_path / "nope"), "kind": "file_count", "min": 1}])
    assert f.severity == Severity.DRIFT and "missing" in f.message


def test_unknown_kind_warns(tmp_path):
    d = _mkfiles(tmp_path, 1)
    (f,) = _run([{"name": "c", "path": str(d), "kind": "weird", "min": 1}])
    assert f.severity == Severity.WARN


def test_line_count_counts_lines(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("a\nb\nc\n", encoding="utf-8")
    (r,) = _run([{"name": "lines", "path": str(f), "kind": "line_count", "min": 3}])
    assert r.severity == Severity.OK and r.message.endswith("(3)")


def test_no_floors_declared_warns():
    findings = FloorsCheck().run({"floors": []}, LocalBox())
    assert findings and findings[0].severity == Severity.WARN
