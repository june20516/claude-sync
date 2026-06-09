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
