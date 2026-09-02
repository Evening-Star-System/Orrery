from pathlib import Path

from orrery.reconciler.box import LocalBox
from orrery.reconciler.checks.org_map import OrgMapCheck
from orrery.reconciler.model import Severity

FIX = Path(__file__).parent / "fixtures"
SOURCE = str(FIX / "orgs.tsv")


def _run(consumers):
    return OrgMapCheck().run(
        {"source": SOURCE, "consumers": consumers}, LocalBox()
    )


def test_clean_set_is_all_ok():
    findings = _run(
        [
            {
                "path": str(FIX / "clean" / "org-guard.py"),
                "parser": "python-dict",
                "symbol": "BUCKET_ACCT",
            },
            {"path": str(FIX / "clean" / "org-tool"), "parser": "bash-assoc", "name": "ACCT"},
            {
                "path": str(FIX / "clean" / "org-lookup"),
                "parser": "bash-case",
                "func": "org_of",
                "implied_host": "github.com",
            },
        ]
    )
    assert not any(f.severity >= Severity.DRIFT for f in findings)
    # every consumer reported at least one OK
    ok_paths = {f.subject for f in findings if f.severity == Severity.OK}
    assert len(ok_paths) == 3
    # case-insensitivity: org-guard uses lowercase, org-tool mixed case, both agree with truth
    # the github-only lookup consumer leaves acme uncovered -> INFO, not drift
    info = [f for f in findings if f.severity == Severity.INFO]
    assert any("org-lookup" in f.subject for f in info)


def test_wrong_account_is_drift():
    findings = _run(
        [
            {
                "path": str(FIX / "drift" / "org-guard.py"),
                "parser": "python-dict",
                "symbol": "BUCKET_ACCT",
            }
        ]
    )
    drifts = [f for f in findings if f.severity == Severity.DRIFT]
    subjects = {f.subject: f for f in drifts}
    # globex mapped to personal-fork instead of the org
    globex = next(f for s, f in subjects.items() if s.endswith(":globex"))
    assert globex.expected == "Globex-Inc"
    assert globex.observed == "personal-fork"
    # a bucket the consumer invents but the truth does not list is also drift
    assert any(s.endswith(":ghost") for s in subjects)


def test_unparseable_consumer_warns_never_passes():
    findings = _run(
        [
            {
                "path": str(FIX / "drift" / "unparseable.py"),
                "parser": "python-dict",
                "symbol": "BUCKET_ACCT",
            }
        ]
    )
    assert all(f.severity != Severity.OK for f in findings)
    assert any(f.severity == Severity.WARN for f in findings)


def test_missing_source_warns():
    findings = OrgMapCheck().run({"consumers": []}, LocalBox())
    assert findings and findings[0].severity == Severity.WARN
