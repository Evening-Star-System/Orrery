"""Core data types. Pure, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Severity(IntEnum):
    """Ordered worst-last, so max() over findings gives the run's verdict.

    OK    declared and observed agree
    INFO  an acknowledged, expected state that is not a problem (planned-absent path)
    WARN  a soft issue: a consumer could not be parsed, so it was skipped not passed
    DRIFT declared and observed DISAGREE. the core product signal
    FAIL  a declared invariant is broken (a required member is missing)
    """

    OK = 0
    INFO = 1
    WARN = 2
    DRIFT = 3
    FAIL = 4

    @property
    def label(self) -> str:
        return self.name


# At or below this severity the run is considered clean (exit 0).
CLEAN_CEILING = Severity.INFO


@dataclass(frozen=True)
class Finding:
    check_id: str
    severity: Severity
    subject: str
    message: str
    expected: str | None = None
    observed: str | None = None

    def as_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "severity": self.severity.label,
            "subject": self.subject,
            "message": self.message,
            "expected": self.expected,
            "observed": self.observed,
        }
