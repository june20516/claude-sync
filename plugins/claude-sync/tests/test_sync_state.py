import os

import pytest

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


def test_merge_clean_non_overlapping():
    base = b"a\nb\nc\nd\ne\n"
    local = b"a\nB\nc\nd\ne\n"   # 2번 줄 변경
    repo = b"a\nb\nc\nD\ne\n"    # 4번 줄 변경
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts == 0
    assert merged == b"a\nB\nc\nD\ne\n"


def test_merge_conflict_overlapping():
    base = b"a\nb\nc\n"
    local = b"a\nX\nc\n"
    repo = b"a\nY\nc\n"
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts > 0
    assert b"<<<<<<<" in merged


def test_merge_identical_change_no_conflict():
    base = b"a\nb\nc\n"
    local = b"a\nZ\nc\n"
    repo = b"a\nZ\nc\n"
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts == 0
    assert merged == b"a\nZ\nc\n"


def test_merge_clean_no_trailing_newline():
    base = b"a\nb\nc"
    local = b"A\nb\nc"
    repo = b"a\nb\nC"
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts == 0
    assert merged == b"A\nb\nC"


def test_iter_synced_relpaths(tmp_path):
    root = tmp_path
    (root / "agents").mkdir()
    (root / "agents" / "a.md").write_text("x")
    (root / "skills" / "s").mkdir(parents=True)
    (root / "skills" / "s" / "SKILL.md").write_text("y")
    (root / "CLAUDE.md").write_text("z")
    (root / "settings.json").write_text("{}")  # 대상 아님
    got = set(ss.iter_synced_relpaths(str(root)))
    assert got == {"agents/a.md", "skills/s/SKILL.md", "CLAUDE.md"}


def test_write_base_leaves_old_blob_intact_when_write_fails(tmp_path, monkeypatch):
    """base 블롭도 같다 — 잘린 base는 parse_base가 None으로 읽어 합집합 degrade를 부른다."""
    base_dir = str(tmp_path / "base")
    ss.write_base("plugins.json", b'{"version": 2}', base_dir=base_dir)
    real_open = open

    def fail_on_tmp(path, *args, **kwargs):
        if str(path).endswith(".tmp"):
            raise OSError("disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fail_on_tmp)
    with pytest.raises(OSError):
        ss.write_base("plugins.json", b"truncated", base_dir=base_dir)
    monkeypatch.undo()
    assert ss.read_base("plugins.json", base_dir=base_dir) == b'{"version": 2}'
    assert os.listdir(base_dir) == ["plugins.json"]


def test_write_base_removes_its_temp_file_on_non_oserror_failure(tmp_path):
    """OSError가 아닌 실패(bytes가 아닌 값)도 .tmp를 지워야 한다.

    open(tmp, "wb")는 성공하고, 그 뒤 f.write(data)가 bytes가 아닌 값에서 TypeError를
    던진다 — open이 이미 성공한 뒤에 터져야 .tmp가 디스크에 남은 상태에서 정리 코드가
    실제로 실행되는 경로를 검증한다. 위 테스트(open 이전에 실패)는 .tmp가 애초에
    생성되지 않으므로 이 정리 경로를 잡지 못한다.
    except를 OSError로 좁히면(X2) TypeError가 정리 코드를 우회해 .tmp가 남고,
    os.remove(tmp)를 지우면(X1) 성공 여부와 무관하게 .tmp가 남는다.
    """
    base_dir = str(tmp_path / "base")
    ss.write_base("plugins.json", b'{"version": 2}', base_dir=base_dir)
    with pytest.raises(TypeError):
        ss.write_base("plugins.json", "not bytes", base_dir=base_dir)
    assert os.listdir(base_dir) == ["plugins.json"]
    assert ss.read_base("plugins.json", base_dir=base_dir) == b'{"version": 2}'
