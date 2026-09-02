"""Reconcile a SET of profiles and roll their verdicts into one fleet verdict.

A "fleet" is nothing more specific than a set of profiles (matched by a glob). This module
COMPOSES the single-profile pieces rather than forking them: it calls `run_profile` per
profile, and the `FleetResult` it returns satisfies the same `Verdict` protocol a single
`Result` does, so the existing enforcer seam and the existing reporters act on a whole fleet
unchanged. One mechanism, many uses; no operator layout is baked in here (a caller supplies
the glob), so this stays open-core and reusable by anyone with more than one profile.

Coverage is made visible on purpose. A profile that will not load is not dropped on the
floor and it is not counted as a pass: it becomes a hole the roll-up reports, because an
unmeasured project is a gap in the fleet, not a clean one. As projects are added under the
glob the fleet grows to cover them with no code change, and any gap surfaces itself.
"""

from __future__ import annotations

import glob as _glob
import tomllib
from dataclasses import dataclass

from .box import Box
from .engine import Result, run_profile


@dataclass(frozen=True)
class ProfileRun:
    """One profile's outcome within a fleet run.

    `result` is None when the profile could not be loaded; `error` then holds why. Such a
    run is deliberately NOT clean: a project we failed to measure is a hole in coverage, not
    a passing box, and the fleet verdict must reflect that.
    """

    path: str
    result: Result | None
    error: str | None = None

    @property
    def clean(self) -> bool:
        return self.result is not None and self.result.clean

    @property
    def box(self) -> str:
        # Fall back to the path so an unloadable profile still names itself in every report.
        return self.result.box if self.result is not None else self.path


@dataclass(frozen=True)
class FleetResult:
    """The aggregate verdict over a set of profiles.

    Satisfies the `Verdict` protocol (`clean` + `exit_code`), so the SAME enforcer that acts
    on one `Result` acts on a fleet with no change. Clean only when every profile ran and
    every profile was clean; an empty fleet is not clean, because "nothing was checked" is
    not "everything passed".
    """

    runs: list[ProfileRun]

    @property
    def clean(self) -> bool:
        return bool(self.runs) and all(r.clean for r in self.runs)

    @property
    def exit_code(self) -> int:
        return 0 if self.clean else 1

    @property
    def dirty(self) -> list[ProfileRun]:
        """The runs that need attention: drift, failure, or a profile that would not load."""
        return [r for r in self.runs if not r.clean]


def matched_profiles(pattern: str) -> list[str]:
    """Every path matching the glob, sorted for a stable, reviewable order."""
    return sorted(_glob.glob(pattern))


def run_fleet(
    paths: list[str], box: Box | None = None, only: str | None = None
) -> FleetResult:
    """Reconcile each profile and aggregate. A profile that will not load becomes a reported
    hole rather than sinking the run, mirroring how the engine keeps one broken check from
    sinking a single profile."""
    runs: list[ProfileRun] = []
    for path in paths:
        try:
            result = run_profile(path, box=box, only=only)
            runs.append(ProfileRun(path=path, result=result))
        except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
            runs.append(ProfileRun(path=path, result=None, error=f"{exc.__class__.__name__}: {exc}"))
    return FleetResult(runs=runs)
