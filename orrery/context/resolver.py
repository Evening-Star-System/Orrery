"""Resolve the context to inject for a given cwd. The isolation happens here.

Global baseline (ethos) is always included. In OPS scope the fleet digest is added.
In PROJECT scope only THAT project's own state is added, never another project's and
never the fleet digest. That single rule is what ends the cross-contamination.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import sources
from .config import ContextConfig
from .scope import Scope, resolve_scope


@dataclass
class ContextBundle:
    scope: Scope
    text: str
    provenance: list[str] = field(default_factory=list)


def resolve(cwd: str, config: ContextConfig) -> ContextBundle:
    parts: list[str] = []
    prov: list[str] = []

    baseline = sources.baseline_head(config.global_baseline, config.baseline_max_lines)
    if baseline:
        parts.append(baseline)
        prov.append("baseline")

    scope = resolve_scope(cwd, config.projects_root)

    if scope.kind == "ops":
        ops = sources.ops_digest_head(config.ops_digest, config.ops_digest_max_lines)
        if ops:
            parts.append("=== OPS / FLEET STATE ===\n" + ops)
            prov.append("ops_digest")
    else:
        header = f"=== PROJECT: {scope.bucket}/{scope.project} ==="
        # the project dir itself must resolve inside the declared projects root; a
        # symlinked bucket/project that escapes the root is refused, not read.
        if sources.within(config.projects_root, scope.path) is None:
            parts.append(
                header
                + "\n(project directory resolves outside the projects root; refusing to read)"
            )
            prov.append("refused")
            return ContextBundle(scope=scope, text="\n\n".join(parts), provenance=prov)
        digest = sources.project_digest(
            scope.path, config.project_digest_relpath, config.project_digest_max_lines
        )
        if digest:
            parts.append(header + "\n" + digest)
            prov.append("project_digest")
        else:
            changes = sources.changes_latest(
                scope.path, config.changes_max_lines, config.max_scan
            )
            tasks = sources.tasks_open(scope.path, config.tasks_cap, config.max_scan)
            if changes or tasks:
                body = [header]
                if changes:
                    body.append("recent:\n" + changes)
                    prov.append("changes")
                if tasks:
                    body.append("open tasks:\n" + tasks)
                    prov.append("tasks")
                parts.append("\n\n".join(body))
            else:
                parts.append(
                    header
                    + f"\nNo curated context yet. Create {config.project_digest_relpath} for this "
                    "project (or add CHANGES.md / TASKS.md)."
                )
                prov.append("empty")

    return ContextBundle(scope=scope, text="\n\n".join(parts), provenance=prov)
