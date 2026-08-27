"""backup과 restore를 교대로 적용했을 때의 수렴을 스크립트 경유로 검증한다 (spec 14.2).

반복 backup만으로는 사용자가 선택지를 고른 뒤의 전이가 드러나지 않는다.
claude plugin 명령은 테스트에서 실행할 수 없으므로 plugin_cli.PluginCLI가 흉내낸다 —
그 밖의 모든 단계는 실제 스크립트를 서브프로세스로 호출한다.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import plugin_config as pc  # noqa: E402
from marks import requires_permission_bits  # noqa: E402
from plugin_cli import PluginCLI  # noqa: E402

SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
COLLECT = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "collect_plugins.py"))
UPDATE_BASE = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "update_base.py"))
PLAN = os.path.abspath(os.path.join(SKILLS, "sync-restore", "scripts", "plan_plugins.py"))
GH = {"source": {"source": "github", "repo": "o/r"}}


class Device:
    """한 기기(임시 HOME) + 공유 레포 디렉토리."""

    def __init__(self, root, repo):
        self.home = os.path.join(root, "home")
        self.repo = repo
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        self.cli = PluginCLI(self.home)

    # --- 로컬 상태 ---
    def local(self):
        return pc.read_local_sections(self.cli.settings_path)

    def base(self):
        path = os.path.join(self.home, ".claude", ".sync-state", "base", pc.BACKUP_RELPATH)
        return pc.parse_base(open(path, "rb").read()) if os.path.exists(path) else None

    def held(self):
        return pc.read_held_state(self.cli.held_path)

    # --- 스크립트 호출 ---
    def _run(self, *args, check=True):
        proc = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                              env=dict(os.environ, HOME=self.home))
        if check:
            assert proc.returncode == 0, proc.stderr
        return proc.stdout

    @property
    def staging(self):
        return os.path.join(self.home, "base-staging")

    def backup(self, push=True):
        """SKILL.md 5·10단계의 흐름: rm -rf → collect → (푸시 성공 시) update_base."""
        shutil.rmtree(self.staging, ignore_errors=True)
        report = json.loads(self._run(COLLECT, self.repo, self.staging))
        staged = os.path.join(self.staging, pc.BACKUP_RELPATH)
        # 게이트는 **최종 파일의 존재**다(7.4의 rename 계약). 위에서 스테이징을 통째로
        # 지우므로 이 파일은 **이번** collect가 rename했을 때만 존재한다.
        #
        # **이 게이트를 report["status"] == "ok"로 바꿔도 이 스위트는 잡지 못한다**
        # (실측 — 변조 M7이 757 passed로 살아남았다). 두 조건의 값이 갈리는 상태는 둘뿐이다.
        #
        #  (i) status "ok" + staged 부재 — 레포 쓰기는 성공했는데 os.replace가 실패해
        #      base_staging이 "failed"인 경우. 그때 status 게이트는 update_base를 부르지만
        #      update_base가 없는 파일에 경고 한 줄을 내고 **exit 0으로 끝나 base를
        #      전진시키지 않는다**(실측: 빈 스테이징으로 실행 → exit 0, base SHA 불변).
        #      결과가 같으므로 관측되지 않는다.
        # (ii) status "skipped" + staged 잔존 — 앞선 실행이 남긴 파일을 이번 실행이 지우지
        #      않은 경우. **여기서는 존재 게이트 쪽이 위험하다** — update_base가 그 옛
        #      파일을 그대로 base로 옮기므로, 이번 실행이 만들지 않은 내용으로 base가
        #      전진한다(실측: staged에 다른 내용을 두고 실행 → base가 그 내용으로 덮임).
        #      위의 rmtree가 그 상태를 만들지 않는 것이 유일한 근거다 — SKILL.md의 rm -rf가
        #      두 수집 단계보다 앞에서 딱 한 번 도는 배선과 같다(collect_plugins docstring).
        #
        # 존재 게이트를 쓰는 것은 SKILL.md의 배선을 그대로 옮긴 것이지 더 강해서가 아니다.
        # **rmtree를 이 함수에서 빼면 (ii)가 살아난다.**
        #
        # **형제 하네스와 조건이 다르다.** test_mcp_cycle.py:66은 여기에 없는
        # `report["status"] == "ok"` 축을 하나 더 갖는다. 플러그인 배선은 아직 SKILL.md에
        # 없지만(Task 14), MCP 배선인 sync-backup/SKILL.md:400은 `REPO_HAS_CONTENT`와
        # 파일 존재 두 축뿐이고 그 자리 주석이 "status 값을 다시 읽을 필요가 없다"라고
        # 못 박는다. 둘을 "맞추는" 수정을 한다면 MCP 쪽을 SKILL.md에 맞출 것.
        if push and os.path.exists(staged):
            self._run(UPDATE_BASE, self.staging, pc.BACKUP_RELPATH)
        return report

    def restore(self, choices=None, secrets=None, fail_marketplaces=()):
        """SKILL.md 5단계의 흐름: plan → CLI 실행 → apply-base → update_base.

        secrets는 {plugin_id: {key: value}} — 사용자가 값을 입력한 항목만이다.
        fail_marketplaces는 등록이 실패하는 이름 — 9.3.2의 blocked를 만든다.
        """
        backup_path = os.path.join(self.repo, pc.BACKUP_RELPATH)
        plan = json.loads(self._run(PLAN, "plan", backup_path))
        if plan["status"] == "skipped":
            return plan
        blocked = set()
        for entry in plan["marketplace_add"]:                       # 1단계
            if entry["name"] in fail_marketplaces:
                blocked.add(entry["name"])
                continue
            self.cli.marketplace_add(entry["name"], entry["arg"])
        for plugin_id in plan["install"]:                           # 2단계
            if self._blocked(plan, plugin_id, blocked):
                continue
            self.cli.install(plugin_id)
        for plugin_id in plan["disable_after_install"]:             # 3단계
            if self._blocked(plan, plugin_id, blocked):
                continue
            self.cli.disable(plugin_id)
        for plugin_id, options in (secrets or {}).items():          # 4단계
            if self._blocked(plan, plugin_id, blocked):
                continue
            self.cli.install(plugin_id, config=options)
        return self._apply_base(backup_path, plan, choices or {})

    @staticmethod
    def _blocked(plan, plugin_id, blocked):
        """1단계 등록이 실패한 마켓플레이스에 속하는가 (9.3.2).

        **2·3·4단계가 같은 술어를 쓴다.** 근거는 단계 종속이 아니라 명령의 형태다 —
        4단계도 `plugin install <id@marketplace> --config k=v` 형태라 등록되지 않은
        마켓플레이스로는 2단계와 똑같이 죽는다. 그래서 `plan_plugins._install_dependencies`가
        `depends_on`에 2단계 목록이 아니라 **2단계 ∪ 4단계**를 싣는다.

        4단계에서 빠뜨리면 조용한 fail-open이 된다 — 이 에뮬레이터의 `install`은 언제나
        exit 0이므로, **실제 CLI가 도달할 수 없는 상태**(등록에 실패한 마켓플레이스의
        플러그인에 설정이 채워진 상태)를 만들고 이어지는 백업이 그 값을 레포로 밀어
        시나리오가 초록으로 통과한다.
        """
        return plan["depends_on"].get(plugin_id) in blocked

    def _apply_base(self, backup_path, plan, choices):
        merged = {section: {"keep_stale": [], "keep_local": []} for section in pc.SECTIONS}
        for section, values in choices.items():
            # setdefault로 두면 섹션 이름 오타가 예외 없이 통과한다 — plan_plugins의
            # choice_list가 모르는 섹션을 그냥 무시하므로, **선택을 하나도 적용하지 않은
            # restore**가 초록으로 지나간다(9.3.4의 세 선택지를 섹션별로 쓸 때 밟는다).
            assert section in pc.SECTIONS, section
            merged[section].update(values)
        path = os.path.join(self.home, "choices.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f)
        shutil.rmtree(self.staging, ignore_errors=True)
        self._run(PLAN, "apply-base", backup_path, self.staging, path)
        self._run(UPDATE_BASE, self.staging, pc.BACKUP_RELPATH)
        return plan


def repo_doc(repo):
    return pc.load_backup(os.path.join(repo, pc.BACKUP_RELPATH))


def set_repo(repo, sections):
    """다른 기기가 레포를 바꾼 상황을 만든다."""
    pc.dump_backup(sections, os.path.join(repo, pc.BACKUP_RELPATH))


def make_device(tmp_path, repo_init=None):
    root = str(tmp_path)
    repo = os.path.join(root, "repo")
    os.makedirs(repo, exist_ok=True)
    if repo_init is not None:
        set_repo(repo, repo_init)
    return Device(root, repo)


# --- 에뮬레이터 계약 (14.3) — 이것이 틀리면 아래 시나리오가 전부 무의미하다 ---

def test_install_writes_true_but_preserves_an_existing_array(tmp_path):
    cli = PluginCLI(str(tmp_path))
    assert cli.install("p@m") == 0
    assert cli.settings()["enabledPlugins"]["p@m"] is True
    cli.set_enabled("q@m", ["1.0.0"])
    assert cli.install("q@m") == 0
    assert cli.settings()["enabledPlugins"]["q@m"] == ["1.0.0"]


def test_install_flattens_an_existing_object_value(tmp_path):
    """**실측 없음 — 추정**(plugin_cli 모듈 docstring 9번).

    1.2와 브리프 C1이 재는 것은 **객체/미설치** 행이다. `set_enabled`가 설치 기록을 함께
    남기므로(그 자리 docstring 참조) 여기서 만드는 상태는 **객체/이미 설치 → 재실행**이고,
    그 행은 두 표 어디에도 없다. 이 에뮬레이터는 설치 여부로 분기하지 않으므로 측정된
    행과 같은 결과를 낸다 — **결론이 아니라 근거가 추정이다.**

    평탄화가 객체 한 갈래뿐이라는 것(배열은 살아남는다)은 실측이고, 그쪽은
    test_install_writes_true_but_preserves_an_existing_array가 잰다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("o@m", {"version": "1.0.0"})
    cli.install("o@m")
    assert cli.settings()["enabledPlugins"]["o@m"] is True


def test_enable_and_disable_are_not_idempotent(tmp_path):
    """이미 그 상태면 exit 1 — 이 성질이 없으면 "현재 상태와 다를 때만"이 무의미해진다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m")
    assert cli.enable("p@m") == 1
    assert cli.disable("p@m") == 0
    assert cli.disable("p@m") == 1


def test_enable_and_disable_reject_an_unknown_plugin(tmp_path):
    """**에뮬레이터의 규약이지 실측이 아니다** (plugin_cli 모듈 docstring 4번).

    브리프 1-b는 설치되지 않은 id에 enable/disable을 낸 갈래를 재지 않았다. 여기서
    고정하는 것은 둘이다 — exit 1이라는 것, 그리고 **값을 만들어 내지 않는다**는 것.
    후자가 실질이다: 설치에 실패한 플러그인에 3단계(disable_after_install)가 로컬 값을
    심으면 다음 백업의 next_base가 그 키를 전진시켜 **복원 실패가 성공처럼 보인다**
    (10.4가 "실패한 항목은 로컬에 없으니 자동으로 빠진다"로 막으려는 것이 그것이다).
    """
    cli = PluginCLI(str(tmp_path))
    assert cli.enable("ghost@m") == 1
    assert cli.disable("ghost@m") == 1
    assert cli.settings()["enabledPlugins"] == {}
    # **두 파일 중 다른 쪽도 함께 잰다.** settings.json만 보면 실패 갈래가
    # installed_plugins.json에 항목을 남겨도 조용하다 — 그러면 read_installed의
    # installed_ids에 유령 id가 들어가 restore의 2단계가 그것을
    # skipped_already_installed로 접는다.
    assert cli.installed()["plugins"] == {}


def test_uninstall_removes_the_config_too_and_fails_when_absent(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m", config={"k": "v"})
    assert "p@m" in cli.installed()["plugins"]
    assert cli.uninstall("p@m") == 0
    assert cli.settings()["enabledPlugins"] == {}
    assert cli.settings()["pluginConfigs"] == {}
    # 설치 기록도 함께 지운다 — 남기면 restore의 2단계가 그 id를
    # skipped_already_installed로 접어 영영 설치하지 않는다.
    assert cli.installed()["plugins"] == {}
    assert cli.uninstall("p@m") == 1


def test_a_failed_uninstall_leaves_the_installed_record_alone(tmp_path):
    """**에뮬레이터의 규약이지 실측이 아니다.** 실패 갈래의 두 파일 일관성을 잰다.

    성공 갈래는 명령마다 두 파일의 절반이 따로 단정돼 있지만, 실패 갈래는 exit code와
    settings.json만 보면 `installed_plugins.json` 쪽 부작용이 조용히 지나간다.
    갈리면 `read_installed`의 installed_ids가 로컬 값과 어긋나 restore의 2단계/4단계
    분리가 틀린 쪽으로 떨어진다.

    "설치 기록만 있고 enabledPlugins에는 없는 id"는 공개 API로 만들 수 없으므로
    파일을 직접 심는다(스코프 테스트와 같은 방식). 그 상태 자체는 실측이 아니라
    이 단정을 공허하지 않게 만드는 픽스처다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.install("q@m")
    data = cli.installed()
    data["plugins"]["orphan@m"] = [{"scope": "user", "auto": False}]
    with open(cli.installed_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    assert cli.uninstall("orphan@m") == 1
    assert set(cli.installed()["plugins"]) == {"q@m", "orphan@m"}
    # 실패한 명령은 다른 항목의 기록도 건드리지 않는다.
    assert cli.settings()["enabledPlugins"] == {"q@m": True}


def test_install_config_merges_partially(tmp_path):
    """N2 — 지정하지 않은 키는 보존된다. 6.3의 부분 입력이 여기 걸려 있다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m", config={"a": "1", "b": "2"})
    cli.install("p@m", config={"b": "3"})
    assert cli.settings()["pluginConfigs"]["p@m"]["options"] == {"a": "1", "b": "3"}


def test_marketplace_remove_cascades_to_member_plugins(tmp_path):
    """실측 — 연쇄 삭제. restore가 이 명령을 실행하지 않는 이유다 (9.3.5)."""
    cli = PluginCLI(str(tmp_path))
    cli.marketplace_add("m", "o/r")
    cli.install("p@m", config={"k": "v"})
    cli.install("q@other")
    assert cli.marketplace_remove("m") == 0
    assert cli.settings()["enabledPlugins"] == {"q@other": True}
    assert cli.settings()["pluginConfigs"] == {}
    # 설치 기록도 소속 플러그인만 사라진다.
    assert set(cli.installed()["plugins"]) == {"q@other"}
    # 재실행은 exit 1 (1-b #8). uninstall(#6)·enable/disable(#5)의 같은 갈래와 짝이다 —
    # restore가 이 명령을 실행하지 않더라도 세 형제의 규약은 함께 고정해 둔다.
    assert cli.marketplace_remove("m") == 1


def test_dependency_install_marks_auto_and_explicit_install_clears_it(tmp_path):
    """N6 — 명시적 설치는 auto 표식을 **되돌릴 수 없게** 지운다."""
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset({"child@m"})
    cli.install("child@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_dependency_install_leaves_an_already_installed_child_alone(tmp_path):
    """C1 표의 마지막 행 — 건드리지 않은 값은 형태 무관 보존된다.

    자식이 이미 수동 설치돼 있으면 부모 설치가 그 값을 덮지도, auto로 되돌리지도
    않는다. 되돌아가면 H1이 사용자가 직접 고른 플러그인을 보류에 넣는다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("child@m", ["1.0.0"])
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    assert cli.settings()["enabledPlugins"]["child@m"] == ["1.0.0"]
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_installing_at_user_scope_keeps_other_scope_entries(tmp_path):
    """N4 — plugins[<id>]는 스코프별 배열이다. user 스코프 항목만 갈아 끼운다.

    이 동기화는 전부 user 스코프로 동작하므로(9.3.1), project 항목을 함께 지우면
    read_installed의 스코프 필터가 필터로 동작하는 입력 자체를 만들 수 없게 된다.
    **실측 없음 — 추정**(plugin_cli 모듈 docstring 8번): N4가 배열의 존재와 항목의 필드를
    쟀을 뿐, `install --scope user`가 다른 스코프 항목을 건드리지 않는다는 것은 재지 않았다.
    """
    cli = PluginCLI(str(tmp_path))
    with open(cli.installed_path, "w", encoding="utf-8") as f:
        json.dump({"version": 2,
                   "plugins": {"p@m": [{"scope": "project", "auto": True}]}}, f)
    cli.install("p@m")
    entries = cli.installed()["plugins"]["p@m"]
    assert {"scope": "project", "auto": True} in entries
    assert {"scope": "user", "auto": False} in entries
    # project 스코프의 auto는 auto 집합에 들어가지 않는다 (spec 3.4).
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_prune_removes_orphaned_auto_entries(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    cli.uninstall("parent@m")
    cli.prune()
    assert "child@m" not in cli.settings()["enabledPlugins"]
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_prune_keeps_a_manually_promoted_child(tmp_path):
    """N6 — auto가 지워진 항목은 부모가 사라져도 prune 대상이 아니다."""
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    cli.install("child@m")
    cli.uninstall("parent@m")
    cli.prune()
    assert cli.settings()["enabledPlugins"]["child@m"] is True


# --- 14.2 #1 부트스트랩 / #6 레포 쓰기 실패 ---

def test_backup_bootstraps_the_base_blob_with_three_sections(tmp_path):
    """7.4의 배선 결함을 잡는 유일한 테스트 — base가 영영 생성되지 않으면 삭제 전파가 죽는다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("p@m")
    for _ in range(3):
        dev.backup()
    base = dev.base()
    assert set(base) == set(pc.SECTIONS)
    assert base["enabledPlugins"] == {"p@m": True}


def test_backup_without_push_does_not_advance_base(tmp_path):
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup(push=False)
    assert dev.base() is None


def test_a_skipped_backup_does_not_promote_stale_staging(tmp_path):
    """`Device.backup`의 `rmtree`를 지키는 단정. 없으면 옛 staged 내용이 base로 올라간다.

    이 함수 위의 주석이 M7 등가성의 근거로 드는 것이 그 rmtree다 — 상태 (ii)
    (`status "skipped"` + staged 잔존)를 rmtree가 애초에 만들지 않는다는 것. 그 근거를
    여기서 관측한다.

    두 조건이 갈리려면 **base가 비어 있는 채로 staged만 남은 시점**이 필요하다. 첫 백업을
    `push=False`로 돌리면 그 시점이 만들어진다. 이어서 settings.json을 지우고 백업하면
    collect가 skipped로 접히므로, rmtree가 있으면 게이트가 끝내 닫혀 base가 생기지 않고,
    rmtree가 없으면 update_base가 앞선 실행이 남긴 파일을 base로 옮긴다.

    (실측 — 이 테스트가 없을 때 "rmtree 제거" 변조가 757 passed로 살아남았다.)
    """
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup(push=False)
    # 이 시점에 staged가 실제로 남아 있어야 아래 단정이 공허하지 않다.
    assert os.path.exists(os.path.join(dev.staging, pc.BACKUP_RELPATH))
    os.remove(dev.cli.settings_path)
    report = dev.backup()
    assert report["status"] == "skipped"
    assert dev.base() is None


@requires_permission_bits
def test_base_does_not_advance_when_the_repo_file_cannot_be_written(tmp_path):
    """14.2 #6 — rename 계약. 레포가 그 내용을 갖지 않았는데 base가 전진하면
    다음 백업이 이 기기 자신의 플러그인을 케이스 4로 오독한다."""
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup()
    dev.cli.install("q@m")
    os.chmod(os.path.join(dev.repo, pc.BACKUP_RELPATH), 0o400)
    os.chmod(dev.repo, 0o500)
    try:
        report = json.loads(dev._run(COLLECT, dev.repo, dev.staging))
    finally:
        os.chmod(dev.repo, 0o700)
        os.chmod(os.path.join(dev.repo, pc.BACKUP_RELPATH), 0o600)
    assert report["status"] == "skipped"
    assert dev.base()["enabledPlugins"] == {"p@m": True}
    # base 단정이 재는 범위는 좁다 — 이 테스트는 update_base를 아예 부르지 않으므로
    # 남는 것은 "`collect_plugins.py`가 base를 건드리지 않는다"뿐이다(rename 계약 자체는
    # 아래에서 잰다). **공허해 보인다고 이 형태를 복제하지 말 것** — 여기 남겨 둔 이유는
    # 그 좁은 성질도 회귀 대상이기 때문이고, 그것을 이 줄에 적어 두는 것이 조건이다.
    # **실제로 rename 계약을 재는 것은 여기다**: 스테이징의
    # 최종 파일이 직전 백업의 내용 그대로여야 한다. 레포 쓰기 실패에도 rename이 일어나면
    # 이 파일이 q@m을 담고, 다음 push 성공 시 base가 레포에 없는 값으로 전진한다.
    staged = os.path.join(dev.staging, pc.BACKUP_RELPATH)
    assert pc.parse_backup(open(staged, "rb").read())["enabledPlugins"] == {"p@m": True}


def test_skipped_backup_touches_neither_repo_nor_base(tmp_path):
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup()
    os.remove(dev.cli.settings_path)
    report = dev.backup()
    assert report["status"] == "skipped"
    assert repo_doc(dev.repo)["enabledPlugins"] == {"p@m": True}
    assert dev.base()["enabledPlugins"] == {"p@m": True}


# --- 9.3.2 등록 실패가 막는 단계 ---

BLOCKED_REPO = {
    "enabledPlugins": {"p@m": True, "q@m": True},
    "extraKnownMarketplaces": {"m": GH},
    "pluginConfigs": {"p@m": {"options": {"token": "s3cr3t"}}},
}


def _blocked_device(tmp_path, name):
    """마켓플레이스 m을 등록해야 하는 계획을 만드는 기기.

    p@m을 **미리 설치해 둔다** — 그래야 p@m이 2단계(install)가 아니라
    skipped_already_installed로 접히고, 4단계(config_keys)만 남는다. 그 분리가 없으면
    2단계 필터가 4단계 필터의 부재를 가려 이 테스트가 4단계를 재지 못한다.
    """
    dev = make_device(os.path.join(str(tmp_path), name), repo_init=BLOCKED_REPO)
    dev.cli.install("p@m")
    return dev


def test_a_blocked_marketplace_stops_the_install_and_config_steps(tmp_path):
    """9.3.2 — 1단계 등록 실패는 2단계뿐 아니라 **4단계도** 막는다.

    근거는 단계 종속이 아니라 명령의 형태다 — 4단계도 `plugin install <id@marketplace>
    --config k=v` 형태라 등록되지 않은 마켓플레이스로는 똑같이 죽는다. 그래서
    `plan_plugins._install_dependencies`가 `depends_on`에 2단계 ∪ 4단계를 싣는다.

    아래 `ok` 절반이 이 단정을 공허하지 않게 만든다 — 같은 픽스처에서 등록이 성공하면
    두 단계가 실제로 값을 만든다. 3단계는 이 테스트가 재지 않는다(에뮬레이터의
    `disable`이 미설치 id에 아무것도 쓰지 않아 필터를 지워도 관측되지 않는다 —
    plugin_cli 모듈 docstring 4번).
    """
    dev = _blocked_device(tmp_path, "blocked")
    plan = dev.restore(secrets={"p@m": {"token": "s3cr3t"}}, fail_marketplaces={"m"})
    # 픽스처가 의도한 계획인지 먼저 확인한다 — 아니면 아래 단정이 공허해진다.
    assert plan["install"] == ["q@m"]                       # 2단계 대상
    assert plan["skipped_already_installed"] == ["p@m"]     # 2단계 대상이 아니다
    assert plan["config_keys"] == {"p@m": ["token"]}        # 4단계 대상
    assert plan["depends_on"] == {"p@m": "m", "q@m": "m"}
    assert dev.cli.settings()["extraKnownMarketplaces"] == {}   # 등록이 실제로 실패했다
    assert "q@m" not in dev.cli.settings()["enabledPlugins"]    # 2단계가 막혔다
    assert dev.cli.settings()["pluginConfigs"] == {}            # 4단계가 막혔다

    ok = _blocked_device(tmp_path, "ok")
    ok.restore(secrets={"p@m": {"token": "s3cr3t"}})
    assert ok.cli.settings()["enabledPlugins"]["q@m"] is True
    assert ok.cli.settings()["pluginConfigs"]["p@m"]["options"] == {"token": "s3cr3t"}


def test_restore_rejects_an_unknown_choice_section(tmp_path):
    """선택지 섹션 이름 오타는 조용히 무시되지 않는다 (9.3.4).

    `plan_plugins`의 `choice_list`는 모르는 섹션을 그냥 무시하므로, 하네스가 오타를
    삼키면 **선택을 하나도 적용하지 않은 restore**가 초록으로 지나간다. 정상 이름이
    통과한다는 절반을 함께 두어 이 단정이 "언제나 죽는다"가 아님을 잰다.
    """
    ok = _blocked_device(tmp_path, "ok")
    assert ok.restore(choices={"enabledPlugins": {"keep_local": []}})["status"] == "ok"
    typo = _blocked_device(tmp_path, "typo")
    with pytest.raises(AssertionError):
        typo.restore(choices={"enabledPlugin": {"keep_local": ["q@m"]}})
