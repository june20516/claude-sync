"""값 무관 코어의 단위 테스트. 도메인 지식은 전부 훅으로 들어온다."""
import keyed_sync as ks


def test_claims_newer_schema_blocks_float_bypass():
    """float 버전 주장을 막는다. jq·YAML 변환기·다른 언어 writer가 실제로 만드는 형태다."""
    assert ks.claims_newer_schema(3, 2) is True
    assert ks.claims_newer_schema(3.0, 2) is True
    assert ks.claims_newer_schema(2, 2) is False


def test_claims_newer_schema_ignores_bool_and_string():
    """True는 int의 인스턴스지만 버전 주장이 아니다. 문자열은 손으로 고친 문서를 막지 않는다."""
    assert ks.claims_newer_schema(True, 2) is False
    assert ks.claims_newer_schema("3", 2) is False
    assert ks.claims_newer_schema(None, 2) is False


def test_decode_distinguishes_broken_from_falsy():
    """None·0·false 같은 유효한 falsy 값과 디코드 실패를 구별해야 한다."""
    assert ks.decode(b"null") is None
    assert ks.decode(b"0") == 0
    assert ks.decode(b"{oops") is ks.BROKEN


def test_same_ignores_key_order():
    assert ks.same({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True
    assert ks.same({"a": 1}, {"a": 2}) is False


def test_no_hold_returns_two_empty_sets():
    """어댑터가 '보류 없음'을 표현하는 기본 훅."""
    h = ks.no_hold({"x": 1}, {"y": 2})
    assert h["value"] == frozenset() and h["action"] == frozenset()
