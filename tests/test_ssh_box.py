from orrery.reconciler.box import SshBox


class Fake:
    """Records the remote command and returns a scripted (rc, stdout)."""

    def __init__(self, rc=0, out=b""):
        self.rc = rc
        self.out = out
        self.cmds = []

    def __call__(self, cmd):
        self.cmds.append(cmd)
        return (self.rc, self.out)


def test_exists_true_false():
    f = Fake(rc=0)
    assert SshBox("h", runner=f).exists("/etc/hostname") is True
    assert "test -e" in f.cmds[-1] and "/etc/hostname" in f.cmds[-1]
    assert SshBox("h", runner=Fake(rc=1)).exists("/nope") is False


def test_non_absolute_path_is_rejected_without_calling_ssh():
    f = Fake(rc=0)
    box = SshBox("h", runner=f)
    assert box.exists("relative/path") is False
    assert box.read_text("-rf") is None       # a flag-shaped value never reaches ssh
    assert box.file_meta("../x") is None
    assert box.list_files("etc") is None
    assert f.cmds == []


def test_read_text_decodes_or_none():
    assert SshBox("h", runner=Fake(0, b"hello\n")).read_text("/a") == "hello\n"
    assert SshBox("h", runner=Fake(1, b"")).read_text("/a") is None
    assert SshBox("h", runner=Fake(0, b"\xff\xfe\x00")).read_text("/a") is None  # non-utf8


def test_read_text_is_regular_file_and_bounded():
    f = Fake(0, b"x")
    SshBox("h", runner=f).read_text("/a")
    assert "test -f" in f.cmds[-1] and "head -c 1000001" in f.cmds[-1]


def test_list_files_splits_lines():
    f = Fake(0, b"/a/1\n/a/2\n")
    got = SshBox("h", runner=f).list_files("/a", 50)
    assert got == ["/a/1", "/a/2"]
    assert "find" in f.cmds[-1] and "-type f" in f.cmds[-1] and "head -n 50" in f.cmds[-1]


def test_file_meta_parses_uid_and_octal_mode():
    assert SshBox("h", runner=Fake(0, b"0 644\n")).file_meta("/a") == (0, 0o644)
    assert SshBox("h", runner=Fake(0, b"1000 755\n")).file_meta("/a") == (1000, 0o755)
    assert SshBox("h", runner=Fake(1, b"")).file_meta("/a") is None
    assert SshBox("h", runner=Fake(0, b"garbage")).file_meta("/a") is None


def test_paths_are_shell_quoted():
    f = Fake(0, b"")
    SshBox("h", runner=f).exists("/weird path/$(rm -rf)")
    # the dangerous characters are quoted, not interpolated
    assert "'/weird path/$(rm -rf)'" in f.cmds[-1]
