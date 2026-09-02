# Change Log: Orrery
<!-- Entries are newest-first. Format: 2006-01-02 15:04 What changed. Which files. Any version bump.
     This file is committed to the repo. Keep entries factual and project-focused.
     No process, tool, or session references. -->

---

2026-08-26 Validate each check's options, not just its id. A check now declares the top-level option
keys it understands and which it requires, so `profile validate` (and `reconcile --strict`) flags an
option key a check does not recognize as a warning, with a suggested correction, and a missing required
option as an error, before a run turns a typo like `edge` for `edges` into silent under-checking. Still
value-blind: an option is named by its key, never its value. Covers the top-level keys of each check;
nested list-entry keys are a later slice. Adds an optional option-schema convention to the check protocol
and a schema for all nine checks.

2026-08-26 Validate a profile before you rely on it. A profile is the most hand-edited input, and its
worst failures are quiet: a check id with a typo runs nothing and reports nothing, so a box looks clean
because it was never actually checked. New `ess-orrery profile validate PATH` reads a profile and reports
its shape problems as findings of their own without running any check against the box: invalid TOML or an
unreadable file, a missing box, a check id the registry does not know (with a suggested correction), a
duplicated check id, and a check left with no options. Exit 0 when sound, 2 when it has an error. It is
report-only and value-blind: an issue names a location and at most a check id or an option key, never an
option value, so a profile that points a check at a secret path validates without that path appearing in
the output. Adds orrery/reconciler/validate.py, orrery/reconciler/profile_cli.py, the `profile` command,
tests/test_profile_validate.py, and docs/profile-schema.md. `reconcile --strict` runs that same
validation first and refuses to start (exit 2) if the profile has an error, for CI; a normal run
stays resilient, degrading an unknown check id to a WARN so the other checks still run.

2026-08-25 Ship the vault-credential tooling and its runbook. The capability check landed without the
thing that produces the report it reads, or the commands that repair what it finds; those lived only
on the machines they ran on, which left the check installable and the rest folklore. Adds
bin/vault-credential-probe, which exercises a credential against the paths its consumer declares it
needs and records whether the probe ran separately from what the probe found. Adds bin/set-vault-token,
which installs a token into an operator env file, matches both the bare and exported spellings of the
key so it cannot silently do nothing, preserves the unseal key, and verifies by exercise with rollback
so a credential that does not work cannot be installed. Adds bin/fix-vault-credentials, a one-command
repair reading the admin token on stdin, and the systemd units that run the probe every fifteen
minutes. New docs/vault-credentials.md records why presence checks pass while a credential is dead,
why a logfile is not monitoring, and why a periodic token still needs a named renewer that actually
runs.

2026-08-24 Vault-capability check: verify a credential can still do what its consumers need.
A credential that has expired or been re-minted with a narrower policy set looks identical to a
healthy one from every signal that was previously checked: the vault reports unsealed, the env file
is present with a plausible token in it, and the secret-to-consumer graph is intact. The credential
simply stops working, in every session and every repository at once, and the next signal is a human
hitting the failure days later. New vault-capability reconciler check asserts capability rather than
presence, reporting each unreadable path against the named consumers that can no longer authenticate.
The exercise runs where the credential already lives, so the reconciler holds no credentials and
stays value-blind: only vault paths and capability names appear in a finding. New
vault-credential-probe compares sys/capabilities-self against the paths the consumer itself declares,
so the expectation is derived rather than restated and cannot drift from the consumer. It records
whether the probe ran separately from what the probe found, so an unreachable vault is never reported
as a broken credential, and a report that stops updating is itself a finding rather than a stale
pass. Adds orrery/reconciler/checks/vault_capability.py, tests/test_vault_capability.py, one registry
line, and a profile entry.

2026-08-20 Build guard and memory-headroom check. A shared box can be brought to a standstill by
two builds that are each individually reasonable, and the usual signals stay green while it happens:
oom_kill reads 0, free reports memory available, and load looks like any busy build. New heavy-build
command serialises resource-heavy builds across sessions and runs each one in its own systemd scope
with its own MemoryMax, so a build that overruns fails immediately and alone instead of throttling
everything beside it. heavy-build status answers whether anything else is building, finding both
guarded builds through the lock and unguarded ones through a process scan, and names the session each
belongs to. New memory-headroom reconciler check reports the composition that cannot recover on its
own - a MemoryHigh brake below an unreachable MemoryMax wall, swap at its ceiling, and a file cache
reclaimed to nothing - as FAIL, because each of those alone is ordinary operation. New
orrery-memory-watch timer pushes that verdict to Uptime Kuma on a push monitor, so a box too stalled
to report alarms by its silence. Adds orrery/buildguard/, orrery/reconciler/checks/memory_headroom.py,
integrations/systemd/builds.slice and the watch units, bin/heavy-build, bin/orrery-memory-watch, and
docs/build-guard.md.

2026-08-13 Prometheus output for Grafana. `ess-orrery reconcile --format prometheus` emits exposition
metrics (orrery_check_status, orrery_findings, orrery_drift_total, orrery_worst_severity, orrery_clean,
orrery_up, and a last-run timestamp) mapped from the finding severities, so fleet drift shows up in Grafana
next to the rest of your metrics and alerts through Alertmanager. A ready-to-import dashboard, example alert
rules, and an integration guide ship under integrations/grafana/. The existing --json flag stays as an
alias. Metrics carry only non-secret identities.

2026-08-09 Opt-in telemetry, off by default. The default install sends nothing; a user may opt in with
telemetry on to help with anonymous, aggregate usage. A single payload builder is the only place data is
assembled, so the exact fields that can ever leave are fixed: an anonymous id, the ess-orrery and Python
versions, the OS family, and per-command counts, never paths, hostnames, profiles, box or org names,
secrets, or reconciler output. The telemetry command's status prints exactly what a send would contain, and
off deletes the id. The sink is collector-agnostic and sends nothing until an endpoint is configured. When
telemetry is off, commands write nothing, so the default install stays read-only.

2026-08-09 Persistent setup and lifecycle. A durable home outside the installed package (XDG config and
state directories, or $ORRERY_HOME to relocate both), holding tool settings and a backup registry, never
operator identity, and created only when first written. New commands: update upgrades the package in place
and never touches the home, so it wipes nothing by construction (--check reports the latest version and
changes nothing, the only command that reaches the network); backup and restore make the setup one portable
archive with a manifest, refusing any path that would escape its target and refusing to overwrite a
different existing file without --force. The published distribution and command are named ess-orrery; the
import package remains orrery.

2026-08-09 Marketing site (site/): a static ten-page site on one design system, a landing page, a
reconciler/features page for the six checks, an honest category comparison, pricing, a get-started page
with real install and reconcile output, documentation, security, terms, privacy, and a branded 404. One
shared header, navigation, and footer across every page; a Dark/Light theme toggle; the public contact is
orrery@eveningstar.app. Cookieless, self-hosted, privacy-respecting analytics (disclosed in the privacy
policy) and no other external requests, WCAG 2.2 AA in both themes, extensionless URLs, sitemap, robots,
favicon, social card, and security headers. Builds to Cloudflare Pages.

2026-08-08 Packaging + install: pyproject.toml packages the core (zero runtime dependencies, optional
tui extra) with an `orrery` console command (reconcile / context / deck / doctor / version) and
`orrery doctor`, a self-check that verifies the installation. Proven with a cold install into a fresh
Ubuntu container: engines run from source with only python3, and `pip install .` yields a working
`orrery` with a healthy doctor.

2026-08-08 Secret-edges reconciler check: the secret-to-consumer graph. Declares each secret by a
non-secret identity and its consumers, confirms edges, and finds undeclared references. Value-blind
(fail-closed identity allowlist; a secret value is never scanned or printed).

2026-08-07 18:05 Themed terminal deck (orrery.tui, optional Textual dependency): a celestial-themed
TUI with a slowly rotating line-art orrery and live panels over the engines (a drift board that runs a
reconciler profile with severity colors, and a context panel showing the resolved scope). Presentation
only; the engines stay dependency-free. `python -m orrery.tui --profile P --context-config C`.

2026-08-07 17:30 Context subsystem (orrery.context): resolves operator context per working directory so
projects stop intermingling. PROJECT scope sees only its own state; OPS scope sees the fleet digest.
Isolation enforced by realpath containment plus config validation; reads are line-bounded. Plain CLI
with human or JSON output.

2026-08-07 15:25 Reconciler v0: report-only conformance engine. New `orrery/reconciler/` package
(engine, pluggable declarative checks, read-only Box abstraction, TOML profiles, human + JSON output,
non-zero exit on drift). Seed checks: org-map (single source of truth vs its consumers),
declared-presence (required members present, planned-absent paths stay absent), and fleet-reach
(declared reach matrix vs actual ssh, with a reopened denied edge reported as drift). Host inputs are
validated and option parsing is ended with `--` before probing. Profile-load errors surface as clean
output with a dedicated exit code. 23 tests. `profiles/example.toml` documents the profile format.

