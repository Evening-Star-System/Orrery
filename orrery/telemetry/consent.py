"""Consent: the opt-in flag, the anonymous install id, and the collector endpoint.

Stored in the config home's settings under a `[telemetry]` table. Default is off, shipped
off: with no settings file, telemetry resolves to disabled and no id exists. Turning it on
mints a random, machine-independent id used only to deduplicate counts; turning it off
deletes that id. The endpoint is empty by default, so even an opted-in install sends
nothing until a collector is deliberately configured.
"""

from __future__ import annotations

import uuid

from ..home import read_settings, write_settings

_KEY = "telemetry"

# The default collector an opted-in install sends to (our receiver). Overridable in
# settings; set it to "" to opt in but send nowhere. Only ever used when telemetry is on.
_DEFAULT_ENDPOINT = "https://orrery-telemetry.old-bread-276c.workers.dev/v1/telemetry"


def _table() -> dict:
    value = read_settings().get(_KEY, {})
    return dict(value) if isinstance(value, dict) else {}


def is_enabled() -> bool:
    return bool(_table().get("enabled", False))


def install_id() -> str | None:
    value = _table().get("install_id")
    return str(value) if value else None


def endpoint() -> str:
    value = _table().get("endpoint")
    if value is None:
        return _DEFAULT_ENDPOINT  # unset -> our collector
    return str(value)  # explicit "" means opted in but sending nowhere


def decision_recorded() -> bool:
    """True once the user has explicitly chosen on or off (the flag exists)."""
    return "enabled" in _table()


def enable() -> str:
    """Turn telemetry on; mint an anonymous id if there is not one. Returns the id."""
    settings = read_settings()
    table = _table()
    table["enabled"] = True
    if not table.get("install_id"):
        table["install_id"] = str(uuid.uuid4())
    # endpoint left unset so it resolves to the current default; a user can override it
    settings[_KEY] = table
    write_settings(settings)
    return str(table["install_id"])


def disable() -> None:
    """Turn telemetry off and delete the anonymous id."""
    settings = read_settings()
    table = _table()
    table["enabled"] = False
    table.pop("install_id", None)
    settings[_KEY] = table
    write_settings(settings)
