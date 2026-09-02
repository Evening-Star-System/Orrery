"""CLI: ess-orrery profile validate PATH [--json]

Checks a profile's shape against the registry before you rely on it. Exit 0 when the
profile is sound (no errors), 2 when it has at least one error (a check that would run
nothing, a missing box, or invalid TOML). Report-only: reads the profile, changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys

from .registry import known_ids, option_schemas
from .validate import ERROR, validate_profile

_USAGE = "ess-orrery profile validate PATH [--json]"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery profile")
    sub = parser.add_subparsers(dest="action")
    v = sub.add_parser("validate", help="check a profile's shape")
    v.add_argument("path", help="path to a TOML profile")
    v.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action != "validate":
        print(_USAGE, file=sys.stderr)
        return 2

    issues = validate_profile(args.path, known_ids(), option_schemas())
    has_error = any(i.level == ERROR for i in issues)

    if args.json:
        payload = {
            "generated_by": "orrery-reconciler",
            "profile": args.path,
            "ok": not has_error,
            "issues": [{"level": i.level, "location": i.location, "message": i.message} for i in issues],
        }
        print(json.dumps(payload, indent=2))
    else:
        if not issues:
            print(f"{args.path}: valid ({len(known_ids())} checks known)")
        else:
            for i in issues:
                print(f"{i.level.upper():5} {i.location}: {i.message}")
            print(f"\n{_summary(issues)}")

    return 2 if has_error else 0


def _summary(issues: list) -> str:
    counts: dict[str, int] = {}
    for i in issues:
        counts[i.level] = counts.get(i.level, 0) + 1
    parts = [f"{n} {level}" for level, n in counts.items()]
    return ", ".join(parts)
