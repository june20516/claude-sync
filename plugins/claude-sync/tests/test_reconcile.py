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
# 매칭 규칙 한 벌은 lib/syncignore.py이고, 4단계 bash와 같은지는 test_skill_wiring.py의
# test_python_syncignore_matches_the_skill_bash가 두 구현을 함께 돌려 잰다.
#
# 제외 대상이 **레포에도 있으면** 로컬 필터로는 사라지지 않는다. 그 자리의 문구는
# `excluded_in_repo`이고, 왜 셋 중 어느 것도 아닌지는 check_status.py의 주석과
# lib/syncignore.py의 정본에 있다. 아래 넷이 그것을 고정한다 — 머리말이 push가 아닐 것,
# 대조군을 삼키지 말 것, restore 쪽 절반을 함께 적을 것, 침묵하지 말 것.

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


def section_of(out, rel):
    """`rel`이 **어느 머리말 아래** 실렸는지. 못 찾으면 None.

    파일 이름만 grep하는 검사는 그 파일이 다른 묶음으로 옮겨가도, 심지어 "backup 시
    push"라는 거짓 머리말 아래 실려도 초록이다 — 이 절이 고치려던 결함이 바로
    그것이었으므로 머리말과 짝지어 잰다.
    """
    head = None
    for line in out.splitlines():
        if line.endswith("개):"):
            head = line
        elif line.strip() == rel:
            return head
    return None


def excluded_in_repo_fixture(tmp_path):
    """제외 대상이 **레포에도 있는** 상태. 대조군 `keep.md`는 로컬에만 있다."""
    home, repo = status_fixture(tmp_path)
    (home / ".claude" / ".syncignore").write_text("agents/internal-*.md\n")
    (repo / "agents" / "internal-secret.md").write_text("다른 기기가 올린 것")
    return home, repo


def test_an_excluded_file_that_is_also_in_the_repo_is_not_called_a_push(tmp_path):
    """**레포 쪽 열거는 거르지 않는다(의도)** — 다만 "backup 시 push"로 부르지 않는다.

    셋 중 참인 문구가 없다: push는 거짓이고(4단계가 레포에서 지운다), 침묵도
    거짓이며(레포에 있으니 restore가 건드린다), "restore 시 내려옴"도 거짓이다
    (`in_sync`는 skip, `local_ahead`는 keep). 남는 참은 backup 방향 하나다.
    필터를 union 전체에 거는 회귀도, 이 파일을 push 묶음으로 되돌리는 회귀도 여기서 죽는다.
    """
    home, repo = excluded_in_repo_fixture(tmp_path)
    out = run_check_status(home, repo).stdout
    head = section_of(out, "agents/internal-secret.md")
    assert head is not None, "제외 파일이 어느 묶음에도 실리지 않았다:\n%s" % out
    assert "push" not in head, head
    assert ".syncignore" in head and "삭제" in head, head


def test_the_excluded_bucket_does_not_swallow_the_ordinary_file(tmp_path):
    """대조군 — 새 묶음이 전부를 삼키면 위 단정은 아무것도 재지 않는다.

    `keep.md`는 로컬에만 있으므로 `local_only`("backup 시 push")여야 하고, 제외
    파일과는 **다른** 머리말 아래 있어야 한다.
    """
    home, repo = excluded_in_repo_fixture(tmp_path)
    out = run_check_status(home, repo).stdout
    keep = section_of(out, "agents/keep.md")
    assert keep is not None and "push" in keep, keep
    assert keep != section_of(out, "agents/internal-secret.md")


def test_the_excluded_bucket_says_what_backup_and_restore_do(tmp_path):
    """머리말은 backup 쪽 절반만 말한다 — 나머지 절반이 함께 있어야 한다.

    restore가 `.syncignore`를 무시한다는 것을 적지 않으면 사용자는 "곧 사라지니
    신경 쓸 것 없다"로 읽는데, 지워지기 전에 복원하면 그 파일이 로컬에 적용될 수 있다.
    **대조군과 짝지어 건다** — 제외 파일이 없을 때 이 두 줄이 나오면 안 된다.
    """
    home, repo = excluded_in_repo_fixture(tmp_path)
    out = run_check_status(home, repo).stdout
    assert "다른 기기가 올려 둔 같은 경로 파일도 함께 사라진다" in out, out
    assert "restore는 `.syncignore`를 보지 않는다" in out, out

    home2, repo2 = status_fixture(tmp_path / "control")
    plain = run_check_status(home2, repo2).stdout
    assert "restore는 `.syncignore`를 보지 않는다" not in plain, plain


def test_an_excluded_file_left_in_the_repo_is_not_reported_as_all_synced(tmp_path):
    """**침묵도 거짓이다.** 로컬·레포가 같아도 다음 백업이 레포 사본을 지운다.

    새 묶음을 "in_sync 취급"으로 되돌리면 이 상태가 "모두 동기화 상태입니다"로
    보고되고, 사용자는 레포에서 파일이 사라질 것을 모른 채 백업을 돌린다.
    """
    home, repo = status_fixture(tmp_path)
    (home / ".claude" / ".syncignore").write_text("agents/internal-*.md\n")
    (repo / "agents" / "internal-secret.md").write_text("사내 URL")
    (repo / "agents" / "keep.md").write_text("공개")
    out = run_check_status(home, repo).stdout
    assert "모두 동기화 상태입니다" not in out, out
    # 대조군이 실제로 in_sync여야 위 단정이 "제외 파일 때문에" 참인 것이 된다 —
    # 대조군이 어긋나 있으면 어느 항목이 그 줄을 막았는지 알 수 없다.
    assert "동일" in section_of(out, "agents/keep.md")
