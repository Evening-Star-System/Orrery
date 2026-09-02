"""Backup then restore reproduces the home and registered files; restore refuses to
clobber, rejects an unknown schema, and refuses a traversal path in the archive."""

import io
import json
import shutil
import tarfile

import pytest

from orrery import home
from orrery.lifecycle import backup, registry


def _home(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "home"))


def test_round_trip(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    home.write_settings({"telemetry": {"enabled": True, "install_id": "id-1"}})
    home.ensure_dir(home.state_home())
    (home.state_home() / "update-check.json").write_text('{"latest":"1.0.0"}', encoding="utf-8")
    ext = tmp_path / "profiles" / "example.toml"
    ext.parent.mkdir()
    ext.write_text("box = 'example'\n", encoding="utf-8")
    registry.add_path(str(ext))

    out = tmp_path / "bk.tar.gz"
    backup.make_backup(out)

    shutil.rmtree(tmp_path / "home")
    ext.unlink()

    written = backup.restore(out)
    assert home.read_settings() == {"telemetry": {"enabled": True, "install_id": "id-1"}}
    assert (home.state_home() / "update-check.json").exists()
    assert ext.read_text(encoding="utf-8") == "box = 'example'\n"
    assert any("example.toml" in w for w in written)


def test_refuse_to_clobber(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    home.write_settings({"a": "one"})
    out = tmp_path / "bk.tar.gz"
    backup.make_backup(out)

    home.write_settings({"a": "TWO"})  # live now differs from the archive
    with pytest.raises(FileExistsError):
        backup.restore(out)
    assert home.read_settings() == {"a": "TWO"}  # nothing written on refusal

    backup.restore(out, force=True)
    assert home.read_settings() == {"a": "one"}


def test_unknown_schema_rejected(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    bad = tmp_path / "bad.tar.gz"
    blob = json.dumps({"schema": 999}).encode("utf-8")
    with tarfile.open(bad, "w:gz") as tar:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
    with pytest.raises(ValueError):
        backup.restore(bad)


def test_traversal_path_refused(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    evil = tmp_path / "evil.tar.gz"
    mani = json.dumps({"schema": 1, "registered": []}).encode("utf-8")
    payload = b"pwned"
    with tarfile.open(evil, "w:gz") as tar:
        mi = tarfile.TarInfo("manifest.json")
        mi.size = len(mani)
        tar.addfile(mi, io.BytesIO(mani))
        ev = tarfile.TarInfo("home/config/../../../../tmp/evil-orrery")
        ev.size = len(payload)
        tar.addfile(ev, io.BytesIO(payload))
    with pytest.raises(ValueError):
        backup.restore(evil)


def test_encrypt_without_extra_refuses(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    with pytest.raises(NotImplementedError):
        backup.make_backup(tmp_path / "x.tar.gz", encrypt=True)
