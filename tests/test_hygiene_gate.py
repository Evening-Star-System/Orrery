"""The shipped hygiene (leak) gate: `sh scripts/orrery-hygiene-gate.sh` scans tracked files for
content that is wrong in ANY repo and fails closed. It is CI-agnostic (one shell script, no tool
dependency), never passes silently (a gate that cannot run exits non-zero), and excludes its own
pattern definitions plus any caller-declared fixture pathspecs.

The forbidden sample strings are ASSEMBLED from parts at runtime so this test file carries no
real-looking secret, yet the file the gate scans matches the gate's patterns.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "templates" / "orrery-hygiene-gate.sh"


def _repo(tmp_path):
    """A fresh git work tree with the shipped gate copied to scripts/, returns the repo dir."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(GATE, tmp_path / "scripts" / "orrery-hygiene-gate.sh")
    return tmp_path


def _run(repo, env=None):
    return subprocess.run(
        ["sh", "scripts/orrery-hygiene-gate.sh"],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def _track(repo, name, content):
    (repo / name).write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)


# Each sample is assembled so the literal never appears whole in this source.
FORBIDDEN = {
    "rfc1918-10": "host = " + "10." + "1.2.3\n",
    "rfc1918-192": "host = " + "192.168." + "1.1\n",
    "rfc1918-172": "host = " + "172." + "16.5.4\n",
    "root-path": "log = " + "/root/" + "secret.log\n",
    "pem-key": ("-" * 5) + "BEGIN RSA PRIVATE KEY" + ("-" * 5) + "\n",
    "github-pat": "token = " + "ghp_" + ("a" * 36) + "\n",
    "aws-key": "id = " + "AKIA" + ("ABCDEFGHIJKLMNOP") + "\n",
    "vault-token": "vt = " + "hvs" + "." + ("Z" * 20) + "\n",
    "slack-token": "st = " + "xoxb-" + ("1234567890abcdef") + "\n",
    "stripe-key": "sk = " + "sk_live_" + ("abcd1234efgh5678ijkl") + "\n",
}


def test_clean_tree_passes(tmp_path):
    repo = _repo(tmp_path)
    _track(repo, "readme.txt", "hello world\na version like 1.2.3.4 is fine\n")
    r = _run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


@pytest.mark.parametrize("name,sample", list(FORBIDDEN.items()))
def test_each_forbidden_class_fails_closed(tmp_path, name, sample):
    repo = _repo(tmp_path)
    _track(repo, "leak.txt", sample)
    r = _run(repo)
    assert r.returncode == 1, f"{name} should fail: {r.stdout + r.stderr}"
    assert "FAIL" in r.stdout
    assert "leak.txt" in r.stdout


def test_gate_script_does_not_flag_its_own_pattern_definitions(tmp_path):
    # the gate's own -e patterns contain literals like /root/ and BEGIN...PRIVATE KEY; the script must
    # exclude itself so a clean tree that merely SHIPS the gate stays green.
    repo = _repo(tmp_path)
    _track(repo, "ok.txt", "nothing to see here\n")
    assert _run(repo).returncode == 0


def test_declared_fixture_can_be_excluded(tmp_path):
    # a repo may keep a deliberate sample (e.g. a security test) and exclude it via the env pathspec.
    repo = _repo(tmp_path)
    _track(repo, "leak.txt", FORBIDDEN["aws-key"])
    assert _run(repo).returncode == 1                       # not excluded: fails
    import os
    env = {**os.environ, "ORRERY_HYGIENE_EXCLUDES": "leak.txt"}
    assert _run(repo, env=env).returncode == 0              # excluded: passes


def test_fails_closed_outside_a_git_work_tree(tmp_path):
    # not a repo at all: the gate must fail (exit 3), never pass silently.
    (tmp_path / "scripts").mkdir()
    shutil.copy(GATE, tmp_path / "scripts" / "orrery-hygiene-gate.sh")
    r = _run(tmp_path)
    assert r.returncode == 3
    assert "GATE ERROR" in r.stdout
