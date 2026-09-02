"""The report-tier enforcers open-core ships, and the registry that resolves one by name.

Both are report-only in the threat-model sense: they never mutate a box. They differ only
in whether a not-clean verdict stops the caller. `gate` is today's reconcile behavior,
named; `report` is the softer observe-only mode for a monitor or dashboard.
"""

from __future__ import annotations

from .base import Enforcer, Verdict


class GateEnforcer:
    """Block on drift. Returns the verdict's exit code, so a not-clean verdict (drift or
    worse) stops a pipeline. Changes nothing itself; the block is the caller refusing to
    proceed. This is the behavior the behavior-lock CI gate relies on, and the default."""

    name = "gate"

    def act(self, verdict: Verdict) -> int:
        return verdict.exit_code


class ReportEnforcer:
    """Observe only. Returns 0 regardless of the verdict, so the findings are emitted but no
    build fails. For a monitor or dashboard that wants the signal without gating on it."""

    name = "report"

    def act(self, verdict: Verdict) -> int:
        return 0


_ENFORCERS: dict[str, type] = {cls.name: cls for cls in (GateEnforcer, ReportEnforcer)}


def known_names() -> list[str]:
    return sorted(_ENFORCERS)


def get_enforcer(name: str) -> Enforcer:
    """Resolve an enforcer by name. Raises ValueError on an unknown name (the CLI also
    constrains the choice, so this guards a programmatic caller)."""
    try:
        return _ENFORCERS[name]()
    except KeyError:
        raise ValueError(f"unknown enforcer {name!r} (known: {', '.join(known_names())})") from None
