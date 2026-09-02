"""recover: restore known-good bytes, refuse safely, save a pre-image, and roll back on a bad store."""

import hashlib

from orrery.integrity.recover import recover_artifact
from orrery.integrity.store import Store


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_recover_restores_the_recorded_bytes(tmp_path):
    store = Store(tmp_path / "cas")
    good = b"the correct config\n"
    h = store.record(good)
    f = tmp_path / "c.txt"
    f.write_bytes(b"CORRUPTED")
    res = recover_artifact({"path": str(f), "hash": "sha256:" + h}, store, log_path=tmp_path / "recover.log")
    assert res.status == "recovered"
    assert f.read_bytes() == good
    assert (tmp_path / "recover.log").exists()  # audited


def test_already_correct_is_a_noop(tmp_path):
    store = Store(tmp_path / "cas")
    good = b"good"
    h = store.record(good)
    f = tmp_path / "c"
    f.write_bytes(good)
    res = recover_artifact({"path": str(f), "hash": "sha256:" + h}, store)
    assert res.status == "already-ok"
    assert f.read_bytes() == good


def test_refuses_when_no_recorded_bytes_exist(tmp_path):
    store = Store(tmp_path / "cas")
    f = tmp_path / "c"
    f.write_bytes(b"x")
    res = recover_artifact({"path": str(f), "hash": _sha(b"never-stored")}, store)
    assert res.status == "refused" and "no recorded bytes" in res.detail
    assert f.read_bytes() == b"x"  # untouched


def test_refuses_to_write_through_a_symlink(tmp_path):
    store = Store(tmp_path / "cas")
    h = store.record(b"g")
    real = tmp_path / "real"
    real.write_bytes(b"other")
    link = tmp_path / "link"
    link.symlink_to(real)
    res = recover_artifact({"path": str(link), "hash": "sha256:" + h}, store)
    assert res.status == "refused" and "symlink" in res.detail
    assert real.read_bytes() == b"other"  # target untouched


def test_dry_run_writes_nothing(tmp_path):
    store = Store(tmp_path / "cas")
    h = store.record(b"good")
    f = tmp_path / "c"
    f.write_bytes(b"bad")
    res = recover_artifact({"path": str(f), "hash": "sha256:" + h}, store, dry_run=True)
    assert res.status == "would-recover"
    assert f.read_bytes() == b"bad"


def test_pre_image_is_saved_before_overwrite(tmp_path):
    store = Store(tmp_path / "cas")
    h = store.record(b"good")
    f = tmp_path / "c"
    f.write_bytes(b"current-bad")
    recover_artifact({"path": str(f), "hash": "sha256:" + h}, store)
    pre = hashlib.sha256(b"current-bad").hexdigest()
    assert store.fetch(pre) == b"current-bad"  # the pre-recover bytes are recoverable


def test_verify_after_mismatch_rolls_back(tmp_path):
    # A corrupt store object (bytes that do not hash to their name) must be caught by the
    # verify-after and rolled back to the pre-image, never left half-written.
    store = Store(tmp_path / "cas")
    recorded = hashlib.sha256(b"good").hexdigest()
    obj = tmp_path / "cas" / recorded[:2] / recorded[2:]
    obj.parent.mkdir(parents=True)
    obj.write_bytes(b"WRONG bytes not matching the hash")
    f = tmp_path / "c"
    f.write_bytes(b"current")
    res = recover_artifact({"path": str(f), "hash": "sha256:" + recorded}, store)
    assert res.status == "failed" and "rolled back" in res.detail
    assert f.read_bytes() == b"current"  # rolled back to the pre-image
