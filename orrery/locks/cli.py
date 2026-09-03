"""CLI: ess-orrery lock <capture|probe|add> [args]

The authoring side of behavior locks. `capture` records a green run as a lock's golden
(the "it works, lock it in" move); `probe` writes the results file the gate reads; `add`
declares a lock and captures it in one step. All operate on a repo's `orrery-locks.toml`,
defaulting to one in the current directory. Report their work and exit non-zero when a
capture could not be made, so a pipeline or a human notices a lock that did not take.
"""

from __future__ import annotations

import argparse
import sys

from . import commands
from .manifest import MANIFEST_NAME

_USAGE = "ess-orrery lock <capture|probe|add|gate> [args]"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery lock")
    # `--manifest` lives on a shared PARENT attached to each subcommand, not on the top
    # level: with subparsers, argparse would demand a top-level optional BEFORE the
    # subcommand (`lock -m PATH capture`), which is the wrong way round for the caller.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-m", "--manifest", default=MANIFEST_NAME,
        help=f"path to the lock manifest (default: ./{MANIFEST_NAME})",
    )
    sub = parser.add_subparsers(dest="action")

    cap = sub.add_parser("capture", parents=[common], help="run a lock's command and record its golden")
    cap.add_argument("id", nargs="?", help="capture only this lock id (default: all)")

    sub.add_parser("probe", parents=[common], help="run all locks and write the results file for the gate")
    sub.add_parser("gate", parents=[common], help="probe + adjudicate all locks; exit non-zero on any regression (the CI gate)")

    added = sub.add_parser("add", parents=[common], help="declare a lock and capture its golden in one step")
    added.add_argument("id", help="stable lock id")
    added.add_argument("--command", required=True, help="command that prints ONE canonical line")
    added.add_argument("--why", required=True, help="the incident or decision that earned this lock")
    added.add_argument("--capture", default="stdout-line", help="how to read the output (default: stdout-line)")

    args = parser.parse_args(argv)

    if args.action == "capture":
        code, messages = commands.capture(args.manifest, only_id=args.id)
    elif args.action == "probe":
        code, messages = commands.probe(args.manifest)
    elif args.action == "gate":
        code, messages = commands.gate(args.manifest)
    elif args.action == "add":
        code, messages = commands.add(args.manifest, args.id, args.command, args.why, args.capture)
    else:
        print(_USAGE, file=sys.stderr)
        return 2

    stream = sys.stdout if code == 0 else sys.stderr
    for line in messages:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
