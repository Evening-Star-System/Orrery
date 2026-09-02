"""Telemetry consent is off by default, mints an anonymous id only when turned on, and
deletes it when turned off."""

from orrery.telemetry import consent


def _home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))


def test_default_off(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    assert consent.is_enabled() is False
    assert consent.install_id() is None
    assert consent.decision_recorded() is False
    # unset endpoint resolves to the built-in default collector (only used when opted in)
    assert consent.endpoint() == consent._DEFAULT_ENDPOINT


def test_enable_mints_id(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    tid = consent.enable()
    assert consent.is_enabled() is True
    assert consent.install_id() == tid and len(tid) >= 32
    assert consent.decision_recorded() is True


def test_enable_is_idempotent(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    assert consent.enable() == consent.enable()


def test_disable_clears_id(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    consent.enable()
    consent.disable()
    assert consent.is_enabled() is False
    assert consent.install_id() is None
    assert consent.decision_recorded() is True  # a choice (off) is still on record
