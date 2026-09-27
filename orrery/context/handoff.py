"""Session continuity: consolidate (wrap) and orient (pickup) as first-class context capabilities.

The resolver READS scoped context at session start. This adds the WRITE half and its audited record: a
session consolidates a durable handoff into the head of its scoped digest, so the next session (including
after a context clear) wakes oriented from it. The handoff lives between PICKUP markers at the TOP of the
digest, which is exactly the slice the resolver injects, so orientation is automatic.

Generic and config-driven: no operator identity here (this ships in open-core). The CONTENT of a handoff is
composed by the caller (a model, a script); this owns the mechanics that must be exact: marker placement,
archive + prune, the head-line ceiling, and emitting a hash-chained audit record so the consolidation is
tamper-evident and can be witnessed off-box by the existing audit anchor.
"""
from __future__ import annotations

import datetime
import os

from .config import ContextConfig
from .scope import resolve_scope

START = "<!-- PICKUP:START -->"
END = "<!-- PICKUP:END -->"
DEFAULT_CEILING = 250
DEFAULT_KEEP = 20


def _target(cwd: str, config: ContextConfig) -> str | None:
    """The digest this cwd consolidates into: the project's digest, or the ops digest."""
    scope = resolve_scope(cwd, config.projects_root)
    if scope.kind == "project" and scope.path:
        return os.path.join(scope.path, config.project_digest_relpath)
    return config.ops_digest  # ops scope; may be None if unconfigured


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return ""


def _pickup_block(text: str) -> str | None:
    if START in text and END in text:
        return text.split(START, 1)[1].split(END, 1)[0].strip()
    return None


def _archive(digest_path: str, block: str, keep: int) -> str | None:
    hdir = os.path.join(os.path.dirname(os.path.abspath(digest_path)), "handoffs")
    os.makedirs(hdir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = os.path.join(hdir, f"{ts}.md")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(block + "\n")
    kept = sorted(x for x in os.listdir(hdir) if x.endswith(".md"))
    for old in kept[:-keep]:
        try:
            os.remove(os.path.join(hdir, old))
        except OSError:
            pass
    return dest


def write_handoff(cwd: str, config: ContextConfig, block_body: str, *,
                  actor: str = "session-wrap", store=None, keep: int = DEFAULT_KEEP) -> dict:
    """Consolidate: place `block_body` as the PICKUP block at the top of the scoped digest, archiving the
    previous block, and emit an audit record of the consolidation. Returns {target, record_id, archived}.
    The caller is responsible for having scrubbed secrets from block_body."""
    target = _target(cwd, config)
    if not target:
        raise ValueError("no digest target for this scope (ops digest unconfigured)")
    existing = _read(target)
    archived = None
    prior = _pickup_block(existing)
    if prior is not None:
        archived = _archive(target, prior, keep)
        # remove the old block (and one trailing blank line) before reinserting
        head, _, rest = existing.partition(START)
        _, _, after = rest.partition(END)
        existing = (head.rstrip() + "\n" + after.lstrip("\n")).lstrip("\n")
    block = f"{START}\n{block_body.strip()}\n{END}\n\n"
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(block + existing)

    subject = f"{resolve_scope(cwd, config.projects_root).bucket or 'ops'}/{resolve_scope(cwd, config.projects_root).project or ''}".rstrip("/")
    record_id = None
    try:
        from ..audit.record import PlanRecord
        rec = PlanRecord.propose(action="session-consolidate", subject=subject,
                                 proposed_body=block_body, actor=actor, store=store)
        rec.record_result(block_body, status="written")
        record_id = rec.id
    except Exception:
        record_id = None  # audit is best-effort here; the consolidation still happened
    return {"target": target, "record_id": record_id, "archived": archived}


def read_handoff(cwd: str, config: ContextConfig) -> str | None:
    """Orient: return the current PICKUP block for this scope, or None if there is no handoff yet."""
    target = _target(cwd, config)
    if not target:
        return None
    return _pickup_block(_read(target))


def head_line_count(cwd: str, config: ContextConfig) -> int:
    target = _target(cwd, config)
    return len(_read(target).splitlines()) if target else 0
