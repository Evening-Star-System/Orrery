"""Counters are a no-op (and write nothing) when telemetry is off; they accumulate and
clear when it is on."""

from orrery.telemetry import consent, counters


def _home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))


def test_off_is_a_noop(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    counters.bump("reconcile")
    assert counters.snapshot() == {}
    assert not (tmp_path / "state").exists()  # nothing written when off


def test_on_accumulates_and_clears(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    consent.enable()
    counters.bump("reconcile")
    counters.bump("reconcile")
    counters.bump("doctor")
    assert counters.snapshot() == {"reconcile": 2, "doctor": 1}
    counters.clear()
    assert counters.snapshot() == {}
