"""The `ess-orrery` command: one entry point dispatching to the subsystems.

Thin by design. Each subcommand hands the remaining argv to an existing module main,
so the CLI adds no logic of its own. `deck` imports Textual lazily so the core install
(no TUI extra) still runs every other command.
"""

from __future__ import annotations

import sys

from . import __version__

# Product commands whose use is counted when telemetry is opted in. `bump` is a no-op when
# telemetry is off (the default), so these commands still write nothing on a default install.
# doctor (a diagnostic), version, telemetry, and help are intentionally not counted.
_COUNTED = {"reconcile", "context", "deck", "update", "backup", "restore", "lock", "ruleset", "protect", "recover", "standard"}

_USAGE = (
    "ess-orrery <command> [args]\n\n"
    "commands:\n"
    "  reconcile   run a reconciler profile, or a fleet with --profiles GLOB (drift report)\n"
    "  profile     validate a profile's shape before you rely on it\n"
    "  ruleset     author an org canon a profile adopts (validate, describe)\n"
    "  lock        author behavior locks (capture a golden, probe, add)\n"
    "  standard    detect a project's stack and render its canonical CI (the operating standard)\n"
    "  protect     record a file's content-address so integrity can be verified\n"
    "  recover     restore a protected file to its recorded content-address\n"
    "  context     resolve the context for a working directory\n"
    "  deck        launch the themed terminal deck (needs the 'tui' extra)\n"
    "  doctor      verify this installation\n"
    "  update      upgrade ess-orrery in place (never touches your setup)\n"
    "  backup      write your setup to a portable archive\n"
    "  restore     restore your setup from a backup archive\n"
    "  telemetry   opt in or out of anonymous usage stats (off by default)\n"
    "  version     print the version\n"
)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_USAGE)
        return 0
    command, rest = argv[0], argv[1:]

    if command in _COUNTED:
        from .telemetry import counters

        counters.bump(command)  # no-op unless the user opted in

    if command == "version":
        print(f"ess-orrery {__version__}")
        return 0
    if command == "telemetry":
        from .telemetry.__main__ import main as telemetry_main

        return telemetry_main(rest)
    if command == "reconcile":
        from .reconciler.__main__ import main as reconcile_main

        return reconcile_main(rest)
    if command == "profile":
        from .reconciler.profile_cli import main as profile_main

        return profile_main(rest)
    if command == "ruleset":
        from .reconciler.ruleset_cli import main as ruleset_main

        return ruleset_main(rest)
    if command == "lock":
        from .locks.cli import main as lock_main

        return lock_main(rest)
    if command == "standard":
        from .standard.cli import main as standard_main

        return standard_main(rest)
    if command == "protect":
        from .integrity.cli import main as protect_main

        return protect_main(rest)
    if command == "recover":
        from .integrity.recover import main as recover_main

        return recover_main(rest)
    if command == "context":
        from .context.__main__ import main as context_main

        return context_main(rest)
    if command == "doctor":
        from .doctor import main as doctor_main

        return doctor_main(rest)
    if command == "update":
        from .lifecycle.update import main as update_main

        return update_main(rest)
    if command == "backup":
        from .lifecycle.backup import backup_main

        return backup_main(rest)
    if command == "restore":
        from .lifecycle.backup import restore_main

        return restore_main(rest)
    if command == "deck":
        try:
            from .tui.__main__ import main as deck_main
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", "textual")
            print(
                f"the deck needs the 'tui' extra ({missing} not installed). "
                "install with: pip install 'ess-orrery[tui]'",
                file=sys.stderr,
            )
            return 2
        return deck_main(rest)

    print(f"unknown command: {command}\n\n{_USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
