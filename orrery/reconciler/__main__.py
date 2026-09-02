"""CLI: python -m orrery.reconciler (--profile PATH | --profiles GLOB) [--ssh HOST] [--format human|json|prometheus] [--check ID] [--strict]

Exit 0 when the box is clean (worst finding at or below INFO), 1 on drift or worse.
Report-only: this never changes the box. With --ssh, measures a remote host read-only.

`--profiles GLOB` reconciles every matched profile and rolls the verdicts into one fleet
verdict: exit 0 only when every profile ran and every profile was clean. The fleet result
flows through the same enforcer seam and the same reporters as a single profile.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib

from .box import SshBox
from .engine import run_profile
from .report import (
    render_fleet_human,
    render_fleet_json,
    render_fleet_prometheus,
    render_human,
    render_json,
    render_prometheus,
    render_prometheus_error,
)

# Exit codes: 0 clean, 1 drift-or-worse, 2 the profile(s) could not be loaded / none matched.
EXIT_PROFILE_ERROR = 2


def _strict_errors(path: str) -> list[str]:
    """Shape errors that should stop a --strict run: a typo'd check id runs nothing, and in
    CI a profile that silently checks less than it claims should fail, not pass quietly."""
    from .registry import known_ids, option_schemas
    from .validate import ERROR, validate_profile

    return [
        f"{i.location}: {i.message}"
        for i in validate_profile(path, known_ids(), option_schemas())
        if i.level == ERROR
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery reconcile")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--profile", help="path to a single TOML profile")
    target.add_argument(
        "--profiles",
        metavar="GLOB",
        help="a glob matching many profiles; reconcile each and roll up into one fleet verdict",
    )
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

    if args.profiles is not None:
        return _run_fleet(args, fmt, box)

    # Default runs are resilient: an unknown check id degrades to a WARN and the rest still
    # run. --strict is for CI, where a profile that silently checks less than it claims should
    # fail the pipeline instead. Report-only either way; this only decides whether to start.
    if args.strict:
        errors = _strict_errors(args.profile)
        if errors:
            lines = errors
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


def _fleet_error(fmt: str, message: str) -> int:
    """Report a fleet that could not run at all (nothing matched, or --strict caught a bad
    profile), in the same format the run would have used."""
    if fmt == "json":
        print(json.dumps({"generated_by": "orrery-reconciler", "kind": "fleet", "error": message}, indent=2))
    elif fmt == "prometheus":
        print(render_prometheus_error(), end="")
    else:
        print(message, file=sys.stderr)
    return EXIT_PROFILE_ERROR


def _run_fleet(args, fmt: str, box) -> int:
    from ..enforce.builtin import get_enforcer
    from .fleet import matched_profiles, run_fleet

    paths = matched_profiles(args.profiles)
    if not paths:
        # An empty match is a misconfigured glob, not an all-clear. Surface it, never pass it.
        return _fleet_error(fmt, f"no profiles matched {args.profiles!r}")

    if args.strict:
        bad = [(p, errs) for p in paths if (errs := _strict_errors(p))]
        if bad:
            lines = [f"{p}: {msg}" for p, errs in bad for msg in errs]
            return _fleet_error(fmt, "invalid profile(s) (--strict):\n  " + "\n  ".join(lines))

    fleet = run_fleet(paths, box=box, only=args.check)
    exit_code = get_enforcer(args.enforce).act(fleet)

    if fmt == "json":
        print(render_fleet_json(fleet))
    elif fmt == "prometheus":
        import time

        print(render_fleet_prometheus(fleet, time.time()), end="")
    else:
        print(render_fleet_human(fleet, exit_code))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
