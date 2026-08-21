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


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo)] + list(args), check=True, capture_output=True
    )


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "commit.gpgsign", "false")  # 전역 서명 설정이 켜져 있으면 커밋이 실패한다
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
        env=dict(os.environ, HOME=str(tmp_path / "fakehome")),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["downgrade_suspected"] is False
