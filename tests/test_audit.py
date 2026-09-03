"""Durable plan-audit: the append-only, tamper-evident record of proposed/approved/diff.

Pins the lifecycle and, above all, the tamper-evidence: a mutated past entry, a broken chain, or a
missing referenced body must all make verify() fail. That is what closes repudiation.
"""
from orrery.audit.record import PlanRecord
from orrery.audit.store import AuditStore
from orrery.integrity.store import Store


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
    rec = PlanRecord.propose("enforce", "melisae", "gate verdict", "cron", store=s)
    rec.record_result("verdict: FAIL", status="failed")
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
