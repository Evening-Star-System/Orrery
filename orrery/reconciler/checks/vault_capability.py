"""vault-capability: a declared credential can still DO what its consumers need.

The failure this exists for has now happened seven times, and every time it was silent.
A vault credential expires, or is re-minted with a narrower policy set, and nothing
notices until a human tries to push to a repo days later. The 2026-08-24 case: a token
re-minted as `-policy=work-ops -policy=default` dropped `scm-read`, and 7 of 8 git
identities stopped being able to arm in ANY session or repo.

`secret-edges` is the complementary check: it verifies the secret-to-consumer GRAPH, that
each declared consumer still references the secret. But an edge can be perfectly intact
while the credential behind it is dead. Presence is not capability. This check closes that
gap: it asserts the credential still WORKS.

WHY THIS CHECK READS A REPORT INSTEAD OF CALLING THE VAULT.
A Box is read-only by construction (exists/read_text/list_files/file_meta) and holds no
credentials, which is what lets the same check run against a remote box over ssh. Probing
a vault would require a token in the reconciler. So the exercise happens where the
credential already lives -- `vault-credential-probe` on the box, via sys/capabilities-self,
comparing against `credential-helper paths` -- and this check reads its report. The reconciler stays
credential-free and value-blind; only vault PATHS and capability names ever appear.

TWO SIGNALS, NEVER CONFLATED. The 2026-08-09 spine incident wrote freshness only on
success, so five days of good syncs looked stale and "the data is old" was indistinguishable
from "the syncer is broken". The report therefore carries `probe_ok` (did the probe run)
separately from `verdict` (what it found), and this check reports them as different
findings: a probe that cannot reach the vault is a WARN about the PROBE, never a claim
that the credential is fine, and never a claim that it is broken.

A STALE REPORT IS A FINDING. A report that stopped updating is exactly how a dead check
hides a dead credential, so age is checked before verdict: a stale OK is DRIFT, not OK.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..box import Box
from ..model import Finding, Severity

ID = "vault-capability"
TITLE = "declared credentials can still do what their consumers need"

_DEFAULT_REPORT = "/var/lib/orrery/vault-credentials.json"
_DEFAULT_MAX_AGE_MIN = 60
_TS = "%Y-%m-%dT%H:%M:%SZ"


class VaultCapabilityCheck:
    id = ID
    title = TITLE
    option_keys = frozenset({"report_path", "max_age_minutes", "name"})
    required_keys: frozenset[str] = frozenset()

    def run(self, options: dict, box: Box) -> list[Finding]:
        report_path = options.get("report_path", _DEFAULT_REPORT)
        max_age = int(options.get("max_age_minutes", _DEFAULT_MAX_AGE_MIN))
        subject = options.get("name", "vault credential")

        raw = box.read_text(report_path)
        if raw is None:
            # Never run, or the probe is not installed. This is the state the fleet was in
            # for all seven outages: nothing was measuring, so nothing was ever wrong.
            return [Finding(
                ID, Severity.FAIL, subject,
                "no credential report; nothing is exercising this credential",
                expected=f"a report at {report_path}, refreshed every {max_age}m",
                observed="absent",
            )]

        try:
            rep = json.loads(raw)
        except ValueError:
            return [Finding(ID, Severity.WARN, subject,
                            f"credential report at {report_path} is not valid JSON")]

        findings: list[Finding] = []
        age_min = self._age_minutes(rep.get("checked_at"))

        if age_min is None:
            findings.append(Finding(
                ID, Severity.WARN, subject,
                "credential report has no usable checked_at timestamp"))
        elif age_min > max_age:
            # Checked BEFORE the verdict on purpose: a stale OK is not an OK.
            findings.append(Finding(
                ID, Severity.DRIFT, subject,
                "credential report is stale; its verdict is not current and the probe "
                "is probably not running",
                expected=f"refreshed within {max_age}m",
                observed=f"{int(age_min)}m old",
            ))

        if not rep.get("probe_ok", False):
            # A probe that could not run says nothing about the credential either way.
            findings.append(Finding(
                ID, Severity.WARN, subject,
                "the probe could not complete, so the credential was NOT assessed"
                + (f": {rep['note']}" if rep.get("note") else ""),
                expected="probe_ok=true", observed="probe_ok=false",
            ))
            return findings

        verdict = str(rep.get("verdict", "UNKNOWN")).upper()
        missing = list(rep.get("missing") or [])
        detail = rep.get("detail") or {}

        if verdict == "OK" and not missing:
            if not any(f.severity >= Severity.DRIFT for f in findings):
                findings.append(Finding(
                    ID, Severity.OK, subject,
                    f"all {len(detail)} required vault path(s) readable"
                    + (f" (checked {int(age_min)}m ago)" if age_min is not None else ""),
                ))
            return findings

        for vp in missing:
            buckets = (detail.get(vp) or {}).get("buckets") or []
            caps = (detail.get(vp) or {}).get("capabilities") or []
            who = ", ".join(buckets) if buckets else "unknown consumer(s)"
            findings.append(Finding(
                ID, Severity.FAIL, f"{subject}: {vp}",
                f"credential cannot read a path its consumers require; "
                f"{who} cannot authenticate in any session or repo",
                expected="read", observed=", ".join(caps) or "no capability",
            ))
        if not missing and verdict != "OK":
            findings.append(Finding(
                ID, Severity.FAIL, subject,
                f"credential report verdict is {verdict}"
                + (f": {rep['note']}" if rep.get("note") else ""),
                expected="OK", observed=verdict,
            ))
        return findings

    @staticmethod
    def _age_minutes(stamp) -> float | None:
        if not isinstance(stamp, str):
            return None
        try:
            when = datetime.strptime(stamp, _TS).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - when).total_seconds() / 60.0
