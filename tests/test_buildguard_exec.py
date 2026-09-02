"""Regression tests for the two bugs that only surfaced by running the thing.

Both were "success paths that had never been exercised": code that looked obviously
correct, passed review, and did nothing at all in production.
"""

import signal
import subprocess
import types

import pytest

from orrery.buildguard import cli


class _Args:
    def __init__(self, **kw):
        self.no_scope = False
        self.mem_max = "5G"
        self.swap_max = "512M"
        self.slice_unit = "builds.slice"
        self.command = ["true"]
        self.__dict__.update(kw)


def _fake_run(returncode):
    def run(cmd, *a, **kw):
        return types.SimpleNamespace(returncode=returncode, args=cmd)
    return run


def test_oom_kill_is_detected_from_a_negative_returncode(monkeypatch, capsys):
    """THE BUG: a scope OOM kills systemd-run too, so subprocess reports -9.

    The shell renders sys.exit(-9) as 247, and the original check compared against
    137/247 -- the numbers a SHELL prints -- so it never matched and the operator
    never saw why their build died. Verified against work-box 2026-08-20.
    """
    monkeypatch.setattr(subprocess, "run", _fake_run(-signal.SIGKILL))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/systemd-run")
    rc = cli._exec_build(_Args(), "hog")
    err = capsys.readouterr().err
    assert "OOM-killed inside its own scope" in err
    assert "the rest of the box was protected" in err
    assert rc == 128 + signal.SIGKILL, "must normalise to the 128+N shell convention"


def test_other_signals_are_reported_but_not_called_oom(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", _fake_run(-signal.SIGTERM))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/systemd-run")
    rc = cli._exec_build(_Args(), "build")
    err = capsys.readouterr().err
    assert "died on signal 15" in err
    assert "OOM" not in err
    assert rc == 128 + signal.SIGTERM


def test_normal_exit_codes_pass_through_untouched(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", _fake_run(3))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/systemd-run")
    assert cli._exec_build(_Args(), "build") == 3
    assert "OOM" not in capsys.readouterr().err


def test_missing_systemd_run_falls_back_to_uncapped_with_a_warning(monkeypatch, capsys):
    """Degrade to an uncapped build rather than refusing to build at all."""
    monkeypatch.setattr(subprocess, "run", _fake_run(0))
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    assert cli._exec_build(_Args(), "build") == 0
    assert "running uncapped" in capsys.readouterr().err


def test_scope_command_carries_the_caps(monkeypatch):
    seen = {}

    def run(cmd, *a, **kw):
        seen["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, args=cmd)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/systemd-run")
    cli._exec_build(_Args(mem_max="2G", swap_max="256M", command=["make", "all"]), "x")
    cmd = seen["cmd"]
    assert "systemd-run" in cmd[0]
    assert "--scope" in cmd
    assert "--slice=builds.slice" in cmd
    assert "MemoryMax=2G" in cmd
    assert "MemorySwapMax=256M" in cmd
    assert cmd[-2:] == ["make", "all"]


# -- session attribution ------------------------------------------------------------

def test_own_session_falls_back_to_the_named_socket_when_not_in_tmux(monkeypatch):
    """THE BUG: work-box's server is on `-L work`, so the default socket found nothing
    and every holder recorded `session ?` -- the one field the guard exists to show."""
    monkeypatch.delenv("TMUX", raising=False)
    calls = []

    def run(cmd, *a, **kw):
        calls.append(cmd)
        if "-L" in cmd:
            return types.SimpleNamespace(returncode=0, stdout="proj-acme-Widget\n")
        return types.SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(subprocess, "run", run)
    assert cli._own_session() == "proj-acme-Widget"
    assert any("-L" in c for c in calls), "must try the named socket"


def test_own_session_prefers_the_ambient_server_when_inside_a_pane(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-0/work,123,0")
    calls = []

    def run(cmd, *a, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="guard-probe\n")

    monkeypatch.setattr(subprocess, "run", run)
    assert cli._own_session() == "guard-probe"
    assert len(calls) == 1, "inside a pane, $TMUX already names the right server"
    assert "-L" not in calls[0]


def test_own_session_never_raises_when_tmux_is_absent(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("PROJ_SESSION", raising=False)

    def boom(*a, **kw):
        raise OSError("no tmux")

    monkeypatch.setattr(subprocess, "run", boom)
    assert cli._own_session() is None
