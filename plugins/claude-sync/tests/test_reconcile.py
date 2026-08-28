import sys
import os
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import reconcile_backup as rb
import update_base as ub
import sync_state as ss
import reconcile_restore as rr


def test_backup_in_sync():
    assert rb.backup_action("a", "a", "x") == "in_sync"


def test_backup_local_ahead_push():
    # L!=R, R==S → push
    assert rb.backup_action("L", "S", "S") == "push"


def test_backup_remote_ahead_reject():
    # L!=R, R!=S → remote가 앞섬 → 거부
    assert rb.backup_action("L", "R", "S") == "reject"


def test_backup_new_local_push():
    # 레포에 없음(R None) → push(추가)
    assert rb.backup_action("L", None, None) == "push"


def test_update_base_writes_local_content(tmp_path):
    """push 성공 후 base가 로컬 파일 내용으로 갱신되는지 확인."""
    source_root = str(tmp_path / "home" / ".claude")
    os.makedirs(os.path.join(source_root, "agents"), exist_ok=True)
    rel = "agents/foo.md"
    content = b"hello from local"
    with open(os.path.join(source_root, rel), "wb") as f:
        f.write(content)

    base_dir = str(tmp_path / "base")
    # update_base_for_pushed 직접 호출하되, write_base의 base_dir를 tmp로 패치
    original_write_base = ss.write_base
    written = {}

    def mock_write_base(r, data, base_dir=ss.BASE_DIR):
        written[r] = data

    ss.write_base = mock_write_base
    try:
        ub.update_base_for_pushed(source_root, [rel])
    finally:
        ss.write_base = original_write_base

    assert written[rel] == content


# ── restore tests ────────────────────────────────────────────────────────────

def test_restore_in_sync():
    assert rr.restore_action("a", "a", "x", True, True) == "skip"


def test_restore_repo_only_add():
    assert rr.restore_action(None, "r", None, False, True) == "add"


def test_restore_fast_forward():
    assert rr.restore_action("S", "R", "S", True, True) == "overwrite"


def test_restore_local_ahead_keep():
    assert rr.restore_action("L", "S", "S", True, True) == "keep"


def test_restore_conflict_needs_merge():
    assert rr.restore_action("L", "R", "S", True, True) == "merge"


def test_restore_local_only_keep():
    assert rr.restore_action("L", None, None, True, False) == "keep"


def test_restore_set_base_from(tmp_path):
    """--set-base-from 모드: source_root에서 base 블롭을 기록한다."""
    source_root = str(tmp_path / "repo")
    os.makedirs(os.path.join(source_root, "agents"), exist_ok=True)
    rel = "agents/bar.md"
    content = b"repo content for base"
    with open(os.path.join(source_root, rel), "wb") as f:
        f.write(content)

    base_dir = str(tmp_path / "base")
    # ss.write_base를 임시 base_dir로 테스트
    rr.apply_set_base_from(source_root, [rel], base_dir=base_dir)
    assert ss.read_base(rel, base_dir=base_dir) == content


def test_apply_add_creates_nested_file_and_base(tmp_path):
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    (repo / "skills" / "nested").mkdir(parents=True)
    (repo / "skills" / "nested" / "SKILL.md").write_text("hello")
    script = os.path.join(
        os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts", "reconcile_restore.py"
    )
    env = dict(os.environ, HOME=str(home))
    r = subprocess.run(
        ["python3", os.path.abspath(script), str(repo), "--apply"],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, r.stderr
    # local file created with nested dirs
    assert (home / ".claude" / "skills" / "nested" / "SKILL.md").read_text() == "hello"
    # base blob recorded under the isolated HOME
    base_blob = home / ".claude" / ".sync-state" / "base" / "skills" / "nested" / "SKILL.md"
    assert base_blob.read_bytes() == b"hello"


def test_update_base_multiple_files(tmp_path):
    """여러 파일 한 번에 base 갱신."""
    source_root = str(tmp_path / "home" / ".claude")
    os.makedirs(os.path.join(source_root, "agents"), exist_ok=True)
    rels = ["agents/a.md", "agents/b.md"]
    for i, rel in enumerate(rels):
        with open(os.path.join(source_root, rel), "wb") as f:
            f.write(f"content {i}".encode())

    base_dir = str(tmp_path / "base")
    written = {}
    original_write_base = ss.write_base

    def mock_write_base(r, data, base_dir=ss.BASE_DIR):
        written[r] = data

    ss.write_base = mock_write_base
    try:
        ub.update_base_for_pushed(source_root, rels)
    finally:
        ss.write_base = original_write_base

    assert len(written) == 2
    assert written["agents/a.md"] == b"content 0"
    assert written["agents/b.md"] == b"content 1"


# ── /sync-status의 `.syncignore` ─────────────────────────────────────────────
#
# check_status.py는 `~/.claude`를 직접 걷는다. 4단계의 `find | rm -rf`는 레포 작업
# 트리만 손대므로, 필터가 없으면 사용자가 제외한 파일이 `local_only`("backup 시 push")로
# 보고된다 — 백업은 그것을 push하지 않으므로 **보고만 어긋난다**(누수가 아니다).
# 매칭 규칙 한 벌은 lib/syncignore.py이고, 4단계 bash와 같은지는 test_script_root.py의
# test_python_syncignore_matches_the_skill_bash가 두 구현을 함께 돌려 잰다.

def run_check_status(home, repo):
    script = os.path.join(
        os.path.dirname(__file__), "..", "skills", "sync-status", "scripts",
        "check_status.py")
    return subprocess.run(
        ["python3", os.path.abspath(script), str(repo)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))


def status_fixture(tmp_path):
    """제외 대상 하나와 대조군 하나를 가진 HOME·레포. `.syncignore`는 아직 없다."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    (home / ".claude" / "agents").mkdir(parents=True)
    (repo / "agents").mkdir(parents=True)
    (home / ".claude" / "agents" / "internal-secret.md").write_text("사내 URL")
    (home / ".claude" / "agents" / "keep.md").write_text("공개")
    return home, repo


def test_syncignore_keeps_an_excluded_local_file_out_of_the_status_report(tmp_path):
    """제외한 파일을 "backup 시 push"로 보고하지 않는다.

    **대조 파일 하나를 함께 둔다** — 없으면 "아무것도 보고하지 않는다"로도 단정이
    참이 되고, 필터가 전부를 지우는 회귀가 조용히 지나간다.
    """
    home, repo = status_fixture(tmp_path)
    (home / ".claude" / ".syncignore").write_text("agents/internal-*.md\n")
    out = run_check_status(home, repo).stdout
    assert "agents/internal-secret.md" not in out
    assert "agents/keep.md" in out


def test_without_syncignore_the_same_file_is_reported(tmp_path):
    """대조군 — 위 단정이 "그 파일이 원래 안 나온다"로 참이 되는 것을 막는다."""
    home, repo = status_fixture(tmp_path)
    out = run_check_status(home, repo).stdout
    assert "agents/internal-secret.md" in out
    assert "agents/keep.md" in out


def test_an_excluded_file_that_is_also_in_the_repo_is_still_reported(tmp_path):
    """**레포 쪽 열거는 거르지 않는다(의도).**

    reconcile_restore.py는 `.syncignore`를 보지 않으므로 레포에 있는 항목은 제외
    대상이라도 restore가 실제로 건드린다. 여기서 함께 걸러 버리면 이 보고가 restore와
    어긋난다 — 그 비대칭이 의도라는 것을 이 테스트가 고정한다. 필터를 union 전체에
    거는 회귀는 여기서 죽는다.
    """
    home, repo = status_fixture(tmp_path)
    (home / ".claude" / ".syncignore").write_text("agents/internal-*.md\n")
    (repo / "agents" / "internal-secret.md").write_text("사내 URL")
    out = run_check_status(home, repo).stdout
    assert "agents/internal-secret.md" in out
