"""Session-continuity: consolidate (wrap) and orient (pickup) in orrery.context."""
import os

from orrery.context.config import load_config_data
from orrery.context.handoff import START, END, read_handoff, write_handoff


def _cfg(root):
    return load_config_data({
        "projects_root": str(root),
        "project_digest_relpath": ".dev/DIGEST.md",
        "ops_digest": None,
    })


def _project(tmp_path):
    p = tmp_path / "bucketx" / "projy"
    (p / ".dev").mkdir(parents=True)
    return p


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "home"))
    proj = _project(tmp_path)
    (proj / ".dev" / "DIGEST.md").write_text("## existing body\nold content\n", encoding="utf-8")
    cfg = _cfg(tmp_path)

    res = write_handoff(str(proj), cfg, "WHERE: here\nNEXT: do the thing")
    text = (proj / ".dev" / "DIGEST.md").read_text(encoding="utf-8")

    assert text.startswith(START)
    assert "NEXT: do the thing" in text
    assert "## existing body" in text          # prior content preserved below the block
    assert res["record_id"]                     # audit record emitted (witnessable)
    assert read_handoff(str(proj), cfg) == "WHERE: here\nNEXT: do the thing"


def test_second_write_archives_prior_and_keeps_one_block(tmp_path, monkeypatch):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "home"))
    proj = _project(tmp_path)
    (proj / ".dev" / "DIGEST.md").write_text("body\n", encoding="utf-8")
    cfg = _cfg(tmp_path)

    write_handoff(str(proj), cfg, "first handoff")
    write_handoff(str(proj), cfg, "second handoff")
    text = (proj / ".dev" / "DIGEST.md").read_text(encoding="utf-8")

    assert text.count(START) == 1               # exactly one live block, not stacked
    assert "second handoff" in text
    assert "first handoff" not in text          # prior block moved out of the digest
    archived = list((proj / ".dev" / "handoffs").glob("*.md"))
    assert archived and any("first handoff" in a.read_text() for a in archived)


def test_ops_scope_without_ops_digest_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "home"))
    cfg = _cfg(tmp_path)  # ops_digest None
    # a cwd outside the projects root is ops scope; no ops digest configured -> explicit error
    try:
        write_handoff(str(tmp_path.parent), cfg, "x")
        assert False, "expected ValueError"
    except ValueError:
        pass
