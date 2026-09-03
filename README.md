# Orrery

An operator control plane for a fleet of Linux boxes.

Orrery holds the declared shape of every box in a fleet and proves continuously that reality still
matches it. An orrery is a clockwork model of a star system: one central mechanism drives many bodies
in correct relation, and you turn it by hand to see where everything is. One control plane, many
boxes, an instrument for seeing, operable by hand.

## Install

The engines have zero runtime dependencies (Python 3.11+ only):

```
pip install .
ess-orrery doctor      # verify the installation
```

The themed terminal deck is an optional extra:

```
pip install '.[tui]'
ess-orrery deck --profile <profile.toml> --context-config <context.toml>
```

## Use

```
ess-orrery reconcile --profile <profile.toml>            # drift report (report-only)
ess-orrery reconcile --profile <profile.toml> --format prometheus   # metrics for Grafana
ess-orrery context   --config  <context.toml>            # resolve context for a working directory
ess-orrery update                                        # upgrade in place; never touches your setup
ess-orrery backup / restore                              # your setup as a portable archive
ess-orrery telemetry status|on|off                       # anonymous usage stats, off by default
ess-orrery doctor                                        # verify this installation
```

A profile declares the desired state a box should have. See `profiles/example.toml` for the format. Orrery
is report-only: it measures and reports, it does not change your boxes.

## Grafana

`ess-orrery reconcile --format prometheus` emits Prometheus metrics, so fleet drift shows up in Grafana
next to your other metrics and alerts through Alertmanager. A ready-to-import dashboard, alert rules, and a
setup guide are in `integrations/grafana/`.

## The operating standard

One consistent way to run every project in a fleet, any language, any CI host: declare, prove, gate,
roll up. Learn it once, apply it everywhere, and run every step by hand. See
[docs/operating-standard.md](docs/operating-standard.md).

## The reconciler

The core generalizes one idea, borrowed from the way good conformance systems treat a rule: a thing
is not "declared", it is declared AND its probe passes, continuously. Each check is declarative and
pluggable:

| Check | What it proves |
|---|---|
| `org-map` | one source-of-truth table agrees with every consumer that re-encodes it |
| `fleet-reach` | actual ssh reach matches the declared matrix (a reopened denied edge is drift) |
| `declared-presence` | required members exist; planned-absent paths stay absent |
| `secret-edges` | the secret-to-consumer graph holds (value-blind: never reads a secret value) |
| `floors` | counts stay within declared floors and ceilings |
| `managed-settings` | the enforcement layer stays root-owned and unwritable, so the rules cannot be quietly disabled |

Findings carry a severity (ok, info, warn, drift, fail); the run exits non-zero on drift so a cron or
CI can alert.

## Design

- **Core** (this repository) is read-only, dependency-free, and identity-free: it ships to any
  installation unchanged.
- **Profiles** are per-installation declarative config. They hold the identity and topology, and they
  live with the installation, not here.
- **Cargo** is the operator's own notes and memory. It is never part of this repository.

Keeping those three separated is the whole discipline.

## License

Orrery's core (this repository) is licensed **AGPL-3.0-or-later**: free to use, run, study, and
modify, with the condition that if you offer a modified version to others over a network you make
your changes available under the same terms. See `LICENSE`.

A **commercial license** is available from Evening Star Productions for anyone who cannot meet the
AGPL terms. The governed-autonomy trust layer, hosted control plane, and GUI are separate proprietary
products and are not part of this repository.

Copyright Evening Star Productions. Contributions require a CLA so the project can keep offering the
commercial dual-license. See `CONTRIBUTING.md`.
