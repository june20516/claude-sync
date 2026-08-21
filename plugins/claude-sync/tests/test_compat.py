"""lib/compat.py의 버전 호환성 판정 테스트.

실제 ~/.claude는 건드리지 않는다 — 모든 경로를 tmp_path로 주입한다.
"""
import json
import os
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


def write_plugin_json(tmp_path, obj):
    """plugin.json 역할의 임시 파일. obj가 None이면 깨진 JSON을 쓴다."""
    path = tmp_path / "plugin.json"
    path.write_text("{ not json" if obj is None else json.dumps(obj), encoding="utf-8")
    return str(path)


def test_read_plugin_version_reads_version(tmp_path):
    path = write_plugin_json(tmp_path, {"name": "claude-sync", "version": "3.0.0"})
    assert compat.read_plugin_version(path) == "3.0.0"


def test_read_plugin_version_missing_file(tmp_path):
    assert compat.read_plugin_version(str(tmp_path / "nope.json")) is None


def test_read_plugin_version_broken_json(tmp_path):
    assert compat.read_plugin_version(write_plugin_json(tmp_path, None)) is None


@pytest.mark.parametrize("obj", [{}, {"version": 3}, {"version": None}, [], "x"])
def test_read_plugin_version_unusable(tmp_path, obj):
    assert compat.read_plugin_version(write_plugin_json(tmp_path, obj)) is None


def write_metadata(tmp_path, obj):
    """레포 디렉토리와 sync-metadata.json을 만든다.

    obj가 None이면 파일 없음, 'broken'이면 깨진 JSON.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    path = repo / compat.METADATA_RELPATH
    if obj == "broken":
        path.write_text("{ not json", encoding="utf-8")
    elif obj is not None:
        path.write_text(json.dumps(obj), encoding="utf-8")
    return str(repo)


def test_load_metadata_reads_dict(tmp_path):
    repo = write_metadata(tmp_path, {"min_reader_version": "3.0.0"})
    assert compat.load_metadata(os.path.join(repo, compat.METADATA_RELPATH)) == {
        "min_reader_version": "3.0.0"
    }


def test_load_metadata_missing_is_none(tmp_path):
    repo = write_metadata(tmp_path, None)
    assert compat.load_metadata(os.path.join(repo, compat.METADATA_RELPATH)) is None


def test_load_metadata_broken_is_none(tmp_path):
    """깨진 metadata를 차단 근거로 삼으면 데드락이다 — 그 파일을 고치는 것이 다음 백업이다."""
    repo = write_metadata(tmp_path, "broken")
    assert compat.load_metadata(os.path.join(repo, compat.METADATA_RELPATH)) is None


@pytest.mark.parametrize("obj", [[], "x", 3, None])
def test_load_metadata_non_dict_is_none(tmp_path, obj):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    assert compat.load_metadata(str(path)) is None


def test_default_plugin_json_path_points_at_real_plugin_json():
    """lib/../.claude-plugin/plugin.json 이 실제로 존재해야 한다."""
    assert os.path.isfile(compat.default_plugin_json_path())
    assert compat.read_plugin_version(compat.default_plugin_json_path()) is not None
