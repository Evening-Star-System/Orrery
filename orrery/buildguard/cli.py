"""`heavy-build`: check before you build, then build inside your own ceiling.

Two subcommands:

    heavy-build status                 what is running, and is there room
    heavy-build run -- <cmd...>        wait your turn, then run <cmd> capped

`run` is the whole point, and it does three things a bare build does not:

  1. WAITS for any other heavy build, guarded or not. Guarded ones are found through
     the lock; unguarded ones through their process signature, because the rule only
     helps if it also survives someone forgetting it.
  2. WAITS for the shared slice to have headroom, so a build does not start into a box
     that is already throttled and merely deepen the hole.
  3. Runs the build in a transient systemd scope under `builds.slice`, which lives in
     system.slice and therefore has its OWN MemoryMax. A build that overruns now dies
     alone and immediately, with a clear OOM in its own scope, instead of dragging the
     interactive sessions into a stall nobody can exit.

Exit code is the build's own, so this is drop-in in front of any existing command.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

from .lock import BuildLock, Holder, LockBusy
from .probe import (
    BUILDS_SLICE, DEFAULT_SLICE, HeavyProc, headroom, heavy_processes, human,
)

# A build needs room to start. Below this much space under the brake, starting one is
# how you get a stall rather than a build.
DEFAULT_MIN_FREE_GB = 3.0
DEFAULT_SCOPE_MEM_MAX = "5G"
DEFAULT_SCOPE_SWAP_MAX = "512M"
_GB = 1024 * 1024 * 1024


def _own_session(socket: str = "work") -> str | None:
    """Best-effort: which tmux session is invoking us.

    Two attempts, in this order, because neither alone covers the real cases:

      1. A bare `tmux display-message`, which resolves through $TMUX and so names the
         right session on ANY socket -- but only when we are genuinely inside a pane.
      2. The named socket, for a caller that is NOT inside tmux (a timer, a hook, an
         ssh one-liner) but shares the box with sessions that are.

    work-box's server runs on `-L work`, so querying the DEFAULT socket -- as this
    originally did -- found nothing and every holder recorded `session ?`, which is
    exactly the field the guard exists to show. Attribution stays best-effort: an
    unattributable build is still a build and must never fail the guard.
    """
    attempts = [["tmux", "display-message", "-p", "#{session_name}"]]
    if os.environ.get("TMUX") is None:
        attempts.append(
            ["tmux", "-L", socket, "display-message", "-p", "#{session_name}"]
        )
    for cmd in attempts:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            continue
    return os.environ.get("PROJ_SESSION") or None


def _others(procs: list[HeavyProc]) -> list[HeavyProc]:
    """Heavy builds other than our own process.

    Excluding just our pid is sufficient because every caller runs this BEFORE the
    build is spawned, so we have no heavy descendants yet. If that ever stops being
    true, this needs a real descendant walk.
    """
    me = os.getpid()
    return [p for p in procs if p.pid != me]


def _fmt_headroom(h) -> list[str]:
    limits = f"  (brake {human(h.high)}, wall {human(h.maximum)})" if h.high else ""
    out = [
        f"  slice          {h.slice_path}",
        f"  in use         {human(h.current)}{limits}",
        f"  free to brake  {human(h.free_to_brake)}",
        f"  anon / cache   {human(h.anon)} anon / {human(h.file_cache)} cache",
        f"  swap           {human(h.swap_current)} / {human(h.swap_max)}"
        + (f"   fail={h.swap_fail}" if h.swap_fail else ""),
        f"  PSI full       avg10={h.psi_full_avg10}  avg300={h.psi_full_avg300}",
    ]
    for n in h.notes:
        out.append(f"  note           {n}")
    return out


def cmd_status(args) -> int:
    h = headroom(args.slice)
    procs = heavy_processes()
    holder = BuildLock.current_holder()

    if args.json:
        print(json.dumps({
            "headroom": h.as_dict(),
            "heavy": [p.as_dict() for p in procs],
            "holder": holder.__dict__ if holder else None,
        }, indent=2, default=str))
        return 0

    print("BUILD GUARD STATUS")
    print()
    print("Memory headroom:")
    for line in _fmt_headroom(h):
        print(line)
    print()
    if holder:
        print(f"Build lock:    HELD by {holder.label} (pid {holder.pid}, "
              f"session {holder.session or '?'}) for {holder.held_for}")
        print(f"               {holder.command}")
    else:
        print("Build lock:    free")
    print()
    if procs:
        print(f"Heavy processes ({len(procs)}):")
        for p in procs:
            print(f"  {p.kind:<14} pid {p.pid:<8} {human(p.rss):>9}  "
                  f"{p.etime:>12}  session={p.session or '?'}")
    else:
        print("Heavy processes: none")
    print()

    free = h.free_to_brake
    min_free = int(args.min_free_gb * _GB)
    if holder:
        print(f"VERDICT: WAIT, {holder.label} is building.")
        return 1
    if procs:
        print(f"VERDICT: WAIT, {len(procs)} unguarded heavy process(es) running.")
        return 1
    if free is not None and free < min_free:
        print(f"VERDICT: WAIT, only {human(free)} under the brake "
              f"(need {human(min_free)}).")
        return 1
    print("VERDICT: GO, lock free, no heavy builds, headroom available.")
    return 0


def _wait_for_room(args, label: str) -> None:
    """Block until no unguarded heavy build is running and there is headroom."""
    min_free = int(args.min_free_gb * _GB)
    started = time.monotonic()
    warned = False
    while True:
        procs = _others(heavy_processes())
        h = headroom(args.slice)
        free = h.free_to_brake
        tight = free is not None and free < min_free
        if not procs and not tight:
            if warned:
                print(f"[heavy-build] clear after {int(time.monotonic()-started)}s; "
                      f"starting {label}", file=sys.stderr)
            return
        waited = int(time.monotonic() - started)
        if args.wait_timeout and waited >= args.wait_timeout:
            reason = "unguarded builds still running" if procs else "no headroom"
            print(f"[heavy-build] giving up after {waited}s: {reason}", file=sys.stderr)
            raise LockBusy(reason)
        if procs:
            who = ", ".join(f"{p.kind}(pid {p.pid}, session {p.session or '?'})"
                            for p in procs[:4])
            print(f"[heavy-build] waiting {waited}s, heavy build(s) running: {who}",
                  file=sys.stderr)
        else:
            print(f"[heavy-build] waiting {waited}s, only {human(free)} under the "
                  f"brake, need {human(min_free)}", file=sys.stderr)
        warned = True
        time.sleep(args.poll)


def cmd_run(args) -> int:
    if not args.command:
        print("heavy-build run: nothing to run (use -- <command>)", file=sys.stderr)
        return 2

    label = args.label or os.path.basename(args.command[0])
    session = _own_session()
    cwd = os.getcwd()
    pretty = " ".join(args.command)

    def on_wait(holder, waited):
        if holder:
            print(f"[heavy-build] waiting {int(waited)}s for {holder.label} "
                  f"(session {holder.session or '?'}, held {holder.held_for})",
                  file=sys.stderr)
        else:
            print(f"[heavy-build] waiting {int(waited)}s for the build lock",
                  file=sys.stderr)

    lock = BuildLock()
    try:
        lock.acquire(
            Holder(pid=os.getpid(), label=label, command=pretty,
                   session=session, cwd=cwd, started_at=time.time()),
            timeout=args.wait_timeout or None, on_wait=on_wait, poll=args.poll,
        )
    except LockBusy as exc:
        print(f"[heavy-build] not starting: {exc}", file=sys.stderr)
        return 75  # EX_TEMPFAIL: a retry later is the right response

    try:
        # The lock only serialises guarded builds. Something started by hand can still
        # be running, and the slice can still be recovering from one; wait for both.
        try:
            _wait_for_room(args, label)
        except LockBusy:
            return 75
        return _exec_build(args, label)
    finally:
        lock.release()


def _exec_build(args, label: str) -> int:
    cmd = list(args.command)
    if args.no_scope or not shutil.which("systemd-run"):
        if not args.no_scope:
            print("[heavy-build] systemd-run unavailable; running uncapped",
                  file=sys.stderr)
        return subprocess.run(cmd).returncode

    unit = f"build-{label}-{os.getpid()}".replace("/", "-").replace(" ", "-")
    wrapped = [
        "systemd-run", "--scope", "--quiet",
        f"--unit={unit}",
        f"--slice={args.slice_unit}",
        "-p", f"MemoryMax={args.mem_max}",
        "-p", f"MemorySwapMax={args.swap_max}",
        # Die alone and loudly rather than stall the box. This is the whole design:
        # a build that will not fit should FAIL, not throttle everything beside it.
        "-p", "OOMPolicy=continue",
        "--",
    ] + cmd
    print(f"[heavy-build] running {label} in {args.slice_unit} "
          f"(MemoryMax={args.mem_max}, MemorySwapMax={args.swap_max})", file=sys.stderr)
    rc = subprocess.run(wrapped).returncode

    # HOW AN OOM ACTUALLY ARRIVES HERE, verified on work-box 2026-08-20 rather than
    # assumed: the scope OOM kills systemd-run too, so subprocess reports a NEGATIVE
    # returncode (-SIGKILL = -9), not 137. A shell then shows 247, because sys.exit(-9)
    # is truncated to (-9 & 0xFF). Checking for 137 or 247 here -- the numbers the
    # SHELL prints -- never matched, so this warning did not fire once until the path
    # was actually exercised. Compare against Pythons convention, not the shells.
    if rc < 0:
        sig = -rc
        if sig == signal.SIGKILL:
            print(f"[heavy-build] {label} was OOM-killed inside its own scope "
                  f"(MemoryMax={args.mem_max}). Raise the cap or shrink the build -- "
                  f"the rest of the box was protected.", file=sys.stderr)
        else:
            print(f"[heavy-build] {label} died on signal {sig}", file=sys.stderr)
        # Normalise to the shell convention so callers and CI see a stable 128+N
        # instead of a truncated negative.
        return 128 + sig
    return rc


def build_parser() -> argparse.ArgumentParser:
    # Shared options live on a PARENT parser and are attached to each subcommand, not
    # to the top level. On the top level argparse would require them before the
    # subcommand (`heavy-build --poll 5 run ...`), which is the wrong way round from
    # every operator's expectation and silently errors out when they get it wrong.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--slice", default=DEFAULT_SLICE,
                        help="cgroup path of the shared slice to measure")
    common.add_argument("--min-free-gb", type=float, default=DEFAULT_MIN_FREE_GB,
                        help="required headroom under the brake before starting")
    common.add_argument("--poll", type=float, default=10.0,
                        help="seconds between checks while waiting")
    common.add_argument("--wait-timeout", type=int, default=0,
                        help="give up after N seconds (0 = wait forever)")

    p = argparse.ArgumentParser(
        prog="heavy-build",
        description="Serialise and cap resource-heavy builds on a shared box.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", parents=[common],
                       help="what is running and whether there is room")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    r = sub.add_parser("run", parents=[common],
                       help="wait your turn, then run a build capped")
    r.add_argument("--label", help="name for this build in status output")
    r.add_argument("--mem-max", default=DEFAULT_SCOPE_MEM_MAX)
    r.add_argument("--swap-max", default=DEFAULT_SCOPE_SWAP_MAX)
    r.add_argument("--slice-unit", default="builds.slice")
    r.add_argument("--no-scope", action="store_true",
                   help="do not wrap in systemd-run (debugging only)")
    r.add_argument("command", nargs=argparse.REMAINDER)
    r.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "command", None) and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
