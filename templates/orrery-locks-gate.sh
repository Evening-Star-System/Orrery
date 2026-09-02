#!/bin/sh
# orrery-locks-gate.sh: fail the build if a locked behavior regressed.
#
# Run from the repo root, in the project's own CI (the ratified posture: the consumer
# runs its own probes, Orrery adjudicates). Any CI system can call this one script, so
# the gate is not tied to a particular CI. Requires `ess-orrery` on PATH.
#
#   sh scripts/orrery-locks-gate.sh [path/to/orrery-locks.toml]
#
# Exit 0 when every lock still matches its golden (or there are no locks yet); non-zero
# when a lock regressed (FAIL) or a probe did not complete (WARN), which stops the build.
set -eu

MANIFEST="${1:-orrery-locks.toml}"
if [ ! -f "$MANIFEST" ]; then
  echo "orrery-locks: no $MANIFEST at the repo root; nothing to gate"
  exit 0
fi

# 1. Produce the observed values. The consumer runs its own probe commands here, where
#    its fixtures and toolchain live, and writes orrery-locks.results.json.
ess-orrery lock probe -m "$MANIFEST"

# 2. Adjudicate observed against the committed goldens. root = "." keeps the profile
#    path-portable: it resolves against the CI checkout, wherever that lands.
PROFILE="$(mktemp)"
trap 'rm -f "$PROFILE"' EXIT
cat > "$PROFILE" <<'EOF'
schema = 1
box = "ci"
[[checks]]
id = "behavior-lock"
[[checks.repos]]
root = "."
EOF

# reconcile exits non-zero on the worst finding, so a regression fails the job.
exec ess-orrery reconcile --profile "$PROFILE" --check behavior-lock
