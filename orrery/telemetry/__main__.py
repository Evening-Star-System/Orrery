"""`ess-orrery telemetry status|on|off|flush`.

status (the default) shows the current state and prints the exact object a send would
contain, so a user sees precisely what would leave before consenting. on records consent
and mints an anonymous id; off revokes consent and deletes the id; flush sends any queued
counts now (a no-op if there is no endpoint or nothing queued).
"""

from __future__ import annotations

import argparse
import json

from . import consent, counters, payload, sink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery telemetry")
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "on", "off", "flush"],
        help="status (default), on, off, or flush",
    )
    args = parser.parse_args(argv)

    if args.action == "on":
        install_id = consent.enable()
        print(f"telemetry ON. anonymous id: {install_id}")
        print(
            "it sends only anonymous, aggregate data. run 'ess-orrery telemetry status' to "
            "see the exact payload. nothing is sent until a collector endpoint is set."
        )
        return 0

    if args.action == "off":
        consent.disable()
        print("telemetry OFF. the anonymous id has been deleted.")
        return 0

    if args.action == "flush":
        if not consent.is_enabled():
            print("telemetry is off; nothing to send.")
            return 0
        ok = sink.flush()
        print(
            "flushed."
            if ok
            else "nothing sent (no endpoint configured, nothing queued, or the send failed)."
        )
        return 0

    # status
    enabled = consent.is_enabled()
    print(f"telemetry: {'ON' if enabled else 'OFF (default)'}")
    print(f"anonymous id: {consent.install_id() or '(none)'}")
    print(f"endpoint: {consent.endpoint() or '(none set; nothing can be sent)'}")
    print("exactly what a send would contain, and nothing else can be added:")
    print(json.dumps(payload.build(counters.snapshot()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
