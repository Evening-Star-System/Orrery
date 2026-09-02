"""Run the checks a profile declares, collect findings, decide the verdict.

Report-only: the engine reads and reports, it never mutates the box. One broken
check never sinks the run; an unknown check id or a check that raises degrades to a
WARN finding and the rest still run.
"""

from __future__ import annotations

from dataclasses import dataclass

from .box import Box, LocalBox
from .model import CLEAN_CEILING, Finding, Severity
from .profile import Profile, load_profile
from .registry import get_check


@dataclass
class Result:
    box: str
    findings: list[Finding]

    @property
    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.OK)

    @property
    def clean(self) -> bool:
        return self.worst <= CLEAN_CEILING

    @property
    def exit_code(self) -> int:
        return 0 if self.clean else 1

    def counts(self) -> dict[str, int]:
        out = {s.label: 0 for s in Severity}
        for f in self.findings:
            out[f.severity.label] += 1
        return out


class Engine:
    def __init__(self, box: Box | None = None):
        self.box = box or LocalBox()

    def run(self, profile: Profile, only: str | None = None) -> Result:
        findings: list[Finding] = []
        for cfg in profile.checks:
            if only and cfg.id != only:
                continue
            check = get_check(cfg.id)
            if check is None:
                findings.append(
                    Finding(cfg.id, Severity.WARN, cfg.id, "unknown check id, skipped")
                )
                continue
            try:
                findings.extend(check.run(cfg.options, self.box))
            except Exception as exc:  # a check bug must not sink the whole run
                findings.append(
                    Finding(
                        cfg.id,
                        Severity.WARN,
                        cfg.id,
                        f"check raised {exc.__class__.__name__}, treated as inconclusive",
                    )
                )
        return Result(box=profile.box, findings=findings)


def run_profile(
    path: str, box: Box | None = None, only: str | None = None
) -> Result:
    return Engine(box=box).run(load_profile(path), only=only)
