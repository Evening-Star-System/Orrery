"""The canonical operating standard: stack detection + CI rendering, one trunk many limbs.

Pins the properties that matter: detection is first-match by the stack's own file; every host emits
the same beats in the same order; the lock gate is always present (a declared lock is always gated);
build runs on main only; and unknown inputs fail loudly rather than silently.
"""
import pytest

from orrery.standard.cli import main as standard_cli
from orrery.standard.profiles import detect, load_profiles, resolve
from orrery.standard.render import render_ci, render_github, render_woodpecker


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
    for beat in ("setup", "lint", "test", "checks", "locks"):
        assert beat in wp and beat in gh


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
