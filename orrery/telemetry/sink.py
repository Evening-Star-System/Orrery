"""The sink: POST the payload to the configured endpoint, batched and fail-silent.

Collector-agnostic: it sends the exact payload from payload.py as JSON to whatever endpoint
the user configured. If telemetry is off, no endpoint is set, or nothing is queued, it does
nothing. A send never blocks a real command and never raises: any network error just leaves
the counts queued for next time. (No collector endpoint ships by default, so an opted-in
install still sends nothing until one is set; the collector is a deferred, deliberate step.)
"""

from __future__ import annotations

import json

from .. import __version__
from . import consent, counters, payload


def flush(timeout: float = 4.0) -> bool:
    """Send queued counts. Returns True only if a send succeeded and the queue was cleared."""
    if not consent.is_enabled():
        return False
    endpoint = consent.endpoint()
    if not endpoint:
        return False
    counts = counters.snapshot()
    if not counts:
        return False

    body = json.dumps(payload.build(counts)).encode("utf-8")
    try:
        import urllib.request

        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"ess-orrery/{__version__}",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            ok = 200 <= resp.status < 300
    except Exception:
        return False  # fail-silent: telemetry never breaks or slows a command

    if ok:
        counters.clear()
    return ok
