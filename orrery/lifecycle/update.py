"""`ess-orrery update`: upgrade the installed code in place, never touching the user's setup.

Because a user's setup lives in the durable home (orrery.home), outside the installed
package, an upgrade cannot wipe it: this command only ever asks the package manager to
replace the `ess-orrery` distribution. The install method is detected read-only. The single
outbound call in this whole feature is `--check`, which reads the latest published version
on demand; there is no automatic or background check (that keeps "no phone-home by default"
true, and richer reporting is the separate opt-in-telemetry feature).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .. import __version__

# The PUBLISHED distribution name (what `pip`/`pipx` install and what PyPI serves), also the
# console-command name. Single source of truth for the version check and the upgrade command.
# The PyPI name "orrery" is owned by an unrelated project, so we publish as "ess-orrery" and
# the command is `ess-orrery`. The import PACKAGE stays "orrery" (internal), unaffected.
_DIST = "ess-orrery"
_PYPI_JSON = f"https://pypi.org/pypi/{_DIST}/json"


def _package_dir() -> Path:
    # orrery/lifecycle/update.py -> orrery/  (the installed package directory)
    return Path(__file__).resolve().parents[1]


def detect_install() -> str:
    """Return 'dev', 'pipx', or 'pip'. Read-only, best-effort, never raises."""
    pkg = _package_dir()
    container = pkg.parent  # repo root, a pipx venv's site-packages, or plain site-packages
    if (container / "pyproject.toml").exists() and (container / ".git").exists():
        return "dev"  # running from a source checkout (incl. `pip install -e`)
    posix = str(pkg).replace(os.sep, "/")
    if "/pipx/venvs/" in posix or "/pipx/" in posix:
        return "pipx"
    return "pip"


def build_upgrade_cmd(kind: str) -> list[str] | None:
    """The exact argv to run for an in-place upgrade, or None for a dev checkout."""
    if kind == "dev":
        return None
    if kind == "pipx":
        return ["pipx", "upgrade", _DIST]
    return [sys.executable, "-m", "pip", "install", "--upgrade", _DIST]


def latest_version(timeout: float = 4.0) -> str | None:
    """Read the latest published version on demand. None on any failure. Caches the result."""
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(_PYPI_JSON, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        version = (data.get("info") or {}).get("version")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if version:
        _cache_check(str(version))
    return version


def _cache_check(latest: str) -> None:
    import json
    import time

    from ..home import ensure_dir, state_home

    try:
        ensure_dir(state_home())
        (state_home() / "update-check.json").write_text(
            json.dumps({"latest": latest, "checked_at": int(time.time())}),
            encoding="utf-8",
        )
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery update")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report the running version against the latest, and change nothing",
    )
    args = parser.parse_args(argv)
    kind = detect_install()

    if args.check:
        latest = latest_version()
        print(f"installed: ess-orrery {__version__}  (install method: {kind})")
        if latest is None:
            print("latest:    could not determine (no network or not published yet)")
            return 0
        if latest == __version__:
            print(f"latest:    ess-orrery {latest}  (up to date)")
        else:
            print(f"latest:    ess-orrery {latest}  (run 'ess-orrery update' to upgrade)")
        return 0

    if kind == "dev":
        print(
            "this is a source checkout, not a packaged install; not auto-upgrading.\n"
            f"update it with git in {_package_dir().parent}:  git pull",
            file=sys.stderr,
        )
        return 0

    cmd = build_upgrade_cmd(kind)
    assert cmd is not None  # only dev returns None, handled above
    print("running:", " ".join(cmd))
    try:
        return subprocess.call(cmd)
    except OSError as exc:
        print(f"upgrade command failed to start: {exc}", file=sys.stderr)
        return 1
