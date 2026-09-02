"""Behavior-lock authoring: runner, surgical manifest write, and the capture/probe/add
commands. Hermetic: probes are trivial shell commands run in a temp repo, no real build."""

import json

import pytest

from orrery.locks import commands, manifest
from orrery.locks.cli import main as lock_cli
from orrery.locks.runner import run_probe


# --- the shared runner --------------------------------------------------------------

def test_run_probe_captures_last_nonempty_line(tmp_path):
    r = run_probe("printf 'noise\\n\\nvalue\\n'", cwd=str(tmp_path))
    assert r.ok and r.value == "value"


def test_run_probe_nonzero_exit_is_a_problem(tmp_path):
    r = run_probe("exit 3", cwd=str(tmp_path))
    assert not r.ok and r.value is None and "exited 3" in r.problem


def test_run_probe_empty_output_is_a_problem(tmp_path):
    r = run_probe("true", cwd=str(tmp_path))
    assert not r.ok and "no stdout" in r.problem


def test_run_probe_missing_command_is_a_problem(tmp_path):
    r = run_probe(None, cwd=str(tmp_path))
    assert not r.ok and "no 'command'" in r.problem


def test_run_probe_unsupported_capture_is_a_problem(tmp_path):
    r = run_probe("echo x", cwd=str(tmp_path), capture="json-field")
    assert not r.ok and "unsupported capture" in r.problem


def test_run_probe_times_out(tmp_path):
    r = run_probe("sleep 5", cwd=str(tmp_path), timeout=1)
    assert not r.ok and "timed out" in r.problem


def test_run_probe_runs_in_the_repo_root(tmp_path):
    (tmp_path / "marker").write_text("orphaned_blobs=0\n")
    r = run_probe("cat marker", cwd=str(tmp_path))
    assert r.ok and r.value == "orphaned_blobs=0"


# --- the surgical manifest write ----------------------------------------------------

_WITH_GOLDEN = (
    "schema = 1\n"
    '# a human note that must survive the write\n'
    'repo = "arcalox"\n'
    "\n"
    "[[locks]]\n"
    'id = "no-orphan-blobs"\n'
    'why = "seed lock"  # the incident\n'
    'command = "scripts/probe.sh"\n'
    'capture = "stdout-line"\n'
    'golden = "orphaned_blobs=1"\n'
)

_NO_GOLDEN = (
    "schema = 1\n"
    "\n"
    "[[locks]]\n"
    'id = "first"\n'
    'command = "echo a"\n'
    "\n"
    "[[locks]]\n"
    'id = "second"\n'
    'command = "echo b"\n'
)


def test_set_golden_replaces_in_place_and_preserves_comments():
    out = manifest.set_golden(_WITH_GOLDEN, "no-orphan-blobs", "orphaned_blobs=0")
    assert 'golden = "orphaned_blobs=0"' in out
    assert 'golden = "orphaned_blobs=1"' not in out
    assert "# a human note that must survive the write" in out
    assert "why = \"seed lock\"  # the incident" in out
    assert manifest.golden_of(manifest.load(out), "no-orphan-blobs") == "orphaned_blobs=0"


def test_set_golden_inserts_when_absent_into_the_right_block():
    out = manifest.set_golden(_NO_GOLDEN, "first", "A")
    doc = manifest.load(out)
    assert manifest.golden_of(doc, "first") == "A"
    assert manifest.golden_of(doc, "second") is None  # the other block is untouched


def test_set_golden_targets_only_the_named_lock():
    out = manifest.set_golden(_NO_GOLDEN, "second", "B")
    doc = manifest.load(out)
    assert manifest.golden_of(doc, "first") is None
    assert manifest.golden_of(doc, "second") == "B"


def test_set_golden_unknown_id_raises():
    with pytest.raises(KeyError):
        manifest.set_golden(_WITH_GOLDEN, "nope", "x")


def test_set_golden_escapes_quotes_and_backslashes():
    out = manifest.set_golden(_WITH_GOLDEN, "no-orphan-blobs", 'a"b\\c')
    # round-trips to exactly the intended value despite the metacharacters
    assert manifest.golden_of(manifest.load(out), "no-orphan-blobs") == 'a"b\\c'


def test_append_lock_then_parses():
    out = manifest.append_lock("schema = 1\n", "new", "echo hi", "because")
    doc = manifest.load(out)
    assert manifest.has_lock(doc, "new")
    lock = manifest.locks(doc)[0]
    assert lock["command"] == "echo hi" and lock["why"] == "because"


# --- capture ------------------------------------------------------------------------

def _write_manifest(tmp_path, body):
    path = tmp_path / manifest.MANIFEST_NAME
    path.write_text(body)
    return str(path)


def test_capture_green_run_writes_the_golden(tmp_path):
    (tmp_path / "marker").write_text("orphaned_blobs=0\n")
    body = (
        "schema = 1\n[[locks]]\n"
        'id = "no-orphan-blobs"\n'
        'command = "cat marker"\n'
        'capture = "stdout-line"\n'
    )
    path = _write_manifest(tmp_path, body)
    code, messages = commands.capture(path)
    assert code == 0
    assert manifest.golden_of(manifest.load(open(path).read()), "no-orphan-blobs") == "orphaned_blobs=0"
    assert any("captured no-orphan-blobs" in m for m in messages)


def test_capture_failed_probe_writes_nothing(tmp_path):
    body = "schema = 1\n[[locks]]\n" 'id = "x"\n' 'command = "exit 1"\n'
    path = _write_manifest(tmp_path, body)
    before = open(path).read()
    code, messages = commands.capture(path)
    assert code == 1
    assert open(path).read() == before  # untouched, no golden pinned from a broken run
    assert manifest.golden_of(manifest.load(before), "x") is None


def test_capture_relock_is_loud_and_shows_old_and_new(tmp_path):
    # A deliberate behavior change: the golden already exists and the new value differs. This
    # is progression, not regression, and must announce old -> new (a reviewed move), not
    # silently overwrite.
    (tmp_path / "m").write_text("v2\n")
    body = "schema = 1\n[[locks]]\n" 'id = "a"\n' 'command = "cat m"\n' 'golden = "v1"\n'
    path = _write_manifest(tmp_path, body)
    code, messages = commands.capture(path)
    assert code == 0
    assert any(m.startswith("re-locked a: v1 -> v2") for m in messages)
    assert manifest.golden_of(manifest.load(open(path).read()), "a") == "v2"


def test_capture_unchanged_is_a_noop_without_rewriting(tmp_path):
    (tmp_path / "m").write_text("same\n")
    body = "schema = 1\n[[locks]]\n" 'id = "a"\n' 'command = "cat m"\n' 'golden = "same"\n'
    path = _write_manifest(tmp_path, body)
    before = open(path).read()
    code, messages = commands.capture(path)
    assert code == 0
    assert any("unchanged a" in m for m in messages)
    assert open(path).read() == before  # identical golden: no write, clean re-run
    assert not any("wrote" in m for m in messages)


def test_capture_only_one_id_leaves_others(tmp_path):
    (tmp_path / "m").write_text("v1\n")
    body = (
        "schema = 1\n"
        "[[locks]]\n" 'id = "a"\n' 'command = "cat m"\n'
        "[[locks]]\n" 'id = "b"\n' 'command = "cat m"\n'
    )
    path = _write_manifest(tmp_path, body)
    code, _ = commands.capture(path, only_id="a")
    doc = manifest.load(open(path).read())
    assert code == 0
    assert manifest.golden_of(doc, "a") == "v1"
    assert manifest.golden_of(doc, "b") is None


def test_capture_missing_manifest_is_exit_2(tmp_path):
    code, messages = commands.capture(str(tmp_path / "nope.toml"))
    assert code == 2 and any("no manifest" in m for m in messages)


def test_capture_invalid_toml_is_exit_2(tmp_path):
    path = _write_manifest(tmp_path, "this is = = not toml\n")
    code, messages = commands.capture(path)
    assert code == 2 and any("not valid TOML" in m for m in messages)


def test_capture_empty_manifest_is_a_clean_noop(tmp_path):
    path = _write_manifest(tmp_path, "schema = 1\n")
    code, messages = commands.capture(path)
    assert code == 0 and any("nothing to capture" in m for m in messages)


def test_capture_unknown_id_is_exit_2(tmp_path):
    path = _write_manifest(tmp_path, "schema = 1\n[[locks]]\n" 'id = "a"\n' 'command = "echo x"\n')
    code, messages = commands.capture(path, only_id="ghost")
    assert code == 2 and any("no lock with id" in m for m in messages)


# --- probe --------------------------------------------------------------------------

def test_probe_writes_results_in_the_shape_the_check_reads(tmp_path):
    (tmp_path / "m").write_text("value=1\n")
    body = "schema = 1\n[[locks]]\n" 'id = "a"\n' 'command = "cat m"\n'
    path = _write_manifest(tmp_path, body)
    code, _ = commands.probe(path)
    assert code == 0
    doc = json.loads((tmp_path / manifest.RESULTS_NAME).read_text())
    assert doc["results"]["a"] == {"ok": True, "observed": "value=1"}


def test_probe_records_a_failure_without_a_false_observed(tmp_path):
    body = "schema = 1\n[[locks]]\n" 'id = "a"\n' 'command = "exit 2"\n'
    path = _write_manifest(tmp_path, body)
    code, _ = commands.probe(path)
    assert code == 0
    entry = json.loads((tmp_path / manifest.RESULTS_NAME).read_text())["results"]["a"]
    assert entry["ok"] is False and "observed" not in entry and "error" in entry


# --- add ----------------------------------------------------------------------------

def test_add_declares_and_captures_in_one_step(tmp_path):
    (tmp_path / "m").write_text("locked=yes\n")
    path = str(tmp_path / manifest.MANIFEST_NAME)
    code, _ = commands.add(path, "new", command="cat m", why="earned it")
    doc = manifest.load(open(path).read())
    assert code == 0
    assert manifest.has_lock(doc, "new")
    assert manifest.golden_of(doc, "new") == "locked=yes"


def test_add_refuses_a_duplicate_id(tmp_path):
    path = _write_manifest(tmp_path, "schema = 1\n[[locks]]\n" 'id = "dup"\n' 'command = "echo x"\n')
    code, messages = commands.add(path, "dup", command="echo y", why="w")
    assert code == 2 and any("already exists" in m for m in messages)


def test_add_creates_the_manifest_when_absent(tmp_path):
    (tmp_path / "m").write_text("ok\n")
    path = str(tmp_path / manifest.MANIFEST_NAME)
    code, _ = commands.add(path, "first", command="cat m", why="w")
    assert code == 0
    doc = manifest.load(open(path).read())
    assert manifest.golden_of(doc, "first") == "ok"


def test_add_leaves_lock_uncaptured_when_probe_fails(tmp_path):
    path = str(tmp_path / manifest.MANIFEST_NAME)
    code, _ = commands.add(path, "broken", command="exit 1", why="w")
    doc = manifest.load(open(path).read())
    assert code == 1
    assert manifest.has_lock(doc, "broken")          # declared
    assert manifest.golden_of(doc, "broken") is None  # but not captured, so the check FAILs it


# --- CLI wiring (the `-m` flag sits AFTER the subcommand; do not let that regress) ---

def test_cli_add_then_capture_via_the_manifest_flag(tmp_path):
    (tmp_path / "m").write_text("v=1\n")
    path = str(tmp_path / manifest.MANIFEST_NAME)
    assert lock_cli(["add", "-m", path, "a", "--command", "cat m", "--why", "w"]) == 0
    assert manifest.golden_of(manifest.load(open(path).read()), "a") == "v=1"
    # capture reads the same flag position
    (tmp_path / "m").write_text("v=2\n")
    assert lock_cli(["capture", "-m", path, "a"]) == 0
    assert manifest.golden_of(manifest.load(open(path).read()), "a") == "v=2"


def test_cli_no_subcommand_is_usage_exit_2():
    assert lock_cli([]) == 2
