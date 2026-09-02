# Project context isolation

The problem this solves: a single shared operator digest loaded into every session, so work from
several open projects intermingles and each project sees the others' state. Orrery resolves the right
context per working directory instead.

## The model

- **OPS scope** (cwd outside the projects root, for example the operator home): load the fleet/ops
  digest. This is the shared, cross-cutting operational state.
- **PROJECT scope** (cwd under `<projects_root>/<bucket>/<project>`): load ONLY that project's own
  state. Never another project's, never the ops digest.
- **Ethos and standing rules** are injected separately by the standing-rules hook on every prompt, so
  the context resolver stays focused purely on scoped state.

Each project's state lives in the project, in priority order:
1. a curated per-project digest at `<project>/.dev/DIGEST.md` (the per-project equivalent of the ops
   digest: a short, hand-maintained "current state" the operator keeps fresh), else
2. the newest `CHANGES.md` entry plus open `TASKS.md` items, else
3. a graceful note telling you to create the digest.

## Using it

```
python -m orrery.context --config <context-config.toml> --cwd <dir> [--json]
```

Prints the context block for that directory. The config (local, not committed, it carries real
paths) declares `projects_root`, `ops_digest`, an optional `global_baseline`, and
`project_digest_relpath` (default `.dev/DIGEST.md`).

## Per-project digest format

`.dev/DIGEST.md` is short and operator-curated, the same discipline as the ops digest but scoped to
one project. A workable shape:

```
# <project> live state

## Now
<the current arc: what is being built, the one or two things that matter right now>

## Next
<the immediate next steps>

## Watch
<gotchas, gated items, anything not to break>
```

Keep it small. It is a handoff header, not an archive; deep history stays in CHANGES.md and the
project's own notes.

## Adopting it (migration)

1. For each active project, create `.dev/DIGEST.md` and seed it with that project's current state
   (moved out of any shared digest into its own home).
2. Point the session hook at `orrery.context` so new sessions load the resolved, scoped context.
3. Trim the shared ops digest back to fleet/ops state, now that per-project state has its own home.

Order matters: seed the per-project digests BEFORE switching the hook, or project sessions open with
no context until their digest exists.
