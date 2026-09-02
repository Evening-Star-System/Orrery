"""What every check looks like.

A check is stateless and read-only. It never raises for a DATA problem: a parse
failure or a surprising file becomes a WARN Finding, because a reconciler that dies
on the first surprise is useless against exactly the drifted box it exists to catch.
The engine additionally wraps run() so an unexpected exception also degrades to WARN.
"""

from __future__ import annotations

from typing import Protocol

from ..box import Box
from ..model import Finding


class Check(Protocol):
    id: str
    title: str

    def run(self, options: dict, box: Box) -> list[Finding]: ...


# Optional, for `profile validate`: a check MAY declare the top-level option keys it
# understands and which of them are required, so a profile with a typo'd or missing
# option surfaces before a run rather than as silent under-checking. A check that does
# not declare these is simply not option-validated (only its id is). Nested keys inside
# list entries (an edge's `to`, a floor's `min`) are out of scope here.
#   option_keys: frozenset[str]    # every top-level key the check reads
#   required_keys: frozenset[str]  # the subset without which the check cannot work
