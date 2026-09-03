"""ruleset promote: adopt or bump a canon reference in a profile, as a reviewable diff."""

from orrery.reconciler.profile import load_profile
from orrery.reconciler.ruleset import promote_text
from orrery.reconciler.ruleset_cli import main as ruleset_cli

_CANON = 'name = "order-canon"\nversion = "1.0.0"\n[[checks]]\nid = "behavior-lock"\nwhy = "w"\n'


def _canon(tmp_path, version="1.0.0"):
    p = tmp_path / "order.ruleset.toml"
    p.write_text(_CANON.replace('version = "1.0.0"', f'version = "{version}"'))
    return p


def test_adopt_adds_a_reference_that_loads(tmp_path):
    canon = _canon(tmp_path)
    prof = tmp_path / "p.toml"
    after, action = promote_text('box = "m"\n', str(canon), str(prof))
    assert action == "adopt"
    prof.write_text(after)
    assert [c.id for c in load_profile(prof).checks] == ["behavior-lock"]  # the canon rule flows in


def test_adopt_pins_the_canon_version(tmp_path):
    canon = _canon(tmp_path, "2.3.4")
    prof = tmp_path / "p.toml"
    after, action = promote_text('box = "m"\n', str(canon), str(prof))
    assert action == "adopt" and 'pin = "2.3.4"' in after


def test_bump_updates_an_existing_pin(tmp_path):
    _canon(tmp_path, "2.0.0")
    prof = tmp_path / "p.toml"
    text = 'box = "m"\n[[rulesets]]\npath = "order.ruleset.toml"\npin = "1.0.0"\n'
    prof.write_text(text)
    after, action = promote_text(text, str(tmp_path / "order.ruleset.toml"), str(prof))
    assert action == "bump" and 'pin = "2.0.0"' in after and 'pin = "1.0.0"' not in after


def test_noop_when_already_at_version(tmp_path):
    _canon(tmp_path, "1.0.0")
    prof = tmp_path / "p.toml"
    text = 'box = "m"\n[[rulesets]]\npath = "order.ruleset.toml"\npin = "1.0.0"\n'
    after, action = promote_text(text, str(tmp_path / "order.ruleset.toml"), str(prof))
    assert action == "noop" and after == text


def test_cli_prints_diff_and_does_not_write_without_apply(tmp_path, capsys):
    canon = _canon(tmp_path)
    prof = tmp_path / "p.toml"
    prof.write_text('box = "m"\n')
    assert ruleset_cli(["promote", str(canon), "--into", str(prof)]) == 0
    out = capsys.readouterr().out
    assert "[[rulesets]]" in out and "+" in out       # a unified diff proposing the addition
    assert prof.read_text() == 'box = "m"\n'           # unchanged: diff only


def test_absolute_writes_the_canon_absolute_path(tmp_path):
    canon = _canon(tmp_path)
    prof = tmp_path / "sub" / "p.toml"
    prof.parent.mkdir()
    after, action = promote_text('box = "m"\n', str(canon), str(prof), absolute=True)
    assert action == "adopt"
    assert f'path = "{canon}"' in after  # the absolute canon path, verbatim, not a ../ relative
    prof.write_text(after)
    assert [c.id for c in load_profile(prof).checks] == ["behavior-lock"]  # still resolves


def test_absolute_reference_is_detected_for_noop_and_bump(tmp_path):
    # An absolute reference, once written, must be recognised on re-promote (noop / bump), not
    # duplicated. This is what makes the fleet backfill idempotent.
    canon = _canon(tmp_path, "1.0.0")
    prof = tmp_path / "p.toml"
    after, _ = promote_text('box = "m"\n', str(canon), str(prof), absolute=True)
    _, action = promote_text(after, str(canon), str(prof), absolute=True)
    assert action == "noop"
    _canon(tmp_path, "1.1.0")  # canon advances
    bumped, action = promote_text(after, str(canon), str(prof), absolute=True)
    assert action == "bump" and 'pin = "1.1.0"' in bumped and str(canon) in bumped


def test_cli_apply_writes_and_loads(tmp_path, capsys):
    canon = _canon(tmp_path)
    prof = tmp_path / "p.toml"
    prof.write_text('box = "m"\n')
    assert ruleset_cli(["promote", str(canon), "--into", str(prof), "--apply"]) == 0
    assert "[[rulesets]]" in prof.read_text()
    load_profile(prof)  # the written profile loads
