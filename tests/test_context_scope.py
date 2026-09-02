from pathlib import Path

from orrery.context.scope import resolve_scope

ROOT = str(Path(__file__).parent / "fixtures" / "ctx" / "projects")


def test_project_scope():
    s = resolve_scope(ROOT + "/esp/ProjA", ROOT)
    assert s.kind == "project" and s.bucket == "esp" and s.project == "ProjA"
    assert s.path == ROOT + "/esp/ProjA"


def test_deep_subdir_still_resolves_to_project():
    s = resolve_scope(ROOT + "/esp/ProjA/orrery/context", ROOT)
    assert s.kind == "project" and s.project == "ProjA"


def test_projects_root_itself_is_ops():
    assert resolve_scope(ROOT, ROOT).kind == "ops"


def test_bare_bucket_is_ops():
    assert resolve_scope(ROOT + "/esp", ROOT).kind == "ops"


def test_outside_root_is_ops():
    assert resolve_scope("/root", ROOT).kind == "ops"
    assert resolve_scope("/tmp/somewhere", ROOT).kind == "ops"


def test_trailing_slash_root_tolerated():
    s = resolve_scope(ROOT + "/esp/ProjB", ROOT + "/")
    assert s.kind == "project" and s.project == "ProjB"
