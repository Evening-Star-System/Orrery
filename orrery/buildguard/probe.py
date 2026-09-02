"""What is running, and does the box have room for one more build.

Read-only. Every input is /proc, /sys/fs/cgroup, or a `tmux list-panes` read, so a
probe can never change the state it is describing.

Two questions, deliberately kept separate, because conflating them is how the
2026-08-20 stall was missed for 1h42m:

  is_busy()   Is another heavy build already running?  -> a scheduling question
  headroom()  Can this slice absorb another one?       -> a capacity question

A guarded build answers both. An UNGUARDED build (started by hand, or by a session
that did not know the rule) holds no lock, so `is_busy` cannot see it from the lock
alone, which is why heavy_processes() scans /proc for build signatures directly. The
guard has to work against the honest case AND the case where someone forgot.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

CGROUP_ROOT = "/sys/fs/cgroup"
DEFAULT_SLICE = "/sys/fs/cgroup/user.slice/user-0.slice"
BUILDS_SLICE = "/sys/fs/cgroup/builds.slice"
_MB = 1024 * 1024
_GB = 1024 * _MB

# Signatures of processes heavy enough that two at once is the problem.
# Matched against the full cmdline. Ordered most-specific first; first hit wins.
_HEAVY = [
    (re.compile(r"kotlin-compiler-embeddable|org\.jetbrains\.kotlin\.daemon"), "kotlin-daemon"),
    (re.compile(r"GradleDaemon|/\.gradle/(caches|daemon|wrapper)"), "gradle"),
    (re.compile(r"dart2wasm|dart\s+compile\s+wasm"), "dart2wasm"),
    (re.compile(r"dart\s+compile\s+js|dart2js"), "dart2js"),
    (re.compile(r"frontend_server|flutter_tools\.snapshot|/flutter/bin/flutter"), "flutter"),
    (re.compile(r"buildkitd|docker-buildx|docker\s+build"), "docker-build"),
    (re.compile(r"\bcargo\b.*\b(build|test)\b|\brustc\b"), "cargo"),
    (re.compile(r"\b(webpack|vite|esbuild|rollup|next-build)\b"), "bundler"),
    (re.compile(r"\bninja\b|\bmake\b\s+-j"), "native-build"),
]

# A process must also be non-trivial in size before it counts. A `grep gradle` should
# never look like a Gradle build; a 2 MB shim wrapping the real compiler should not
# either. 200 MB RSS is comfortably above any wrapper and below any real build daemon.
_MIN_RSS_BYTES = 200 * _MB


@dataclass
class HeavyProc:
    pid: int
    kind: str
    rss: int
    etime: str
    session: str | None
    cmdline: str

    def as_dict(self) -> dict:
        return {
            "pid": self.pid, "kind": self.kind, "rss": self.rss,
            "etime": self.etime, "session": self.session,
            "cmdline": self.cmdline[:160],
        }


@dataclass
class Headroom:
    slice_path: str
    current: int | None = None
    high: int | None = None
    maximum: int | None = None
    swap_current: int | None = None
    swap_max: int | None = None
    file_cache: int | None = None
    anon: int | None = None
    psi_full_avg10: float | None = None
    psi_full_avg300: float | None = None
    swap_fail: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def free_to_brake(self) -> int | None:
        """Bytes of headroom before the memory.high brake engages. None if no brake.

        Reclaimable page cache charged to the slice counts as free, not as
        committed usage. File pages are evicted under pressure long before the
        slice throttles, so a warm cache must not read as "no room" - counting
        it starved builds for hours behind an otherwise idle box (the 2026-08-21
        stall: high-current sat ~2.6G under the 3G floor while ~3G of that
        "usage" was just cache the kernel drops on demand). This is the cgroup
        analogue of trusting MemAvailable over MemFree.
        """
        if self.high is None or self.current is None:
            return None
        reclaimable = self.file_cache or 0
        committed = self.current - reclaimable
        return self.high - committed

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["free_to_brake"] = self.free_to_brake
        return d


def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _num(path: str) -> int | None:
    raw = _read(path)
    if raw is None:
        return None
    raw = raw.strip()
    if raw in ("", "max"):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _keyed(path: str) -> dict[str, int]:
    raw = _read(path) or ""
    out: dict[str, int] = {}
    for line in raw.split("\n"):
        parts = line.split()
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return out


def headroom(slice_path: str = DEFAULT_SLICE) -> Headroom:
    h = Headroom(slice_path=slice_path)
    if not os.path.exists(f"{slice_path}/memory.current"):
        h.notes.append("slice not present or no cgroup v2 memory controller")
        return h
    h.current = _num(f"{slice_path}/memory.current")
    h.high = _num(f"{slice_path}/memory.high")
    h.maximum = _num(f"{slice_path}/memory.max")
    h.swap_current = _num(f"{slice_path}/memory.swap.current")
    h.swap_max = _num(f"{slice_path}/memory.swap.max")
    stat = _keyed(f"{slice_path}/memory.stat")
    h.file_cache = stat.get("file")
    h.anon = stat.get("anon")
    h.swap_fail = _keyed(f"{slice_path}/memory.swap.events").get("fail", 0)
    raw = _read(f"{slice_path}/memory.pressure") or ""
    for line in raw.split("\n"):
        parts = line.split()
        if parts and parts[0] == "full":
            for p in parts[1:]:
                k, _, v = p.partition("=")
                try:
                    if k == "avg10":
                        h.psi_full_avg10 = float(v)
                    elif k == "avg300":
                        h.psi_full_avg300 = float(v)
                except ValueError:
                    pass
    return h


def _tmux_pane_map(socket: str = "work") -> dict[int, str]:
    """pane pid -> tmux session name. Empty dict if tmux is unreachable.

    Attribution is best-effort by design: a build that cannot be traced to a session
    still counts as a build. Never let this fail the guard.
    """
    try:
        p = subprocess.run(
            ["tmux", "-L", socket, "list-panes", "-a", "-F", "#{pane_pid} #{session_name}"],
            capture_output=True, text=True, timeout=8,
        )
        if p.returncode != 0:
            return {}
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out: dict[int, str] = {}
    for line in p.stdout.split("\n"):
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            out[int(parts[0])] = parts[1].strip()
    return out


def _ppid_of(pid: int) -> int | None:
    raw = _read(f"/proc/{pid}/stat")
    if not raw:
        return None
    # comm can contain spaces and parens; everything after the LAST ')' is safe to split.
    tail = raw.rpartition(")")[2].split()
    if len(tail) < 2:
        return None
    try:
        return int(tail[1])
    except ValueError:
        return None


def _session_of(pid: int, panes: dict[int, str]) -> str | None:
    """Walk up the ppid chain until we hit a known tmux pane pid."""
    seen = 0
    cur: int | None = pid
    while cur and cur > 1 and seen < 40:  # bounded: never loop on a cycle
        if cur in panes:
            return panes[cur]
        cur = _ppid_of(cur)
        seen += 1
    return None


def _rss_of(pid: int) -> int:
    for line in (_read(f"/proc/{pid}/status") or "").split("\n"):
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return 0


def _etime_of(pid: int) -> str:
    try:
        p = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
        return p.stdout.strip() or "?"
    except (OSError, subprocess.TimeoutExpired):
        return "?"


def heavy_processes(min_rss: int = _MIN_RSS_BYTES) -> list[HeavyProc]:
    """Every running process that looks like a heavy build, guarded or not."""
    panes = _tmux_pane_map()
    me = os.getpid()
    found: list[HeavyProc] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == me:
            continue
        raw = _read(f"/proc/{pid}/cmdline")
        if not raw:
            continue
        cmdline = raw.replace("\0", " ").strip()
        if not cmdline:
            continue
        kind = None
        for pattern, label in _HEAVY:
            if pattern.search(cmdline):
                kind = label
                break
        if kind is None:
            continue
        rss = _rss_of(pid)
        if rss < min_rss:
            continue
        found.append(HeavyProc(
            pid=pid, kind=kind, rss=rss, etime=_etime_of(pid),
            session=_session_of(pid, panes), cmdline=cmdline,
        ))
    found.sort(key=lambda p: -p.rss)
    return found


def human(n: int | None) -> str:
    if n is None:
        return "max"
    val = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(val) < 1024.0 or unit == "T":
            return f"{val:.0f}{unit}" if unit == "B" else f"{val:.2f}{unit}"
        val /= 1024.0
    return f"{val:.2f}T"
