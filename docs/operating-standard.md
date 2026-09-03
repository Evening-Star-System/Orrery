# The operating standard: one way to build, across every project

This is one small, consistent way to run every project in a fleet, whatever its language and whatever
CI host it uses. It is meant to be learned once and applied everywhere. Every step here runs and reads
by hand, with no AI in the loop; automation may drive the same steps, but it never gets a softer path
than a person, and a person is always in control.

## The four beats

Every project, any stack, runs the same loop:

1. **Declare** what the project agrees to: a small profile that adopts a shared set of rules. Conduct
   rules are held by people and process; the one machine-checked rule is the behavior lock.
2. **Prove** the behavior still holds: run the project's own checks. That means lint, then tests, then
   any project-specific checks, then the behavior-lock gate. Native tests stay the deep source of truth
   for a project's behavior; the lock adds a small, uniform guardrail on top.
3. **Gate** hard: CI runs the prove step and BLOCKS the merge or deploy on any failure. A red guardrail
   stops the change. There is no "warn and keep going" for a declared rule.
4. **Roll up**: one command reconciles every project into a single view, so the whole fleet's guardrail
   status is legible at a glance. The roll-up is a MONITOR: it reflects what each project's CI last
   recorded, so a stale or hand-edited result is only ever as trustworthy as that project's CI. The hard
   gate that a change must pass is beat 3, in the project's own CI, which re-runs the checks every time.

The loop is the same everywhere (the trunk). Only the commands differ by stack (the limbs), and those
live in one small table so adding a language is one entry, not a rewrite.

## Run it by hand (no AI required)

- **Detect a project's stack**

      ess-orrery standard detect .

- **Render its CI** for either host (the same four beats, filled from the stack table):

      ess-orrery standard render-ci . --host github
      ess-orrery standard render-ci . --host woodpecker

- **Lock a hard-won behavior** (declare it and capture its golden in one step):

      ess-orrery lock add <id> --command "<one line that prints a canonical value>" --why "<why>"

- **Run the gate** (probe every lock, compare to its golden, exit non-zero on any regression):

      ess-orrery lock gate

- **Reconcile one project, or a whole fleet**:

      ess-orrery reconcile --profile .dev/orrery.profile.toml
      ess-orrery reconcile --profiles "/path/to/projects/*/*/.dev/orrery.profile.toml"

Read the output; it is written to be understood by a person, not just parsed by a machine.

## Hard guards, not suggestions

A guardrail either blocks or it is not a guardrail. The gate returns a non-zero exit on any failed
beat, and both CI hosts stop on the first failure. The lock gate has no skip flag and no separate path
for an automated caller; the verdict depends only on whether the locked behavior held. If the gate
cannot even run, it fails rather than passing silently: a gate that cannot run is a failed gate, not a
skipped one.

The only way past a red lock is a deliberate, recorded human act: re-capture the golden in the same
change that changes the behavior (a loud re-lock, reviewed like any other change), or record an
explicit exception in the project's own layer. Nothing bypasses a guard quietly.

## Getting better without regressing

A lock can hold an exact value, or a floor, or a ceiling:

- exact (`eq`): any change is a regression or a deliberate re-lock.
- floor (`>=`): the value may rise freely; falling below the golden fails. Use it for things that should
  only improve (test coverage, a count of passing checks).
- ceiling (`<=`): the value may fall freely; rising above fails. Use it for things that should only
  shrink (bundle size, latency).

To raise a floor after a genuine improvement, re-run `lock add`/capture at the better value. This is how
the standard ratchets forward: it can improve, and it is structurally prevented from sliding back.

## Human first

Everything above runs from a terminal with no AI involved. A person can detect the stack, render the
CI, capture a lock, run the gate, and read the fleet roll-up, all by hand. The human operator owns the
decisions that matter: re-locks, exceptions, and any go-live. Automation proposes; the human disposes.

## Adopting the standard

- A new project is scaffolded onto the standard from the start: it is born with a profile, a lock
  manifest, the gate script, and the rendered CI for its stack.
- An existing project is folded in without losing what it already has: its own tests and checks stay,
  and the canonical CI runs them plus the lock gate. An existing, hand-tuned CI is never overwritten.
- A starter set of conduct rules a team can adopt and edit lives in `rulesets/starter.ruleset.toml`.

Keep the fewest moving parts that still protect the behavior. Native tests are the deep truth; the lock
is the uniform guardrail and the thing that makes every project legible to the fleet. Do not lock the
same behavior twice.
