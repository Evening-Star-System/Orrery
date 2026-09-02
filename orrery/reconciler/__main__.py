"""CLI: python -m orrery.reconciler --profile PATH [--ssh HOST] [--format human|json|prometheus] [--check ID] [--strict]

Exit 0 when the box is clean (worst finding at or below INFO), 1 on drift or worse.
Report-only: this never changes the box. With --ssh, measures a remote host read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib

from .box import SshBox
from .engine import run_profile
from .report import render_human, render_json, render_prometheus, render_prometheus_error

# Exit codes: 0 clean, 1 drift-or-worse, 2 the profile itself could not be loaded.
EXIT_PROFILE_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery reconcile")
    parser.add_argument("--profile", required=True, help="path to a TOML profile")
    parser.add_argument("--ssh", metavar="HOST", help="measure a remote host (ssh alias) read-only")
    parser.add_argument(
        "--format",
        choices=["human", "json", "prometheus"],
        default="human",
        help="output format (human, json, or prometheus for Grafana)",
    )
    parser.add_argument("--json", action="store_true", help="alias for --format json")
    parser.add_argument("--check", metavar="ID", help="run only this check id")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="refuse to run if the profile has shape errors (a typo'd check id runs nothing)",
    )
    parser.add_argument(
        "--enforce",
        choices=["gate", "report"],
        default="gate",
        help="how to act on the verdict: gate (exit non-zero on drift, the default) or report "
        "(emit findings, always exit 0)",
    )
    args = parser.parse_args(argv)

    fmt = "json" if args.json else args.format
    box = SshBox(args.ssh) if args.ssh else None

    # Default runs are resilient: an unknown check id degrades to a WARN and the rest still
    # run. --strict is for CI, where a profile that silently checks less than it claims should
    # fail the pipeline instead. Report-only either way; this only decides whether to start.
    if args.strict:
        from .registry import known_ids, option_schemas
        from .validate import ERROR, validate_profile

        errors = [
            i
            for i in validate_profile(args.profile, known_ids(), option_schemas())
            if i.level == ERROR
        ]
        if errors:
            lines = [f"{i.location}: {i.message}" for i in errors]
            if fmt == "json":
                print(
                    json.dumps(
                        {"generated_by": "orrery-reconciler", "error": "invalid profile", "issues": lines},
                        indent=2,
                    )
                )
            elif fmt == "prometheus":
                print(render_prometheus_error(), end="")
            else:
                print("invalid profile (--strict):", file=sys.stderr)
                for ln in lines:
                    print(f"  {ln}", file=sys.stderr)
            return EXIT_PROFILE_ERROR

    # The profile is the most hand-edited input, so a typo must produce the tool's own
    # clean, scriptable output, not a raw traceback (same contract the checks honor).
    try:
        result = run_profile(args.profile, box=box, only=args.check)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        message = f"profile error: {exc}"
        if fmt == "json":
            print(json.dumps({"generated_by": "orrery-reconciler", "error": message}, indent=2))
        elif fmt == "prometheus":
            # still emit something scrapeable so a dashboard shows the reconcile is down
            print(render_prometheus_error(), end="")
        else:
            print(message, file=sys.stderr)
        return EXIT_PROFILE_ERROR

    # The Enforcer seam: the verdict is produced above; how to ACT on it (block or observe)
    # is the enforcer's call. Default `gate` returns result.exit_code, so this is a no-op for
    # every existing caller; `report` always exits 0 for a monitor that wants the signal only.
    # Decide the exit before rendering so the human summary reports the action, not the verdict.
    from ..enforce.builtin import get_enforcer

    exit_code = get_enforcer(args.enforce).act(result)

    if fmt == "json":
        print(render_json(result))
    elif fmt == "prometheus":
        import time

        print(render_prometheus(result, time.time()), end="")
    else:
        print(render_human(result, exit_code))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
