"""CLI: ess-orrery protect <path> [--why WHY]

Record a file's exact bytes in the content-addressed store and print the profile stanza that
declares it protected. Declare-and-record together: after this, the `content-address` check proves
the file stays byte-exact, and the recorded bytes are what a later `recover` restores.
"""

from __future__ import annotations

import argparse
import os
import sys

from .store import Store


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery protect")
    parser.add_argument("path", help="the file to protect")
    parser.add_argument("--why", default="", help="why this artifact is protected (the incident or decision)")
    parser.add_argument("--store", default=None, help="content-addressed store root (default: the state home's cas/)")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.path):
        print(f"protect: not a readable file: {args.path}", file=sys.stderr)
        return 2

    try:
        digest = Store(args.store).record_path(args.path)
    except OSError as exc:
        print(f"protect: could not record {args.path} ({exc.__class__.__name__})", file=sys.stderr)
        return 3

    abspath = os.path.abspath(args.path)
    print(f"recorded {abspath}")
    print(f"  sha256:{digest}")
    print("\nadd this to the content-address check in your profile:\n")
    print("  [[checks.artifacts]]")
    print(f'  path = "{abspath}"')
    print(f'  hash = "sha256:{digest}"')
    print(f'  why  = "{args.why}"' if args.why else '  why  = ""')
    return 0
