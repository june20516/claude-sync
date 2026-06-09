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


def test_classify_repo_only():
    assert ss.classify(None, "r", None, local_exists=False, repo_exists=True) == "repo_only"


def test_classify_local_only():
    assert ss.classify("l", None, None, local_exists=True, repo_exists=False) == "local_only"


def test_classify_in_sync_equal():
    assert ss.classify("a", "a", "x", True, True) == "in_sync"


def test_classify_local_ahead():
    # 로컬만 변경(L!=S), remote는 그대로(R==S)
    assert ss.classify("L", "S", "S", True, True) == "local_ahead"


def test_classify_fast_forward():
    # remote만 변경(R!=S), 로컬은 그대로(L==S)
    assert ss.classify("S", "R", "S", True, True) == "fast_forward"


def test_classify_conflict_both_changed():
    assert ss.classify("L", "R", "S", True, True) == "conflict"


def test_classify_conflict_no_base():
    # base 없음 + 둘 다 존재 + 다름 → conflict
    assert ss.classify("L", "R", None, True, True) == "conflict"
