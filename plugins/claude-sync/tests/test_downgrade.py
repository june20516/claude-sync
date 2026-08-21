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
