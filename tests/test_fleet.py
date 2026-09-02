"""Fleet reconcile: reconcile a set of profiles and roll their verdicts into one.

The fleet is generic (a glob of profiles); it reuses the single-profile engine, the enforcer
seam, and the reporters rather than forking them. These tests pin the aggregation rules that
matter: a fleet is clean only when every profile ran AND every profile was clean; an
unloadable profile is a reported hole, not a silent pass; an empty match is an error.
"""

import json

import pytest

from orrery.reconciler.__main__ import main as reconcile
from orrery.reconciler.fleet import run_fleet


def _profile(path, box, required):
    # A declared-presence profile: required paths that exist -> clean, missing -> FAIL.
    lines = [f'box = "{box}"', "", "[[checks]]", 'id = "declared-presence"', "required = ["]
    lines += [f'  "{p}",' for p in required]
    lines.append("]")
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def _clean(tmp_path, name):
    # requires a path that exists (the profile file itself), so the box is clean
    p = tmp_path / f"{name}.toml"
    return _profile(p, name, [str(p)])


def _dirty(tmp_path, name):
    p = tmp_path / f"{name}.toml"
    return _profile(p, name, [str(tmp_path / "does-not-exist")])


# --- aggregation logic -----------------------------------------------------------------


def test_all_clean_is_a_clean_fleet(tmp_path):
    fleet = run_fleet([_clean(tmp_path, "a"), _clean(tmp_path, "b")])
    assert fleet.clean and fleet.exit_code == 0 and fleet.dirty == []


def test_one_dirty_profile_makes_the_fleet_dirty(tmp_path):
    fleet = run_fleet([_clean(tmp_path, "a"), _dirty(tmp_path, "b")])
    assert not fleet.clean and fleet.exit_code == 1
    assert [r.box for r in fleet.dirty] == ["b"]


def test_unloadable_profile_is_a_reported_hole_not_a_pass(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is not valid toml = = =\n")
    fleet = run_fleet([_clean(tmp_path, "a"), str(bad)])
    hole = [r for r in fleet.runs if r.result is None][0]
    assert hole.error and not hole.clean
    assert not fleet.clean  # a project we could not measure is not a clean project


def test_empty_fleet_is_not_clean():
    # "nothing was checked" must never read as "everything passed".
    assert run_fleet([]).clean is False


# --- CLI: the same seam and reporters as a single profile -------------------------------


def test_cli_profiles_glob_clean_exits_zero(tmp_path, capsys):
    _clean(tmp_path, "a")
    _clean(tmp_path, "b")
    code = reconcile(["--profiles", str(tmp_path / "*.toml")])
    out = capsys.readouterr().out
    assert code == 0 and "CLEAN" in out and "2 profile(s)" in out


def test_cli_profiles_glob_dirty_exits_one_and_names_the_box(tmp_path, capsys):
    _clean(tmp_path, "a")
    _dirty(tmp_path, "bad-box")
    code = reconcile(["--profiles", str(tmp_path / "*.toml")])
    out = capsys.readouterr().out
    assert code == 1 and "DRIFT" in out and "bad-box" in out


def test_cli_report_enforcer_observes_a_dirty_fleet_without_gating(tmp_path, capsys):
    _dirty(tmp_path, "bad-box")
    # the enforcer seam acts on the fleet verdict exactly as it does on a single result
    code = reconcile(["--profiles", str(tmp_path / "*.toml"), "--enforce", "report"])
    assert code == 0  # observed, not gated


def test_cli_empty_glob_is_an_error_not_an_all_clear(tmp_path, capsys):
    code = reconcile(["--profiles", str(tmp_path / "none-*.toml")])
    err = capsys.readouterr().err
    assert code == 2 and "no profiles matched" in err


def test_cli_fleet_json_is_valid_and_carries_a_rollup(tmp_path, capsys):
    _clean(tmp_path, "a")
    _dirty(tmp_path, "b")
    code = reconcile(["--profiles", str(tmp_path / "*.toml"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["kind"] == "fleet" and payload["clean"] is False
    assert payload["summary"] == {"profiles": 2, "clean": 1, "need_attention": 1}
    assert len(payload["profiles"]) == 2


def test_cli_strict_fails_the_fleet_on_a_bad_profile(tmp_path, capsys):
    good = _clean(tmp_path, "a")  # noqa: F841
    bad = tmp_path / "b.toml"
    bad.write_text('box = "b"\n[[checks]]\nid = "no-such-check"\n')
    code = reconcile(["--profiles", str(tmp_path / "*.toml"), "--strict"])
    err = capsys.readouterr().err
    assert code == 2 and "--strict" in err


def test_cli_profile_and_profiles_are_mutually_exclusive(tmp_path):
    p = _clean(tmp_path, "a")
    with pytest.raises(SystemExit):
        reconcile(["--profile", p, "--profiles", str(tmp_path / "*.toml")])
