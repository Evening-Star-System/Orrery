"""secret-edges: the secret-to-consumer graph, verified. Value-blind.

The profile declares each secret by its NON-SECRET identity (a vault path or an env
var name, never its value) and the consumers that reference it. This check confirms
those edges, flags stale ones, and finds undeclared references, which is the graph
linked rotation (Step 5) needs and the thing neither Infisical nor Doppler ships.

Value-blindness is enforced by a FAIL-CLOSED gate: a `ref` is scanned and echoed only
if it matches a constrained identity shape (a vault path or an UPPER_SNAKE env name)
and does not match the known secret-value patterns. Anything else is refused, never
scanned, never echoed. So a misdeclared secret value does not get grepped across the
box. An optional `name` label can be given per secret to keep even the identity out of
the output entirely. Residual, documented: a secret value that happens to match the
constrained vault-path shape, with discovery enabled, could still be scanned; declare
identities, not values, and prefer `name`.
"""

from __future__ import annotations

import os
import re

from ..box import Box
from ..model import Finding, Severity

ID = "secret-edges"
TITLE = "declared secret-to-consumer edges match reality"

# A ref matching one of these is a secret VALUE, not an identity. Denylist backstop.
_SECRET_VALUE = re.compile(
    r"(BEGIN [A-Z0-9 ]*PRIVATE KEY"
    r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[baprse]-[A-Za-z0-9-]{10,}|hvs\.[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{10,}\."
    r"|(sk|rk|pk)_(live|test)_[A-Za-z0-9]{10,}|re_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,})"
)
# Allowlist (fail-closed): identities we will scan for. Everything else is refused.
# env name = UPPER_SNAKE (so a mixed-case secret blob like an AWS secret key does not
# pass as an "identity"); vault path = slash-separated short segments.
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_VAULT_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}(/[A-Za-z0-9._-]{1,31}){1,7}$")
_MAX_SCAN_FILES = 2000


def _is_safe_identity(ref: object) -> bool:
    if not isinstance(ref, str) or not ref or len(ref) > 96:
        return False
    if _SECRET_VALUE.search(ref):
        return False
    return bool(_ENV_NAME.match(ref) or _VAULT_PATH.match(ref))


def _abs(path: str) -> str:
    return os.path.abspath(os.path.normpath(path))


def _references(box: Box, path: str, ref: str) -> bool | None:
    """Whether the file contains the literal ref. Returns a bool only, never content."""
    text = box.read_text(path)
    if text is None:
        return None
    return ref in text


class SecretEdgesCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"secrets", "discover_root"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        secrets = options.get("secrets", [])
        if not secrets:
            return [Finding(ID, Severity.WARN, ID, "no secrets declared for secret-edges")]
        discover_root = options.get("discover_root")
        findings: list[Finding] = []
        for index, secret in enumerate(secrets):
            findings.extend(self._check_secret(index, secret, discover_root, box))
        return findings

    def _check_secret(
        self, index: int, secret: dict, discover_root: str | None, box: Box
    ) -> list[Finding]:
        ref = secret.get("ref")
        # label for output: never the raw ref unless the operator gave no name (and then
        # only because ref has already passed the fail-closed identity gate below).
        name = secret.get("name")
        if not _is_safe_identity(ref):
            label = str(name) if name else f"secret#{index}"
            return [
                Finding(
                    ID,
                    Severity.WARN,
                    label,
                    "ref is not a valid identity (declare a vault path or env var NAME, not a "
                    "secret value); refused, not scanned",
                )
            ]
        label = str(name) if name else ref  # ref is a constrained identity here

        findings: list[Finding] = []
        declared: set[str] = set()
        for consumer in secret.get("consumers", []):
            path = consumer.get("path")
            if not path:
                findings.append(Finding(ID, Severity.WARN, label, "consumer missing 'path'"))
                continue
            declared.add(_abs(path))
            present = _references(box, path, ref)
            subject = f"{label} -> {path}"
            if present is None:
                findings.append(
                    Finding(
                        ID, Severity.DRIFT, subject,
                        "declared consumer file is missing or unreadable",
                        expected="references the secret", observed="file absent",
                    )
                )
            elif present:
                findings.append(Finding(ID, Severity.OK, subject, "edge confirmed"))
            else:
                findings.append(
                    Finding(
                        ID, Severity.DRIFT, subject,
                        "consumer no longer references the secret (stale edge)",
                        expected="references the secret", observed="reference absent",
                    )
                )

        if discover_root:
            findings.extend(self._discover(box, discover_root, ref, label, declared))
        return findings

    def _discover(
        self, box: Box, root: str, ref: str, label: str, declared: set[str]
    ) -> list[Finding]:
        if not box.exists(root):
            return [Finding(ID, Severity.WARN, label, f"discover_root does not exist: {root}")]
        lister = getattr(box, "list_files", None)
        files = lister(root, _MAX_SCAN_FILES) if lister else None
        if files is None:
            return [Finding(ID, Severity.WARN, label, f"discover_root not listable: {root}")]
        out: list[Finding] = []
        for path in files:
            if _abs(path) in declared:
                continue
            if _references(box, path, ref):
                out.append(
                    Finding(
                        ID, Severity.DRIFT, f"{label} -> {path}",
                        "undeclared edge: references the secret but is not a declared consumer",
                        expected="declared consumer", observed="undeclared reference",
                    )
                )
        return out
