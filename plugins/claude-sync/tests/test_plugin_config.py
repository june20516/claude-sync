"""플러그인 어댑터 단위 테스트 (spec 3·4·6·7·8장).

실제 ~/.claude는 절대 건드리지 않는다 — 모든 읽기 함수가 경로 인자를 받는다.
"""
import json
import os

import pytest

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
