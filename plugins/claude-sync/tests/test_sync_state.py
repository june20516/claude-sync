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


def test_write_base_records_an_empty_blob_instead_of_deleting_it(tmp_path):
    """`b""`(빈 문서)와 `None`(삭제)은 다른 입력이다 — 접으면 조용한 오탐이 난다.

    변조 `if data is None:` → `if not data:`가 스위트 전체에서 살아남아 이 테스트가
    생겼다. 동기화 대상 중 **빈 파일**(빈 CLAUDE.md, 빈 agent 파일)이 있으면
    reconcile_restore가 `write_base(rel, b"")`를 부르는데, 접힌 코드는 그것을 삭제로
    읽어 base를 지운다. 그러면 `base_hash`가 None이 되고, 그 파일이 다음에 갈릴 때
    `changed_local`·`changed_remote`가 **둘 다 참**이 되어 fast_forward여야 할 것이
    conflict로 판정된다 — 그리고 base가 없으니 머지도 못 해 `no_base` 충돌로 남는다.
    이 저장소가 `parse_base`의 docstring에 적어 둔 그 구별이다.
    """
    bd = str(tmp_path / "base")
    ss.write_base("empty.md", b"", base_dir=bd)
    assert ss.read_base("empty.md", base_dir=bd) == b""
    assert ss.base_hash("empty.md", base_dir=bd) == ss.content_hash(b"")


def test_write_base_delete_also_removes_a_stray_temp_file(tmp_path):
    """삭제 분기가 `<path>.tmp`를 남기지 않는다.

    **현재 영향은 없다 — 버그 수정이 아니라 위생이다.** 실측 둘로 그것을 못 박는다:
    (a) base 디렉토리를 walk하는 코드가 이 저장소에 없다(소비자는 전부 relpath 하나를
    `read_base`로 읽는다), (b) `write_base(rel, None)`을 부르는 프로덕션 호출자도 없다.
    그래서 남은 `.tmp`가 지금 무엇을 망가뜨리지는 않는다. 다음 독자가 이 줄을 "무슨
    사고를 막았나" 하고 되짚지 않도록 적어 둔다.

    `.tmp`는 `dump_bytes`가 `os.replace` 전에 SIGKILL로 죽으면 남는다(정상 실패 경로는
    스스로 지운다). 그 뒤 같은 relpath를 삭제하면 최종 파일만 사라지고 `.tmp`가 base
    디렉토리에 영구히 남는다 — 그것을 지운다.
    """
    bd = str(tmp_path / "base")
    ss.write_base("a.md", b"x", base_dir=bd)
    stray = ss.base_blob_path("a.md", base_dir=bd) + ".tmp"
    with open(stray, "wb") as f:
        f.write(b"half-written")
    ss.write_base("a.md", None, base_dir=bd)
    assert os.listdir(bd) == []


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


def test_write_base_routes_through_ks_dump_bytes(tmp_path, monkeypatch):
    """write_base가 실제로 ks.dump_bytes를 거치는지 고정한다 — I1의 재발을 여기서 잡는다.

    위 두 테스트는 "원자적인가"만 본다 — 원자적 패턴을 write_base가 직접 복사해도
    통과한다. 라우팅 자체를 단정해야 dump_bytes의 docstring이 경고하는 "두 어댑터가
    각자 복사하면 다음 수정이 한쪽에만 반영된다"는 재발을 이 파일에서도 잡는다.
    """
    calls = []
    monkeypatch.setattr(ss.ks, "dump_bytes", lambda data, target: calls.append((data, target)))
    base_dir = str(tmp_path / "base")
    ss.write_base("plugins.json", b"payload", base_dir=base_dir)
    assert calls == [(b"payload", ss.base_blob_path("plugins.json", base_dir))]
