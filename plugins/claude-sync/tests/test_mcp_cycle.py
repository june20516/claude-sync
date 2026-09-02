"""backup과 restore를 교대로 적용했을 때의 수렴을 스크립트 경유로 검증한다 (spec 13장).

Task 3의 backup 반복만으로는 사용자가 선택지를 고른 뒤의 전이가 드러나지 않는다.
실제로 8.3의 base override 누락은 backup 반복 표를 전부 통과했다.

claude mcp add-json/remove는 테스트에서 실행할 수 없으므로 ~/.claude.json을 직접
수정해 CLI의 결과를 흉내낸다. 그 밖의 모든 단계는 실제 스크립트를 호출한다.
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import mcp_config as mc  # noqa: E402

SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
COLLECT = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "collect_mcp.py"))
UPDATE_BASE = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "update_base.py"))
PLAN = os.path.abspath(os.path.join(SKILLS, "sync-restore", "scripts", "plan_mcp.py"))

A = {"command": "a"}
B = {"command": "b"}
ORIG = {"command": "o"}


class Device:
    """한 기기(임시 HOME) + 공유 레포 디렉토리."""

    def __init__(self, root, repo, servers):
        self.home = os.path.join(root, "home")
        self.repo = repo
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        self.set_local(servers)

    # --- 로컬 상태 (claude mcp add-json / remove의 결과를 흉내낸다) ---
    def set_local(self, servers):
        with open(os.path.join(self.home, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump({"mcpServers": servers}, f)

    def local(self):
        with open(os.path.join(self.home, ".claude.json"), encoding="utf-8") as f:
            return json.load(f)["mcpServers"]

    def base(self):
        path = os.path.join(self.home, ".claude", ".sync-state", "base", mc.BACKUP_RELPATH)
        return mc.parse_base(open(path, "rb").read()) if os.path.exists(path) else None

    # --- 스크립트 호출 ---
    def _run(self, *args):
        proc = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                              env=dict(os.environ, HOME=self.home))
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    @property
    def staging(self):
        return os.path.join(self.home, "staging")

    def backup(self, push=True):
        """SKILL.md 6·10단계의 흐름: collect → (푸시 성공 시) update_base."""
        shutil.rmtree(self.staging, ignore_errors=True)
        report = json.loads(self._run(COLLECT, self.repo, self.staging))
        staged = os.path.join(self.staging, mc.BACKUP_RELPATH)
        if push and report["status"] == "ok" and os.path.exists(staged):
            self._run(UPDATE_BASE, self.staging, mc.BACKUP_RELPATH)
        return report

    def restore(self, adopt=(), keep_stale=(), keep_local=(), remove=()):
        """SKILL.md 6단계의 흐름: plan → CLI 실행 → apply-base → update_base."""
        backup_path = os.path.join(self.repo, mc.BACKUP_RELPATH)
        plan = json.loads(self._run(PLAN, "plan", backup_path))
        servers = self.local()
        for name in list(bucket(plan, "add")) + list(adopt):     # add-json
            servers[name] = plan["configs"][name]
        for name in remove:                              # mcp remove
            servers.pop(name, None)
        self.set_local(servers)
        choices_path = os.path.join(self.home, "choices.json")
        with open(choices_path, "w", encoding="utf-8") as f:
            json.dump({"keep_stale": list(keep_stale), "keep_local": list(keep_local)}, f)
        shutil.rmtree(self.staging, ignore_errors=True)
        self._run(PLAN, "apply-base", backup_path, self.staging, choices_path)
        self._run(UPDATE_BASE, self.staging, mc.BACKUP_RELPATH)
        return plan


def repo_servers(repo):
    return mc.load_backup(os.path.join(repo, mc.BACKUP_RELPATH))


def bucket(plan, name):
    """계획의 버킷 — `sections[<섹션>]` 안이다(spec 7). 섹션 이름은 어댑터에서 뽑는다."""
    (section,) = mc.SECTIONS
    return plan["sections"][section][name]


def set_repo(repo, servers):
    """다른 기기가 레포를 바꾼 상황을 만든다."""
    mc.dump_backup(servers, os.path.join(repo, mc.BACKUP_RELPATH))


def make_device(tmp_path, servers, repo_init=None):
    root = str(tmp_path)
    repo = os.path.join(root, "repo")
    os.makedirs(repo, exist_ok=True)
    if repo_init is not None:
        set_repo(repo, repo_init)
    return Device(root, repo, servers)


def test_case8_adopt_then_backup_converges_to_repo_value(tmp_path):
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()                                  # base 부트스트랩
    set_repo(dev.repo, {"x": B})                  # 타 기기가 변경
    assert dev.backup()["repo_ahead"]["present"] == ["x"]
    plan = dev.restore(adopt=["x"])
    assert bucket(plan, "repo_ahead") == ["x"]
    report = dev.backup()
    assert dev.local()["x"] == B
    assert repo_servers(dev.repo)["x"] == B
    assert dev.base()["x"] == B
    assert report["repo_ahead"] == {"present": [], "absent": []}
    assert dev.backup()["repo_ahead"] == {"present": [], "absent": []}


def test_case8_keep_local_pushes_local_value(tmp_path):
    """'로컬 유지'는 반드시 '나중에'와 다른 결과여야 한다 — override ③ 회귀."""
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()
    set_repo(dev.repo, {"x": B})
    dev.backup()
    dev.restore(keep_local=["x"])
    assert dev.base()["x"] == B                   # 그 이력은 잊는다
    report = dev.backup()
    assert repo_servers(dev.repo)["x"] == ORIG    # 케이스 7 경유로 push
    assert report["repo_ahead"] == {"present": [], "absent": []}
    dev.backup()
    assert repo_servers(dev.repo)["x"] == ORIG    # 이후 불변


def test_case8_defer_keeps_reporting(tmp_path):
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()
    set_repo(dev.repo, {"x": B})
    dev.backup()
    dev.restore()                                  # 무선택
    report = dev.backup()
    assert repo_servers(dev.repo)["x"] == B
    assert dev.local()["x"] == ORIG
    assert report["repo_ahead"]["present"] == ["x"]


def test_case9_three_choices(tmp_path):
    """채택 → in_sync / 로컬 유지 → 케이스 7 → push / 나중에 → 케이스 9 유지."""
    def setup(sub):
        dev = make_device(tmp_path / sub, {"Z": ORIG})
        dev.backup()
        set_repo(dev.repo, {"Z": B})               # 타 기기가 변경
        dev.set_local({"Z": A})                    # 이 기기도 변경 → 케이스 9
        assert dev.backup()["conflicts"]["repo_kept"] == ["Z"]
        return dev

    dev = setup("adopt")
    assert bucket(dev.restore(adopt=["Z"]), "both_changed") == ["Z"]
    assert dev.backup()["conflicts"] == {"repo_kept": [], "repo_absent": []}
    assert repo_servers(dev.repo)["Z"] == B

    dev = setup("keep")
    dev.restore(keep_local=["Z"])
    assert dev.backup()["conflicts"] == {"repo_kept": [], "repo_absent": []}
    assert repo_servers(dev.repo)["Z"] == A

    dev = setup("later")
    dev.restore()
    assert dev.backup()["conflicts"]["repo_kept"] == ["Z"]
    assert repo_servers(dev.repo)["Z"] == B


def test_case7_restore_does_not_touch_local(tmp_path):
    """케이스 7에는 선택지를 주지 않는다 — 미백업 로컬 변경이 파괴되면 안 된다."""
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()
    dev.set_local({"x": A})                        # 아직 백업하지 않은 로컬 변경
    plan = dev.restore()
    assert bucket(plan, "local_ahead") == ["x"]
    assert dev.local()["x"] == A


def test_case4_keep_brings_server_back_and_stabilizes(tmp_path):
    """기기 A가 삭제, 기기 B가 '유지' — X가 레포로 복귀한 뒤 부활·소멸이 반복되지 않는다."""
    dev = make_device(tmp_path, {"X": A, "y": A})
    dev.backup()
    set_repo(dev.repo, {"y": A})                   # 기기 A가 X를 지우고 백업한 결과
    assert dev.backup()["local_stale"] == ["X"]
    plan = dev.restore(keep_stale=["X"])
    assert bucket(plan, "local_stale") == ["X"]
    assert "X" not in dev.base()
    dev.backup()
    assert sorted(repo_servers(dev.repo)) == ["X", "y"]
    report = dev.backup()
    assert report["local_stale"] == [] and report["deleted"] == []
    assert sorted(repo_servers(dev.repo)) == ["X", "y"]


def test_case4_remove_converges(tmp_path):
    dev = make_device(tmp_path, {"X": A, "y": A})
    dev.backup()
    set_repo(dev.repo, {"y": A})
    dev.backup()
    dev.restore(remove=["X"])
    assert "X" not in dev.local()
    report = dev.backup()
    assert report["local_stale"] == []
    assert sorted(repo_servers(dev.repo)) == ["y"]


def test_two_cycles_reach_fixed_point(tmp_path):
    """backup→restore를 반복하면 2주기째부터 레포·base·보고가 변하지 않는다.

    1주기째는 restore가 케이스 2의 서버를 실제로 설치하므로 2주기와 다를 수 있다 —
    그 설치는 정당한 상태 변화다. 고정점은 2주기와 3주기가 같은지로 판정한다.
    """
    dev = make_device(tmp_path, {"X": A, "x": ORIG})
    dev.backup()                                   # base 부트스트랩: X·x는 이 기기가 올렸다
    set_repo(dev.repo, {"x": B, "z": B})           # 타 기기: X 삭제, x 변경, z 추가
    snapshots = []
    for _ in range(3):
        report = dev.backup()
        plan = dev.restore()                       # 무선택
        snapshots.append((repo_servers(dev.repo), dev.base(), report,
                          {k: v for k, v in plan["sections"][mc.SECTIONS[0]].items()
                           if isinstance(v, list) and v}))
    assert snapshots[1] == snapshots[2], "2주기와 3주기가 다르다 — 고정점이 아니다"
    assert snapshots[2][2]["local_stale"] == ["X"]
    assert snapshots[2][2]["repo_ahead"]["present"] == ["x"]


def test_v1_migration_restore_reports_unrestorable_without_failures(tmp_path):
    """마이그레이션 직후 restore가 add-json 실패를 0건으로 유지한다 — 10장."""
    dev = make_device(tmp_path, {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}})
    v1 = [{"name": "claude.ai Notion", "url": "https://mcp.notion.com/mcp", "type": "stdio"},
          {"name": "context7", "url": "https://mcp.context7.com/mcp", "type": "HTTP"}]
    with open(os.path.join(dev.repo, mc.BACKUP_RELPATH), "w", encoding="utf-8") as f:
        json.dump(v1, f)
    plan = dev.restore()
    assert sorted(bucket(plan, "unrestorable")) == ["claude.ai Notion", "context7"]
    assert bucket(plan, "add") == [] and bucket(plan, "needs_secret") == []
    dev.backup()
    assert sorted(repo_servers(dev.repo)) == ["claude.ai Notion", "context7", "playwright"]


def test_backup_without_changes_still_bootstraps_base(tmp_path):
    """'커밋할 변경 없음' 경로에서도 base가 기록되어야 삭제가 전파된다."""
    dev = make_device(tmp_path, {"x": A})
    dev.backup()
    assert dev.base() == {"x": A}
    dev.backup()                                   # 두 번째는 레포에 변경이 없다
    assert dev.base() == {"x": A}
    dev.set_local({})
    assert dev.backup()["deleted"] == ["x"]
    assert repo_servers(dev.repo) == {}


def test_backup_without_push_does_not_advance_base(tmp_path):
    """푸시 실패 — 레포가 그 내용을 갖지 않으므로 base를 기록하지 않는다."""
    dev = make_device(tmp_path, {"x": A})
    dev.backup(push=False)
    assert dev.base() is None


def test_skipped_backup_touches_neither_repo_nor_base(tmp_path):
    """MCP 단계 skip — 레포 파일 불변, base 불변."""
    dev = make_device(tmp_path, {"x": A})
    dev.backup()
    os.remove(os.path.join(dev.home, ".claude.json"))
    report = dev.backup()
    assert report["status"] == "skipped"
    assert repo_servers(dev.repo) == {"x": A}
    assert dev.base() == {"x": A}
