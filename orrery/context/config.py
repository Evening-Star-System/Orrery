"""Context config: where the operator's context lives. Local/gitignored (paths).

Path knobs carry operator identity and have NO baked defaults: identity is declared,
never guessed. Non-path knobs (line caps) may default. Validation is strict on the
values that could break isolation: projects_root must be absolute, and
project_digest_relpath must be a relative path that cannot escape the project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ContextConfig:
    projects_root: str
    ops_digest: str | None
    global_baseline: str | None
    project_digest_relpath: str
    ops_digest_max_lines: int
    project_digest_max_lines: int
    baseline_max_lines: int
    changes_max_lines: int
    tasks_cap: int
    max_scan: int


def load_config(path: str | Path) -> ContextConfig:
    import tomllib

    return load_config_data(tomllib.loads(Path(path).read_text(encoding="utf-8")))


def load_config_data(data: dict) -> ContextConfig:
    projects_root = data.get("projects_root")
    if not projects_root:
        raise ValueError("context config missing required key: projects_root")
    projects_root = str(projects_root)
    if not os.path.isabs(projects_root):
        raise ValueError("projects_root must be an absolute path")

    relpath = str(data.get("project_digest_relpath", ".dev/DIGEST.md"))
    if os.path.isabs(relpath) or os.path.normpath(relpath).split(os.sep)[0] == os.pardir:
        raise ValueError(
            "project_digest_relpath must be a relative path inside the project "
            "(no absolute path, no leading ..)"
        )

    return ContextConfig(
        projects_root=projects_root,
        ops_digest=data.get("ops_digest"),
        global_baseline=data.get("global_baseline"),
        project_digest_relpath=relpath,
        ops_digest_max_lines=int(data.get("ops_digest_max_lines", 21)),
        project_digest_max_lines=int(data.get("project_digest_max_lines", 24)),
        baseline_max_lines=int(data.get("baseline_max_lines", 12)),
        changes_max_lines=int(data.get("changes_max_lines", 20)),
        tasks_cap=int(data.get("tasks_cap", 12)),
        max_scan=int(data.get("max_scan", 4000)),
    )
