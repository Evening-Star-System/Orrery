"""The Enforcer seam: the two report-tier enforcers, the registry, and the reconcile wiring.
The integration tests drive the real reconcile CLI to prove default `gate` preserves today's
exit codes and `report` never blocks."""

import pytest

from orrery.enforce import GateEnforcer, ReportEnforcer, get_enforcer, known_names
from orrery.enforce.base import Verdict
from orrery.reconciler.engine import Result
from orrery.reconciler.__main__ import main as reconcile_main


class FakeVerdict:
    def __init__(self, clean: bool, exit_code: int):
        self.clean = clean
        self.exit_code = exit_code


# --- the enforcers ------------------------------------------------------------------

def test_gate_blocks_on_drift_and_passes_when_clean():
    assert GateEnforcer().act(FakeVerdict(clean=True, exit_code=0)) == 0
    assert GateEnforcer().act(FakeVerdict(clean=False, exit_code=1)) == 1


def test_report_never_blocks():
    assert ReportEnforcer().act(FakeVerdict(clean=True, exit_code=0)) == 0
    assert ReportEnforcer().act(FakeVerdict(clean=False, exit_code=1)) == 0


def test_registry_resolves_known_and_rejects_unknown():
    assert isinstance(get_enforcer("gate"), GateEnforcer)
    assert isinstance(get_enforcer("report"), ReportEnforcer)
    assert known_names() == ["gate", "report"]
    with pytest.raises(ValueError):
        get_enforcer("rotate")  # a future enforcer, not shipped


def test_result_satisfies_the_verdict_protocol():
    # The reconciler's Result must be usable as a Verdict with no adapter, so the seam does
    # not couple the enforcer to the reconciler.
    assert isinstance(Result(box="x", findings=[]), Verdict)


# --- the reconcile wiring (real CLI) ------------------------------------------------

def _fail_profile(tmp_path):
    """A consumer repo whose lock is declared but never captured (a FAIL), and a profile
    pointing the behavior-lock check at it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "orrery-locks.toml").write_text(
        'schema = 1\n[[locks]]\nid = "x"\ncommand = "echo v"\ncapture = "stdout-line"\n'
    )
    profile = tmp_path / "prof.toml"
    profile.write_text(
        f'schema = 1\nbox = "t"\n[[checks]]\nid = "behavior-lock"\n[[checks.repos]]\nroot = "{repo}"\n'
    )
    return str(profile)


def _clean_profile(tmp_path):
    """A consumer repo with an empty manifest: nothing to check, so the verdict is clean."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "orrery-locks.toml").write_text("schema = 1\n")
    profile = tmp_path / "prof.toml"
    profile.write_text(
        f'schema = 1\nbox = "t"\n[[checks]]\nid = "behavior-lock"\n[[checks.repos]]\nroot = "{repo}"\n'
    )
    return str(profile)


def test_default_gate_exits_nonzero_on_drift(tmp_path, capsys):
    profile = _fail_profile(tmp_path)
    assert reconcile_main(["--profile", profile, "--check", "behavior-lock"]) == 1


def test_explicit_gate_exits_nonzero_on_drift(tmp_path, capsys):
    profile = _fail_profile(tmp_path)
    assert reconcile_main(["--profile", profile, "--check", "behavior-lock", "--enforce", "gate"]) == 1


def test_report_exits_zero_on_the_same_drift(tmp_path, capsys):
    profile = _fail_profile(tmp_path)
    # Same drifting profile, but report-only: the findings are emitted, the process does not fail.
    assert reconcile_main(["--profile", profile, "--check", "behavior-lock", "--enforce", "report"]) == 0


def test_both_enforcers_exit_zero_when_clean(tmp_path, capsys):
    profile = _clean_profile(tmp_path)
    assert reconcile_main(["--profile", profile, "--check", "behavior-lock"]) == 0
    assert reconcile_main(["--profile", profile, "--check", "behavior-lock", "--enforce", "report"]) == 0


def test_human_summary_reports_the_enforced_exit_not_the_verdict(tmp_path, capsys):
    profile = _fail_profile(tmp_path)
    # report mode still SHOWS the drift finding, but the summary must not claim an exit it
    # will not cause.
    reconcile_main(["--profile", profile, "--check", "behavior-lock", "--enforce", "report"])
    out = capsys.readouterr().out
    assert "DRIFT DETECTED (exit 0)" in out and "FAIL" in out
    reconcile_main(["--profile", profile, "--check", "behavior-lock", "--enforce", "gate"])
    assert "DRIFT DETECTED (exit 1)" in capsys.readouterr().out
