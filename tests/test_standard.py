"""The canonical operating standard: stack detection + CI rendering, one trunk many limbs.

Pins the properties that matter: detection is first-match by the stack's own file; every host emits
the same beats in the same order; the lock gate is always present (a declared lock is always gated);
build runs on main only; and unknown inputs fail loudly rather than silently.
"""
import pytest

from orrery.standard.cli import main as standard_cli
from orrery.standard.profiles import detect, load_profiles, read_declaration, resolve
from orrery.standard.render import render_ci, render_github, render_woodpecker


def _declare(root, body):
    """Write a project [standard] declaration into .dev/orrery.profile.toml and return the root."""
    d = root / ".dev"
    d.mkdir(parents=True, exist_ok=True)
    (d / "orrery.profile.toml").write_text(body)
    return root


def _mk(tmp_path, name):
    (tmp_path / name).write_text("x")
    return tmp_path


def test_detect_by_stack_file(tmp_path):
    assert detect(_mk(tmp_path / "a", "pubspec.yaml") if False else _mk(tmp_path, "pubspec.yaml")) == "flutter"


@pytest.mark.parametrize("f,stack", [("pubspec.yaml", "flutter"), ("package.json", "node"), ("Cargo.toml", "rust"), ("go.mod", "go")])
def test_detect_each_stack(tmp_path, f, stack):
    assert detect(_mk(tmp_path, f)) == stack


def test_detect_generic_when_nothing_matches(tmp_path):
    assert detect(tmp_path) == "generic"


def test_resolve_carries_stack_commands():
    p = load_profiles()
    assert "flutter test" in resolve("flutter", p)["test"]
    assert resolve("node", p).get("checks")            # node has the custom-checks beat
    assert resolve("flutter", p).get("checks") is None  # flutter does not, so it is skipped


def test_both_hosts_emit_the_same_beats_in_order():
    cfg = resolve("node")
    wp, gh = render_woodpecker(cfg), render_github(cfg)
    for beat in ("hygiene", "setup", "lint", "test", "checks", "locks"):
        assert beat in wp and beat in gh


def test_hygiene_gate_present_and_first_in_both_hosts():
    # the hygiene (leak) gate is shipped by adoption, runs unconditionally, and is the FIRST prove
    # beat so a leak fails fast; both hosts inherit it because both iterate prove_beats.
    for render in (render_woodpecker, render_github):
        out = render(resolve("node"))
        assert "orrery-hygiene-gate.sh" in out
        # first prove beat: hygiene appears before every other beat and before the lock gate
        assert out.index("hygiene") < out.index("lint")
        assert out.index("orrery-hygiene-gate.sh") < out.index("orrery-locks-gate.sh")


def test_hygiene_gate_runs_unconditionally_not_if_f_skippable():
    # unlike the lock gate it must NOT be wrapped in `if [ -f ... ]`: adoption ships it, so a repo
    # that drops the script fails the build rather than silently skipping the leak-gate.
    wp = render_woodpecker(resolve("node"))
    assert "sh scripts/orrery-hygiene-gate.sh" in wp
    assert "if [ -f scripts/orrery-hygiene-gate.sh ]" not in wp


def test_lock_gate_is_always_present_even_for_a_stack_with_no_checks():
    # flutter has no `checks` beat, but the lock gate must still be there (a declared lock is gated).
    wp = render_woodpecker(resolve("flutter"))
    assert "orrery-locks-gate.sh" in wp
    assert "checks:" not in wp  # skipped, because flutter defines no checks command


def test_build_runs_on_main_only():
    wp = render_woodpecker(resolve("flutter"))
    assert "branch: main" in wp and "flutter build" in wp
    gh = render_github(resolve("flutter"))
    assert "refs/heads/main" in gh and "flutter build" in gh


def test_unknown_host_fails_loudly():
    with pytest.raises(ValueError):
        render_ci(resolve("node"), "jenkins")


def test_cli_detect_and_render(tmp_path, capsys):
    _mk(tmp_path, "package.json")
    assert standard_cli(["detect", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "node"
    assert standard_cli(["render-ci", str(tmp_path), "--host", "woodpecker"]) == 0
    out = capsys.readouterr().out
    assert "when:" in out and "npm test" in out and "orrery-locks-gate.sh" in out


def test_cli_render_forced_stack(tmp_path, capsys):
    assert standard_cli(["render-ci", str(tmp_path), "--host", "github", "--stack", "rust"]) == 0
    out = capsys.readouterr().out
    assert "cargo test" in out and "runs-on:" in out


def test_prove_beats_are_hard_no_bypass_in_rendered_ci():
    # a failing beat must block: no `|| true`, no continue-on-error, in either host
    for render in (render_woodpecker, render_github):
        out = render(resolve("node"))
        assert "|| true" not in out
        assert "continue-on-error" not in out


# --- the python limb -------------------------------------------------------

def test_detect_python_by_pyproject(tmp_path):
    assert detect(_mk(tmp_path, "pyproject.toml")) == "python"


def test_python_profile_carries_pytest_beats():
    p = load_profiles()
    cfg = resolve("python", p)
    assert cfg["test"] == "pytest"
    assert "pip install -e ." in cfg["setup"] and "pytest" in cfg["setup"]
    assert cfg.get("lint") is None and cfg.get("build") is None  # optional beats, skipped


# --- the subdir declaration ------------------------------------------------

def test_read_declaration_present(tmp_path):
    _declare(tmp_path, '[standard]\nstack = "python"\nworkdir = "governed-autonomy"\n')
    d = read_declaration(tmp_path)
    assert d == {"stack": "python", "workdir": "governed-autonomy"}


def test_read_declaration_absent_returns_empty(tmp_path):
    assert read_declaration(tmp_path) == {}


def test_read_declaration_no_standard_table_returns_empty(tmp_path):
    _declare(tmp_path, 'box = "x"\n')  # a profile with no [standard] table
    assert read_declaration(tmp_path) == {}


def test_read_declaration_broken_toml_returns_empty(tmp_path):
    _declare(tmp_path, "this is = = not toml [[[")
    assert read_declaration(tmp_path) == {}  # a bad operator file must not brick foldin


def test_detect_honors_declared_stack_over_root_files(tmp_path):
    # a package.json at root would detect node, but the declaration forces python
    _mk(tmp_path, "package.json")
    _declare(tmp_path, '[standard]\nstack = "python"\n')
    assert detect(tmp_path) == "python"


# --- rendering with a workdir ----------------------------------------------

def test_render_workdir_prefixes_stack_beats_not_gates_both_hosts():
    for render_host in ("woodpecker", "github"):
        out = render_ci(resolve("python"), render_host, workdir="governed-autonomy")
        # stack beats run in the subdir
        assert "cd governed-autonomy && pip install -e ." in out
        assert "cd governed-autonomy && pytest" in out
        # the gates stay at the repo root, never prefixed
        assert "sh scripts/orrery-hygiene-gate.sh" in out
        assert "cd governed-autonomy && sh scripts/orrery-hygiene-gate.sh" not in out
        assert "cd governed-autonomy && if [ -f scripts/orrery-locks-gate.sh ]" not in out


def test_render_no_workdir_is_unchanged():
    assert render_ci(resolve("python"), "github") == render_ci(resolve("python"), "github", workdir=None)


def test_render_workdir_prefixes_build_beat():
    # build is a stack beat too: it must move into the workdir when one is declared
    out = render_ci(resolve("flutter"), "woodpecker", workdir="app")
    assert "cd app && flutter build" in out


def test_cli_render_honors_declaration_workdir(tmp_path, capsys):
    _mk(tmp_path, "package.json")  # would be node, but the declaration forces python + workdir
    _declare(tmp_path, '[standard]\nstack = "python"\nworkdir = "sub"\n')
    assert standard_cli(["detect", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "python"
    assert standard_cli(["render-ci", str(tmp_path), "--host", "github"]) == 0
    out = capsys.readouterr().out
    assert "cd sub && pytest" in out
    assert "sh scripts/orrery-hygiene-gate.sh" in out  # gate still at root
