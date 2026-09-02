"""The Enforcer seam: the narrow interface the engine acts THROUGH after a verdict.

The engine separates DECLARE (a profile, a manifest) from PROVE (a check produces a
verdict), but not PROVE from ACT: until now the reconcile CLI hardcoded the action, print
the findings and exit non-zero on drift. An `Enforcer` is that missing seam. It takes a
verdict and decides what to do about it, returning the process exit code and, for a
richer enforcer, having effects.

Open-core ships the two report-tier enforcers, both of which change nothing on the box:
`gate` (block a pipeline when the verdict is not clean, today's behavior) and `report`
(observe only, never block). A `rotate`/`apply` enforcer is a future implementation of the
SAME interface, gated behind the threat model's fix-dial controls, not a change to it.

The interface is deliberately minimal so open-core is not shaped around the unbuilt
governed-autonomy product: a commercial enforcer that acts below the model takes whatever
extra context it needs (a declared policy, a managed-settings root) in its own constructor
and implements the same `act(verdict) -> int`. This mirrors the read-only `Box` seam,
where `LocalBox` and `SshBox` both answer "read this path" and a new one slotted in with
no engine change. See docs/DECISION-one-engine.md.
"""

from .base import Enforcer, Verdict
from .builtin import GateEnforcer, ReportEnforcer, get_enforcer, known_names

__all__ = [
    "Enforcer",
    "Verdict",
    "GateEnforcer",
    "ReportEnforcer",
    "get_enforcer",
    "known_names",
]
