"""Reachability probing, kept separate from Box.

Box answers "what is on this one target's filesystem". A Prober answers "can the
machine we run on reach another box", which is about edges between boxes, not a
single box's contents. The fleet-reach check uses a Prober; nothing else does.

SshProber runs the same read-only probe fleet-audit uses: `ssh host true` under
BatchMode, so an unauthorized or passphrase-only key fails non-interactively rather
than hanging. It never mutates the remote and never raises.
"""

from __future__ import annotations

import subprocess
from typing import Protocol, runtime_checkable


@runtime_checkable
class Prober(Protocol):
    def can_reach(self, host: str, timeout: int) -> bool: ...


class SshProber:
    def can_reach(self, host: str, timeout: int) -> bool:
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    f"ConnectTimeout={timeout}",
                    "--",  # end option parsing: a host starting with - is never read as a flag
                    host,
                    "true",
                ],
                capture_output=True,
                timeout=timeout + 3,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False
