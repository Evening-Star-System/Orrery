"""Decide what scope a working directory belongs to. Pure path logic, no filesystem.

A cwd under `<projects_root>/<bucket>/<project>` (or deeper) is PROJECT scope; anything
else, including projects_root itself and /root, is OPS scope. This is the one decision
that stops project context from bleeding across projects.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    kind: str  # "project" | "ops"
    bucket: str | None = None
    project: str | None = None
    path: str | None = None  # absolute project dir, when kind == "project"


def resolve_scope(cwd: str, projects_root: str) -> Scope:
    # abspath (not just normpath) so a relative input resolves deterministically and a
    # relative projects_root cannot make scope silently depend on process cwd downstream
    root = os.path.abspath(projects_root)
    cur = os.path.abspath(cwd)
    try:
        rel = os.path.relpath(cur, root)
    except ValueError:
        # different drive (non-posix); treat as outside
        return Scope(kind="ops")
    # outside the projects root -> ops
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return Scope(kind="ops")
    parts = [] if rel == os.curdir else rel.split(os.sep)
    if len(parts) >= 2:
        bucket, project = parts[0], parts[1]
        return Scope(
            kind="project",
            bucket=bucket,
            project=project,
            path=os.path.join(root, bucket, project),
        )
    # projects_root itself, or a bare bucket dir with no project -> ops
    return Scope(kind="ops")
