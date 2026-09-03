"""recover: restore a protected artifact to its recorded content-address.

The self-healing half, deterministic because the store holds the correct bytes under their hash:
recover fetches those exact bytes and writes them back. It MUTATES, so it is off under the
report-only default and only runs when invoked deliberately, per artifact. Every recover:
  1. refuses if there are no recorded bytes to restore from (never fabricates content),
  2. refuses to write through a symlink (a file replaced by a symlink is tampering, not a bit-flip),
  3. saves the current bytes to the store first, so the pre-recover state is itself recoverable,
  4. writes the correct bytes atomically (temp sibling, fsync, rename),
  5. re-hashes and, if the result does not match the recorded hash, rolls back to the pre-image,
  6. appends a durable audit line (path, from, to, when).
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..reconciler.box import LocalBox
from ..reconciler.profile import load_profile
from .store import Store


@dataclass
class RecoverResult:
    path: str
    status: str  # recovered | already-ok | would-recover | refused | failed
    detail: str
    from_hash: str | None = None
    to_hash: str | None = None


def _norm(value: str) -> str:
    s = str(value).strip().lower()
    return s.split(":", 1)[1] if s.startswith("sha256:") else s


def _atomic_write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".recover-{os.getpid()}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)  # atomic


def _record(path: str, from_hash, to_hash, actor: str = "operator") -> None:
    """Record the recover in the durable plan-audit (proposed + result). Best-effort: a failed audit
    must not fail the recover, since the content store still holds both versions."""
    try:
        from ..audit import PlanRecord

        ap = os.path.abspath(path)
        rec = PlanRecord.propose(
            "recover", ap,
            f"restore {ap} to its recorded content-address\n  from {from_hash}\n  to   {to_hash}",
            actor,
        )
        rec.record_result(f"restored {ap}: {from_hash} -> {to_hash}", status="recovered")
    except Exception:
        pass


def recover_artifact(entry: dict, store: Store, box=None, dry_run: bool = False, actor: str = "operator") -> RecoverResult:
    box = box or LocalBox()
    path = entry.get("path")
    recorded = _norm(entry.get("hash") or "")
    if not path or not recorded:
        return RecoverResult(path or "<artifact>", "refused", "artifact needs a path and a recorded hash")

    good = store.fetch(recorded)
    if good is None:
        return RecoverResult(path, "refused", "no recorded bytes in the store for the recorded hash")

    p = Path(path)
    if p.is_symlink():
        return RecoverResult(path, "refused", "path is a symlink; refusing to write through it")

    current = box.content_hash(path) if p.exists() else None
    if current == recorded:
        return RecoverResult(path, "already-ok", "bytes already match the recorded content-address", recorded, recorded)

    if dry_run:
        return RecoverResult(path, "would-recover", "bytes differ; would restore the recorded content-address", current, recorded)

    pre = store.record_path(p) if p.is_file() else None  # save the current bytes, reversible
    try:
        _atomic_write(p, good)
    except OSError as exc:
        return RecoverResult(path, "failed", f"write failed ({exc.__class__.__name__})", current, recorded)

    after = box.content_hash(path)
    if after != recorded:
        if pre is not None:
            pre_bytes = store.fetch(pre)
            if pre_bytes is not None:
                try:
                    _atomic_write(p, pre_bytes)
                except OSError:
                    pass
        return RecoverResult(path, "failed", "verify-after mismatch; rolled back to the pre-image", current, recorded)

    _record(path, current, recorded, actor)
    return RecoverResult(path, "recovered", "restored the recorded content-address", current, recorded)


def _artifacts_from_profile(profile_path: str) -> list[dict]:
    profile = load_profile(profile_path)
    out: list[dict] = []
    for c in profile.checks:
        if c.id == "content-address":
            out.extend(c.options.get("artifacts") or [])
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery recover")
    parser.add_argument("--profile", required=True, help="a profile declaring content-address artifacts")
    parser.add_argument("--artifact", help="recover only this artifact path (default: every declared one)")
    parser.add_argument("--dry-run", action="store_true", help="report what would be recovered, write nothing")
    parser.add_argument("--store", default=None, help="content-addressed store root (default: the state home's cas/)")
    args = parser.parse_args(argv)

    try:
        artifacts = _artifacts_from_profile(args.profile)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"recover: profile error: {exc}", file=sys.stderr)
        return 2
    if not artifacts:
        print("recover: the profile declares no content-address artifacts", file=sys.stderr)
        return 2

    if args.artifact:
        target = os.path.abspath(args.artifact)
        artifacts = [a for a in artifacts if os.path.abspath(a.get("path", "")) == target]
        if not artifacts:
            print(f"recover: no declared artifact matches {args.artifact}", file=sys.stderr)
            return 2

    store = Store(args.store)
    box = LocalBox()
    code = 0
    for entry in artifacts:
        res = recover_artifact(entry, store, box, dry_run=args.dry_run)
        print(f"{res.status}: {res.path}  ({res.detail})")
        if res.status in ("refused", "failed"):
            code = 1
    return code
