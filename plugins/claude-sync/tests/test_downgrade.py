"""다운그레이드 탐지 — 실제 git 레포 픽스처를 쓴다.

실제 ~/.claude/.sync-state는 건드리지 않는다 — base_dir을 tmp_path로 주입한다.

**판정은 백업 문서 둘 각각에 돈다**(mcp-servers.json·plugins.json). 출력은
`{"status", "reason", "files": {relpath: {…}}}`이고, 두 항목은 서로 독립이다 —
한쪽의 base나 형태가 다른 쪽을 가리면 사고가 조용히 삼켜진다(불변식 6).
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import plugin_config as pc  # noqa: E402
import detect_downgrade as dd  # noqa: E402

from marks import requires_permission_bits  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "skills", "sync-backup", "scripts", "detect_downgrade.py",
)


# 전역·시스템 git 설정을 통째로 끊는다. commit.gpgsign 하나만 끄면 core.hooksPath나
# init.templateDir로 심긴 훅에 다시 걸린다 — 다른 기기·CI에서 원인 추적이 매우 어렵다.
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        check=True, capture_output=True, env=GIT_ENV,
    )


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    return repo


def commit_file(repo, relpath, payload, message):
    """payload를 relpath로 쓰고 커밋한다. payload는 이미 직렬화된 문자열."""
    (repo / relpath).write_text(payload, encoding="utf-8")
    git(repo, "add", relpath)
    git(repo, "commit", "-q", "-m", message)


def commit_mcp(repo, payload, message):
    commit_file(repo, mc.BACKUP_RELPATH, payload, message)


def commit_plugins(repo, payload, message):
    commit_file(repo, pc.BACKUP_RELPATH, payload, message)


def v2(servers):
    return json.dumps({"version": 2, "scope": "user", "servers": servers}, indent=2)


def v1(names):
    return json.dumps([{"name": n, "command": n} for n in names], indent=2)


# 위의 v2()는 version을 달고 있어 **mcp 규칙으로도 plugins 규칙으로도 v2_object**다 —
# 그 픽스처만으로는 형태 판정에 넘긴 relpath가 틀려도 드러나지 않는다.
# 아래 둘은 두 규칙이 서로 다른 답을 내는 입력이다.

def v2_without_version(servers):
    """version 키가 없는 v2 mcp 문서.

    mcp 규칙(servers가 객체)으로는 v2_object, plugins 규칙(version 존재)으로는
    v1_object다. mcp_config._recognized_servers가 인정하는 정상 형태이기도 하다.
    """
    return json.dumps({"servers": servers}, indent=2)


def version_without_servers(version=mc.SCHEMA_VERSION):
    """servers가 없는 객체.

    mcp 규칙으로는 unknown(후보가 아니다), plugins 규칙으로는 v2_object다.
    """
    return json.dumps({"version": version}, indent=2)


# --- plugins.json 픽스처 ---
#
# 2.x의 extract_plugins.py가 쓰는 문서다. 그 스크립트는 로컬 settings.json에서
# enabledPlugins·extraKnownMarketplaces 중 **있는 키만** 담아 dump하고 version을
# 쓰지 않는다(`git show main:plugins/claude-sync/skills/sync-backup/scripts/
# extract_plugins.py`로 **사람이 대조한 실측**이다 — 그 대조를 기계가 다시 하지는 않는다.
# **손으로 지어낸 v1 모양을 쓰면 2.x가 실제로 쓰는 것과 갈려도 초록이다.**
# 기계가 무는 것은 그중 둘이다(test_two_x_fixture_is_the_shape_2x_actually_writes) —
# 키가 pc.SECTIONS의 진짜 섹션 이름인가, version 표식이 없는가. 값의 모양까지는
# 이 저장소 안에 기계로 대조할 원천이 없다(2.x 스크립트는 main에만 있다).
TWO_X_SECTIONS = {
    "enabledPlugins": {"a@m": True, "b@m": True},
    "extraKnownMarketplaces": {"m": {"source": {"source": "github", "repo": "o/r"}}},
}


def p_v1(sections=None):
    """2.x가 쓰는 plugins.json — version 표식이 없는 객체."""
    return json.dumps(TWO_X_SECTIONS if sections is None else sections, indent=2)


def p_v2(sections=None, version=pc.SCHEMA_VERSION):
    """3.x가 쓰는 plugins.json — version 표식이 있다."""
    doc = {"version": version, "scope": "user"}
    doc.update(TWO_X_SECTIONS if sections is None else sections)
    return json.dumps(doc, indent=2)


def base_dir_with(tmp_path, mcp=None, plugins=None):
    """base 블롭 디렉토리. payload가 None인 문서는 이력이 없다.

    **문서마다 따로 쓴다.** 한 파일만 두고 두 판정에 돌려 쓰면 없는 쪽의 base 부재가
    있는 쪽의 base로 가려진다 — test_base_is_read_per_file이 그 방향을 건다.
    """
    d = tmp_path / "base"
    d.mkdir(exist_ok=True)
    for relpath, payload in ((mc.BACKUP_RELPATH, mcp), (pc.BACKUP_RELPATH, plugins)):
        if payload is not None:
            (d / relpath).write_text(payload, encoding="utf-8")
    return str(d)


def mcp_of(out):
    """출력 맵의 mcp-servers.json 항목. 키가 없으면 KeyError로 죽는다 —
    맵에서 항목이 빠지는 것을 단정이 조용히 통과시키면 안 된다."""
    return out["files"][mc.BACKUP_RELPATH]


def plugins_of(out):
    return out["files"][pc.BACKUP_RELPATH]


# --- 출력 맵 자체의 완전성 ---

def test_relpaths_are_exactly_the_two_backup_documents():
    """판정 대상 목록이 조용히 줄면 그 문서의 사고가 영영 탐지되지 않는다.

    리터럴을 적지 않고 두 어댑터 모듈에서 뽑는다 — 적으면 BACKUP_RELPATH가 바뀌어도
    이 단정은 초록이고, 그때 탐지는 실제로 쓰이지 않는 relpath만 본다.
    """
    assert set(dd.RELPATHS) == {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}
    assert set(dd._ADAPTERS) == set(dd.RELPATHS)


def test_files_map_has_an_entry_for_every_backup_document(tmp_path):
    """맵에서 문서 하나가 빠지면 그 문서에 대한 아래 단정들이 통째로 사라진다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path))
    assert set(out["files"]) == {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}


def test_two_x_fixture_is_the_shape_2x_actually_writes():
    """픽스처가 2.x의 출력에서 벗어나면 아래 회귀가 전부 헛돈다.

    **바늘은 pc.SECTIONS이지 extract_plugins.py가 아니다.** 그 스크립트는 main에만 있어
    기계로 대조할 원천이 이 트리 안에 없다 — 값의 모양은 사람이 대조한 실측이고(위 주석),
    여기서 기계가 무는 것은 다음 둘이다.

    - 키는 pc.SECTIONS의 실재하는 섹션 이름이어야 한다(오타면 아무 문서나 재게 된다)
    - version 표식이 없어야 한다 — 있으면 v2_object가 되어 사고가 탐지되지 않는다
    """
    assert set(TWO_X_SECTIONS) < set(pc.SECTIONS)
    assert "version" not in TWO_X_SECTIONS
    assert compat.shape_of(p_v1(), pc.BACKUP_RELPATH) == compat.SHAPE_V1_OBJECT
    assert compat.shape_of(p_v2(), pc.BACKUP_RELPATH) == compat.SHAPE_V2_OBJECT


# --- mcp-servers.json ---

def test_detects_downgrade_and_finds_last_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}, "b": {"command": "b"}}), "backup: v2")
    commit_mcp(repo, v1(["a"]), "backup: 옛 기기가 덮어씀")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    assert out["status"] == "ok"
    entry = mcp_of(out)
    assert entry["status"] == "ok"
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"]["subject"] == "backup: v2"
    # 후보 요약은 relpath 중립이다. 버킷 이름은 어댑터가 정한다.
    (section,) = mc.SECTIONS
    assert entry["candidate"]["entries"] == {section: ["a", "b"]}
    assert len(entry["candidate"]["sha"]) == 40


def test_no_detection_when_base_is_v1(tmp_path):
    """정말 오래된 레포다. 사고가 아니다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v1(["a"])))
    assert mcp_of(out)["downgrade_suspected"] is False
    assert mcp_of(out)["candidate"] is None


def test_no_detection_when_base_absent(tmp_path):
    """신뢰할 수 없는 이력은 근거가 될 수 없다 (불변식 2)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path))
    assert mcp_of(out)["downgrade_suspected"] is False


def test_no_detection_when_repo_is_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    assert mcp_of(out)["downgrade_suspected"] is False


def test_candidate_null_when_history_has_no_v2(tmp_path):
    """사고는 알리되 복구는 제안하지 않는다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup 1")
    commit_mcp(repo, v1(["a", "b"]), "backup 2")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    assert mcp_of(out)["downgrade_suspected"] is True
    assert mcp_of(out)["candidate"] is None
    # 후보가 없는 것과 알아보지 못해 건너뛴 것은 다른 말이다.
    assert mcp_of(out)["newer_schema_seen"] is False


def test_skips_commits_where_file_absent(tmp_path):
    """파일이 없던 커밋에서 git show가 실패해도 탐색이 멈추면 안 된다."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("x", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "initial")
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: v2")
    git(repo, "rm", "-q", mc.BACKUP_RELPATH)
    git(repo, "commit", "-q", "-m", "삭제")
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    assert mcp_of(out)["candidate"]["subject"] == "backup: v2"


@requires_permission_bits
def test_unreadable_repo_file_is_not_absent(tmp_path):
    """못 읽음을 absent로 접으면 탐지가 조용히 꺼진다(불변식 6)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    (repo / mc.BACKUP_RELPATH).chmod(0)
    try:
        out = dd.detect(str(repo),
                        base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    finally:
        (repo / mc.BACKUP_RELPATH).chmod(0o644)
    assert mcp_of(out)["repo_shape"] == compat.SHAPE_UNREADABLE
    assert mcp_of(out)["downgrade_suspected"] is False


@requires_permission_bits
def test_unreadable_base_blob_is_not_absent(tmp_path):
    """**base 쪽도** 못 읽음을 absent로 접지 않는다(불변식 6).

    불리언 판정은 어느 쪽이든 False라 바뀌지 않는다. **바뀌는 것은 사용자에게 그대로
    출력되는 base_shape다** — "base가 없다"로 보고하면 사용자는 *"이 기기는 아직 base가
    없으니 탐지할 게 없구나"* 로 읽는데, 실제로는 **확인하지 못한** 것이다. 다운그레이드
    대화의 존재 이유가 정확히 그 둘을 가르는 것이므로 이 값이 거짓이면 대화가 거짓이 된다.

    레포 파일 쪽 짝은 test_unreadable_repo_file_is_not_absent다. 한쪽만 물려 있으면
    대칭인 두 자리 중 하나가 조용히 뚫린다.
    """
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    base_dir = base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}}), plugins=p_v2())
    blob = os.path.join(base_dir, mc.BACKUP_RELPATH)
    os.chmod(blob, 0)
    try:
        out = dd.detect(str(repo), base_dir=base_dir)
    finally:
        os.chmod(blob, 0o644)
    assert mcp_of(out)["base_shape"] == compat.SHAPE_UNREADABLE
    assert mcp_of(out)["downgrade_suspected"] is False
    # base는 문서마다 따로 읽으므로 다른 문서의 base는 영향을 받지 않는다.
    assert plugins_of(out)["base_shape"] == compat.SHAPE_V2_OBJECT


def test_base_without_version_key_is_still_v2(tmp_path):
    """base 블롭의 형태는 **mcp 규칙**으로 판정해야 한다 (_base_shape에 넘기는 relpath).

    version 키가 없는 v2 문서를 plugins 규칙으로 읽으면 v1_object가 되어 base가
    "옛 형식"으로 보이고, base가 v2였다는 전제가 깨져 **실제 다운그레이드 사고가
    조용히 '사고 없음'이 된다**(불변식 6).

    후보 탐색(find_last_v2_commit)에 넘기는 relpath도 같은 커밋으로 문다 —
    plugins 규칙이면 그 커밋이 v1_object라 건너뛰어져 후보가 사라진다.
    """
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2_without_version({"a": {"command": "a"}, "b": {"command": "b"}}),
               "backup: version 없는 v2")
    commit_mcp(repo, v1(["a"]), "backup: 옛 기기가 덮어씀")
    out = dd.detect(
        str(repo),
        base_dir=base_dir_with(tmp_path, mcp=v2_without_version({"a": {"command": "a"}})),
    )
    entry = mcp_of(out)
    assert entry["base_shape"] == compat.SHAPE_V2_OBJECT
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"]["subject"] == "backup: version 없는 v2"
    (section,) = mc.SECTIONS
    assert entry["candidate"]["entries"][section] == ["a", "b"]


def test_servers_less_object_in_history_is_not_a_candidate(tmp_path):
    """히스토리 판정도 **mcp 규칙**이어야 한다 (find_last_v2_commit에 넘기는 relpath).

    servers가 없는 객체는 mcp 규칙으로 unknown이라 애초에 후보가 아니다. plugins
    규칙(version 존재 = v2)으로 읽으면 v2로 보이고, parse_base가 None을 내어
    **"알아보지 못하는 문서를 건너뛰었다"는 사실이 아닌 보고**가 사용자에게 나간다.
    """
    repo = make_repo(tmp_path)
    commit_mcp(repo, version_without_servers(), "backup: servers 없는 객체")
    commit_mcp(repo, v1(["a"]), "backup: 옛 기기가 덮어씀")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    entry = mcp_of(out)
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"] is None
    # **이 줄이 판별한다.** candidate는 두 규칙 모두에서 None이지만, plugins 규칙이면
    # 그 커밋이 v2로 보여 parse_base가 None을 내고 newer_schema_seen이 참이 된다.
    assert entry["newer_schema_seen"] is False


def test_shapes_are_always_reported(tmp_path):
    """탐지하지 못한 이유가 호출부에 드러나야 한다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path))
    assert mcp_of(out)["repo_shape"] == compat.SHAPE_V1_ARRAY
    assert mcp_of(out)["base_shape"] == compat.SHAPE_ABSENT
    assert mcp_of(out)["downgrade_suspected"] is False


def test_newer_schema_backup_is_not_reported_as_zero_servers(tmp_path):
    """상위 버전 문서를 '서버 0개인 정상 백업'으로 제시하면 안 된다(불변식 6)."""
    repo = make_repo(tmp_path)
    v3 = json.dumps({"version": 3, "scope": "user",
                     "servers": {"a": {"command": "a"}, "b": {"command": "b"}}}, indent=2)
    commit_mcp(repo, v3, "backup: v3 기기가 씀")
    commit_mcp(repo, v1(["a"]), "backup: 2.x가 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    entry = mcp_of(out)
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"] is None          # 0개짜리 가짜 후보를 만들지 않는다
    assert entry["newer_schema_seen"] is True  # 건너뛴 사실이 드러난다


def test_newer_schema_does_not_hide_older_valid_candidate(tmp_path):
    """상위 버전 문서를 건너뛰되 그 아래의 진짜 v2 후보는 찾아야 한다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}, "b": {"command": "b"}}), "backup: 진짜 v2")
    v3 = json.dumps({"version": 3, "scope": "user", "servers": {"a": {"command": "a"}}},
                    indent=2)
    commit_mcp(repo, v3, "backup: v3")
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    entry = mcp_of(out)
    assert entry["candidate"]["subject"] == "backup: 진짜 v2"
    (section,) = mc.SECTIONS
    assert entry["candidate"]["entries"][section] == ["a", "b"]
    assert entry["newer_schema_seen"] is True


def test_normal_path_reports_newer_schema_false(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: v2")
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    assert mcp_of(out)["newer_schema_seen"] is False
    assert mcp_of(out)["candidate"]["subject"] == "backup: v2"


# --- plugins.json (spec 11.4 · 11.6) ---

def test_plugins_downgrade_is_detected_with_v2_candidate(tmp_path):
    """레포가 2.x 형식이고 base가 v2면 승격이 아니라 다운그레이드 사고다(spec 11.4).

    2.x의 extract_plugins.py가 만든 문서는 **정당한 v1 문서와 형태상 완전히 같다.**
    그것을 가르는 유일한 근거가 "이 기기의 base에는 version이 있었다"이다.
    """
    repo = make_repo(tmp_path)
    commit_plugins(repo, p_v2(), "backup: v2")
    commit_plugins(repo, p_v1(), "backup: 2.x가 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, plugins=p_v2()))
    entry = plugins_of(out)
    assert entry["repo_shape"] == compat.SHAPE_V1_OBJECT
    assert entry["base_shape"] == compat.SHAPE_V2_OBJECT
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"]["subject"] == "backup: v2"
    # 버킷 이름은 어댑터가 낸다 — 손으로 적지 않는다. 부재 섹션도 {}로 채워지므로
    # 키 집합은 항상 세 섹션 전부다.
    assert set(entry["candidate"]["entries"]) == set(pc.SECTIONS)
    assert entry["candidate"]["entries"]["enabledPlugins"] == ["a@m", "b@m"]
    assert entry["candidate"]["entries"]["extraKnownMarketplaces"] == ["m"]


def test_plugins_candidate_never_points_at_a_v1_commit(tmp_path):
    """**v2 판정은 shape_of이지 parse_base가 아니다.**

    plugin_config의 인식 조건은 *"version이 없거나 SCHEMA_VERSION 이하"* 이므로
    **2.x가 쓴 v1 문서도 parse_base가 그대로 인식한다**(실측: 세 섹션 매핑을 돌려준다).
    v2 판정을 `parse_base(blob) is not None`으로 두면 히스토리에서 **가장 최근의 v1 커밋**이
    "마지막 정상 판본"으로 제시되고, 대화가 그 sha로 되돌리라고 안내한다 — 탐지가 사고를
    복구하는 대신 **고착시킨다.**

    그래서 v1 커밋이 v2 커밋보다 **나중**에 있는 히스토리를 세운다. 후보는 v1을 가리키면
    안 되고, v1 문서는 애초에 후보 자격이 없으므로 건너뛴 것으로 세지도 않는다.
    """
    repo = make_repo(tmp_path)
    commit_plugins(repo, p_v2(), "backup: v2")
    commit_plugins(repo, p_v1({"enabledPlugins": {"a@m": True}}), "backup: 2.x 1회차")
    commit_plugins(repo, p_v1(), "backup: 2.x 2회차")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, plugins=p_v2()))
    entry = plugins_of(out)
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"]["subject"] == "backup: v2"
    assert entry["newer_schema_seen"] is False


def test_plugins_no_detection_when_repo_is_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_plugins(repo, p_v2(), "backup: v2")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, plugins=p_v2()))
    assert plugins_of(out)["downgrade_suspected"] is False
    assert plugins_of(out)["candidate"] is None


def test_plugins_absent_in_repo_is_not_an_accident(tmp_path):
    """레포에 문서가 아직 없는 것은 사고가 아니라 첫 백업 전이다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, plugins=p_v2()))
    entry = plugins_of(out)
    assert entry["repo_shape"] == compat.SHAPE_ABSENT
    assert entry["downgrade_suspected"] is False


def test_plugins_v1_promotion_without_base_is_not_a_downgrade(tmp_path):
    """반대 방향 — **정당한 v1 승격**은 사고가 아니고 백업이 정상 진행해야 한다.

    이 행이 없으면 판정이 승격 경로 전체를 막아 세워도(항상 true) 초록이다.
    base가 없다는 것은 이 기기가 v2를 본 적이 없다는 뜻이고, 그때 v1 레포는
    그냥 아직 승격되지 않은 레포다(불변식 2).
    """
    repo = make_repo(tmp_path)
    commit_plugins(repo, p_v1(), "backup: 2.x가 쓴 레포")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path))
    entry = plugins_of(out)
    assert entry["repo_shape"] == compat.SHAPE_V1_OBJECT
    assert entry["base_shape"] == compat.SHAPE_ABSENT
    assert entry["downgrade_suspected"] is False
    assert entry["status"] == "ok"
    assert entry["candidate"] is None


def test_plugins_newer_schema_is_not_reported_as_zero_entries(tmp_path):
    """상위 스키마 문서를 '항목 0개인 정상 백업'으로 제시하면 안 된다(불변식 6)."""
    repo = make_repo(tmp_path)
    commit_plugins(repo, p_v2(version=pc.SCHEMA_VERSION + 1), "backup: 상위 버전 기기가 씀")
    commit_plugins(repo, p_v1(), "backup: 2.x가 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, plugins=p_v2()))
    entry = plugins_of(out)
    assert entry["downgrade_suspected"] is True
    assert entry["candidate"] is None
    assert entry["newer_schema_seen"] is True


# --- 두 문서의 독립성 ---

def test_the_two_files_are_judged_independently(tmp_path):
    """한 문서의 판정이 다른 문서를 가리면 사고가 조용히 삼켜진다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: mcp v2")
    commit_plugins(repo, p_v2(), "backup: plugins v2")
    commit_plugins(repo, p_v1(), "backup: 2.x가 plugins만 되돌림")
    out = dd.detect(
        str(repo),
        base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}}), plugins=p_v2()),
    )
    assert mcp_of(out)["downgrade_suspected"] is False
    assert mcp_of(out)["repo_shape"] == compat.SHAPE_V2_OBJECT
    assert plugins_of(out)["downgrade_suspected"] is True
    assert plugins_of(out)["repo_shape"] == compat.SHAPE_V1_OBJECT
    assert plugins_of(out)["candidate"]["subject"] == "backup: plugins v2"


@pytest.mark.parametrize(
    "which,other", [("mcp", "plugins"), ("plugins", "mcp")]
)
def test_base_is_read_per_file(tmp_path, which, other):
    """base를 한 번 읽어 두 판정에 돌려 쓰면 없는 쪽의 base 부재가 가려진다.

    두 방향을 다 건다 — 어느 쪽 base를 공유하도록 접든 한쪽은 잡힌다.
    레포는 두 문서가 모두 옛 형식이고, base는 **한 문서에만** 있다.
    """
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup: mcp v1")
    commit_plugins(repo, p_v1(), "backup: plugins v1")
    payloads = {"mcp": v2({"a": {"command": "a"}}), "plugins": p_v2()}
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, **{which: payloads[which]}))
    entries = {"mcp": mcp_of(out), "plugins": plugins_of(out)}
    assert entries[which]["base_shape"] == compat.SHAPE_V2_OBJECT
    assert entries[which]["downgrade_suspected"] is True
    assert entries[other]["base_shape"] == compat.SHAPE_ABSENT
    assert entries[other]["downgrade_suspected"] is False


# --- 실패 경로 ---

def test_not_a_git_repo_is_skipped_globally(tmp_path):
    """탐지 실패가 백업을 막지 않는다. **전역 skipped여도 files는 채워서 낸다.**

    비우면 그 맵을 도는 SKILL.md의 루프가 0회 돌아 아무것도 보고되지 않고,
    "확인하지 못했다"가 "사고가 없다"로 조용히 읽힌다(불변식 6).
    형태 판정은 git 없이도 되므로 그 결과는 여전히 실려야 한다.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / mc.BACKUP_RELPATH).write_text(v1(["a"]), encoding="utf-8")
    (plain / pc.BACKUP_RELPATH).write_text(p_v1(), encoding="utf-8")
    out = dd.detect(str(plain),
                    base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}}),
                                           plugins=p_v2()))
    assert out["status"] == "skipped"
    assert out["reason"]
    assert set(out["files"]) == {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}
    assert mcp_of(out)["repo_shape"] == compat.SHAPE_V1_ARRAY
    assert plugins_of(out)["repo_shape"] == compat.SHAPE_V1_OBJECT
    # 후보 탐색은 실패했으므로 파일별로도 skipped이고 사유가 실린다.
    for entry in out["files"].values():
        assert entry["status"] == "skipped"
        assert entry["reason"]
        assert entry["downgrade_suspected"] is True


def test_global_status_is_ok_when_only_one_file_fails(tmp_path):
    """파일별 실패를 전역으로 접으면 나머지 문서의 정상 판정이 함께 묻힌다.

    레포는 git이고 mcp 쪽 후보 탐색만 손상으로 실패한다 — 전역은 ok여야 하고
    plugins 항목은 자기 판정을 그대로 낸다.
    """
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: v2")
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True,
                         env=GIT_ENV).stdout.strip()
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    commit_plugins(repo, p_v2(), "backup: plugins v2")
    corrupt_blob(repo, sha, mc.BACKUP_RELPATH)
    out = dd.detect(
        str(repo),
        base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}}), plugins=p_v2()),
    )
    assert out["status"] == "ok"
    assert out["reason"] is None
    assert mcp_of(out)["status"] == "skipped"
    assert mcp_of(out)["reason"]
    assert plugins_of(out)["status"] == "ok"
    assert plugins_of(out)["downgrade_suspected"] is False


def corrupt_blob(repo, sha, relpath):
    """커밋의 relpath blob 오브젝트를 지워 레포를 고장낸다."""
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "%s:%s" % (sha, relpath)],
        check=True, capture_output=True, text=True, env=GIT_ENV,
    ).stdout.strip()
    obj = repo / ".git" / "objects" / out[:2] / out[2:]
    obj.unlink()


def test_corrupt_repo_is_skipped_not_reported_as_no_candidate(tmp_path):
    """레포 손상을 'v2가 없음'으로 접으면 사실이 아닐 수 있는 결론이 전달된다(불변식 6)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: v2")
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True,
                         env=GIT_ENV).stdout.strip()
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    corrupt_blob(repo, sha, mc.BACKUP_RELPATH)
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, mcp=v2({"a": {"command": "a"}})))
    entry = mcp_of(out)
    assert entry["status"] == "skipped"
    assert entry["reason"]
    # 키 모양이 정상 경로와 같아야 한다 — 없으면 None(falsy)으로 '사고 없음'처럼 읽힌다
    for key in ("downgrade_suspected", "repo_shape", "base_shape", "candidate",
                "newer_schema_seen"):
        assert key in entry


def test_global_skip_still_reports_every_file(tmp_path):
    """탐지 자체가 실패한 경우(main의 마지막 방어선)도 files를 비우지 않는다."""
    out = dd._skipped_all("ValueError: 무엇인가")
    assert out["status"] == "skipped"
    assert set(out["files"]) == set(dd.RELPATHS)
    for entry in out["files"].values():
        for key in ("status", "reason", "downgrade_suspected", "repo_shape",
                    "base_shape", "candidate", "newer_schema_seen"):
            assert key in entry


def test_unknown_relpath_is_not_a_silent_no_accident():
    """모르는 relpath를 빈 결과로 접으면 '판정할 수 없었다'가 '사고 없음'이 된다."""
    with pytest.raises(ValueError):
        dd._adapter("sync-metadata.json")


def test_cli_prints_json(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    commit_plugins(repo, p_v2(), "backup")
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(repo)],
        capture_output=True, text=True,
        env=dict(GIT_ENV, HOME=str(tmp_path / "fakehome")),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert set(out["files"]) == {mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}
    for entry in out["files"].values():
        assert entry["downgrade_suspected"] is False
