"""sync-metadata.json 표식 생성과 semver 불변식.

실제 ~/.claude는 건드리지 않는다 — claude_dir을 tmp_path로 주입한다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import pytest  # noqa: E402

from marks import requires_permission_bits  # noqa: E402

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
    """plugins.json은 아직 schema 맵에 오르지 않는다. 없는 사실을 쓰지 않는다.

    **plugins.json 자체에는 version 필드가 생겼다** — plugin_config.SCHEMA_VERSION = 2를
    dump_backup이 기록한다. 이 맵이 여전히 비어 있는 이유는 레포 쓰기를 아직 레거시
    스크립트가 하고 있어서이지, 그 필드가 없어서가 아니다.
    스킬이 새 어댑터 기반 스크립트를 부르게 된 뒤 **별도 작업에서** 이 맵에 추가한다.
    그때까지는 단정을 뒤집지 않는다 — 지금 추가하면 실제로 쓰이지 않는 사실을 쓰게 된다.
    """
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert "plugins.json" not in meta["schema"]


def test_default_output_name_matches_compat_constant():
    """쓰는 쪽과 읽는 쪽이 같은 파일을 봐야 한다. 리터럴이 갈리면 무증상 고장이다.

    이것만으로는 부족하다 — 실제 쓰기는 argv로 일어나고 그 값은 SKILL.md가 쓴다.
    아래 두 테스트가 그 경로를 잇는다.
    """
    src = open(gm.__file__, encoding="utf-8").read()
    assert "compat.METADATA_RELPATH" in src
    assert '"sync-metadata.json"' not in src


SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
SKILL_NAMES = ("sync-backup", "sync-status", "sync-restore")


def read_skill(name):
    with open(os.path.join(SKILLS_DIR, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def test_skill_writes_the_filename_compat_reads():
    """SKILL.md가 argv로 넘기는 파일명이 compat이 읽는 파일명과 같아야 한다.

    generate_metadata.py 안에 리터럴이 없는지만 보면 이 경로가 안 걸린다. 실제 쓰기는
    argv[1]로 일어나고 그 값은 SKILL.md의 리터럴이다. 이름이 갈리면 표식은 써지는데
    아무도 읽지 못해, 차단 장치 전체가 켜진 적 없는 채로 모든 기기가 조용히 통과한다.
    """
    m = re.search(
        r'generate_metadata\.py"\s+"\$SYNC_REPO/([^"]+)"', read_skill("sync-backup")
    )
    assert m, "sync-backup SKILL.md에서 generate_metadata.py 호출을 찾지 못했다"
    assert m.group(1) == compat.METADATA_RELPATH


def test_skills_mention_only_one_metadata_filename():
    """세 SKILL.md에 등장하는 표식 파일명이 하나여야 한다.

    호출 밖에서도 이름이 나온다 — 12단계의 `git show HEAD~1:...`가 그렇다.
    거기만 옛 이름으로 남으면 "표식을 처음 기록했습니다"가 매 백업마다 뜬다.
    """
    names = set()
    for name in SKILL_NAMES:
        names.update(re.findall(r"sync-[a-z-]*meta[a-z-]*\.json", read_skill(name)))
    assert names == {compat.METADATA_RELPATH}, names


def test_metadata_is_byte_stable_across_runs(tmp_path):
    """표식 파일이 소음이 되면 안 된다 — 같은 입력이면 같은 바이트여야 한다."""
    claude_dir = fake_claude_dir(tmp_path)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    out1, out2 = str(tmp_path / "m1.json"), str(tmp_path / "m2.json")
    gm.write_metadata(out1, gm.build_metadata(claude_dir, plugin_json))
    gm.write_metadata(out2, gm.build_metadata(claude_dir, plugin_json))
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read()


def test_metadata_bytes_are_independent_of_key_order(tmp_path):
    """sort_keys가 없으면 여기서 죽는다 — 같은 런의 두 호출로는 os.walk 순서 차이를 못 만든다."""
    claude_dir = fake_claude_dir(tmp_path)
    meta = gm.build_metadata(claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    reversed_meta = {k: meta[k] for k in reversed(list(meta))}
    reversed_meta["files"] = {k: meta["files"][k] for k in reversed(list(meta["files"]))}
    out1, out2 = str(tmp_path / "a.json"), str(tmp_path / "b.json")
    gm.write_metadata(out1, meta)
    gm.write_metadata(out2, reversed_meta)
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read()


def test_dangling_symlink_is_skipped_not_fatal(tmp_path):
    """표식 생성이 통째로 죽으면 표식 없는 백업이 푸시된다. 파일 하나가 빠지는 게 싸다."""
    d = fake_claude_dir(tmp_path)
    os.symlink(os.path.join(d, "nowhere.md"), os.path.join(d, "agents", "dangling.md"))
    meta = gm.build_metadata(d, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert "agents/dangling.md" not in meta["files"]
    assert "agents/a.md" in meta["files"]
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION


# --- `.syncignore`: 제외한 파일이 표식에 남는가 ---
#
# **표식은 레포가 아니라 `~/.claude`를 직접 걷는다.** 4단계의 `find | rm -rf`는 레포
# 작업 트리만 손대므로, 필터가 없으면 사용자가 제외한 파일의 **이름과 sha256이 푸시되는
# `sync-metadata.json`에 그대로 남는다** — README가 "민감 파일을 `.syncignore`로 걸러내고
# 백업하라"고 말하는 바로 그 자리의 조용한 fail-open이다.
# 매칭 규칙이 4단계의 `find -path`와 같은지는 test_script_root.py의
# test_python_syncignore_matches_the_skill_bash가 두 구현을 함께 돌려 잰다.

def write_syncignore(claude_dir, text):
    with open(os.path.join(claude_dir, ".syncignore"), "w", encoding="utf-8") as f:
        f.write(text)


def secret_agent(claude_dir, rel="agents/internal-secret.md"):
    """제외 대상 파일 하나를 만들고 (상대경로, 내용의 sha256)을 돌려준다."""
    path = os.path.join(claude_dir, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("사내 URL과 내부 규칙")
    return rel, gm.file_sha256(path)


def test_syncignore_keeps_the_name_and_the_hash_out_of_metadata(tmp_path):
    """이름도 해시도 남으면 안 된다.

    **키만 확인하면 부족하다** — 해시는 그 자체로 내용의 지문이라, 값만 남아도
    같은 파일을 가진 사람이 대조할 수 있다. 직렬화한 바이트 전체에서 찾는다.
    남겨 두는 대조 파일이 없으면 "전부 뺀다"로도 단정이 참이 된다.
    """
    claude_dir = fake_claude_dir(tmp_path)
    rel, digest = secret_agent(claude_dir)
    write_syncignore(claude_dir, "agents/internal-*.md\n")
    meta = gm.build_metadata(
        claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert rel not in meta["files"]
    assert digest not in json.dumps(meta), "제외한 파일의 sha256이 표식에 남았다"
    assert "agents/a.md" in meta["files"], "패턴에 없는 파일까지 뺐다"


def test_without_syncignore_the_same_file_is_recorded(tmp_path):
    """대조군 — 위 단정이 "표식이 원래 비어 있다"로 참이 되는 것을 막는다."""
    claude_dir = fake_claude_dir(tmp_path)
    rel, digest = secret_agent(claude_dir)
    meta = gm.build_metadata(
        claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert meta["files"][rel] == digest


def test_syncignore_directory_pattern_excludes_the_whole_subtree(tmp_path):
    """디렉토리 패턴은 4단계에서 `rm -rf`로 통째로 지워진다.

    파일 경로만 대조하면 `skills/demo`는 `skills/demo/SKILL.md`와 매치되지 않아,
    디렉토리를 제외한 사용자만 표식으로 새어 나간다.
    """
    claude_dir = fake_claude_dir(tmp_path)
    write_syncignore(claude_dir, "skills/demo\n")
    meta = gm.build_metadata(
        claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert "skills/demo/SKILL.md" not in meta["files"]
    assert "CLAUDE.md" in meta["files"]


def test_syncignore_of_only_comments_and_blank_lines_excludes_nothing(tmp_path):
    """주석·빈 줄을 패턴으로 읽으면 아무 관계 없는 파일이 조용히 빠진다."""
    claude_dir = fake_claude_dir(tmp_path)
    write_syncignore(claude_dir, "# agents\n\n   \n")
    meta = gm.build_metadata(
        claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert len(meta["files"]) == 3


def test_metadata_is_byte_stable_with_syncignore(tmp_path):
    """필터를 거쳐도 정렬이 유지돼야 한다 — 표식 파일이 소음이 되면 안 된다."""
    claude_dir = fake_claude_dir(tmp_path)
    secret_agent(claude_dir)
    write_syncignore(claude_dir, "agents/internal-*.md\n")
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    out1, out2 = str(tmp_path / "s1.json"), str(tmp_path / "s2.json")
    gm.write_metadata(out1, gm.build_metadata(claude_dir, plugin_json))
    gm.write_metadata(out2, gm.build_metadata(claude_dir, plugin_json))
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read()


def test_syncignore_with_a_utf8_bom_still_excludes(tmp_path):
    """BOM이 붙어도 첫 패턴이 살아야 한다 — lib/의 바이너리 읽기 계약이 여기 걸린다.

    텍스트 모드로 읽으면 BOM이 첫 패턴의 첫 글자로 남아 매치 0건이 되고, 사용자는
    걸렀다고 믿은 파일을 그대로 푸시한다. Windows 계열 편집기가 실제로 BOM을 붙인다.
    (4단계 bash의 `read -r`은 이 경우 아무것도 제외하지 못한다 — 갈리는 방향이
    "파이썬이 더 많이 제외한다"이므로 누수가 아니다. lib/syncignore.py에 적혀 있다.)
    """
    claude_dir = fake_claude_dir(tmp_path)
    rel, _ = secret_agent(claude_dir)
    with open(os.path.join(claude_dir, ".syncignore"), "wb") as f:
        f.write(b"\xef\xbb\xbfagents/internal-*.md\n")
    meta = gm.build_metadata(
        claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert rel not in meta["files"]
    assert "agents/a.md" in meta["files"]


@requires_permission_bits
def test_unreadable_syncignore_is_not_folded_into_no_patterns(tmp_path):
    """`.syncignore`를 **못 읽는 것**과 **없는 것**은 다르다.

    OSError를 삼켜 빈 목록으로 접으면 제외 목록이 통째로 사라진 채 표식이 써진다 —
    사용자는 걸렀다고 믿고 이름과 해시를 푸시한다. 조용히 새는 것보다 시끄럽게
    서는 것이 싸다. (파일 **부재**는 정상 경로이므로 위 테스트들이 그쪽을 받친다.)
    """
    claude_dir = fake_claude_dir(tmp_path)
    secret_agent(claude_dir)
    path = os.path.join(claude_dir, ".syncignore")
    write_syncignore(claude_dir, "agents/internal-*.md\n")
    os.chmod(path, 0)
    try:
        with pytest.raises(OSError):
            gm.build_metadata(
                claude_dir, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    finally:
        os.chmod(path, 0o600)


def test_the_excluded_count_is_reported(tmp_path, capsys):
    """제외를 **조용히** 하면 안 된다 — 사용자는 표식이 전수 목록이라고 믿는다.

    sync-backup/SKILL.md 7단계가 "제외된 개수는 stderr에 알린다"고 적는다. 그 문장을
    코드에 묶는 것이 이 단정이다. 제외가 0건일 때는 아무 말도 하지 않는 것까지 함께
    건다 — 매 백업마다 뜨는 줄은 소음이 되고, 소음은 읽히지 않는다.
    """
    claude_dir = fake_claude_dir(tmp_path)
    secret_agent(claude_dir)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})

    gm.build_metadata(claude_dir, plugin_json)
    assert ".syncignore" not in capsys.readouterr().err

    write_syncignore(claude_dir, "agents/internal-*.md\n")
    gm.build_metadata(claude_dir, plugin_json)
    err = capsys.readouterr().err
    assert ".syncignore" in err and "1개" in err, err
