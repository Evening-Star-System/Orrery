"""The payload contains exactly the allowed fields and never any identifying data."""

import getpass
import json
import platform
import socket

from orrery.telemetry import consent, payload

ALLOWED = {"id", "schema", "orrery_version", "python", "os", "commands"}


def _home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))


def test_exact_keys(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    p = payload.build({"reconcile": 3})
    assert set(p.keys()) == ALLOWED
    assert p["commands"] == {"reconcile": 3}
    assert p["schema"] == payload.SCHEMA
    assert p["id"] is None  # off by default, so no id


def test_id_present_only_when_enabled(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    tid = consent.enable()
    assert payload.build({})["id"] == tid


def test_no_identifying_data(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    blob = json.dumps(payload.build({"reconcile": 1, "doctor": 2}))
    forbidden = [platform.node(), socket.gethostname(), str(tmp_path)]
    try:
        forbidden.append(getpass.getuser())
    except Exception:
        pass
    for value in forbidden:
        if value:
            assert value not in blob
    # the os field is a family, never the kernel/release string
    if platform.release():
        assert platform.release() not in blob
