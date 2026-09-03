"""The append-only audit store: a hash-chained log of entries, plus the folded record view.

Every consequential action appends entries (propose, approve, result); entries never change. Each
entry carries `prev` (the previous entry's `self` hash) and `self` (the hash of its own content), so
the log is a chain: altering or dropping any past entry breaks it, which `verify` detects. Bodies (the
proposal text, the resulting diff) live in the content-addressed store and are referenced by hash, so
what a record CLAIMS was proposed or changed cannot quietly differ from the bytes. No new crypto: the
same sha256 content-addressing the integrity store already uses.

The chain proves nobody can alter, reorder, or mid-delete an entry without rewriting every later hash.
It cannot, on its own, prove the TAIL is complete: lopping off the newest entries leaves a shorter but
consistent chain. Detecting that needs an anchor the actor cannot retro-edit. This store emits the head
(seq + self) to `ORRERY_AUDIT_ANCHOR` when set (point it at an append-only sink outside the log's own
trust domain), and `verify` fails if an anchored head is no longer in the log. With no anchor set,
`verify` is internally honest and SAYS a truncated tail would not be detected.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..home import ensure_dir, state_home
from ..integrity.store import Store, hash_bytes

_LOG = "log.jsonl"


def _canon(d: dict) -> str:
    """Deterministic serialization for hashing (stable key order, no incidental whitespace)."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class AuditStore:
    def __init__(self, root: Path | str | None = None, cas: Store | None = None,
                 anchor: Path | str | None = None):
        self.root = Path(root) if root is not None else state_home() / "audit"
        self.cas = cas if cas is not None else Store()
        env_anchor = os.environ.get("ORRERY_AUDIT_ANCHOR")
        self.anchor = Path(anchor) if anchor else (Path(env_anchor) if env_anchor else None)

    @property
    def log_path(self) -> Path:
        return self.root / _LOG

    # --- append (the only mutation: add one entry to the end) ---------------------------------

    def append(self, entry: dict) -> str:
        """Append one entry, chaining it to the previous one, and return its `self` hash. The entry
        dict is the content MINUS `prev`/`self`, which this computes."""
        ensure_dir(self.root)
        prev = self._last_self()
        body = {k: v for k, v in entry.items() if k not in ("prev", "self")}
        body["prev"] = prev
        this = hash_bytes(_canon(body).encode("utf-8"))
        line = _canon({**body, "self": this}) + "\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        if self.anchor is not None:
            self._emit_head(this)
        return this

    def _emit_head(self, self_hash: str) -> None:
        """Append the new head (seq + self) to the external anchor, best-effort. A failed emit must not
        fail the action; it only means this head is not yet anchored (verify treats newer-than-anchor
        entries as benign, so the sole exposure is the same crash window an unanchored newest entry has)."""
        try:
            self.anchor.parent.mkdir(parents=True, exist_ok=True)
            with open(self.anchor, "a", encoding="utf-8") as f:
                f.write(_canon({"seq": len(self.entries()), "self": self_hash}) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass

    def expected_head(self) -> str | None:
        """The last head self-hash recorded in the external anchor, or None if unset/empty."""
        if self.anchor is None or not self.anchor.exists():
            return None
        last = None
        with open(self.anchor, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = json.loads(line).get("self")
        return last

    def head(self) -> dict | None:
        """The current on-disk head: {seq, self}, or None if the log is empty. What an anchor captures."""
        es = self.entries()
        return {"seq": len(es), "self": es[-1].get("self")} if es else None

    def _last_self(self) -> str | None:
        last = None
        for e in self.entries():
            last = e.get("self")
        return last

    # --- read ---------------------------------------------------------------------------------

    def entries(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        out = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def records(self) -> list[dict]:
        """Fold the entries into one record per record_id: {id, ts, actor, action, subject,
        proposed, approved_by, result, status}, in the order they were first proposed."""
        recs: dict[str, dict] = {}
        order: list[str] = []
        for e in self.entries():
            rid = e.get("record_id")
            if rid is None:
                continue
            kind = e.get("kind")
            if kind == "propose":
                if rid not in recs:
                    order.append(rid)
                recs[rid] = {
                    "id": rid,
                    "ts": e.get("ts"),
                    "actor": e.get("actor"),
                    "action": e.get("action"),
                    "subject": e.get("subject"),
                    "proposed": {"summary": e.get("summary"), "body_hash": e.get("body_hash")},
                    "approved_by": None,
                    "result": None,
                    "status": "proposed",
                }
            elif kind == "approve" and rid in recs:
                recs[rid]["approved_by"] = e.get("by")
                if recs[rid]["status"] == "proposed":
                    recs[rid]["status"] = "approved"
            elif kind == "result" and rid in recs:
                recs[rid]["result"] = {"status": e.get("status"), "diff_hash": e.get("diff_hash")}
                recs[rid]["status"] = e.get("status") or recs[rid]["status"]
        return [recs[r] for r in order]

    def get(self, record_id: str) -> dict | None:
        for r in self.records():
            if r["id"] == record_id:
                return r
        return None

    # --- verify (re-walk the chain and re-check every content-address) -------------------------

    def verify(self, expect_head: str | None = None) -> tuple[bool, str]:
        prev = None
        selves: list[str] = []
        for i, e in enumerate(self.entries()):
            body = {k: v for k, v in e.items() if k != "self"}
            expect = hash_bytes(_canon(body).encode("utf-8"))
            if e.get("self") != expect:
                return False, f"entry {i}: self hash mismatch (record altered)"
            if body.get("prev") != prev:
                return False, f"entry {i}: broken chain (prev does not match the previous entry)"
            for h in (e.get("body_hash"), e.get("diff_hash")):
                if h and not self.cas.has(h):
                    return False, f"entry {i}: referenced body {h} is missing from the store"
            prev = e.get("self")
            selves.append(e["self"])

        n = len(selves)
        want = expect_head or self.expected_head()
        if want:
            if want not in selves:
                return False, (f"anchored head {want[:12]} is not in the log: the tail was "
                               f"truncated or rewritten below the anchor")
            newer = n - 1 - selves.index(want)
            tail = "tail complete" if newer == 0 else f"tail complete to the anchor, {newer} newer not yet anchored"
            return True, f"{n} entries, chain consistent, head anchored ({want[:12]}); {tail}"
        return True, (f"{n} entries, chain internally consistent; no head anchor set, "
                      f"so a truncated tail would not be detected")
