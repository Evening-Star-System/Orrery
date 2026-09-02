# The profile format

A profile is the declared shape of one box: which checks run against it, and how each
is configured. It is per-installation data, so a real profile is kept local (gitignored)
and never committed; the engine and its checks do not change per install. The annotated
reference profile is `profiles/example.toml`, which documents every check's options in
place. This page describes the overall shape and how to validate one.

## Shape

```toml
schema = 1                 # the profile schema version (integer)
box = "work-box"           # required: a name for this box

[[checks]]                 # one table per check, in any order
id = "org-map"             # required: must be a check the registry knows
# ...check-specific options follow, documented per check in profiles/example.toml
```

- `box` is required and must be a non-empty string.
- `checks` is an array of tables. Each entry needs an `id` that names a registered
  check; everything else in the table is that check's own options.
- A check with no options is allowed (some checks need none); it runs with its defaults.

The set of known check ids comes from the registry. As of this writing there are nine:
`org-map`, `declared-presence`, `fleet-reach`, `secret-edges`, `floors`,
`managed-settings`, `session-ownership`, `memory-headroom`, and `vault-capability`.
Adding a check is one registry line, after which it is available to every profile.

## Validate before you rely on it

```
ess-orrery profile validate PATH [--json]
```

The failures that hurt are quiet: a check id with a typo runs nothing and reports
nothing, so a box looks clean because it was never actually checked. `validate` reads the
profile and reports its shape problems as findings of their own, without running any check
against the box:

- invalid TOML, or an unreadable file, is a single error;
- a missing or blank `box` is an error;
- a check id the registry does not know is an error, with a suggested correction;
- the same check id declared more than once is a warning;
- a check with no options is noted (info), in case that was an oversight.

Exit code is 0 when the profile has no errors, 2 when it has at least one. It is
report-only: it reads the profile and changes nothing.

`reconcile` can enforce the same check before it runs. A normal run is resilient (an
unknown check id degrades to a WARN and the other checks still run), which is what you
want when inspecting a drifted box. In CI, where a profile that silently checks less than
it claims should fail the pipeline, add `--strict`: `ess-orrery reconcile --profile PATH
--strict` validates first and refuses to run (exit 2) if the profile has any error,
rather than starting a run that would report less than it appears to.

It is value-blind: an issue names a location (`box`, `checks[2].id`) and, at most, a
check id or an option key, never an option value. A profile that points a check at a
secret path can be validated without that path appearing in the output.

## Per-check options

A check that declares its option schema is also checked at the top level: an option key
the check does not recognize is a warning (with a suggested correction, so `edge` is
flagged in favor of `edges`), and a required option the check cannot work without is an
error (org-map without a `source`, for example). A check that declares no schema is
validated by id only. This is still value-blind: an unknown or missing option is named by
its KEY, never its value.

## Scope

Validation covers the top-level keys of each `[[checks]]` table. It does not yet descend
into list entries (an edge's `to`, a floor's `min`, a consumer's `path`); a mistake there
surfaces when the check runs, as a WARN finding, not here. Nested validation is a later
slice.
