"""The content-addressed store: bytes kept under their own sha256.

Git-object shaped, `<root>/ab/cdef...`, immutable and append-only. The name IS the hash, so a
write is idempotent, the store cannot hold wrong bytes under a right name, and identical content
across artifacts is stored once. Default root is the state home's `cas/`; a caller may pass another
root (tests, a per-fleet store later). The only writer of the store is `record`/`record_path`, and
they never overwrite an existing object (its bytes already hash to its name).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ..home import ensure_dir, state_home

_CHUNK = 65536


class Store:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else state_home() / "cas"

    def _obj_path(self, digest: str) -> Path:
        d = digest.lower()
        return self.root / d[:2] / d[2:]

    def has(self, digest: str) -> bool:
        return self._obj_path(digest).is_file()

    def fetch(self, digest: str) -> bytes | None:
        """The bytes recorded under `digest`, or None if never recorded."""
        p = self._obj_path(digest)
        try:
            return p.read_bytes() if p.is_file() else None
        except OSError:
            return None

    def record(self, data: bytes) -> str:
        """Store in-memory bytes; return their sha256 hex. Idempotent."""
        digest = hashlib.sha256(data).hexdigest()
        obj = self._obj_path(digest)
        if not obj.is_file():
            ensure_dir(obj.parent)
            self._atomic_write(obj, data)
        return digest

    def record_path(self, path: str | Path) -> str:
        """Stream `path` into the store (hash while copying, never load it whole); return the
        sha256 hex. If the content is already stored, the temp copy is discarded (dedup)."""
        h = hashlib.sha256()
        tmpdir = self.root / ".tmp"
        ensure_dir(tmpdir)
        tmp = tmpdir / f"rec-{os.getpid()}-{id(path)}"
        try:
            with open(path, "rb") as src, open(tmp, "wb") as dst:
                for chunk in iter(lambda: src.read(_CHUNK), b""):
                    h.update(chunk)
                    dst.write(chunk)
            digest = h.hexdigest()
            obj = self._obj_path(digest)
            if obj.is_file():
                tmp.unlink()  # already recorded; drop the duplicate
            else:
                ensure_dir(obj.parent)
                os.replace(tmp, obj)  # atomic publish under the hash name
            return digest
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @staticmethod
    def _atomic_write(obj: Path, data: bytes) -> None:
        tmp = obj.with_name(obj.name + f".tmp-{os.getpid()}")
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, obj)


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
