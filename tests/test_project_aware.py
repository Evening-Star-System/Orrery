"""Project-aware fleet reconcile: a canon behavior-lock adjudicates each project's OWN manifest.

An operator profile at <project>/.dev/orrery.profile.toml gets its project root injected into a
repos-less behavior-lock check, so a fleet reconcile surfaces each project's real guardrail status with
no per-project config. A profile not under .dev keeps its exact prior behavior.
"""
from orrery.reconciler.engine import run_profile
from orrery.reconciler.profile import load_profile


def _dev_profile(tmp_path, checks='[[checks]]\nid = "behavior-lock"\n'):
    (tmp_path / ".dev").mkdir()
    p = tmp_path / ".dev" / "orrery.profile.toml"
    p.write_text('box = "p"\n' + checks)
    return p


def test_dev_profile_injects_project_root(tmp_path):
    p = load_profile(_dev_profile(tmp_path))
    bl = next(c for c in p.checks if c.id == "behavior-lock")
    assert bl.options["repos"] == [{"root": str(tmp_path)}]


def test_non_dev_profile_is_untouched(tmp_path):
    plain = tmp_path / "p.toml"
    plain.write_text('box = "p"\n[[checks]]\nid = "behavior-lock"\n')
    bl = next(c for c in load_profile(plain).checks if c.id == "behavior-lock")
    assert not bl.options.get("repos")  # unchanged: reports nothing-to-check


def test_explicit_repos_are_not_overridden(tmp_path):
    p = load_profile(_dev_profile(tmp_path, '[[checks]]\nid = "behavior-lock"\n  [[checks.repos]]\n  root = "/x"\n'))
    bl = next(c for c in p.checks if c.id == "behavior-lock")
    assert bl.options["repos"] == [{"root": "/x"}]


def test_blank_project_reconciles_clean(tmp_path):
    # no manifest at the project root -> nothing to check -> clean
    result = run_profile(str(_dev_profile(tmp_path)))
    assert result.clean


def test_project_with_a_regressed_lock_reconciles_dirty(tmp_path):
    (tmp_path / "orrery-locks.toml").write_text(
        'schema = 1\n[[locks]]\nid = "v"\nwhy = "w"\ncommand = "true"\n'
        'capture = "stdout-line"\ncompare = "eq"\ngolden = "expected"\n'
    )
    (tmp_path / "orrery-locks.results.json").write_text(
        '{"results": {"v": {"ok": true, "observed": "DIFFERENT"}}}'
    )
    result = run_profile(str(_dev_profile(tmp_path)))
    assert not result.clean  # the project's own regressed lock shows up in the fleet reconcile
