"""CLI: ess-orrery audit <list|show|verify|export|head>

Read the plan-audit by hand: list records (filtered), show one record with its full proposal and
diff, verify the chain is intact, export the whole trail, or print the current head (what an external
anchor captures). Human-readable by default, JSON/CSV for a machine. This is the human-first surface;
a person can read and audit the entire trail with no AI.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys

from .store import AuditStore

_USAGE = "ess-orrery audit <list|show|verify|export|head> ..."
_FIELDS = ["id", "ts", "actor", "action", "subject", "status", "approved_by"]


def _short(h: str | None) -> str:
    return (h or "").split(":")[-1][:12] if h else ""


def _matches(rec: dict, args) -> bool:
    if args.actor and args.actor not in (rec.get("actor") or ""):
        return False
    if args.action and rec.get("action") != args.action:
        return False
    if args.status and rec.get("status") != args.status:
        return False
    if args.since and (rec.get("ts") or "") < args.since:
        return False
    return True


def _flat(rec: dict) -> dict:
    return {
        "id": rec["id"], "ts": rec["ts"], "actor": rec["actor"], "action": rec["action"],
        "subject": rec["subject"], "status": rec["status"], "approved_by": rec["approved_by"],
        "proposed_hash": (rec.get("proposed") or {}).get("body_hash"),
        "result_hash": (rec.get("result") or {}).get("diff_hash"),
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(_USAGE, file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(prog="ess-orrery audit")
    sub = parser.add_subparsers(dest="action_cmd")

    p_list = sub.add_parser("list", help="list records (newest actions last)")
    p_list.add_argument("--actor"); p_list.add_argument("--action")
    p_list.add_argument("--status"); p_list.add_argument("--since", help="ISO time/date lower bound")
    p_list.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="show one record with its proposal and diff")
    p_show.add_argument("id", help="a record id or a unique prefix of it")
    p_show.add_argument("--json", action="store_true")

    p_ver = sub.add_parser("verify", help="re-check the chain and content-addresses (exit non-zero on a break)")
    p_ver.add_argument("--expect-head", default=None,
                       help="a head self-hash the tail must still contain (else a truncated tail is a break); "
                            "default: the ORRERY_AUDIT_ANCHOR sink if set")

    p_exp = sub.add_parser("export", help="export the whole trail")
    p_exp.add_argument("--format", choices=["csv", "json"], default="json")

    p_head = sub.add_parser("head", help="print the current head (seq + self) to capture in an external anchor")
    p_head.add_argument("--json", action="store_true")

    p_rec = sub.add_parser("record", help="append a record (for a caller that is not python, e.g. a sprig)")
    p_rec.add_argument("--action", required=True)
    p_rec.add_argument("--subject", required=True)
    p_rec.add_argument("--actor", default="operator")
    p_rec.add_argument("--proposed", default="", help="the plan (default: a summary from action+subject)")
    p_rec.add_argument("--approved-by", default=None)
    p_rec.add_argument("--result", default=None, help="the resulting diff/outcome")
    p_rec.add_argument("--status", default="applied")

    args = parser.parse_args(argv)
    store = AuditStore()

    if args.action_cmd == "list":
        recs = [r for r in store.records() if _matches(r, args)]
        if args.json:
            print(json.dumps(recs, indent=2))
            return 0
        if not recs:
            print("no records")
            return 0
        print(f"{'id':<14}{'when':<21}{'actor':<18}{'action':<12}{'status':<11}subject")
        for r in recs:
            print(f"{_short(r['id']):<14}{(r['ts'] or ''):<21}{(r['actor'] or ''):<18}"
                  f"{(r['action'] or ''):<12}{(r['status'] or ''):<11}{r['subject'] or ''}")
        return 0

    if args.action_cmd == "show":
        matches = [r for r in store.records()
                   if r["id"] == args.id or r["id"].split(":")[-1].startswith(args.id)]
        if not matches:
            print(f"no record matching {args.id!r}", file=sys.stderr)
            return 1
        if len(matches) > 1:
            print(f"{args.id!r} is ambiguous ({len(matches)} records); use a longer prefix", file=sys.stderr)
            return 2
        rec = matches[0]
        if args.json:
            print(json.dumps(rec, indent=2))
            return 0
        for k in _FIELDS:
            print(f"{k:<12}: {rec[k]}")
        body = store.cas.fetch((rec.get("proposed") or {}).get("body_hash") or "")
        print("\n--- proposed ---")
        print(body.decode("utf-8", "replace") if body else "(body unavailable)")
        dh = (rec.get("result") or {}).get("diff_hash")
        if dh:
            diff = store.cas.fetch(dh)
            print("\n--- result diff ---")
            print(diff.decode("utf-8", "replace") if diff else "(diff unavailable)")
        return 0

    if args.action_cmd == "record":
        from .record import PlanRecord

        proposed = args.proposed or f"{args.action}: {args.subject}"
        rec = PlanRecord.propose(args.action, args.subject, proposed, args.actor, store=store)
        if args.approved_by:
            rec.approve(args.approved_by)
        if args.result is not None:
            rec.record_result(args.result, status=args.status)
        print(rec.id.split(":")[-1][:12])
        return 0

    if args.action_cmd == "verify":
        ok, msg = store.verify(expect_head=args.expect_head)
        print(f"audit: {msg}")
        return 0 if ok else 1

    if args.action_cmd == "export":
        recs = store.records()
        if args.format == "json":
            print(json.dumps([_flat(r) for r in recs], indent=2))
        else:
            buf = io.StringIO()
            cols = ["id", "ts", "actor", "action", "subject", "status", "approved_by",
                    "proposed_hash", "result_hash"]
            w = csv.DictWriter(buf, fieldnames=cols)
            w.writeheader()
            for r in recs:
                w.writerow(_flat(r))
            sys.stdout.write(buf.getvalue())
        return 0

    if args.action_cmd == "head":
        h = store.head()
        anchored = store.expected_head()
        if args.json:
            print(json.dumps({"head": h, "anchored": anchored,
                              "anchor": str(store.anchor) if store.anchor else None}, indent=2))
            return 0
        if h is None:
            print("audit: no records yet (no head)")
            return 0
        print(f"head   : seq {h['seq']}  {h['self']}")
        print(f"short  : {_short(h['self'])}")
        if store.anchor is not None:
            state = "matches" if anchored == h["self"] else ("ahead of anchor" if anchored else "anchor empty")
            print(f"anchor : {store.anchor}  ({state})")
        else:
            print("anchor : none set (ORRERY_AUDIT_ANCHOR unset); a truncated tail would not be detected")
        return 0

    print(_USAGE, file=sys.stderr)
    return 2
