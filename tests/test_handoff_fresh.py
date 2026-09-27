"""handoff-freshness reconciler check."""
import time

from orrery.reconciler.checks.handoff_fresh import HandoffFreshnessCheck, START, END
from orrery.reconciler.model import Severity
from orrery.reconciler.registry import get_check


class FakeBox:
    def __init__(self, files):
        self.files = files  # path -> (text, mtime_epoch)

    def exists(self, p):
        return p in self.files

    def read_text(self, p):
        v = self.files.get(p)
        return v[0] if v else None

    def file_meta(self, p):
        v = self.files.get(p)
        return (len(v[0].encode()), v[1]) if v else None


def _sev(findings, subject):
    return next(f.severity for f in findings if f.subject == subject)


def test_registered():
    assert get_check("handoff-freshness") is not None


def test_present_and_fresh_is_ok():
    now = time.time()
    box = FakeBox({"/p/.dev/DIGEST.md": (f"{START}\nWHERE: x\n{END}\nbody", now)})
    out = HandoffFreshnessCheck().run({"handoffs": [{"path": "/p/.dev/DIGEST.md"}]}, box)
    assert _sev(out, "/p/.dev/DIGEST.md") == Severity.OK


def test_missing_block_is_fail():
    box = FakeBox({"/p/.dev/DIGEST.md": ("no markers here", time.time())})
    out = HandoffFreshnessCheck().run({"handoffs": [{"path": "/p/.dev/DIGEST.md"}]}, box)
    assert _sev(out, "/p/.dev/DIGEST.md") == Severity.FAIL


def test_absent_digest_is_fail():
    out = HandoffFreshnessCheck().run({"handoffs": [{"path": "/nope"}]}, FakeBox({}))
    assert _sev(out, "/nope") == Severity.FAIL


def test_stale_block_is_warn():
    old = time.time() - 40 * 86400
    box = FakeBox({"/p/.dev/DIGEST.md": (f"{START}\nx\n{END}", old)})
    out = HandoffFreshnessCheck().run(
        {"handoffs": [{"path": "/p/.dev/DIGEST.md", "max_age_days": 14}]}, box
    )
    assert _sev(out, "/p/.dev/DIGEST.md") == Severity.WARN
