"""PlanRecord: the small API every consequential action uses to record itself.

Three moves, always the same, so every writer (recover, promote, a fold-in) produces the same
three-part record. `approve(by)` is a neutral seam: the mechanism records who approved, and a caller
supplies that value from whatever policy it runs, without forking this API:

    rec = PlanRecord.propose(action, subject, proposed_body, actor)   # opens a record (proposed)
    rec.approve(by)                                                   # marks the GO (approved)
    rec.record_result(diff_body, status="applied")                   # closes it with the diff
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..integrity.store import hash_bytes
from .store import AuditStore, _canon


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_bytes(body) -> bytes:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _summary(body) -> str:
    """A one-line human hook for the record; the full body lives in the content store."""
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", "replace")
    if not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)
    first = body.strip().splitlines()[0] if body.strip() else ""
    return first[:200]


class PlanRecord:
    def __init__(self, store: AuditStore, record_id: str):
        self.store = store
        self.id = record_id

    @classmethod
    def propose(cls, action: str, subject: str, proposed_body, actor: str,
                store: AuditStore | None = None) -> "PlanRecord":
        store = store or AuditStore()
        body_hash = store.cas.record(_as_bytes(proposed_body))
        ts = _now()
        # A stable, unique id for this record: the content-address of its opening facts.
        rid = hash_bytes(_canon({
            "ts": ts, "actor": actor, "action": action, "subject": subject, "body": body_hash,
        }).encode("utf-8"))
        store.append({
            "kind": "propose", "record_id": rid, "ts": ts, "actor": actor,
            "action": action, "subject": subject, "summary": _summary(proposed_body),
            "body_hash": body_hash,
        })
        return cls(store, rid)

    def approve(self, by: str) -> None:
        self.store.append({"kind": "approve", "record_id": self.id, "ts": _now(), "by": by})

    def record_result(self, diff_body, status: str = "applied") -> None:
        diff_hash = self.store.cas.record(_as_bytes(diff_body))
        self.store.append({
            "kind": "result", "record_id": self.id, "ts": _now(),
            "status": status, "diff_hash": diff_hash,
        })

    def view(self) -> dict | None:
        return self.store.get(self.id)
