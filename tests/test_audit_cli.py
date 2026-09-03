"""The `ess-orrery audit` CLI: read the plan-audit by hand (list, show, verify, export).

Drives the real default store via an ORRERY_HOME override, so it exercises the same path a person on a
box would. Confirms the human table, filters, one-record show with bodies, verify exit codes, and export.
"""
import json

import pytest

from orrery.audit.cli import main as audit
from orrery.audit.record import PlanRecord


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))
    r1 = PlanRecord.propose("recover", "/etc/x", "restore /etc/x", "operator")
    r1.approve("operator (GO)"); r1.record_result("--- a\n+++ b\n", status="applied")
    PlanRecord.propose("promote", "canon", "bump the pin", "agent:builder")
    return r1


def test_list_human_table(seeded, capsys):
    assert audit(["list"]) == 0
    out = capsys.readouterr().out
    assert "recover" in out and "promote" in out and "/etc/x" in out


def test_list_json_and_filter(seeded, capsys):
    assert audit(["list", "--json"]) == 0
    recs = json.loads(capsys.readouterr().out)
    assert len(recs) == 2
    assert audit(["list", "--action", "promote"]) == 0
    out = capsys.readouterr().out
    assert "promote" in out and "recover" not in out


def test_show_renders_proposal_and_diff(seeded, capsys):
    short = seeded.id.split(":")[-1][:12]
    assert audit(["show", short]) == 0
    out = capsys.readouterr().out
    assert "restore /etc/x" in out and "--- proposed ---" in out and "--- result diff ---" in out


def test_show_unknown_id_fails(seeded, capsys):
    assert audit(["show", "deadbeefdead"]) == 1


def test_verify_ok(seeded, capsys):
    assert audit(["verify"]) == 0
    assert "intact" in capsys.readouterr().out


def test_verify_fails_after_tamper(seeded, tmp_path, capsys):
    from orrery.audit.store import AuditStore
    log = AuditStore().log_path
    lines = log.read_text().splitlines()
    lines[0] = lines[0].replace('"operator"', '"impostor"')
    log.write_text("\n".join(lines) + "\n")
    assert audit(["verify"]) == 1


def test_export_csv_and_json(seeded, capsys):
    assert audit(["export", "--format", "csv"]) == 0
    csv_out = capsys.readouterr().out
    assert csv_out.splitlines()[0].startswith("id,ts,actor,action")
    assert audit(["export", "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 2 and "proposed_hash" in rows[0]


def test_record_subcommand_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("ORRERY_HOME", str(tmp_path))
    assert audit(["record", "--action", "fold-in", "--subject", "example/app",
                  "--result", "adopted CI", "--status", "applied"]) == 0
    from orrery.audit.store import AuditStore
    recs = AuditStore().records()
    assert len(recs) == 1 and recs[0]["action"] == "fold-in" and recs[0]["status"] == "applied"
