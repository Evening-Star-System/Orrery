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


def _toml_str(value: str) -> str:
    out = ['"']
    for ch in str(value):
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def promote_text(profile_text: str, canon_path: str | Path, profile_path: str | Path, version: str | None = None):
    """Return (new_profile_text, action) for adopting or bumping a `[[rulesets]]` reference to
    `canon_path` in the profile at `profile_path`, pinned to `version` (default: the canon's current
    version). action is 'adopt' (a new reference added), 'bump' (an existing pin updated), or 'noop'
    (already at that version). Promotion moves a rule reference; it enforces nothing."""
    ruleset = load_ruleset(canon_path)
    ver = str(version) if version else ruleset.version
    profile_dir = os.path.dirname(os.path.abspath(str(profile_path)))
    canon_abs = os.path.abspath(str(canon_path))
    rel = os.path.relpath(canon_abs, profile_dir)

    data = tomllib.loads(profile_text) if profile_text.strip() else {}
    for ref in data.get("rulesets", []) or []:
        rp = ref if isinstance(ref, str) else ref.get("path", "")
        if not rp:
            continue
        ref_abs = rp if os.path.isabs(rp) else os.path.abspath(os.path.join(profile_dir, rp))
        if ref_abs == canon_abs:
            current_pin = None if isinstance(ref, str) else ref.get("pin")
            if str(current_pin or "") == ver:
                return profile_text, "noop"
            return _bump_pin(profile_text, rp, ver), "bump"

    nl = "\r\n" if "\r\n" in profile_text else "\n"
    prefix = "" if (not profile_text or profile_text.endswith(("\n", "\r"))) else nl
    block = f"{nl}[[rulesets]]{nl}path = {_toml_str(rel)}{nl}pin = {_toml_str(ver)}{nl}"
    return profile_text + prefix + block, "adopt"


def _bump_pin(text: str, path_val: str, version: str) -> str:
    """Surgically set the `pin` of the `[[rulesets]]` block whose `path` equals path_val, leaving all
    other bytes and comments intact."""
    lines = text.splitlines(keepends=True)
    blocks: list[dict] = []
    cur: dict | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            if cur is not None:
                cur["end"] = i
                blocks.append(cur)
            is_rs = stripped.replace(" ", "") == "[[rulesets]]"
            cur = {"start": i, "end": len(lines), "is_rs": is_rs, "path_val": None, "path_line": None, "pin_line": None} if is_rs else None
        elif cur is not None and "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            if key == "path":
                cur["path_val"] = val.strip().strip('"').strip("'")
                cur["path_line"] = i
            elif key == "pin":
                cur["pin_line"] = i
    if cur is not None:
        blocks.append(cur)

    target = next((b for b in blocks if b["is_rs"] and b["path_val"] == path_val), None)
    if target is None:
        return text
    nl = "\r\n" if "\r\n" in text else "\n"
    pin_line = f"pin = {_toml_str(version)}{nl}"
    if target["pin_line"] is not None:
        indent = lines[target["pin_line"]][: len(lines[target["pin_line"]]) - len(lines[target["pin_line"]].lstrip())]
        lines[target["pin_line"]] = indent + pin_line
    else:
        lines.insert(target["path_line"] + 1, pin_line)
    return "".join(lines)
