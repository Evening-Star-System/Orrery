"""A ruleset: a named, versioned bundle of rules an org declares once and many profiles adopt.

A ruleset is a profile FRAGMENT, not a new artifact: `name` + `version` + the same `[[checks]]`
a profile already declares, each carrying a plain-language `why` (the incident or decision that
earned the rule). A profile ADOPTS a ruleset by reference (`[[rulesets]]` with a path and an
optional version `pin`); at load time the ruleset's rules merge into the profile, so the canon
flows to every adopter without being re-authored, and a project can override a single canon rule
by declaring a check with the same id locally.

The `why` is metadata: documentation for a human and promotion memory that travels with the rule.
It is stripped before a check runs, so it never becomes a check option. Everything here operates
on plain dicts and TOML, legible to a human reading the file and to a machine parsing it.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Ruleset:
    name: str
    version: str
    checks: list[dict]      # [[checks]]: rules the RECONCILER enforces (id + options + optional why)
    principles: list[dict]  # [[principles]]: conduct rules enforced at the hook/agent/review layer


def load_ruleset(path: str | Path) -> Ruleset:
    """Load and shape-check a ruleset file. Raises ValueError with the path on a missing name or
    version, a check with no id, or a principle with no id or statement.

    A canon holds two kinds of rule, matching the two places a rule is enforced. `[[checks]]` are
    machine rules the reconciler adjudicates and a profile can adopt. `[[principles]]` are conduct
    rules (the ethos and the hard nos) enforced below the model by hooks, agent runtime, or human
    review, not by the reconciler; each states the rule, why it exists, and optionally how it is
    enforced. Both travel together as the canon."""
    p = Path(path)
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    name = data.get("name")
    version = data.get("version")
    if not name:
        raise ValueError(f"ruleset {p} is missing the required key: name")
    if version is None or str(version) == "":
        raise ValueError(f"ruleset {p} is missing the required key: version")
    checks = data.get("checks", [])
    for raw in checks:
        if not raw.get("id"):
            raise ValueError(f"ruleset {name} ({p}): every [[checks]] rule needs an id")
    principles = data.get("principles", [])
    for raw in principles:
        if not raw.get("id"):
            raise ValueError(f"ruleset {name} ({p}): every [[principles]] rule needs an id")
        if not str(raw.get("statement", "")).strip():
            raise ValueError(f"ruleset {name} ({p}): principle {raw.get('id')!r} needs a statement")
    return Ruleset(name=str(name), version=str(version), checks=list(checks), principles=list(principles))


def apply_rulesets(data: dict, base_dir: Path) -> dict:
    """Merge any rulesets a profile references into its checks, and return the resolved profile
    data. Canon rules come first (in reference order), then the profile's own checks, deduped by
    check id so a local check OVERRIDES a canon rule of the same id. A `pin` that does not match
    the ruleset's version fails loudly, so a canon bump is deliberate and visible. If the profile
    references no rulesets, the data is returned unchanged."""
    refs = data.get("rulesets")
    if not refs:
        return data

    canon: list[dict] = []
    for ref in refs:
        rel = ref if isinstance(ref, str) else ref.get("path")
        pin = None if isinstance(ref, str) else ref.get("pin")
        if not rel:
            raise ValueError("every [[rulesets]] entry needs a path")
        rpath = Path(rel) if os.path.isabs(rel) else (base_dir / rel)
        ruleset = load_ruleset(rpath)
        if pin is not None and str(pin) != ruleset.version:
            raise ValueError(
                f"ruleset {ruleset.name} is pinned to {pin} but {rpath} is version {ruleset.version}; "
                "bump the pin deliberately to adopt the change"
            )
        for rule in ruleset.checks:
            canon.append({k: v for k, v in rule.items() if k != "why"})  # why is metadata, not an option

    # Dedup by check id: last wins, so the profile's own checks override canon rules of the same id.
    merged: dict = {}
    for chk in canon + list(data.get("checks", [])):
        cid = chk.get("id")
        key = cid if cid is not None else ("__no_id__", id(chk))  # keep id-less entries distinct
        merged[key] = chk

    out = dict(data)
    out["checks"] = list(merged.values())
    out.pop("rulesets", None)
    return out
