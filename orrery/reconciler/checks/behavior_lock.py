"""behavior-lock: a shipped feature's observable behavior, held as a floor.

A product team fixes a bug at one point in time, on one code path. Nothing pins the
fixed behavior, so the same defect can walk back in through a path the fix never
touched and no signal fires until a user hits it. Arcalox lived this: "sync must not
ship orphaned media blobs" was fixed on the web export path (92904af) and the native
path regressed the same defect months later, because no test pinned the behavior at
the boundary that both paths share.

A behavior lock is the golden-trace record-then-assert loop given `floors` severity,
pointed at a consumer repo. The consumer declares each locked behavior in an in-repo
manifest: a stable `id`, the `why` that earned the lock, a `command` that prints ONE
canonical value, and the recorded `golden` that command must keep producing. A run
whose observed value no longer matches the golden is a regression, and a regression is
a FAIL, the same severity a breached file floor produces, so a release gate stops on it.

WHY THIS CHECK ADJUDICATES INSTEAD OF EXECUTING (the load-bearing posture).
The `command` is arbitrary consumer build code. Running it here would make a judge that
is meant to stay small and trusted into a permanent sandbox liability, so the default
path never executes it. The consumer's own pipeline runs each probe where its fixtures
and toolchain already live, writes the observed canonical value to a results file, and
Orrery reads that file and owns the verdict. Orrery holds the golden and the gate; the
consumer does the touching. This mirrors the rotation design's split, and it is what
makes the check pure and hermetically testable.

A local-run mode exists for development only (mode 2): Orrery shells the command out
itself under a hard timeout with the working tree read-only, capturing the last
non-empty stdout line. It is a convenience for authoring a lock, never the gate.

SEVERITY.
  OK    observed equals golden (whitespace-normalized). The behavior is still locked.
  INFO  the lock is marked `hold`: a known, accepted, pending re-lock, reported not gated.
  WARN  the probe errored, timed out, or produced nothing parseable, so there is no
        observed value to judge. A skipped lock is never a silent pass.
  FAIL  observed != golden (the regression this exists for), OR the lock is declared
        with no captured golden -- an empty lock protects nothing, so it blocks until
        captured, forcing declare-and-capture in the same PR.

DRIFT (a hand-edited golden, detected by a second golden store that disagrees with the
manifest) is deferred: the ratified decision keeps the golden ONLY in the consumer
repo, so there is no independent store to disagree with it here. See design.md.

Discipline from `checks/base.py` holds without change: a data or execution problem
degrades to WARN, never a raise, and one broken lock never sinks the run.
"""

from __future__ import annotations

import json
import os
import tomllib

from ..box import Box
from ..model import Finding, Severity

ID = "behavior-lock"
TITLE = "shipped behaviors stay locked to their recorded goldens"

_MANIFEST = "orrery-locks.toml"
_RESULTS = "orrery-locks.results.json"


class BehaviorLockCheck:
    id = ID
    title = TITLE
    # `repos` is the list of consumer roots to adjudicate; `mode` selects adjudicate
    # (default) or the dev-only local run. Declared so a typo'd option surfaces under
    # `profile validate` rather than as silent under-checking.
    option_keys = frozenset({"repos", "mode"})
    required_keys = frozenset({"repos"})

    def run(self, options: dict, box: Box) -> list[Finding]:
        repos = options.get("repos") or []
        if not repos:
            return [Finding(ID, Severity.WARN, ID, "no consumer repos declared")]
        default_mode = str(options.get("mode", "adjudicate")).lower()

        findings: list[Finding] = []
        for entry in repos:
            findings.extend(self._check_repo(entry, default_mode, box))
        return findings

    def _check_repo(self, entry: dict, default_mode: str, box: Box) -> list[Finding]:
        if isinstance(entry, str):
            entry = {"root": entry}
        root = entry.get("root")
        if not root:
            return [Finding(ID, Severity.WARN, ID, "repo entry missing 'root'")]

        manifest_path = entry.get("manifest") or _join(root, _MANIFEST)
        raw = box.read_text(manifest_path)
        if raw is None:
            # Absent manifest is nothing to check, not a failure: a consumer that ships
            # no locks is simply not opted in yet.
            return []
        try:
            manifest = tomllib.loads(raw)
        except (tomllib.TOMLDecodeError, ValueError):
            return [Finding(ID, Severity.WARN, root, f"lock manifest at {manifest_path} is not valid TOML")]

        repo_name = str(manifest.get("repo") or os.path.basename(root.rstrip("/")) or root)
        locks = manifest.get("locks") or []
        if not locks:
            return []

        mode = str(entry.get("mode", default_mode)).lower()
        results = {} if mode == "local" else self._load_results(entry, root, box)

        findings: list[Finding] = []
        for lock in locks:
            findings.append(self._check_lock(lock, repo_name, root, mode, results))
        return findings

    def _load_results(self, entry: dict, root: str, box: Box) -> dict:
        """The consumer-produced observed values, keyed by lock id. Absent or malformed
        yields an empty map, so every lock degrades to WARN ("no observed value")
        rather than a false OK."""
        results_path = entry.get("results") or _join(root, _RESULTS)
        raw = box.read_text(results_path)
        if raw is None:
            return {}
        try:
            doc = json.loads(raw)
        except ValueError:
            return {}
        got = doc.get("results") if isinstance(doc, dict) else None
        return got if isinstance(got, dict) else {}

    def _check_lock(self, lock: dict, repo_name: str, root: str, mode: str, results: dict) -> Finding:
        lock_id = lock.get("id") or "<lock>"
        subject = f"{repo_name}/{lock_id}"

        if lock.get("hold"):
            # Deliberately captured but held pending a re-lock: report, do not gate.
            return Finding(ID, Severity.INFO, subject, "lock is on hold (accepted, pending re-lock)")

        golden = lock.get("golden")
        if golden is None or not str(golden).strip():
            # Declared but never captured. An empty lock protects nothing, so it blocks
            # until a golden is recorded in the same PR that declares it.
            return Finding(
                ID, Severity.FAIL, subject,
                "lock is declared but never captured; record its golden before it can gate",
                expected="a recorded golden", observed="none",
            )

        observed, problem = self._observe(lock, lock_id, root, mode, results)
        if problem is not None:
            # Errored, timed out, or unparseable probe: loud and non-green, but never a
            # false OK. This is a statement about the PROBE, not about the behavior.
            return Finding(ID, Severity.WARN, subject, problem)

        severity, message, expected, observed_out = _adjudicate(
            observed, golden, str(lock.get("compare", "eq"))
        )
        return Finding(ID, severity, subject, message, expected=expected, observed=observed_out)

    def _observe(self, lock: dict, lock_id: str, root: str, mode: str, results: dict):
        """Return (observed_value, problem). Exactly one is not None."""
        if mode == "local":
            return self._observe_local(lock, root)
        entry = results.get(lock_id)
        if not isinstance(entry, dict):
            return None, "no observed value was produced for this lock (probe did not run)"
        if entry.get("ok") is False or entry.get("error"):
            note = entry.get("error") or "probe reported failure"
            return None, f"probe did not complete: {note}"
        observed = entry.get("observed")
        if observed is None or not str(observed).strip():
            return None, "probe produced no parseable value"
        return str(observed), None

    def _observe_local(self, lock: dict, root: str):
        """Mode 2, development only: shell the command out under a hard timeout, capturing
        the last non-empty stdout line. Any breach is a WARN, never a false OK. Not the
        gate and not the tested path. Uses the one shared runner (`orrery.locks.runner`)
        so local mode, `lock capture`, and `lock probe` all run a command the same way."""
        from ...locks.runner import run_probe

        result = run_probe(
            lock.get("command"),
            cwd=root,
            timeout=lock.get("timeout"),
            capture=str(lock.get("capture", "stdout-line")),
        )
        if not result.ok:
            return None, f"local mode: {result.problem}"
        return result.value, None


def _join(root: str, name: str) -> str:
    return root.rstrip("/") + "/" + name


def _norm(value) -> str:
    return " ".join(str(value).split())


def _as_number(value):
    """A bare number, or None. Directional compare needs a scalar, so a value like
    'orphaned_blobs=0' is not a number here; the probe for a floor/ceiling lock prints the
    number alone."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _adjudicate(observed, golden, compare: str):
    """Judge observed against golden under the lock's compare mode. Returns
    (severity, message, expected, observed) for the Finding.

    eq  : exact match (default). Any change is a regression to fix or a deliberate re-lock.
    >=  : a floor. The value may IMPROVE (rise) freely; falling below the golden is the
          regression. For a metric where more is better (coverage, a passing count).
    <=  : a ceiling. The value may improve (fall) freely; rising above the golden is the
          regression. For a metric where less is better (bundle size, latency, a defect
          count). This is how a lock allows the positive change and blocks only the negative.
    """
    if compare == "eq":
        if _norm(observed) == _norm(golden):
            return Severity.OK, "behavior still matches its golden", None, None
        return Severity.FAIL, "locked behavior regressed", str(golden), str(observed)

    if compare in (">=", "<="):
        obs, gold = _as_number(observed), _as_number(golden)
        if obs is None or gold is None:
            return (
                Severity.WARN,
                f"compare {compare!r} needs numeric values (golden={golden!r}, observed={observed!r})",
                None,
                None,
            )
        if compare == ">=":
            if obs >= gold:
                return Severity.OK, f"behavior holds its floor (observed {observed} >= golden {golden})", None, None
            return Severity.FAIL, "locked behavior regressed below its floor", str(golden), str(observed)
        if obs <= gold:
            return Severity.OK, f"behavior holds its ceiling (observed {observed} <= golden {golden})", None, None
        return Severity.FAIL, "locked behavior regressed above its ceiling", str(golden), str(observed)

    return Severity.WARN, f"unknown compare mode {compare!r} (use eq, >=, or <=)", None, None
