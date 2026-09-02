"""The two protocols that make the enforcement side a seam.

`Verdict` is structural on purpose: it names only what an enforcer needs to act (is the
verdict clean, and what exit code does it carry), so the enforcer never imports the
reconciler and the same interface serves a different verdict type later (a fleet Result
today, an agent-action verdict when the governed-autonomy layer is built). The reconciler's
`Result` already satisfies it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Verdict(Protocol):
    """What an enforcer reads from a proven result. `clean` is true when the worst finding
    is at or below the clean ceiling; `exit_code` is 0 when clean, non-zero on drift."""

    @property
    def clean(self) -> bool: ...

    @property
    def exit_code(self) -> int: ...


@runtime_checkable
class Enforcer(Protocol):
    """Acts on a verdict. Returns the process exit code and may have effects. The two
    open-core enforcers change nothing on the box; a commercial enforcer may act below the
    model, but always through this same one method."""

    name: str

    def act(self, verdict: Verdict) -> int: ...
