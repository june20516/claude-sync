import ast
import json
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


def test_backup_reject_bucket_is_decided_by_base_presence_alone():
    """spec 3.1 — backup_action의 세 반환값은 그대로고, reject의 갈래는 S 하나가 정한다.

    S 없음·R 있음·L≠R은 여전히 reject다(push하지 않는다). 다른 것은 **사용자에게 할
    말**이고, 그것을 정하는 사실은 기준선의 유무 하나다.
    """
    assert rb.backup_action("L", "R", None) == "reject"
    assert rb.reject_bucket(None) == "no_base"
    assert rb.reject_bucket("S") == "remote_ahead"


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
    assert ss.restore_action("a", "a", "x", True, True) == "skip"


def test_restore_repo_only_add():
    assert ss.restore_action(None, "r", None, False, True) == "add"


def test_restore_fast_forward():
    assert ss.restore_action("S", "R", "S", True, True) == "overwrite"


def test_restore_local_ahead_keep():
    assert ss.restore_action("L", "S", "S", True, True) == "keep"


def test_restore_conflict_needs_merge():
    assert ss.restore_action("L", "R", "S", True, True) == "merge"


def test_restore_local_only_keep():
    assert ss.restore_action("L", None, None, True, False) == "keep"


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


# ── 4단계 --apply의 로컬 쓰기는 원자적이다 ───────────────────────────────────
#
# `open(local, "wb")`는 **선-truncate**한다. 쓰기 도중 ENOSPC로 죽으면
# `~/.claude/agents/foo.md`가 **잘린 채** 남고, 예외가 traceback으로 서서 `write_base`가
# 실행되지 않아 base는 옛 값 그대로다. 다음 판정이 `L≠S, R==S` → `local_ahead` →
# **다음 백업이 잘린 로컬을 레포의 온전한 사본 위에 push한다.** 잘린 파일이 모든 기기로
# 퍼지고 온전한 원본은 어디에도 남지 않는다.
#
# 아래 둘은 `add`/`overwrite` 갈래와 `merge` 갈래를 **각각** 건다. 두 갈래는 서로 다른
# 쓰기 호출이므로 한 곳만 `ks.dump_bytes`로 고치는 변조는 반대쪽 테스트만 빨개진다 —
# 둘 다 있어야 그 변조가 잡힌다.
#
# 실패 주입은 **디스크를 채우지 않는다.** `builtins.open`을 감싸 HOME 아래 쓰기 모드에서만
# "절반 쓰고 ENOSPC"를 흉내낸다. 옛 코드(직접 `open`)와 새 코드(`dump_bytes`의 `.tmp`)가
# **같은 지점**에서 실패하므로 갈리는 것은 실패 여부가 아니라 **로컬 파일이 잘렸는가**
# 하나다 — `os.replace`만 표적으로 삼으면 옛 코드는 그 줄에 닿지도 않아 "실패가 주입되지
# 않았다"와 "원자적이다"가 같은 초록이 된다.
#
# 하위 프로세스로 도는 이유는 `ss.BASE_DIR`가 **import 시점**의 HOME으로 고정되기
# 때문이다 — 인프로세스로 돌리면 개발 기기의 실제 base 블롭을 읽는다.

ENOSPC_RUNNER = r"""
import builtins, sys

lib, scripts, repo, home = sys.argv[1:5]
sys.path.insert(0, lib)
sys.path.insert(0, scripts)
import reconcile_restore as rr

real_open = builtins.open


class HalfWrite:
    def __init__(self, f):
        self.f = f

    def write(self, data):
        self.f.write(data[: len(data) // 2])
        self.f.flush()
        raise OSError(28, "No space left on device")

    def flush(self):
        self.f.flush()

    def fileno(self):
        return self.f.fileno()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.f.close()
        return False


def fake_open(path, mode="r", *a, **kw):
    f = real_open(path, mode, *a, **kw)
    if "w" in mode and str(path).startswith(home):
        return HalfWrite(f)
    return f


builtins.open = fake_open
sys.argv = ["reconcile_restore.py", repo, "--apply"]
try:
    rr.main()
except OSError:
    sys.exit(3)
finally:
    builtins.open = real_open
sys.exit(0)
"""


def run_restore_apply_with_enospc(tmp_path, home, repo):
    """`--apply`를 하위 프로세스에서 돌리되 HOME 아래 쓰기를 ENOSPC로 죽인다.

    반환값이 아니라 **exit code 3**을 단정한다 — 0이면 쓰기가 아예 시도되지 않은 것이고,
    그러면 아래 내용 단정은 "고쳐서 온전하다"가 아니라 "건드리지도 않았다"로 공허하게
    초록이 된다(⑵ 깊이 기준: 가드는 자기 입력이 비면 스스로 실패한다).
    """
    runner = tmp_path / "enospc_runner.py"
    runner.write_text(ENOSPC_RUNNER)
    root = os.path.dirname(__file__)
    r = subprocess.run(
        ["python3", str(runner),
         os.path.abspath(os.path.join(root, "..", "lib")),
         os.path.abspath(os.path.join(root, "..", "skills", "sync-restore", "scripts")),
         str(repo), str(home)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert r.returncode == 3, (
        "ENOSPC가 주입되지 않았다 — 이 시나리오가 그 쓰기 갈래를 타지 않은 것이다:\n%s%s"
        % (r.stdout, r.stderr)
    )


def leftover_temp_files(home):
    return sorted(
        os.path.join(r, f)
        for r, _, files in os.walk(str(home))
        for f in files
        if f.endswith(".tmp")
    )


def test_apply_overwrite_leaves_the_local_file_whole_when_the_write_dies(tmp_path):
    """fast_forward(=overwrite) 갈래. 잘린 로컬이 남으면 다음 백업이 그것을 push한다."""
    home, repo = tmp_path / "home", tmp_path / "repo"
    rel = "agents/foo.md"
    old = b"OLD LOCAL CONTENT THAT MUST SURVIVE\n"
    new = b"NEW CONTENT FROM THE REPO\n"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / rel).write_bytes(old)
    base = home / ".claude" / ".sync-state" / "base" / "agents"
    base.mkdir(parents=True)
    (base / "foo.md").write_bytes(old)                      # L == S
    (repo / "agents").mkdir(parents=True)
    (repo / rel).write_bytes(new)                           # R != S
    # 픽스처가 의도한 갈래를 실제로 타는지 고정한다 — 드리프트하면 이 테스트는 아래
    # merge 테스트의 사본이 되고, "한 곳만 고치기" 변조가 새어 나간다.
    assert ss.restore_action(
        ss.content_hash(old), ss.content_hash(new), ss.content_hash(old), True, True
    ) == "overwrite"

    run_restore_apply_with_enospc(tmp_path, home, repo)

    assert (home / ".claude" / rel).read_bytes() == old, "로컬 파일이 잘렸다"
    assert leftover_temp_files(home) == []


def test_apply_auto_merge_leaves_the_local_file_whole_when_the_write_dies(tmp_path):
    """clean auto_merge 갈래. 위와 **다른 쓰기 호출**이므로 따로 건다."""
    home, repo = tmp_path / "home", tmp_path / "repo"
    rel = "agents/bar.md"
    base_bytes = b"a\nb\nc\nd\ne\nf\ng\n"
    local_bytes = b"LOCAL\nb\nc\nd\ne\nf\ng\n"
    repo_bytes = b"a\nb\nc\nd\ne\nf\nREPO\n"
    (home / ".claude" / "agents").mkdir(parents=True)
    (home / ".claude" / rel).write_bytes(local_bytes)
    base = home / ".claude" / ".sync-state" / "base" / "agents"
    base.mkdir(parents=True)
    (base / "bar.md").write_bytes(base_bytes)
    (repo / "agents").mkdir(parents=True)
    (repo / rel).write_bytes(repo_bytes)
    assert ss.restore_action(
        ss.content_hash(local_bytes), ss.content_hash(repo_bytes),
        ss.content_hash(base_bytes), True, True
    ) == "merge"
    # 겹치지 않아야 병합이 깨끗하고, 그래야 쓰기까지 간다. 겹치면 conflicts로 접혀
    # 쓰기가 없고 위 exit code 단정이 그것을 잡는다.
    merged, nconf = ss.three_way_merge(local_bytes, base_bytes, repo_bytes)
    assert nconf == 0 and merged != local_bytes

    run_restore_apply_with_enospc(tmp_path, home, repo)

    assert (home / ".claude" / rel).read_bytes() == local_bytes, "로컬 파일이 잘렸다"
    assert leftover_temp_files(home) == []


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


def test_status_does_not_call_a_baseless_difference_a_two_sided_change(tmp_path):
    """spec 3.4 — 기준선 없는 L≠R은 "양쪽 변경"이 아니라 "기준선 없음"이다.

    `classify`는 그것을 conflict로 낸다(판정으로는 옳다 — 어느 쪽이 앞선지 모르니 restore가
    선택을 받아야 한다). 거짓인 것은 머리말이다 — 아무도 양쪽을 바꾸지 않았을 수 있다.
    대조군: 기준선을 두면 같은 파일이 진짜 충돌 머리말 아래로 간다.
    """
    home, repo = status_fixture(tmp_path)
    (repo / "agents" / "keep.md").write_text("레포 판본")
    out = run_check_status(home, repo).stdout
    assert section_of(out, "agents/keep.md").startswith("⚠ 기준선 없음")
    assert "양쪽 변경" not in out

    base = home / ".claude" / ".sync-state" / "base" / "agents"
    base.mkdir(parents=True)
    (base / "keep.md").write_text("옛 판본")           # L ≠ S, R ≠ S → 진짜 충돌
    out = run_check_status(home, repo).stdout
    assert section_of(out, "agents/keep.md").startswith("⚠ 충돌 — 양쪽 변경")
    assert "기준선 없음" not in out


def run_reconcile_backup(home, repo):
    script = os.path.join(
        os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts",
        "reconcile_backup.py")
    proc = subprocess.run(
        ["python3", os.path.abspath(script), str(repo)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def every_rel(out):
    """reconcile_backup 출력의 모든 relpath. `reject`는 두 갈래의 dict다(spec 3.1)."""
    rels = list(out["push"]) + list(out["in_sync"])
    for bucket in out["reject"].values():
        rels += bucket
    return rels


def test_backup_reconcile_splits_reject_by_base_presence(tmp_path):
    """①(spec 3.1) — 기준선이 없는 L≠R은 `reject.no_base`, 기준선 뒤로 레포가 바뀐 것은
    `reject.remote_ahead`. 실측(2026-09-01)의 형태 그대로다 — 첫 백업의 유일한 reject는
    기준선이 없어서였고 로컬이 앞서 있었다.

    **대조군을 함께 둔다** — `in_sync` 하나가 없으면 "아무것도 push하지 않는다"로도 단정이
    참이 된다.
    """
    home, repo = status_fixture(tmp_path)
    (repo / "agents" / "keep.md").write_text("레포 판본")            # 로컬 "공개"와 다르다
    (repo / "agents" / "internal-secret.md").write_text("사내 URL")  # 로컬과 같다 — 대조군
    out = run_reconcile_backup(home, repo)
    assert out["reject"] == {"remote_ahead": [], "no_base": ["agents/keep.md"]}
    assert out["in_sync"] == ["agents/internal-secret.md"] and out["push"] == []

    base = home / ".claude" / ".sync-state" / "base" / "agents"
    base.mkdir(parents=True)
    (base / "keep.md").write_text("옛 레포 판본")     # S ≠ R, S ≠ L → 리모트가 앞섰다
    out = run_reconcile_backup(home, repo)
    assert out["reject"] == {"remote_ahead": ["agents/keep.md"], "no_base": []}


def test_backup_reconcile_does_not_promise_to_push_an_excluded_file(tmp_path):
    """두 스킬이 같은 제외 파일을 **같게** 설명해야 한다.

    파일 결과는 걸든 안 걸든 같다 — 4단계 bash가 레포에서 지운다. 갈리는 것은 보고다:
    걸지 않으면 `/sync-backup`의 `push`가 이 파일을 "곧 업로드될 파일"로 렌더링하는데
    같은 세션의 `/sync-status`는 침묵한다. 10단계가 그 목록으로 base를 갱신하므로
    "올렸다"는 거짓 기록까지 남는다.

    **대조 파일을 함께 둔다** — 없으면 "아무것도 push하지 않는다"로도 단정이 참이 되고,
    필터가 전부를 지우는 회귀가 조용히 지나간다.
    """
    home, repo = status_fixture(tmp_path)
    (home / ".claude" / ".syncignore").write_text("agents/internal-*.md\n")
    out = run_reconcile_backup(home, repo)
    assert out["push"] == ["agents/keep.md"]
    assert all("internal-secret" not in rel for rel in every_rel(out))


def test_without_syncignore_the_backup_reconcile_pushes_both(tmp_path):
    """대조군 — 위 단정이 "그 파일이 원래 push에 없다"로 참이 되는 것을 막는다."""
    home, repo = status_fixture(tmp_path)
    out = run_reconcile_backup(home, repo)
    assert out["push"] == ["agents/internal-secret.md", "agents/keep.md"]


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

# ── 제외 파일도 **항목마다** 복원 처방이 다르다 ──────────────────────────────
#
# 앞 판은 이 묶음에 3-way 판정을 태우지 않고 머리말 하나로 *"평소의 3-way 판정을 그대로
# 받는다(추가·덮어쓰기·머지·보존)"* 만 말했다. 그러면 **항목별 처방을 적을 수 없다** —
# 레포에만 있는 파일은 복원이 **로컬에 만들고**, 로컬이 앞선 파일은 **손대지 않는다.**
# 사용자가 할 일이 그 둘에서 다르다.
#
# **backup 방향은 항목과 무관하게 하나다**(레포 사본이 지워진다). 그쪽은 머리말이 말하고
# 여기 섞지 않는다 — 섞으면 `keep` 항목에 "backup 시 push"가 붙는데 제외 파일에서
# 그것은 거짓이다.


def excluded_three_way_fixture(tmp_path):
    """제외 파일 셋이 **서로 다른** 3-way 판정을 받는 상태.

    한 갈래만 두면 "모든 항목에 같은 문구"를 쓰는 구현도 통과한다.
    """
    home, repo = status_fixture(tmp_path)
    (home / ".claude" / ".syncignore").write_text("agents/internal-*.md\n")
    # add — 레포에만 있다(로컬에 없다)
    (repo / "agents" / "internal-new.md").write_text("다른 기기가 올린 것")
    # skip — 양쪽이 같다
    (home / ".claude" / "agents" / "internal-same.md").write_text("같음")
    (repo / "agents" / "internal-same.md").write_text("같음")
    # keep — 로컬이 앞섰다(base == 레포)
    (home / ".claude" / "agents" / "internal-mine.md").write_text("이 기기가 고쳤다")
    (repo / "agents" / "internal-mine.md").write_text("옛 내용")
    base = home / ".claude" / ".sync-state" / "base" / "agents"
    base.mkdir(parents=True)
    (base / "internal-mine.md").write_text("옛 내용")
    return home, repo


def restore_prescription_table():
    """`check_status.py`의 처방표. **소스에서 읽는다** — 그 파일은 import하면 곧바로
    실행되는 스크립트라(모듈 최상위에서 argv를 읽고 출력한다) import로는 꺼낼 수 없다.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "skills", "sync-status",
                        "scripts", "check_status.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "RESTORE_PRESCRIPTION"
                for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("check_status.py에서 RESTORE_PRESCRIPTION을 찾지 못했다")


def prescription_of(out, rel):
    """`rel` 줄 **바로 다음** 줄의 처방. 없으면 None."""
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == rel and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            return nxt if nxt.startswith("복원:") else None
    return None


def test_each_excluded_file_carries_its_own_restore_prescription(tmp_path):
    """셋이 **서로 다른** 처방을 받는다. 같으면 판정을 안 태운 것이다."""
    home, repo = excluded_three_way_fixture(tmp_path)
    out = run_check_status(home, repo).stdout
    got = {rel: prescription_of(out, "agents/" + rel) for rel in
           ("internal-new.md", "internal-same.md", "internal-mine.md")}
    assert all(got.values()), (got, out)
    assert len(set(got.values())) == 3, got
    assert "추가" in got["internal-new.md"], got
    assert "유지" in got["internal-mine.md"], got
    # 셋 다 같은 머리말 아래여야 한다 — 판정을 태우면서 묶음을 흩뜨리면 "backup 시
    # push" 같은 거짓 머리말이 다시 붙는다.
    heads = {section_of(out, "agents/" + rel) for rel in got}
    assert len(heads) == 1 and ".syncignore" in heads.pop(), out


def test_the_ordinary_files_get_no_restore_prescription_line(tmp_path):
    """대조군 — 처방 줄은 제외 묶음에만 붙는다.

    일반 파일에도 붙이면 머리말이 이미 말하는 것을 두 번 말하게 되고, 그 둘이 갈리는
    자리가 생긴다(머리말은 backup·restore 양쪽을 말하고 이 줄은 restore만 말한다).
    """
    home, repo = excluded_three_way_fixture(tmp_path)
    out = run_check_status(home, repo).stdout
    assert prescription_of(out, "agents/keep.md") is None, out


def test_the_prescription_table_covers_every_action_the_shared_mapping_emits():
    """**완전성 단정 — 두 소비자가 같은 매핑을 쓴다.**

    `ss.restore_action`은 이제 소비자가 둘이다(`reconcile_restore`가 실행하고
    `check_status`가 설명한다). 처방표에 없는 동작이 나오면 그 항목은 `KeyError`로 죽거나
    조용히 빈 문구를 받는다 — 어느 쪽도 사용자에게 도달하지 않는다.

    기대 집합을 손으로 적지 않고 **매핑을 실제로 돌려서** 뽑는다. 아래 여섯 입력이
    `classify`의 여섯 출력을 남김없이 덮는지는 **같은 단정이 자기 몸통에서 확인한다** —
    덮지 못하면 이 단정이 재는 동작 집합이 조용히 줄어든다.
    """
    inputs = {
        "in_sync":      ("a", "a", "a", True, True),
        "repo_only":    (None, "r", None, False, True),
        "local_only":   ("l", None, None, True, False),
        "local_ahead":  ("l", "s", "s", True, True),
        "fast_forward": ("s", "r", "s", True, True),
        "conflict":     ("l", "r", "s", True, True),
    }
    for name, args in inputs.items():
        assert ss.classify(*args) == name, (name, ss.classify(*args))
    actions = {ss.restore_action(*args) for args in inputs.values()}
    assert set(restore_prescription_table()) == actions


