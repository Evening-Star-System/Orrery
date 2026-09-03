"""Render a project's CI file from its resolved stack profile, for either CI host.

Both hosts emit the SAME beats in the SAME order: the prove beats the stack defines (setup, lint,
test, checks), then the lock gate (always, so a declared behavior-lock is always enforced), then a
build on main only. No stack logic lives here; the beats come entirely from the profile. Every beat
is a hard gate: any non-zero exit stops the pipeline, because both hosts fail fast on a failed step.
"""
from __future__ import annotations

from .profiles import BEATS

_HEADER = (
    "# Canonical operating standard. Beats: prove (lint, test, checks, locks), gate (any failure\n"
    "# blocks the merge/deploy), build on main. Generated from stack-profiles.toml by\n"
    "# `ess-orrery standard render-ci`. The same beats run on every stack and every CI host.\n"
)

# The lock gate runs the shipped, CI-agnostic script if the repo declares locks; it no-ops cleanly
# when there is no manifest, so it is safe to include unconditionally and it hard-fails on a regression.
_LOCK_CMD = "if [ -f scripts/orrery-locks-gate.sh ]; then sh scripts/orrery-locks-gate.sh; fi"


def prove_beats(cfg: dict) -> list[tuple[str, str]]:
    """The ordered (label, command) prove beats present for this stack, plus the lock gate."""
    beats = [(b, cfg[b]) for b in BEATS if cfg.get(b)]
    beats.append(("locks", _LOCK_CMD))
    return beats


def render_woodpecker(cfg: dict) -> str:
    image = cfg.get("image", "debian:stable-slim")
    lines = [_HEADER, "when:", "  - event: [push, pull_request]", "", "steps:"]
    for label, cmd in prove_beats(cfg):
        lines += [f"  {label}:", f"    image: {image}", "    commands:", f"      - {cmd}"]
    build = cfg.get("build")
    if build:
        lines += [
            "  build:", f"    image: {image}", "    when:", "      branch: main",
            "    commands:", f"      - {build}",
        ]
    return "\n".join(lines) + "\n"


def render_github(cfg: dict, runs_on: str = "ubuntu-latest") -> str:
    image = cfg.get("image", "debian:stable-slim")
    lines = [
        _HEADER, "on:", "  push:", "    branches: [main]", "  pull_request:", "",
        "jobs:", "  prove:", f"    runs-on: {runs_on}", f"    container: {image}", "    steps:",
        "      - uses: actions/checkout@v5",
    ]
    for label, cmd in prove_beats(cfg):
        lines += [f"      - name: {label}", f"        run: {cmd}"]
    build = cfg.get("build")
    if build:
        lines += [
            "  build:", "    needs: prove", "    if: github.ref == 'refs/heads/main'",
            f"    runs-on: {runs_on}", f"    container: {image}", "    steps:",
            "      - uses: actions/checkout@v5",
            "      - name: build", f"        run: {build}",
        ]
    return "\n".join(lines) + "\n"


def render_ci(cfg: dict, host: str) -> str:
    if host == "woodpecker":
        return render_woodpecker(cfg)
    if host in ("github", "gha", "github-actions"):
        return render_github(cfg)
    raise ValueError(f"unknown CI host {host!r} (expected 'woodpecker' or 'github')")
