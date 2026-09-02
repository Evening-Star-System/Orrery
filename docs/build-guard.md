# Build guard

One heavy build at a time, each inside a ceiling it can actually hit.

## The incident this exists for

work-box, 2026-08-20. Two Widget builds ran at once, Android (Gradle 3.49G + Kotlin
daemon 1.17G) and web (dart2js + dart2wasm, ~0.94G), on top of eight interactive
editor and agent sessions holding ~2.5G. Total ≈ 8.1G against a `MemoryHigh=8G` brake on the
slice they all shared.

For 1h42m the box did essentially no work:

| Signal | Value |
| --- | --- |
| CPU | 92–94% **system**, ~1% user |
| Block reads | ~2 GB/s, sustained |
| `memory.current` | 8.59G, pinned exactly at `memory.high` |
| `memory.stat file` | **1.8 MB**: the file cache, fully reclaimed |
| `workingset_refault_file` | 12,357,256,771 |
| `pgmajfault` | 427,594,089 |
| PSI memory `full avg300` | 73.56% |
| `memory.events high` | 193,110,942 |
| **`oom_kill`** | **0** |

## Why the existing protections could not end it

Three limits, each added after a real incident, each correct alone:

| Limit | Added | For |
| --- | --- | --- |
| `MemoryMax=10G` | 2026-07-16 | bound the blast radius of a runaway |
| `MemoryHigh=8G` | 2026-08-14 | throttle instead of OOM-killing legitimate builds |
| `MemorySwapMax=1G` | 2026-08-18 | stop swap thrash, and let the OOM killer reach the wall |

Composed, they produce a **stable non-terminating stall**:

1. The brake holds the slice at 8G. Holding it there requires reclaim.
2. Swap is already at its 1G ceiling, `memory.swap.events: fail` reached 57,070,433,
   so the only reclaimable thing left is the file cache.
3. The file cache is evicted to ~nothing, and every process re-reads its own binaries,
   JARs, and mappings from disk on each touch. Hence 2 GB/s and 92% system CPU.
4. Because the brake **succeeds**, the slice never reaches `MemoryMax`. The in-cgroup
   OOM killer, the thing the swap cap was added to enable, can never fire.

Nothing dies, so nothing recovers. `oom_kill 0` reads as healthy on every dashboard.

> A limit set that can only be escaped by an operator noticing is not a protection.
> It is a slower outage.

## What this ships

**`heavy-build`**: a CLI in front of any build command.

```
heavy-build status                    # what is running, and is there room
heavy-build run -- <cmd...>           # wait your turn, then run capped
```

`run` does three things a bare build does not:

1. **Waits for any other heavy build**, guarded or not. Guarded builds are found via
   the lock; unguarded ones via their process signature, because the rule only helps
   if it survives someone forgetting it.
2. **Waits for headroom** on the shared slice, so a build does not start into an
   already-throttled box and deepen the hole.
3. **Runs inside a transient systemd scope under `builds.slice`**, which lives in
   `system.slice` and has its own `MemoryMax`. A build that overruns dies alone and
   immediately instead of stalling every session beside it.

**`builds.slice`**: `MemoryMax=6G`, `MemorySwapMax=512M`, `CPUWeight=20`, and
**deliberately no `MemoryHigh`**. That absence is the lesson, not an oversight: for
interactive work a brake is right, because going slow beats being killed. For a build
the opposite holds: a build that does not fit should die immediately and say so,
because a build that merely goes slow is indistinguishable from a hung one and costs
hours before anyone looks.

**`memory-headroom`**: a reconciler check that reports the *conjunction* as `FAIL`:
a brake below an unreachable wall, plus swap at its ceiling, plus a collapsed file
cache. Any one alone is ordinary; together they mean the box cannot get out on its own.

**`orrery-memory-watch`**: a 2-minute timer pushing that verdict to Uptime Kuma as a
**push** monitor. Push, not pull, because a pull monitor cannot tell "the box is fine"
from "the box is too wedged to answer", and the second is the case that matters.

## Two bugs found only by running it

Both looked obviously correct and did nothing in production. Both now have regression
tests, and they are the reason this document exists rather than a changelog line.

- **OOM detection compared against the wrong numbers.** A scope OOM kills `systemd-run`
  too, so `subprocess` reports `-9`; a shell renders `sys.exit(-9)` as 247. The check
  tested for `137`/`247`, the numbers a *shell* prints, so the explanatory message
  never fired once. Compare against Python's convention, not the shell's.
- **Session attribution queried the wrong tmux socket.** work-box's server runs on
  `-L work`; the default socket found nothing, so every holder recorded `session ?`:
  the single field the guard exists to display.

## Operating it

```
# before starting anything heavy
heavy-build status

# start a build (waits if the box is busy; --wait-timeout 0 = wait forever)
heavy-build run --label widget-web -- ./build-web.sh

# give up rather than queue
heavy-build run --wait-timeout 300 --label x -- make all    # exit 75 = try later
```

Exit codes: the build's own, except `75` (`EX_TEMPFAIL`, could not get a turn) and
`128+N` for signal deaths, with `137` meaning it was OOM-killed inside its own scope.

Cap JVM heaps in the project too. A JVM sizes its heap against **host** RAM and never
sees the cgroup ceiling it lives under, and `org.gradle.jvmargs` does **not** reach the
Kotlin daemon. That needs `kotlin.daemon.jvmargs` separately.
