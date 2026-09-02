"""Orrery's durable home: where a user's setup lives, outside the installed package.

Resolved from the environment, never invented. Two roots follow the XDG convention: a
config home for user-owned settings and a state home for tool-managed local state. A
single override, $ORRERY_HOME, relocates both under it. Nothing is created on import or
by an unrelated command; a directory appears only when something is first written, so a
read-only run of `ess-orrery reconcile` never causes a write.

This home holds TOOL state only: settings, an update-check cache, a registry of paths to
back up. It never holds operator IDENTITY. The context subsystem still requires an
explicit --config with no baked default (see context/config.py); the home does not invent
identity, it only remembers preferences the user set here.
"""

from __future__ import annotations

import os
from pathlib import Path

_APP = "orrery"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def config_home() -> Path:
    """User-owned settings live here. Pure: computes a path, touches nothing."""
    override = _env_path("ORRERY_HOME")
    if override is not None:
        return override / "config"
    base = _env_path("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return base / _APP


def state_home() -> Path:
    """Tool-managed local state lives here. Pure: computes a path, touches nothing."""
    override = _env_path("ORRERY_HOME")
    if override is not None:
        return override / "state"
    base = _env_path("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return base / _APP


def ensure_dir(path: Path) -> Path:
    """Create `path` (mode 0700, parents as needed) if absent. The only writer of the home.

    Idempotent. Perms are set only on a directory we create, so we never fight a user who
    deliberately widened them later.
    """
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if not existed:
        try:
            path.chmod(0o700)
        except OSError:
            pass
    return path


# ---- settings.toml / registry.toml (human-readable, hand-editable) -------------------

def settings_path() -> Path:
    return config_home() / "settings.toml"


def registry_path() -> Path:
    return config_home() / "registry.toml"


def read_settings() -> dict:
    return _read_toml(settings_path())


def write_settings(data: dict) -> None:
    _write_toml(settings_path(), data)


def read_registry() -> dict:
    return _read_toml(registry_path())


def write_registry(data: dict) -> None:
    _write_toml(registry_path(), data)


def _read_toml(path: Path) -> dict:
    """Absent or unreadable file -> empty dict. A read never creates anything."""
    if not path.exists():
        return {}
    import tomllib

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _write_toml(path: Path, data: dict) -> None:
    """Atomic write (tmp + replace), 0600, creating the home on first write."""
    ensure_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(toml_dumps(data), encoding="utf-8")
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


# ---- a minimal, correct TOML emitter for the shapes we write -------------------------
# We write only flat scalars, lists of scalars, and one level of [table]. tomllib reads
# TOML but cannot write it; rather than add a dependency we emit exactly what we use and
# round-trip test it (write -> tomllib.loads equals the original).

def toml_dumps(data: dict) -> str:
    scalars: list[str] = []
    tables: list[tuple[str, dict]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            scalars.append(f"{_toml_key(key)} = {_toml_val(value)}")
    parts: list[str] = []
    if scalars:
        parts.append("\n".join(scalars))
    for name, table in tables:
        body = "\n".join(f"{_toml_key(k)} = {_toml_val(v)}" for k, v in table.items())
        parts.append(f"[{_toml_key(name)}]\n{body}" if body else f"[{_toml_key(name)}]")
    return ("\n\n".join(parts)).strip() + "\n"


def _toml_key(key: str) -> str:
    # bare keys are safe for our identifiers; quote anything with a surprise character
    if key and all(c.isalnum() or c in "-_" for c in key):
        return key
    return _toml_str(key)


def _toml_val(value) -> str:
    if isinstance(value, bool):  # bool before int: bool is a subclass of int
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return _toml_str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_val(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def _toml_str(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
