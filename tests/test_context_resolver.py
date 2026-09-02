import pytest
from pathlib import Path

from orrery.context.config import load_config_data
from orrery.context.resolver import resolve

CTX = Path(__file__).parent / "fixtures" / "ctx"
ROOT = str(CTX / "projects")


def cfg():
    return load_config_data(
        {
            "projects_root": ROOT,
            "ops_digest": str(CTX / "ops_digest.md"),
            "global_baseline": str(CTX / "baseline.md"),
            # fixture digest lives at state/ (not .dev/, which the repo gitignores)
            "project_digest_relpath": "state/DIGEST.md",
        }
    )


def test_project_with_digest_shows_only_itself():
    b = resolve(ROOT + "/esp/ProjA", cfg())
    assert b.scope.kind == "project"
    assert "project_digest" in b.provenance
    assert "PROJA-DIGEST-MARKER" in b.text
    # no bleed from the other project or the fleet
    assert "PROJB-CHANGES-MARKER" not in b.text
    assert "OPS-FLEET-MARKER" not in b.text
    # baseline ethos always present
    assert "BASELINE-ETHOS-MARKER" in b.text


def test_project_without_digest_falls_back_to_changes_and_tasks():
    b = resolve(ROOT + "/esp/ProjB", cfg())
    assert "changes" in b.provenance and "tasks" in b.provenance
    assert "PROJB-CHANGES-MARKER" in b.text
    assert "projb-open-task-one" in b.text
    assert "projb-open-task-two" in b.text
    assert "projb-done-task" not in b.text  # completed tasks excluded
    # only the newest CHANGES entry, not the older one
    assert "Older entry" not in b.text
    assert "OPS-FLEET-MARKER" not in b.text
    assert "PROJA-DIGEST-MARKER" not in b.text


def test_bare_project_gives_graceful_note():
    b = resolve(ROOT + "/esp/ProjC", cfg())
    assert b.provenance[-1] == "empty"
    assert "No curated context" in b.text
    assert "OPS-FLEET-MARKER" not in b.text


def test_ops_scope_shows_fleet_digest():
    b = resolve("/root", cfg())
    assert b.scope.kind == "ops"
    assert "ops_digest" in b.provenance
    assert "OPS-FLEET-MARKER" in b.text
    assert "PROJA-DIGEST-MARKER" not in b.text
    assert "BASELINE-ETHOS-MARKER" in b.text


def test_missing_projects_root_is_clean_error():
    with pytest.raises(ValueError):
        load_config_data({"ops_digest": "x"})
