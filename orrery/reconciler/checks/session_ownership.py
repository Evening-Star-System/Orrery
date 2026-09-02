"""session-ownership: a unit that declares it owns a process tree actually owns it.

A systemd unit can report `active` while owning nothing. A daemonising server detaches
from its starter, so whichever process reached the socket FIRST is the one whose cgroup it
lands in. tmux is the canonical case: if an operator ran `tmux -L <socket>` from an ssh
login before the unit did, the unit's ExecStart succeeds against the already-running
server, and with `Type=oneshot` plus `RemainAfterExit=yes` the unit reports active forever
over a cgroup with zero processes in it. The real process tree lives in a `session-N.scope`
under `user.slice`.

Two things break, and neither is visible from `systemctl status`:

  1. Any cgroup policy on that unit is silently a NO-OP. MemoryMax, MemorySwapMax, IO
     limits: all attached to an empty cgroup. That is worse than having no limit, because
     the limit is written down, believed, and does nothing.
  2. The process tree inherits the LIFETIME of whatever scope does own it. An ssh login
     scope is reaped when logind closes it, taking every session in it.

Read-only and bounded. Reads `cgroup.procs` for the declared unit and `/proc/<pid>/comm`
for the pids it names; executes nothing and writes nothing, so it works unchanged against
LocalBox or SshBox.
"""

from __future__ import annotations

from ..box import Box
from ..model import Finding, Severity

ID = "session-ownership"
TITLE = "units own the process trees they declare"

_PID_SCAN_CAP = 512  # bound the /proc reads; a huge cgroup must not stall a run
_DEFAULT_SLICE = "system.slice"
_CGROUP_ROOT = "/sys/fs/cgroup"


class SessionOwnershipCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"units"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        units = options.get("units", [])
        if not units:
            return [Finding(ID, Severity.WARN, ID, "no units declared")]
        return [self._check_one(entry, box) for entry in units]

    def _check_one(self, entry: dict, box: Box) -> Finding:
        unit = entry.get("unit")
        name = entry.get("name") or unit or "<unit>"
        if not unit:
            return Finding(ID, Severity.WARN, name, "unit entry missing 'unit'")

        slice_name = entry.get("slice", _DEFAULT_SLICE)
        expect = entry.get("expect_process")
        min_procs = entry.get("min_procs", 1)
        procs_path = f"{_CGROUP_ROOT}/{slice_name}/{unit}/cgroup.procs"

        if not box.exists(procs_path):
            # No cgroup at all: the unit is not running. That is a legitimate stopped
            # state, not a lie about ownership, so it is DRIFT (declared and observed
            # disagree) rather than FAIL.
            return Finding(
                ID, Severity.DRIFT, name, "unit has no cgroup; it is not running",
                expected=f"{unit} active and owning processes", observed="no cgroup",
            )

        raw = box.read_text(procs_path)
        if raw is None:
            return Finding(ID, Severity.WARN, name, f"cannot read {procs_path}")

        pids = [ln.strip() for ln in raw.split("\n") if ln.strip().isdigit()]
        if len(pids) < min_procs:
            # THE BUG THIS CHECK EXISTS FOR: green unit, empty cgroup.
            return Finding(
                ID, Severity.FAIL, name,
                "unit owns no processes; any cgroup limit on it is a no-op",
                expected=f">= {min_procs} process(es) in {slice_name}/{unit}",
                observed=f"{len(pids)}",
            )

        if not expect:
            return Finding(ID, Severity.OK, name, f"owns {len(pids)} process(es)")

        # comm is the kernel's 15-char name and tmux reports "tmux: server", so match on
        # substring. Exact matching here would report a false DRIFT on a correct box.
        found = False
        for pid in pids[:_PID_SCAN_CAP]:
            comm = box.read_text(f"/proc/{pid}/comm")
            if comm and expect in comm.strip():
                found = True
                break
        if not found:
            return Finding(
                ID, Severity.DRIFT, name,
                "unit owns processes, but not the one it is supposed to own",
                expected=f"a process matching '{expect}'",
                observed=f"{len(pids)} process(es), none matching",
            )
        return Finding(
            ID, Severity.OK, name, f"owns '{expect}' and {len(pids)} process(es)"
        )
