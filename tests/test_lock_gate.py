"""The hard-gate contract: `ess-orrery lock gate` blocks on any regression, holds the floor as the
regeneration mechanism (improve freely, never drop below), and has no bypass. One command probes +
adjudicates, reusing the behavior-lock check so the compare logic is single-sourced.
"""
from orrery.locks import commands


def _manifest(tmp_path, compare="eq", command="cat value.txt"):
    m = tmp_path / "orrery-locks.toml"
    m.write_text(
        "schema = 1\n[[locks]]\n"
        'id = "v"\n'
        'why = "it must not regress"\n'
        f'command = "{command}"\n'
        'capture = "stdout-line"\n'
        f'compare = "{compare}"\n'
    )
    return str(m)


def _set(tmp_path, text):
    (tmp_path / "value.txt").write_text(str(text))


def test_no_manifest_is_nothing_to_gate(tmp_path):
    code, _ = commands.gate(str(tmp_path / "orrery-locks.toml"))
    assert code == 0


def test_clean_passes(tmp_path):
    m = _manifest(tmp_path); _set(tmp_path, "hello")
    commands.capture(m)                         # record golden = hello
    assert commands.gate(m)[0] == 0


def test_eq_regression_blocks(tmp_path):
    m = _manifest(tmp_path); _set(tmp_path, "hello")
    commands.capture(m)
    _set(tmp_path, "goodbye")                    # behavior changed
    code, msgs = commands.gate(m)
    assert code == 1 and any("GATE FAIL" in x for x in msgs)


def test_floor_allows_improvement_blocks_a_drop(tmp_path):
    m = _manifest(tmp_path, compare=">=")
    _set(tmp_path, "90"); commands.capture(m)    # floor = 90
    _set(tmp_path, "95")                          # improved
    assert commands.gate(m)[0] == 0
    _set(tmp_path, "80")                          # regressed below the floor
    assert commands.gate(m)[0] == 1


def test_ceiling_allows_decrease_blocks_a_rise(tmp_path):
    m = _manifest(tmp_path, compare="<=")
    _set(tmp_path, "100"); commands.capture(m)   # ceiling = 100 (e.g. bundle size)
    _set(tmp_path, "80")                          # got smaller: fine
    assert commands.gate(m)[0] == 0
    _set(tmp_path, "120")                         # grew past the ceiling
    assert commands.gate(m)[0] == 1


def test_ratchet_raises_the_floor(tmp_path):
    m = _manifest(tmp_path, compare=">=")
    _set(tmp_path, "90"); commands.capture(m)     # floor 90
    _set(tmp_path, "95"); commands.capture(m)     # ratchet: re-lock at the improved value -> floor 95
    _set(tmp_path, "92")                           # would have passed the old floor, not the new one
    assert commands.gate(m)[0] == 1


def test_incomplete_probe_blocks(tmp_path):
    # a command that cannot produce an observed value must fail the gate, never pass silently
    m = tmp_path / "orrery-locks.toml"
    m.write_text(
        'schema = 1\n[[locks]]\nid = "v"\nwhy = "w"\ncommand = "false"\n'
        'capture = "stdout-line"\ncompare = "eq"\ngolden = "x"\n'
    )
    assert commands.gate(str(m))[0] == 1


def test_gate_has_no_bypass_flag():
    # the gate subcommand accepts no --skip/--force; argparse rejects the unknown flag (no bypass exists)
    import pytest

    from orrery.locks import cli
    with pytest.raises(SystemExit):
        cli.main(["gate", "--skip"])
