"""Durable plan-audit: the append-only, tamper-evident record of proposed/approved/diff.

Pins the lifecycle and, above all, the tamper-evidence: a mutated past entry, a broken chain, or a
missing referenced body must all make verify() fail. That is what closes repudiation.
"""
import pytest

from orrery.audit.record import PlanRecord
from orrery.audit.store import AuditStore
from orrery.integrity.store import Store


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path_factory, monkeypatch):
    """Never let a unit test read this box's real settings.toml or a stray anchor env var. A test that
    wants a specific home or anchor overrides these afterward (its monkeypatch call wins by order)."""
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path_factory.mktemp("home")))
    monkeypatch.delenv("ORRERY_AUDIT_ANCHOR", raising=False)


def _store(tmp_path):
    return AuditStore(root=tmp_path / "audit", cas=Store(tmp_path / "cas"))


def test_lifecycle_proposed_approved_applied(tmp_path):
    s = _store(tmp_path)
    rec = PlanRecord.propose("recover", "/etc/x", "restore /etc/x to golden", "operator", store=s)
    assert s.get(rec.id)["status"] == "proposed"
    rec.approve("operator (GO)")
    v = s.get(rec.id)
    assert v["status"] == "approved" and v["approved_by"] == "operator (GO)"
    rec.record_result("--- a/x\n+++ b/x\n", status="applied")
    v = s.get(rec.id)
    assert v["status"] == "applied" and v["result"]["diff_hash"]


def test_unapproved_stays_proposed(tmp_path):
    s = _store(tmp_path)
    rec = PlanRecord.propose("promote", "canon", "bump pin", "agent:builder", store=s)
    assert s.get(rec.id)["status"] == "proposed" and s.get(rec.id)["approved_by"] is None


def test_failed_result_closes_failed(tmp_path):
    s = _store(tmp_path)
    rec = PlanRecord.propose("recover", "/etc/x", "restore /etc/x to golden", "operator", store=s)
    rec.record_result("write failed: verify-after mismatch", status="failed")
    assert s.get(rec.id)["status"] == "failed"


def test_bodies_land_in_the_content_store(tmp_path):
    s = _store(tmp_path)
    rec = PlanRecord.propose("recover", "/x", "the full plan body", "operator", store=s)
    bh = s.get(rec.id)["proposed"]["body_hash"]
    assert s.cas.fetch(bh) == b"the full plan body"


def test_verify_passes_on_a_clean_chain(tmp_path):
    s = _store(tmp_path)
    r1 = PlanRecord.propose("recover", "/a", "plan a", "op", store=s); r1.approve("go"); r1.record_result("diff a")
    PlanRecord.propose("promote", "canon", "plan b", "op", store=s)
    ok, msg = s.verify()
    assert ok, msg
    # records fold in order
    assert [r["action"] for r in s.records()] == ["recover", "promote"]


def test_verify_fails_on_a_mutated_entry(tmp_path):
    s = _store(tmp_path)
    r = PlanRecord.propose("recover", "/a", "plan a", "op", store=s); r.record_result("diff a")
    lines = s.log_path.read_text().splitlines()
    lines[0] = lines[0].replace('"actor":"op"', '"actor":"someone-else"')  # forge the actor
    s.log_path.write_text("\n".join(lines) + "\n")
    ok, msg = s.verify()
    assert not ok and "self hash mismatch" in msg


def test_verify_fails_on_a_broken_chain(tmp_path):
    s = _store(tmp_path)
    PlanRecord.propose("recover", "/a", "plan a", "op", store=s)
    PlanRecord.propose("recover", "/b", "plan b", "op", store=s)
    PlanRecord.propose("recover", "/c", "plan c", "op", store=s)
    lines = s.log_path.read_text().splitlines()
    del lines[1]  # drop a middle entry
    s.log_path.write_text("\n".join(lines) + "\n")
    ok, msg = s.verify()
    assert not ok and "broken chain" in msg


def test_verify_fails_when_a_referenced_body_is_removed(tmp_path):
    s = _store(tmp_path)
    r = PlanRecord.propose("recover", "/a", "plan a", "op", store=s)
    bh = s.get(r.id)["proposed"]["body_hash"]
    s.cas._obj_path(bh).unlink()  # remove the body via the store's own path logic
    ok, msg = s.verify()
    assert not ok and "missing" in msg


def test_truncating_the_tail_is_honest_without_an_anchor(tmp_path):
    # With no anchor, a dropped newest entry leaves a consistent chain; verify does NOT flag it, but
    # it SAYS so instead of claiming completeness it cannot prove.
    s = _store(tmp_path)
    PlanRecord.propose("recover", "/a", "plan a", "op", store=s)
    PlanRecord.propose("recover", "/b", "plan b", "op", store=s)
    lines = s.log_path.read_text().splitlines()
    s.log_path.write_text(lines[0] + "\n")  # drop the newest entry
    ok, msg = s.verify()
    assert ok and "truncated tail would not be detected" in msg


def test_expect_head_detects_a_truncated_tail(tmp_path):
    s = _store(tmp_path)
    PlanRecord.propose("recover", "/a", "plan a", "op", store=s)
    PlanRecord.propose("recover", "/b", "plan b", "op", store=s)
    head = s.head()["self"]
    lines = s.log_path.read_text().splitlines()
    s.log_path.write_text(lines[0] + "\n")  # drop the entry the anchored head names
    ok, msg = s.verify(expect_head=head)
    assert not ok and "truncated or rewritten" in msg


def test_external_anchor_detects_a_truncated_tail(tmp_path):
    anchor = tmp_path / "ext" / "anchor.jsonl"  # outside the log dir, an append-only sink
    s = AuditStore(root=tmp_path / "audit", cas=Store(tmp_path / "cas"), anchor=anchor)
    for x in "abc":
        PlanRecord.propose("recover", f"/{x}", f"plan {x}", "op", store=s)
    assert s.verify()[0]  # anchored head matches the on-disk tail
    lines = s.log_path.read_text().splitlines()
    s.log_path.write_text("\n".join(lines[:-1]) + "\n")  # truncate the log; the external anchor is untouched
    ok, msg = s.verify()
    assert not ok and "truncated or rewritten" in msg


def test_entries_newer_than_the_anchor_are_benign(tmp_path):
    # The crash window (append succeeded, head not yet anchored) must not be a false positive: entries
    # PAST the anchored head are fine.
    s = _store(tmp_path)
    PlanRecord.propose("recover", "/a", "plan a", "op", store=s)
    early = s.head()["self"]
    PlanRecord.propose("recover", "/b", "plan b", "op", store=s)  # newer than the anchor
    ok, msg = s.verify(expect_head=early)
    assert ok and "newer not yet anchored" in msg


def test_anchor_resolves_from_settings_toml(tmp_path, monkeypatch):
    # The persistent per-operator default: [audit].anchor in settings.toml, no env, no explicit arg.
    from orrery.home import write_settings

    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "home"))
    anchor = tmp_path / "ext" / "anchor.jsonl"
    write_settings({"audit": {"anchor": str(anchor)}})
    s = AuditStore(root=tmp_path / "audit", cas=Store(tmp_path / "cas"))
    assert s.anchor == anchor
    for x in "ab":
        PlanRecord.propose("recover", f"/{x}", f"p{x}", "op", store=s)
    assert anchor.exists() and s.verify()[0]  # emits to the configured sink and verifies against it


def test_env_anchor_overrides_settings(tmp_path, monkeypatch):
    from orrery.home import write_settings

    monkeypatch.setenv("ORRERY_HOME", str(tmp_path / "home"))
    write_settings({"audit": {"anchor": str(tmp_path / "from_settings.jsonl")}})
    monkeypatch.setenv("ORRERY_AUDIT_ANCHOR", str(tmp_path / "from_env.jsonl"))
    s = AuditStore(root=tmp_path / "audit", cas=Store(tmp_path / "cas"))
    assert s.anchor == tmp_path / "from_env.jsonl"


def test_explicit_anchor_overrides_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ORRERY_AUDIT_ANCHOR", str(tmp_path / "env.jsonl"))
    s = AuditStore(root=tmp_path / "audit", cas=Store(tmp_path / "cas"), anchor=tmp_path / "explicit.jsonl")
    assert s.anchor == tmp_path / "explicit.jsonl"


def test_emit_failure_warns_once_and_still_records(tmp_path, capsys):
    import orrery.audit.store as store_mod

    store_mod._warned_anchors.clear()
    blocker = tmp_path / "blocker"
    blocker.write_text("x")  # a FILE where the anchor's parent dir would go, so the emit mkdir fails
    s = AuditStore(root=tmp_path / "audit", cas=Store(tmp_path / "cas"), anchor=blocker / "anchor.jsonl")
    PlanRecord.propose("recover", "/a", "p", "op", store=s)
    PlanRecord.propose("recover", "/b", "p", "op", store=s)
    err = capsys.readouterr().err
    assert err.count("could not write the head anchor") == 1  # warned once, not per action
    assert [r["action"] for r in s.records()] == ["recover", "recover"]  # the actions still recorded
