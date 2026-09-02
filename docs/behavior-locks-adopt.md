# Adopting behavior locks in a repo

A behavior lock pins a shipped behavior as a floor: once a behavior is verified working, you
capture it, and the gate refuses any future build that changes it. This is how a fixed bug
stays fixed instead of walking back in through a path nobody re-tested. Three moves: declare,
capture, gate.

The check is implementation-blind. It reads only the value your command prints at an observable
boundary (an export envelope, an API response, a rendered count), never how the code produced it.
That blindness is why one lock covers a fixed path and its untested twin.

## 1. Declare and capture (one command)

From the repo root, once the behavior is green:

    ess-orrery lock add export-envelope-no-orphan-blobs \
      --command "scripts/probe-orphan-blobs.sh" \
      --why "Fixed on the web path (92904af); the native twin regressed the same bug unseen."

This declares the lock and captures its golden from a clean run, together, and writes both to
`orrery-locks.toml`. Commit that file. If the probe is not green, no golden is written and the
command exits non-zero, so you never pin a broken behavior.

The `--command` must print ONE canonical line: the value that must not change (a count, a hash, a
normalized envelope). Keep it deterministic. It runs from the repo root under a stripped
environment and a hard timeout; it is the authoring run of a command you already trust, not a
sandbox, so heavier isolation belongs inside the command.

## 1b. Floors and ceilings (allow the positive, block the negative)

Exact match is right when the behavior is a fixed contract (an envelope, an API shape). When the
behavior is a MEASURABLE number that should be allowed to improve, use a directional `compare` so an
improvement passes without a re-lock and only a regression fails:

- `compare = ">="` is a FLOOR: the value may rise freely; falling below the golden fails. Use it where
  more is better (test coverage, a passing count).
- `compare = "<="` is a CEILING: the value may fall freely; rising above the golden fails. Use it where
  less is better (bundle size, latency, a defect count).
- `compare = "eq"` (the default) is exact: any change is a regression or a deliberate re-lock.

The probe must print a bare number for a directional lock (a non-number is a WARN, never a false pass).
To LOCK IN an improvement, run `lock capture` after it: on a floor that raises the golden (ratchets the
bar up), so a later drop back to the old level now fails too. The gate allows the improvement; the
deliberate capture is how you decide to hold the new, better level.

## 2. Re-capturing on purpose

When you intend to change a locked behavior, make the code change, verify it, then:

    ess-orrery lock capture export-envelope-no-orphan-blobs

This rewrites the golden from the new green run. A re-lock is a reviewed diff to `orrery-locks.toml`
in the same PR as the behavior change, which is exactly the audit trail you want.

## 3. The gate (per-project CI)

The gate runs in the project's own CI (the consumer runs its probes; Orrery adjudicates). One
CI-agnostic script does both steps:

- Copy `templates/orrery-locks-gate.sh` (from this repo) into your project as
  `scripts/orrery-locks-gate.sh`. It runs `ess-orrery lock probe` (produces the observed values)
  then `ess-orrery reconcile ... --check behavior-lock` (adjudicates observed against the goldens),
  and exits non-zero on a regression, which fails the build.
- Call `sh scripts/orrery-locks-gate.sh` as a CI step.

For a GitHub-hosted project, copy `templates/behavior-locks.yml` to
`.github/workflows/behavior-locks.yml`; it installs `ess-orrery` and runs the gate script. For a
non-GitHub CI (Codeberg, a forge runner), do not copy the workflow: just add the one script call as
a step. The gate logic is in the script, so every CI shares it.

An empty `orrery-locks.toml` (no active `[[locks]]`) is nothing to check, so the gate is green until
you declare your first lock. New projects ship this stub (`templates/orrery-locks.toml`) by default.

### Install dependency (current)

The gate needs `ess-orrery` installable in CI. It is not on PyPI yet (that publish is gated), so
`pip install ess-orrery` does not resolve today. Until it is published, install it from a source
your CI can reach (a pinned wheel or an authenticated install) or hold the gate step. The manifest,
`lock add`, `lock capture`, and `lock probe` all work locally now regardless.

## What a lock is not

It is not a test framework, a coverage tool, or a replacement for your CI. It is a thin floor over a
handful of load-bearing behaviors that were bug-fixed or hard-won and must never come back. Spend it
on those, not on everything.
