"""Read the pieces of context from disk. Read-only; each returns None on absence.

Containment is enforced here, not assumed: before opening any file in project scope,
the file's realpath must stay inside the project's realpath. That is what makes the
isolation guarantee hold against a `..` in config, an absolute-path override, or a
symlink planted inside a project that points at another project or outside the tree.
Reads are line-bounded (never load a whole file) so a large CHANGES/TASKS cannot
blow up a session-start.
"""

from __future__ import annotations

import os
import re

_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}\b")
_DEFAULT_SCAN = 4000


def within(base: str, candidate: str) -> str | None:
    """Realpath(candidate) must be base itself or inside base. Returns it, or None."""
    try:
        base_r = os.path.realpath(base)
        cand_r = os.path.realpath(candidate)
    except OSError:
        return None
    if cand_r == base_r or cand_r.startswith(base_r + os.sep):
        return cand_r
    return None


def _head(path: str, max_lines: int) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            out = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                out.append(line.rstrip("\n"))
    except (OSError, UnicodeDecodeError):
        return None
    text = "\n".join(out).strip()
    return text or None


def baseline_head(path: str | None, max_lines: int) -> str | None:
    # operator-declared absolute path, not project-scoped: no containment needed
    return _head(path, max_lines) if path else None


def ops_digest_head(path: str | None, max_lines: int) -> str | None:
    return _head(path, max_lines) if path else None


def project_digest(project_path: str, relpath: str, max_lines: int) -> str | None:
    safe = within(project_path, os.path.join(project_path, relpath))
    return _head(safe, max_lines) if safe else None


def changes_latest(
    project_path: str, max_lines: int, max_scan: int = _DEFAULT_SCAN
) -> str | None:
    """First dated entry block of CHANGES.md (house format is newest-first). Bounded."""
    safe = within(project_path, os.path.join(project_path, "CHANGES.md"))
    if not safe:
        return None
    block: list[str] | None = None
    try:
        with open(safe, encoding="utf-8") as f:
            for scanned, line in enumerate(f):
                if scanned >= max_scan:
                    break
                s = line.rstrip("\n")
                if block is None:
                    if _DATED.match(s.strip()):
                        block = [s]
                else:
                    if _DATED.match(s.strip()):
                        break
                    block.append(s)
                    if len(block) >= max_lines:
                        break
    except (OSError, UnicodeDecodeError):
        return None
    if not block:
        return None
    text = "\n".join(block).strip()
    return text or None


def tasks_open(
    project_path: str, cap: int, max_scan: int = _DEFAULT_SCAN
) -> str | None:
    safe = within(project_path, os.path.join(project_path, "TASKS.md"))
    if not safe:
        return None
    items: list[str] = []
    total = 0
    capped_scan = False
    try:
        with open(safe, encoding="utf-8") as f:
            for scanned, line in enumerate(f):
                if scanned >= max_scan:
                    capped_scan = True
                    break
                s = line.strip()
                if s.startswith("- [ ]"):
                    total += 1
                    if len(items) < cap:
                        items.append(s)
    except (OSError, UnicodeDecodeError):
        return None
    if not items:
        return None
    text = "\n".join(items)
    if total > len(items):
        text += f"\n... (+{total - len(items)} more open)"
    if capped_scan:
        text += f"\n... (scan stopped at {max_scan} lines)"
    return text
