import sync_state as ss


def test_content_hash_stable():
    assert ss.content_hash(b"hello") == ss.content_hash(b"hello")
    assert ss.content_hash(b"a") != ss.content_hash(b"b")


def test_file_hash_missing_returns_none(tmp_path):
    assert ss.file_hash(str(tmp_path / "nope")) is None


def test_file_hash_matches_content(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"data")
    assert ss.file_hash(str(p)) == ss.content_hash(b"data")


def test_base_roundtrip(tmp_path):
    bd = str(tmp_path / "base")
    ss.write_base("agents/x.md", b"hello", base_dir=bd)
    assert ss.read_base("agents/x.md", base_dir=bd) == b"hello"
    assert ss.base_hash("agents/x.md", base_dir=bd) == ss.content_hash(b"hello")


def test_base_missing_returns_none(tmp_path):
    bd = str(tmp_path / "base")
    assert ss.read_base("nope.md", base_dir=bd) is None
    assert ss.base_hash("nope.md", base_dir=bd) is None


def test_write_base_none_deletes(tmp_path):
    bd = str(tmp_path / "base")
    ss.write_base("a.md", b"x", base_dir=bd)
    ss.write_base("a.md", None, base_dir=bd)
    assert ss.read_base("a.md", base_dir=bd) is None
