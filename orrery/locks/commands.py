"""capture, probe, add: the behavior-lock authoring moves.

Each returns `(exit_code, messages)` and touches only this repo's own files, so the CLI
stays a thin printer and the logic stays testable against a temp directory. The golden
is captured only from a clean, green probe: a command that exits non-zero, times out, or
prints nothing writes no golden and fails loudly, because a golden pinned from a broken
run would lock in the very regression this exists to stop.
"""

from __future__ import annotations

import json
import os
import tomllib

from . import manifest
from .runner import run_probe


def capture(manifest_path: str, only_id: str | None = None) -> tuple[int, list[str]]:
    """Run each target lock's command and, on a green run, write its golden into the
    manifest. `only_id` captures one lock; otherwise all. Writes the manifest once, only
    if at least one golden was captured. Exit 1 if any target failed to capture."""
    doc_text = _read(manifest_path)
    if doc_text is None:
        return 2, [f"no manifest at {manifest_path}"]
    try:
        doc = manifest.load(doc_text)
    except tomllib.TOMLDecodeError as exc:
        return 2, [f"{manifest_path} is not valid TOML: {exc}"]

    all_locks = manifest.locks(doc)
    if only_id is not None:
        targets = [lock for lock in all_locks if lock.get("id") == only_id]
        if not targets:
            return 2, [f"no lock with id {only_id!r} in {manifest_path}"]
    else:
        targets = all_locks
        if not targets:
            return 0, [f"no locks declared in {manifest_path}; nothing to capture"]

    root = _root_of(manifest_path)
    text = doc_text
    messages: list[str] = []
    captured = 0
    failed = 0
    for lock in targets:
        lock_id = lock.get("id")
        if not lock_id:
            messages.append("skipped a lock with no id")
            failed += 1
            continue
        result = run_probe(
            lock.get("command"),
            cwd=root,
            timeout=lock.get("timeout"),
            capture=str(lock.get("capture", "stdout-line")),
        )
        if not result.ok:
            messages.append(f"FAIL {lock_id}: {result.problem}; golden not written")
            failed += 1
            continue

        # Progression vs regression is human intent, made visible here. A first capture and a
        # deliberate MOVE of an existing golden are both writes, but a move means "this locked
        # behavior changed on purpose"; say so loudly (old -> new) so it lands as a reviewed diff,
        # not a silent overwrite. An identical value is a no-op, so re-running capture is clean.
        prior = lock.get("golden")
        value = result.value
        if prior is not None and str(prior).strip() and _norm(str(prior)) == _norm(value):
            messages.append(f"unchanged {lock_id}: already locked to {value}")
            continue
        try:
            text = manifest.set_golden(text, lock_id, value)
        except (KeyError, ValueError) as exc:
            messages.append(f"FAIL {lock_id}: could not write golden ({exc})")
            failed += 1
            continue
        if prior is None or not str(prior).strip():
            messages.append(f"captured {lock_id}: {value}")
        else:
            messages.append(f"re-locked {lock_id}: {prior} -> {value}  (behavior changed on purpose)")
        captured += 1

    if captured:
        _write(manifest_path, text)
        messages.append(f"wrote {manifest_path}; review the diff and commit")
    return (1 if failed else 0), messages


def probe(manifest_path: str, results_path: str | None = None) -> tuple[int, list[str]]:
    """Run every lock's command and write `orrery-locks.results.json` in the shape the
    reconciler check reads. Always exit 0 once the file is written: a failed probe is
    recorded as `ok:false`, and the gate (reconcile) turns that into a WARN that blocks,
    so probe's job is only to produce the observations, not to judge them."""
    doc_text = _read(manifest_path)
    if doc_text is None:
        return 2, [f"no manifest at {manifest_path}"]
    try:
        doc = manifest.load(doc_text)
    except tomllib.TOMLDecodeError as exc:
        return 2, [f"{manifest_path} is not valid TOML: {exc}"]

    root = _root_of(manifest_path)
    results: dict[str, dict] = {}
    messages: list[str] = []
    for lock in manifest.locks(doc):
        lock_id = lock.get("id")
        if not lock_id:
            continue
        result = run_probe(
            lock.get("command"),
            cwd=root,
            timeout=lock.get("timeout"),
            capture=str(lock.get("capture", "stdout-line")),
        )
        if result.ok:
            results[lock_id] = {"ok": True, "observed": result.value}
            messages.append(f"probed {lock_id}: {result.value}")
        else:
            results[lock_id] = {"ok": False, "error": result.problem}
            messages.append(f"probe {lock_id} did not complete: {result.problem}")

    out = results_path or os.path.join(root, manifest.RESULTS_NAME)
    _write(out, json.dumps({"generated_by": "orrery-locks", "results": results}, indent=2) + "\n")
    messages.append(f"wrote {out} ({len(results)} lock(s))")
    return 0, messages


def gate(manifest_path: str) -> tuple[int, list[str]]:
    """The CI gate in one call: probe every lock, then adjudicate the observed values against the
    goldens, and return a HARD exit code. 0 when every lock still holds (or there is no manifest yet);
    non-zero when any lock regressed, breached its floor/ceiling, or could not be observed.

    This reuses `probe` and the reconciler's behavior-lock check, so the directional compare
    (eq / >= floor / <= ceiling) has a SINGLE source of truth and is never re-implemented. There is no
    skip path and no operator-type branch: the verdict depends only on whether the locked behavior held.
    """
    if _read(manifest_path) is None:
        return 0, [f"no {manifest_path}; nothing to gate"]
    code, messages = probe(manifest_path)
    if code != 0:
        return code, messages  # e.g. the manifest is not valid TOML: block, do not pass

    from ..reconciler.box import LocalBox
    from ..reconciler.checks.behavior_lock import BehaviorLockCheck
    from ..reconciler.model import CLEAN_CEILING, Severity

    root = _root_of(manifest_path)
    findings = BehaviorLockCheck().run({"repos": [{"root": root}]}, LocalBox())
    worst = max((f.severity for f in findings), default=Severity.OK)
    for f in findings:
        messages.append(f"{f.severity.label:5} {f.subject}: {f.message}")
    clean = worst <= CLEAN_CEILING
    messages.append("GATE PASS" if clean else "GATE FAIL: a locked behavior regressed or could not be observed")
    return (0 if clean else 1), messages


def add(manifest_path: str, lock_id: str, command: str, why: str, capture_kind: str = "stdout-line") -> tuple[int, list[str]]:
    """Declare a new lock and capture its golden in one step, honoring the rule that a
    lock is declared and captured together. If the probe is not green the lock is left
    declared without a golden (which the check FAILs on) and the exit code is non-zero, so
    the gap is loud rather than silent."""
    doc_text = _read(manifest_path)
    if doc_text is None:
        text = "schema = 1\n"
    else:
        try:
            doc = manifest.load(doc_text)
        except tomllib.TOMLDecodeError as exc:
            return 2, [f"{manifest_path} is not valid TOML: {exc}"]
        if manifest.has_lock(doc, lock_id):
            return 2, [f"a lock with id {lock_id!r} already exists in {manifest_path}"]
        text = doc_text

    text = manifest.append_lock(text, lock_id, command, why, capture_kind)
    _write(manifest_path, text)
    code, messages = capture(manifest_path, only_id=lock_id)
    return code, [f"declared {lock_id}"] + messages


def _norm(value: str) -> str:
    """Whitespace-normalized comparison, matching how the check compares observed to golden,
    so 'unchanged' here means exactly what 'still matches' means at the gate."""
    return " ".join(str(value).split())


def _root_of(manifest_path: str) -> str:
    return os.path.dirname(os.path.abspath(manifest_path))


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
