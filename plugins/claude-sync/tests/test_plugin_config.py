"""플러그인 어댑터 단위 테스트 (spec 3·4·6·7·8장).

실제 ~/.claude는 절대 건드리지 않는다 — 모든 읽기 함수가 경로 인자를 받는다.
"""
import json
import os

import pytest

import keyed_sync as ks
import plugin_config as pc
from marks import requires_permission_bits


def write_settings(tmp_path, data, name="settings.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def write_installed(tmp_path, plugins):
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")
    return str(path)


def write_held(tmp_path, data):
    path = tmp_path / "plugins-held.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(path)


GH = {"source": {"source": "github", "repo": "june20516/suberpower"}}


@pytest.fixture
def default_paths(tmp_path, monkeypatch):
    """세 기본 경로를 전부 tmp_path의 서로 다른 파일로 갈아끼운다.

    셋을 한꺼번에 바꾸는 이유는 둘이다 — (a) 실제 ~/.claude를 **읽지도 않기** 위해서,
    (b) DEFAULT_INSTALLED를 DEFAULT_SETTINGS로 바꾸는 식의 변조가 "없는 파일"이 아니라
    **내용이 다른 실재 파일**을 읽게 만들어 확실히 FAIL하도록.
    """
    for name, path in (
        ("DEFAULT_SETTINGS", write_settings(tmp_path, {"enabledPlugins": {"p@m": True}})),
        ("DEFAULT_INSTALLED",
         write_installed(tmp_path, {"dep@m": [{"scope": "user", "auto": True}]})),
        ("DEFAULT_HELD",
         write_held(tmp_path, {"version": 1, "pluginConfigs": {"delta@m": "abc"}})),
    ):
        monkeypatch.setattr(pc, name, path)


def test_read_local_sections_defaults_to_the_settings_path(default_paths):
    """인자 없이 부르면 DEFAULT_SETTINGS를 본다 — 상수가 갈리면 무증상 고장이다."""
    assert pc.read_local_sections()["enabledPlugins"] == {"p@m": True}


def test_read_auto_ids_defaults_to_the_installed_path(default_paths):
    """인자 없이 부르면 DEFAULT_INSTALLED를 본다."""
    assert pc.read_auto_ids() == frozenset({"dep@m"})


def test_read_held_state_defaults_to_the_held_path(default_paths):
    """인자 없이 부르면 DEFAULT_HELD를 본다."""
    assert pc.read_held_state()["pluginConfigs"] == {"delta@m": "abc"}


# --- 3.2 로컬 읽기 ---

def test_read_local_returns_three_sections_with_empty_defaults(tmp_path):
    """키가 없으면 {} — 0개는 정상 상태다."""
    local = pc.read_local_sections(write_settings(tmp_path, {}))
    assert local == {"enabledPlugins": {}, "extraKnownMarketplaces": {}, "pluginConfigs": {}}


def test_read_local_rejects_null_section(tmp_path):
    """{"enabledPlugins": null}을 "0개"로 읽으면 base의 항목 전부가 케이스 3이 된다."""
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(write_settings(tmp_path, {"enabledPlugins": None}))


def test_read_local_rejects_non_object_sections(tmp_path):
    for bad in ([], "x", 3, True):
        with pytest.raises(pc.LocalConfigUnavailable):
            pc.read_local_sections(write_settings(tmp_path, {"pluginConfigs": bad}))


def test_read_local_rejects_missing_and_broken_file(tmp_path):
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(str(tmp_path / "none.json"))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(str(broken))
    top = tmp_path / "top.json"
    top.write_text("[]", encoding="utf-8")
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(str(top))


@requires_permission_bits
def test_read_local_propagates_permission_error(tmp_path):
    """권한 오류를 LocalConfigUnavailable로 감싸면 "설정 0개"로 접힌다 — 전파한다."""
    path = write_settings(tmp_path, {})
    os.chmod(path, 0)
    try:
        with pytest.raises(PermissionError):
            pc.read_local_sections(path)
    finally:
        os.chmod(path, 0o600)


# --- 3.3 별칭 키 ---

def test_read_local_reads_the_alias_key(tmp_path):
    """additionalMarketplaces만 있는 기기의 마켓플레이스를 놓치면 안 된다."""
    local = pc.read_local_sections(write_settings(tmp_path, {"additionalMarketplaces": {"m": GH}}))
    assert local["extraKnownMarketplaces"] == {"m": GH}


def test_read_local_ignores_the_alias_when_both_exist(tmp_path):
    """CLI와 같은 규칙 — 둘 다 있으면 별칭을 무시한다."""
    local = pc.read_local_sections(write_settings(
        tmp_path, {"extraKnownMarketplaces": {"canonical": GH},
                   "additionalMarketplaces": {"alias": GH}}))
    assert local["extraKnownMarketplaces"] == {"canonical": GH}


def test_read_local_validates_only_the_adopted_alias(tmp_path):
    """채택하지 않은 쪽이 깨져 있어도 읽기는 성공한다 — 그 값을 쓰지 않기 때문이다."""
    local = pc.read_local_sections(write_settings(
        tmp_path, {"extraKnownMarketplaces": {"canonical": GH},
                   "additionalMarketplaces": "손상"}))
    assert local["extraKnownMarketplaces"] == {"canonical": GH}
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(write_settings(tmp_path, {"additionalMarketplaces": "손상"},
                                              name="only-alias.json"))


# --- 3.4 auto 집합 ---

def test_read_auto_ids_takes_user_scope_true_only(tmp_path):
    path = write_installed(tmp_path, {
        "dep@m": [{"scope": "user", "auto": True}],
        "manual@m": [{"scope": "user", "auto": False}],
        "other@m": [{"scope": "project", "auto": True}],
        "mixed@m": [{"scope": "project", "auto": False}, {"scope": "user", "auto": True}],
    })
    assert pc.read_auto_ids(path) == frozenset({"dep@m", "mixed@m"})


def test_read_auto_ids_rejects_missing_or_broken_file(tmp_path):
    """판정 불가를 빈 집합으로 접으면 auto 항목이 레포로 승격 전파된다 (N6)."""
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(tmp_path / "none.json"))
    broken = tmp_path / "installed_plugins.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(broken))


def test_read_auto_ids_rejects_unknown_shape(tmp_path):
    """plugins[<id>]는 배열이다 — 형태가 다르면 판정 불가다."""
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"plugins": {"x@m": {"scope": "user"}}}), encoding="utf-8")
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(path))


def test_read_auto_ids_rejects_document_without_plugins_key(tmp_path):
    """plugins 키 부재를 "auto 0개"로 접으면 auto 항목이 그대로 레포로 승격된다 (N6).

    같은 함수가 plugins[<id>]의 형태 위반은 예외로 막으면서 그보다 상위인 plugins 키
    부재를 통과시키면 일관성이 없다.
    """
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(path))


def test_read_auto_ids_rejects_higher_schema_version(tmp_path):
    """이 파일도 스스로 version을 달고 다닌다 — 상위 버전이면 auto의 의미를 보장할 수 없다.

    float 우회까지 본다. 같은 모듈의 read_held_state·_recognized_sections와 같은 게이트다.
    """
    path = tmp_path / "installed_plugins.json"
    for version in (3, 3.0, 2.5):
        path.write_text(json.dumps({"version": version, "plugins": {}}), encoding="utf-8")
        with pytest.raises(pc.AutoFlagsUnavailable):
            pc.read_auto_ids(str(path))
    # 경계값은 통과해야 한다 — 게이트가 정상 문서를 막으면 그것도 사고다.
    path.write_text(json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
    assert pc.read_auto_ids(str(path)) == frozenset()


def test_read_auto_ids_accepts_a_document_without_a_version_key(tmp_path):
    """version 키 부재는 "주장 없음"이지 이상이 아니다 — version을 필수로 만드는 변조를 잡는다."""
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"plugins": {"dep@m": [{"scope": "user", "auto": True}]}}),
                    encoding="utf-8")
    assert pc.read_auto_ids(str(path)) == frozenset({"dep@m"})


def test_read_auto_ids_rejects_non_bool_auto(tmp_path):
    """auto=1·"true"·[True]는 `is True`가 거짓이라 조용히 "auto 아님"이 된다 — N6의 입구다."""
    for bad in (1, "true", [True], None):
        with pytest.raises(pc.AutoFlagsUnavailable):
            pc.read_auto_ids(write_installed(
                tmp_path, {"x@m": [{"scope": "user", "auto": bad}]}))


def test_read_auto_ids_rejects_non_string_scope(tmp_path):
    """scope=["user"]·1은 == 비교가 거짓이라 조용히 판정에서 빠진다."""
    for bad in (["user"], 1, None):
        with pytest.raises(pc.AutoFlagsUnavailable):
            pc.read_auto_ids(write_installed(
                tmp_path, {"x@m": [{"scope": bad, "auto": True}]}))


def test_read_auto_ids_accepts_entries_missing_those_keys(tmp_path):
    """키 **부재**는 이상이 아니다 — 실기기의 항목에는 auto 키가 아예 없다.

    "키 부재 = auto 아님"을 유지하지 않으면 정상 파일이 거부된다(과잉 차단).
    """
    path = write_installed(tmp_path, {"plain@m": [{"scope": "user"}], "bare@m": [{}]})
    assert pc.read_auto_ids(path) == frozenset()


def test_read_auto_ids_rejects_non_object_entry(tmp_path):
    """원소가 객체가 아니면 그 항목의 auto를 읽을 수 없다 — 조용히 건너뛰면 N6이다."""
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(write_installed(tmp_path, {"x@m": ["손상"]}))


@requires_permission_bits
def test_read_auto_ids_propagates_permission_error(tmp_path):
    """권한 오류는 "판정 불가"가 아니라 그대로 전파한다 — mcp_config와 같은 규약이다.

    except FileNotFoundError를 except OSError로 넓히는 변조를 잡는 줄이다. 넓히면
    PermissionError가 AutoFlagsUnavailable로 둔갑해 예외 종류가 사실을 잃는다.
    """
    path = write_installed(tmp_path, {})
    os.chmod(path, 0)
    try:
        with pytest.raises(PermissionError):
            pc.read_auto_ids(path)
    finally:
        os.chmod(path, 0o600)


# --- 6.4 보류 상태 파일 ---

def test_read_held_state_treats_missing_file_as_empty(tmp_path):
    """파일 부재는 첫 실행의 정상 상태다 — 예외가 아니다."""
    assert pc.read_held_state(str(tmp_path / "none.json")) == pc.EMPTY_HELD


def test_read_held_state_rejects_broken_or_unknown_shape(tmp_path):
    for bad in ("{not json", {"pluginConfigs": []}, {"pluginConfigs": {"x@m": 3}},
                {"release": {"enabledPlugins": "x@m"}}, {"version": 3}):
        with pytest.raises(pc.HeldStateUnavailable):
            pc.read_held_state(write_held(tmp_path, bad))


def test_read_held_state_returns_both_axes(tmp_path):
    state = pc.read_held_state(write_held(tmp_path, {
        "version": 1, "pluginConfigs": {"delta@m": "abc"},
        "release": {"enabledPlugins": ["p@m"]}}))
    assert state == {"pluginConfigs": {"delta@m": "abc"},
                     "release": {"enabledPlugins": ["p@m"]}}


def test_read_held_state_does_not_share_state_with_the_module_constant(tmp_path):
    """반환값을 변형해도 EMPTY_HELD가 오염되면 안 된다.

    copy.deepcopy를 `return EMPTY_HELD`(또는 얕은 복사)로 바꾸는 변조를 잡는 줄이다.
    오염되면 그 프로세스의 이후 모든 read_held_state가 거짓 보류를 돌려준다.
    """
    state = pc.read_held_state(str(tmp_path / "none.json"))
    state["pluginConfigs"]["x@m"] = "지문"
    state["release"]["enabledPlugins"].append("p@m")
    assert pc.EMPTY_HELD == {"pluginConfigs": {}, "release": {"enabledPlugins": []}}
    assert pc.read_held_state(str(tmp_path / "none.json")) == {
        "pluginConfigs": {}, "release": {"enabledPlugins": []}}


@requires_permission_bits
def test_read_held_state_propagates_permission_error(tmp_path):
    """부재 갈래는 **파일 부재만** 담는다 — 권한 오류는 전파한다.

    except FileNotFoundError를 except OSError로 넓히는 변조를 잡는 줄이다. 넓히면
    읽을 수 없는 보류 파일이 "보류 없음"으로 조용히 접히고, 사용자가 보류해 둔
    pluginConfigs가 그대로 레포로 올라간다.
    """
    path = write_held(tmp_path, {"version": 1})
    os.chmod(path, 0)
    try:
        with pytest.raises(PermissionError):
            pc.read_held_state(path)
    finally:
        os.chmod(path, 0o600)


# --- 4.4 인식 규칙 ---

def recognized(obj):
    return pc.parse_backup(json.dumps(obj).encode("utf-8"))


def test_recognizes_v2_document_and_fills_absent_sections(tmp_path):
    """인식된 문서에서 없는 섹션은 {} — "이력이 비어 있었다"는 뜻이다."""
    out = recognized({"version": 2, "scope": "user", "enabledPlugins": {"p@m": True}})
    assert out == {"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": {},
                   "pluginConfigs": {}}


def test_recognizes_v1_document_without_version(tmp_path):
    """v1(두 필드만, version 없음)은 그대로 통과한다 — 마이그레이션 스크립트가 없다."""
    out = recognized({"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": {"m": GH}})
    assert out["pluginConfigs"] == {}
    assert out["enabledPlugins"] == {"p@m": True}


EMPTY_SECTIONS = {"enabledPlugins": {}, "extraKnownMarketplaces": {}, "pluginConfigs": {}}


def test_does_not_recognize_document_without_any_known_section():
    """조건 3 — {"foo": 1}이나 {}를 "항목 0개"로 읽으면 그 문서를 덮어써 파괴한다.

    미인식이어도 parse_backup은 **세 섹션 키를 갖춰** 돌려준다 — 호출부의
    out["enabledPlugins"]가 KeyError로 죽지 않게 하는 것이 이 함수의 계약이다.
    """
    assert recognized({}) == EMPTY_SECTIONS
    assert recognized({"foo": 1}) == EMPTY_SECTIONS
    assert pc.parse_backup(b"{not json") == EMPTY_SECTIONS
    assert pc.parse_base(json.dumps({"foo": 1}).encode("utf-8")) is None


def test_does_not_recognize_when_any_known_section_is_not_an_object():
    """조건 4 — 손상된 섹션이 "0개"로 읽혀 로컬 값으로 덮이는 것을 막는다."""
    assert pc.parse_base(json.dumps(
        {"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": "손상"}
    ).encode("utf-8")) is None


def test_does_not_recognize_higher_schema_version():
    """숫자로 상위 버전을 주장하면 알아보지 않는다. float 우회 포함."""
    for version in (3, 3.0, 2.5):
        assert pc.parse_base(json.dumps(
            {"version": version, "enabledPlugins": {}}).encode("utf-8")) is None


def test_recognizes_string_and_bool_version_claims():
    """문자열은 손으로 고친 문서를 막지 않기 위해, bool은 버전 주장이 아니라서 통과한다.

    **parse_base로 단정한다.** parse_backup은 미인식일 때 None이 아니라 빈 세 섹션을
    돌려주므로 `is not None`이 어떤 입력에도 참이 되어 아무것도 지키지 못한다 —
    그 단정으로는 "문자열·bool 버전을 거부"하도록 규칙을 뒤집어도 초록이었다.
    값까지 단정해 "인식은 됐는데 내용이 비었다"와도 구별한다.
    """
    for version in ("3", True):
        out = pc.parse_base(json.dumps(
            {"version": version, "enabledPlugins": {"p@m": True}}).encode("utf-8"))
        assert out is not None, version
        assert out["enabledPlugins"] == {"p@m": True}


def test_load_backup_raises_on_unrecognized_document(tmp_path):
    path = tmp_path / pc.BACKUP_RELPATH
    path.write_text(json.dumps({"version": 3, "enabledPlugins": {}}), encoding="utf-8")
    with pytest.raises(pc.UnknownBackupSchema):
        pc.load_backup(str(path))


def test_load_backup_returns_empty_sections_when_file_missing(tmp_path):
    """레포에 파일이 없으면 세 섹션 모두 {} — 첫 백업의 정상 상태다."""
    assert pc.load_backup(str(tmp_path / "none.json")) == {
        "enabledPlugins": {}, "extraKnownMarketplaces": {}, "pluginConfigs": {}}


# --- 4.3 쓰기 규칙 ---

def test_dump_backup_always_writes_three_sections(tmp_path):
    """빈 섹션을 생략하면 다음 백업의 인식 규칙에 걸려 영구 skip된다 (4.3)."""
    path = str(tmp_path / pc.BACKUP_RELPATH)
    pc.dump_backup({"enabledPlugins": {"p@m": True}}, path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["version"] == 2 and raw["scope"] == "user"
    assert set(raw) == {"version", "scope", *pc.SECTIONS}
    assert raw["pluginConfigs"] == {}


def test_dump_backup_rejects_a_non_object_section(tmp_path):
    """{"enabledPlugins": None}을 그대로 쓰면 자기가 쓴 파일을 자기가 못 읽는다.

    다음 load_backup이 조건 4에서 인식에 실패해 그 백업이 영구히 UnknownBackupSchema가
    된다. ValueError인 근거는 **쓰기 전에 던져 손상 파일이 레포에 들어가지 않는다**는
    것과, 코어의 _normalized가 계약 위반에 쓰는 것과 같은 신호 종류라는 것이다.
    스크립트의 except 튜플에는 ValueError가 이미 있으므로 이 예외도 skip으로 접힌다 —
    전용 예외로 빼면 훅 결함 하나가 흐름 전체를 세우므로(결함 C) 알고 받아들인다.
    """
    path = str(tmp_path / pc.BACKUP_RELPATH)
    with pytest.raises(ValueError):
        pc.dump_backup({"enabledPlugins": None}, path)
    assert not os.path.exists(path)      # 쓰기 전에 막는다 — 잔해를 남기지 않는다


def test_dump_backup_round_trips_through_load(tmp_path):
    path = str(tmp_path / pc.BACKUP_RELPATH)
    doc = {"enabledPlugins": {"p@m": ["1.0.0"]}, "extraKnownMarketplaces": {"m": GH},
           "pluginConfigs": {"p@m": {"options": {"k": "v"}}}}
    pc.dump_backup(doc, path)
    assert pc.load_backup(path) == doc


# --- 7.2 섹션별 정규화 ---

def test_enabled_plugins_normalize_is_identity_on_all_three_value_types():
    """값을 좁히지 않는다 — bool로 좁히면 확장 포맷을 파괴한다 (G5)."""
    norm = pc.SECTION_NORMALIZE["enabledPlugins"]
    values = {"a@m": True, "b@m": ["1.0.0"], "c@m": {"version": "1.0.0"}}
    assert norm(values) == values


def test_marketplace_normalize_drops_auto_update_field_only():
    """autoUpdate는 marketplace add로 설정할 수 없어 수렴시킬 CLI 수단이 없다 (7.2).

    필드 제거이지 키 제거가 아니다 — 값 층위에서 안전하다.
    """
    norm = pc.SECTION_NORMALIZE["extraKnownMarketplaces"]
    out = norm({"m": {"source": {"source": "github", "repo": "a/b"}, "autoUpdate": True}})
    assert out == {"m": {"source": {"source": "github", "repo": "a/b"}}}


def test_plugin_configs_normalize_masks_values_and_keeps_key_names():
    """키 이름을 보존해야 레포 파일만 보고 "어떤 값을 물어야 하는지"를 안다 (6.1)."""
    norm = pc.SECTION_NORMALIZE["pluginConfigs"]
    out = norm({"p@m": {"options": {"apiKey": "sk-real", "region": "kr"}, "other": 1}})
    assert out == {"p@m": {"options": {"apiKey": pc.SENTINEL, "region": pc.SENTINEL},
                           "other": 1}}


def test_plugin_configs_normalize_replaces_non_object_options_wholesale():
    """options가 객체가 아니면 필드 전체를 문자열 SENTINEL로 바꾼다 (6.1)."""
    norm = pc.SECTION_NORMALIZE["pluginConfigs"]
    assert norm({"p@m": {"options": ["secret"]}}) == {"p@m": {"options": pc.SENTINEL}}


@pytest.mark.parametrize("section", pc.SECTIONS)
def test_every_normalize_is_idempotent_and_key_preserving(section):
    """멱등하지 않으면 로컬(원본)과 레포(정규화됨)가 수렴하지 않는다.

    코어는 키 보존만 집행하고 멱등성은 집행하지 않는다(spec 5.2) — 어댑터의 책임이다.
    """
    norm = pc.SECTION_NORMALIZE[section]
    sample = {"a@m": True, "b@m": {"source": {"source": "directory", "path": "/x"},
                                   "autoUpdate": True},
              "c@m": {"options": {"k": "v"}}}
    once = norm(sample)
    assert set(once) == set(sample)
    assert once == norm(once)


def test_normalize_does_not_mutate_its_input():
    """입력을 바꾸면 원본 로컬 설정이 오염되고 비밀 평문이 사라진다."""
    original = {"p@m": {"options": {"apiKey": "sk-real"}}}
    pc.SECTION_NORMALIZE["pluginConfigs"](original)
    assert original == {"p@m": {"options": {"apiKey": "sk-real"}}}


# --- 6.1·6.2 비밀 키 ---

def test_secret_keys_lists_option_names_for_plugin_configs():
    assert pc.SECTION_SECRET_KEYS["pluginConfigs"](
        {"options": {"region": "x", "apiKey": "y"}}) == ["apiKey", "region"]


def test_secret_keys_is_empty_when_there_is_nothing_to_ask(section=None):
    """options가 비었거나 없으면 물어볼 것이 없다 — add 버킷으로 간다 (6.2)."""
    ask = pc.SECTION_SECRET_KEYS["pluginConfigs"]
    assert ask({"options": {}}) == [] and ask({}) == [] and ask("x") == []


@pytest.mark.parametrize("section", ("enabledPlugins", "extraKnownMarketplaces"))
def test_secret_keys_is_always_empty_for_the_other_two_sections(section):
    """다른 섹션에 비밀이 있다고 말하면 정상 항목이 needs_secret으로 새어 나간다."""
    assert pc.SECTION_SECRET_KEYS[section]({"options": {"k": "v"}}) == []


# --- 7.3 보류 ---

def hooks_for(local, repo, auto_ids=frozenset(), held=None):
    return pc.build_hooks(local, repo, auto_ids=auto_ids,
                          held_state=held or pc.EMPTY_HELD)


def hold_of(section, local, repo, **kw):
    """코어가 부르는 방식 그대로 — 정규화된 입력을 넘긴다."""
    norm = pc.SECTION_NORMALIZE[section]
    hooks = hooks_for({section: local}, {section: repo}, **kw)
    return hooks[section]["hold"](norm(local), norm(repo))


def test_h1_holds_auto_dependency_on_both_axes():
    """의존성 플러그인은 값도 행동도 보류다 — 명시적 install이 auto 표식을 영구 소실시킨다."""
    held = hold_of("enabledPlugins", {"dep@m": True}, {}, auto_ids=frozenset({"dep@m"}))
    assert held["value"] == {"dep@m"} and held["action"] == {"dep@m"}


def test_h1_also_holds_the_plugin_configs_entry():
    held = hold_of("pluginConfigs", {"dep@m": {"options": {}}}, {},
                   auto_ids=frozenset({"dep@m"}))
    assert held["value"] == {"dep@m"} and held["action"] == {"dep@m"}


def test_h1_does_not_hold_a_marketplace_that_shares_a_name_with_an_auto_id():
    """auto 플래그는 플러그인의 사실이지 마켓플레이스의 사실이 아니다.

    H1의 `section != "extraKnownMarketplaces"` 가드를 지우는 변조를 잡는 줄이다.
    read_auto_ids는 id의 형태를 강제하지 않으므로 이름 충돌은 실제로 가능하고, 가드를
    지우면 같은 이름의 마켓플레이스가 보류된다. 그런데
    HELD_KINDS["extraKnownMarketplaces"]에는 "auto" 종류가 없어 held_kinds가 그 키를
    분류하지 못하고 ValueError를 던져 **마켓플레이스 섹션 전체가 skipped로 접힌다.**
    """
    held = hold_of("extraKnownMarketplaces", {"shared": GH}, {},
                   auto_ids=frozenset({"shared"}))
    assert held == {"value": set(), "action": set()}
    # 위 단정이 지키는 결과를 명시한다 — 보류됐다면 여기서 ValueError가 났을 것이다.
    assert pc.held_kinds("extraKnownMarketplaces", [], auto_ids=frozenset({"shared"}),
                         directory_names=frozenset(), held_configs={},
                         repo_norm={}) == {"local_marketplace": []}
    with pytest.raises(ValueError):
        pc.held_kinds("extraKnownMarketplaces", ["shared"],
                      auto_ids=frozenset({"shared"}), directory_names=frozenset(),
                      held_configs={}, repo_norm={})


def test_h2_holds_directory_marketplace_and_its_plugins_in_all_three_sections():
    """마켓플레이스만 빼면 소속 플러그인이 기기 B에서 해소 불가 상태가 된다 (7.3)."""
    local = {"enabledPlugins": {"p@mylocal": True, "q@gh": True},
             "extraKnownMarketplaces": {"mylocal": {"source": {"source": "directory",
                                                               "path": "/x"}},
                                        "gh": GH},
             "pluginConfigs": {"p@mylocal": {"options": {}}}}
    hooks = hooks_for(local, {name: {} for name in pc.SECTIONS})
    for section, expected in (("enabledPlugins", {"p@mylocal"}),
                              ("extraKnownMarketplaces", {"mylocal"}),
                              ("pluginConfigs", {"p@mylocal"})):
        norm = pc.SECTION_NORMALIZE[section]
        held = hooks[section]["hold"](norm(local[section]), norm({}))
        assert held["value"] == expected and held["action"] == expected


def test_h2_sees_directory_source_on_the_repo_side_too():
    """이미 레포에 실린 옛 directory 항목도 보류한다 — 등록할 소스가 이 기기에 없다."""
    repo = {"extraKnownMarketplaces": {"theirs": {"source": {"source": "directory",
                                                             "path": "/x"}}},
            "enabledPlugins": {"p@theirs": True}, "pluginConfigs": {}}
    hooks = hooks_for({name: {} for name in pc.SECTIONS}, repo)
    norm = pc.SECTION_NORMALIZE["enabledPlugins"]
    assert hooks["enabledPlugins"]["hold"](norm({}), norm(repo["enabledPlugins"])) == {
        "value": {"p@theirs"}, "action": {"p@theirs"}}


def test_h3_holds_value_only_and_judges_by_the_repo_side():
    """H3는 값만 보류한다 — 설치는 한다. 그리고 **레포** 값을 본다 (7.3)."""
    held = hold_of("enabledPlugins", {"p@m": True}, {"p@m": ["1.0.0"]})
    assert held["value"] == {"p@m"}
    assert held["action"] == set()


def test_h3_covers_objects_as_well_as_arrays():
    """1차 개정은 객체만 잡았다. 새 기기에는 키가 없으므로 install이 true를 쓴다 (0.1)."""
    assert hold_of("enabledPlugins", {}, {"p@m": {"version": "1.0.0"}})["value"] == {"p@m"}


def test_h3_does_not_hold_when_only_the_local_side_is_extended():
    """레포 기준이라 새 값의 등록을 막지 않는다 — 로컬 배열은 정상 push된다."""
    assert hold_of("enabledPlugins", {"p@m": ["1.0.0"]}, {})["value"] == set()


def test_h3_is_lifted_by_the_release_marker():
    """7.3의 탈출구 — release에 있는 키는 H3 값 보류에서 뺀다."""
    held = hold_of("enabledPlugins", {"p@m": True}, {"p@m": ["1.0.0"]},
                   held={"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}})
    assert held["value"] == set()


def test_h4_holds_only_when_the_fingerprint_matches_the_masked_repo_value():
    """지문 대상은 **레포 값(마스킹 후)**이다. 로컬 값이나 입력값을 넣으면 영영 매치되지
    않아 탈출구가 무증상으로 죽는다 (6.4)."""
    repo = {"delta@m": {"options": {"apiKey": "x"}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo)
    good = {"pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
            "release": {"enabledPlugins": []}}
    assert hold_of("pluginConfigs", {}, repo, held=good)["value"] == {"delta@m"}
    stale = {"pluginConfigs": {"delta@m": "0" * 64}, "release": {"enabledPlugins": []}}
    assert hold_of("pluginConfigs", {}, repo, held=stale)["value"] == set()


def test_h4_holds_both_axes():
    repo = {"delta@m": {"options": {"apiKey": "x"}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo)
    held = hold_of("pluginConfigs", {}, repo, held={
        "pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
        "release": {"enabledPlugins": []}})
    assert held["action"] == {"delta@m"}


def test_value_fingerprint_is_a_sha256_of_the_canonical_serialization():
    """코어와 같은 정규 직렬화를 써야 디스크 표현과 지문이 어긋나지 않는다."""
    import hashlib
    value = {"options": {"b": 1, "a": 2}}
    assert pc.value_fingerprint(value) == hashlib.sha256(
        ks.fingerprint(value).encode("utf-8")).hexdigest()


def test_build_hooks_gives_the_core_the_four_hook_contract():
    """코어가 보는 계약은 normalize(mapping)·hold(local, repo)·restorable(key, value)·
    secret_keys(value) 넷이다.

    자기 섹션 밖의 입력(auto_ids·다른 섹션의 출처와 등록 가능 여부·보류 파일)은
    어댑터가 클로저로 닫는다 — 이 테스트가 고정하는 것이 그 사실이다.

    어댑터는 여기에 보고용 reason을 하나 더 얹는데 **코어는 그것을 보지 않는다** —
    계약이 넷이라는 말은 그대로 참이다.

    **`==`가 아니라 `>=`인 것은 의도된 개방이다.** 이후 task가 훅을 더 얹어도 여기서
    깨지지 않아야 한다. 조이지 말 것 — 훅 하나하나의 배선은 이 줄이 아니라 아래
    normalize 단정과 restorable·secret_keys 전용 테스트가 잡는다(변조로 실측했다).
    """
    hooks = hooks_for({name: {} for name in pc.SECTIONS},
                      {name: {} for name in pc.SECTIONS})
    for section in pc.SECTIONS:
        assert set(hooks[section]) >= {"normalize", "hold"}
        # 섹션마다 **자기** 정규화를 실어야 한다. 키가 있는지만 보면
        # SECTION_NORMALIZE[section]을 SECTION_NORMALIZE["enabledPlugins"]로 바꾸는
        # 변조가 통과하는데, 그러면 코어가 pluginConfigs를 _identity로 정규화해
        # **비밀 평문이 그대로 레포에 실린다.** hold_of는 SECTION_NORMALIZE를 직접
        # 찾아 쓰므로 이 줄이 없으면 그 변조를 잡는 단정이 하나도 없다.
        assert hooks[section]["normalize"] is pc.SECTION_NORMALIZE[section]
        assert hooks[section]["hold"]({}, {}) == {"value": set(), "action": set()}


# --- 보류 종류 보고 ---

def test_held_kinds_splits_by_reason_and_covers_every_key():
    """사용자에게는 종류별 문구로 보고한다 — 한 키가 여러 종류에 걸릴 수 있다."""
    repo = {"ext@m": ["1.0.0"], "dep@m": True}
    kinds = pc.held_kinds("enabledPlugins", ["ext@m", "dep@m"],
                          auto_ids=frozenset({"dep@m"}), directory_names=frozenset(),
                          held_configs={}, repo_norm=repo)
    assert kinds == {"auto": ["dep@m"], "local_marketplace": [], "extended_value": ["ext@m"]}


def test_held_kinds_uses_the_section_specific_key_set():
    """섹션마다 나올 수 있는 종류가 다르다. 화이트리스트를 기계로 고정한다."""
    assert set(pc.held_kinds("extraKnownMarketplaces", [], auto_ids=frozenset(),
                             directory_names=frozenset(), held_configs={},
                             repo_norm={})) == {"local_marketplace"}
    assert set(pc.held_kinds("pluginConfigs", [], auto_ids=frozenset(),
                             directory_names=frozenset(), held_configs={},
                             repo_norm={})) == {"auto", "local_marketplace", "declined"}


def test_held_kinds_refuses_to_drop_an_unclassified_key():
    """분류되지 않은 보류 키를 조용히 빠뜨리면 사용자 보고에서 통째로 사라진다.

    불변식 6 — 조용한 fail-open 금지. 스크립트의 except 튜플이 ValueError를 잡아
    그 섹션을 skipped로 접고 사유를 보여준다.
    """
    with pytest.raises(ValueError):
        pc.held_kinds("enabledPlugins", ["ghost@m"], auto_ids=frozenset(),
                      directory_names=frozenset(), held_configs={}, repo_norm={})


def test_hold_and_held_kinds_never_diverge_when_fed_one_context():
    """훅과 보고가 **같은 held_context**를 보면 갈릴 수 없다는 것을 고정한다.

    두 곳이 각자 계산하던 시절에는 호출부가 셋(directory_names·held_configs·auto_ids)
    중 하나만 어긋나도 hold는 보류로 판정하는데 held_kinds가 그 키를 분류하지 못해
    ValueError를 던졌고, 스크립트의 except 튜플이 그것을 잡아 **섹션이 통째로
    skipped**가 됐다.

    시나리오가 H1~H4를 전부 태운다 — 특히 p@theirs는 **레포 쪽** directory 출처로만
    보류되므로, held_context의 directory_marketplaces에서 repo를 빼는 변조는
    아래 expected의 local_marketplace 줄에서 잡힌다.
    """
    local = {"enabledPlugins": {"dep@m": True, "plain@m": True},
             "extraKnownMarketplaces": {"m": GH},
             "pluginConfigs": {"dep@m": {"options": {}},
                               "delta@m": {"options": {"apiKey": "sk-real"}}}}
    repo = {"enabledPlugins": {"p@theirs": True, "ext@m": ["1.0.0"]},
            "extraKnownMarketplaces": {"theirs": {"source": {"source": "directory",
                                                             "path": "/x"}},
                                       "m": GH},
            "pluginConfigs": {"delta@m": {"options": {"apiKey": "x"}}}}
    auto_ids = frozenset({"dep@m"})
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    held_state = {"pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
                  "release": {"enabledPlugins": []}}

    context = pc.held_context(local, repo, auto_ids=auto_ids, held_state=held_state)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=held_state)

    expected = {
        # dep@m=H1(auto), p@theirs=H2(레포 쪽 directory), ext@m=H3(레포 값이 배열)
        "enabledPlugins": {"auto": ["dep@m"], "local_marketplace": ["p@theirs"],
                           "extended_value": ["ext@m"]},
        "extraKnownMarketplaces": {"local_marketplace": ["theirs"]},
        # dep@m=H1(auto), delta@m=H4(지문 일치 → 사용자가 거절함)
        "pluginConfigs": {"auto": ["dep@m"], "local_marketplace": [],
                          "declined": ["delta@m"]},
    }
    for section in pc.SECTIONS:
        norm = pc.SECTION_NORMALIZE[section]
        repo_norm = norm(repo[section])
        held = hooks[section]["hold"](norm(local[section]), repo_norm)
        both = held["value"] | held["action"]
        kinds = pc.held_kinds(section, sorted(both), repo_norm=repo_norm, **context)
        assert kinds == expected[section], section
        # 분류가 보류 집합을 **정확히** 덮는다 — held_kinds의 ValueError가 한쪽을,
        # 이 단정이 "보류하지도 않은 키를 보고에 넣는" 반대쪽을 막는다.
        assert {key for names in kinds.values() for key in names} == both, section


# --- 8.2·8.3 열거형 대조 (14.4) ---

def test_always_known_marketplaces_are_exactly_these_five():
    """상수 import만으로 대조하면 이름 하나가 빠져도 테스트와 코드가 함께 바뀌어 통과한다.

    개수 + 이름 전수를 리터럴로 적어 "목록이 줄어들면 실패"하게 만든다 (spec 14.4).
    """
    assert pc.ALWAYS_KNOWN == frozenset({
        "inline", "skills-dir", "synced", "builtin", "claude-plugins-official"})
    assert len(pc.ALWAYS_KNOWN) == 5


def test_pseudo_sources_are_the_four_that_cannot_be_registered():
    """claude-plugins-official만 always-known이면서 복원 가능하다 (8.1)."""
    assert pc.PSEUDO_SOURCES == frozenset({"inline", "skills-dir", "synced", "builtin"})
    assert "claude-plugins-official" not in pc.PSEUDO_SOURCES


def test_reserved_marketplace_names_are_exactly_these_sixteen():
    assert pc.RESERVED_MARKETPLACE_NAMES == frozenset({
        "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
        "anthropic-marketplace", "anthropic-plugins", "agent-skills",
        "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins",
        "claude-for-legal", "claude-for-financial-services",
        "financial-services-plugins", "first-party-plugins",
        "claude-community", "claude-plugins-community", "healthcare"})
    assert len(pc.RESERVED_MARKETPLACE_NAMES) == 16


# --- 8.6 마켓플레이스 인자 ---

def test_marketplace_arg_from_github_repo():
    assert pc.marketplace_arg(GH) == "june20516/suberpower"


def test_marketplace_arg_from_url_sources():
    for kind in ("url", "git"):
        assert pc.marketplace_arg(
            {"source": {"source": kind, "url": "https://x/y.git"}}) == "https://x/y.git"


def test_marketplace_arg_is_none_when_no_command_can_be_built():
    """"시도한다"가 실행 가능한 명령으로 번역되지 않으면 unrestorable이다 (8.6).

    마지막 항목(repo가 배열)은 타입 검사를 지키는 줄이다 — 문자열이 아닌 값을 인자로
    돌려주면 그것이 그대로 `marketplace add`의 argv에 실려 CLI 호출에서 터진다.
    """
    for value in ({"source": {"source": "directory", "path": "/x"}},
                  {"source": {"source": "github"}},
                  {"source": {"source": "github", "repo": ""}},
                  {"source": {"source": "novel"}}, {"source": "x"}, "x", None,
                  {"source": {"source": "github", "repo": ["june20516/suberpower"]}}):
        assert pc.marketplace_arg(value) is None


# --- 8.1 복원 가능성 ---

def restorable_for(section, repo):
    return pc.build_hooks({name: {} for name in pc.SECTIONS}, repo,
                          auto_ids=frozenset(), held_state=pc.EMPTY_HELD)[section]["restorable"]


def test_plugin_is_unrestorable_when_id_is_not_plugin_at_marketplace():
    """id 형태가 아니면 어떤 설치 명령도 만들 수 없다.

    각 bad id가 **id 형태 갈래로** 거부되는지까지 본다. 형태 검사가 느슨해지면
    (marketplace_of가 "@"를 포함하기만 하면 통과하도록) "a@b@c"의 마켓플레이스가
    'b@c'로 읽혀 판정은 그대로 False인데 사유만 "소스가 없다"로 바뀐다 — 사용자는
    존재한 적 없는 마켓플레이스를 백업하라는 안내를 받는다. 판정만 보는 단정으로는
    그 변조가 잡히지 않는다(실측).
    """
    repo = {"extraKnownMarketplaces": {"m": GH}}
    ok = restorable_for("enabledPlugins", repo)
    assert ok("p@m", True) is True
    for bad in ("noat", "@m", "p@", "a@b@c", ""):
        assert ok(bad, True) is False
        assert "id 형태" in pc.unrestorable_reason("enabledPlugins", bad, True, repo)


def test_plugin_is_unrestorable_under_pseudo_sources():
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {}})
    for name in sorted(pc.PSEUDO_SOURCES):
        assert ok("p@%s" % name, True) is False


def test_official_marketplace_plugin_is_restorable_without_registration():
    """내장이라 등록이 무의미할 뿐 설치는 된다 (8.1)."""
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {}})
    assert ok("p@claude-plugins-official", True) is True


def test_plugin_is_unrestorable_when_the_repo_has_no_source_for_its_marketplace():
    """H2의 소비 측 안전망 — 등록할 소스가 레포 어디에도 없으면 시도해도 반드시 실패한다."""
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {"known": GH}})
    assert ok("p@known", True) is True
    assert ok("p@unknown", True) is False


def test_plugin_configs_uses_the_same_rule_as_its_plugin():
    """설정을 채우는 명령이 `install --config`이므로 판정 기준이 같다."""
    ok = restorable_for("pluginConfigs", {"extraKnownMarketplaces": {"m": GH}})
    assert ok("p@m", {"options": {}}) is True
    assert ok("p@nowhere", {"options": {}}) is False


def test_marketplace_restorability_is_decided_by_the_argument():
    ok = restorable_for("extraKnownMarketplaces", {"extraKnownMarketplaces": {}})
    assert ok("m", GH) is True
    assert ok("m", {"source": {"source": "directory", "path": "/x"}}) is False


# --- 10.2 갈래별 사유 ---

def test_unrestorable_reason_distinguishes_the_four_branches():
    """"복원 불가"만 말하면 사용자가 무엇을 해야 하는지 알 수 없다 (10.2)."""
    repo = {"extraKnownMarketplaces": {"known": GH}}

    def reason(section, key, value):
        return pc.unrestorable_reason(section, key, value, repo)

    assert "id 형태" in reason("enabledPlugins", "noat", True)
    assert "의사 출처" in reason("enabledPlugins", "p@inline", True)
    assert "소스가 없" in reason("enabledPlugins", "p@unknown", True)
    assert "인자" in reason("extraKnownMarketplaces", "m",
                            {"source": {"source": "directory", "path": "/x"}})


def test_unrestorable_reason_is_present_exactly_when_restorable_is_false():
    """사유와 판정이 갈리면 양쪽 다 무증상이다.

    복원 가능한데 사유가 붙으면 사용자는 되지도 않을 조치를 하고, 복원 불가인데
    사유가 None이면 그 항목은 보고에서 "이유 없이 빠진" 것이 된다(불변식 6).
    두 함수가 각자 갈래를 세므로 이 대응을 기계로 고정한다.
    """
    repo = {"extraKnownMarketplaces": {"known": GH}}
    cases = (
        ("enabledPlugins", "p@known", True),
        ("enabledPlugins", "p@claude-plugins-official", True),
        ("enabledPlugins", "p@inline", True),
        ("enabledPlugins", "p@unknown", True),
        ("enabledPlugins", "noat", True),
        ("pluginConfigs", "p@known", {"options": {}}),
        ("pluginConfigs", "p@unknown", {"options": {}}),
        ("extraKnownMarketplaces", "known", GH),
        ("extraKnownMarketplaces", "d",
         {"source": {"source": "directory", "path": "/x"}}),
    )
    for section, key, value in cases:
        ok = restorable_for(section, repo)(key, value)
        why = pc.unrestorable_reason(section, key, value, repo)
        assert ok is (why is None), (section, key, why)


# --- 7.6 정합성 ---

def test_orphaned_reports_plugins_whose_marketplace_is_gone():
    """런타임은 조용히 건너뛰고 새 기기 restore는 "플러그인이 없다"로 실패한다 (7.6)."""
    assert pc.orphaned({"alpha@bar": True, "beta@known": True},
                       {"known": GH}) == ["alpha@bar"]


def test_orphaned_accepts_always_known_marketplaces():
    """내장 마켓플레이스는 extraKnownMarketplaces에 없는 것이 정상이다 (4.1·8.2)."""
    assert pc.orphaned({"p@claude-plugins-official": True}, {}) == []


def test_orphaned_reports_malformed_ids_too():
    """마켓플레이스 부분이 없는 id는 어떤 마켓플레이스에도 속하지 않는다."""
    assert pc.orphaned({"noat": True}, {}) == ["noat"]


def test_build_hooks_wires_the_section_specific_secret_keys():
    """build_hooks가 섹션마다 **다른** secret_keys를 다는지 본다.

    SECTION_SECRET_KEYS만 직접 검사하면 build_hooks가 그 표를 섹션 무관하게 고정해도
    어떤 테스트도 실패하지 않는다(실측). 그때 pluginConfigs에 _no_secrets가 달리면
    마스킹된 값이 needs_secret으로 가지 않고 그대로 add 버킷에 실려, restore가
    **"<REDACTED>"를 진짜 옵션 값으로 설치한다** — 조용하고 되돌리기 어려운 fail-open이다.
    """
    empty = {name: {} for name in pc.SECTIONS}
    hooks = pc.build_hooks(empty, empty, auto_ids=frozenset(), held_state=pc.EMPTY_HELD)
    cfg = {"options": {"apiKey": pc.SENTINEL}}
    assert hooks["pluginConfigs"]["secret_keys"](cfg) == ["apiKey"]
    for section in ("enabledPlugins", "extraKnownMarketplaces"):
        assert hooks[section]["secret_keys"](cfg) == []


def test_marketplace_arg_git_source_falls_back_to_repo_when_url_is_absent():
    """후보가 둘인 것이 8.6의 장치다 — 하나로 줄여도 아무 테스트가 실패하지 않았다(변조 실측).

    어느 쪽이 옳은 필드인지는 여전히 주장하지 않는다. 둘 다 있을 때의 우선순위도
    고정하지 않는다 — 필드 이름이 미측정이라 짐작을 계약으로 굳히지 않기 위해서다.
    여기서 고정하는 것은 **폴백이 살아 있다**는 사실 하나뿐이다.
    """
    assert pc.marketplace_arg({"source": {"source": "git", "repo": "u/r"}}) == "u/r"


def test_marketplace_reason_distinguishes_three_ways_to_fail_to_build_an_argument():
    """"인자를 만들 수 없다"의 세 갈래는 사용자가 할 일이 서로 다르다 (10.2).

    (a) 종류는 멀쩡한데 필드가 비었다 → **필드 이름**을 대야 고칠 수 있다. 종류만
        지목하면 멀쩡한 종류가 범인이 된다.
    (b) 우리가 모르는 종류다 → 필드를 물어봐야 소용없다.
    (c) 값에서 종류조차 읽을 수 없다 → 종류를 그대로 끼워 넣으면 파이썬 값 None이
        사용자 눈앞에 나간다. 이 경로는 도달 가능하다 — _recognized_sections는 섹션이
        객체인 것만 요구하므로 {"extraKnownMarketplaces": {"m": "oops"}}는 정상 인식된다.
    """
    def reason(value):
        return pc.unrestorable_reason("extraKnownMarketplaces", "m", value, {})

    empty_field = reason({"source": {"source": "github", "repo": ""}})
    assert "repo" in empty_field and "github" in empty_field

    unknown_kind = reason({"source": {"source": "novel"}})
    assert "novel" in unknown_kind and "인자" in unknown_kind

    for opaque in ("oops", None, {"source": "oops"}, {"source": {"source": 42}}):
        message = reason(opaque)
        assert "None" not in message and "인자" in message


def test_build_hooks_closes_the_same_repo_over_restorable_and_reason():
    """판정과 사유가 **같은 repo**를 보게 훅 묶음이 한 번 닫는다.

    unrestorable_reason은 문서 전체를 받는데 restorable(key, value)는 섹션 층위라,
    한 스크립트 안에서 층위가 섞여 섹션 매핑을 문서 자리에 넘기기 쉽다. 그러면
    복원 가능한 항목에 "레포에 소스가 없다"가 붙는다 — 판정은 참인데 사유가 거짓이고,
    둘 다 무증상이다. held_context가 hold·held_kinds에 쓴 처방과 같은 처방이다.
    """
    repo = {"enabledPlugins": {}, "pluginConfigs": {},
            "extraKnownMarketplaces": {"known": GH}}
    hooks = pc.build_hooks({name: {} for name in pc.SECTIONS}, repo,
                           auto_ids=frozenset(), held_state=pc.EMPTY_HELD)
    cases = (
        ("enabledPlugins", "p@known", True),
        ("enabledPlugins", "p@unknown", True),
        ("enabledPlugins", "p@inline", True),
        ("pluginConfigs", "p@known", {"options": {}}),
        ("extraKnownMarketplaces", "known", GH),
        ("extraKnownMarketplaces", "d",
         {"source": {"source": "directory", "path": "/x"}}),
    )
    for section, key, value in cases:
        ok = hooks[section]["restorable"](key, value)
        why = hooks[section]["reason"](key, value)
        assert ok is (why is None), (section, key, why)
    assert hooks["enabledPlugins"]["reason"]("p@known", True) is None
    assert "소스가 없" in hooks["enabledPlugins"]["reason"]("p@unknown", True)


def test_value_held_for_normalizes_and_keeps_the_argument_order():
    """next_base(value_held=)에 넘길 집합을 만드는 조립을 어댑터에 한 번으로 고정한다.

    안 넘기면 코어 기본값이 빈 집합이라 예외도 경고도 없이 "보류 없음"이 되고, 보류 키가
    base에 얼어붙어 **보류가 풀리는 나중 시점에 케이스 3(삭제)** 으로 터진다.
    조립의 함정 둘이 이 단정에 걸린다 —
      * 정규화를 빼면 H4의 지문이 평문으로 계산돼 보류가 통째로 빈다.
      * (local, repo)를 뒤집으면 "레포에만 있는 키"가 전부 사라져 역시 빈다.
    enabledPlugins 쪽은 H3(값 보류이되 행동 보류는 아님)이라 value 축을 action으로
    바꾸는 변조도 함께 잡는다.
    """
    local = {"enabledPlugins": {}, "extraKnownMarketplaces": {}, "pluginConfigs": {}}
    repo = {"enabledPlugins": {"ext@m": ["1.0.0"]}, "extraKnownMarketplaces": {"m": GH},
            "pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    held_state = {"pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
                  "release": {"enabledPlugins": []}}
    hooks = pc.build_hooks(local, repo, auto_ids=frozenset(), held_state=held_state)

    assert pc.value_held_for("pluginConfigs", hooks, local["pluginConfigs"],
                             repo["pluginConfigs"]) == frozenset({"delta@m"})
    assert pc.value_held_for("enabledPlugins", hooks, local["enabledPlugins"],
                             repo["enabledPlugins"]) == frozenset({"ext@m"})
    # 그 키가 행동 보류는 **아니다** — value 축을 쓰는 것이 이 함수의 계약이다.
    assert hooks["enabledPlugins"]["hold"]({}, {"ext@m": ["1.0.0"]})["action"] == set()
