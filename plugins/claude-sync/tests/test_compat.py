"""lib/compat.py의 버전 호환성 판정 테스트.

실제 ~/.claude는 건드리지 않는다 — 모든 경로를 tmp_path로 주입한다.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import compat  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("3.0.0", (3, 0, 0)),
    ("v3.0.0", (3, 0, 0)),
    ("3.0.0-rc1", (3, 0, 0)),
    ("  3.0.0", (3, 0, 0)),
    ("3.10.0", (3, 10, 0)),
    ("10.0.0", (10, 0, 0)),
])
def test_parse_version_accepts(text, expected):
    assert compat.parse_version(text) == expected


@pytest.mark.parametrize("text", [
    "unknown", "", "3.0", "a.b.c", "v", None, 3, ["3.0.0"], "3.0.0.5", "1.2.3.4",
])
def test_parse_version_rejects(text):
    assert compat.parse_version(text) is None


def test_parse_version_still_accepts_non_numeric_suffix():
    """lookahead가 접미사까지 막아버리면 안 된다 — 막는 것은 4번째 숫자 구성요소뿐이다."""
    assert compat.parse_version("3.0.0-rc1") == (3, 0, 0)
    assert compat.parse_version("3.0.0+build.7") == (3, 0, 0)
    assert compat.parse_version("3.0.0 or later") == (3, 0, 0)


def test_parse_version_orders_by_number_not_string():
    """문자열 비교였다면 '3.10.0' < '3.9.0'이 되어 거짓이 된다."""
    assert compat.parse_version("3.10.0") > compat.parse_version("3.9.0")
    assert compat.parse_version("3.0.0") < compat.parse_version("3.0.1")
    assert compat.parse_version("2.9.9") < compat.parse_version("10.0.0")


def write_plugin_json(tmp_path, obj=None, *, broken=False):
    """plugin.json 역할의 임시 파일 경로를 반환한다.

    broken=True면 깨진 JSON을 쓴다. obj는 그대로 직렬화한다.
    """
    path = tmp_path / "plugin.json"
    path.write_text("{ not json" if broken else json.dumps(obj), encoding="utf-8")
    return str(path)


def test_read_plugin_version_reads_version(tmp_path):
    path = write_plugin_json(tmp_path, {"name": "claude-sync", "version": "3.0.0"})
    assert compat.read_plugin_version(path) == "3.0.0"


def test_read_plugin_version_missing_file(tmp_path):
    assert compat.read_plugin_version(str(tmp_path / "nope.json")) is None


def test_read_plugin_version_broken_json(tmp_path):
    assert compat.read_plugin_version(write_plugin_json(tmp_path, broken=True)) is None


@pytest.mark.parametrize("obj", [{}, {"version": 3}, {"version": None}, [], "x"])
def test_read_plugin_version_unusable(tmp_path, obj):
    assert compat.read_plugin_version(write_plugin_json(tmp_path, obj)) is None


def write_metadata(tmp_path, obj=None, *, broken=False, missing=False):
    """sync-metadata.json 파일 경로를 반환한다 (레포 디렉토리가 아니라 파일 경로다).

    missing=True면 파일을 만들지 않는다. broken=True면 깨진 JSON을 쓴다.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    path = repo / compat.METADATA_RELPATH
    if broken:
        path.write_text("{ not json", encoding="utf-8")
    elif not missing:
        path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def test_load_metadata_reads_dict(tmp_path):
    path = write_metadata(tmp_path, {"min_reader_version": "3.0.0"})
    assert compat.load_metadata(path) == {"min_reader_version": "3.0.0"}


def test_load_metadata_missing_is_none(tmp_path):
    path = write_metadata(tmp_path, missing=True)
    assert compat.load_metadata(path) is None


def test_load_metadata_broken_is_none(tmp_path):
    """깨진 metadata를 차단 근거로 삼으면 데드락이다 — 그 파일을 고치는 것이 다음 백업이다."""
    path = write_metadata(tmp_path, broken=True)
    assert compat.load_metadata(path) is None


@pytest.mark.parametrize("obj", [[], "x", 3, None])
def test_load_metadata_non_dict_is_none(tmp_path, obj):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    assert compat.load_metadata(str(path)) is None


def test_default_plugin_json_path_points_at_real_plugin_json():
    """lib/../.claude-plugin/plugin.json 이 실제로 존재해야 한다."""
    assert os.path.isfile(compat.default_plugin_json_path())
    assert compat.read_plugin_version(compat.default_plugin_json_path()) is not None


def test_load_metadata_directory_path_is_unreadable(tmp_path):
    """열 수 없는 경로에서도 예외를 던지지 않는다 — CLI가 종료 코드 0을 지켜야 한다."""
    d = tmp_path / "as_dir"
    d.mkdir()
    assert compat.load_metadata(str(d)) is compat.UNREADABLE


@pytest.mark.skipif(os.getuid() == 0, reason="root는 권한 검사를 건너뛴다")
def test_load_metadata_unreadable_file_is_not_none(tmp_path):
    """못 읽음을 없음으로 접으면 상위 버전이 쓴 레포를 통과시킨다."""
    p = tmp_path / "m.json"
    p.write_text('{"min_reader_version": "9.9.9"}', encoding="utf-8")
    p.chmod(0)
    try:
        assert compat.load_metadata(str(p)) is compat.UNREADABLE
    finally:
        p.chmod(0o644)


def test_load_metadata_missing_is_none_not_unreadable(tmp_path):
    """파일 없음과 못 읽음은 서로 다른 값이어야 한다."""
    result = compat.load_metadata(str(tmp_path / "nope.json"))
    assert result is None
    assert result is not compat.UNREADABLE


@pytest.mark.skipif(os.getuid() == 0, reason="root는 권한 검사를 건너뛴다")
def test_read_plugin_version_unreadable_file_is_none(tmp_path):
    """plugin.json 쪽은 못 읽어도 None이면 된다 — 상위 판정이 차단으로 접는다."""
    p = tmp_path / "plugin.json"
    p.write_text('{"version": "3.0.0"}', encoding="utf-8")
    p.chmod(0)
    try:
        assert compat.read_plugin_version(str(p)) is None
    finally:
        p.chmod(0o644)


def test_read_plugin_version_defaults_to_real_plugin_json():
    """인자 없이 부르면 이 플러그인의 plugin.json을 읽는다."""
    assert compat.read_plugin_version() == compat.read_plugin_version(
        compat.default_plugin_json_path()
    )
    assert compat.read_plugin_version() is not None


# --- spec 6.4 판정표 전수 ---

def test_evaluate_0_unreadable_metadata_blocks():
    """못 읽음은 없음이 아니다 — 상위 버전이 쓴 레포를 통과시키면 안 된다."""
    v = compat.evaluate(compat.UNREADABLE, "3.0.0")
    assert v["blocked"] is True
    assert v["reason"] == "metadata_unreadable"


def test_message_for_unreadable_metadata_omits_upgrade_commands():
    """플러그인을 올려도 해결되지 않는다. 잘못된 해법을 내밀면 안 된다."""
    msg = compat.evaluate(compat.UNREADABLE, "3.0.0")["message"]
    assert "claude plugin update" not in msg
    assert "권한" in msg
    assert compat.METADATA_RELPATH in msg


def test_evaluate_1_no_metadata_passes():
    """표식 없음 = 2.x가 쓴 것 = 우리보다 앞설 수 없다 (결정 4)."""
    v = compat.evaluate(None, "3.0.0")
    assert v["blocked"] is False
    assert v["reason"] is None
    assert v["message"] == ""


def test_evaluate_2_no_min_reader_field_passes():
    v = compat.evaluate({"written_by_version": "3.0.0"}, "3.0.0")
    assert v["blocked"] is False
    assert v["repo_written_by"] == "3.0.0"


@pytest.mark.parametrize("bad", ["", "unknown", "3.0", 3, ["3.0.0"]])
def test_evaluate_3_unparsable_min_reader_blocks(bad):
    """필드가 있는데 못 읽는다 = 상위 버전이 모르는 형식으로 썼을 수 있다. 모르면 안 쓴다."""
    v = compat.evaluate({"min_reader_version": bad}, "3.0.0")
    assert v["blocked"] is True
    assert v["reason"] == "min_reader_unparsable"


def test_evaluate_explicit_null_is_treated_as_absent():
    """JSON의 null은 필드 없음과 구별되지 않는다 — dict.get이 둘 다 None을 준다.

    구별하려면 센티널이 필요한데, 여기서는 구별할 실익이 없다. null은 '요구 없음'이다.
    """
    v = compat.evaluate({"min_reader_version": None}, "3.0.0")
    assert v["blocked"] is False
    assert v["reason"] is None


def test_evaluate_4_unknown_my_version_with_requirement_blocks():
    """레포가 최소치를 요구하는데 충족을 증명할 수 없다."""
    v = compat.evaluate({"min_reader_version": "3.0.0"}, None)
    assert v["blocked"] is True
    assert v["reason"] == "my_version_unknown"


def test_evaluate_4b_unknown_my_version_without_requirement_passes():
    """요구가 없으면 증명할 것도 없다."""
    v = compat.evaluate(None, None)
    assert v["blocked"] is False


def test_evaluate_5_older_than_min_reader_blocks():
    v = compat.evaluate({"min_reader_version": "4.0.0"}, "3.0.0")
    assert v["blocked"] is True
    assert v["reason"] == "older_than_min_reader"
    assert v["repo_min_reader"] == "4.0.0"
    assert v["my_version"] == "3.0.0"


def test_evaluate_6_equal_or_newer_passes():
    assert compat.evaluate({"min_reader_version": "3.0.0"}, "3.0.0")["blocked"] is False
    assert compat.evaluate({"min_reader_version": "3.0.0"}, "3.10.0")["blocked"] is False


def test_evaluate_uses_numeric_comparison():
    """3.9.0 기기가 3.10.0을 요구하는 레포를 만나면 막혀야 한다.

    문자열 비교였다면 '3.9.0' > '3.10.0'이 참이 되어 통과해 버린다.
    """
    v = compat.evaluate({"min_reader_version": "3.10.0"}, "3.9.0")
    assert v["blocked"] is True


# --- 안내 문구 ---

def test_message_contains_both_commands_and_restart_notice():
    v = compat.evaluate({"min_reader_version": "4.0.0"}, "3.0.0")
    msg = v["message"]
    assert "claude plugin marketplace update claude-sync" in msg
    assert "claude plugin update claude-sync" in msg
    assert "/reload-plugins" in msg
    assert "재시작" in msg
    assert "4.0.0" in msg and "3.0.0" in msg


@pytest.mark.parametrize("meta,mine", [
    (compat.UNREADABLE, "3.0.0"),                  # metadata_unreadable
    ({"min_reader_version": "?"}, "3.0.0"),        # min_reader_unparsable
    ({"min_reader_version": "4.0.0"}, None),       # my_version_unknown
    ({"min_reader_version": "4.0.0"}, "3.0.0"),    # older_than_min_reader
])
def test_message_says_nothing_about_stopping_or_continuing(meta, mine):
    """행동은 각 SKILL.md가 정한다 — backup은 중단, status는 계속, restore는 질문.

    네 갈래를 전부 본다. 한 갈래만 보면 나머지에 행동 단어가 새어 들어가도 못 잡는다.
    """
    msg = compat.evaluate(meta, mine)["message"]
    assert msg != ""
    assert "중단" not in msg
    assert "계속" not in msg
    assert "멈춥니다" not in msg


def test_message_for_unknown_my_version_suggests_checking_install():
    """자기 버전을 못 읽었다면 설치가 깨졌을 수 있다 — update만으로 안 풀린다."""
    msg = compat.evaluate({"min_reader_version": "4.0.0"}, None)["message"]
    assert "claude plugin list" in msg


def test_message_for_unknown_my_version():
    msg = compat.evaluate({"min_reader_version": "4.0.0"}, None)["message"]
    assert "버전 미상" in msg
    assert "claude plugin update claude-sync" in msg


def test_message_for_unparsable_min_reader():
    msg = compat.evaluate({"min_reader_version": "?"}, "3.0.0")["message"]
    assert "알아볼 수 없" in msg
    assert "claude plugin update claude-sync" in msg


def test_upgrade_message_rejects_unknown_reason():
    """판정표에 행을 더하고 문구를 안 더하면 조용히 틀린 문장이 나오면 안 된다."""
    with pytest.raises(ValueError):
        compat._upgrade_message("some_future_reason", None, "3.0.0")


@pytest.mark.parametrize("reason", [
    "metadata_unreadable", "min_reader_unparsable",
    "my_version_unknown", "older_than_min_reader",
])
def test_upgrade_message_covers_every_blocking_reason(reason):
    """_block_reason이 낼 수 있는 모든 차단 사유에 문구가 있어야 한다."""
    msg = compat._upgrade_message(reason, "4.0.0", "3.0.0")
    assert msg and "알 수 없음" not in msg


# --- check() + CLI ---

LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
COMPAT_CLI = os.path.join(LIB_DIR, "compat.py")


def dir_snapshot(path):
    """디렉토리 안 모든 파일의 (상대경로, 내용) 집합. 쓰기 여부 검증용."""
    out = {}
    for root, _, files in os.walk(path):
        for f in files:
            full = os.path.join(root, f)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, path)] = fh.read()
    return out


def repo_with_metadata(tmp_path, obj=None, **kw):
    """레포 디렉토리 경로를 반환한다.

    write_metadata는 파일 경로를 주는데 check()는 레포 디렉토리를 받는다.
    """
    return os.path.dirname(write_metadata(tmp_path, obj, **kw))


def test_check_passes_on_repo_without_metadata(tmp_path):
    repo = repo_with_metadata(tmp_path, missing=True)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(repo, plugin_json_path=plugin_json)
    assert v["status"] == "ok"
    assert v["blocked"] is False


def test_check_blocks_on_higher_min_reader(tmp_path):
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "4.0.0",
                                         "written_by_version": "4.0.0"})
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(repo, plugin_json_path=plugin_json)
    assert v["blocked"] is True
    assert v["repo_written_by"] == "4.0.0"


def test_check_writes_nothing(tmp_path):
    """읽기 전용이다. 차단 판정이 나도 레포를 건드리지 않는다."""
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "4.0.0"})
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    before = dir_snapshot(repo)
    compat.check(repo, plugin_json_path=plugin_json)
    assert dir_snapshot(repo) == before


def test_cli_prints_json_and_exits_zero(tmp_path):
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "3.0.0"})
    proc = subprocess.run([sys.executable, COMPAT_CLI, repo],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["blocked"] is False
    assert out["repo_min_reader"] == "3.0.0"


def test_cli_exits_zero_even_when_blocking(tmp_path):
    """비-0으로 끝내면 SKILL.md의 셸이 set -e로 죽어 안내를 못 보여준다."""
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "99.0.0"})
    proc = subprocess.run([sys.executable, COMPAT_CLI, repo],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["blocked"] is True
    assert "claude plugin update claude-sync" in out["message"]


def test_cli_without_argument_fails():
    proc = subprocess.run([sys.executable, COMPAT_CLI], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "사용:" in proc.stderr


def test_check_blocks_when_metadata_unreadable(tmp_path):
    """load_metadata와 evaluate를 잇는 배선이 UNREADABLE을 접으면 안 된다."""
    repo = tmp_path / "repo"
    (repo / compat.METADATA_RELPATH).mkdir(parents=True)   # 디렉토리라 열 수 없다
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(str(repo), plugin_json_path=plugin_json)
    assert v["blocked"] is True
    assert v["reason"] == "metadata_unreadable"


@pytest.mark.parametrize("bad", ["", "/no/such/repo-dir-xyz", None, 3])
def test_check_blocks_when_repo_missing(bad, tmp_path):
    """빈 문자열은 cwd의 파일을 읽어 거짓 통과를 낸다. 없는 경로도 결론이 아니다."""
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(bad, plugin_json_path=plugin_json)
    assert v["blocked"] is True
    assert v["reason"] == "repo_not_found"
    assert "claude plugin update" not in v["message"]


def test_check_still_passes_on_real_repo_without_metadata(tmp_path):
    """레포가 실제로 있고 표식만 없으면 통과다 — repo_not_found가 과하게 잡으면 안 된다."""
    repo = repo_with_metadata(tmp_path, missing=True)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(repo, plugin_json_path=plugin_json)
    assert v["blocked"] is False


# --- 다운그레이드 판정 (spec 9.1) ---

@pytest.mark.parametrize("data,expected", [
    (None, "absent"),
    (b"{ not json", "broken"),
    (b"[]", "v1_array"),
    (b'[{"name":"a","command":"a"}]', "v1_array"),
    (b'{"version":2,"servers":{}}', "v2_object"),
    (b'{"servers":{"a":{}}}', "v2_object"),
    (b'{"version":3,"servers":{}}', "v2_object"),
    (b"null", "unknown"),
    (b'"x"', "unknown"),
    (b'{"servers":[]}', "unknown"),
    (b"3", "unknown"),
])
def test_shape_of(data, expected):
    assert compat.shape_of(data) == expected


def test_shape_of_accepts_str():
    assert compat.shape_of('{"version":2,"servers":{}}') == "v2_object"


def test_downgrade_suspected_when_repo_v1_and_base_v2():
    """레포는 v1인데 내 base는 v2였다 = 옛 기기가 덮어썼다."""
    assert compat.downgrade_suspected("v1_array", "v2_object") is True


@pytest.mark.parametrize("repo,base", [
    ("v1_array", "v1_array"),    # 정말 오래된 레포
    ("v1_array", "absent"),      # 이력 없음 — 근거가 될 수 없다
    ("v1_array", "broken"),      # 신뢰할 수 없는 이력 (불변식 2)
    ("v1_array", "unknown"),
    ("v2_object", "v2_object"),  # 정상
    ("v2_object", "v1_array"),   # 오히려 전진
    ("absent", "v2_object"),     # 파일이 사라진 것은 다른 문제다
    ("broken", "v2_object"),
])
def test_downgrade_not_suspected(repo, base):
    assert compat.downgrade_suspected(repo, base) is False


def test_shape_of_rejects_parsed_object():
    """호출자 오류를 값으로 삼키면 그 실수가 '사고 없음'이라는 결론이 된다(불변식 6)."""
    with pytest.raises(TypeError):
        compat.shape_of([{"name": "a", "command": "a"}])
    with pytest.raises(TypeError):
        compat.shape_of({"servers": {}})
    with pytest.raises(TypeError):
        compat.shape_of(3)


@pytest.mark.parametrize("repo,base", [
    ("v1array", "v2_object"),      # 오타
    ("v1_array", "v2object"),      # 오타
    ("V1_ARRAY", "V2_OBJECT"),     # 대소문자
    (None, None),
    ("", ""),
])
def test_downgrade_suspected_rejects_unknown_shape(repo, base):
    """모르는 shape를 조용히 False로 만들면 오타가 '사고 없음'이 된다(불변식 6)."""
    with pytest.raises(ValueError):
        compat.downgrade_suspected(repo, base)


def test_downgrade_suspected_accepts_unreadable_shape():
    """읽기 실패는 표현 가능한 상태다 — 탐지하지 않되 예외도 아니다."""
    assert compat.downgrade_suspected(compat.SHAPE_UNREADABLE, compat.SHAPE_V2_OBJECT) is False
    assert compat.downgrade_suspected(compat.SHAPE_V1_ARRAY, compat.SHAPE_UNREADABLE) is False


def test_shape_constants_match_returned_values():
    """상수와 실제 반환값이 갈리면 호출부가 조용히 어긋난다."""
    assert compat.shape_of(None) == compat.SHAPE_ABSENT
    assert compat.shape_of(b"{ nope") == compat.SHAPE_BROKEN
    assert compat.shape_of(b"[]") == compat.SHAPE_V1_ARRAY
    assert compat.shape_of(b'{"servers":{}}') == compat.SHAPE_V2_OBJECT
    assert compat.shape_of(b"null") == compat.SHAPE_UNKNOWN
