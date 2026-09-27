"""CLI: python -m orrery.context --config C [--cwd D] [--json]

Prints the context block to inject for a working directory. The SessionStart hook is
a thin client of this. Exit 2 if the config cannot be loaded (clean message, no
traceback); 0 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib

from .config import load_config
from .resolver import resolve

EXIT_CONFIG_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery context")
    parser.add_argument("--config", required=True, help="path to a TOML context config")
    parser.add_argument("--cwd", default=None, help="working dir (defaults to process cwd)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument("--consolidate", action="store_true",
                        help="read a handoff block from stdin, write it to the scoped digest head (audited)")
    parser.add_argument("--orient", action="store_true",
                        help="print the current PICKUP handoff for this scope")
    args = parser.parse_args(argv)

    cwd = os.path.abspath(args.cwd or os.getcwd())
    try:
        config = load_config(args.config)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        message = f"context config error: {exc}"
        if args.json:
            print(json.dumps({"generated_by": "orrery-context", "error": message}, indent=2))
        else:
            print(message, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if args.consolidate or args.orient:
        from .handoff import read_handoff, write_handoff
        if args.orient:
            block = read_handoff(cwd, config)
            print(block if block else "(no handoff yet)")
            return 0
        try:
            res = write_handoff(cwd, config, sys.stdin.read())
        except ValueError as exc:
            print(f"consolidate error: {exc}", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        print(json.dumps({"generated_by": "orrery-context", **res}, indent=2))
        return 0

    bundle = resolve(cwd, config)
    if args.json:
        print(
            json.dumps(
                {
                    "generated_by": "orrery-context",
                    "scope": {
                        "kind": bundle.scope.kind,
                        "bucket": bundle.scope.bucket,
                        "project": bundle.scope.project,
                    },
                    "provenance": bundle.provenance,
                    "text": bundle.text,
                },
                indent=2,
            )
        )
    else:
        print(bundle.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
