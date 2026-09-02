"""The content-addressed store: record/fetch, streamed record_path, dedup, hash-named objects."""

from orrery.integrity.store import Store, hash_bytes


def test_record_and_fetch(tmp_path):
    s = Store(tmp_path / "cas")
    h = s.record(b"hello")
    assert h == hash_bytes(b"hello")
    assert s.has(h)
    assert s.fetch(h) == b"hello"


def test_fetch_absent_is_none(tmp_path):
    assert Store(tmp_path / "cas").fetch("0" * 64) is None


def test_object_is_named_by_its_hash(tmp_path):
    s = Store(tmp_path / "cas")
    h = s.record(b"abc")
    assert (tmp_path / "cas" / h[:2] / h[2:]).read_bytes() == b"abc"


def test_record_path_streams_hashes_and_matches(tmp_path):
    s = Store(tmp_path / "cas")
    f = tmp_path / "f.bin"
    f.write_bytes(b"some content")
    h = s.record_path(f)
    assert h == hash_bytes(b"some content")
    assert s.fetch(h) == b"some content"


def test_identical_content_dedups(tmp_path):
    s = Store(tmp_path / "cas")
    (tmp_path / "a").write_bytes(b"same")
    (tmp_path / "b").write_bytes(b"same")
    h1 = s.record_path(tmp_path / "a")
    h2 = s.record_path(tmp_path / "b")
    assert h1 == h2
    # exactly one object stored under the shared hash
    assert (tmp_path / "cas" / h1[:2] / h1[2:]).is_file()


def test_record_is_idempotent(tmp_path):
    s = Store(tmp_path / "cas")
    h1 = s.record(b"x")
    h2 = s.record(b"x")
    assert h1 == h2 and s.fetch(h1) == b"x"
