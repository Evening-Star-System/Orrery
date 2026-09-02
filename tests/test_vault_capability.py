import json
from datetime import datetime, timedelta, timezone

from orrery.reconciler.checks.vault_capability import VaultCapabilityCheck
from orrery.reconciler.model import Severity

REPORT = "/var/lib/orrery/vault-credentials.json"


class FakeBox:
    def __init__(self, files: dict):
        self.files = files

    def exists(self, path: str) -> bool:
        return path in self.files

    def read_text(self, path: str) -> str | None:
        return self.files.get(path)

    def list_files(self, root: str, max_files: int = 2000):
        return None

    def file_meta(self, path: str):
        return None


def _stamp(minutes_ago=0):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _report(**kw):
    base = {"checked_at": _stamp(), "probe_ok": True, "verdict": "OK",
            "missing": [], "detail": {"ess/github-app": {"buckets": ["ess"],
                                                         "capabilities": ["read"],
                                                         "ok": True}}}
    base.update(kw)
    return {REPORT: json.dumps(base)}


def _run(files, options=None):
    return VaultCapabilityCheck().run(options or {}, FakeBox(files))


def test_healthy_credential_is_ok():
    (f,) = _run(_report())
    assert f.severity == Severity.OK


def test_missing_report_is_fail_not_silence():
    """The state every one of the seven outages was in: nothing measuring."""
    (f,) = _run({})
    assert f.severity == Severity.FAIL
    assert "nothing is exercising" in f.message


def test_denied_path_names_the_affected_consumers():
    files = _report(verdict="FAIL", missing=["ess/github-app"],
                    detail={"ess/github-app": {"buckets": ["ess", "hfh", "esp"],
                                               "capabilities": ["deny"], "ok": False}})
    (f,) = _run(files)
    assert f.severity == Severity.FAIL
    assert "ess, hfh, esp" in f.message
    assert f.observed == "deny"


def test_stale_report_is_drift_even_when_verdict_is_ok():
    """A stale OK is not an OK -- that is how a dead probe hides a dead credential."""
    findings = _run(_report(checked_at=_stamp(minutes_ago=600)))
    assert any(f.severity == Severity.DRIFT for f in findings)
    assert not any(f.severity == Severity.OK for f in findings)


def test_probe_failure_does_not_claim_the_credential_is_broken_or_fine():
    """probe_ok and verdict are different signals (the 2026-08-09 spine lesson)."""
    findings = _run(_report(probe_ok=False, verdict="UNKNOWN",
                            note="vault unreachable (tunnel down?)"))
    assert [f.severity for f in findings] == [Severity.WARN]
    assert "NOT assessed" in findings[0].message


def test_report_never_leaks_a_secret_value():
    """Value-blind by construction: only paths and capability names are ever emitted."""
    secret = "s.SUPERSECRETTOKENVALUE"
    files = _report(verdict="FAIL", missing=["ess/github-app"],
                    note=f"token {secret} rejected",
                    detail={"ess/github-app": {"buckets": ["ess"],
                                               "capabilities": ["deny"], "ok": False}})
    for f in _run(files):
        assert secret not in (f.message + str(f.expected) + str(f.observed) + f.subject)


def test_malformed_report_warns_rather_than_raising():
    (f,) = _run({REPORT: "{not json"})
    assert f.severity == Severity.WARN
