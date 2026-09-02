import os

import pytest

from orrery.reconciler.box import LocalBox
from orrery.reconciler.checks.secret_edges import SecretEdgesCheck, _is_safe_identity
from orrery.reconciler.model import Severity

REF = "some-store/tokens/example"
FAKE_SECRET_VALUE = "hvs.AABBCCDDEEFF00112233445566778899zzz"  # looks real, is not


def _tree(tmp_path):
    good = tmp_path / "uses_it.sh"
    good.write_text(f'VAULT_PATH="{REF}"\n', encoding="utf-8")
    stale = tmp_path / "no_longer.sh"
    stale.write_text("nothing here references the secret\n", encoding="utf-8")
    leaky = tmp_path / "has_value.env"
    leaky.write_text(f"# {REF}\nTOKEN={FAKE_SECRET_VALUE}\n", encoding="utf-8")
    return good, stale, leaky


def _run(opts):
    return SecretEdgesCheck().run(opts, LocalBox())


def _all_text(findings) -> str:
    parts = []
    for f in findings:
        parts += [f.subject, f.message, str(f.expected), str(f.observed)]
    return "\n".join(parts)


def test_confirmed_edge_is_ok(tmp_path):
    good, *_ = _tree(tmp_path)
    findings = _run({"secrets": [{"ref": REF, "consumers": [{"path": str(good)}]}]})
    assert any(f.severity == Severity.OK for f in findings)
    assert all(f.severity != Severity.DRIFT for f in findings)


def test_missing_consumer_file_is_drift(tmp_path):
    findings = _run(
        {"secrets": [{"ref": REF, "consumers": [{"path": str(tmp_path / "nope.sh")}]}]}
    )
    assert any(f.severity == Severity.DRIFT and "missing" in f.message for f in findings)


def test_stale_edge_is_drift(tmp_path):
    _good, stale, _leaky = _tree(tmp_path)
    findings = _run({"secrets": [{"ref": REF, "consumers": [{"path": str(stale)}]}]})
    assert any(f.severity == Severity.DRIFT and "stale" in f.message for f in findings)


def test_undeclared_edge_via_discovery_is_drift(tmp_path):
    _tree(tmp_path)
    findings = _run({"secrets": [{"ref": REF, "consumers": []}], "discover_root": str(tmp_path)})
    assert any("undeclared" in f.message for f in findings)


# --- audit regressions ---

def test_allowlist_is_fail_closed_against_secret_shapes():
    # none of these are vault-path / env-name identities: all must be refused, not scanned
    bad = [
        "AIzaSyD-1234567890abcdefghijklmnopqrstuv",       # google api key
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",        # jwt
        "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY12",        # aws secret (no slash)
        "gho_16CharsAtLeastxxxxxxxxxxxxxxxxxxxxxx",         # github oauth
        "sk_test_abcdefghijklmnop",                         # stripe test
        "rk_live_abcdefghijklmnop",                         # stripe restricted
        "xoxe-1-abcdefghijklmnop",                          # slack refresh
        "-----BEGIN PRIVATE KEY-----",                      # generic pkcs8
        "0123456789abcdef0123456789abcdef01234567",         # bare hex blob
        "this has spaces",                                   # not an identity
        12345,                                               # not even a string
    ]
    for value in bad:
        findings = SecretEdgesCheck().run(
            {"secrets": [{"ref": value, "consumers": []}], "discover_root": None}, LocalBox()
        )
        assert findings and findings[0].severity == Severity.WARN, f"not refused: {value!r}"
        assert "refused" in findings[0].message
        assert str(value) not in _all_text(findings)  # the value never appears


def test_valid_identities_pass():
    assert _is_safe_identity("some-store/tokens/example")
    assert _is_safe_identity("RESEND_API_KEY")
    assert not _is_safe_identity("AIzaSyD-1234567890abcdefghijklmnopqrstuv")
    assert not _is_safe_identity("")
    assert not _is_safe_identity(None)


def test_name_label_keeps_ref_out_of_output(tmp_path):
    good, *_ = _tree(tmp_path)
    findings = _run(
        {"secrets": [{"ref": REF, "name": "example-token", "consumers": [{"path": str(good)}]}]}
    )
    blob = _all_text(findings)
    assert "example-token" in blob
    assert REF not in blob  # with a name set, even the identity stays out of output


def test_fifo_does_not_hang(tmp_path):
    box = LocalBox()
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    # read of a FIFO returns None fast (isfile guard), never blocks on a writerless pipe
    assert box.read_text(str(fifo)) is None
    # and list_files excludes it
    good = tmp_path / "real.txt"
    good.write_text("ok\n", encoding="utf-8")
    listed = box.list_files(str(tmp_path), 100)
    assert str(fifo) not in listed
    assert str(good) in listed


def test_declared_file_not_reflagged_undeclared_despite_path_form(tmp_path):
    good, *_ = _tree(tmp_path)
    # declared as a non-normalized path; discovery must still recognize it as the same file
    declared = str(tmp_path) + "/./uses_it.sh"
    findings = _run(
        {"secrets": [{"ref": REF, "consumers": [{"path": declared}]}], "discover_root": str(tmp_path)}
    )
    undeclared_for_good = [
        f for f in findings if "undeclared" in f.message and "uses_it.sh" in f.subject
    ]
    assert not undeclared_for_good  # no false DRIFT for an already-declared file


def test_missing_discover_root_warns(tmp_path):
    findings = _run(
        {"secrets": [{"ref": REF, "consumers": []}], "discover_root": str(tmp_path / "nope")}
    )
    assert any(f.severity == Severity.WARN and "does not exist" in f.message for f in findings)


def test_no_secret_value_ever_leaks_into_findings(tmp_path):
    good, _stale, leaky = _tree(tmp_path)
    findings = _run(
        {
            "secrets": [{"ref": REF, "consumers": [{"path": str(good)}, {"path": str(leaky)}]}],
            "discover_root": str(tmp_path),
        }
    )
    blob = _all_text(findings)
    assert FAKE_SECRET_VALUE not in blob
    assert REF in blob  # the declared identity is fine to show
