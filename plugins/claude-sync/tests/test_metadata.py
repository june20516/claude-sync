"""sync-metadata.json 표식 생성과 semver 불변식.

실제 ~/.claude는 건드리지 않는다 — claude_dir을 tmp_path로 주입한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import generate_metadata as gm  # noqa: E402


def fake_claude_dir(tmp_path):
    """agents/skills/CLAUDE.md를 가진 ~/.claude 역할 디렉토리."""
    d = tmp_path / "claude"
    (d / "agents").mkdir(parents=True)
    (d / "skills" / "demo").mkdir(parents=True)
    (d / "agents" / "a.md").write_text("a", encoding="utf-8")
    (d / "skills" / "demo" / "SKILL.md").write_text("s", encoding="utf-8")
    (d / "CLAUDE.md").write_text("c", encoding="utf-8")
    return str(d)


def write_plugin_json(tmp_path, obj=None, *, missing=False):
    """plugin.json 역할의 임시 파일 경로. missing=True면 파일을 만들지 않는다.

    test_compat.py의 같은 이름 헬퍼와 키워드 의미를 맞춘다 — 같은 이름이 파일마다
    다른 뜻을 가지면 호출부를 읽을 때마다 어느 쪽인지 확인해야 한다.
    """
    path = tmp_path / "plugin.json"
    if not missing:
        path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def test_metadata_has_all_three_markers(tmp_path):
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert meta["written_by_version"] == "3.0.0"
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION
    assert meta["schema"] == {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION}
    assert len(meta["files"]) == 3


def test_min_reader_is_constant_not_plugin_version(tmp_path):
    """같은 major 안의 상승이 옛 기기를 막아서는 안 된다.

    plugin.json이 3.9.9여도 min_reader_version은 3.0.0이다. 현재 버전을 그대로 쓰면
    3.0.1을 내는 순간 3.0.0 기기가 전부 막힌다.
    """
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.9.9"})
    )
    assert meta["written_by_version"] == "3.9.9"
    assert meta["min_reader_version"] == "3.0.0"


def test_min_reader_major_matches_plugin_json():
    """MIN_READER_VERSION의 major == 레포 plugin.json의 major.

    이 테스트가 이 프로젝트에서 semver를 의미 있게 만드는 유일한 장치다.
    major를 올리면서 상수를 안 건드리면 여기서 깨진다 — 조용한 실패를 시끄러운
    실패로 바꾸는 것이 존재 이유다.
    """
    plugin_version = compat.read_plugin_version(compat.default_plugin_json_path())
    assert plugin_version is not None
    assert compat.parse_version(compat.MIN_READER_VERSION)[0] == \
        compat.parse_version(plugin_version)[0]


def test_min_reader_minor_and_patch_are_zero():
    """결정 1에 따라 호환 경계는 항상 {major}.0.0이다."""
    assert compat.parse_version(compat.MIN_READER_VERSION)[1:] == (0, 0)


def test_written_by_omitted_when_plugin_json_unreadable(tmp_path):
    """자기 버전을 몰라도 min_reader는 정상 기록된다 — 상수를 쓰는 두 번째 이유."""
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, missing=True)
    )
    assert "written_by_version" not in meta
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION


def test_schema_map_omits_plugins_json(tmp_path):
    """plugins.json에는 자체 version 필드가 없다. 없는 사실을 쓰지 않는다."""
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert "plugins.json" not in meta["schema"]


def test_default_output_name_matches_compat_constant():
    """쓰는 쪽과 읽는 쪽이 같은 파일을 봐야 한다. 리터럴이 갈리면 무증상 고장이다."""
    src = open(gm.__file__, encoding="utf-8").read()
    assert "compat.METADATA_RELPATH" in src
    assert '"sync-metadata.json"' not in src


def test_metadata_is_byte_stable_across_runs(tmp_path):
    """표식 파일이 소음이 되면 안 된다 — 같은 입력이면 같은 바이트여야 한다."""
    claude_dir = fake_claude_dir(tmp_path)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    out1, out2 = str(tmp_path / "m1.json"), str(tmp_path / "m2.json")
    gm.write_metadata(out1, gm.build_metadata(claude_dir, plugin_json))
    gm.write_metadata(out2, gm.build_metadata(claude_dir, plugin_json))
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read()
