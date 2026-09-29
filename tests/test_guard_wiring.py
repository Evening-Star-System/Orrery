from orrery.reconciler.checks.guard_wiring import GuardWiringCheck
from orrery.reconciler.model import Severity


class FakeBox:
    """Filesystem answers from a dict; presence = key present, contents = value."""

    def __init__(self, files: dict):
        self._files = files

    def exists(self, path: str) -> bool:
        return path in self._files

    def read_text(self, path: str):
        return self._files.get(path)


_SETTINGS_OK = (
    '{"hooks":{"PreToolUse":[{"hooks":['
    '{"command":"python3 /h/block-a.py"},'
    '{"command":"python3 /h/block-b.py"}]}]}}'
)


def _run(files, guards, hooks_dir="/h", settings="/s.json"):
    return GuardWiringCheck().run(
        {"hooks_dir": hooks_dir, "settings": settings, "guards": guards}, FakeBox(files)
    )


def test_present_and_wired_all_ok():
    files = {"/s.json": _SETTINGS_OK, "/h/block-a.py": "x", "/h/block-b.py": "x"}
    fs = _run(files, ["block-a.py", "block-b.py"])
    assert fs and all(f.severity == Severity.OK for f in fs)


def test_present_but_unwired_fails():
    files = {"/s.json": _SETTINGS_OK, "/h/block-c.py": "x"}  # present on disk, absent from settings
    (f,) = _run(files, ["block-c.py"])
    assert f.severity == Severity.FAIL and "NOT wired" in f.message


def test_missing_from_hooks_dir_fails():
    files = {"/s.json": _SETTINGS_OK}  # wired in settings but the file is gone
    (f,) = _run(files, ["block-a.py"])
    assert f.severity == Severity.FAIL and "MISSING" in f.message


def test_malformed_settings_warns_not_pass():
    files = {"/s.json": "{ not json", "/h/block-a.py": "x"}
    (f,) = _run(files, ["block-a.py"])
    assert f.severity == Severity.WARN


def test_unreadable_settings_warns():
    files = {"/h/block-a.py": "x"}  # settings path absent -> read_text None
    (f,) = _run(files, ["block-a.py"])
    assert f.severity == Severity.WARN


def test_missing_options_warns():
    (f,) = GuardWiringCheck().run({}, FakeBox({}))
    assert f.severity == Severity.WARN
