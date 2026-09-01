"""lib/compat.py의 버전 호환성 판정 테스트.

실제 ~/.claude는 건드리지 않는다 — 모든 경로를 tmp_path로 주입한다.
"""
import itertools
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import plugin_config as pc  # noqa: E402

from marks import requires_permission_bits  # noqa: E402


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


@requires_permission_bits
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


@requires_permission_bits
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


def test_main_falls_back_to_check_failed(monkeypatch, capsys):
    """마지막 방어선. 예외가 트레이스백으로 새어 나가면 안 된다.

    새면 종료 코드가 비-0이 되고 stdout에 JSON이 없다. SKILL.md는 그것을 8.0에 따라
    "검사가 성립하지 않았다"로 다루므로 차단은 유지되지만, compat.py가 만들어 주는
    문구 대신 사용자가 트레이스백을 본다. check_failed는 그 경로를 JSON 한 덩이로
    유지하기 위한 것이다.
    """
    def boom(_repo_dir):
        raise RuntimeError("예상 못 한 고장")

    monkeypatch.setattr(compat, "check", boom)
    monkeypatch.setattr(sys, "argv", ["compat.py", "/tmp"])
    compat.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "error"
    assert out["blocked"] is True
    assert out["reason"] == "check_failed"
    assert "RuntimeError" in out["message"]
    # 업그레이드로 풀리는 갈래가 아니다 — restore SKILL.md가 그 사실에 기대어 분기한다.
    assert "claude plugin update" not in out["message"]


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


# --- 다운그레이드 판정 (spec 9.1 · 11.6) ---
#
# 형태 판정표(plan ③의 정본)를 두 relpath 각각으로 전수한다.
# 각 relpath마다 여섯 형태가 있어야 한다 — absent·broken·unreadable·v1·v2·unknown.
# unreadable만 이 표에 없다: shape_of가 내지 않고 읽는 쪽이 만든다.
# 그 완전성은 test_shape_table_covers_every_shape_per_relpath가 짝지어 건다.

# 2.x의 extract_plugins.py가 만들 수 있는 문서 전수.
# 그 스크립트는 로컬 settings.json에서 enabledPlugins·extraKnownMarketplaces 중
# **있는 키만** 담아 dump한다(`git show main:.../extract_plugins.py`로 실측) —
# 두 키가 각각 optional이므로 조합은 넷이고, 둘 다 없으면 `{}`다.
# 이 넷이 전부 plugins.json의 옛 형식으로 판정되어야 다운그레이드가 탐지된다.
#
# **부분집합을 손으로 적지 않고 만들어 낸다.** 손으로 적으면 그중 하나(특히 `{}`)가
# 조용히 빠져도 남은 셋이 초록이라 아무도 못 잡는다.
TWO_X_KEY_VALUES = {
    "enabledPlugins": {"a@m": True},
    "extraKnownMarketplaces": {"m": {"source": {"source": "github", "repo": "o/r"}}},
}
TWO_X_PLUGINS_DOCUMENTS = tuple(
    {k: TWO_X_KEY_VALUES[k] for k in combo}
    for size in range(len(TWO_X_KEY_VALUES) + 1)
    for combo in itertools.combinations(sorted(TWO_X_KEY_VALUES), size)
)


def canonical(obj_or_raw):
    """비교용 정규형. 표의 리터럴 공백·키 순서에 단정이 걸리지 않게 한다."""
    if isinstance(obj_or_raw, (bytes, bytearray, str)):
        obj_or_raw = json.loads(obj_or_raw)
    return json.dumps(obj_or_raw, sort_keys=True)


MCP_SHAPE_ROWS = [
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
    # servers가 없는 객체는 여전히 unknown이다 — plugins 규칙(version 존재)이
    # 이 relpath로 새어 들어오면 v2_object가 되어 버린다.
    # 이 행이 표에서 사라지는 것은 test_shape_table_contains_every_version_marked_non_v2_document가 잡는다.
    (b'{"version":2}', "unknown"),
    # 같은 바이트가 plugins.json에서는 v1_object다. 두 규칙이 합쳐지면 한쪽이 깨진다.
    (b"{}", "unknown"),
    (b'{"enabledPlugins":{"a@m":true}}', "unknown"),
]

PLUGINS_SHAPE_ROWS = [
    (None, "absent"),
    (b"{ not json", "broken"),
    # 2.x가 쓰는 실제 값이다(TWO_X_PLUGINS_DOCUMENTS). unknown으로 접으면 사고를 놓친다.
    (b"{}", "v1_object"),
    (b'{"enabledPlugins":{"a@m":true}}', "v1_object"),
    (b'{"extraKnownMarketplaces":{"m":{"source":{"source":"github","repo":"o/r"}}}}',
     "v1_object"),
    (b'{"enabledPlugins":{"a@m":true},'
     b'"extraKnownMarketplaces":{"m":{"source":{"source":"github","repo":"o/r"}}}}',
     "v1_object"),
    (b'{"version":2,"scope":"user","enabledPlugins":{}}', "v2_object"),
    # **값이 아니라 존재를 본다.** 값을 보면 상위 버전 문서가 unknown으로 떨어져
    # downgrade_suspected가 조용히 False가 된다.
    (b'{"version":3,"enabledPlugins":{}}', "v2_object"),
    (b'{"version":null}', "v2_object"),
    # 이 relpath에서 배열은 옛 형식이 아니라 알 수 없는 문서다. v1_array가 **아니다**.
    (b"[]", "unknown"),
    (b'[{"name":"a","command":"a"}]', "unknown"),
    (b"null", "unknown"),
    (b'"x"', "unknown"),
    (b"3", "unknown"),
]

SHAPE_TABLE = (
    [(mc.BACKUP_RELPATH, raw, exp) for raw, exp in MCP_SHAPE_ROWS]
    + [(pc.BACKUP_RELPATH, raw, exp) for raw, exp in PLUGINS_SHAPE_ROWS]
)


def parsable_rows(relpath):
    """그 relpath의 판정표 행 중 **파싱 가능한** 문서의 정규형 집합.

    아래 완전성 단정 셋이 같은 필터를 쓴다. 손으로 세 벌 적으면 조건이 갈라지고,
    갈라진 쪽이 조용히 덜 잡는다 — 이 파일이 스스로 경계하는 드리프트다.
    absent(data가 None)와 broken(구문 오류)은 정규형이 없으므로 뺀다.
    """
    return {canonical(raw) for rp, raw, exp in SHAPE_TABLE
            if rp == relpath
            and exp not in (compat.SHAPE_ABSENT, compat.SHAPE_BROKEN)}


# 각 relpath의 "옛 형식" 문서 표본. 이 문서를 **다른** relpath에서 읽으면 그쪽의
# 옛 형식이 되어서는 안 된다 — 두 relpath가 상수나 규칙을 공유하면 여기서 깨진다.
FOREIGN_OLD_FORM_SAMPLES = {
    mc.BACKUP_RELPATH: (b"[]", b'[{"name":"a","command":"a"}]'),
    pc.BACKUP_RELPATH: (b"{}", b'{"enabledPlugins":{"a@m":true}}'),
}

# 각 relpath에서 "v2 표식(`version` 키)은 달았지만 그 relpath의 v2 조건은 만족하지
# 않는" 문서. mcp-servers.json의 v2 조건은 `servers`가 객체인 것이므로 그런 문서가
# 있고, plugins.json은 version 존재 자체가 v2 조건이라 그런 문서가 없다.
# 바늘(스키마 버전)을 mcp_config에서 뽑는다 — 리터럴을 적으면 SCHEMA_VERSION이
# 올라가도 "v2 표식"을 재지 않는 값이 되어 조용히 초록이 된다.
VERSION_MARKED_BUT_NOT_V2 = {
    mc.BACKUP_RELPATH: json.dumps({"version": mc.SCHEMA_VERSION}).encode("utf-8"),
}

# plugins.json의 version 값이 무엇이든 v2_object여야 한다 — **존재만 본다.**
# 바늘(스키마 버전)을 plugin_config에서 뽑는다. 리터럴을 적으면 SCHEMA_VERSION이
# 올라가도 "상위 버전"을 재지 않는 값이 되어 조용히 초록이 된다.
NEWER_SCHEMA_VERSION = pc.SCHEMA_VERSION + 1
VERSION_VALUES_STILL_V2 = (pc.SCHEMA_VERSION, NEWER_SCHEMA_VERSION, None, "2", 0)

# 각 relpath에서 "그 문서의 섹션 키는 있으나 값이 **객체가 아닌**" 문서.
# mcp-servers.json의 v2 조건은 `servers`가 객체인 것이므로 그런 문서가 있고,
# plugins.json의 v2 조건은 `version`의 **존재**라 섹션 값과 무관하다 — 해당 없음.
#
# **이 문서가 mcp의 v2 조건을 재는 유일한 입력이다.** 판정표에서 이 행이 빠지면
# 프로덕션의 `isinstance(obj.get("servers"), dict)`를 `"servers" in obj`로 약화해도
# 아무 테스트도 빨개지지 않고, 그때 `{"servers": []}`가 v2_object가 되어
# 다운그레이드 판정의 base 쪽이 조용히 참이 된다.
# 바늘(섹션 이름)을 mcp_config.SECTIONS에서 뽑는다 — 리터럴을 적으면 문서 키가 바뀌어도
# "섹션 키는 있는데 객체가 아니다"를 재지 않는 값이 되어 조용히 초록이 된다.
SECTION_KEY_BUT_NOT_OBJECT = {
    mc.BACKUP_RELPATH: json.dumps({mc.SECTIONS[0]: []}).encode("utf-8"),
}


def test_every_selector_has_the_shape_its_assertions_assume():
    """**선택자가 비면 그 위를 도는 단정이 0회 돌아 초록이 된다**(공허해지는 형태 ②).

    아래 완전성 단정들은 전부 선택자 위를 돈다 — 선택자를 한 줄로 지우면 가드와 바늘이
    함께 사라지고, 그 뒤에는 표에서 행을 빼도 아무도 잡지 못한다. 그래서 **선택자 자체의
    모양**을 여기서 건다. 이 파일의 관례이기도 하다(test_shape_table_contains_a_newer_
    schema_document의 `assert newer`가 같은 형태다).

    키·바늘은 두 모듈에서 뽑는다 — 리터럴을 적으면 상수가 바뀌어도 초록이다(M19).
    """
    # SHAPE_TABLE — 비면 test_shape_of가 통째로 사라진다.
    # (test_shape_table_covers_every_shape_per_relpath가 _SHAPES와 등호로 잠그지만,
    #  두 relpath가 모두 표에 있다는 것은 여기서 본다.)
    assert {relpath for relpath, _, _ in SHAPE_TABLE} == {mc.BACKUP_RELPATH,
                                                          pc.BACKUP_RELPATH}

    # FOREIGN_OLD_FORM_SAMPLES — 비면 test_foreign_old_form_is_not_an_old_form_here와
    # test_shape_table_contains_every_foreign_old_form이 함께 공허해진다.
    assert set(FOREIGN_OLD_FORM_SAMPLES) == {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}
    assert all(FOREIGN_OLD_FORM_SAMPLES.values()), "표본이 빈 relpath가 있다"

    # VERSION_MARKED_BUT_NOT_V2 — mcp에만 있는 성질이다("v2 표식은 달았지만 그 relpath의
    # v2 조건인 servers가 없다"). plugins.json은 version 존재가 곧 v2 조건이라 해당 없음.
    assert set(VERSION_MARKED_BUT_NOT_V2) == {mc.BACKUP_RELPATH}

    # VERSION_VALUES_STILL_V2 — 비면 test_plugins_v2_looks_at_presence_not_value가
    # 파라미터 없이 조용히 사라진다. 스키마 버전과 그 상위 버전이 반드시 들어 있어야 한다.
    assert {pc.SCHEMA_VERSION, NEWER_SCHEMA_VERSION} <= set(VERSION_VALUES_STILL_V2)

    # SECTION_KEY_BUT_NOT_OBJECT — mcp에만 있는 성질이다("섹션 키는 있으나 값이 객체가
    # 아니다"). 비면 test_section_key_alone_is_not_v2와 그 완전성 단정이 함께 사라진다.
    assert set(SECTION_KEY_BUT_NOT_OBJECT) == {mc.BACKUP_RELPATH}

    # TWO_X_KEY_VALUES — 개수는 lattice 테스트가 잠근다. 여기서는 키가 실재하는
    # 섹션 이름인지를 본다(오타면 2.x 문서가 아니라 아무 문서나 재게 된다).
    assert set(TWO_X_KEY_VALUES) < set(pc.SECTIONS)


def test_parsable_rows_are_filtered_by_relpath():
    """**선택자가 relpath로 가르지 않으면 그 위의 완전성 단정 셋이 함께 넓어진다.**

    `parsable_rows`의 `rp == relpath` 필터를 지우면 두 relpath가 판정표 **전체**를
    받는다. 그러면 아래 완전성 단정 넷이 "어느 relpath에든 그 문서가 있으면 통과"로
    넓어져, **한쪽 표에서 행을 빼도 다른 쪽에 같은 문서가 남아 있으면 초록**이 된다.
    (이 단정을 넣기 전 실측: 필터를 지워도 1047개가 전부 통과했다.)

    바늘은 손으로 적지 않는다 — 이 파일이 이미 mcp 전용으로 뽑아 둔 문서를 쓴다.
    """
    mcp_rows = parsable_rows(mc.BACKUP_RELPATH)
    plugins_rows = parsable_rows(pc.BACKUP_RELPATH)
    assert mcp_rows and plugins_rows, "선택자가 비면 그 위의 단정 넷이 공허해진다"
    # 필터를 지우면 둘이 같은 집합(합집합)이 되어 두 차집합이 함께 빈다.
    assert mcp_rows - plugins_rows, "mcp 전용 행이 없다 — 필터가 사라졌는가"
    assert plugins_rows - mcp_rows, "plugins 전용 행이 없다 — 필터가 사라졌는가"
    # 위 두 줄은 필터를 **뒤집어도**(rp != relpath) 살아남는다. 이 바늘이 방향을 문다.
    needle = canonical(VERSION_MARKED_BUT_NOT_V2[mc.BACKUP_RELPATH])
    assert needle in mcp_rows, "mcp 전용 바늘이 mcp 쪽에 없다"
    assert needle not in plugins_rows, "선택자가 relpath를 뒤집어 읽는다"


@pytest.mark.parametrize("relpath,data,expected", SHAPE_TABLE)
def test_shape_of(relpath, data, expected):
    assert compat.shape_of(data, relpath) == expected


@pytest.mark.parametrize("value", VERSION_VALUES_STILL_V2)
def test_plugins_v2_looks_at_presence_not_value(value):
    """v2 판정은 version의 *값*이 아니라 *존재*를 본다.

    값을 보면 상위 버전 문서가 unknown으로 떨어져 downgrade_suspected가 조용히
    False가 된다 — 이 함수가 답할 질문이 아니다(불변식 6).
    """
    raw = json.dumps({"version": value, "enabledPlugins": {}}).encode("utf-8")
    assert compat.shape_of(raw, pc.BACKUP_RELPATH) == compat.SHAPE_V2_OBJECT


def test_shape_table_contains_a_newer_schema_document():
    """입력 축 완전성 — 표에서 `version: 3` 행을 빼면 여기서 잡힌다.

    바늘을 plugin_config.SCHEMA_VERSION에서 뽑았으므로 표가 스스로 줄어드는 것을
    표 자신이 아니라 이 단정이 본다.
    """
    newer = [raw for relpath, raw, exp in SHAPE_TABLE
             if relpath == pc.BACKUP_RELPATH
             and exp not in (compat.SHAPE_ABSENT, compat.SHAPE_BROKEN)
             and isinstance(json.loads(raw), dict)
             and isinstance(json.loads(raw).get("version"), int)
             and json.loads(raw)["version"] > pc.SCHEMA_VERSION]
    assert newer, "판정표에 상위 스키마(version > %d) 문서가 없다" % pc.SCHEMA_VERSION


@pytest.mark.parametrize("relpath,raw", sorted(VERSION_MARKED_BUT_NOT_V2.items()))
def test_version_marker_alone_is_not_v2(relpath, raw):
    """version 표식만으로 v2가 되어서는 안 되는 relpath가 있다(축 분리).

    plugins 규칙(version 존재 = v2)이 mcp-servers.json으로 새어 들어오면 `servers`가
    없는 문서가 v2_object가 되고, 그 문서가 base였을 때 다운그레이드 판정의 base 쪽이
    조용히 참이 된다.
    """
    assert compat.shape_of(raw, relpath) == compat.SHAPE_UNKNOWN


def test_shape_table_contains_every_version_marked_non_v2_document():
    """입력 축 완전성 — 표에서 `mcp-servers.json + {"version":2}` 행을 빼면 여기서 잡힌다.

    바늘을 mcp_config.SCHEMA_VERSION에서 뽑았으므로 표가 스스로 줄어드는 것을
    표 자신이 아니라 이 단정이 본다.
    """
    for relpath, raw in VERSION_MARKED_BUT_NOT_V2.items():
        assert canonical(raw) in parsable_rows(relpath), (
            "%s 판정표에 %r 행이 없다" % (relpath, raw))


@pytest.mark.parametrize("relpath,raw", sorted(SECTION_KEY_BUT_NOT_OBJECT.items()))
def test_section_key_alone_is_not_v2(relpath, raw):
    """섹션 키의 **존재**만으로 v2가 되어서는 안 되는 relpath가 있다.

    mcp-servers.json의 v2 조건은 `servers`가 **객체**인 것이다. 그 조건을
    `"servers" in obj`로 약화하면 `{"servers": []}`가 v2_object가 되고, 그 문서가
    base였을 때 다운그레이드 판정의 base 쪽이 조용히 참이 된다(불변식 6).
    """
    assert compat.shape_of(raw, relpath) == compat.SHAPE_UNKNOWN


def test_shape_table_contains_every_section_key_without_object_document():
    """입력 축 완전성 — 표에서 `mcp-servers.json + {"servers":[]}` 행을 빼면 여기서 잡힌다.

    바늘을 mcp_config.SECTIONS에서 뽑았으므로 표가 스스로 줄어드는 것을 표 자신이
    아니라 이 단정이 본다.
    """
    for relpath, raw in SECTION_KEY_BUT_NOT_OBJECT.items():
        assert canonical(raw) in parsable_rows(relpath), (
            "%s 판정표에 %r 행이 없다" % (relpath, raw))


def test_foreign_old_form_is_not_an_old_form_here():
    """한 문서의 옛 형식이 다른 relpath에서 옛 형식으로 읽히면 안 된다(축 분리)."""
    for owner, samples in FOREIGN_OLD_FORM_SAMPLES.items():
        for raw in samples:
            assert compat.shape_of(raw, owner) == compat._OLD_SHAPE[owner]
            for other in FOREIGN_OLD_FORM_SAMPLES:
                if other != owner:
                    assert compat.shape_of(raw, other) != compat._OLD_SHAPE[other]


def test_shape_table_contains_every_foreign_old_form():
    """입력 축 완전성 — 표에서 `plugins.json + []` 행을 빼면 여기서 잡힌다."""
    for relpath in FOREIGN_OLD_FORM_SAMPLES:
        rows = parsable_rows(relpath)
        missing = [raw for owner, samples in FOREIGN_OLD_FORM_SAMPLES.items()
                   if owner != relpath
                   for raw in samples if canonical(raw) not in rows]
        assert not missing, "%s 판정표에 타 relpath 옛 형식이 빠졌다: %r" % (
            relpath, missing)


def test_two_x_document_set_is_the_whole_subset_lattice():
    """두 키가 각각 optional이므로 조합은 2**2 = 4이고 `{}`가 그중 하나다.

    이 단정이 없으면 TWO_X_KEY_VALUES에서 키가 빠져도 아래 단정들이 조용히 줄어든다.
    """
    assert len(TWO_X_PLUGINS_DOCUMENTS) == 2 ** len(TWO_X_KEY_VALUES) == 4
    assert {} in TWO_X_PLUGINS_DOCUMENTS


@pytest.mark.parametrize("doc", TWO_X_PLUGINS_DOCUMENTS)
def test_two_x_plugins_backup_is_old_shape(doc):
    """2.x 백업이 만드는 문서는 전부 옛 형식이어야 한다 — 아니면 사고가 탐지되지 않는다."""
    raw = json.dumps(doc).encode("utf-8")
    assert compat.shape_of(raw, pc.BACKUP_RELPATH) == compat.SHAPE_V1_OBJECT


def test_shape_table_contains_every_2x_document():
    """입력 축 완전성 — 표에서 `{}` 행을 빼면 여기서 잡힌다.

    바늘을 표 밖(2.x 스크립트의 동작)에서 뽑아 왔으므로, 표가 스스로 줄어드는 것을
    표 자신이 아니라 이 단정이 본다.
    """
    rows = parsable_rows(pc.BACKUP_RELPATH)
    missing = [d for d in TWO_X_PLUGINS_DOCUMENTS if canonical(d) not in rows]
    assert not missing, "판정표에 2.x 문서가 빠졌다: %r" % (missing,)


def test_shape_rules_and_old_shape_cover_exactly_the_two_backup_documents():
    """relpath 표 둘의 키 집합이 실제 백업 문서 둘과 같아야 한다.

    리터럴을 손으로 적지 않고 두 모듈에서 뽑는다 — 적으면 BACKUP_RELPATH가 바뀌어도
    이 테스트는 초록이고, 그때 compat은 실제로 쓰이지 않는 relpath만 알게 된다.
    """
    expected = {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}
    assert set(compat._SHAPE_RULES) == expected
    assert set(compat._OLD_SHAPE) == expected


def test_shape_table_covers_every_shape_per_relpath():
    """여섯 행이 relpath마다 있어야 한다(absent·broken·unreadable·v1·v2·unknown).

    unreadable은 shape_of가 내지 않으므로(읽는 쪽이 만든다) 여기서 더해 준다.
    다른 relpath의 옛 형식 상수도 더해 준 뒤 _SHAPES와 같은지 본다 — 표가 줄어들면
    한쪽이 비고, _SHAPES에 상수를 더하고 표를 안 늘리면 다른 쪽이 빈다.
    """
    old_shapes = {compat.SHAPE_V1_ARRAY, compat.SHAPE_V1_OBJECT}
    for relpath in (mc.BACKUP_RELPATH, pc.BACKUP_RELPATH):
        produced = {exp for rp, _, exp in SHAPE_TABLE if rp == relpath}
        foreign = old_shapes - {compat._OLD_SHAPE[relpath]}
        # 다른 relpath의 옛 형식이 이 relpath에서 나오면 안 된다(축 분리).
        assert produced.isdisjoint(foreign), relpath
        assert produced | {compat.SHAPE_UNREADABLE} | foreign == compat._SHAPES, relpath


def test_shape_of_accepts_str():
    assert compat.shape_of('{"version":2,"servers":{}}', mc.BACKUP_RELPATH) == "v2_object"
    assert compat.shape_of('{"version":2}', pc.BACKUP_RELPATH) == "v2_object"


def test_shape_of_requires_relpath():
    """기본값을 두면 갱신 안 된 호출자가 조용히 mcp 규칙으로 plugins.json을 판정한다."""
    with pytest.raises(TypeError):
        compat.shape_of(b"{}")


@pytest.mark.parametrize("relpath", ["", None, "plugins", "mcp-servers.json ",
                                     "sync-metadata.json"])
# data를 함께 돈다: relpath 검증이 데이터 처리 **뒤로** 밀리면 None은 absent,
# 깨진 JSON은 broken, 파싱된 객체는 TypeError가 되어 오타가 조용히 값이 된다.
@pytest.mark.parametrize("data", [None, b"{}", b"[]", b"{ not json", 3])
def test_shape_of_rejects_unknown_relpath(relpath, data):
    """모르는 relpath에 mcp 규칙으로 fallback하면 조용한 fail-open이다(불변식 6)."""
    with pytest.raises(ValueError):
        compat.shape_of(data, relpath)


def test_shape_of_rejects_parsed_object():
    """호출자 오류를 값으로 삼키면 그 실수가 '사고 없음'이라는 결론이 된다(불변식 6)."""
    for relpath in (mc.BACKUP_RELPATH, pc.BACKUP_RELPATH):
        with pytest.raises(TypeError):
            compat.shape_of([{"name": "a", "command": "a"}], relpath)
        with pytest.raises(TypeError):
            compat.shape_of({"servers": {}}, relpath)
        with pytest.raises(TypeError):
            compat.shape_of(3, relpath)


def test_shape_constants_match_returned_values():
    """상수와 실제 반환값이 갈리면 호출부가 조용히 어긋난다."""
    assert compat.shape_of(None, mc.BACKUP_RELPATH) == compat.SHAPE_ABSENT
    assert compat.shape_of(b"{ nope", mc.BACKUP_RELPATH) == compat.SHAPE_BROKEN
    assert compat.shape_of(b"[]", mc.BACKUP_RELPATH) == compat.SHAPE_V1_ARRAY
    assert compat.shape_of(b'{"servers":{}}', mc.BACKUP_RELPATH) == compat.SHAPE_V2_OBJECT
    assert compat.shape_of(b"null", mc.BACKUP_RELPATH) == compat.SHAPE_UNKNOWN
    assert compat.shape_of(b"{}", pc.BACKUP_RELPATH) == compat.SHAPE_V1_OBJECT
    assert compat.shape_of(b'{"version":2}', pc.BACKUP_RELPATH) == compat.SHAPE_V2_OBJECT


@pytest.mark.parametrize("relpath,old", [
    (mc.BACKUP_RELPATH, compat.SHAPE_V1_ARRAY),
    (pc.BACKUP_RELPATH, compat.SHAPE_V1_OBJECT),
])
def test_downgrade_suspected_when_repo_is_old_shape_and_base_v2(relpath, old):
    """레포는 그 문서의 옛 형식인데 내 base는 v2였다 = 옛 기기가 덮어썼다.

    옛 형식을 _OLD_SHAPE에서 뽑지 않고 상수를 직접 적는다 — 뽑아 쓰면 relpath 사이에서
    맞바꾼 표를 그대로 읽어 초록이 된다(축 분리).
    """
    assert compat.downgrade_suspected(old, compat.SHAPE_V2_OBJECT, relpath) is True


@pytest.mark.parametrize("relpath,foreign_old", [
    (mc.BACKUP_RELPATH, compat.SHAPE_V1_OBJECT),
    (pc.BACKUP_RELPATH, compat.SHAPE_V1_ARRAY),
])
def test_foreign_old_shape_is_not_a_downgrade(relpath, foreign_old):
    """다른 relpath의 옛 형식은 이 relpath의 옛 형식이 아니다."""
    assert compat.downgrade_suspected(
        foreign_old, compat.SHAPE_V2_OBJECT, relpath) is False


@pytest.mark.parametrize("relpath", [mc.BACKUP_RELPATH, pc.BACKUP_RELPATH])
@pytest.mark.parametrize("repo,base", [
    ("OLD", "OLD"),              # 정말 오래된 레포
    ("OLD", "absent"),           # 이력 없음 — 근거가 될 수 없다
    ("OLD", "broken"),           # 신뢰할 수 없는 이력 (불변식 2)
    ("OLD", "unknown"),
    ("v2_object", "v2_object"),  # 정상
    ("v2_object", "OLD"),        # 오히려 전진
    ("absent", "v2_object"),     # 파일이 사라진 것은 다른 문제다
    ("broken", "v2_object"),
    ("unknown", "v2_object"),
])
def test_downgrade_not_suspected(relpath, repo, base):
    old = compat._OLD_SHAPE[relpath]
    repo = old if repo == "OLD" else repo
    base = old if base == "OLD" else base
    assert compat.downgrade_suspected(repo, base, relpath) is False


@pytest.mark.parametrize("repo,base", [
    ("v1array", "v2_object"),      # 오타
    ("v1_array", "v2object"),      # 오타
    ("V1_ARRAY", "V2_OBJECT"),     # 대소문자
    ("v1object", "v2_object"),     # 새 상수의 오타
    (None, None),
    ("", ""),
])
def test_downgrade_suspected_rejects_unknown_shape(repo, base):
    """모르는 shape를 조용히 False로 만들면 오타가 '사고 없음'이 된다(불변식 6)."""
    with pytest.raises(ValueError):
        compat.downgrade_suspected(repo, base, mc.BACKUP_RELPATH)


@pytest.mark.parametrize("relpath", ["", None, "plugins", "sync-metadata.json"])
def test_downgrade_suspected_rejects_unknown_relpath(relpath):
    """모르는 relpath를 mcp 규칙으로 접으면 조용한 fail-open이다."""
    with pytest.raises(ValueError):
        compat.downgrade_suspected(
            compat.SHAPE_V1_ARRAY, compat.SHAPE_V2_OBJECT, relpath)


def test_downgrade_suspected_requires_relpath():
    """기본값을 두면 갱신 안 된 호출자가 조용히 mcp 규칙으로 판정한다."""
    with pytest.raises(TypeError):
        compat.downgrade_suspected(compat.SHAPE_V1_ARRAY, compat.SHAPE_V2_OBJECT)


@pytest.mark.parametrize("relpath", [mc.BACKUP_RELPATH, pc.BACKUP_RELPATH])
def test_downgrade_suspected_accepts_unreadable_shape(relpath):
    """읽기 실패는 표현 가능한 상태다 — 탐지하지 않되 예외도 아니다."""
    old = compat._OLD_SHAPE[relpath]
    assert compat.downgrade_suspected(
        compat.SHAPE_UNREADABLE, compat.SHAPE_V2_OBJECT, relpath) is False
    assert compat.downgrade_suspected(old, compat.SHAPE_UNREADABLE, relpath) is False
