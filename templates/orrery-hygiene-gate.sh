#!/bin/sh
# orrery-hygiene-gate.sh: the repo-hygiene CI gate. Fail the build if forbidden content is committed.
#
# CI-agnostic: any CI system calls this one script from the repo root. It runs a single
# `git grep -nIE` over the tracked files for classes of content that are wrong in ANY repository
# (private network addresses, absolute home-root paths, private-key blocks, secret-token shapes),
# and exits non-zero (fail-closed) on any hit, printing every matching line so the fix is obvious.
#
#   sh scripts/orrery-hygiene-gate.sh
#
# Exit 0 when the tree is clean; 1 when forbidden content is present; 3 when the gate cannot run
# (no git). It NEVER passes silently: a gate that cannot run is a failed gate, not a skipped one.
#
# Only git-tracked files are scanned (git grep ignores .git and untracked files by design). The gate
# script itself is excluded so its own pattern definitions are not reported. To exclude a known,
# deliberate fixture path (for example a security test that stores a sample token on purpose), set
# ORRERY_HYGIENE_EXCLUDES to a space-separated list of pathspecs.
set -eu

if ! command -v git >/dev/null 2>&1; then
  echo "orrery-hygiene: GATE ERROR git is not available to run the gate; failing the build"
  exit 3
fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "orrery-hygiene: GATE ERROR not inside a git work tree; failing the build"
  exit 3
fi

# Pathspecs: everything from the repo root, minus this gate script, minus any caller-declared fixtures.
set -- ':/' ':(exclude)scripts/orrery-hygiene-gate.sh'
if [ -n "${ORRERY_HYGIENE_EXCLUDES:-}" ]; then
  for _p in $ORRERY_HYGIENE_EXCLUDES; do
    set -- "$@" ":(exclude)$_p"
  done
fi

# Forbidden classes, all universally wrong in a repository. Each -e is an extended (ERE) pattern.
matches=$(git grep -nIE \
  -e '(^|[^0-9.])10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' \
  -e '(^|[^0-9.])192\.168\.[0-9]{1,3}\.[0-9]{1,3}' \
  -e '(^|[^0-9.])172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}' \
  -e '(^|[^A-Za-z0-9_.])/root/' \
  -e '[-]{5}BEGIN [A-Z0-9 ]*PRIVATE KEY[-]{5}' \
  -e 'ghp_[A-Za-z0-9]{20,}' \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'hvs\.[A-Za-z0-9_-]{10,}' \
  -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
  -e 'sk_live_[0-9a-zA-Z]{16,}' \
  -- "$@") && _status=0 || _status=$?

if [ "${_status}" -gt 1 ]; then
  echo "orrery-hygiene: GATE ERROR git grep failed (exit ${_status}); failing the build"
  exit 3
fi

if [ -n "$matches" ]; then
  echo "orrery-hygiene: FAIL forbidden content in tracked files:"
  printf '%s\n' "$matches"
  echo "orrery-hygiene: remove the above (private IPs, absolute home-root paths, private keys, or secret tokens) before merging."
  exit 1
fi

echo "orrery-hygiene: OK no forbidden patterns in tracked files"
exit 0
