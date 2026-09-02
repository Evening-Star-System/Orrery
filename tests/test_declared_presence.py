from pathlib import Path

from orrery.reconciler.box import LocalBox
from orrery.reconciler.checks.declared_presence import DeclaredPresenceCheck
from orrery.reconciler.model import Severity

FIX = Path(__file__).parent / "fixtures"


def test_required_present_and_missing():
    findings = DeclaredPresenceCheck().run(
        {
            "required": [str(FIX / "orgs.tsv"), str(FIX / "does-not-exist")],
            "planned_absent": [],
        },
        LocalBox(),
    )
    by_sev = {f.severity for f in findings}
    assert Severity.OK in by_sev
    assert Severity.FAIL in by_sev
    fail = next(f for f in findings if f.severity == Severity.FAIL)
    assert "does-not-exist" in fail.subject


def test_planned_absent_info_and_stale_warn():
    findings = DeclaredPresenceCheck().run(
        {
            "required": [],
            # one truly absent (INFO, as planned) and one that exists (WARN, stale)
            "planned_absent": [str(FIX / "does-not-exist"), str(FIX / "orgs.tsv")],
        },
        LocalBox(),
    )
    sevs = {f.subject.split("/")[-1]: f.severity for f in findings}
    assert sevs["does-not-exist"] == Severity.INFO
    assert sevs["orgs.tsv"] == Severity.WARN
