"""다운그레이드 탐지 — 실제 git 레포 픽스처를 쓴다.

실제 ~/.claude/.sync-state는 건드리지 않는다 — base_dir을 tmp_path로 주입한다.
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


def commit_mcp(repo, payload, message):
    """payload를 mcp-servers.json으로 쓰고 커밋한다. payload는 이미 직렬화된 문자열."""
    (repo / mc.BACKUP_RELPATH).write_text(payload, encoding="utf-8")
    git(repo, "add", mc.BACKUP_RELPATH)
    git(repo, "commit", "-q", "-m", message)


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


def base_dir_with(tmp_path, payload):
    """base 블롭 디렉토리. payload가 None이면 이력 없음."""
    d = tmp_path / "base"
    d.mkdir(exist_ok=True)
    if payload is not None:
        (d / mc.BACKUP_RELPATH).write_text(payload, encoding="utf-8")
    return str(d)


def test_detects_downgrade_and_finds_last_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}, "b": {"command": "b"}}), "backup: v2")
    commit_mcp(repo, v1(["a"]), "backup: 옛 기기가 덮어씀")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["status"] == "ok"
    assert out["downgrade_suspected"] is True
    assert out["candidate"]["subject"] == "backup: v2"
    assert out["candidate"]["server_count"] == 2
    assert out["candidate"]["server_names"] == ["a", "b"]
    assert len(out["candidate"]["sha"]) == 40


def test_no_detection_when_base_is_v1(tmp_path):
    """정말 오래된 레포다. 사고가 아니다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v1(["a"])))
    assert out["downgrade_suspected"] is False
    assert out["candidate"] is None


def test_no_detection_when_base_absent(tmp_path):
    """신뢰할 수 없는 이력은 근거가 될 수 없다 (불변식 2)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, None))
    assert out["downgrade_suspected"] is False


def test_no_detection_when_repo_is_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["downgrade_suspected"] is False


def test_candidate_null_when_history_has_no_v2(tmp_path):
    """사고는 알리되 복구는 제안하지 않는다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup 1")
    commit_mcp(repo, v1(["a", "b"]), "backup 2")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["downgrade_suspected"] is True
    assert out["candidate"] is None


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
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["candidate"]["subject"] == "backup: v2"


@requires_permission_bits
def test_unreadable_repo_file_is_not_absent(tmp_path):
    """못 읽음을 absent로 접으면 탐지가 조용히 꺼진다(불변식 6)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    (repo / mc.BACKUP_RELPATH).chmod(0)
    try:
        out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    finally:
        (repo / mc.BACKUP_RELPATH).chmod(0o644)
    assert out["repo_shape"] == compat.SHAPE_UNREADABLE
    assert out["downgrade_suspected"] is False


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
        base_dir=base_dir_with(tmp_path, v2_without_version({"a": {"command": "a"}})),
    )
    assert out["base_shape"] == compat.SHAPE_V2_OBJECT
    assert out["downgrade_suspected"] is True
    assert out["candidate"]["subject"] == "backup: version 없는 v2"
    assert out["candidate"]["server_count"] == 2


def test_servers_less_object_in_history_is_not_a_candidate(tmp_path):
    """히스토리 판정도 **mcp 규칙**이어야 한다 (find_last_v2_commit에 넘기는 relpath).

    servers가 없는 객체는 mcp 규칙으로 unknown이라 애초에 후보가 아니다. plugins
    규칙(version 존재 = v2)으로 읽으면 v2로 보이고, parse_base가 None을 내어
    **"상위 스키마 문서를 건너뛰었다"는 사실이 아닌 보고**가 사용자에게 나간다.
    """
    repo = make_repo(tmp_path)
    commit_mcp(repo, version_without_servers(), "backup: servers 없는 객체")
    commit_mcp(repo, v1(["a"]), "backup: 옛 기기가 덮어씀")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["downgrade_suspected"] is True
    assert out["candidate"] is None
    # **이 줄이 판별한다.** candidate는 두 규칙 모두에서 None이지만, plugins 규칙이면
    # 그 커밋이 v2로 보여 parse_base가 None을 내고 newer_schema_seen이 참이 된다.
    assert out["newer_schema_seen"] is False


def test_shapes_are_always_reported(tmp_path):
    """탐지하지 못한 이유가 호출부에 드러나야 한다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, None))
    assert out["repo_shape"] == compat.SHAPE_V1_ARRAY
    assert out["base_shape"] == compat.SHAPE_ABSENT
    assert out["downgrade_suspected"] is False


def test_not_a_git_repo_is_skipped(tmp_path):
    """탐지 실패가 백업을 막지 않는다."""
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / mc.BACKUP_RELPATH).write_text(v1(["a"]), encoding="utf-8")
    out = dd.detect(str(plain), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["status"] == "skipped"
    assert "reason" in out


def test_cli_prints_json(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(repo)],
        capture_output=True, text=True,
        env=dict(GIT_ENV, HOME=str(tmp_path / "fakehome")),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["downgrade_suspected"] is False


def corrupt_blob(repo, sha):
    """커밋의 mcp-servers.json blob 오브젝트를 지워 레포를 고장낸다."""
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "%s:%s" % (sha, mc.BACKUP_RELPATH)],
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
    corrupt_blob(repo, sha)
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["status"] == "skipped"
    assert "reason" in out
    # 키 모양이 정상 경로와 같아야 한다 — 없으면 None(falsy)으로 '사고 없음'처럼 읽힌다
    for key in ("downgrade_suspected", "repo_shape", "base_shape", "candidate",
                "newer_schema_seen"):
        assert key in out


def test_newer_schema_backup_is_not_reported_as_zero_servers(tmp_path):
    """상위 버전 문서를 '서버 0개인 정상 백업'으로 제시하면 안 된다(불변식 6)."""
    repo = make_repo(tmp_path)
    v3 = json.dumps({"version": 3, "scope": "user",
                     "servers": {"a": {"command": "a"}, "b": {"command": "b"}}}, indent=2)
    commit_mcp(repo, v3, "backup: v3 기기가 씀")
    commit_mcp(repo, v1(["a"]), "backup: 2.x가 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["downgrade_suspected"] is True
    assert out["candidate"] is None          # 0개짜리 가짜 후보를 만들지 않는다
    assert out["newer_schema_seen"] is True  # 건너뛴 사실이 드러난다


def test_newer_schema_does_not_hide_older_valid_candidate(tmp_path):
    """상위 버전 문서를 건너뛰되 그 아래의 진짜 v2 후보는 찾아야 한다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}, "b": {"command": "b"}}), "backup: 진짜 v2")
    v3 = json.dumps({"version": 3, "scope": "user", "servers": {"a": {"command": "a"}}},
                    indent=2)
    commit_mcp(repo, v3, "backup: v3")
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["candidate"]["subject"] == "backup: 진짜 v2"
    assert out["candidate"]["server_count"] == 2
    assert out["newer_schema_seen"] is True


def test_normal_path_reports_newer_schema_false(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: v2")
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["newer_schema_seen"] is False
    assert out["candidate"]["subject"] == "backup: v2"
