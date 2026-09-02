"""Regression tests for the parser and safety fixes from the 2026-08-07 audit."""

import subprocess
import sys

from orrery.reconciler.checks.fleet_reach import FleetReachCheck
from orrery.reconciler.checks.org_map import parse_bash_assoc, parse_bash_case_func
from orrery.reconciler.model import Severity


def test_bash_case_func_name_is_boundary_anchored():
    # org_of must not match inside my_org_of (which would return the wrong function's map)
    text = (
        'my_org_of(){ case "$1" in wrong) echo wrong-org;; esac; }\n'
        'org_of(){ case "$1" in globex|initech) echo globex-inc;; umbrella) echo umbrella;; *) echo "";; esac; }\n'
    )
    got = parse_bash_case_func(text, "org_of", implied_host="github.com")
    assert got == {
        "globex": ("github.com", "globex-inc"),
        "initech": ("github.com", "globex-inc"),
        "umbrella": ("github.com", "umbrella"),
    }
    assert "wrong" not in got


def test_bash_case_body_with_brace_expansion_not_truncated():
    text = 'org_of(){ local x="${1}"; case "$x" in globex) echo globex-inc;; esac; }'
    got = parse_bash_case_func(text, "org_of", implied_host="github.com")
    assert got == {"globex": ("github.com", "globex-inc")}


def test_bash_assoc_strips_quotes():
    text = 'declare -A ACCT=( [globex]="github.com/Globex-Inc" [umbrella]=github.com/umbrella )'
    got = parse_bash_assoc(text, "ACCT")
    assert got["globex"] == ("github.com", "Globex-Inc")
    assert got["umbrella"] == ("github.com", "umbrella")


def test_bash_assoc_empty_value_is_kept_not_dropped():
    text = "declare -A ACCT=( [acme]= [globex]=github.com/Globex-Inc )"
    got = parse_bash_assoc(text, "ACCT")
    assert "acme" in got  # must not silently vanish
    assert got["acme"] == (None, "")


def test_fleet_reach_refuses_unsafe_host():
    class NeverProber:
        def can_reach(self, host, timeout):
            raise AssertionError("must not probe an unsafe host")

    check = FleetReachCheck(prober=NeverProber())
    (f,) = check.run(
        {"edges": [{"to": "-oProxyCommand=touch /tmp/x", "expect": "ok"}]}, box=None
    )
    assert f.severity == Severity.WARN
    assert "unsafe" in f.message


def test_cli_bad_profile_exits_clean_not_traceback(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('this is = not valid toml [[[', encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "orrery.reconciler", "--profile", str(bad), "--json"],
        capture_output=True,
        text=True,
        cwd=_repo_root(),
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert '"error"' in proc.stdout  # clean JSON error on stdout


def _repo_root() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parent.parent)
