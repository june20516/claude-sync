"""backup과 restore를 교대로 적용했을 때의 수렴을 스크립트 경유로 검증한다 (spec 14.2).

반복 backup만으로는 사용자가 선택지를 고른 뒤의 전이가 드러나지 않는다.
claude plugin 명령은 테스트에서 실행할 수 없으므로 plugin_cli.PluginCLI가 흉내낸다 —
그 밖의 모든 단계는 실제 스크립트를 서브프로세스로 호출한다.

**그 에뮬레이터 자신의 계약은 test_plugin_cli.py가 잰다.** 이 파일은 `Device` 하네스와
그 시나리오만 담는다 — 두 책임이 한 파일에 있으면 시나리오가 늘어날 때 에뮬레이터
계약이 그 사이에 묻힌다.
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
COMPARE = os.path.abspath(os.path.join(SKILLS, "sync-status", "scripts", "compare_plugins.py"))
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

    def status(self):
        """읽기 전용 비교. 아무것도 바꾸지 않는다.

        backup·restore와 달리 base를 읽지도 갱신하지도 않는다(compare_plugins의 계약).
        보류가 status에서도 조용한지는 이 경로로만 잴 수 있다 — backup의 보고는 merge를
        거치므로 같은 사실을 다른 버킷 이름으로 말한다.
        """
        return json.loads(self._run(COMPARE, os.path.join(self.repo, pc.BACKUP_RELPATH)))

    # --- 스크립트 호출 ---
    def _run(self, *args):
        """스크립트를 서브프로세스로 부르고 stdout을 돌려준다.

        **0이 아닌 종료를 삼키지 않는다.** 삼키면 실패한 실행의 빈 stdout이 json 파싱에서
        죽거나 "항목 0개"로 접혀, 상태 기계가 그것을 삭제로 읽는다.
        """
        proc = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                              env=dict(os.environ, HOME=self.home))
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
        # 없지만(Task 14), MCP 배선인 sync-backup/SKILL.md:401은 `REPO_HAS_CONTENT`와
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
            # 실제 흐름은 **계획이 지목한 키만** 되묻는다(`plan["config_keys"]`). 대조하지
            # 않으면 계획이 요구하지 않은 id에도 설정이 채워져 **실제 흐름이 만들 수 없는
            # 상태**가 되고, 이어지는 백업이 그 값을 레포로 밀어 시나리오가 초록으로
            # 지나간다. `_apply_base`의 섹션 이름 가드와 같은 규율이다.
            assert plugin_id in plan["config_keys"], plugin_id
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


# `plan_plugins.py plan`의 최상위 필드 전부. **삭제 단계가 없다**는 사실을 이름이 아니라
# 집합으로 고정한다(9.3.5). 계획에 단계가 늘면 여기서 먼저 걸린다.
PLAN_TOP_LEVEL_KEYS = {
    "status", "sections", "marketplace_add", "skipped_always_known", "install",
    "skipped_already_installed", "disable_after_install", "config_keys",
    "repo_values", "local_values", "depends_on", "unrestorable_reasons",
}


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


# --- 14.2 #1 부트스트랩 / #6 레포 쓰기 실패 ---

def test_backup_bootstraps_the_base_blob_with_three_sections(tmp_path):
    """7.4의 배선 결함을 잡는 유일한 테스트 — base가 영영 생성되지 않으면 삭제 전파가 죽는다.

    **단 `Device` 모형의 배선이지 SKILL.md의 배선이 아니다.** 실제 배선의 같은 계열
    오사용(`update_base.py "$BASE_STAGING"` → `"$SYNC_REPO"`)은 어떤 테스트도 잡지
    못한다 — Task 14 Step 4b가 그 자리를 다룬다.
    """
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
    두 단계가 실제로 값을 만든다.

    **3단계는 이 테스트가 재지 않는다** — 사유는 `disable`의 미설치 갈래가 아니다.
    BLOCKED_REPO의 `enabledPlugins`가 둘 다 `True`라 `value_command`가 `"disable"`을 내지
    않고, 그래서 이 계획의 `disable_after_install`이 **비어 3단계 루프가 한 번도 돌지
    않는다**(실측 — 아래 단정이 그 사실을 고정한다). 3단계는 바로 아래
    `test_a_blocked_marketplace_stops_the_disable_step`이 **네 조건을 함께 세워** 잰다.
    """
    dev = _blocked_device(tmp_path, "blocked")
    plan = dev.restore(secrets={"p@m": {"token": "s3cr3t"}}, fail_marketplaces={"m"})
    # 픽스처가 의도한 계획인지 먼저 확인한다 — 아니면 아래 단정이 공허해진다.
    assert plan["install"] == ["q@m"]                       # 2단계 대상
    assert plan["skipped_already_installed"] == ["p@m"]     # 2단계 대상이 아니다
    assert plan["config_keys"] == {"p@m": ["token"]}        # 4단계 대상
    assert plan["disable_after_install"] == []              # 3단계 루프가 돌지 않는다
    assert plan["depends_on"] == {"p@m": "m", "q@m": "m"}
    assert dev.cli.settings()["extraKnownMarketplaces"] == {}   # 등록이 실제로 실패했다
    assert "q@m" not in dev.cli.settings()["enabledPlugins"]    # 2단계가 막혔다
    assert dev.cli.settings()["pluginConfigs"] == {}            # 4단계가 막혔다

    ok = _blocked_device(tmp_path, "ok")
    ok.restore(secrets={"p@m": {"token": "s3cr3t"}})
    assert ok.cli.settings()["enabledPlugins"]["q@m"] is True
    assert ok.cli.settings()["pluginConfigs"]["p@m"]["options"] == {"token": "s3cr3t"}


def test_a_blocked_marketplace_stops_the_disable_step(tmp_path):
    """9.3.2 — 등록 실패는 2·4단계뿐 아니라 **3단계도** 막는다.

    위 테스트가 3단계를 재지 못하는 것은 그 픽스처의 `disable_after_install`이 비어서다.
    3단계를 관측하려면 **네 조건이 함께** 필요하다(실측 — 하나라도 빠지면 필터 유무가
    값에 나타나지 않는다).

      ① 레포 값이 `false`다 — 그래야 `value_command`가 `"disable"`을 낸다.
      ② `pluginConfigs`로 candidates에 들어온다 — `enabledPlugins` 경로의 키는 정의상
         로컬에 없으므로 이미 설치된 id는 이 경로로만 candidates에 온다
         (`plan_plugins.py:208-212`).
      ③ **이미 설치돼 있다** — 로컬 `enabledPlugins`에 값이 있어야 `disable`이 exit 0으로
         실제로 쓴다. 없으면 추정 4번의 갈래(exit 1, 아무것도 쓰지 않음)로 떨어진다.
      ④ **그 마켓플레이스의 1단계 등록이 실패한다** — `_blocked`는 `depends_on`이 blocked에
         있을 때만 참이므로 이것 없이는 필터가 애초에 동작하지 않는다.

    **④가 특히 놓치기 쉽다.** 등록이 성공하면 `blocked`가 비어 필터가 애초에 동작하지
    않고, 그 id에 secret까지 주어지면 3단계가 `disable`을 낸 직후 4단계의
    `install --config`가 그 값을 되돌려(`PluginCLI.install` — 값이 배열이 아니면 `True`)
    최종 값이 `True`가 된다(실측). 같은 이유로 **아래 두 번째 복원에는
    `secrets`를 주지 않는다** — 주면 4단계가 3단계를 되돌려 수렴 단정이 거짓으로 죽는다.

    두 번째 복원이 이 단정을 공허하지 않게 만든다 — 원인을 없애면 3단계가 실제로 값을
    바꾼다. 이것은 9.3.2의 3단계 판이고, 14.2 #7("부분 실패 후 재실행 수렴")의 2단계 판은
    Task 13의 `test_blocked_install_is_recovered_by_the_next_restore`가 따로 잰다 — 그
    픽스처로는 3단계가 관측되지 않는다(실측: 레포 값이 둘 다 `true`이고 `pluginConfigs`가
    비어 `disable_after_install`이 언제나 `[]`다).
    """
    dev = make_device(tmp_path, repo_init={
        "enabledPlugins": {"p@m": False},                       # ①
        "extraKnownMarketplaces": {"m": GH},
        "pluginConfigs": {"p@m": {"options": {"token": pc.SENTINEL}}}})   # ②
    dev.cli.install("p@m")                                      # ③
    plan = dev.restore(fail_marketplaces={"m"})                 # ④
    # 픽스처가 의도한 계획인지 먼저 확인한다 — 아니면 아래 단정이 공허해진다.
    assert plan["disable_after_install"] == ["p@m"]             # ①②가 성립했다
    assert plan["skipped_already_installed"] == ["p@m"]         # ③이 성립했다
    assert plan["depends_on"] == {"p@m": "m"}                   # ④가 걸릴 자리가 있다
    assert dev.local()["enabledPlugins"]["p@m"] is True         # 3단계가 막혔다

    dev.restore()                                               # 원인 제거 (secrets 없이)
    assert dev.local()["enabledPlugins"]["p@m"] is False        # 3단계가 실제로 값을 바꾼다


def test_restore_rejects_a_secret_the_plan_did_not_ask_for(tmp_path):
    """계획이 되묻지 않은 id의 설정은 조용히 채워지지 않는다 (9.3.1 4단계).

    실제 흐름은 `plan["config_keys"]`가 지목한 키만 사용자에게 되묻는다. 하네스가 아무
    id나 받으면 **실제 흐름이 만들 수 없는 상태**를 만들고, 이어지는 백업이 그 값을
    레포로 밀어 시나리오가 초록으로 지나간다. 정상 id가 통과하는 절반을 함께 두어 이
    단정이 "언제나 죽는다"가 아님을 잰다.
    """
    ok = _blocked_device(tmp_path, "ok")
    assert ok.restore(secrets={"p@m": {"token": "s3cr3t"}})["status"] == "ok"
    stray = _blocked_device(tmp_path, "stray")
    # match를 거는 것은 이 파일에 AssertionError를 내는 자리가 셋이기 때문이다
    # (Device._run의 returncode 단정 · _apply_base의 섹션 가드 · 이 가드).
    with pytest.raises(AssertionError, match="q@m"):
        # q@m은 2단계(install) 대상이지 4단계 대상이 아니다.
        stray.restore(secrets={"q@m": {"token": "s3cr3t"}})


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


# --- 14.2 #2 선택지 실행 후 2회 백업 ---

def test_case4_keep_brings_the_plugin_back_and_stabilizes(tmp_path):
    """9.3.4 케이스 4의 "유지" — 레포로 되돌아간 뒤 부활·소멸이 반복되지 않는다.

    복원 뒤 두 backup을 한 회차로 줄여도 아래 단정은 참이다(실측 777 passed).
    전방 카나리아이고, 이 파일의 다른 2회차들과 같은 지위다. 하중을 지는 것은
    `set_repo` 앞의 최초 백업이다 — 그것을 지우면 CAUGHT다(실측).
    """
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("X@m")
    dev.cli.install("y@m")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {"y@m": True},
                        "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}})
    assert dev.backup()["sections"]["enabledPlugins"]["local_stale"] == ["X@m"]
    dev.restore(choices={"enabledPlugins": {"keep_stale": ["X@m"]}})
    assert "X@m" not in dev.base()["enabledPlugins"]
    dev.backup()
    assert sorted(repo_doc(dev.repo)["enabledPlugins"]) == ["X@m", "y@m"]
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["local_stale"] == []
    assert report["sections"]["enabledPlugins"]["deleted"] == []
    assert sorted(repo_doc(dev.repo)["enabledPlugins"]) == ["X@m", "y@m"]


def test_marketplace_keep_returns_it_without_running_remove(tmp_path):
    """9.3.5 — 마켓플레이스는 삭제를 자동 실행하지 않지만 "유지"는 반드시 효과가 있어야 한다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {}, "extraKnownMarketplaces": {},
                        "pluginConfigs": {}})
    dev.backup()
    plan = dev.restore(choices={"extraKnownMarketplaces": {"keep_stale": ["m"]}})
    # 계획에 **삭제 단계 자체가 없다**(9.3.5 — 연쇄 삭제가 소속 플러그인까지 지우므로
    # 자동 실행하지 않는다). 이 줄이 없으면 아래 로컬 단정은 "하네스가 remove를 부르지
    # 않는다"를 되풀이할 뿐이다.
    # **이름으로 거르지 않고 화이트리스트로 잰다.** "remove가 들어간 키가 없다"는
    # uninstall·prune·purge나 다른 이름을 놓치고, 그러면 주석이 코드보다 넓어진다.
    # 여기서는 최상위 필드 집합을 통째로 고정하므로 **이름과 무관하게** 새 단계가 생기면
    # 말한다. 늘어난 필드가 정당하면 이 목록에 더하면서 그 단계가 삭제인지 확인하면 된다.
    assert set(plan) == PLAN_TOP_LEVEL_KEYS
    dev.backup()
    assert "m" in repo_doc(dev.repo)["extraKnownMarketplaces"]
    assert "m" in dev.local()["extraKnownMarketplaces"]


# --- 14.2 #3 보류 후 침묵 ---

# 아래 두 시나리오가 **문자 그대로 같은** 픽스처를 쓴다. 같은 파일의 BLOCKED_REPO와 같은
# 규율이다 — 한 쌍이 공유하는 리터럴은 상수로 올린다. 셋 이상으로 늘릴 때가 아니라
# **둘이 문자 그대로 같아진 순간**이 기준이다(갈리면 한쪽만 다른 케이스로 미끄러진다).
DECLINED_REPO = {"enabledPlugins": {"delta@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}


def test_declined_config_silences_status_until_the_repo_value_changes(tmp_path):
    """6.4 — 보류를 고른 뒤 status가 조용해야 하고, 레포 값이 바뀌면 다시 보고해야 한다."""
    dev = make_device(tmp_path, repo_init=DECLINED_REPO)
    dev.restore(choices={"pluginConfigs": {"declined": ["delta@m"]}})
    assert dev.held()["pluginConfigs"]["delta@m"]
    section = dev.status()["sections"]["pluginConfigs"]
    assert section["only_repo"] == [] and section["changed"] == []
    assert section["held"]["declined"] == ["delta@m"]

    changed = json.loads(json.dumps(DECLINED_REPO))
    changed["pluginConfigs"]["delta@m"]["options"]["extra"] = pc.SENTINEL
    set_repo(dev.repo, changed)
    assert dev.status()["sections"]["pluginConfigs"]["only_repo"] == ["delta@m"]


def test_declined_config_keeps_the_repo_entry_across_two_backups(tmp_path):
    """6.4 — 초판의 "base에 레포 값 기록"이 케이스 3으로 착지시켰던 자리다.

    기기 B가 "이 기기에서는 안 쓴다"고 말했을 뿐인데 기기 A가 백업해 둔 설정 키 목록이
    레포에서 사라지면 안 된다.

    **아래 base 단정은 오늘 두 겹으로 참이다** — next_base가 값 보류 키를 base에서 빼는
    것(H4)과, 그 앞의 "로컬이 동의한 키만 전진"이 로컬에 없는 키를 애초에 올리지 않는
    것. 어느 한쪽만 뒤집어도 참이 유지되므로 **단일 변조로는 잡히지 않는다.** 그런데도
    거는 이유는 6.4가 지목하는 초판의 형태(apply-base가 레포 값을 base에 그대로 기록)가
    그 두 겹을 **함께** 우회하고, 그때 다음 백업이 케이스 3(삭제)으로 착지하기 때문이다.
    """
    dev = make_device(tmp_path, repo_init=DECLINED_REPO)
    dev.restore(choices={"pluginConfigs": {"declined": ["delta@m"]}})
    assert "delta@m" not in dev.base()["pluginConfigs"]
    dev.backup()
    # 14.2 #3이 요구하는 2회차다. **오늘은 1회차와 같은 상태를 낸다** — 두 회차를 한 회차로
    # 줄여도 아래 단정은 참이다(실측). 그래도 남기는 것은 전방 카나리아이기 때문이다:
    # 보류가 회차 사이에 풀리는 형태의 회귀는 2회차에서만 드러난다.
    # **같은 파일 `test_case4_keep…`의 2회차도 오늘 관측되지 않는다(실측 — 그쪽도 한
    # 회차로 줄이면 777 passed다).** 이 파일의 2회차는 전부 같은 지위다. 앞 판은 그쪽이
    # "실제로 값을 바꾸는 회차"라고 적었는데 거짓이었다 — 값을 바꾸는 것은 그 시나리오의
    # **1회차**이고(그 직후 레포에 X@m이 처음 나타난다), 하중을 지는 것은 `set_repo`
    # **앞의** 최초 백업이다(그것을 지우면 CAUGHT다).
    dev.backup()
    assert repo_doc(dev.repo)["pluginConfigs"]["delta@m"]["options"] == {
        "apiKey": pc.SENTINEL}
    # 보류 선택은 backup을 거쳐도 살아 있어야 한다 — 소유자가 apply-base 하나뿐이라는
    # 계약(write_held_state)이 여기서도 걸린다. 사라지면 다음 restore가 다시 묻는다.
    assert dev.held()["pluginConfigs"]["delta@m"]


def test_partially_entered_config_does_not_drop_the_other_keys(tmp_path):
    """14.1 — 세 키 중 두 개만 입력해도 레포의 세 번째 키가 사라지지 않는다 (6.3).

    **"사라지지 않음"만 재면 이 시나리오의 두 입력 중 어느 것도 단정을 좌우하지 않는다**
    (실측 — `declined`만 빼도, `secrets`만 빼도 스위트가 그대로 통과했다). 보류가 없으면
    그 항목은 `conflicts.repo_kept`로 떨어지는데 **그때도 레포 값은 보존되기** 때문이다.
    두 경로가 실제로 갈리는 곳은 다음 실행의 침묵이다 —

      [declined 있음] status: changed == []
      [declined 없음] status: changed == ["p@m"]  ← 영원히 다시 묻는다

    spec 6.3이 부분 입력에 보류를 요구하는 **이유 자체**가 그것이고, 14.2 #5가 경고한
    형태("사라지지 않음만 보므로 영원히 다시 묻는 실패를 통과시킨다")의 pluginConfigs
    판이다. enabledPlugins와 달리 그것을 대신 잡는 형제 시나리오가 없으므로 여기서 잰다.
    """
    repo_init = {"enabledPlugins": {"p@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"p@m": {"options": {k: pc.SENTINEL
                                                       for k in ("a", "b", "c")}}}}
    dev = make_device(tmp_path, repo_init=repo_init)
    dev.restore(secrets={"p@m": {"a": "1", "b": "2"}},
                choices={"pluginConfigs": {"declined": ["p@m"]}})
    # 입력한 두 키만 로컬에 들어간다 (N2 — `install --config`는 부분 병합이다).
    # 이 줄이 secrets를 단정에 싣는 유일한 자리다.
    assert dev.local()["pluginConfigs"]["p@m"]["options"] == {"a": "1", "b": "2"}
    assert dev.held()["pluginConfigs"]["p@m"]                       # 6.3 → 보류로 기록된다
    # 아래 2회차도 **오늘 관측되지 않는다**(실측 — 한 회차로 줄여도 777 passed).
    # 전방 카나리아이고, 이 파일의 다른 2회차들과 같은 지위다(위 declined 시나리오 참조).
    dev.backup()
    dev.backup()
    assert sorted(repo_doc(dev.repo)["pluginConfigs"]["p@m"]["options"]) == ["a", "b", "c"]
    # **위 줄만으로는 두 경로가 갈리지 않는다**(위 docstring). 갈리는 곳이 여기다.
    assert dev.status()["sections"]["pluginConfigs"]["changed"] == []


# --- 14.2 #4 보류 진입 → 이탈 ---

def test_auto_dependency_round_trip_keeps_the_entry_in_the_repo(tmp_path):
    """14.2 #4의 H1 — z를 손으로 설치 → 백업 → z가 의존성이 됨 → 백업 →
    부모 제거 + prune → 백업. **z가 레포에 남아 있어야 한다.**

    1·2·3은 held가 유지되는 동안만 확인하므로 이 결함을 하나도 잡지 못한다.
    """
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("z@m")
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True

    dev.cli.uninstall("z@m")
    dev.cli.set_manifest("p@m", ["z@m"])
    dev.cli.install("p@m")                              # z가 auto로 다시 들어온다
    # **주석이 약속한 사실을 확인한다.** 자식이 로컬에 들어오지 않으면 아래가 재는 것은
    # "레포에만 있고 auto로 표시된 키가 보류된다"이지 14.2 #4/H1이 요구하는 **로컬에
    # 되살아난 auto 의존성**이 아니다. **초판에서는** 이 줄이 없어 에뮬레이터가 자식을
    # 넣지 않게 만드는 변조가 스위트 전체에서 살아남았다(그 시점의 실측). 지금은 같은
    # 변조를 계약 파일도 잡으므로 이 줄만 지워도 CAUGHT다(실측) — 그래도 남기는 이유는
    # 층이 다르기 때문이다: 계약 파일은 N1의 규약을, 이 줄은 **이 시나리오가 딛고 선
    # 상태**를 잰다. N1의 계약 자체는 test_plugin_cli.py가 잰다.
    assert dev.local()["enabledPlugins"]["z@m"] is True
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["held"]["auto"] == ["z@m"]
    assert report["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True

    dev.cli.uninstall("p@m")
    dev.cli.prune()
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["deleted"] == ["p@m"]
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True
    assert dev.backup()["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True


def test_local_directory_marketplace_never_reaches_the_repo(tmp_path):
    """H2 — 마켓플레이스와 **그 소속 플러그인**이 둘 다 올라가지 않아야 한다.

    플러그인 키만 올라가면 기기 B의 restore가 매번 "먼저 마켓플레이스를 등록해야
    합니다"를 내는데, 기기 B에는 등록할 소스 자체가 없다.
    """
    dev = make_device(tmp_path)
    dev.cli.set_directory_marketplace("mylocal", "/tmp/x")
    dev.cli.install("p@mylocal")
    dev.cli.marketplace_add("gh", "o/r")
    dev.cli.install("q@gh")
    dev.backup()
    doc = repo_doc(dev.repo)
    # 값의 **계약**은 test_plugin_cli.py가 지고(추정 6·7번), 여기서는 그것을 상수 `GH`로
    # **참조만 한다** — 리터럴을 다시 적지 않는다는 뜻이지 모양을 재지 않는다는 뜻이
    # 아니다. 실제로 에뮬레이터의 값 모양을 미끄러뜨리면 계약 테스트와 이 시나리오가
    # **함께** FAIL한다(실측: github→url, directory→dir 둘 다). **그것이 정상이다** —
    # 공유 상수를 거쳐 같은 사실에 걸리는 것이지 계약이 이 파일에 있다는 뜻이 아니다.
    # 이 시나리오의 주제는 "directory 것만 빠지고 github 것은 그대로 올라간다"다.
    assert doc["extraKnownMarketplaces"] == {"gh": GH}
    assert doc["enabledPlugins"] == {"q@gh": True}
    assert dev.backup()["sections"]["enabledPlugins"]["deleted"] == []


# --- 14.2 #5 선택 후 고정점 ---

def test_keep_choice_is_not_asked_again(tmp_path):
    """14.2 #5 — #2는 "사라지지 않음"만 보므로 **영원히 다시 묻는** 실패를 통과시킨다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("X@m")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {}, "extraKnownMarketplaces": {"m": GH},
                        "pluginConfigs": {}})
    dev.backup()
    dev.restore(choices={"enabledPlugins": {"keep_stale": ["X@m"]}})
    dev.backup()
    dev.backup()
    plan = dev.restore()
    assert plan["sections"]["enabledPlugins"]["local_stale"] == []
    assert plan["sections"]["enabledPlugins"]["in_sync"] == ["X@m"]


# --- 14.2 #7 부분 실패 후 재실행 수렴 ---

def test_blocked_install_is_recovered_by_the_next_restore(tmp_path):
    """9.3.2 — 등록이 실패한 마켓플레이스의 플러그인은 시도하지 않는다.

    시도하면 CLI가 "플러그인이 없다"와 똑같은 문구로 실패해 거짓 실패를 양산한다.
    원인을 없애고 다시 돌리면 남은 항목이 복원되어야 한다.

    **규정이 예상한 SURVIVE는 실측으로 반증됐다.** 규정은 "`Device.restore`의 `blocked`
    검사를 지우면 에뮬레이터가 실패하지 않으므로 이 시나리오가 통과해 버린다"고 적었으나,
    2단계의 필터를 지우는 변조도 그 필터가 읽는 `depends_on`을 비우는 변조도 둘 다 이
    시나리오가 FAIL로 잡았다 — 등록이 실패했는데도 **p@m이 설치돼 버리는 것**이 아래
    로컬 단정에 걸리기 때문이다. 실패를 흉내낼 수단이 없다는 것과 잘못된 성공을 잴 수
    없다는 것은 다른 말이었다.

    그런데도 `depends_on` 단정을 따로 두는 것은 층이 다르기 때문이다 — 그 필터가 딛고 선
    **프로덕션 쪽 입력**이 비면 필터가 무엇을 하든 아무것도 막지 못하고, 그때 실패
    메시지가 증상(설치됐다)이 아니라 원인(계획이 의존을 싣지 않았다)을 가리킨다.
    """
    dev = make_device(tmp_path, repo_init={
        "enabledPlugins": {"p@m": True, "q@other": True},
        "extraKnownMarketplaces": {"m": GH, "other": {"source": {"source": "github",
                                                                 "repo": "o/o"}}},
        "pluginConfigs": {}})
    plan = dev.restore(fail_marketplaces=["m"])
    assert plan["depends_on"] == {"p@m": "m", "q@other": "other"}
    assert "p@m" not in dev.local()["enabledPlugins"]
    assert dev.local()["enabledPlugins"]["q@other"] is True
    assert "p@m" not in (dev.base() or {}).get("enabledPlugins", {})   # 10.4
    dev.restore()
    assert dev.local()["enabledPlugins"]["p@m"] is True


# --- 14.2 #8 H3 탈출구 왕복 ---

# 아래 두 시나리오가 **문자 그대로 같은** 픽스처를 쓴다(DECLINED_REPO와 같은 규율).
# 레포 값이 확장 포맷이라는 것이 H3의 술어이므로, 이 값이 불리언으로 미끄러지면 두
# 시나리오가 **동시에** 주제를 잃는다 — 한 자리에 두면 그 미끄러짐이 한 번만 일어난다.
EXTENDED_REPO = {"enabledPlugins": {"p@m": ["1.0.0"]},
                 "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}}


def test_extended_value_escape_hatch_round_trip(tmp_path):
    """7.3 — 탈출구 실행 → backup 2회 → 레포 값이 true → 그 뒤 uninstall이 케이스 3으로 전파.

    #4·#5 어느 것도 이 경로를 덮지 않는다. "지우려면 먼저 불리언화"가 실제로 성립하는지가
    여기서 판정된다.
    """
    dev = make_device(tmp_path, repo_init=EXTENDED_REPO)
    plan = dev.restore()
    assert plan["sections"]["enabledPlugins"]["add"] == ["p@m"]     # 설치는 한다
    assert dev.local()["enabledPlugins"]["p@m"] is True
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] == ["1.0.0"]  # 값은 밀지 않는다

    dev.restore(choices={"enabledPlugins": {"release": ["p@m"]}})    # 탈출구
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] is True
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] is True
    # **정리하는 것은 backup이 아니라 apply-base다.** 규정 초안은 두 backup 뒤에 곧바로
    # []를 기대했으나 실측은 ['p@m']이었다 — plugins-held.json의 소유자는
    # plan_plugins.py apply-base **하나뿐이고**(write_held_state의 계약: 소유자가 둘이면
    # backup이 사용자의 선택을 덮어쓴다), collect_plugins는 그 파일을 읽기만 한다.
    # 그러므로 "조건이 사라졌다"는 사실만으로 항목이 사라지지 않는다. 아래 두 줄이
    # 그 순서를 그대로 잰다 — 위가 없으면 아래는 "restore가 지웠다"가 아니라 "언젠가
    # 지워졌다"만 말한다.
    assert dev.held()["release"]["enabledPlugins"] == ["p@m"]        # backup은 손대지 않는다
    dev.restore()
    assert dev.held()["release"]["enabledPlugins"] == []             # 조건이 사라져 정리됨

    dev.cli.uninstall("p@m")
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["deleted"] == ["p@m"]
    assert "p@m" not in repo_doc(dev.repo)["enabledPlugins"]


def test_uninstall_before_the_escape_hatch_does_not_propagate(tmp_path):
    """7.3 — H3의 조건은 **레포 값**이므로 로컬에서 지워도 보류가 유지된다.

    삭제가 전파되지 않고 다음 restore가 다시 설치한다. 안내 문구가 "먼저 불리언화"를
    적어야 하는 이유이고, 이 성질이 깨지면 그 안내가 거짓이 된다.

    **`deleted == []`는 세 겹으로 참이다(실측한 행렬이다).** 겹치는 가드는 셋이다 —
      ⓐ `merge`의 값 보류 스킵(그 키가 판정표를 아예 타지 않는다)
      ⓑ `next_base`의 값 보류 스킵(base에서 그 키를 뺀다)
      ⓒ `next_base`의 **값 동의 규칙**("로컬이 동의한 키만 전진")

    셋 중 **하나만** 뒤집어도(ⓐ·ⓑ·ⓒ 각각) 이 시나리오는 통과하고, **둘을 함께**
    뒤집어도(ⓐⓑ·ⓑⓒ·ⓐⓒ) 통과한다. **셋을 함께 뒤집을 때 비로소 FAIL한다** — 그때
    레포의 `p@m`이 실제로 사라진다(프로브: `deleted: ['p@m']`, `REPO: {}`). 일곱 조합을
    전부 재서 얻은 표다.

    **ⓑ가 이 시나리오에서 일하지 않는다는 것도 실측이다.** ⓑ만 지우고 base를 찍으면
    복원 후에도 백업 후에도 `{}`다 — `p@m`을 막고 있는 것은 ⓑ가 아니라 ⓒ다(로컬은
    `True`, merged는 `["1.0.0"]`이라 `same()`이 거짓이고, 이전 base에도 그 키가 없다).
    이 문단의 앞 판은 겹을 둘로 적고 그 둘째를 ⓑ로 지목했는데 **둘 다 틀렸다.**

    그러므로 **이 시나리오가 재는 것은 그 겹들의 조합이 아니다.** 재는 것은 7.3의 안내
    문구가 참이라는 것 — 뒤따르는 두 단정(레포 값 보존·다음 restore의 재설치)이 그것이고,
    그 성질을 **단일·이중 변조로 깨는 방법은 아직 찾지 못했다.**
    """
    dev = make_device(tmp_path, repo_init=EXTENDED_REPO)
    dev.restore()
    dev.backup()
    dev.cli.uninstall("p@m")
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] == ["1.0.0"]
    assert dev.restore()["sections"]["enabledPlugins"]["add"] == ["p@m"]


# --- 주기 고정점 ---

def test_two_cycles_reach_a_fixed_point(tmp_path):
    """backup→restore를 반복하면 2주기째부터 레포·base·보고가 변하지 않는다.

    1주기째는 restore가 케이스 2의 항목을 실제로 설치하므로 2주기와 다를 수 있다 —
    그 설치는 정당한 상태 변화다.
    """
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("X@m")
    dev.cli.install("x@m")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {"x@m": False, "z@m": True},
                        "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}})
    snapshots = []
    for _ in range(3):
        report = dev.backup()
        plan = dev.restore()
        snapshots.append((repo_doc(dev.repo), dev.base(), report,
                          plan["sections"]["enabledPlugins"]))
    assert snapshots[1] == snapshots[2], "2주기와 3주기가 다르다 — 고정점이 아니다"
    assert snapshots[2][2]["sections"]["enabledPlugins"]["local_stale"] == ["X@m"]
