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


def write_bom(tmp_path, name, data):
    """UTF-8 BOM이 붙은 JSON. Windows 계열 편집기가 실제로 만드는 형태다.

    open(path, "rb") + json.loads(bytes)는 json.detect_encoding이 BOM을 처리해 통과하지만,
    open(path, "r")로 읽으면 BOM 문자가 본문에 남아 JSONDecodeError가 된다.
    """
    path = tmp_path / name
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))
    return str(path)


GH = {"source": {"source": "github", "repo": "june20516/suberpower"}}


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


def test_read_local_reads_bytes_so_a_bom_does_not_look_broken(tmp_path):
    """settings.json을 바이너리로 읽는다 — BOM이 붙어도 "읽기 실패"가 아니다.

    open(path, "rb")를 open(path, "r")로 바꾸면 BOM 문자가 본문에 남아 JSONDecodeError가
    되고, 그 기기의 백업이 통째로 skip된다. 그 변조를 잡는 줄이다.
    """
    path = write_bom(tmp_path, "settings.json", {"enabledPlugins": {"p@m": True}})
    assert pc.read_local_sections(path)["enabledPlugins"] == {"p@m": True}


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


def test_read_auto_ids_reads_bytes_so_a_bom_does_not_look_broken(tmp_path):
    """installed_plugins.json도 바이너리로 읽는다 — "rb"→"r" 변조를 잡는 줄이다.

    BOM 하나로 auto 판정이 불가가 되면 두 섹션이 통째로 skip된다(3.4).
    """
    path = write_bom(tmp_path, "installed_plugins.json",
                     {"version": 2, "plugins": {"dep@m": [{"scope": "user", "auto": True}]}})
    assert pc.read_auto_ids(path) == frozenset({"dep@m"})


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


def test_read_held_state_reads_bytes_so_a_bom_does_not_look_broken(tmp_path):
    """보류 파일도 바이너리로 읽는다 — "rb"→"r" 변조를 잡는 줄이다.

    BOM 하나로 HeldStateUnavailable이 되면 사용자의 보류 선택이 매번 다시 물어진다.
    """
    path = write_bom(tmp_path, "plugins-held.json",
                     {"version": 1, "pluginConfigs": {"delta@m": "abc"}})
    assert pc.read_held_state(path)["pluginConfigs"] == {"delta@m": "abc"}


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


def test_does_not_recognize_document_without_any_known_section():
    """조건 3 — {"foo": 1}이나 {}를 "항목 0개"로 읽으면 그 문서를 덮어써 파괴한다."""
    assert recognized({}) == {}
    assert recognized({"foo": 1}) == {}
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
    """문자열은 손으로 고친 문서를 막지 않기 위해, bool은 버전 주장이 아니라서 통과한다."""
    assert recognized({"version": "3", "enabledPlugins": {}}) is not None
    assert recognized({"version": True, "enabledPlugins": {}}) is not None


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


def test_dump_backup_round_trips_through_load(tmp_path):
    path = str(tmp_path / pc.BACKUP_RELPATH)
    doc = {"enabledPlugins": {"p@m": ["1.0.0"]}, "extraKnownMarketplaces": {"m": GH},
           "pluginConfigs": {"p@m": {"options": {"k": "v"}}}}
    pc.dump_backup(doc, path)
    assert pc.load_backup(path) == doc
