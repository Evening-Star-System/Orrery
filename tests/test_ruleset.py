"""Rulesets: the format, adoption-by-reference into a profile, pinning, and the CLI.
Adoption is exercised through the real load_profile so 'declare once, applies to many' is
proven, not asserted."""

import json

import pytest

from orrery.reconciler.profile import load_profile
from orrery.reconciler.ruleset import Ruleset, apply_rulesets, load_ruleset
from orrery.reconciler.ruleset_cli import main as ruleset_cli


_CANON = (
    'name = "order-canon"\n'
    'version = "1.0.0"\n'
    "[[checks]]\n"
    'id = "behavior-lock"\n'
    'why = "A shipped behavior never silently regresses."\n'
    "[[checks.repos]]\n"
    'root = "/some/repo"\n'
)


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    return p


# --- the format ---------------------------------------------------------------------

def test_load_ruleset_reads_name_version_and_rules(tmp_path):
    rs = load_ruleset(_write(tmp_path, "c.ruleset.toml", _CANON))
    assert rs.name == "order-canon" and rs.version == "1.0.0"
    assert rs.checks[0]["id"] == "behavior-lock" and "why" in rs.checks[0]


def test_missing_name_or_version_raises(tmp_path):
    with pytest.raises(ValueError):
        load_ruleset(_write(tmp_path, "n.toml", 'version = "1"\n'))
    with pytest.raises(ValueError):
        load_ruleset(_write(tmp_path, "v.toml", 'name = "x"\n'))


def test_rule_without_a_check_id_raises(tmp_path):
    body = 'name = "x"\nversion = "1"\n[[checks]]\nwhy = "no id"\n'
    with pytest.raises(ValueError):
        load_ruleset(_write(tmp_path, "bad.toml", body))


# --- adoption by reference (through the real profile loader) -------------------------

def _profile_referencing(tmp_path, extra=""):
    _write(tmp_path, "order.ruleset.toml", _CANON)
    body = 'box = "melisae"\n[[rulesets]]\npath = "order.ruleset.toml"\n' + extra
    return _write(tmp_path, "profile.toml", body)


def test_a_profile_adopts_the_canon_rules(tmp_path):
    profile = load_profile(_profile_referencing(tmp_path))
    ids = [c.id for c in profile.checks]
    assert ids == ["behavior-lock"]  # the canon rule flowed in
    # the why is stripped: it never becomes a check option
    assert "why" not in profile.checks[0].options


def test_a_local_check_overrides_a_canon_rule_of_the_same_id(tmp_path):
    # the project declares its own behavior-lock; it must win over the canon's
    extra = '[[checks]]\nid = "behavior-lock"\n[[checks.repos]]\nroot = "/local/override"\n'
    profile = load_profile(_profile_referencing(tmp_path, extra))
    assert len([c for c in profile.checks if c.id == "behavior-lock"]) == 1
    assert profile.checks[0].options["repos"][0]["root"] == "/local/override"


def test_pin_mismatch_fails_loudly(tmp_path):
    _write(tmp_path, "order.ruleset.toml", _CANON)  # version 1.0.0
    body = 'box = "m"\n[[rulesets]]\npath = "order.ruleset.toml"\npin = "2.0.0"\n'
    profile = _write(tmp_path, "profile.toml", body)
    with pytest.raises(ValueError, match="pinned to 2.0.0"):
        load_profile(profile)


def test_matching_pin_loads(tmp_path):
    _write(tmp_path, "order.ruleset.toml", _CANON)
    body = 'box = "m"\n[[rulesets]]\npath = "order.ruleset.toml"\npin = "1.0.0"\n'
    profile = load_profile(_write(tmp_path, "profile.toml", body))
    assert [c.id for c in profile.checks] == ["behavior-lock"]


def test_a_profile_with_no_rulesets_is_unchanged():
    data = {"box": "x", "checks": [{"id": "behavior-lock"}]}
    assert apply_rulesets(data, __import__("pathlib").Path(".")) is data


# --- the CLI ------------------------------------------------------------------------

def test_validate_accepts_a_sound_canon(tmp_path, capsys):
    assert ruleset_cli(["validate", str(_write(tmp_path, "c.toml", _CANON))]) == 0


def test_validate_rejects_an_unknown_check_id(tmp_path, capsys):
    body = 'name = "x"\nversion = "1"\n[[checks]]\nid = "no-such-check"\nwhy = "w"\n'
    assert ruleset_cli(["validate", str(_write(tmp_path, "c.toml", body))]) == 2


def test_describe_shows_each_rule_and_its_why(tmp_path, capsys):
    assert ruleset_cli(["describe", str(_write(tmp_path, "c.toml", _CANON))]) == 0
    out = capsys.readouterr().out
    assert "order-canon" in out and "v1.0.0" in out and "never silently regresses" in out


def test_describe_json_is_machine_readable(tmp_path, capsys):
    ruleset_cli(["describe", "--json", str(_write(tmp_path, "c.toml", _CANON))])
    doc = json.loads(capsys.readouterr().out)
    assert doc["name"] == "order-canon" and doc["checks"][0]["id"] == "behavior-lock"


# --- principles: the conduct rules a canon carries alongside checks ------------------

_WITH_PRINCIPLE = _CANON + (
    "\n[[principles]]\n"
    'id = "verify-before-assert"\n'
    'statement = "Before stating a cause, a date, or that something does not exist, check it."\n'
    'why = "A fast wrong answer costs more than a slow verified one."\n'
    'enforced_by = "agent-runtime"\n'
)


def test_load_ruleset_reads_principles(tmp_path):
    rs = load_ruleset(_write(tmp_path, "c.toml", _WITH_PRINCIPLE))
    assert rs.principles[0]["id"] == "verify-before-assert"
    assert rs.checks[0]["id"] == "behavior-lock"


def test_principle_without_id_or_statement_raises(tmp_path):
    no_id = 'name="x"\nversion="1"\n[[principles]]\nstatement = "s"\n'
    with pytest.raises(ValueError):
        load_ruleset(_write(tmp_path, "a.toml", no_id))
    no_stmt = 'name="x"\nversion="1"\n[[principles]]\nid = "p"\n'
    with pytest.raises(ValueError):
        load_ruleset(_write(tmp_path, "b.toml", no_stmt))


def test_principles_do_not_merge_into_a_profile_as_checks(tmp_path):
    # a canon's principles are conduct rules, not reconciler checks; adopting the canon runs its
    # checks but never turns a principle into a check.
    _write(tmp_path, "order.ruleset.toml", _WITH_PRINCIPLE)
    prof = _write(tmp_path, "p.toml", 'box="m"\n[[rulesets]]\npath="order.ruleset.toml"\n')
    profile = load_profile(prof)
    assert [c.id for c in profile.checks] == ["behavior-lock"]  # only the check, not the principle


def test_describe_shows_a_principle_with_its_statement_and_enforcer(tmp_path, capsys):
    ruleset_cli(["describe", str(_write(tmp_path, "c.toml", _WITH_PRINCIPLE))])
    out = capsys.readouterr().out
    assert "verify-before-assert" in out and "agent-runtime" in out and "check it" in out.lower()
