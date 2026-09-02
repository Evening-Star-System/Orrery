"""The one bounded runner for a lock's probe command.

Extracted verbatim from the behavior-lock check's dev-only local mode so capture, probe,
and that local mode all run a consumer command the same single way. The bound is a
stripped environment (only PATH and HOME reach the command) and a hard timeout; the
command runs with the repo root as its working directory and its last non-empty stdout
line, trimmed, is the canonical value. A non-zero exit, a timeout, a failure to start,
or empty output is a PROBLEM, never a value: a probe that did not cleanly produce an
answer must never be mistaken for one.

This is not a sandbox. It does not make the tree read-only or cut off the network; it
is the authoring-time run of a command the developer already trusts, in their own repo.
The gate never runs it (the check adjudicates a consumer-produced results file instead),
which is the posture that keeps the judge hermetic. Heavier isolation, if a probe ever
needs it, belongs in the consumer's own command, not here.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

DEFAULT_TIMEOUT = 120
MAX_TIMEOUT = 900


@dataclass(frozen=True)
class ProbeResult:
    """Exactly one of `value` / `problem` is set. `value` is the canonical observed
    string; `problem` explains why there is no value to judge."""

    value: str | None
    problem: str | None

    @property
    def ok(self) -> bool:
        return self.problem is None


def resolve_timeout(raw) -> int:
    """A lock's optional `timeout`, coerced and clamped. A missing or unparseable value
    falls back to the default rather than raising, matching the check's tolerance for a
    hand-edited manifest."""
    try:
        return min(int(raw), MAX_TIMEOUT) if raw is not None else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def run_probe(command, cwd: str, timeout=None, capture: str = "stdout-line") -> ProbeResult:
    """Run one lock's command under the bound and return its canonical value or a problem.

    `capture` is the only supported reading of the output for now: `stdout-line` takes the
    last non-empty stdout line, trimmed. An unknown capture is a problem, not a guess.
    """
    if not command:
        return ProbeResult(None, "lock has no 'command' to run")
    if capture != "stdout-line":
        return ProbeResult(None, f"unsupported capture '{capture}'")

    seconds = resolve_timeout(timeout)
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    try:
        proc = subprocess.run(
            ["/bin/sh", "-c", str(command)],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=seconds,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(None, f"probe timed out after {seconds}s")
    except OSError as exc:
        return ProbeResult(None, f"probe could not start ({exc.__class__.__name__})")

    if proc.returncode != 0:
        return ProbeResult(None, f"probe exited {proc.returncode}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return ProbeResult(None, "probe produced no stdout")
    return ProbeResult(lines[-1].strip(), None)
