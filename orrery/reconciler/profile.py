"""Load a declared-shape profile (TOML) into check configs.

A profile names the box and lists checks by id, each with its own options. Enabling
a check or pointing it at a different source is a profile edit, not a code change.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CheckConfig:
    id: str
    options: dict[str, Any]


@dataclass
class Profile:
    box: str
    checks: list[CheckConfig]


def load_profile(path: str | Path) -> Profile:
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    # Adoption by reference: fold any rulesets this profile names into its checks, resolving
    # their paths relative to the profile. A profile that references none is unchanged.
    from .ruleset import apply_rulesets

    data = apply_rulesets(data, path.parent)
    return load_profile_data(data)


def load_profile_data(data: dict) -> Profile:
    box = data.get("box")
    if not box:
        raise ValueError("profile is missing the required key: box")
    checks: list[CheckConfig] = []
    for raw in data.get("checks", []):
        cid = raw.get("id")
        if not cid:
            raise ValueError("every [[checks]] entry needs an id")
        options = {k: v for k, v in raw.items() if k != "id"}
        checks.append(CheckConfig(id=cid, options=options))
    return Profile(box=str(box), checks=checks)
