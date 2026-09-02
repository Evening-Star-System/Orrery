"""The target a reconciler measures. Read-only by construction.

v0 ships LocalBox (this machine's filesystem). A future SshBox implements the same
two methods for a remote target, and the engine and checks work unchanged because
they only ever touch this interface.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import stat as _stat
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable


_MAX_LIST_FILE_BYTES = 1_000_000
_HASH_CHUNK = 65536


@runtime_checkable
class Box(Protocol):
    def exists(self, path: str) -> bool: ...

    def read_text(self, path: str) -> str | None:
        """Return file contents, or None if absent or unreadable. Never raises."""
        ...

    def list_files(self, root: str, max_files: int) -> list[str] | None:
        """Return up to max_files file paths under root, or None if unlistable."""
        ...

    def file_meta(self, path: str) -> "tuple[int, int] | None":
        """Return (owner uid, permission bits) for path, or None if absent/unreadable."""
        ...

    def content_hash(self, path: str) -> str | None:
        """Return the sha256 hex digest of path's bytes, or None if absent or unreadable.
        Value-blind: it identifies the bytes, it never interprets them."""
        ...


class LocalBox:
    """The local filesystem, read-only. There is no write path in this class."""

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def read_text(self, path: str) -> str | None:
        # isfile() is True only for a regular file (or a symlink to one), never a
        # FIFO/socket/device, so a read never blocks forever on a pipe with no writer.
        try:
            if not os.path.isfile(path):
                return None
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def list_files(self, root: str, max_files: int = 2000) -> list[str] | None:
        out: list[str] = []
        try:
            for dirpath, _dirs, filenames in os.walk(root):  # followlinks=False: no loops
                for name in filenames:
                    fp = os.path.join(dirpath, name)
                    try:
                        if not os.path.isfile(fp):  # skip FIFO/socket/device: no hang
                            continue
                        if os.path.getsize(fp) > _MAX_LIST_FILE_BYTES:
                            continue
                    except OSError:
                        continue
                    out.append(fp)
                    if len(out) >= max_files:
                        return out
        except OSError:
            return None
        return out

    def file_meta(self, path: str) -> tuple[int, int] | None:
        try:
            st = os.stat(path)  # follows symlinks to the real file
        except OSError:
            return None
        return (st.st_uid, _stat.S_IMODE(st.st_mode))

    def content_hash(self, path: str) -> str | None:
        # Streamed so a large file is hashed without being loaded whole. isfile() first,
        # so a FIFO/device never blocks the read.
        try:
            if not os.path.isfile(path):
                return None
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(_HASH_CHUNK), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return None


class SshBox:
    """A remote box measured over ssh, read-only.

    Every remote command is a read (test, head, find, stat), run under BatchMode
    with a connect timeout, and never raises: a failure returns None/False, exactly
    like LocalBox. Paths must be absolute and are shell-quoted, so a profile value
    cannot become a remote flag or be injected into the remote shell. Reads are
    bounded so a large or special file cannot stall a run. The host is an ssh alias;
    ssh config resolves the address, user, and key.
    """

    def __init__(self, host: str, timeout: int = 8, runner=None):
        self.host = host
        self.timeout = int(timeout)
        self._runner = runner or self._ssh_run

    def _ssh_run(self, remote_cmd: str) -> tuple[int, bytes]:
        try:
            p = subprocess.run(
                [
                    "ssh", "-o", "BatchMode=yes",
                    "-o", f"ConnectTimeout={self.timeout}",
                    "--", self.host, remote_cmd,
                ],
                capture_output=True, timeout=self.timeout + 12,
            )
            return (p.returncode, p.stdout)
        except (subprocess.TimeoutExpired, OSError):
            return (255, b"")

    @staticmethod
    def _ok_path(path: str) -> bool:
        return isinstance(path, str) and path.startswith("/")

    def exists(self, path: str) -> bool:
        if not self._ok_path(path):
            return False
        rc, _ = self._runner("test -e " + shlex.quote(path))
        return rc == 0

    def read_text(self, path: str) -> str | None:
        if not self._ok_path(path):
            return None
        q = shlex.quote(path)
        rc, out = self._runner(f"test -f {q} && head -c 1000001 {q}")
        if rc != 0:
            return None
        try:
            return out.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def list_files(self, root: str, max_files: int = 2000) -> list[str] | None:
        if not self._ok_path(root):
            return None
        q = shlex.quote(root)
        rc, out = self._runner(
            f"find {q} -type f -size -1000k 2>/dev/null | head -n {int(max_files)}"
        )
        text = out.decode("utf-8", "replace")
        files = [ln for ln in text.split("\n") if ln]
        if not files and rc != 0:
            return []  # missing/unreadable root; callers check exists() first
        return files

    def file_meta(self, path: str) -> tuple[int, int] | None:
        if not self._ok_path(path):
            return None
        rc, out = self._runner("stat -c '%u %a' " + shlex.quote(path))
        if rc != 0:
            return None
        try:
            parts = out.decode("utf-8").split()
            return (int(parts[0]), int(parts[1], 8))
        except (ValueError, IndexError):
            return None

    def content_hash(self, path: str) -> str | None:
        # sha256sum on the remote, the same read-only, bounded, quoted discipline as the
        # other probes. The digest is the first field; validate its shape before trusting it.
        if not self._ok_path(path):
            return None
        rc, out = self._runner("sha256sum -- " + shlex.quote(path))
        if rc != 0:
            return None
        try:
            digest = out.decode("utf-8").split()[0].lower()
        except (IndexError, UnicodeDecodeError):
            return None
        if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
            return digest
        return None
