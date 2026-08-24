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


def test_load_backup_propagates_permission_error(tmp_path):
    """FileNotFoundError만 {}로 접는다. 다른 OSError를 접으면 못 읽은 백업이
    "항목 0개"가 되고, merge가 그 레포를 덮어써 파괴한다."""
    path = tmp_path / "backup.json"
    path.write_text(json.dumps({"items": {"a": 1}}), encoding="utf-8")
    path.chmod(0)
    try:
        # except FileNotFoundError를 except OSError로 넓히면 PermissionError가
        # {}로 접혀 이 raises가 FAIL한다.
        with pytest.raises(PermissionError):
            ks.load_backup(str(path), only_dict_with_items)
    finally:
        path.chmod(0o644)


def test_load_backup_reads_file_as_bytes_so_invalid_utf8_degrades_to_empty(tmp_path):
    """"rb"가 아니면 잘못된 UTF-8이 파일을 여는 시점에 UnicodeDecodeError로
    전파된다. 바이너리로 읽어야 decode()가 그 바이트를 받아 BROKEN으로 판정하고
    {}로 degrade한다.
    """
    path = tmp_path / "backup.json"
    path.write_bytes(b"\xff")
    # open(path, "rb")를 open(path, "r")로 바꾸면 f.read()에서 UnicodeDecodeError가
    # 그대로 터져 이 assert에 도달하지 못하고 이 테스트가 FAIL한다.
    assert ks.load_backup(str(path), only_dict_with_items) == {}


def test_parse_backup_is_lenient():
    assert ks.parse_backup(b"{oops", only_dict_with_items) == {}
    assert ks.parse_backup(b'{"nope": 1}', only_dict_with_items) == {}
    assert ks.parse_backup(b'{"items": {"a": 1}}', only_dict_with_items) == {"a": 1}


def mask_secret(mapping):
    """테스트용 normalize 훅 — 'secret' 필드 값을 가린다. 멱등이다."""
    out = {}
    for key, value in mapping.items():
        if isinstance(value, dict) and "secret" in value:
            copied = dict(value)
            copied["secret"] = "<X>"
            out[key] = copied
        else:
            out[key] = value
    return out


def hold_keys(value=(), action=()):
    """지정한 키를 보류로 만드는 훅 팩토리."""
    def _hold(local, repo):
        return {"value": frozenset(value), "action": frozenset(action)}
    return _hold


def test_diff_applies_normalize_to_both_sides():
    """로컬은 평문, 레포는 마스킹됨. 정규화 없이 비교하면 영원히 changed가 된다."""
    local = {"a": {"secret": "plain"}}
    repo = {"a": {"secret": "<X>"}}
    out = ks.diff(local, repo, normalize=mask_secret, hold=ks.no_hold)
    assert out["changed"] == []


def trim_whitespace(mapping):
    """테스트용 normalize 훅 — 문자열 값의 앞뒤 공백을 제거한다. 멱등이다.

    mask_secret과 달리 repo 쪽 원본이 이미 정규화된 형태가 아니므로, local만 정규화하고
    repo를 원본 그대로 두는 변조도 이 훅으로는 숨을 곳이 없다.
    """
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in mapping.items()}


def test_diff_applies_normalize_to_local_side_too():
    """local만 정규화해도 repo가 우연히 이미 정규화된 형태라 앞의 테스트를 통과할 수 있다
    (mask_secret은 멱등이라 repo="<X>"는 이미 정규화된 값과 같다). 양쪽 다 원본이
    미정규화 상태인 값을 써서, local 쪽 정규화 누락도 changed로 드러나게 한다.
    """
    local = {"a": "value "}
    repo = {"a": " value"}
    # local, repo = normalize(local), repo (변조 2: local만 정규화)로 바꾸면
    # repo가 " value"로 남아 local의 "value"와 달라 changed=["a"]가 되어 이 줄이 FAIL한다.
    out = ks.diff(local, repo, normalize=trim_whitespace, hold=ks.no_hold)
    assert out["changed"] == []


def test_diff_reports_three_buckets():
    out = ks.diff({"a": 1, "b": 1}, {"b": 2, "c": 1},
                  normalize=lambda m: m, hold=ks.no_hold)
    assert out["only_local"] == ["a"]
    assert out["only_repo"] == ["c"]
    assert out["changed"] == ["b"]
    assert out["held"] == []


def test_diff_moves_held_keys_out_of_all_three_buckets():
    """보류 키는 only_local/only_repo/changed 어디에도 들어가지 않는다."""
    out = ks.diff({"a": 1, "b": 1}, {"b": 2, "c": 1},
                  normalize=lambda m: m, hold=hold_keys(value=("a", "b", "c")))
    assert out["only_local"] == [] and out["only_repo"] == [] and out["changed"] == []
    assert out["held"] == ["a", "b", "c"]


def test_diff_buckets_are_sorted():
    """네 버킷은 전부 정렬된 리스트다 — 사용자에게 그대로 보고되는 순서이므로 결정론이어야 한다.

    set의 순회 순서는 파이썬 프로세스마다 무작위인 문자열 해시에 의존한다. 원소를 2~3개만
    쓰면 set 순회 순서가 우연히 정렬 순서와 같아져 sorted를 list로 바꾼 변조(변조 6)를
    놓칠 수 있다. 10개 키를 삽입 순서와 다르게 넣어 우연히 일치할 확률을 무시할 수준으로
    낮춘다 — sorted(...)를 list(...)로 바꾸면 이 네 단언 중 최소 하나는 거의 모든 실행에서
    FAIL한다. 재현: `PYTHONHASHSEED=<n> pytest -k buckets_are_sorted`를 여러 시드로
    돌려 확인한다.
    """
    keys = ["j", "h", "f", "d", "b", "i", "g", "e", "c", "a"]
    expected = sorted(keys)

    only_local = ks.diff({k: 1 for k in keys}, {}, normalize=lambda m: m, hold=ks.no_hold)
    assert only_local["only_local"] == expected

    only_repo = ks.diff({}, {k: 1 for k in keys}, normalize=lambda m: m, hold=ks.no_hold)
    assert only_repo["only_repo"] == expected

    changed = ks.diff({k: 1 for k in keys}, {k: 2 for k in keys},
                       normalize=lambda m: m, hold=ks.no_hold)
    assert changed["changed"] == expected

    held = ks.diff({k: 1 for k in keys}, {}, normalize=lambda m: m, hold=hold_keys(value=keys))
    assert held["held"] == expected


def recording_hold(seen):
    """hold가 받은 인자를 그대로 기록하는 훅."""
    def _hold(local, repo):
        seen.append((dict(local), dict(repo)))
        return {"value": frozenset(), "action": frozenset()}
    return _hold


def test_diff_gives_hold_normalized_local_and_repo_in_that_order():
    """hold는 정규화된 입력을 (local, repo) 순서로 정확히 한 번 받는다(훅 계약).

    plugin_config의 hold 넷은 좌우 대칭이 아니다 — H3는 '레포 값'을, H1·H2는 로컬을 본다.
    순서가 뒤집히거나 미정규화 값이 넘어가면 보류 판정이 조용히 반대로 선다(spec 7.3).
    """
    seen = []
    ks.diff({"a": "x "}, {"b": " y"},
            normalize=trim_whitespace, hold=recording_hold(seen))
    # seen == [...] 단일 원소 리스트 동등이므로 값(정규화됨)·순서(local, repo)·
    # 호출 횟수(정확히 1회)를 한 번에 고정한다. value_held를 정규화 전 값으로 계산하거나
    # hold(repo, local)로 좌우를 뒤집으면 이 줄이 FAIL한다.
    assert seen == [({"a": "x"}, {"b": "y"})]


def test_diff_rejects_normalize_that_drops_keys():
    """키 층위 제외를 normalize로 하면 merge가 그것을 케이스 3(삭제)으로 읽는다(spec 5.2)."""
    with pytest.raises(ValueError):
        ks.diff({"a": 1, "b": 1}, {"a": 1},
                normalize=lambda m: {k: v for k, v in m.items() if k != "b"},
                hold=ks.no_hold)


def test_diff_reports_held_key_absent_from_both_sides():
    """보류 훅이 어느 쪽에도 없는 키를 지목해도 held에 그대로 실린다(merge와 같은 형태).

    held를 value_held & (set(local) | set(repo))로 좁히면 "ghost"가 걸러져 이 줄이 FAIL한다.
    """
    out = ks.diff({"a": 1}, {"a": 1}, normalize=lambda m: m,
                  hold=hold_keys(value=("ghost",)))
    assert out["held"] == ["ghost"]


def test_next_base_advances_only_where_local_agrees():
    """타 기기가 추가·변경한 값을 base에 기록하면 다음 백업이 '내가 삭제했다'로 오독한다."""
    out = ks.next_base({"mine": 1}, {"mine": 1, "theirs": 0}, {"mine": 1, "theirs": 9},
                       normalize=lambda m: m)
    assert out["mine"] == 1      # 로컬이 동의 → 전진
    assert out["theirs"] == 0    # 로컬이 동의 안 함 → 이전 base 유지


def test_next_base_drops_keys_absent_from_both_sides():
    out = ks.next_base({}, {"gone": 1}, {}, normalize=lambda m: m)
    assert "gone" not in out


def test_next_base_keeps_old_only_keys_when_local_still_has_them():
    """old(base)에는 있고 merged에는 없지만 local은 여전히 갖고 있는 키는 "이전 base 유지" 갈래를 탄다.

    (예: 타 기기 삭제를 아직 로컬에 반영하기 전.) 순회 대상을 `sorted(set(merged))`로
    좁히면(변조 10) 이 키가 애초에 순회에 안 잡혀 조용히 사라진다 — 위
    test_next_base_drops_keys_absent_from_both_sides는 local도 비어 있어 결과가 "드롭"으로
    우연히 같아 이 차이를 못 잡는다.
    """
    out = ks.next_base({"stale": 1}, {"stale": 1}, {}, normalize=lambda m: m)
    assert out["stale"] == 1


def test_next_base_removes_value_held_keys():
    """값 보류 키를 base에 남기면 해제 시 케이스 3(삭제)이 난다."""
    out = ks.next_base({"h": 1, "n": 1}, {"h": 1, "n": 1}, {"h": 1, "n": 1},
                       normalize=lambda m: m, value_held={"h"})
    assert "h" not in out
    assert out["n"] == 1


def test_next_base_applies_normalize_so_secrets_do_not_leak():
    """restore가 평문 로컬을 넘겨도 base 블롭에 평문이 기록되면 안 된다."""
    out = ks.next_base({"a": {"secret": "plain"}}, None, {"a": {"secret": "<X>"}},
                       normalize=mask_secret)
    assert out["a"]["secret"] == "<X>"


def test_next_base_applies_normalize_to_merged_side_too():
    """merged만 정규화를 건너뛰어도 위 mask_secret 테스트는 통과해버린다.

    mask_secret이 멱등이라 위 테스트의 merged={"secret": "<X>"}가 이미 정규화된 형태와 같기
    때문이다. trim_whitespace로 양쪽 다 미정규화 상태인 값을 써서 merged 쪽 정규화 누락도
    changed 취급(= 이전 base 유지로 새어 KeyError)으로 드러나게 한다.
    """
    # local, merged = _normalized(local, normalize), merged (변조: merged 정규화 생략)로 바꾸면
    # merged["a"]==" value"가 local의 정규화된 "value"와 달라 same()이 거짓이 되고, old={}(base=None)라
    # "a"가 out에 실리지 않아 아래 줄이 KeyError로 FAIL한다.
    out = ks.next_base({"a": "value "}, None, {"a": " value"}, normalize=trim_whitespace)
    assert out["a"] == "value"


def test_next_base_does_not_share_nested_objects_with_inputs():
    """반환값을 호출부가 가공해도 원본이 오염되면 안 된다."""
    merged = {"a": {"n": [1]}}
    out = ks.next_base({"a": {"n": [1]}}, None, merged, normalize=lambda m: m)
    out["a"]["n"].append(2)
    assert merged["a"]["n"] == [1]


def test_next_base_does_not_share_nested_objects_with_base_either():
    """"이전 base 유지" 경로도 deepcopy를 써야 한다.

    merged 경로(위 테스트, copy.deepcopy(merged[name]))와는 별개의 코드 경로다
    (copy.deepcopy(old[name])). old[name]을 그대로 참조하면(`out[name] = old[name]`)
    반환값을 호출부가 가공할 때 base 원본이 오염된다.
    """
    base = {"theirs": {"n": [1]}}
    # local에 "theirs"가 없으므로 로컬 동의 조건이 성립하지 않아 "이전 base 유지" 갈래를 탄다.
    out = ks.next_base({}, base, {"theirs": {"n": [9]}}, normalize=lambda m: m)
    out["theirs"]["n"].append(2)
    assert base["theirs"]["n"] == [1]
