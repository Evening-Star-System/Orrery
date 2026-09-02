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


def render_json(result: Result) -> str:
    payload = {
        "box": result.box,
        "generated_by": "orrery-reconciler",
        "worst": result.worst.label,
        "clean": result.clean,
        "exit_code": result.exit_code,
        "summary": {k: v for k, v in result.counts().items() if v},
        "findings": [f.as_dict() for f in result.findings],
    }
    return json.dumps(payload, indent=2)
