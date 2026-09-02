"""The Prometheus renderer emits valid exposition: one HELP + TYPE per metric, correct severity
mapping and aggregates, escaped label values, and an error form when a reconcile could not run."""

from orrery.reconciler.engine import Result
from orrery.reconciler.model import Finding, Severity
from orrery.reconciler.report import render_prometheus, render_prometheus_error


def _r(findings, box="prod-box"):
    return Result(box=box, findings=findings)


def _parse(text):
    helps, types, samples = [], [], []
    for line in text.splitlines():
        if line.startswith("# HELP "):
            helps.append(line.split()[2])
        elif line.startswith("# TYPE "):
            types.append(line.split()[2])
        elif line and not line.startswith("#"):
            name = line.split("{")[0].split(" ")[0]
            value = line.rsplit(" ", 1)[1]
            samples.append((name, value))
    return helps, types, samples


ALL = {
    "orrery_check_status", "orrery_findings", "orrery_worst_severity", "orrery_clean",
    "orrery_drift_total", "orrery_last_run_timestamp_seconds", "orrery_up",
}


def test_valid_exposition_and_mapping():
    out = render_prometheus(
        _r([
            Finding("fleet-reach", Severity.OK, "box:app-01", "ok"),
            Finding("org-map", Severity.DRIFT, "cfg:x", "disagrees"),
            Finding("floors", Severity.FAIL, "mem", "below floor"),
        ]),
        now=1700000000.0,
    )
    helps, types, samples = _parse(out)
    assert len(helps) == len(set(helps))          # no duplicate HELP
    assert set(helps) == set(types) == ALL        # one HELP + one TYPE per metric
    for _name, value in samples:                  # every sample value is numeric
        float(value)
    assert 'orrery_check_status{box="prod-box",check="org-map",subject="cfg:x"} 3' in out
    assert 'orrery_check_status{box="prod-box",check="floors",subject="mem"} 4' in out
    assert 'orrery_findings{box="prod-box",severity="drift"} 1' in out
    assert 'orrery_findings{box="prod-box",severity="fail"} 1' in out
    assert 'orrery_findings{box="prod-box",severity="ok"} 1' in out
    assert 'orrery_drift_total{box="prod-box"} 2' in out   # drift + fail
    assert 'orrery_worst_severity{box="prod-box"} 4' in out
    assert 'orrery_clean{box="prod-box"} 0' in out
    assert 'orrery_up{box="prod-box"} 1' in out
    assert 'orrery_last_run_timestamp_seconds{box="prod-box"} 1700000000' in out


def test_clean_run():
    out = render_prometheus(_r([Finding("fleet-reach", Severity.OK, "box:a", "ok")]), now=1.0)
    assert 'orrery_clean{box="prod-box"} 1' in out
    assert 'orrery_drift_total{box="prod-box"} 0' in out


def test_label_values_are_escaped():
    weird = 'a"b\\c\nd'  # quote, backslash, newline
    out = render_prometheus(_r([Finding("c", Severity.OK, weird, "m")]), now=1.0)
    assert r'subject="a\"b\\c\nd"' in out
    # no raw newline leaked into the middle of a sample line
    for line in out.splitlines():
        assert line == "" or "\n" not in line


def test_error_exposition():
    out = render_prometheus_error()
    assert 'orrery_up{box="unknown"} 0' in out
    assert "# TYPE orrery_up gauge" in out
