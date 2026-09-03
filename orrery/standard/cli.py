"""CLI: ess-orrery standard <detect|render-ci>

detect <dir>                       print the stack detected for a project
render-ci <dir> --host <h> [--stack S]   render the project's CI file (woodpecker|github) to stdout

The renderer reads only the stack profile, so the CI a project gets is reproducible: re-run it and
the same stack yields the same pipeline, on either host, with the same four beats.
"""
from __future__ import annotations

import argparse
import sys

from .profiles import detect, load_profiles, resolve
from .render import render_ci

_USAGE = "ess-orrery standard <detect|render-ci> ..."


def main(argv: list[str]) -> int:
    if not argv:
        print(_USAGE, file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]

    if cmd == "detect":
        d = rest[0] if rest else "."
        print(detect(d))
        return 0

    if cmd == "render-ci":
        parser = argparse.ArgumentParser(prog="ess-orrery standard render-ci")
        parser.add_argument("project_dir", nargs="?", default=".")
        parser.add_argument("--host", required=True, choices=["woodpecker", "github"],
                            help="the CI host to render for")
        parser.add_argument("--stack", default="auto",
                            help="force a stack (default: auto-detect from the project)")
        args = parser.parse_args(rest)

        profiles = load_profiles()
        stack = detect(args.project_dir, profiles) if args.stack == "auto" else args.stack
        cfg = resolve(stack, profiles)
        if not cfg:
            print(f"standard: unknown stack {stack!r}", file=sys.stderr)
            return 2
        sys.stdout.write(render_ci(cfg, args.host))
        return 0

    print(_USAGE, file=sys.stderr)
    return 2
