"""Update detects the install method read-only and builds the right upgrade command; the
version check reads the index on demand and fails soft."""

import json
import urllib.error
import urllib.request

from orrery.lifecycle import update


def test_build_upgrade_cmd():
    assert update.build_upgrade_cmd("dev") is None
    assert update.build_upgrade_cmd("pipx") == ["pipx", "upgrade", "ess-orrery"]
    pip = update.build_upgrade_cmd("pip")
    assert pip[1:] == ["-m", "pip", "install", "--upgrade", "ess-orrery"]


def test_detect_install_from_checkout():
    # the test suite runs from the source checkout (pyproject + .git alongside the package)
    assert update.detect_install() == "dev"


class _Resp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_latest_version_reads_index(monkeypatch, tmp_path):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))
    body = json.dumps({"info": {"version": "9.9.9"}}).encode("utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(body))
    assert update.latest_version() == "9.9.9"
    # result cached to the state home
    assert (tmp_path / "state" / "update-check.json").exists()


def test_latest_version_network_failure_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))

    def boom(*a, **k):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert update.latest_version() is None
