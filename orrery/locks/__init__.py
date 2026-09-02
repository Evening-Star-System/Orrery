"""Behavior-lock authoring: the two moves the reconciler check cannot do itself.

The `behavior-lock` reconciler check ADJUDICATES: it reads a consumer repo's
`orrery-locks.toml` (the golden) and `orrery-locks.results.json` (the observed value a
consumer's pipeline produced) and owns the verdict. It never records a golden and never
runs a probe in the gate, by ratified design: the judge stays small, trusted, and
hermetic.

This package is the authoring side that lives next to the check, not inside it:

  * `capture` runs a lock's command once, on a verified-working tree, and writes the
    canonical value it prints as that lock's `golden`. This is the "it works, lock it
    in" move. It is deliberate and developer-invoked, never a hook and never the gate,
    so a golden is only ever captured from a green run on purpose.
  * `probe` runs every lock's command and writes `orrery-locks.results.json` in the
    shape the check already reads, so a project's gate is one command, not a hand-rolled
    runner.

Both share ONE bounded runner (`runner.run_probe`), the same run the check's dev-only
local mode uses, so there is a single place that decides how a consumer command is run.
Writing a golden is a surgical, stdlib-only edit of the manifest (`manifest.set_golden`);
the engines carry zero runtime dependencies, so there is no TOML-writer library to lean
on, and preserving the file's comments and ordering matters for a file humans read.
"""
