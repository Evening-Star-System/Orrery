# Vault credentials: capability, not presence

## The failure this exists for

Seven outages on this fleet shared one shape. A vault credential expired, or was re-minted with a
narrower policy set, and **nothing was measuring whether it still worked**. Every signal that was
being checked stayed green:

- `bao status` reports the vault unsealed, but it needs **no token**, so it says nothing about
  credentials at all.
- The operator env file is present, with a plausible-looking token in it.
- The secret-to-consumer graph (`secret-edges`) is intact: every consumer still references the secret.

The credential simply stops working: in every session and every repository at once, because
credentials are read at use time. The next signal is a human failing to push, days later.

**Presence is not capability.** `secret-edges` verifies the graph; `vault-capability` verifies the
credential behind it.

## How to test a token (the two obvious checks both lie)

This vault's hardened `default` policy DENIES `auth/token/lookup-self` and `sys/mounts`, so
`vault-whoami` printing `(none)` is **not** proof of a bad token either.

Use **`sys/capabilities-self`**:

| token state | `capabilities-self` returns |
|---|---|
| valid, permitted | `["read"]` |
| valid, **not** permitted | `["deny"]` (still a list) |
| **invalid / expired** | HTTP 403 |

A valid token answers *even when the answer is `deny`*. That is the only way to distinguish "expired"
from "merely unprivileged", and it is what the probe uses.

## The pieces

- **`bin/vault-credential-probe`**: runs on the box that holds the credential. Compares
  `capabilities-self` against the paths the **consumer itself** declares it needs (`credential-helper paths`), and
  writes `/var/lib/orrery/vault-credentials.json`. Emails on transition; re-alerts at most daily.
- **`checks/vault_capability.py`**: reads that report. Holds no credentials, so it works unchanged
  over `LocalBox` and `SshBox`, and stays value-blind: only vault paths and capability names ever
  reach a finding.
- **`bin/set-vault-token`**: installs a token into an operator env file.
- **`bin/fix-vault-credentials`**: one-command repair, admin token on stdin.
- **`integrations/systemd/vault-credential-probe.{service,timer}`**: every 15 minutes.

## Three design rules, each bought with an outage

**1. Derive the expectation from the consumer, never restate it.**
The mint scripts held a hand-typed path list containing only the APP buckets, so every re-mint
silently dropped three SSH keys. `credential-helper paths` prints what the credential helper actually needs from its own tables;
the policy and the probe both derive from it, so adding a bucket widens the next mint automatically.
*Signature of the bug it prevents: app buckets fine, all SSH buckets 403.*

**2. Record whether the probe RAN separately from what it FOUND.**
`probe_ok` and `verdict` are different fields. A probe that cannot reach the vault reports
`probe_ok=false` and makes **no claim** about the credential. Conflating them once cost five days: a
syncer wrote freshness only on success, so five days of good syncs looked stale and "the data is old"
was indistinguishable from "the syncer is broken". A stale report is itself a finding: a stale `OK`
is DRIFT, not OK, because that is exactly how a dead probe hides a dead credential.

**3. Make it a systemd unit, never cron.**
The OpenBao raft snapshot was a cron job that wrote `SNAPSHOT FAILED` to a logfile and exited 1. It
did that every night for ten nights and nobody knew, because cron failures are invisible to
`systemctl --failed` and nobody reads a logfile that is usually boring. **A logfile is not
monitoring.** A failed unit appears where failures are already looked for.

## Operating it

Repair (admin token on stdin, never argv):

    printf '%s' '<admin-token>' | fix-vault-credentials

It writes the policy from `credential-helper paths`, mints with **every** required policy, installs via
`set-vault-token`, clears the cached App tokens, and verifies. Then confirm with `credential-helper verify`, which
authenticates each bucket against its real host rather than checking presence.

Two footguns it exists to remove:

- `bao token create -policy=X -policy=default` **REPLACES** the policy set. It does not add.
- `sed -i 's|^BAO_TOKEN=.*|...|'` against a line reading `export BAO_TOKEN=` matches **nothing**, yet
  still rewrites the file. New mtime, old dead token. It looks applied and is not. `set-vault-token`
  matches both spellings, appends if neither exists so it can never silently no-op, preserves the
  unseal key, and **verifies by exercise with rollback**: a token that does not work cannot be
  installed.

**Periodic tokens still expire.** A `period=768h` token has no max TTL but dies if nothing renews it
inside the period. Every such token needs a named renewer, and the renewer must be something that
actually runs: a credential nothing renews is a credential with an expiry date nobody wrote down.
Use `bao token renew`; `renew-self` is an API path, not a CLI subcommand, and OpenBao 2.6 rejects it.
