"""Render a Result as human text or as JSON. Pure formatting, no I/O decisions."""

from __future__ import annotations

import json

from .engine import Result
from .model import Severity

_GLYPH = {
    Severity.OK: "ok  ",
    Severity.INFO: "info",
    Severity.WARN: "warn",
    Severity.DRIFT: "DRIFT",
    Severity.FAIL: "FAIL",
}


def render_human(result: Result, exit_code: int | None = None) -> str:
    # The summary reports the ACTUAL process exit, which an enforcer decides. Defaults to the
    # verdict's own exit_code so a caller that does not pass one (or a plain gate run) is
    # unchanged; report-only mode passes 0 so the line does not claim a failure it will not cause.
    code = result.exit_code if exit_code is None else exit_code
    lines: list[str] = [f"reconciler: {result.box}", ""]
    by_check: dict[str, list] = {}
    for f in result.findings:
        by_check.setdefault(f.check_id, []).append(f)
    for check_id in sorted(by_check):
        lines.append(f"[{check_id}]")
        findings = sorted(by_check[check_id], key=lambda f: f.severity, reverse=True)
        for f in findings:
            detail = ""
            if f.expected is not None or f.observed is not None:
                detail = f"  (expected {f.expected!r}, observed {f.observed!r})"
            lines.append(f"  {_GLYPH[f.severity]:5} {f.subject}: {f.message}{detail}")
        lines.append("")
    counts = result.counts()
    summary = " ".join(f"{k}={v}" for k, v in counts.items() if v)
    verdict = "CLEAN" if result.clean else "DRIFT DETECTED"
    lines.append(f"summary: {summary or 'no findings'}  ->  {verdict} (exit {code})")
    return "\n".join(lines)


def _esc(value: str) -> str:
    # Prometheus label-value escaping: backslash, double-quote, newline.
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_prometheus(result: Result, now: float) -> str:
    """Prometheus exposition format. Pure over the Result; `now` is the wall clock, passed in.

    Severity is an ordered IntEnum, so it maps straight to a gauge value; the legend is in HELP.
    Metrics carry check ids, box names, and subjects (non-secret identities the reconciler already
    reports), never secret values, consistent with the value-blind invariant.
    """
    box = _esc(result.box)
    counts = result.counts()  # {severity label: count}
    drift_total = sum(1 for f in result.findings if f.severity >= Severity.DRIFT)
    lines: list[str] = []

    def block(name: str, help_text: str, samples: list[str]) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.extend(samples)

    block(
        "orrery_check_status",
        "Reconciler finding severity (0 ok, 1 info, 2 warn, 3 drift, 4 fail).",
        [
            f'orrery_check_status{{box="{box}",check="{_esc(f.check_id)}",subject="{_esc(f.subject)}"}} {int(f.severity)}'
            for f in result.findings
        ],
    )
    block(
        "orrery_findings",
        "Count of findings at each severity.",
        [
            f'orrery_findings{{box="{box}",severity="{sev.label.lower()}"}} {counts.get(sev.label, 0)}'
            for sev in Severity
        ],
    )
    block("orrery_worst_severity", "Worst finding severity across the run.",
          [f'orrery_worst_severity{{box="{box}"}} {int(result.worst)}'])
    block("orrery_clean", "1 if the run is clean (worst at or below info), else 0.",
          [f'orrery_clean{{box="{box}"}} {1 if result.clean else 0}'])
    block("orrery_drift_total", "Findings at drift or worse (the number to alert on).",
          [f'orrery_drift_total{{box="{box}"}} {drift_total}'])
    block("orrery_last_run_timestamp_seconds", "Unix time the reconcile ran.",
          [f'orrery_last_run_timestamp_seconds{{box="{box}"}} {int(now)}'])
    block("orrery_up", "1 when a reconcile produced output.",
          [f'orrery_up{{box="{box}"}} 1'])
    return "\n".join(lines) + "\n"


def render_prometheus_error(box: str = "unknown") -> str:
    """A minimal exposition when a reconcile could not even run (bad profile): up = 0."""
    b = _esc(box)
    return (
        "# HELP orrery_up 1 when a reconcile produced output.\n"
        "# TYPE orrery_up gauge\n"
        f'orrery_up{{box="{b}"}} 0\n'
    )


def _result_payload(result: Result) -> dict:
    return {
        "box": result.box,
        "worst": result.worst.label,
        "clean": result.clean,
        "exit_code": result.exit_code,
        "summary": {k: v for k, v in result.counts().items() if v},
        "findings": [f.as_dict() for f in result.findings],
    }


def render_json(result: Result) -> str:
    return json.dumps({"generated_by": "orrery-reconciler", **_result_payload(result)}, indent=2)


# --- fleet: many profiles rolled into one verdict ---------------------------------------
# These reuse the single-profile renderers above (one mechanism, many uses). Import the
# fleet type lazily inside the functions so report has no import-time dependency on it.


def render_fleet_human(fleet, exit_code: int | None = None) -> str:
    """A scannable roll-up: one status line per profile, then the findings of only the ones
    that need attention (a clean profile's OK findings are noise in a fleet view), then a
    summary that states coverage. Legible to a human at a glance; the JSON form serves a
    machine."""
    code = fleet.exit_code if exit_code is None else exit_code
    lines: list[str] = ["reconciler fleet", ""]
    for run in fleet.runs:
        if run.result is None:
            lines.append(f"  ERROR {run.box}: could not load ({run.error})")
        elif run.result.clean:
            summary = " ".join(f"{k}={v}" for k, v in run.result.counts().items() if v)
            lines.append(f"  ok    {run.box}: clean ({summary or 'no findings'})")
        else:
            summary = " ".join(f"{k}={v}" for k, v in run.result.counts().items() if v)
            lines.append(f"  DRIFT {run.box}: {summary}")
    dirty = fleet.dirty
    if dirty:
        lines.append("")
        for run in dirty:
            if run.result is None:
                continue  # already reported above; nothing to expand
            block = render_human(run.result, run.result.exit_code)
            lines.append("--- " + run.box + " " + "-" * max(4, 60 - len(run.box)))
            lines.append(block)
    clean_n = sum(1 for r in fleet.runs if r.clean)
    total = len(fleet.runs)
    verdict = "CLEAN" if fleet.clean else "DRIFT DETECTED"
    lines.append("")
    lines.append(
        f"fleet: {total} profile(s)  ->  {clean_n} clean, {len(dirty)} need attention"
        f"  ->  {verdict} (exit {code})"
    )
    return "\n".join(lines)


def render_fleet_json(fleet) -> str:
    profiles = [
        {
            "path": r.path,
            "box": r.box,
            "clean": r.clean,
            "error": r.error,
            "result": _result_payload(r.result) if r.result is not None else None,
        }
        for r in fleet.runs
    ]
    payload = {
        "generated_by": "orrery-reconciler",
        "kind": "fleet",
        "clean": fleet.clean,
        "exit_code": fleet.exit_code,
        "summary": {
            "profiles": len(fleet.runs),
            "clean": sum(1 for r in fleet.runs if r.clean),
            "need_attention": len(fleet.dirty),
        },
        "profiles": profiles,
    }
    return json.dumps(payload, indent=2)


def render_fleet_prometheus(fleet, now: float) -> str:
    """One exposition block per profile. Each carries its own box label, which is exactly how
    Prometheus distinguishes series, so a fleet is naturally many boxes. An unloadable profile
    still emits `orrery_up 0` under its path, so a gap is scrapeable, not invisible."""
    parts: list[str] = []
    for run in fleet.runs:
        if run.result is not None:
            parts.append(render_prometheus(run.result, now))
        else:
            parts.append(render_prometheus_error(run.box))
    return "".join(parts)
