"""The content-address check: match/changed/missing/unrecorded/unreadable, plus real Box hashing."""

import hashlib

from orrery.reconciler.box import LocalBox, SshBox
from orrery.reconciler.checks.content_address import ContentAddressCheck
from orrery.reconciler.model import Severity


class FakeBox:
    """path -> bytes (present) or None (missing). content_hash returns None for a missing file."""

    def __init__(self, files):
        self.files = files

    def exists(self, path):
        return self.files.get(path) is not None

    def content_hash(self, path):
        b = self.files.get(path)
        return hashlib.sha256(b).hexdigest() if isinstance(b, (bytes, bytearray)) else None

    def read_text(self, path):
        return None

    def list_files(self, root, max_files=2000):
        return None

    def file_meta(self, path):
        return None


def _run(artifacts, box):
    return ContentAddressCheck().run({"artifacts": artifacts}, box)


def _sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --- adjudication -------------------------------------------------------------------

def test_match_is_ok():
    (f,) = _run([{"path": "/x", "hash": _sha(b"data")}], FakeBox({"/x": b"data"}))
    assert f.severity is Severity.OK


def test_changed_bytes_is_fail():
    (f,) = _run([{"path": "/x", "hash": _sha(b"original")}], FakeBox({"/x": b"tampered"}))
    assert f.severity is Severity.FAIL and "changed" in f.message


def test_missing_file_is_fail():
    (f,) = _run([{"path": "/x", "hash": _sha(b"x")}], FakeBox({"/x": None}))
    assert f.severity is Severity.FAIL and f.observed == "absent"


def test_declared_but_unrecorded_is_fail():
    (f,) = _run([{"path": "/x"}], FakeBox({"/x": b"data"}))  # no hash
    assert f.severity is Severity.FAIL and f.observed == "none"


def test_present_but_unhashable_is_warn():
    class Unhashable(FakeBox):
        def exists(self, path):
            return True

        def content_hash(self, path):
            return None

    (f,) = _run([{"path": "/x", "hash": _sha(b"x")}], Unhashable({}))
    assert f.severity is Severity.WARN


def test_no_artifacts_warns():
    findings = ContentAddressCheck().run({"artifacts": []}, FakeBox({}))
    assert findings and findings[0].severity is Severity.WARN


def test_bare_hex_hash_matches_too():
    bare = hashlib.sha256(b"data").hexdigest()  # no sha256: prefix
    (f,) = _run([{"path": "/x", "hash": bare}], FakeBox({"/x": b"data"}))
    assert f.severity is Severity.OK


def test_option_schema_requires_artifacts():
    c = ContentAddressCheck()
    assert "artifacts" in c.option_keys and "artifacts" in c.required_keys


# --- real Box hashing ---------------------------------------------------------------

def test_localbox_content_hash_streams_correctly(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"stream me")
    assert LocalBox().content_hash(str(p)) == hashlib.sha256(b"stream me").hexdigest()


def test_localbox_content_hash_missing_is_none(tmp_path):
    assert LocalBox().content_hash(str(tmp_path / "nope")) is None


def test_sshbox_content_hash_parses_sha256sum():
    digest = "a" * 64
    box = SshBox("host", runner=lambda cmd: (0, f"{digest}  /path\n".encode()))
    assert box.content_hash("/path") == digest


def test_sshbox_content_hash_rejects_garbage():
    box = SshBox("host", runner=lambda cmd: (0, b"not-a-hash"))
    assert box.content_hash("/path") is None
