"""The sink sends nothing when off or with no endpoint, sends and clears on success, and
retains the queue on failure. Never touches the real network."""

import json
import urllib.error
import urllib.request

from orrery import home
from orrery.telemetry import consent, counters, sink

ENDPOINT = "https://collector.example/telemetry"


def _home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))


def _set_endpoint(url):
    settings = home.read_settings()
    settings["telemetry"]["endpoint"] = url
    home.write_settings(settings)


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_off_never_sends(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: calls.append(1) or _Resp())
    assert sink.flush() is False
    assert calls == []


def test_empty_endpoint_hard_disables(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    consent.enable()
    _set_endpoint("")  # explicit empty endpoint = opted in but send nowhere
    counters.bump("reconcile")
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: calls.append(1) or _Resp())
    assert sink.flush() is False
    assert calls == []


def test_default_endpoint_is_used_when_unset(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    consent.enable()  # endpoint left unset -> the default collector
    counters.bump("reconcile")
    captured = {}
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda request, timeout=None: captured.update(url=request.full_url) or _Resp(),
    )
    assert sink.flush() is True
    assert captured["url"] == consent._DEFAULT_ENDPOINT


def test_flush_sends_and_clears(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    consent.enable()
    _set_endpoint(ENDPOINT)
    counters.bump("reconcile")
    counters.bump("doctor")
    captured = {}

    def fake(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = request.data
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert sink.flush() is True
    assert captured["url"] == ENDPOINT
    assert json.loads(captured["body"])["commands"] == {"doctor": 1, "reconcile": 1}
    assert counters.snapshot() == {}  # cleared on success


def test_send_failure_retains_queue(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    consent.enable()
    _set_endpoint(ENDPOINT)
    counters.bump("reconcile")

    def boom(*a, **k):
        raise urllib.error.URLError("collector down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert sink.flush() is False
    assert counters.snapshot() == {"reconcile": 1}  # retained for next time
