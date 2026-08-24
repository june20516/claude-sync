"""값 무관 코어의 단위 테스트. 도메인 지식은 전부 훅으로 들어온다."""
import json

import pytest

import keyed_sync as ks


def test_claims_newer_schema_blocks_float_bypass():
    """float 버전 주장을 막는다. jq·YAML 변환기·다른 언어 writer가 실제로 만드는 형태다."""
    assert ks.claims_newer_schema(3, 2) is True
    assert ks.claims_newer_schema(3.0, 2) is True
    assert ks.claims_newer_schema(2, 2) is False


def test_claims_newer_schema_ignores_bool_and_string():
    """True는 int의 인스턴스지만 버전 주장이 아니다. 문자열은 손으로 고친 문서를 막지 않는다."""
    assert ks.claims_newer_schema(True, 2) is False
    # bool 가드가 없으면 True(==1) > 0이 참이 되어 여기서 실제로 FAIL한다.
    # schema_version=2 조합은 1 > 2가 우연히 거짓이라 가드 삭제를 잡지 못한다.
    assert ks.claims_newer_schema(True, 0) is False
    assert ks.claims_newer_schema("3", 2) is False
    assert ks.claims_newer_schema(None, 2) is False


def test_decode_distinguishes_broken_from_falsy():
    """None·0·false 같은 유효한 falsy 값과 디코드 실패를 구별해야 한다."""
    assert ks.decode(b"null") is None
    assert ks.decode(b"0") == 0
    assert ks.decode(b"{oops") is ks.BROKEN
    # 센티널이 None이면 이 줄이 FAIL한다. 위 세 줄만으로는 BROKEN = None을 못 잡는다.
    assert ks.decode(b"null") is not ks.BROKEN
    # 유효하지 않은 UTF-8도 BROKEN이어야 한다. except에서 UnicodeDecodeError를 빼면 이 줄이 FAIL한다.
    assert ks.decode(b"\xff") is ks.BROKEN


def test_same_ignores_key_order():
    assert ks.same({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True
    assert ks.same({"a": 1}, {"a": 2}) is False
    # 지문 비교라야 잡히는 차이. same을 `a == b`로 바꾸면 아래 두 줄이 FAIL한다.
    # 레포 파일을 다른 도구(jq 등)가 쓰면 1이 1.0으로 바뀌어 들어올 수 있다.
    assert ks.same(1, 1.0) is False
    assert ks.same(1, True) is False


def test_fingerprint_keeps_non_ascii_literal():
    """ensure_ascii=False가 살아 있어야 지문이 디스크 표현과 같은 옵션을 쓴다는 주장이 참이 된다."""
    assert ks.fingerprint({"k": "한"}) == '{"k": "한"}'


def test_no_hold_returns_two_empty_sets():
    """어댑터가 '보류 없음'을 표현하는 기본 훅."""
    h = ks.no_hold({"x": 1}, {"y": 2})
    assert h["value"] == frozenset() and h["action"] == frozenset()


def only_dict_with_items(obj):
    """테스트용 recognize 훅 — {"items": {...}} 만 인정한다."""
    if isinstance(obj, dict) and isinstance(obj.get("items"), dict):
        if ks.claims_newer_schema(obj.get("version"), 2):
            return None
        return dict(obj["items"])
    return None


def test_parse_base_returns_none_for_untrusted_history():
    """이력을 못 믿으면 {}가 아니라 None이다. {}는 삭제 판정의 근거가 된다."""
    assert ks.parse_base(None, only_dict_with_items) is None
    assert ks.parse_base(b"{oops", only_dict_with_items) is None
    assert ks.parse_base(b'{"nope": 1}', only_dict_with_items) is None
    assert ks.parse_base(b'{"items": {}}', only_dict_with_items) == {}


def test_load_backup_raises_on_unrecognized_document(tmp_path):
    """알아볼 수 없는 문서는 {}로 degrade하지 않는다 — 덮어쓰면 파괴한다."""
    path = tmp_path / "backup.json"
    path.write_text(json.dumps({"version": 3, "items": {"a": 1}}), encoding="utf-8")
    with pytest.raises(ks.UnknownBackupSchema):
        ks.load_backup(str(path), only_dict_with_items)


def test_load_backup_returns_empty_when_file_missing(tmp_path):
    assert ks.load_backup(str(tmp_path / "none.json"), only_dict_with_items) == {}


def test_load_backup_degrades_broken_syntax_to_empty(tmp_path):
    """구문이 깨진 파일 하나가 백업 전체를 막지 않는다. 다음 백업이 되돌린다."""
    path = tmp_path / "backup.json"
    path.write_text("{oops", encoding="utf-8")
    assert ks.load_backup(str(path), only_dict_with_items) == {}


def test_parse_backup_is_lenient():
    assert ks.parse_backup(b"{oops", only_dict_with_items) == {}
    assert ks.parse_backup(b'{"nope": 1}', only_dict_with_items) == {}
    assert ks.parse_backup(b'{"items": {"a": 1}}', only_dict_with_items) == {"a": 1}
