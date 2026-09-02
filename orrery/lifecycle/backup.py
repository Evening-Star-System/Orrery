"""`ess-orrery backup` / `ess-orrery restore`: the user's setup as one portable artifact.

A backup is a deterministic tar.gz of the config and state homes plus any paths the user
registered, with a manifest recording where registered files came from so restore can put
them back. Restore validates the manifest, refuses to write outside its expected roots
(no tar traversal), and refuses to clobber an existing, different file unless forced.
Nothing is deleted that the archive does not replace.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
from pathlib import Path

from .. import __version__
from ..home import config_home, ensure_dir, state_home
from . import registry

SCHEMA = 1


def _walk_files(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            yield path


def _reset(info: tarfile.TarInfo) -> tarfile.TarInfo:
    # deterministic + private: no uid/gid or owner name leaking into the archive
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def make_backup(out: Path, extra_paths=None, encrypt: bool = False) -> Path:
    if encrypt:
        raise NotImplementedError(
            "encrypted backups need the optional crypto extra, which is not installed; "
            "refusing to write plaintext under an encrypted name"
        )
    out = Path(out)
    members: list[tuple[str, Path]] = []
    for root, prefix in ((config_home(), "home/config"), (state_home(), "home/state")):
        for f in _walk_files(root):
            members.append((f"{prefix}/{f.relative_to(root).as_posix()}", f))

    registered_manifest: list[dict] = []
    wanted = list(registry.list_paths()) + [
        str(Path(p).expanduser().resolve()) for p in (extra_paths or [])
    ]
    idx = 0
    for original in dict.fromkeys(sorted(wanted)):  # dedupe, stable order
        src = Path(original)
        if not src.exists() or src.is_symlink():
            continue
        prefix = f"registered/{idx}/"
        if src.is_file():
            members.append((f"{prefix}{src.name}", src))
            registered_manifest.append(
                {"prefix": prefix, "original": str(src), "is_dir": False}
            )
        elif src.is_dir():
            for f in _walk_files(src):
                members.append((f"{prefix}{f.relative_to(src).as_posix()}", f))
            registered_manifest.append(
                {"prefix": prefix, "original": str(src), "is_dir": True}
            )
        else:
            continue
        idx += 1

    manifest = {
        "schema": SCHEMA,
        "orrery_version": __version__,
        "generator": "orrery-backup",
        "registered": registered_manifest,
    }
    members.sort(key=lambda m: m[0])

    if out.parent not in (Path(""), Path(".")):
        ensure_dir(out.parent)
    with tarfile.open(out, "w:gz") as tar:
        blob = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(blob)
        tar.addfile(_reset(info), io.BytesIO(blob))
        for arc, src in members:
            tar.add(src, arcname=arc, filter=_reset)
    return out


def _dest_for(name: str, registered: list[dict]) -> Path | None:
    if name.startswith("home/config/"):
        return config_home() / name[len("home/config/") :]
    if name.startswith("home/state/"):
        return state_home() / name[len("home/state/") :]
    for entry in registered:
        prefix = entry.get("prefix", "")
        if prefix and name.startswith(prefix):
            rest = name[len(prefix) :]
            original = Path(entry["original"])
            return (original / rest) if entry.get("is_dir") else original
    return None


def _within(child: Path, root: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_dest(name: str, dest: Path, registered: list[dict]) -> bool:
    if name.startswith("home/config/"):
        return _within(dest, config_home())
    if name.startswith("home/state/"):
        return _within(dest, state_home())
    for entry in registered:
        prefix = entry.get("prefix", "")
        if prefix and name.startswith(prefix):
            original = Path(entry["original"])
            root = original if entry.get("is_dir") else original.parent
            return _within(dest, root)
    return False


def _differs(tar: tarfile.TarFile, member: tarfile.TarInfo, dest: Path) -> bool:
    try:
        existing = dest.read_bytes()
    except OSError:
        return True
    src = tar.extractfile(member)
    return existing != (src.read() if src else b"")


def restore(archive: Path, force: bool = False) -> list[str]:
    archive = Path(archive)
    with tarfile.open(archive, "r:gz") as tar:
        mf = tar.extractfile("manifest.json")
        if mf is None:
            raise ValueError("not an ess-orrery backup: manifest.json missing")
        manifest = json.loads(mf.read().decode("utf-8"))
        if manifest.get("schema") != SCHEMA:
            raise ValueError(f"unsupported backup schema: {manifest.get('schema')!r}")
        registered = manifest.get("registered", [])

        plan: list[tuple[tarfile.TarInfo, Path]] = []
        for member in tar.getmembers():
            if not member.isfile() or member.name == "manifest.json":
                continue
            dest = _dest_for(member.name, registered)
            if dest is None:
                continue
            if not _safe_dest(member.name, dest, registered):
                raise ValueError(f"refusing unsafe path in archive: {member.name}")
            plan.append((member, dest))

        conflicts = [
            str(dest)
            for member, dest in plan
            if dest.exists() and _differs(tar, member, dest)
        ]
        if conflicts and not force:
            raise FileExistsError(
                "restore would overwrite existing, different files (use --force):\n  "
                + "\n  ".join(sorted(conflicts))
            )

        if any(m.name.startswith("home/config/") for m, _ in plan):
            ensure_dir(config_home())
        if any(m.name.startswith("home/state/") for m, _ in plan):
            ensure_dir(state_home())

        written: list[str] = []
        for member, dest in plan:
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            dest.write_bytes(src.read() if src else b"")
            written.append(str(dest))
    return sorted(written)


def backup_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery backup")
    parser.add_argument(
        "--out", default=None, help="archive path (default: ./ess-orrery-backup-<version>.tar.gz)"
    )
    parser.add_argument(
        "--add", action="append", default=[], metavar="PATH",
        help="register a path to include in backups, then exit",
    )
    parser.add_argument(
        "--include", action="append", default=[], metavar="PATH",
        help="include an extra path in THIS backup only",
    )
    parser.add_argument("--list", action="store_true", help="list registered paths and exit")
    parser.add_argument("--encrypt", action="store_true", help="encrypt (needs the crypto extra)")
    args = parser.parse_args(argv)

    if args.list:
        for p in registry.list_paths():
            print(p)
        return 0
    if args.add:
        for p in args.add:
            print(f"registered: {registry.add_path(p)}")
        return 0

    out = Path(args.out) if args.out else Path(f"ess-orrery-backup-{__version__}.tar.gz")
    try:
        written = make_backup(out, extra_paths=args.include, encrypt=args.encrypt)
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {written}")
    return 0


def restore_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ess-orrery restore")
    parser.add_argument("archive", help="a backup archive from `ess-orrery backup`")
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing, different files"
    )
    args = parser.parse_args(argv)
    try:
        written = restore(Path(args.archive), force=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ValueError, tarfile.TarError, OSError) as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        return 2
    print(f"restored {len(written)} file(s)")
    return 0
