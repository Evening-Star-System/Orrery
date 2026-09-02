import json

from orrery.reconciler.checks.behavior_lock import BehaviorLockCheck
from orrery.reconciler.model import Severity

ROOT = "/repo"
MANIFEST = "/repo/orrery-locks.toml"
RESULTS = "/repo/orrery-locks.results.json"

_GOLDEN = "orphaned_blobs=0 paths=web,native"


class FakeBox:
    """Only read_text is exercised; the check never writes and never runs a build."""

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


def _manifest(golden=_GOLDEN, hold=False, lock_id="export-envelope-no-orphan-blobs"):
    lines = [
        "schema = 1",
        'repo = "arcalox"',
        "[[locks]]",
        f'id = "{lock_id}"',
        'why = "seed lock"',
        'command = "scripts/locks/orphan-blob-probe.sh"',
        'capture = "stdout-line"',
    ]
    if golden is not None:
        lines.append(f'golden = "{golden}"')
    if hold:
        lines.append("hold = true")
    return "\n".join(lines) + "\n"


def _results(observed=_GOLDEN, lock_id="export-envelope-no-orphan-blobs", **kw):
    entry = {"observed": observed}
    entry.update(kw)
    return json.dumps({"results": {lock_id: entry}})


def _run(files, options=None):
    opts = options or {"repos": [{"root": ROOT}]}
    return BehaviorLockCheck().run(opts, FakeBox(files))


def test_golden_holds_is_ok():
    (f,) = _run({MANIFEST: _manifest(), RESULTS: _results(observed=_GOLDEN)})
    assert f.severity == Severity.OK
    assert f.subject == "arcalox/export-envelope-no-orphan-blobs"


def test_golden_holds_ignores_incidental_whitespace():
    (f,) = _run({MANIFEST: _manifest(), RESULTS: _results(observed="orphaned_blobs=0   paths=web,native")})
    assert f.severity == Severity.OK


def test_observed_changed_is_fail():
    changed = "orphaned_blobs=3 paths=web,native"
    (f,) = _run({MANIFEST: _manifest(), RESULTS: _results(observed=changed)})
    assert f.severity == Severity.FAIL
    assert f.expected == _GOLDEN and f.observed == changed


def test_declared_but_never_captured_is_fail():
    """No golden protects nothing, so it blocks until captured (ratified decision 5)."""
    (f,) = _run({MANIFEST: _manifest(golden=None), RESULTS: _results()})
    assert f.severity == Severity.FAIL
    assert "never captured" in f.message


def test_missing_observed_is_warn_not_a_false_ok():
    (f,) = _run({MANIFEST: _manifest()})  # manifest present, no results file at all
    assert f.severity == Severity.WARN
    assert "did not run" in f.message


def test_errored_probe_is_warn():
    files = {MANIFEST: _manifest(), RESULTS: _results(observed="", ok=False, error="timed out after 120s")}
    (f,) = _run(files)
    assert f.severity == Severity.WARN
    assert "timed out" in f.message


def test_hold_is_info():
    (f,) = _run({MANIFEST: _manifest(hold=True), RESULTS: _results()})
    assert f.severity == Severity.INFO
    assert "hold" in f.message


def test_absent_manifest_is_nothing_to_check():
    assert _run({}) == []


def test_malformed_manifest_warns_rather_than_raising():
    (f,) = _run({MANIFEST: "[[locks]\nid = ", RESULTS: _results()})
    assert f.severity == Severity.WARN
    assert "not valid TOML" in f.message


def test_malformed_results_degrade_to_warn_per_lock():
    (f,) = _run({MANIFEST: _manifest(), RESULTS: "{not json"})
    assert f.severity == Severity.WARN


def test_no_repos_declared_warns():
    findings = BehaviorLockCheck().run({"repos": []}, FakeBox({}))
    assert findings and findings[0].severity == Severity.WARN


def test_repo_may_be_a_bare_string_root():
    (f,) = _run({MANIFEST: _manifest(), RESULTS: _results()}, options={"repos": [ROOT]})
    assert f.severity == Severity.OK


def test_option_schema_declares_repos_required():
    check = BehaviorLockCheck()
    assert "repos" in check.option_keys
    assert "repos" in check.required_keys


# --- directional compare: allow the positive change, block the negative --------------

def _dir(golden, compare, observed, lock_id="m"):
    manifest = (
        f'schema = 1\nrepo = "r"\n[[locks]]\nid = "{lock_id}"\ncommand = "x"\n'
        f'capture = "stdout-line"\ncompare = "{compare}"\ngolden = "{golden}"\n'
    )
    results = json.dumps({"results": {lock_id: {"observed": observed}}})
    (f,) = _run({MANIFEST: manifest, RESULTS: results})
    return f.severity


def test_floor_allows_improvement_and_holds_but_blocks_regression():
    assert _dir("87", ">=", "90") is Severity.OK    # improved, allowed
    assert _dir("87", ">=", "87") is Severity.OK    # held at the floor
    assert _dir("87", ">=", "80") is Severity.FAIL  # fell below the floor: a regression


def test_ceiling_allows_improvement_and_holds_but_blocks_regression():
    assert _dir("100", "<=", "80") is Severity.OK     # smaller is better: improved
    assert _dir("100", "<=", "100") is Severity.OK    # held at the ceiling
    assert _dir("100", "<=", "120") is Severity.FAIL  # rose above the ceiling: a regression


def test_directional_on_a_nonnumber_is_warn_not_a_false_verdict():
    assert _dir("green", ">=", "greener") is Severity.WARN


def test_unknown_compare_mode_warns():
    assert _dir("1", "~=", "2") is Severity.WARN


def test_eq_is_still_the_default_and_exact():
    # No compare field: exact match, so any change (better OR worse) trips (a deliberate change
    # is a re-lock). This preserves the original behavior.
    manifest = _manifest()  # no compare -> eq
    (ok,) = _run({MANIFEST: manifest, RESULTS: _results()})
    assert ok.severity is Severity.OK
    (changed,) = _run({MANIFEST: manifest, RESULTS: _results(observed="anything-else")})
    assert changed.severity is Severity.FAIL
