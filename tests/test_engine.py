from pathlib import Path

from orrery.reconciler import engine as engine_mod
from orrery.reconciler.engine import Engine
from orrery.reconciler.model import Finding, Severity
from orrery.reconciler.profile import load_profile_data

FIX = Path(__file__).parent / "fixtures"


def _profile(checks):
    return load_profile_data({"box": "test", "checks": checks})


def test_unknown_check_id_warns_not_crash():
    result = Engine().run(_profile([{"id": "no-such-check"}]))
    assert result.findings[0].severity == Severity.WARN
    # WARN means "could not verify": for a conformance tool that is non-clean, so a
    # cron/CI alerts rather than reading blindness as success.
    assert result.exit_code == 1


def test_worst_severity_and_exit_code():
    profile = _profile(
        [
            {
                "id": "org-map",
                "source": str(FIX / "orgs.tsv"),
                "consumers": [
                    {
                        "path": str(FIX / "drift" / "org-guard.py"),
                        "parser": "python-dict",
                        "symbol": "BUCKET_ACCT",
                    }
                ],
            }
        ]
    )
    result = Engine().run(profile)
    assert result.worst == Severity.DRIFT
    assert result.exit_code == 1
    assert not result.clean


def test_check_that_raises_degrades_to_warn(monkeypatch):
    class Boom:
        id = "boom"
        title = "always raises"

        def run(self, options, box):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(engine_mod, "get_check", lambda cid: Boom())
    result = Engine().run(_profile([{"id": "boom"}]))
    assert result.worst == Severity.WARN
    assert result.exit_code == 1  # inconclusive is non-clean by design
    assert "kaboom".upper() not in result.findings[0].message  # no leak of raw text
    assert "RuntimeError" in result.findings[0].message


def test_only_filter_runs_one_check():
    profile = _profile(
        [
            {"id": "declared-presence", "required": [str(FIX / "orgs.tsv")]},
            {"id": "org-map", "source": str(FIX / "orgs.tsv"), "consumers": []},
        ]
    )
    result = Engine().run(profile, only="declared-presence")
    assert {f.check_id for f in result.findings} == {"declared-presence"}
