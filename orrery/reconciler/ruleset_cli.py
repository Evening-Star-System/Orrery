"""CLI: ess-orrery ruleset <validate|describe> PATH [--json]

Author and read an org's canon. `validate` shape-checks a ruleset against the registry (known
check ids, a why on each rule) the same value-blind way `profile validate` does. `describe`
prints the canon so a human can read it top to bottom, or emits JSON for a machine. Both speak
to human and machine, which is a first-class requirement for a shared ruleset.
"""

from __future__ import annotations

import argparse
import json
import sys

from .registry import known_ids
from .ruleset import load_ruleset

_USAGE = "ess-orrery ruleset <validate|describe> PATH [--json]"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery ruleset")
    sub = parser.add_subparsers(dest="action")
    for name in ("validate", "describe"):
        s = sub.add_parser(name)
        s.add_argument("path", help="path to a ruleset TOML file")
        s.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action == "validate":
        return _validate(args.path, args.json)
    if args.action == "describe":
        return _describe(args.path, args.json)
    print(_USAGE, file=sys.stderr)
    return 2


def _load(path: str):
    try:
        return load_ruleset(path), None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def _validate(path: str, as_json: bool) -> int:
    ruleset, error = _load(path)
    issues: list[dict] = []
    if error:
        issues.append({"level": "error", "message": error})
    else:
        known = known_ids()
        for rule in ruleset.checks:
            cid = rule.get("id")
            if cid not in known:
                issues.append({"level": "error", "message": f"check rule uses unknown check id {cid!r}"})
            if not str(rule.get("why", "")).strip():
                issues.append({"level": "warn", "message": f"check rule {cid!r} has no why (record why it exists)"})
        for principle in ruleset.principles:
            if not str(principle.get("why", "")).strip():
                pid = principle.get("id")
                issues.append({"level": "warn", "message": f"principle {pid!r} has no why (record why it exists)"})

    has_error = any(i["level"] == "error" for i in issues)
    if as_json:
        print(json.dumps({"generated_by": "orrery-ruleset", "path": path, "ok": not has_error, "issues": issues}, indent=2))
    elif not issues:
        n = len(ruleset.principles) + len(ruleset.checks)
        print(f"{path}: valid ({ruleset.name} v{ruleset.version}, {len(ruleset.principles)} principle(s), {len(ruleset.checks)} check(s), {n} rule(s))")
    else:
        for i in issues:
            print(f"{i['level'].upper():5} {i['message']}")
    return 2 if has_error else 0


def _describe(path: str, as_json: bool) -> int:
    ruleset, error = _load(path)
    if error:
        print(error, file=sys.stderr)
        return 2
    principles = [
        {
            "id": p.get("id"),
            "statement": str(p.get("statement", "")).strip(),
            "why": str(p.get("why", "")).strip(),
            "enforced_by": str(p.get("enforced_by", "")).strip(),
        }
        for p in ruleset.principles
    ]
    checks = [{"id": c.get("id"), "why": str(c.get("why", "")).strip()} for c in ruleset.checks]
    if as_json:
        print(json.dumps({"name": ruleset.name, "version": ruleset.version, "principles": principles, "checks": checks}, indent=2))
    else:
        print(f"{ruleset.name}  v{ruleset.version}  ({len(principles)} principle(s), {len(checks)} check(s))")
        if principles:
            print("\nprinciples (enforced below the model: hooks, agent runtime, review):")
            for p in principles:
                by = f"  [{p['enforced_by']}]" if p["enforced_by"] else ""
                print(f"  - {p['id']}{by}: {p['statement']}")
                if p["why"]:
                    print(f"      why: {p['why']}")
        if checks:
            print("\nchecks (enforced by the reconciler; a profile can adopt these):")
            for c in checks:
                print(f"  - {c['id']}: {c['why'] or '(no why recorded)'}")
    return 0
