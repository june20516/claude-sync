"""sync-metadata.json 표식 생성과 semver 불변식.

실제 ~/.claude는 건드리지 않는다 — claude_dir을 tmp_path로 주입한다.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import pytest  # noqa: E402


import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import plugin_config as pc  # noqa: E402
import generate_metadata as gm  # noqa: E402
import sync_state as ss  # noqa: E402


def fake_tree(tmp_path, name="claude"):
    """agents/skills/CLAUDE.md를 가진 트리. 레포 작업 트리 역할(spec 3.3) — `~/.claude`가 아니다."""
    d = tmp_path / name
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
        fake_tree(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert meta["written_by_version"] == "3.0.0"
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION
    assert meta["schema"] == {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION,
                              pc.BACKUP_RELPATH: pc.SCHEMA_VERSION}
    assert len(meta["files"]) == 3


def test_min_reader_is_constant_not_plugin_version(tmp_path):
    """같은 major 안의 상승이 옛 기기를 막아서는 안 된다.

    plugin.json이 3.9.9여도 min_reader_version은 3.0.0이다. 현재 버전을 그대로 쓰면
    3.0.1을 내는 순간 3.0.0 기기가 전부 막힌다.
    """
    meta = gm.build_metadata(
        fake_tree(tmp_path), write_plugin_json(tmp_path, {"version": "3.9.9"})
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
        fake_tree(tmp_path), write_plugin_json(tmp_path, missing=True)
    )
    assert "written_by_version" not in meta
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION


def test_schema_map_carries_both_backup_documents(tmp_path):
    """`plugins.json`이 이 맵에 올랐다 — `version-compat` spec 5.3의 약속이 발동했다.

    앞 판은 *"아직 오르지 않는다"*를 잠가 두었고 그 근거는 **레포 쓰기를 레거시
    스크립트가 하고 있다**는 것이었다. 그 근거는 사라졌다 — `sync-backup/SKILL.md`가
    `collect_plugins.py`를 부르고 그것이 `pc.dump_backup`으로 `version: 2`를 기록한다.

    **두 상수를 각 모듈에서 뽑는다.** 리터럴 `"plugins.json": 2`를 적으면 상수가 바뀌어도
    이 단정이 초록이고, 그때 표식은 실제와 다른 버전을 말하게 된다.
    """
    meta = gm.build_metadata(
        fake_tree(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert meta["schema"][pc.BACKUP_RELPATH] == pc.SCHEMA_VERSION


def test_schema_map_covers_exactly_the_two_backup_documents(tmp_path):
    """**완전성 단정.** 맵의 키 집합이 백업 문서 둘과 정확히 같다.

    없으면 셋째 문서가 생겼을 때 조용히 빠진다 — 그 문서만 스키마 요약에서 사라지고
    아무 테스트도 실패하지 않는다(공허해지는 형태 ③). 기대 집합을 손으로 적지 않고
    두 모듈에서 뽑는 것은 `test_compat.py`의 같은 자리와 **같은 규율**이다.
    """
    meta = gm.build_metadata(
        fake_tree(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert set(meta["schema"]) == {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}


# ── 7단계의 표식 예시 JSON은 실제 산출물과 어긋나면 안 된다 ──────────────────
#
# **변조 실측**: 예시에서 `plugins.json` 행을 지워도 스위트 전체가 초록이었다(plan ③
# Task 4의 S6). 이 예시는 사용자가 백업 레포에서 볼 파일의 모양을 말하는 자리이므로,
# 어긋나면 *"내 표식에는 왜 이 키가 있지"* 를 묻게 만든다. 예시를 실제 출력에 묶는다.

METADATA_EXAMPLE = re.compile(r"생성되는 파일 예시:\n\n```json\n(.*?)```", re.S)


def metadata_example():
    m = METADATA_EXAMPLE.search(read_skill("sync-backup"))
    assert m, "sync-backup SKILL.md에서 표식 예시 JSON을 찾지 못했다 — 앵커가 낡았다"
    return json.loads(m.group(1))


def test_the_metadata_example_matches_what_the_script_writes(tmp_path):
    """예시의 **필드 집합과 상수 값**이 실제 산출물과 같아야 한다.

    `files`의 값(해시)은 예시라 다르지만 **키 집합은 같아야 한다** — 필드가 늘거나
    줄면 예시가 낡는다. `schema`·`min_reader_version`은 상수에서 뽑아 대조한다.
    """
    real = gm.build_metadata(
        fake_tree(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"}))
    example = metadata_example()
    assert set(example) == set(real), (sorted(example), sorted(real))
    assert example["schema"] == real["schema"]
    assert example["min_reader_version"] == compat.MIN_READER_VERSION


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


def test_write_metadata_leaves_the_old_marker_intact_when_the_write_fails(tmp_path):
    """버전 게이트의 **유일한 입력**을 잘린 채로 남기지 않는다.

    7단계는 이 파일을 레포 작업 트리에 직접 쓰고 10단계의 `git add -A`가 그것을
    커밋·푸시한다. 선-truncate 쓰기가 남긴 잘린 JSON이 푸시되면 모든 기기에서
    `load_metadata`가 None이 되고 `_block_reason`이 `raw_min is None`으로 차단을
    포기한다 — 정상 백업이 덮을 때까지 **전 기기에서** `min_reader_version` 게이트가
    조용히 꺼진다. 이 PR의 다른 writer 셋과 같은 원자적 쓰기를 여기에도 건다.
    """
    out = str(tmp_path / compat.METADATA_RELPATH)
    gm.write_metadata(out, {"files": {}})
    with open(out, "rb") as f:
        good = f.read()

    with pytest.raises(TypeError):
        gm.write_metadata(out, {"files": object()})

    with open(out, "rb") as f:
        assert f.read() == good
    assert json.loads(good)  # 잘리지 않은 문서로 남았다
    assert [n for n in os.listdir(tmp_path) if n.endswith(".tmp")] == []


def test_write_metadata_routes_through_the_atomic_writer(tmp_path, monkeypatch):
    """위 테스트는 직렬화가 메모리에서 끝난다는 것까지만 잰다 — ENOSPC/SIGKILL 갈래는
    tmp + `os.replace`가 막는다. 그 경로를 여기서 직접 고정한다(형제 writer 셋과 같은
    규율). 원자적 블록을 이 파일에 복사해 오는 편집도 여기서 걸린다.
    """
    calls = []
    monkeypatch.setattr(gm.ks, "dump_json", lambda payload, path: calls.append((payload, path)))
    out = str(tmp_path / compat.METADATA_RELPATH)
    gm.write_metadata(out, {"files": {}})
    assert calls == [({"files": {}}, out)]


def test_metadata_is_byte_stable_across_runs(tmp_path):
    """표식 파일이 소음이 되면 안 된다 — 같은 입력이면 같은 바이트여야 한다."""
    claude_dir = fake_tree(tmp_path)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    out1, out2 = str(tmp_path / "m1.json"), str(tmp_path / "m2.json")
    gm.write_metadata(out1, gm.build_metadata(claude_dir, plugin_json))
    gm.write_metadata(out2, gm.build_metadata(claude_dir, plugin_json))
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read()


def test_metadata_bytes_are_independent_of_key_order(tmp_path):
    """sort_keys가 없으면 여기서 죽는다 — 같은 런의 두 호출로는 os.walk 순서 차이를 못 만든다."""
    claude_dir = fake_tree(tmp_path)
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
    d = fake_tree(tmp_path)
    os.symlink(os.path.join(d, "nowhere.md"), os.path.join(d, "agents", "dangling.md"))
    meta = gm.build_metadata(d, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert "agents/dangling.md" not in meta["files"]
    assert "agents/a.md" in meta["files"]
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION



# --- 표식은 레포 작업 트리를 걷는다 (spec 3.3) ---
#
# 앞 판은 `~/.claude`를 걸어 **이 기기의 로컬**을 적었다. 그래서 표식이 레포에 없는 내용
# (reject 파일의 로컬 해시)을 레포 것이라 말하고, 다른 기기가 올린 파일은 통째로 빠뜨렸다
# (실측 — 2026-09-01). 7단계 시점의 레포 트리가 정의상 "이 백업이 담는 내용"이다 — 4단계가
# push 복사와 `.syncignore` 삭제를 마쳤으므로 제외 파일은 트리에 없고 표식에도 없다.
# 제외의 근거가 필터에서 **구조**로 옮겨 갔다.

def test_files_map_is_exactly_the_synced_files_of_the_tree(tmp_path):
    """양방향 완전성 — reject 해시·타 기기 파일 누락·제외 파일 유출 셋을 한 단정으로 덮는다.

    ⊆만 걸면 파일을 하나씩 잃어도 초록이고, ⊇만 걸면 트리 밖의 것을 실어도 초록이다.
    걷는 집합의 정의는 sync_state.iter_synced_relpaths 하나다 — 세 소비자와 같다.
    """
    tree = fake_tree(tmp_path)
    meta = gm.build_metadata(tree, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert set(meta["files"]) == set(ss.iter_synced_relpaths(tree))
    for rel, digest in meta["files"].items():
        assert digest == gm.file_sha256(os.path.join(tree, rel)), rel


def test_files_map_records_the_tree_not_some_other_directory(tmp_path):
    """트리 인자가 실제로 쓰인다 — 같은 relpath에 다른 내용을 가진 둘째 트리가 아니다.

    ④의 실측 형태 그대로다(레포의 code-reviewer.md ≠ 로컬의 code-reviewer.md).
    """
    repo = fake_tree(tmp_path, name="repo")
    local = fake_tree(tmp_path, name="local")
    with open(os.path.join(local, "agents", "a.md"), "w", encoding="utf-8") as f:
        f.write("로컬이 앞선 판본")
    meta = gm.build_metadata(repo, write_plugin_json(tmp_path, {"version": "3.0.0"}))
    assert meta["files"]["agents/a.md"] == gm.file_sha256(os.path.join(repo, "agents", "a.md"))
    assert meta["files"]["agents/a.md"] != gm.file_sha256(os.path.join(local, "agents", "a.md"))


def test_the_tree_root_is_required(tmp_path):
    """기본값을 두면 갱신되지 않은 호출자가 조용히 옛 동작(로컬을 적는다)으로 돌아간다."""
    with pytest.raises(TypeError):
        gm.build_metadata(write_plugin_json(tmp_path, {"version": "3.0.0"}))


def test_generate_metadata_does_not_read_syncignore():
    """제외의 근거는 필터가 아니라 구조다 — 4단계가 레포 트리에서 지웠다.

    다시 부르기 시작하면 여기가 빨개진다. 그때 고칠 것은 이 단정이 아니라
    lib/syncignore.py 정본의 소비자 목록과 sync-backup/SKILL.md 7단계다.
    """
    src = open(gm.__file__, encoding="utf-8").read()
    assert "import syncignore" not in src and "syncignore." not in src


def test_cli_takes_output_and_tree_and_refuses_anything_else(tmp_path):
    """SKILL.md가 넘기는 인자 모양 그대로 — 트리를 빠뜨린 호출은 exit 1로 서야 한다."""
    tree = fake_tree(tmp_path)
    out = str(tmp_path / "m.json")
    script = os.path.abspath(gm.__file__)
    proc = subprocess.run([sys.executable, script, out, tree], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    with open(out, encoding="utf-8") as f:
        assert set(json.load(f)["files"]) == set(ss.iter_synced_relpaths(tree))
    proc = subprocess.run([sys.executable, script, out], capture_output=True, text=True)
    assert proc.returncode == 1 and "레포 작업 트리" in proc.stderr
