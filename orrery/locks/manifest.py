"""Read a lock manifest, and write a golden back into it without disturbing anything else.

The manifest is `orrery-locks.toml`: an array of `[[locks]]` tables, each with a stable
`id`, a human `why`, a `command`, a `capture`, and (once captured) a `golden`. The check
reads it with `tomllib`; this module reads the same way and adds the one write the check
never does.

Writing is surgical on purpose. The engines carry zero runtime dependencies, so there is
no TOML writer to round-trip through, and re-emitting the file would flatten the comments
and ordering a human relies on (the `why`, the reason a lock exists, lives in this file).
So a write finds the target lock's block by `id`, replaces or inserts its single `golden`
line in place, and leaves every other byte alone. The result is re-parsed with `tomllib`
and the intended value is confirmed to round-trip before it is handed back to be saved:
the write is never trusted blind.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass

MANIFEST_NAME = "orrery-locks.toml"
RESULTS_NAME = "orrery-locks.results.json"

# A `[[locks]]` header (tolerant of inner spacing). Any other `[` line ends the current
# lock's scope: a new table, so its keys no longer belong to the lock above.
_LOCK_HEADER = re.compile(r"^\s*\[\[\s*locks\s*\]\]\s*$")
_ANY_HEADER = re.compile(r"^\s*\[")
# `id`/`golden` key lines, tolerant of spacing and either quote style for the id value.
_ID = re.compile(r"""^(\s*)id\s*=\s*(?:"([^"]*)"|'([^']*)')\s*$""")
_GOLDEN = re.compile(r"^(\s*)golden\s*=")


@dataclass
class _Block:
    start: int  # index of the `[[locks]]` header line
    end: int    # exclusive; first line no longer in this block
    id: str | None
    id_line: int | None
    golden_line: int | None


def load(text: str) -> dict:
    """Parse the manifest text. Raises tomllib.TOMLDecodeError on invalid TOML, the same
    failure the check degrades to a WARN; callers surface it as a clean message."""
    return tomllib.loads(text)


def locks(doc: dict) -> list[dict]:
    got = doc.get("locks")
    return got if isinstance(got, list) else []


def golden_of(doc: dict, lock_id: str):
    for lock in locks(doc):
        if lock.get("id") == lock_id:
            return lock.get("golden")
    return None


def has_lock(doc: dict, lock_id: str) -> bool:
    return any(lock.get("id") == lock_id for lock in locks(doc))


def set_golden(text: str, lock_id: str, value: str) -> str:
    """Return the manifest text with `lock_id`'s golden set to `value`, everything else
    preserved. Raises KeyError if no lock has that id, ValueError if the write does not
    round-trip through tomllib to the intended value."""
    lines = text.splitlines(keepends=True)
    block = _find_block(lines, lock_id)
    if block is None:
        raise KeyError(lock_id)

    nl = _newline(text)
    if block.golden_line is not None:
        indent = _indent(lines[block.golden_line])
        lines[block.golden_line] = f"{indent}golden = {toml_string(value)}{nl}"
    else:
        indent = _indent(lines[block.id_line]) if block.id_line is not None else ""
        # Insert after the block's last non-blank line so the golden sits with its lock,
        # not below the blank gap before the next one.
        at = block.end
        while at - 1 > block.start and not lines[at - 1].strip():
            at -= 1
        insertion = f"{indent}golden = {toml_string(value)}{nl}"
        if at > 0 and not lines[at - 1].endswith(("\n", "\r")):
            insertion = nl + insertion  # the file did not end in a newline; do not join lines
        lines.insert(at, insertion)

    new_text = "".join(lines)
    if golden_of(tomllib.loads(new_text), lock_id) != value:
        raise ValueError(f"golden write for {lock_id!r} did not round-trip")
    return new_text


def append_lock(text: str, lock_id: str, command: str, why: str, capture: str = "stdout-line") -> str:
    """Return the manifest text with a new `[[locks]]` block appended (no golden yet: a
    capture writes that). The caller guarantees the id is not already present."""
    nl = _newline(text)
    prefix = ""
    if text and not text.endswith(("\n", "\r")):
        prefix = nl  # close the last line first
    block = (
        f"{nl}[[locks]]{nl}"
        f"id = {toml_string(lock_id)}{nl}"
        f"why = {toml_string(why)}{nl}"
        f"command = {toml_string(command)}{nl}"
        f"capture = {toml_string(capture)}{nl}"
    )
    return text + prefix + block


def toml_string(value: str) -> str:
    """A TOML basic string for `value`, escaping what must be escaped. A captured golden is
    one trimmed stdout line, but it can still hold a quote or a backslash, so escape rather
    than assume."""
    out = []
    for ch in str(value):
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _find_block(lines: list[str], lock_id: str) -> _Block | None:
    blocks: list[_Block] = []
    cur: _Block | None = None
    for i, line in enumerate(lines):
        if _LOCK_HEADER.match(line):
            if cur is not None:
                cur.end = i
                blocks.append(cur)
            cur = _Block(start=i, end=len(lines), id=None, id_line=None, golden_line=None)
        elif _ANY_HEADER.match(line):
            if cur is not None:
                cur.end = i
                blocks.append(cur)
                cur = None
        elif cur is not None:
            m = _ID.match(line)
            if m and cur.id is None:
                cur.id = m.group(2) if m.group(2) is not None else m.group(3)
                cur.id_line = i
            elif _GOLDEN.match(line) and cur.golden_line is None:
                cur.golden_line = i
    if cur is not None:
        blocks.append(cur)
    return next((b for b in blocks if b.id == lock_id), None)


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]
