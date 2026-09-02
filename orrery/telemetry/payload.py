"""The payload chokepoint: the ONE place a telemetry payload is assembled.

Because every send is built here and nowhere else, the exact set of fields that can ever
leave is fixed and testable. It is deliberately tiny: the anonymous id, the schema version,
the orrery and Python versions, the OS family, and per-command counts. It has no access to
paths, hostnames, usernames, profiles, box or org names, or reconciler output, so none of
those can appear in a send even by mistake. `telemetry status` prints exactly this object.
"""

from __future__ import annotations

import platform
import sys

from .. import __version__
from . import consent

SCHEMA = 1


def build(counts: dict) -> dict:
    return {
        "id": consent.install_id(),
        "schema": SCHEMA,
        "orrery_version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        # family only (Linux/Darwin/Windows), never the release, node name, or hostname
        "os": platform.system().lower(),
        "commands": {str(k): int(v) for k, v in sorted(counts.items())},
    }
