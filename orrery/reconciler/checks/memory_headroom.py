"""memory-headroom: a slice can still reclaim, and its wall is still reachable.

Memory limits are usually reviewed one at a time, "is the cap set?", "is swap bounded?",
and each answer can be yes while the SET of them composes into a state no single limit
describes. This check reads them together, because the failure that matters is a
composition failure.

THE BUG THIS CHECK EXISTS FOR (work-box, 2026-08-20, third occurrence):

  MemoryHigh=8G   throttle + reclaim brake      (added 08-14, to avoid OOM kills)
  MemoryMax=10G   in-cgroup OOM wall            (added 07-16, to bound blast radius)
  MemorySwapMax=1G  swap ceiling                (added 08-18, to stop swap thrash)

Each was correct in isolation and each did what its own note claimed. Composed, they
produce a STABLE NON-TERMINATING STALL:

  * The brake holds the slice at 8G. To hold it there the kernel must reclaim, and with
    swap already at its 1G ceiling (`memory.swap.events: fail` climbing into the tens of
    millions) the ONLY reclaimable thing left is the file cache.
  * So the file cache is evicted to near zero, 1.8 MB observed against 7.8 GB of anon,
    and every process re-reads its own binaries, JARs, and heap-adjacent mappings from
    disk on each touch. ~2 GB/s of block reads, 92% system CPU, ~1% user.
  * Because the brake succeeds at holding 8G, the slice NEVER reaches MemoryMax=10G. The
    in-cgroup OOM killer, the thing 08-18 capped swap specifically to enable, can
    therefore never fire. `oom_kill` stayed 0 through 1h42m of total stall.

Nothing dies, so nothing recovers. A limit set that can only be escaped by an operator
noticing is not a protection; it is a slower outage. `oom_kill 0` reads as "healthy" on
every dashboard, which is precisely why this needed a check rather than a graph.

The signal is the CONJUNCTION, and that is what `_unreachable_wall` reports as FAIL:
a brake below a wall, plus swap at its ceiling, plus a collapsed file cache. Any one
alone is normal operation; together they mean the box cannot get out on its own.

Read-only and bounded: every input is a small pseudo-file under the cgroup and /proc,
read through Box, so this works unchanged against LocalBox or SshBox. It executes
nothing. Unparseable input degrades to WARN, never an exception: a reconciler that
dies on a surprising cgroup is useless against exactly the drifted box it exists for.
"""

from __future__ import annotations

from ..box import Box
from ..model import Finding, Severity

ID = "memory-headroom"
TITLE = "a slice can still reclaim, and its wall is reachable"

_MB = 1024 * 1024

# Defaults, overridable per slice in the profile.
_DEF_PSI_FULL_AVG300_MAX = 20.0  # % of wall-clock the whole cgroup is stalled
_DEF_MIN_FILE_CACHE_MB = 128     # below this the slice is re-reading from disk
_DEF_SWAP_SATURATION = 0.95      # fraction of swap.max that counts as "at the ceiling"


def _num(box: Box, path: str) -> int | None:
    """Read a single-value cgroup file. 'max' means no limit -> None."""
    raw = box.read_text(path)
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "max" or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _keyed(box: Box, path: str) -> dict[str, int] | None:
    """Parse a 'key value' cgroup file (memory.stat, memory.events)."""
    raw = box.read_text(path)
    if raw is None:
        return None
    out: dict[str, int] = {}
    for line in raw.split("\n"):
        parts = line.split()
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return out


def _pressure(box: Box, path: str) -> dict[str, dict[str, float]] | None:
    """Parse PSI: lines of 'some avg10=.. avg60=.. avg300=.. total=..'."""
    raw = box.read_text(path)
    if raw is None:
        return None
    out: dict[str, dict[str, float]] = {}
    for line in raw.split("\n"):
        parts = line.split()
        if not parts:
            continue
        kind, fields = parts[0], {}
        for p in parts[1:]:
            if "=" not in p:
                continue
            k, _, v = p.partition("=")
            try:
                fields[k] = float(v)
            except ValueError:
                continue
        if fields:
            out[kind] = fields
    return out or None


class MemoryHeadroomCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"slices"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        slices = options.get("slices", [])
        if not slices:
            return [Finding(ID, Severity.WARN, ID, "no slices declared")]
        return [self._check_one(entry, box) for entry in slices]

    def _check_one(self, entry: dict, box: Box) -> Finding:
        path = entry.get("path")
        name = entry.get("name") or path or "<slice>"
        if not path:
            return Finding(ID, Severity.WARN, name, "slice entry missing 'path'")

        if not box.exists(f"{path}/memory.current"):
            # Not a cgroup v2 memory-enabled path. Declared but absent is DRIFT, not
            # FAIL: the slice may legitimately not be running.
            return Finding(
                ID, Severity.DRIFT, name, "slice has no memory.current; not present",
                expected=f"cgroup v2 memory controller at {path}", observed="absent",
            )

        current = _num(box, f"{path}/memory.current")
        high = _num(box, f"{path}/memory.high")
        maximum = _num(box, f"{path}/memory.max")
        swap_cur = _num(box, f"{path}/memory.swap.current")
        swap_max = _num(box, f"{path}/memory.swap.max")
        stat = _keyed(box, f"{path}/memory.stat") or {}
        swap_ev = _keyed(box, f"{path}/memory.swap.events") or {}
        psi = _pressure(box, f"{path}/memory.pressure")

        if current is None:
            return Finding(ID, Severity.WARN, name, f"cannot read {path}/memory.current")

        file_cache = stat.get("file")
        anon = stat.get("anon")
        swap_fail = swap_ev.get("fail", 0)
        psi_full_300 = None
        if psi and "full" in psi:
            psi_full_300 = psi["full"].get("avg300")

        psi_ceiling = float(entry.get("psi_full_avg300_max", _DEF_PSI_FULL_AVG300_MAX))
        min_cache = int(entry.get("min_file_cache_mb", _DEF_MIN_FILE_CACHE_MB)) * _MB
        sat = float(entry.get("swap_saturation", _DEF_SWAP_SATURATION))

        cache_collapsed = file_cache is not None and file_cache < min_cache
        swap_pinned = (
            swap_cur is not None and swap_max is not None and swap_cur >= swap_max * sat
        )
        brake_engaged = high is not None and current >= high
        wall_unreachable = high is not None and maximum is not None and high < maximum

        # ---- FAIL: the composition that cannot self-recover -------------------------
        if wall_unreachable and swap_pinned and cache_collapsed:
            return Finding(
                ID, Severity.FAIL, name,
                "brake below an unreachable wall, swap at ceiling, file cache "
                "collapsed: the slice can only thrash, and the in-cgroup OOM killer "
                "can never fire to end it",
                expected=(
                    f"reclaimable headroom: swap below {_h(swap_max)} "
                    f"or file cache above {_h(min_cache)}"
                ),
                observed=(
                    f"current={_h(current)} high={_h(high)} max={_h(maximum)} "
                    f"swap={_h(swap_cur)}/{_h(swap_max)} file={_h(file_cache)} "
                    f"anon={_h(anon)} swap_fail={swap_fail}"
                ),
            )

        # ---- FAIL: actively thrashing, whatever the limit topology ------------------
        if cache_collapsed and psi_full_300 is not None and psi_full_300 > psi_ceiling:
            return Finding(
                ID, Severity.FAIL, name,
                "file cache reclaimed to nothing while the slice is stalled: it is "
                "re-reading from disk instead of doing work",
                expected=f"file cache > {_h(min_cache)}, PSI full avg300 <= {psi_ceiling}",
                observed=f"file={_h(file_cache)} PSI full avg300={psi_full_300}",
            )

        # ---- DRIFT: degraded but still reclaimable ---------------------------------
        if brake_engaged:
            return Finding(
                ID, Severity.DRIFT, name,
                "slice is pinned against its MemoryHigh brake; work in it is throttled",
                expected=f"current below high ({_h(high)})",
                observed=(
                    f"anon={_h(anon)} current={_h(current)} swap_fail={swap_fail}"
                ),
            )

        if swap_pinned:
            return Finding(
                ID, Severity.DRIFT, name,
                "swap is at its ceiling; the next reclaim has only the file cache left",
                expected=f"swap below {_h(swap_max)}",
                observed=f"swap={_h(swap_cur)} fail={swap_fail}",
            )

        if psi_full_300 is not None and psi_full_300 > psi_ceiling:
            return Finding(
                ID, Severity.DRIFT, name,
                "slice is stalling on memory",
                expected=f"PSI full avg300 <= {psi_ceiling}",
                observed=f"PSI full avg300={psi_full_300}",
            )

        # Judge headroom on ANON, not on memory.current. memory.current includes
        # reclaimable page cache, so it cannot tell "9.4G, nearly all evictable cache"
        # from "9.4G of anon about to hit the wall" - the two print identically and only
        # the second is fatal. On 08-24 this line read "[OK] 9.47G in use, 29.61M below
        # the brake" when anon was only ~1.9G. The inverse is worse: through the 08-29
        # stall the same figure would have held STEADY while the cache collapsed and anon
        # filled the cgroup, so the readout would have looked unchanged as the box died.
        # anon is the part reclaim cannot hand back, so anon is what forecasts the wall.
        # memory.current is still reported, because the brake itself acts on it.
        basis = current if anon is None else anon
        headroom = (
            "" if high is None
            else f", {_h(high - basis)} of anon headroom to the brake"
        )
        return Finding(
            ID, Severity.OK, name,
            f"anon {_h(anon)} of {_h(current)} charged{headroom}; "
            f"file cache {_h(file_cache)}",
        )


def _h(n: int | None) -> str:
    """Human-readable bytes. None (= no limit set) prints as 'max'."""
    if n is None:
        return "max"
    step = 1024.0
    val = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if abs(val) < step or unit == "T":
            return f"{val:.0f}{unit}" if unit == "B" else f"{val:.2f}{unit}"
        val /= step
    return f"{val:.2f}T"
