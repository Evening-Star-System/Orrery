"""Regression tests for the 2026-08-07 context audit: the isolation guarantee must
hold against config traversal, absolute overrides, and in-tree symlinks."""

import os
import pytest

from orrery.context.config import load_config_data
from orrery.context.resolver import resolve


def _cfg(root, **over):
    data = {"projects_root": root, "project_digest_relpath": ".dev/DIGEST.md"}
    data.update(over)
    return load_config_data(data)


def test_relative_projects_root_rejected():
    with pytest.raises(ValueError):
        load_config_data({"projects_root": "relative/path"})


def test_absolute_digest_relpath_rejected():
    with pytest.raises(ValueError):
        load_config_data({"projects_root": "/opt/projects", "project_digest_relpath": "/etc/hostname"})


def test_traversal_digest_relpath_rejected():
    with pytest.raises(ValueError):
        load_config_data(
            {"projects_root": "/opt/projects", "project_digest_relpath": "../other/CHANGES.md"}
        )


def _make_tree(tmp_path):
    root = tmp_path / "projects"
    a = root / "esp" / "ProjA"
    b = root / "esp" / "ProjB"
    (a / ".dev").mkdir(parents=True)
    (b / ".dev").mkdir(parents=True)
    (a / ".dev" / "DIGEST.md").write_text("PROJA-OWN\n", encoding="utf-8")
    (b / ".dev" / "DIGEST.md").write_text("PROJB-SECRET\n", encoding="utf-8")
    return root, a, b


def test_symlinked_dev_dir_does_not_leak_other_project(tmp_path):
    root, a, b = _make_tree(tmp_path)
    # planted symlink: ProjA/.dev -> ProjB/.dev
    import shutil

    shutil.rmtree(a / ".dev")
    os.symlink(b / ".dev", a / ".dev")
    bundle = resolve(str(a), _cfg(str(root)))
    assert "PROJB-SECRET" not in bundle.text  # containment must block the alias
    assert "project_digest" not in bundle.provenance


def test_project_dir_symlinked_outside_root_is_refused(tmp_path):
    root, a, b = _make_tree(tmp_path)
    outside = tmp_path / "outside"
    (outside / ".dev").mkdir(parents=True)
    (outside / ".dev" / "DIGEST.md").write_text("OUTSIDE-CONTENT\n", encoding="utf-8")
    # ProjA replaced by a symlink to a dir outside projects_root
    import shutil

    shutil.rmtree(a)
    os.symlink(outside, a)
    bundle = resolve(str(a), _cfg(str(root)))
    assert "OUTSIDE-CONTENT" not in bundle.text
    assert "refused" in bundle.provenance


def test_tasks_scan_is_bounded(tmp_path):
    root = tmp_path / "projects"
    p = root / "esp" / "ProjBig"
    p.mkdir(parents=True)
    # far more open tasks than the scan window
    p.joinpath("TASKS.md").write_text("\n".join("- [ ] t%d" % i for i in range(5000)), encoding="utf-8")
    bundle = resolve(str(p), _cfg(str(root), max_scan=100, tasks_cap=5))
    assert "scan stopped at 100 lines" in bundle.text
    # only cap items shown
    assert bundle.text.count("- [ ] t") == 5
