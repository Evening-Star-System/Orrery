"""Report-only conformance engine.

Proves the box still matches its declared shape. Generalizes the gate-conformance
pattern (declared AND its probe passes, continuously) from guards to the whole
declared shape. Read-only in v0: it measures and reports, it never mutates.
"""

from .engine import Engine, run_profile
from .model import Finding, Severity

__all__ = ["Engine", "run_profile", "Finding", "Severity"]
