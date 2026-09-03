#!/bin/sh
# orrery-locks-gate.sh: the behavior-lock CI gate. Fail the build if a locked behavior regressed.
#
# CI-agnostic: any CI system calls this one script from the repo root. It runs the single adjudicator
# `ess-orrery lock gate` (probe + adjudicate + hard exit code). The compare logic lives in one place
# (the tool), so this script never re-implements it.
#
#   sh scripts/orrery-locks-gate.sh [path/to/orrery-locks.toml]
#
# Exit 0 when every lock still holds (or there is no manifest yet); non-zero when a lock regressed or a
# probe did not complete. It NEVER passes silently: if the adjudicator cannot be obtained, it exits 3
# and blocks, because a gate that cannot run is a failed gate, not a skipped one.
set -eu

MANIFEST="${1:-orrery-locks.toml}"
if [ ! -f "$MANIFEST" ]; then
  echo "orrery-locks: no $MANIFEST at the repo root; nothing to gate"
  exit 0
fi

# Obtain the adjudicator. Prefer an installed ess-orrery; else run it ephemerally with pipx; else
# install it with pip. If none of these work, FAIL (exit 3), never skip.
if command -v ess-orrery >/dev/null 2>&1; then
  set -- ess-orrery
elif command -v pipx >/dev/null 2>&1; then
  set -- pipx run ess-orrery
elif command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
  echo "orrery-locks: installing ess-orrery to run the gate ..."
  python3 -m pip install --quiet --disable-pip-version-check ess-orrery >/dev/null 2>&1 \
    || { echo "orrery-locks: GATE ERROR could not install ess-orrery; failing the build"; exit 3; }
  set -- ess-orrery
else
  echo "orrery-locks: GATE ERROR no ess-orrery / pipx / python3+pip available to run the gate; failing the build"
  exit 3
fi

exec "$@" lock gate -m "$MANIFEST"
