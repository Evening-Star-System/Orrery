import os

from orrery.reconciler.box import LocalBox
from orrery.reconciler.checks.managed_settings import ManagedSettingsCheck
from orrery.reconciler.model import Severity


def _run(files):
    return ManagedSettingsCheck().run({"files": files}, LocalBox())


def test_present_correct_owner_and_mode_is_ok(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    os.chmod(f, 0o644)
    uid = os.stat(f).st_uid
    (r,) = _run([{"path": str(f), "require_owner_uid": uid, "max_mode": "0644"}])
    assert r.severity == Severity.OK


def test_world_writable_is_fail(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    os.chmod(f, 0o666)  # group + world write
    uid = os.stat(f).st_uid
    (r,) = _run([{"path": str(f), "require_owner_uid": uid, "max_mode": "0644"}])
    assert r.severity == Severity.FAIL
    assert "permissive" in r.message


def test_stricter_mode_is_ok(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    os.chmod(f, 0o600)  # stricter than 0644 is fine
    uid = os.stat(f).st_uid
    (r,) = _run([{"path": str(f), "require_owner_uid": uid, "max_mode": "0644"}])
    assert r.severity == Severity.OK


def test_wrong_owner_is_drift(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    os.chmod(f, 0o644)
    (r,) = _run([{"path": str(f), "require_owner_uid": 999999, "max_mode": "0644"}])
    assert r.severity == Severity.DRIFT
    assert r.expected == "uid 999999"


def test_planned_absent_is_info(tmp_path):
    (r,) = _run([{"path": str(tmp_path / "nope.json"), "require_owner_uid": 0, "planned": True}])
    assert r.severity == Severity.INFO


def test_required_absent_is_fail(tmp_path):
    (r,) = _run([{"path": str(tmp_path / "nope.json"), "require_owner_uid": 0}])
    assert r.severity == Severity.FAIL and "missing" in r.message


def test_no_files_declared_warns():
    findings = ManagedSettingsCheck().run({"files": []}, LocalBox())
    assert findings and findings[0].severity == Severity.WARN
