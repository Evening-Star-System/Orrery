from orrery.reconciler.checks.deployed_image import DeployedImageCheck
from orrery.reconciler.model import Severity


class FakeProber:
    """Returns scripted probe output, so tests never touch ssh."""

    def __init__(self, out: str, rc: int = 0, raise_: bool = False):
        self._out, self._rc, self._raise = out, rc, raise_

    def can_reach(self, host, timeout):
        return True

    def read(self, host, command, timeout):
        if self._raise:
            raise OSError("boom")
        return (self._rc, self._out)


def _mk(ps, psa, cfd):
    return (
        "#PS\n" + "\n".join(ps) + "\n"
        "#PSA\n" + "\n".join(psa) + "\n"
        "#CFD\n" + "\n".join(cfd) + "\n#END\n"
    )


_GOOD = _mk(
    ps=[
        "games-web-abc||ghcr.io/aitomus/games:sha123||",
        "kamal-proxy||basecamp/kamal-proxy||127.0.0.1:80->80/tcp",
    ],
    psa=["games-web-abc", "kamal-proxy"],
    cfd=["active"],
)


def _run(out, rc=0, tag="sha123", raise_=False, host="df-box"):
    check = DeployedImageCheck(prober=FakeProber(out, rc, raise_))
    return check.run(
        {"host": host, "image": "ghcr.io/aitomus/games", "tag": tag, "timeout": 1}, box=None
    )


def test_good_box_no_fail_or_drift():
    fs = _run(_GOOD)
    sev = {f.severity for f in fs}
    assert Severity.FAIL not in sev and Severity.DRIFT not in sev
    assert any(f.severity == Severity.OK and "declared tag" in f.message for f in fs)
    assert any(f.severity == Severity.OK and "loopback-only" in f.message for f in fs)
    assert any(f.severity == Severity.INFO for f in fs)  # CF Access = external, not a false pass


def test_wrong_tag_is_drift():
    fs = _run(_GOOD, tag="sha999")
    d = [f for f in fs if f.severity == Severity.DRIFT]
    assert d and d[0].expected == "ghcr.io/aitomus/games:sha999"


def test_public_port_fails():
    out = _mk(
        ps=[
            "games-web||ghcr.io/aitomus/games:sha123||",
            "kamal-proxy||x||0.0.0.0:80->80/tcp",
        ],
        psa=["kamal-proxy"],
        cfd=["active"],
    )
    fs = _run(out)
    assert any(f.severity == Severity.FAIL and "PUBLIC" in f.message for f in fs)


def test_coolify_present_fails():
    out = _mk(
        ps=[
            "games-web||ghcr.io/aitomus/games:sha123||",
            "kamal-proxy||x||127.0.0.1:80->80/tcp",
        ],
        psa=["kamal-proxy", "coolify-proxy"],
        cfd=["active"],
    )
    fs = _run(out)
    assert any(f.severity == Severity.FAIL and "coolify" in f.message.lower() for f in fs)


def test_no_cloudflared_fails():
    out = _mk(
        ps=["games-web||ghcr.io/aitomus/games:sha123||", "kamal-proxy||x||127.0.0.1:80->80/tcp"],
        psa=["kamal-proxy"],
        cfd=["inactive"],
    )
    fs = _run(out)
    assert any(f.severity == Severity.FAIL and "cloudflared" in f.message for f in fs)


def test_unmeasurable_box_warns_not_clean():
    (f,) = _run("", rc=255)
    assert f.severity == Severity.WARN


def test_prober_error_warns():
    fs = _run(_GOOD, raise_=True)
    assert fs[0].severity == Severity.WARN


def test_unsafe_host_refused():
    check = DeployedImageCheck(prober=FakeProber(_GOOD))
    (f,) = check.run({"host": "-oProxyCommand=x", "image": "ghcr.io/aitomus/games"}, box=None)
    assert f.severity == Severity.WARN
