"""org-map: one source of truth (orgs.tsv), many consumers that re-encode it.

The bucket-to-account fact lives in orgs.tsv and is copied, in three different
encodings, into org-tool (a bash assoc-array), org-guard.py (a Python dict),
and org-lookup (a bash case function, github-only, subset of buckets). This
check reads the truth and each consumer's own encoding, and reports where they
disagree. Account comparison is case-insensitive on purpose: org-tool stores
`Globex-Inc`, org-guard stores `globex-inc`, and that difference is
intentional, not drift.
"""

from __future__ import annotations

import ast
import re

from ..box import Box
from ..model import Finding, Severity

ID = "org-map"
TITLE = "bucket-to-account map agrees across all consumers"

# A bucket -> (host, account). host may be None when a consumer does not encode it.
OrgMap = dict[str, "tuple[str | None, str]"]


def _norm_acct(account: str) -> str:
    return account.strip().lower()


def _norm_host(host: str | None) -> str | None:
    return host.strip().lower() if host else None


def parse_orgs_tsv(text: str) -> OrgMap | None:
    """Header-driven TSV. None signals a header we cannot use (a structural problem)."""
    rows = [line for line in text.splitlines() if line.strip()]
    if not rows:
        return None
    header = [h.strip() for h in rows[0].split("\t")]
    idx = {name: i for i, name in enumerate(header)}
    if not all(col in idx for col in ("bucket", "host", "account")):
        return None
    out: OrgMap = {}
    for line in rows[1:]:
        cols = line.split("\t")
        try:
            bucket = cols[idx["bucket"]].strip()
            host = cols[idx["host"]].strip()
            account = cols[idx["account"]].strip()
        except IndexError:
            continue
        if bucket:
            out[bucket] = (host, account)
    return out


def parse_python_dict(text: str, symbol: str) -> OrgMap | None:
    """ast.literal_eval a named dict assignment. No code is executed."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, TypeError, SyntaxError):
                        return None
                    return _coerce_pairs(value)
    return None


def parse_bash_assoc(text: str, name: str) -> OrgMap | None:
    """`declare -A NAME=( [k]=host/account ... )`, possibly across lines.

    Values may be quoted (`[k]="host/account"`) and may be empty (`[k]=`); both are
    ordinary bash. A quoted value is unquoted, and an empty value is kept as a blank
    account so it surfaces as drift, never silently vanishing.
    """
    m = re.search(r"declare\s+-A\s+" + re.escape(name) + r"=\((.*?)\)", text, re.S)
    if not m:
        return None
    body = m.group(1)
    out: OrgMap = {}
    for k, raw in re.findall(r"\[([^\]]+)\]=(\"[^\"]*\"|'[^']*'|\S*)", body):
        v = raw.strip().strip("\"'")
        host, sep, account = v.partition("/")
        if sep:
            out[k.strip()] = (host.strip(), account.strip())
        else:
            out[k.strip()] = (None, v.strip())
    return out or None


def parse_bash_case_func(
    text: str, func: str, implied_host: str | None = None
) -> OrgMap | None:
    """`func(){ case "$1" in PAT) echo VALUE;; ... esac; }`, PAT may be `a|b`.

    The function name is boundary-anchored so `org_of` does not match inside a longer
    identifier like `my_org_of`. The case body is read up to `esac` directly, not by
    brace-matching, so a `${1}` expansion inside the body does not truncate the match.
    """
    fm = re.search(r"(?<![A-Za-z0-9_])" + re.escape(func) + r"\s*\(\)\s*\{", text)
    if not fm:
        return None
    cm = re.search(r"case\b.*?\bin\b(.*?)\besac\b", text[fm.end():], re.S)
    if not cm:
        return None
    out: OrgMap = {}
    for pat, value in re.findall(r"([A-Za-z0-9_|]+)\)\s*echo\s+(\S+)\s*;;", cm.group(1)):
        val = value.strip().strip('"').strip("'")
        if not val:
            continue  # the `*)` default, or an empty echo
        for bucket in pat.split("|"):
            bucket = bucket.strip()
            if bucket and bucket != "*":
                out[bucket] = (implied_host, val)
    return out or None


def _coerce_pairs(value: object) -> OrgMap | None:
    if not isinstance(value, dict):
        return None
    out: OrgMap = {}
    for k, v in value.items():
        if isinstance(v, (tuple, list)) and len(v) >= 2:
            out[str(k)] = (str(v[0]), str(v[1]))
        elif isinstance(v, str):
            out[str(k)] = (None, v)
    return out


_PARSERS = {
    "python-dict": lambda text, cfg: parse_python_dict(text, cfg["symbol"]),
    "bash-assoc": lambda text, cfg: parse_bash_assoc(text, cfg["name"]),
    "bash-case": lambda text, cfg: parse_bash_case_func(
        text, cfg["func"], cfg.get("implied_host")
    ),
}


class OrgMapCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"source", "consumers"})
    required_keys = frozenset({"source"})

    def run(self, options: dict, box: Box) -> list[Finding]:
        source_path = options.get("source")
        if not source_path:
            return [_warn("no 'source' declared for org-map")]
        source_text = box.read_text(source_path)
        if source_text is None:
            return [_warn(f"source of truth unreadable: {source_path}")]
        truth = parse_orgs_tsv(source_text)
        if truth is None:
            return [_warn(f"source of truth has no usable header: {source_path}")]

        findings: list[Finding] = []
        consumers = options.get("consumers", [])
        if not consumers:
            findings.append(_warn("no consumers declared for org-map"))

        for consumer in consumers:
            findings.extend(self._check_consumer(consumer, truth, box))
        return findings

    def _check_consumer(self, consumer: dict, truth: OrgMap, box: Box) -> list[Finding]:
        path = consumer.get("path", "<unknown>")
        parser_name = consumer.get("parser")
        parser = _PARSERS.get(parser_name)
        if parser is None:
            return [_warn(f"{path}: unknown parser '{parser_name}'")]
        text = box.read_text(path)
        if text is None:
            return [_warn(f"{path}: unreadable")]
        try:
            observed = parser(text, consumer)
        except Exception as exc:  # a parser bug must not sink the run
            return [_warn(f"{path}: parser error ({exc.__class__.__name__})")]
        if not observed:
            return [_warn(f"{path}: parser extracted no entries, skipped not passed")]

        findings: list[Finding] = []
        # Compare the buckets this consumer actually encodes against the truth.
        for bucket, (obs_host, obs_acct) in sorted(observed.items()):
            if bucket not in truth:
                findings.append(
                    Finding(
                        ID,
                        Severity.DRIFT,
                        f"{path}:{bucket}",
                        "consumer maps a bucket that the source of truth does not list",
                        expected="(absent from orgs.tsv)",
                        observed=f"{obs_host or ''}/{obs_acct}".lstrip("/"),
                    )
                )
                continue
            true_host, true_acct = truth[bucket]
            if _norm_acct(obs_acct) != _norm_acct(true_acct):
                findings.append(
                    Finding(
                        ID,
                        Severity.DRIFT,
                        f"{path}:{bucket}",
                        "account disagrees with orgs.tsv",
                        expected=true_acct,
                        observed=obs_acct,
                    )
                )
            elif obs_host is not None and _norm_host(obs_host) != _norm_host(true_host):
                findings.append(
                    Finding(
                        ID,
                        Severity.DRIFT,
                        f"{path}:{bucket}",
                        "host disagrees with orgs.tsv",
                        expected=str(true_host),
                        observed=str(obs_host),
                    )
                )

        # Buckets in truth that this consumer does not encode: expected (consumers
        # legitimately cover subsets), reported INFO so coverage is visible.
        uncovered = sorted(set(truth) - set(observed))
        if uncovered:
            findings.append(
                Finding(
                    ID,
                    Severity.INFO,
                    f"{path}",
                    "buckets not encoded by this consumer",
                    expected=", ".join(uncovered),
                    observed="(not covered)",
                )
            )
        if not any(f.severity >= Severity.DRIFT for f in findings):
            findings.insert(
                0,
                Finding(
                    ID,
                    Severity.OK,
                    f"{path}",
                    f"agrees with orgs.tsv on all {len(observed)} encoded buckets",
                ),
            )
        return findings


def _warn(message: str) -> Finding:
    return Finding(ID, Severity.WARN, ID, message)
