"""Profile validation: quiet profile mistakes must surface as their own finding."""

from __future__ import annotations

from orrery.reconciler.profile_cli import main as profile_main
from orrery.reconciler.registry import known_ids, option_schemas
from orrery.reconciler.validate import (
    ERROR,
    INFO,
    WARN,
    validate_profile,
    validate_profile_data,
)

KNOWN = known_ids()
SCHEMAS = option_schemas()


def _levels(issues, location=None):
    return [i.level for i in issues if location is None or i.location == location]


def test_sound_profile_has_no_errors():
    data = {"box": "work-box", "checks": [{"id": "org-map", "source": "/x/orgs.tsv"}]}
    issues = validate_profile_data(data, KNOWN)
    assert not any(i.level == ERROR for i in issues)


def test_missing_box_is_error():
    issues = validate_profile_data({"checks": [{"id": "org-map"}]}, KNOWN)
    assert ERROR in _levels(issues, "box")


def test_blank_box_is_error():
    issues = validate_profile_data({"box": "  ", "checks": [{"id": "org-map"}]}, KNOWN)
    assert ERROR in _levels(issues, "box")


def test_unknown_check_id_is_error_with_suggestion():
    # a plausible typo of a real id
    issues = validate_profile_data({"box": "b", "checks": [{"id": "org_map"}]}, KNOWN)
    err = next(i for i in issues if i.location == "checks[0].id")
    assert err.level == ERROR
    assert "org-map" in err.message  # difflib suggested the real id


def test_duplicate_check_id_is_warn():
    data = {"box": "b", "checks": [{"id": "org-map"}, {"id": "org-map"}]}
    issues = validate_profile_data(data, KNOWN)
    assert any(i.level == WARN and "declared 2 times" in i.message for i in issues)


def test_no_checks_is_warn():
    assert WARN in _levels(validate_profile_data({"box": "b"}, KNOWN), "checks")
    assert WARN in _levels(validate_profile_data({"box": "b", "checks": []}, KNOWN), "checks")


def test_checks_not_a_list_is_error():
    assert ERROR in _levels(validate_profile_data({"box": "b", "checks": "nope"}, KNOWN), "checks")


def test_check_missing_id_is_error():
    issues = validate_profile_data({"box": "b", "checks": [{"source": "/x"}]}, KNOWN)
    assert ERROR in _levels(issues, "checks[0].id")


def test_check_without_options_is_info_not_error():
    issues = validate_profile_data({"box": "b", "checks": [{"id": "org-map"}]}, KNOWN)
    assert INFO in _levels(issues, "checks[0]")
    assert not any(i.level == ERROR for i in issues)


def test_validation_is_value_blind():
    # A secret-looking option value must never appear in any issue message.
    secret = "/run/secrets/PROD_DB_PASSWORD_do_not_leak"
    data = {"box": "b", "checks": [{"id": "org_typo", "source": secret}]}
    issues = validate_profile_data(data, KNOWN)
    assert issues  # the typo'd id produces an error
    assert all(secret not in i.message for i in issues)


def test_bad_toml_file_is_a_single_error(tmp_path):
    p = tmp_path / "broken.toml"
    p.write_text("box = = =\n", encoding="utf-8")
    issues = validate_profile(p, KNOWN)
    assert len(issues) == 1 and issues[0].level == ERROR and "TOML" in issues[0].message


def test_missing_file_is_error(tmp_path):
    issues = validate_profile(tmp_path / "nope.toml", KNOWN)
    assert len(issues) == 1 and issues[0].level == ERROR


def test_cli_valid_profile_exits_zero(tmp_path, capsys):
    p = tmp_path / "ok.toml"
    p.write_text('box = "work-box"\n[[checks]]\nid = "org-map"\nsource = "/x"\n', encoding="utf-8")
    assert profile_main(["validate", str(p)]) == 0


def test_cli_unknown_id_exits_two(tmp_path, capsys):
    p = tmp_path / "bad.toml"
    p.write_text('box = "b"\n[[checks]]\nid = "org_map"\n', encoding="utf-8")
    assert profile_main(["validate", str(p)]) == 2


def test_cli_json_shape(tmp_path, capsys):
    import json

    p = tmp_path / "bad.toml"
    p.write_text('box = "b"\n[[checks]]\nid = "nope"\n', encoding="utf-8")
    rc = profile_main(["validate", str(p), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2 and out["ok"] is False and out["issues"]


# --- per-check option validation (slice 2): top-level keys only ---


def test_every_registered_check_declares_a_schema():
    # all nine checks declare their option keys, so validation covers the whole registry
    assert set(SCHEMAS) == set(KNOWN)


def test_unknown_option_key_is_warn_with_suggestion():
    data = {"box": "b", "checks": [{"id": "fleet-reach", "edge": []}]}
    issues = validate_profile_data(data, KNOWN, SCHEMAS)
    warn = next(i for i in issues if i.location == "checks[0].edge")
    assert warn.level == WARN and "edges" in warn.message


def test_missing_required_option_is_error():
    data = {"box": "b", "checks": [{"id": "org-map", "consumers": []}]}
    issues = validate_profile_data(data, KNOWN, SCHEMAS)
    assert any(i.level == ERROR and i.location == "checks[0].source" for i in issues)


def test_recognized_options_are_clean():
    data = {"box": "b", "checks": [{"id": "org-map", "source": "/x", "consumers": []}]}
    issues = validate_profile_data(data, KNOWN, SCHEMAS)
    assert not any(i.level in (ERROR, WARN) for i in issues)


def test_option_validation_is_value_blind():
    secret = "/run/secrets/DB_PASSWORD_leak"
    data = {"box": "b", "checks": [{"id": "fleet-reach", "edgez": secret}]}
    issues = validate_profile_data(data, KNOWN, SCHEMAS)
    assert any(i.level == WARN for i in issues)
    assert all(secret not in i.message for i in issues)


def test_no_schema_means_options_not_checked():
    # with an empty schema map, unknown option keys are allowed (id still validated)
    data = {"box": "b", "checks": [{"id": "floors", "anything_goes": 1}]}
    issues = validate_profile_data(data, KNOWN, schemas={})
    assert not any(i.location == "checks[0].anything_goes" for i in issues)


# --- reconcile --strict: refuse to run a profile that would silently check less ---

from orrery.reconciler.__main__ import EXIT_PROFILE_ERROR
from orrery.reconciler.__main__ import main as reconcile_main


def test_reconcile_strict_blocks_unknown_id(tmp_path, capsys):
    p = tmp_path / "typo.toml"
    p.write_text('box = "b"\n[[checks]]\nid = "org_map"\n', encoding="utf-8")
    assert reconcile_main(["--profile", str(p), "--strict"]) == EXIT_PROFILE_ERROR


def test_reconcile_strict_blocks_invalid_toml(tmp_path):
    p = tmp_path / "broken.toml"
    p.write_text("box = = =\n", encoding="utf-8")
    assert reconcile_main(["--profile", str(p), "--strict"]) == EXIT_PROFILE_ERROR


def test_reconcile_strict_json_lists_issues(tmp_path, capsys):
    import json

    p = tmp_path / "typo.toml"
    p.write_text('box = "b"\n[[checks]]\nid = "nope"\n', encoding="utf-8")
    rc = reconcile_main(["--profile", str(p), "--strict", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == EXIT_PROFILE_ERROR and out["error"] == "invalid profile" and out["issues"]


def test_reconcile_strict_allows_valid_profile(tmp_path):
    # A shape-valid profile is never rejected by --strict (it may still run and report
    # drift, but that is exit 0/1, never the profile-error code).
    p = tmp_path / "ok.toml"
    p.write_text('box = "b"\n[[checks]]\nid = "floors"\n', encoding="utf-8")
    assert reconcile_main(["--profile", str(p), "--strict"]) != EXIT_PROFILE_ERROR
