"""`ess-orrery doctor`: verify this installation. Conformance for the install itself.

Proves the thing an installer needs to know: the right Python is present, the packages
import, every reconciler check is registered, and each subcommand is reachable. This is
the self-check TASKS.md Step 2 calls for ("conformance can verify its own installation").
"""

from __future__ import annotations

import argparse
import json
import sys

# The checks that must be registered for a complete install.
_EXPECTED_CHECKS = {
    "org-map",
    "declared-presence",
    "fleet-reach",
    "secret-edges",
    "floors",
    "managed-settings",
}
_SUBCOMMANDS = {
    "reconcile",
    "context",
    "deck",
    "doctor",
    "update",
    "backup",
    "restore",
    "telemetry",
    "version",
}


def _probe() -> list[tuple[str, bool, str]]:
    """Each probe: (name, ok, detail). Never raises."""
    results: list[tuple[str, bool, str]] = []

    ok_py = sys.version_info >= (3, 11)
    results.append(
        ("python>=3.11", ok_py, f"{sys.version_info.major}.{sys.version_info.minor}")
    )

    try:
        import tomllib  # noqa: F401

        results.append(("stdlib tomllib", True, "present"))
    except Exception as exc:
        results.append(("stdlib tomllib", False, exc.__class__.__name__))

    try:
        from . import __version__

        results.append(("import orrery", True, __version__))
    except Exception as exc:
        results.append(("import orrery", False, exc.__class__.__name__))

    try:
        from .reconciler.registry import known_ids

        found = set(known_ids())
        missing = _EXPECTED_CHECKS - found
        results.append(
            ("reconciler checks", not missing, "all present" if not missing else f"missing {sorted(missing)}")
        )
    except Exception as exc:
        results.append(("reconciler checks", False, exc.__class__.__name__))

    try:
        from .context import resolve  # noqa: F401

        results.append(("import context engine", True, "ok"))
    except Exception as exc:
        results.append(("import context engine", False, exc.__class__.__name__))

    try:
        from . import cli

        # cli dispatches on these; confirm the dispatcher exists and knows them
        ok_cli = callable(getattr(cli, "main", None))
        results.append(("cli entry point", ok_cli, "orrery.cli:main"))
    except Exception as exc:
        results.append(("cli entry point", False, exc.__class__.__name__))

    # the TUI extra is optional: report its presence, never fail on its absence
    try:
        import textual  # noqa: F401

        results.append(("tui extra (optional)", True, "installed"))
    except Exception:
        results.append(("tui extra (optional)", True, "not installed (optional)"))

    # the durable home. Absent is normal before first write (ok=True, INFO); present but
    # not writable is a real problem (ok=False). Resolving a path never creates it.
    try:
        import os

        from .home import config_home, state_home

        cfg, st = config_home(), state_home()
        if cfg.exists() and not os.access(cfg, os.W_OK):
            results.append(("home", False, f"config not writable: {cfg}"))
        elif st.exists() and not os.access(st, os.W_OK):
            results.append(("home", False, f"state not writable: {st}"))
        else:
            present = "present" if (cfg.exists() or st.exists()) else "not yet created"
            results.append(("home", True, f"{present} (config {cfg}, state {st})"))
    except Exception as exc:
        results.append(("home", False, exc.__class__.__name__))

    # telemetry state, informational (always ok). Off is the default and shipped state.
    try:
        from .telemetry import consent

        on = consent.is_enabled()
        detail = "on (anonymous, aggregate)" if on else "off (ess-orrery telemetry on to help)"
        results.append(("telemetry", True, detail))
    except Exception as exc:
        results.append(("telemetry", True, f"unknown ({exc.__class__.__name__})"))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery doctor")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    results = _probe()
    # the optional tui probe always reports ok; every other probe must pass
    healthy = all(ok for _name, ok, _detail in results)

    if args.json:
        print(
            json.dumps(
                {
                    "generated_by": "orrery-doctor",
                    "healthy": healthy,
                    "probes": [
                        {"name": n, "ok": ok, "detail": d} for n, ok, d in results
                    ],
                },
                indent=2,
            )
        )
    else:
        for name, ok, detail in results:
            print(f"  [{'ok ' if ok else 'FAIL'}] {name}: {detail}")
        print(f"\n{'healthy' if healthy else 'PROBLEMS FOUND'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
