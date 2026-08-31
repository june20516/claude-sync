"""값 무관 코어의 단위 테스트. 도메인 지식은 전부 훅으로 들어온다."""
import ast
import json
import os
import re

import pytest

import keyed_sync as ks
import mcp_config as mc
import plugin_config as pc
from marks import requires_permission_bits

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")


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


def test_load_backup_raises_on_broken_syntax(tmp_path):
    """구문이 깨진 파일을 "항목 0개"로 읽지 않는다(5차 개정).

    초판은 {}로 degrade하고 근거를 "다음 백업이 되돌린다"로 적었다. **base가 있으면
    거짓이다**(실측) — 레포의 모든 키가 케이스 4로 떨어져 병합 결과가 {}가 되고,
    레포에만 있던 다른 기기의 항목이 영구 소실된다. 호출부는 이 예외를 문서 단위
    skip으로 접는다(tests/test_plugin_scripts.py·test_mcp_scripts.py가 그것을 잰다).
    """
    path = tmp_path / "backup.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ks.BrokenBackupSyntax):
        ks.load_backup(str(path), only_dict_with_items)
    # 파일 부재와 구별된다 — 그쪽만 "이력이 비어 있었다"라는 읽어 낸 사실이다.
    assert ks.load_backup(str(tmp_path / "none.json"), only_dict_with_items) == {}


@requires_permission_bits
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


def test_load_backup_reads_file_as_bytes_so_invalid_utf8_is_broken_syntax(tmp_path):
    """"rb"가 아니면 잘못된 UTF-8이 파일을 여는 시점에 UnicodeDecodeError로
    전파된다. 바이너리로 읽어야 decode()가 그 바이트를 받아 BROKEN으로 판정하고
    BrokenBackupSyntax로 접는다 — 호출부가 아는 예외 하나로 모아야 skip이 된다.
    """
    path = tmp_path / "backup.json"
    path.write_bytes(b"\xff")
    # open(path, "rb")를 open(path, "r")로 바꾸면 f.read()에서 UnicodeDecodeError가
    # 터진다. 그것은 BrokenBackupSyntax가 아니므로 이 raises가 FAIL한다.
    with pytest.raises(ks.BrokenBackupSyntax):
        ks.load_backup(str(path), only_dict_with_items)


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


def test_diff_ignores_the_action_axis_of_hold():
    """행동 보류는 restore_plan 전용이다. diff에 영향을 주면 축 분리가 무너진다(spec 5.3).

    value_held = set(hold(...)["value"]) | set(hold(...)["action"])로 축을 합치면
    action만 보류된 "a"가 held로 새어 changed에서 빠진다.
    """
    out = ks.diff({"a": 1}, {"a": 2}, normalize=lambda m: m, hold=hold_keys(action=("a",)))
    assert out["held"] == []
    assert out["changed"] == ["a"]


def test_next_base_advances_only_where_local_agrees():
    """타 기기가 추가·변경한 값을 base에 기록하면 다음 백업이 '내가 삭제했다'로 오독한다."""
    out = ks.next_base({"mine": 1}, {"mine": 1, "theirs": 0}, {"mine": 1, "theirs": 9},
                       normalize=lambda m: m)
    assert out["mine"] == 1      # 로컬이 동의 → 전진
    assert out["theirs"] == 0    # 로컬이 동의 안 함 → 이전 base 유지


def test_next_base_keeps_old_value_when_local_disagrees_with_merged_value():
    """타 기기가 바꾼 값을 base에 기록하면 다음 백업이 케이스 7로 오독해 그 변경을 되돌린다.

    위 test_next_base_advances_only_where_local_agrees의 "theirs"는 local에 아예 없는
    키라 `name in local`만 남기고 `same(merged[name], local[name])`를 지워도(변조 1의
    부분판) 우연히 같은 결과가 나온다. 여기서는 local·merged 둘 다 "x"를 갖되 값이
    달라, 동의 검사를 지우면 값이 새는 것이 직접 드러난다.
    """
    out = ks.next_base({"x": 1}, {"x": 1}, {"x": 2}, normalize=lambda m: m)
    # same() 동의 검사를 지우면(merged에 있고 local에도 있기만 하면 전진) 2가 되어 FAIL한다.
    assert out["x"] == 1


def test_next_base_drops_keys_absent_from_both_sides():
    out = ks.next_base({}, {"gone": 1}, {}, normalize=lambda m: m)
    assert "gone" not in out


def test_next_base_omits_remote_added_key_the_local_never_had():
    """base에 이력 없이 레포에만 생긴 항목. 넣으면 다음 백업이 케이스 3으로 읽어 레포에서 지운다.

    old에 없는 키이므로 `elif name in old:`가 `else:`로 바뀌면(old[name] KeyError를
    내지 않고 무조건 싣는) 이 키가 조용히 out에 실린다.
    """
    out = ks.next_base({}, None, {"theirs": 1}, normalize=lambda m: m)
    # `elif name in old:`를 `else:`로 바꾸면 "theirs"가 실려 FAIL한다.
    assert "theirs" not in out


def test_next_base_omits_conflicting_key_absent_from_base():
    """base에 이력이 없는 충돌 키는 어느 쪽 값도 기록하지 않는다.

    old에 없는데 old[name]에 접근하면 KeyError가 나야 정상이다. `elif name in old:`를
    `else:`로 바꾸면 크래시조차 없이 조용히 merged 값이 실려버린다 — 이 팔에 도달하는
    테스트가 없으면 그 크래시조차 관측되지 않는다.
    """
    out = ks.next_base({"x": 1}, None, {"x": 2}, normalize=lambda m: m)
    assert "x" not in out


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


def test_next_base_applies_normalize_to_base_side_too():
    """'이전 base 유지' 경로도 정규화된 값을 실어야 한다.

    위 두 정규화 테스트는 base=None이라 `old = _normalized(base, normalize) if base
    else {}` 줄 자체를 지나지 않는다. 여기서는 local이 merged와 동의하지 않는 값을 둬서
    "이전 base 유지" 갈래를 타게 하고, base 쪽 값이 미정규화 상태이게 한다.
    """
    out = ks.next_base({"a": "local"}, {"a": "value "}, {}, normalize=trim_whitespace)
    # base 정규화를 생략하면(`dict(base) if base else {}`) "value "로 FAIL한다.
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


def test_merge_covers_decision_table():
    """케이스 1~10을 한 번에 건다."""
    local = {"c1": 1, "c4": 1, "c5": 2, "c6": 1, "c7": 2, "c8": 1, "c9": 2}
    repo = {"c2": 1, "c3": 1, "c6": 1, "c7": 1, "c8": 2, "c9": 3}
    base = {"c3": 1, "c4": 1, "c5": 1, "c7": 1, "c8": 1, "c9": 1, "c10": 1}
    r = ks.merge(local, repo, base, normalize=lambda m: m, hold=ks.no_hold)
    assert r["merged"]["c1"] == 1                 # 1 로컬 신규
    assert r["merged"]["c2"] == 1                 # 2 타 기기 추가
    assert "c3" not in r["merged"]                # 3 로컬에서 삭제
    assert r["deleted"] == ["c3"]
    assert r["local_stale"] == ["c4"]             # 4 타 기기 삭제, 로컬 잔존
    assert "c5" in r["conflicts"] and "c5" not in r["merged"]   # 5
    assert r["merged"]["c6"] == 1                 # 6 in_sync
    assert r["merged"]["c7"] == 2                 # 7 로컬만 변경
    assert r["merged"]["c8"] == 2                 # 8 타 기기 변경
    assert "c9" in r["conflicts"] and r["merged"]["c9"] == 3    # 9
    assert "c10" not in r["merged"]               # 10 base에만 존재
    assert sorted(r["repo_ahead"]) == ["c2", "c8"]
    # next_base를 케이스 8·9에 대해 직접 단언한다(Task 5 리뷰 I2와 중복 방어).
    # 로컬이 merged 값에 동의하지 않으므로(local="1"/"2" != merged="2"/"3") 이전
    # base 값 1이 그대로 유지돼야 한다 — repo 값이 새면 다음 백업이 "로컬이 동의했다"로
    # 오독해 아직 반영 안 된 타 기기 변경을 base에 확정해버린다.
    assert r["next_base"]["c8"] == 1
    assert r["next_base"]["c9"] == 1


def halve_string_length(mapping):
    """테스트 전용 비멱등 normalize 훅 — 문자열 값을 절반으로 자른다.

    호출할 때마다 값이 계속 바뀌므로 실제 훅으로는 계약 위반이지만(spec 5.2 —
    normalize는 멱등이어야 한다), 그 계약 위반이 발생했을 때 merge의 next_base 경로가
    이중 정규화로부터 안전한지 드러내는 용도로만 쓴다.
    """
    return {k: (v[: len(v) // 2] if isinstance(v, str) else v) for k, v in mapping.items()}


def test_merge_next_base_does_not_double_normalize():
    """merge는 next_base를 만들 때 공개 next_base가 아니라 _next_base_normalized를
    불러야 한다 — local·base·merged를 merge가 이미 정규화해 넘기므로, 공개 next_base를
    부르면 비멱등 훅에서 정규화가 두 번 적용된다(Task 5 리뷰 I2, spec 5.2).

    "aaaa"를 한 번 자르면 "aa"(단일 정규화, 올바른 경로). 두 번 자르면 "a"(이중 정규화,
    회귀). merge 내부에서 local·repo·base가 이미 한 번 정규화된 뒤 next_base 계산에
    다시 normalize가 걸리면 이 값이 "a"로 새어 아래 단언이 FAIL한다.
    """
    r = ks.merge({"x": "aaaa"}, {"x": "aaaa"}, {"x": "aaaa"},
                 normalize=halve_string_length, hold=ks.no_hold)
    assert r["merged"]["x"] == "aa"
    assert r["next_base"]["x"] == "aa"


def test_merge_degrades_to_union_when_base_is_none():
    """base가 없으면 삭제 없이 합집합. 단 양쪽에 있는 키는 로컬이 이긴다."""
    r = ks.merge({"a": 1, "both": 9}, {"b": 1, "both": 8}, None,
                 normalize=lambda m: m, hold=ks.no_hold)
    assert r["deleted"] == []
    assert r["merged"] == {"a": 1, "b": 1, "both": 9}


def test_merge_keeps_repo_value_for_value_held_keys():
    """값 보류 키는 판정표를 타지 않고 레포 값이 그대로 실린다."""
    r = ks.merge({"h": "local"}, {"h": "repo"}, {"h": "old"},
                 normalize=lambda m: m, hold=hold_keys(value=("h",)))
    assert r["merged"]["h"] == "repo"
    assert r["conflicts"] == [] and r["deleted"] == [] and r["local_stale"] == []
    assert r["held"] == ["h"]


def test_merge_does_not_delete_value_held_key_missing_from_local():
    """로컬에서 사라져도 보류 키는 케이스 3이 되지 않는다."""
    r = ks.merge({}, {"h": "repo"}, {"h": "repo"},
                 normalize=lambda m: m, hold=hold_keys(value=("h",)))
    assert r["deleted"] == []
    assert r["merged"]["h"] == "repo"


def test_merge_removes_value_held_key_from_next_base():
    r = ks.merge({"h": 1, "n": 1}, {"h": 1, "n": 1}, {"h": 1, "n": 1},
                 normalize=lambda m: m, hold=hold_keys(value=("h",)))
    assert "h" not in r["next_base"]
    assert r["next_base"]["n"] == 1


def test_merge_gives_hold_normalized_local_and_repo_in_that_order():
    """hold는 정규화된 입력을 (local, repo) 순서로 정확히 한 번 받는다(훅 계약).

    hold는 좌우 대칭이 아니다 — 순서가 뒤집히면 plugin_config의 보류 판정이
    조용히 반대로 선다. MCP는 no_hold라 Task 8 게이트가 이것을 잡지 못한다.
    """
    seen = []
    ks.merge({"a": "x "}, {"b": " y"}, {}, normalize=trim_whitespace, hold=recording_hold(seen))
    assert seen == [({"a": "x"}, {"b": "y"})]      # 값·순서·호출 횟수를 한 줄로 고정


def test_merge_ignores_the_action_axis_of_hold():
    """행동 보류는 restore_plan 전용이다. merge에 영향을 주면 축 분리가 무너진다(spec 5.3)."""
    r = ks.merge({"a": 1}, {"a": 2}, {"a": 1},
                 normalize=lambda m: m, hold=hold_keys(action=("a",)))
    assert r["held"] == []
    assert r["repo_ahead"] == ["a"] and r["merged"]["a"] == 2   # 케이스 8을 정상적으로 탄다


def test_merge_empty_base_is_not_the_none_degrade():
    """{}(이력이 비어 있었다)와 None(이력을 읽을 수 없다)은 다르다 — 합치면 타 기기 변경을
    경고 없이 되돌린다. base={}는 첫 백업 직후에 실제로 나오는 값이다(spec 3.2)."""
    r = ks.merge({"x": 1}, {"x": 2}, {}, normalize=lambda m: m, hold=ks.no_hold)
    assert r["conflicts"] == ["x"] and r["merged"]["x"] == 2
    d = ks.merge({"x": 1}, {"x": 2}, None, normalize=lambda m: m, hold=ks.no_hold)
    assert d["conflicts"] == [] and d["merged"]["x"] == 1


def test_merge_buckets_are_exact_not_membership():
    """판정표 테스트는 멤버십만 봐서 '과다 분류' 변조를 놓친다. 다섯 버킷을 정확 등호로 건다.

    기존 test_merge_covers_decision_table을 고치지 않고 별도 테스트로 둔다 — 판정표
    테스트의 실패 원인이 가려지지 않도록 한다.
    """
    local = {"c1": 1, "c4": 1, "c5": 2, "c6": 1, "c7": 2, "c8": 1, "c9": 2}
    repo = {"c2": 1, "c3": 1, "c6": 1, "c7": 1, "c8": 2, "c9": 3}
    base = {"c3": 1, "c4": 1, "c5": 1, "c7": 1, "c8": 1, "c9": 1, "c10": 1}
    r = ks.merge(local, repo, base, normalize=lambda m: m, hold=ks.no_hold)
    assert r["conflicts"] == ["c5", "c9"]
    assert r["repo_ahead"] == ["c2", "c8"]
    assert sorted(r["merged"]) == ["c1", "c2", "c6", "c7", "c8", "c9"]


def always_restorable(key, value):
    return True


def no_secrets(value):
    return []


def test_restore_plan_separates_cases_7_8_9():
    """세 케이스를 한 버킷으로 뭉치면 안 된다 — 처방이 다르다."""
    local = {"c7": 2, "c8": 1, "c9": 2}
    repo = {"c7": 1, "c8": 2, "c9": 3}
    base = {"c7": 1, "c8": 1, "c9": 1}
    plan = ks.restore_plan(local, repo, base, normalize=lambda m: m, hold=ks.no_hold,
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["local_ahead"] == ["c7"]
    assert plan["repo_ahead"] == ["c8"]
    assert plan["both_changed"] == ["c9"]


def test_restore_plan_local_stale_holds_cases_4_and_5():
    """케이스 5를 담지 않으면 탈출구 없는 상태가 된다."""
    plan = ks.restore_plan({"c4": 1, "c5": 2}, {}, {"c4": 1, "c5": 1},
                           normalize=lambda m: m, hold=ks.no_hold,
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["local_stale"] == ["c4", "c5"]


def test_restore_plan_routes_add_needs_secret_and_unrestorable():
    plan = ks.restore_plan({}, {"ok": 1, "sec": 1, "bad": 1}, {},
                           normalize=lambda m: m, hold=ks.no_hold,
                           restorable=lambda k, v: k != "bad",
                           secret_keys=lambda v: ["k"] if v == 1 else [])
    assert plan["unrestorable"] == ["bad"]
    assert plan["needs_secret"] == ["ok", "sec"]
    assert plan["add"] == []


def test_restore_plan_action_held_goes_to_its_own_bucket_only():
    """행동 보류 키는 어떤 CLI 명령의 대상도 되지 않는다."""
    plan = ks.restore_plan({}, {"h": 1}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("h",), action=("h",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["action_held"] == ["h"]
    assert plan["add"] == [] and plan["value_held"] == []


def test_restore_plan_value_held_installs_when_absent_locally():
    """값 보류지만 행동 보류가 아니면 설치 대상이다 (H3)."""
    plan = ks.restore_plan({}, {"h": ["1.0.0"]}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("h",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["add"] == ["h"]
    assert plan["value_held"] == [] and plan["action_held"] == []


def test_restore_plan_value_held_new_key_still_goes_through_route_new():
    """값 보류라도 로컬에 없으면 restorable·secret_keys를 반드시 거친다.

    route_new는 두 곳에서 불린다("레포에만 있는" 갈래와 "값 보류인데 로컬엔 없는" 갈래).
    위 test_restore_plan_value_held_installs_when_absent_locally는 always_restorable·
    no_secrets만 써서 add 하나만 밟는다 — value_held 갈래가 route_new를 건너뛰고
    곧장 add에 넣는 변조를 못 잡는다. 그 계약이 무너지면 비밀이 필요한 항목이
    비밀 없이 설치되거나(needs_secret 누락), 복원 불가 항목이 실패할 CLI 명령으로
    제시된다(unrestorable 누락).
    """
    plan = ks.restore_plan({}, {"ok": 1, "sec": 2, "bad": 3}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("ok", "sec", "bad")),
                           restorable=lambda k, v: k != "bad",
                           secret_keys=lambda v: ["k"] if v == 2 else [])
    assert plan["add"] == ["ok"]
    assert plan["needs_secret"] == ["sec"]
    assert plan["unrestorable"] == ["bad"]
    assert plan["value_held"] == []


def test_restore_plan_value_held_uses_own_bucket_when_present_locally():
    """이미 설치돼 있으면 전용 버킷 — 케이스 9로 부르면 금지된 문구가 나간다."""
    plan = ks.restore_plan({"h": True}, {"h": ["1.0.0"]}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("h",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["value_held"] == ["h"]
    assert plan["both_changed"] == [] and plan["add"] == []


def test_restore_plan_gives_hold_normalized_local_and_repo_in_that_order():
    """hold는 정규화된 입력을 (local, repo) 순서로 정확히 한 번 받는다(훅 계약).

    MCP는 no_hold뿐이라 Task 8 게이트는 이 계약을 잡지 못한다 — plugin_config가
    붙는 순간에야 발현한다(spec 7.3의 H1~H4는 좌우 비대칭이다).
    """
    seen = []
    ks.restore_plan({"a": "x "}, {"b": " y"}, {}, normalize=trim_whitespace,
                     hold=recording_hold(seen), restorable=always_restorable,
                     secret_keys=no_secrets)
    assert seen == [({"a": "x"}, {"b": "y"})]


def test_restore_plan_keeps_the_two_hold_axes_disjoint():
    """value_held·action_held에 서로 다른 키를 넣어 두 축을 동시에 비어 있지 않게 한다.

    이 픽스처가 없으면 두 축을 합치거나(합집합) 서로 바꾸는 변조가 조용히 통과한다 —
    기존 테스트들은 매번 한쪽 축만 채우거나 같은 키를 양쪽에 넣어 구별이 안 된다.
    """
    plan = ks.restore_plan({"v": True}, {"v": ["1.0.0"], "a": 1}, {},
                           normalize=lambda m: m,
                           hold=hold_keys(value=("v",), action=("a",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["value_held"] == ["v"]
    assert plan["action_held"] == ["a"]
    assert plan["add"] == [] and plan["local_only"] == [] and plan["both_changed"] == []


def test_restore_plan_base_none_does_not_crash_and_matches_empty_base():
    """base=None(이력을 못 믿음)은 known={}로 degrade한다 — base={}와 결과가 같아야 하고
    크래시가 나면 안 된다. 주어진 테스트들은 모두 base={} 또는 비어 있지 않은 base만
    쓰므로, None 경로 자체는 이 테스트가 없으면 한 번도 실행되지 않는다.
    """
    plan = ks.restore_plan({"c9": 2}, {"c9": 3}, None, normalize=lambda m: m,
                           hold=ks.no_hold, restorable=always_restorable,
                           secret_keys=no_secrets)
    assert plan["both_changed"] == ["c9"]
    assert plan["local_ahead"] == [] and plan["repo_ahead"] == []


def test_restore_plan_buckets_are_exact_not_membership():
    """열한 버킷 전부를 정확 등호로 건다 — 멤버십만 보면 과다 분류 변조가 통과한다."""
    local = {"c1": 1, "c4": 1, "c5": 2, "c6": 1, "c7": 2, "c8": 1, "c9": 2}
    repo = {"c2": 1, "c3": 1, "c6": 1, "c7": 1, "c8": 2, "c9": 3, "new": 1}
    base = {"c3": 1, "c4": 1, "c5": 1, "c7": 1, "c8": 1, "c9": 1, "c10": 1}
    plan = ks.restore_plan(local, repo, base, normalize=lambda m: m, hold=ks.no_hold,
                           restorable=always_restorable, secret_keys=no_secrets)
    # c3은 base·repo에 있고 local에는 없다(merge의 케이스 3 형태) — restore는 merge와
    # 달리 이런 항목도 "레포에만 있음"으로 보고 add 후보에 넣는다. base 이력 유무로
    # add/local_stale을 가르지 않는다 — 그건 local이 그 항목을 가졌는지 여부의 몫이다.
    assert plan["add"] == ["c2", "c3", "new"]
    assert plan["needs_secret"] == []
    assert plan["unrestorable"] == []
    assert plan["in_sync"] == ["c6"]
    assert plan["local_ahead"] == ["c7"]
    assert plan["repo_ahead"] == ["c8"]
    assert plan["both_changed"] == ["c9"]
    assert plan["local_stale"] == ["c4", "c5"]
    assert plan["local_only"] == ["c1"]
    assert plan["value_held"] == []
    assert plan["action_held"] == []


def test_route_new_keys_gives_hold_normalized_local_and_repo_in_that_order():
    """hold는 정규화된 입력을 (local, repo) 순서로 정확히 한 번 받는다(훅 계약).

    이 함수의 hold는 **행동 축만** 본다. 순서가 뒤집히면 로컬 전용 키가 "새 항목"으로
    올라가는데 예외도 빈 결과도 나지 않는다.
    """
    seen = []
    ks.route_new_keys({"a": "x "}, {"b": " y"},
                      normalize=trim_whitespace, hold=recording_hold(seen))
    assert seen == [({"a": "x"}, {"b": "y"})]


def test_route_new_keys_matches_the_three_restore_plan_buckets():
    """`add` + `needs_secret` + `unrestorable`과 **정확히 같은 집합**이어야 한다.

    두 곳이 각자 만들면 갈리고, 갈려도 증상이 없다 — 한쪽 소비자는 "설치한다"고,
    다른 쪽은 "복원 불가"라고 말하게 된다. 픽스처가 세 버킷을 **동시에** 비어 있지
    않게 만드는 것이 요점이다: 하나만 채우면 두 버킷을 빠뜨리는 변조가 통과한다.
    값 보류 키(`vheld`)와 행동 보류 키(`aheld`)를 함께 두는 것도 같은 이유다 —
    전자는 이 집합에 **들어와야** 하고 후자는 **빠져야** 한다.
    """
    local = {"mine": 1, "both": 1, "vlocal": 1}
    repo = {"ok": 1, "sec": 2, "bad": 3, "both": 9, "vheld": 4, "aheld": 5,
            "vlocal": 7}
    hooks = dict(normalize=lambda m: m,
                 hold=hold_keys(value=("vheld", "vlocal"), action=("aheld",)))
    plan = ks.restore_plan(local, repo, {}, restorable=lambda k, v: k != "bad",
                           secret_keys=lambda v: ["k"] if v == 2 else [], **hooks)
    assert ks.route_new_keys(local, repo, **hooks) == sorted(
        plan["add"] + plan["needs_secret"] + plan["unrestorable"])
    # 픽스처가 diff와 **갈리는** 키를 실제로 담는지 함께 건다 — 담지 않으면 위 등호가
    # only_repo로 바꿔도 참이 되어 이 테스트가 자기 주제를 재지 않는다(다섯째 축, 실측).
    assert "vheld" not in ks.diff(local, repo, **hooks)["only_repo"]
    # 픽스처가 실제로 셋을 다 채우는지 함께 건다 — 채우지 못하면 위 등호가 공허해진다.
    assert plan["add"] == ["ok", "vheld"]
    assert plan["needs_secret"] == ["sec"] and plan["unrestorable"] == ["bad"]
    assert plan["action_held"] == ["aheld"] and plan["value_held"] == ["vlocal"]


def test_route_new_keys_is_not_the_only_repo_of_diff():
    """diff의 only_repo와 **다른 집합**이다 — 값 보류 키에서 갈린다.

    두 집합을 같다고 읽는 소비자는 H3 보류 + 레포 전용 키를 복원 가능성 판정에서
    빠뜨린다. 이 줄이 그 차이를 명시적으로 고정한다(양쪽을 같게 만드는 변조를 잡는다).
    """
    local, repo = {}, {"vheld": 1, "plain": 2}
    hooks = dict(normalize=lambda m: m, hold=hold_keys(value=("vheld",)))
    assert ks.diff(local, repo, **hooks)["only_repo"] == ["plain"]
    assert ks.route_new_keys(local, repo, **hooks) == ["plain", "vheld"]


def test_route_new_keys_rejects_normalize_that_drops_keys():
    """코어의 키 보존 집행을 이 진입점도 받는다 — 빠지면 값 무관 계약에 구멍이 난다."""
    with pytest.raises(ValueError):
        ks.route_new_keys({"a": 1, "b": 1}, {"a": 1},
                          normalize=lambda m: {k: v for k, v in m.items() if k != "b"},
                          hold=ks.no_hold)


HOLD_CONSUMER = re.compile(r"^def (\w+)\((.*?)\):\s*$", re.M | re.S)
HOLD_TEST = "def test_%s_gives_hold_normalized_local_and_repo_in_that_order("


def test_every_hold_consuming_function_has_a_recording_hold_test():
    """hold를 받는 코어 함수는 인자·순서·정규화 여부를 거는 테스트를 하나씩 가져야 한다.

    MCP는 no_hold뿐이라 호출 계약이 틀려도 기존 테스트 게이트가 잡지 못한다 —
    plugin_config가 붙는 순간에야 발현한다(spec 7.3의 H1~H4는 좌우 비대칭이다).
    파라미터 목록에서 찾으므로 줄바꿈에 무관하고, 접두사가 아니라 정확한 테스트
    이름 규약을 요구하므로 이름 충돌·문자열 언급만으로는 통과하지 못한다.
    """
    source = open(os.path.join(LIB_DIR, "keyed_sync.py"), encoding="utf-8").read()
    consumers = {name for name, params in HOLD_CONSUMER.findall(source)
                 if re.search(r"\bhold\b", params) and not name.startswith("_")}
    tests = open(__file__, encoding="utf-8").read()
    missing = [name for name in sorted(consumers) if HOLD_TEST % name not in tests]
    assert missing == [], "recording_hold 테스트가 없는 hold 소비 함수: %s" % missing


# recognize를 코어 세 함수에 넘기는 어댑터 전수. (모듈, 인식되는 최소 문서) 쌍이다.
# 손으로 복제하는 대신 파라미터화한다 — 복제를 잊으면 그 어댑터의 비대칭이 무증상으로
# 들어오고, 그 비대칭이 상위 버전 백업을 파괴한다(spec 4.4).
RECOGNIZE_ADAPTERS = [
    (mc, b'{"version": 2, "scope": "user", "servers": {}}'),
    (pc, b'{"version": 2, "scope": "user", "enabledPlugins": {}}'),
]


@pytest.mark.parametrize("adapter,sample", RECOGNIZE_ADAPTERS,
                         ids=lambda x: x.__name__ if hasattr(x, "__name__") else "")
def test_adapter_passes_one_recognize_hook_to_all_three(adapter, sample, tmp_path, monkeypatch):
    """어댑터가 세 함수에 같은 recognize를 넘겨야 한다.

    코어는 훅을 파라미터로 받으므로 공유를 강제할 수 없다. 갈리면 "이력은 못 믿는데
    레포는 믿는" 비대칭이 생기고 상위 버전 백업이 파괴된다(spec 4.4).
    """
    seen = []

    def capture(*args):
        seen.append(args[-1])   # 세 코어 함수 모두 recognize가 마지막 위치 인자다
        return {}

    monkeypatch.setattr(adapter.ks, "parse_base", capture)
    monkeypatch.setattr(adapter.ks, "load_backup", capture)
    monkeypatch.setattr(adapter.ks, "parse_backup", capture)

    adapter.parse_base(sample)
    adapter.load_backup(str(tmp_path / "none.json"))
    adapter.parse_backup(sample)

    assert len(seen) == 3
    assert len({id(hook) for hook in seen}) == 1


# 두 어댑터의 로컬 리더 전체. 자리가 여기인 이유는 이 파일이 이미 RECOGNIZE_ADAPTERS로
# 어댑터 간 불변식을 소유하고 있기 때문이다 — 어댑터별 파일에 흩어 두면 다음 어댑터가
# 붙을 때 조용히 빠진다.
BYTE_READERS = [
    (mc.read_local_servers, {"mcpServers": {"a": {"command": "x"}}}),
    (pc.read_local_sections, {"enabledPlugins": {"p@m": True}}),
    (pc.read_auto_ids, {"version": 2, "plugins": {}}),
    (pc.read_held_state, {"pluginConfigs": {}, "release": {"enabledPlugins": []}}),
]


@pytest.mark.parametrize("reader,payload", BYTE_READERS,
                         ids=lambda x: x.__name__ if callable(x) else "")
def test_adapter_readers_open_local_files_in_binary_mode(reader, payload, tmp_path):
    """어댑터의 로컬 리더는 전부 open(path, "rb")여야 한다. BOM으로 그것을 고정한다.

    **왜 BOM인가** — 이 리더들은 `except (json.JSONDecodeError, UnicodeDecodeError)`로
    파싱 실패를 자기 예외로 감싼다. 그래서 잘못된 UTF-8 바이트로는 "rb"와 "r"을 구별할
    수 없다: 텍스트 모드에서도 f.read()의 UnicodeDecodeError가 같은 except에 잡혀 같은
    예외가 나온다. 두 모드가 실제로 갈리는 입력은 UTF-8 BOM이다 —
    json.loads(bytes)는 json.detect_encoding이 BOM을 처리해 통과하지만, 텍스트 모드로
    읽으면 BOM 문자가 본문 첫 글자로 남아 JSONDecodeError가 된다.

    Windows 계열 편집기가 실제로 BOM을 붙인다. 그때 한 리더가 텍스트 모드면 그 파일이
    "깨졌다"로 읽혀 해당 섹션이나 백업 전체가 통째로 skip된다.
    """
    path = tmp_path / "input.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    # 단정은 "예외가 나지 않는다" 그 자체다 — 예외가 나면 그 리더가 텍스트 모드다.
    reader(str(path))


class OpenModeFinder(ast.NodeVisitor):
    """소스에서 open() 호출을 찾아 바이너리 모드가 아닌 것을 모은다."""

    def __init__(self):
        self.offenders = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            mode = node.args[1] if len(node.args) >= 2 else None
            for kw in node.keywords:
                if kw.arg == "mode":
                    mode = kw.value
            if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
                self.offenders.append((node.lineno, "모드가 문자열 리터럴이 아니다"))
            elif "b" not in mode.value:
                self.offenders.append((node.lineno, "텍스트 모드 %r" % mode.value))
        self.generic_visit(node)


def test_lib_opens_every_file_in_binary_mode():
    """lib/의 모든 open()은 바이너리 모드여야 한다. 등재를 잊을 여지가 없는 소스 스캔이다.

    위 BYTE_READERS 표는 **동작**으로 검증하지만 손으로 등재하는 목록이라 다음 리더가
    붙을 때 조용히 빠진다 — RECOGNIZE_ADAPTERS가 소스 스캔 가드를 얻은 것과 같은 이유다.
    이 가드는 리더뿐 아니라 writer(dump_bytes의 "wb")까지 덮는다.

    왜 바이너리인가 — 읽기 쪽은 (a) 텍스트 모드가 로케일 인코딩에 의존하고 (b) UTF-8
    BOM을 본문 첫 글자로 남겨 정상 문서를 "깨졌다"로 만든다. 쓰기 쪽은 원자적 writer가
    이미 인코딩을 마친 바이트를 다루므로 "wb"가 아니면 타입부터 맞지 않는다.
    """
    offenders = []
    for name in sorted(os.listdir(LIB_DIR)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(LIB_DIR, name)
        with open(path, encoding="utf-8") as f:
            finder = OpenModeFinder()
            finder.visit(ast.parse(f.read(), filename=path))
        offenders.extend("%s:%d %s" % (name, line, why) for line, why in finder.offenders)
    assert offenders == [], "lib/의 open()이 바이너리 모드가 아니다: %s" % offenders


KEYED_SYNC_IMPORT = re.compile(r"^\s*(?:import keyed_sync\b|from keyed_sync import\b)", re.M)
RECOGNIZE_HOOK_CALL = re.compile(r"\bks\.(?:parse_base|load_backup|parse_backup)\(")

# lib/에서 keyed_sync를 import하지만 recognize를 받는 세 함수(parse_base·load_backup·
# parse_backup)는 전혀 부르지 않는 모듈. sync_state는 ks.dump_bytes만 쓴다 — recognize
# 공유와 무관하므로 RECOGNIZE_ADAPTERS에 넣을 수 없다(그 세 함수가 없어 파라미터화
# 테스트가 AttributeError로 깨진다). 그렇다고 완전성 스캔에서 통째로 빼면 소스 스캔의
# 의미가 없으므로, 아래 테스트가 "정말 세 함수를 안 부르는지"를 매번 재확인한다 —
# 나중에 호출이 생기면 이 목록이 거짓이 되어 가드가 잡는다.
NON_ADAPTER_KEYED_SYNC_IMPORTERS = {"sync_state"}


def test_recognize_adapter_list_covers_every_keyed_sync_importer():
    """lib/에서 코어를 import하는 모듈은 전부 위 두 목록 중 하나에 있어야 한다.

    목록을 손으로 관리하면 새 어댑터가 붙을 때 조용히 빠진다 — 그것이 이 가드가
    mc에 하드코딩돼 있던 동안의 상태였다. 소스를 훑어 강제한다. import 한 줄만 있는
    빈 어댑터 스텁도 걸려야 하므로(뒤늦게 함수 호출이 생길 때까지 기다리지 않는다),
    기준은 "recognize 함수를 부르는가"가 아니라 "keyed_sync를 import하는가"다 —
    그래서 비-어댑터는 이름만 적지 않고 세 함수를 안 부른다는 사실도 함께 검증한다.
    """
    found = set()
    for name in sorted(os.listdir(LIB_DIR)):
        if not name.endswith(".py") or name == "keyed_sync.py":
            continue
        with open(os.path.join(LIB_DIR, name), encoding="utf-8") as f:
            source = f.read()
        if not KEYED_SYNC_IMPORT.search(source):
            continue
        found.add(name[:-3])
        if name[:-3] in NON_ADAPTER_KEYED_SYNC_IMPORTERS:
            assert not RECOGNIZE_HOOK_CALL.search(source), (
                "%s가 recognize를 받는 함수를 호출하기 시작했다 — "
                "RECOGNIZE_ADAPTERS로 옮겨야 한다" % name
            )

    assert found == (
        {module.__name__ for module, _ in RECOGNIZE_ADAPTERS} | NON_ADAPTER_KEYED_SYNC_IMPORTERS
    ), (
        "새 keyed_sync importer가 목록에 없다 — recognize를 코어 세 함수에 넘기는 "
        "어댑터면 RECOGNIZE_ADAPTERS에, 아니면 NON_ADAPTER_KEYED_SYNC_IMPORTERS에 등재하라"
    )


def test_dump_json_leaves_old_file_intact_when_write_fails(tmp_path, monkeypatch):
    """교체(os.replace)가 실패해도 이전 내용이 온전해야 한다.

    직접 open(path, "w")했다면 truncate가 먼저 일어나 잘린 파일이 다음 load_backup에서
    {}로 degrade하고, 그러면 모든 항목이 케이스 4로 판정되어 restore가 "다른 기기가
    삭제했습니다"라는 거짓 문구를 띄운다 — 그것이 원자적 쓰기가 막는 것이다.
    이 테스트는 "교체 단계에서 실패해도 옛 내용이 남는가"만 본다. 쓰기 도중 실패의
    실물 검증(open 성공 후 실제 쓰기가 실패하는 경로)은
    test_dump_bytes_removes_its_temp_file_on_non_oserror_failure가 맡는다.
    """
    path = str(tmp_path / "x.json")
    ks.dump_json({"a": 1}, path)

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    # dump_json이 이제 json.dumps로 먼저 텍스트를 완성한 뒤 dump_bytes에 위임하므로
    # (I1), "쓰기 도중 실패"는 더 이상 json.dump가 아니라 os.replace에서 흉내낸다.
    # 이 선택이 fsync 유무(I2)에 우연히 결합되지 않도록 write/flush/fsync가 아니라
    # replace를 표적으로 삼는다 — 그래야 fsync 줄을 지우는 변조와 무관하게 이 테스트가
    # 계속 "쓰기 실패 → 이전 내용 보존"만 검증한다.
    monkeypatch.setattr(ks.os, "replace", boom)
    with pytest.raises(OSError):
        ks.dump_json({"b": 2}, path)
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}


def test_dump_json_removes_its_temp_file_when_write_fails(tmp_path, monkeypatch):
    """실패가 남긴 .tmp를 지운다 — 레포 디렉토리에 남으면 `git add -A`가 커밋한다."""
    path = str(tmp_path / "x.json")

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    # os.replace를 표적으로 삼는 이유는 위 테스트와 같다(fsync 유무와 무관해야 한다).
    monkeypatch.setattr(ks.os, "replace", boom)
    with pytest.raises(OSError):
        ks.dump_json({"b": 2}, path)
    assert os.listdir(str(tmp_path)) == []


def test_dump_json_writes_the_same_bytes_as_before(tmp_path):
    """직렬화 옵션은 바뀌지 않는다 — 지문 비교와 디스크 표현의 일치가 계약이다."""
    path = str(tmp_path / "x.json")
    ks.dump_json({"b": 1, "a": {"ko": "한글"}}, path)
    with open(path, encoding="utf-8") as f:
        assert f.read() == '{\n  "a": {\n    "ko": "한글"\n  },\n  "b": 1\n}\n'


def test_dump_json_creates_nothing_when_serialization_fails(tmp_path):
    """직렬화가 실패하면 파일도 .tmp도 남지 않는다.

    dump_json은 json.dumps로 메모리에서 먼저 직렬화한 뒤에야 dump_bytes를 부르므로(I1)
    현재 구현에서는 .tmp가 생성조차 되지 않는다. 다만 이 단정이 관측하는 것은 "생성
    여부"가 아니라 "종료 상태"다 — 직렬화를 열린 tmp로 스트리밍하도록 되돌리면서
    정리를 OSError로 좁히면 이 단정이 깨진다. 그 변조를 잡는 것이 이 테스트의
    존재 이유다(지난 라운드의 구멍). 정리 경로 자체는
    test_dump_bytes_removes_its_temp_file_on_non_oserror_failure가 맡는다.
    """
    path = str(tmp_path / "x.json")
    with pytest.raises(TypeError):
        ks.dump_json({"b": {1, 2}}, path)
    assert os.listdir(str(tmp_path)) == []


def test_dump_bytes_removes_its_temp_file_on_non_oserror_failure(tmp_path):
    """OSError가 아닌 실패(bytes가 아닌 값)도 .tmp를 지워야 한다.

    dump_bytes(data, path)에 bytes가 아닌 값을 넘기면 open(tmp, "wb")는 성공하고
    f.write(data)가 TypeError를 던진다 — open이 이미 성공한 뒤에 터져야 .tmp가
    디스크에 남은 상태에서 정리 코드가 실제로 실행되는 경로를 검증한다.

    dump_json 쪽 테스트(위)는 직렬화가 dump_bytes 호출 전 메모리에서 끝나 버려
    이 경로를 검증하지 못한다 — 정리 경로의 검증은 이 테스트가 유일하게 책임진다.
    except를 OSError로 좁히면 TypeError가 정리 코드를 우회해 .tmp가 남고,
    os.remove(tmp)를 지우면 성공 여부와 무관하게 .tmp가 남는다.
    """
    path = str(tmp_path / "x.json")
    ks.dump_bytes(b"old", path)
    with pytest.raises(TypeError):
        ks.dump_bytes("not bytes", path)
    assert os.listdir(str(tmp_path)) == ["x.json"]
    with open(path, "rb") as f:
        assert f.read() == b"old"


def test_dump_bytes_fsyncs_before_replace(tmp_path, monkeypatch):
    """fsync 없이 replace하면 rename과 writeback 사이 크래시가 0바이트 파일을 publish한다.

    원자성 테스트들은 fsync와 결합되지 않도록 일부러 os.replace를 표적으로 삼는다 —
    그래서 이 줄(f.flush(); os.fsync(f.fileno()))을 지키는 책임은 이 테스트만 진다.
    """
    order = []
    real_fsync, real_replace = ks.os.fsync, ks.os.replace
    monkeypatch.setattr(ks.os, "fsync", lambda fd: order.append("fsync") or real_fsync(fd))
    monkeypatch.setattr(ks.os, "replace", lambda a, b: order.append("replace") or real_replace(a, b))
    ks.dump_bytes(b"x", str(tmp_path / "f"))
    assert order == ["fsync", "replace"]


def test_dump_json_routes_through_dump_bytes(tmp_path, monkeypatch):
    """I1이 만든 코어 내부 edge(dump_json -> dump_bytes)를 고정한다.

    어댑터->코어 라우팅(test_dump_backup_routes_through_ks_dump_json 등)은 이 edge를
    지키지 못한다 — dump_json이 원자적 블록을 자기 안에 복사해도 어댑터 쪽 라우팅
    테스트는 여전히 통과한다. 여기서 복사가 재발하면 fsync(I2)도 함께 조용히 사라진다.
    """
    calls = []
    monkeypatch.setattr(ks, "dump_bytes", lambda data, target: calls.append((data, target)))
    path = str(tmp_path / "x.json")
    ks.dump_json({"a": 1}, path)
    assert calls == [(b'{\n  "a": 1\n}\n', path)]


def test_diff_and_merge_report_held_on_the_same_axis():
    """diff와 merge의 held가 **같은 축(value)** 을 담는다는 숨은 결합을 잠근다.

    compare_plugins는 ks.diff의 held를, collect_plugins는 ks.merge의 held를 각각 같은
    pc.held_kinds에 넘긴다. 한쪽이 action을 섞어 돌려주면 그쪽에서만 분류 불가로
    ValueError가 나 섹션이 통째로 접힌다 — 두 스크립트가 같은 상태에서 서로 다른 보고를
    낸다. keyed_sync를 고치는 사람에게 이 대응을 알리는 것은 이 테스트뿐이다.

    **행동 보류와 값 보류가 둘 다 일어나는** fixture여야 한다. 한 축만 있으면 두 축이
    우연히 같아져 "value 축만 담는다"가 실측으로 잠기지 않는다.
    """
    def hold(local, repo):
        return {"value": {"v@m", "both@m"}, "action": {"a@m", "both@m"}}

    ident = {"v@m": 1, "a@m": 1, "both@m": 1, "plain@m": 1}
    repo = {"v@m": 2, "a@m": 2, "both@m": 2, "plain@m": 2}

    diffed = ks.diff(ident, repo, normalize=lambda m: m, hold=hold)
    merged = ks.merge(ident, repo, dict(ident), normalize=lambda m: m, hold=hold)

    assert diffed["held"] == merged["held"] == ["both@m", "v@m"]
    # 축이 실제로 갈라져 있다 — action에만 있는 키는 어느 쪽 held에도 없다.
    assert "a@m" not in diffed["held"] and "a@m" not in merged["held"]
