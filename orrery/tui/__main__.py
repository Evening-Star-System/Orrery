"""python -m orrery.tui --profile P --context-config C [--cwd D]

Launches the Orrery deck. Profile and context-config paths are operator-supplied
(never baked in); missing ones just render a hint in their panel.
"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery deck")
    parser.add_argument("--profile", default=None, help="reconciler profile TOML")
    parser.add_argument("--context-config", default=None, help="context config TOML")
    parser.add_argument("--cwd", default=None, help="working dir for context scope")
    args = parser.parse_args(argv)

    try:
        from .app import OrreryApp
    except ModuleNotFoundError as exc:  # the 'tui' extra (Textual) is not installed
        missing = getattr(exc, "name", "textual")
        print(
            f"the deck needs the 'tui' extra ({missing} not installed). "
            "install with: pip install 'ess-orrery[tui]'",
            file=sys.stderr,
        )
        return 2

    app = OrreryApp(
        profile=args.profile,
        context_config=args.context_config,
        cwd=os.path.abspath(args.cwd or os.getcwd()),
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
