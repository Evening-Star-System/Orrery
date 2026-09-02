"""The durable home resolves from the environment, creates nothing until written, and
its settings round-trip through the minimal TOML emitter."""

import stat
from pathlib import Path

from orrery import home


def _clear(mp):
    for var in ("ORRERY_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        mp.delenv(var, raising=False)


def test_override_relocates_both(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "h"))
    assert home.config_home() == tmp_path / "h" / "config"
    assert home.state_home() == tmp_path / "h" / "state"


def test_xdg_used_when_set(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "c"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "s"))
    assert home.config_home() == tmp_path / "c" / "orrery"
    assert home.state_home() == tmp_path / "s" / "orrery"


def test_defaults_under_home(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setattr(home.Path, "home", staticmethod(lambda: tmp_path))
    assert home.config_home() == tmp_path / ".config" / "orrery"
    assert home.state_home() == tmp_path / ".local" / "state" / "orrery"


def test_resolving_creates_nothing(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "h"))
    home.config_home()
    home.state_home()
    home.read_settings()  # a read must not create anything either
    assert not (tmp_path / "h").exists()


def test_ensure_dir_is_0700(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "h"))
    created = home.ensure_dir(home.config_home())
    assert created.exists()
    assert stat.S_IMODE(created.stat().st_mode) == 0o700


def test_settings_round_trip(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "h"))
    data = {
        "a": "x",
        "n": 3,
        "flag": True,
        "list": ["p", "q"],
        "telemetry": {"enabled": False, "install_id": "abc-1"},
    }
    home.write_settings(data)
    assert home.read_settings() == data
    # written 0600, no stray .tmp left behind
    assert stat.S_IMODE(home.settings_path().stat().st_mode) == 0o600
    assert not home.settings_path().with_name("settings.toml.tmp").exists()


def test_read_absent_is_empty(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "h"))
    assert home.read_settings() == {}
    assert home.read_registry() == {}
