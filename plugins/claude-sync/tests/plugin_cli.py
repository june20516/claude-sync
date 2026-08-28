"""`claude plugin` CLI 에뮬레이터 (spec 14.3).

**이 파일이 곧 CLI 동작의 정의가 된다.** 브리프 1-b의 실측표를 그대로 구현하지 않으면
교대 테스트가 아무것도 검증하지 않는다. 실측되지 않은 갈래는 주석에 그렇게 적는다.

두 파일을 모두 재현한다 — settings.json(값)과 installed_plugins.json(auto 플래그).
후자를 빼면 hold가 항상 빈 집합이 되어 **H1을 교대 테스트가 전혀 검증하지 못한다.**

**출처 둘.** ① `docs/superpowers/2026-08-20-plugins-sync-followup-BRIEF.md`의
1-b 실측 결과 표(항목 #2~#13, `claude 2.1.241`), 그 아래 발견 N1·N2·N4·N6,
1-c의 C1(확장 포맷 값 표). ② `docs/superpowers/2026-08-29-plugin-cli-smoke.md` —
spec 14.5의 실환경 스모크(`claude 2.1.250`). 아래 목록의 판정은 ②가 갱신한 것이다.
메서드마다 근거 항목 번호를 적어 둔다 — 실제 CLI가 바뀌었을 때
드리프트가 보이게 하려는 것이다. **명령 메서드에 번호가 없는 동작은 아래 목록에 있어야
한다**(순수 파일 입출력 헬퍼 `_read`/`_write`는 CLI 동작이 아니라 근거가 없다).

**갈래 열하나의 판정.** 초판은 이 열하나를 전부 *"실측 없음 — 추정"*으로 선언했다.
spec 14.5의 실환경 스모크(`docs/superpowers/2026-08-29-plugin-cli-smoke.md`,
`claude 2.1.250`)가 그중 **여섯을 실측으로 닫았고**(2·3·5·7·9·11), **둘을 뒤집었으며**
(4·6), **셋은 여전히 미확인**이다(1·8·10). 셋이 남은 이유는 하나다 — 그 스모크의 픽스처가
**마켓플레이스 하나·플러그인 하나·스코프 하나**였다. 각 항목 머리의 표식이 그 판정이다.

*표시 규약*: 사용처에는 표식을 **`**실측**(모듈 docstring N번)` 또는
`**실측 없음 — 추정**(모듈 docstring N번)` 두 형태로만** 적는다. 번호가 양방향으로
걸려 있어야 사용처만 읽는 사람도 그 자리의 근거 등급을 알 수 있다. **한쪽만 고치면
규약이 무너진다** — 승격도 강등도 두 자리를 함께 고친다.

*목록의 규율*: **CLI가 파일에 무엇을 남기는지를 정하는 자리는 헬퍼라도 넣는다**
(`_forget_installed`·`_mark_installed`가 그래서 2번·8번이다). 순수 입출력(`_read`/`_write`)과
CLI 명령이 아닌 픽스처 장치(`__init__`·`set_enabled`·`set_manifest`·
`set_directory_marketplace`)는 넣지 않는다 — 대신 그 자리에 픽스처 결정임을 적는다.

  1. **[미확인]** `marketplace remove`가 `pluginConfigs`까지 지우는가. 1-b #8은
     `enabledPlugins`에서 사라진다는 것만 쟀다. #6(`uninstall`)이 두 필드를 함께 지우므로
     같은 규율을 폈다. 스모크도 닫지 못했다 — 그 시점의 픽스처에 `pluginConfigs`가
     **비어 있어** 지워졌는지 애초에 비어 있었는지 구별할 수 없었다.
  2. **[실측]** 세 삭제 명령이 `installed_plugins.json` 항목을 지운다. N1은
     "`uninstall epsilon` 후에도 zeta가 남고 `prune`이 그때서야 잡는다"로 **부모 항목의
     소멸을 함의**할 뿐 그 파일의 내용을 직접 재지 않았다. 스모크가 `uninstall`과
     `marketplace remove` 둘 다에서 항목이 사라지는 것을 직접 읽었다(5장).
  3. **[실측]** 값이 `false`인 플러그인을 다시 `install` 하면 **`true`**가 된다. #2의
     멱등성은 켜진 항목에서 쟀고 C1 표는 배열·객체만 쟀다. 스모크가 `false` 행을 직접
     쟀다(2장) — spec 8.4가 "로컬에 키가 없다"에 대해 두는 가정과 같은 방향이었다.
  4. **[실측 — 추정이 틀렸다]** 설치되지 않은 id에 `enable`/`disable`을 냈을 때.
     초판은 *"exit 1을 내고 값도 설치 기록도 만들지 않는다"*로 두었으나, 실제 CLI는
     **exit 0이고 `settings.json`에 키를 만든다**(`{"ghost@smoke-mkt": false}` — 2장).
     설치 기록은 만들지 않으므로 그 결과는 **유령 키**다. `_set_value`가 그것을 재현하고
     `test_enable_and_disable_on_an_unknown_plugin_create_a_ghost_key`가 고정한다.
     **하네스가 이것을 무해한 no-op으로 흉내 내던 동안 복원 3단계의 위험이 보이지
     않았다** — 그 위험 자체는 그 테스트의 docstring에 적었다.
  5. **[실측]** `prune`의 exit code는 **언제나 0**이다(`Nothing to prune…` — 5장).
     N3의 `-y` 요구가 `prune`에도 걸리는 갈래는 여전히 재지 않았고, 여기서는 `-y`
     개념이 없다.
  6. **[실측 — 추정이 틀렸다]** `marketplace add`가 만드는 **값의 모양**. 이 에뮬레이터는
     언제나 github 출처로 쓴다. 실제 CLI는 **인자에서 출처 종류를 판별한다** — 디렉토리
     경로를 주면 `directory` 출처로 쓴다(2장). 초판이 *"그럴 것"*이라 적어 둔 것이 그대로
     확인됐다. url·git 출처를 복원하는 시나리오를 쓸 때 이 자리를 먼저 고칠 것.
  7. **[실측]** directory 출처 값의 모양(`set_directory_marketplace`)은
     `{"source": {"source": "directory", "path": "<절대경로>"}}`다 — **가정과 정확히
     같았다**(2장). `plugin_config._source_kind`가 읽는 형태다.
  8. **[미확인]** `install`이 **다른 스코프 항목을 보존하는가**(`_mark_installed`). N4는
     배열의 존재와 항목의 필드를 쟀을 뿐, `install --scope user`가 project 스코프 항목을
     건드리지 않는다는 것은 재지 않았다. 스모크도 **스코프 하나만** 세워 닫지 못했다.
  9. **[실측]** **이미 설치된** 플러그인의 **객체 값**을 bare `install`이 **`true`로
     평탄화한다**(2장). 1-c C1과 spec 1.2의 표는 네 행뿐이었고 — 배열/미설치·배열/재실행·
     객체/미설치·건드리지 않음 — **객체/재실행 행이 없었다.** 이 에뮬레이터는 설치 여부로
     분기하지 않으므로 측정된 객체/미설치 행과 같은 결과를 냈고, 그 결과가 맞았다.
 10. **[미확인]** `marketplace remove`의 **소속 판정 규칙**(`pid.endswith("@" + name)`).
     1-b #8은 소속 플러그인이 전부 사라진다는 **결과**만 쟀지 소속을 무엇으로 판정하는지는
     재지 않았다. 스모크도 그 마켓플레이스에 **플러그인이 하나뿐**이라 규칙을 가를 입력이
     없었다. `plugin_config.marketplace_of`는 `@`가 정확히 하나일 때만 마켓플레이스를
     알아보므로 `a@b@m` 같은 id에서 두 규칙이 갈린다.
 11. **[실측]** **삭제 명령의 실패 갈래가 두 파일 어느 쪽도 건드리지 않는다**(`uninstall`·
     `marketplace_remove`의 exit 1 갈래). 1-b #6·#8이 잰 것은 "재실행은 exit 1"까지였다.
     스모크가 `uninstall ghost`(미설치)를 내고 **두 파일이 불변**임을 읽었다(2장).
     `marketplace_remove`의 실패 갈래는 재지 않았으나 같은 규율을 폈다.

**미확인 셋을 닫는 방법**(다음 스모크에 인계): 마켓플레이스 하나에 플러그인 **둘**을 두고
(→ 10번), 그중 하나에 `--config`로 `pluginConfigs`를 채운 뒤 `marketplace remove`를 내고
(→ 1번), `--scope project`로 한 벌 더 설치해 두고 `--scope user`로 재설치한다(→ 8번).

**목록에 없던 것 하나가 저장소 안에서 이미 반증돼 있었다.** *"이미 설치된 id에 bare
install을 내면 exit 1로 죽는다"*는 문장이 프로덕션 산문 여러 곳에 있었는데, 브리프 1-b
**#2가 2026-08-24에 이미 `exit 0`, `Plugin "x" is already installed`로 쟀다**(스모크가
2026-08-29에 재확인했다). 이 에뮬레이터의 `install`은 처음부터 exit 0이었으므로 어긋나 있던
것은 산문 쪽이다. 그 정정은 `plan_plugins.build_plan`·`sync-restore/SKILL.md` 5-2에 있다.

**재현하지 않는 것(의도).** `install --scope project|local`(이 동기화는 전부 user
스코프다 — spec 9.3.1), `plugin update`, `plugin tag`, `uninstall --keep-data`,
`~/.claude/plugins/cache/`(1-b #13 — uninstall 후에도 남는다. 한 플러그인의 버전
디렉토리가 여럿 쌓인다는 것은 1-c "그 밖에 기록해 둘 표면"이다),
`known_marketplaces.json`(1-b #9·N4 — 기기별 절대 경로 `installLocation`이
들어 있어 동기화 대상이 될 수 없다), `installed_plugins.json` 항목의 **다섯 필드**
(`installPath`·`version`·`installedAt`·`lastUpdated`·`gitCommitSha` — N4는 `scope`·`auto`와
함께 일곱을 쟀는데 여기서는 둘만 쓴다. `read_installed`가 나머지를 읽지 않아 판정은
갈리지 않지만, 그래서 이 하네스는 **실기기 모양의 `installed_plugins.json`을 한 번도
통과시키지 않는다**), 그리고 **`install`의 실패 갈래 둘**(1-b #3 미등록
마켓플레이스 · #4 없는 플러그인 — 둘 다 **exit 1을 실측**했으나 여기서는 언제나 0이다).
마지막 것은 추정이 아니라 의도적 미재현이다. #3의 **결과**(등록 실패 → 소속 플러그인
미설치)는 `Device.restore`의 `fail_marketplaces`가 층을 바꿔 흉내낸다 — 그 필터는
2·3단계뿐 아니라 **4단계에도** 걸린다(9.3.2: 4단계도 `plugin install <id@marketplace>
--config k=v` 형태라 등록되지 않은 마켓플레이스로는 똑같이 죽고, 그래서
`plan_plugins._install_dependencies`가 `depends_on`에 2단계∪4단계를 싣는다).
`test_a_blocked_marketplace_stops_the_install_and_config_steps`가 그중 **2·4단계를**,
`test_a_blocked_marketplace_stops_the_disable_step`이 **3단계를** 잰다. 3단계가 두 번째
테스트를 따로 요구하는 것은 첫 테스트의 픽스처에서 `disable_after_install`이 비어 **3단계
루프가 한 번도 돌지 않기** 때문이다(실측). 3단계를 관측하려면 **네 조건이 함께** 필요하다 —
레포 값이 `false` · `pluginConfigs`로 candidates에 들어옴 · **이미 설치됨** · **그
마켓플레이스의 1단계 등록이 실패함**. 넷째가 빠지면 `blocked`가 비어 필터가 애초에
동작하지 않고, 거기에 secret까지 주어지면 3단계가 낸 `disable`을 4단계의
`install --config`가 곧바로 되돌린다 — 어느 쪽이든 필터 유무가 값에 나타나지
않는다(실측).
셋째가 필요한 것은 그 id가 `install`(2단계)이 아니라 `skipped_already_installed`로 가야
이 픽스처가 **3단계 판이기 때문**이다(`plan_plugins.py:208-212`가 그 상황을 적는다).
*초판은 그 사유를 "미설치 id에는 `disable`이 exit 1로 아무것도 쓰지 않으므로"라고 적었다 —
**위 4번의 정정으로 거짓이 됐다.** 실제 CLI는 그때 `false` 키를 만든다.*
#4에는 대역이 없다 — 없는 플러그인을 설치하려는 계획을
만드는 시나리오를 쓸 때 이 자리를 먼저 고칠 것.

**이 하네스가 재현하지 못하는 위험 하나**(4번의 정정에서 나왔다): `install`이 언제나
exit 0이므로 **2단계가 실패한 id에 3단계가 `disable`을 내는 갈래**를 이 저장소 안에서는
만들 수 없다. 실제 CLI에서 그 갈래는 유령 키를 만들고, 레포 값도 `false`이므로 다음
백업이 그것을 in_sync로 읽어 base를 전진시킨다 — spec 10.4의 *"실패한 항목은 로컬에
없으니 자동으로 빠진다"*가 거기서는 참이 아니다. `install`의 실패 갈래를 재현하기로
결정하면(위 "재현하지 않는 것"의 #4) 그때 이 시나리오를 함께 세울 것.
"""
import json
import os

_ABSENT = object()   # 「키 부재」와 「값이 None」을 가르는 표식 (_set_value)


class PluginCLI:
    """임시 HOME 하나에 대한 claude plugin 명령. 반환값은 exit code다.

    **생성자가 두 파일을 초기화한다.** 같은 HOME에 두 번 만들면 이전 상태가 지워지므로
    기기 하나당 한 인스턴스만 만든다.
    """

    def __init__(self, home):
        self.home = home
        self.settings_path = os.path.join(home, ".claude", "settings.json")
        self.installed_path = os.path.join(home, ".claude", "plugins",
                                           "installed_plugins.json")
        self.held_path = os.path.join(home, ".claude", ".sync-state", "plugins-held.json")
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.installed_path), exist_ok=True)
        # **픽스처 결정이지 CLI 동작이 아니다.** 1-b #3은 실제 CLI가 실패했을 때
        # settings.json을 "만들지도 않는다"고 기록한다 — 즉 이 파일의 존재를 CLI가
        # 보장하지 않는다. 여기서 미리 만드는 것은 명령 메서드가 읽기-수정-쓰기만
        # 하도록 두어 각 메서드의 근거를 1-b 항목 하나에 묶어 두기 위해서다.
        # 파일 부재 자체를 재는 시나리오는 이 인스턴스를 쓰지 말고 직접 지울 것
        # (test_plugin_cycle.py의 skipped 계열이 그렇게 한다).
        self._write(self.settings_path, {"enabledPlugins": {}, "extraKnownMarketplaces": {},
                                         "pluginConfigs": {}})
        # N4 — installed_plugins.json은 자체 "version": 2 스키마를 갖고, plugins[<id>]가
        # 배열이다. plugin_config.read_installed가 그 형태를 요구한다.
        self._write(self.installed_path, {"version": 2, "plugins": {}})
        self._manifests = {}        # 플러그인 id → plugin.json의 dependencies 배열

    # --- 파일 ---
    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)

    def settings(self):
        return self._read(self.settings_path)

    def installed(self):
        return self._read(self.installed_path)

    # --- 픽스처 (CLI 명령이 아니다) ---
    def set_enabled(self, plugin_id, value):
        """테스트가 확장 포맷 값을 심을 때 쓴다. CLI 명령이 아니다.

        installed_plugins.json에도 함께 넣는 것은 C1 표의 왼쪽 열("그 값이 이미 있는
        플러그인")을 만들기 위해서다 — 값만 심고 설치 기록을 빼면 그 항목이
        read_installed의 installed_ids에서 빠져 restore의 2단계/4단계 분리가 어긋난다.
        """
        data = self.settings()
        data["enabledPlugins"][plugin_id] = value
        self._write(self.settings_path, data)
        self._mark_installed(plugin_id, auto=False)

    def set_manifest(self, plugin_id, dependencies=()):
        """플러그인 매니페스트(`plugin.json`)의 `dependencies`. CLI 명령이 아니다.

        **명령의 인자가 아니라 플러그인 자신의 내용이다**(N1). 그래서 `install`이 인자로
        받지 않고 여기서 읽는다 — 인자로 받으면 같은 부모를 설치하는 모든 호출부가 그
        배열을 기억해야 하고, 잊으면 자식이 조용히 딸려오지 않는다. 특히
        `Device.restore`의 2단계는 `install(plugin_id)`로만 부르므로, 인자 형태에서는
        **복원 경로에서 의존성 끌어오기가 영영 표현되지 않는다**(spec 9.3.1).
        """
        self._manifests[plugin_id] = list(dependencies)

    def set_directory_marketplace(self, name, path):
        """로컬 디렉토리 출처를 심는다 (H2). CLI 명령이 아니라 픽스처다.

        `marketplace add <경로>`의 **결과**이지만 `marketplace_add`와 나누어 둔 것은
        복원 경로가 이 갈래에 도달하지 않기 때문이다 — directory 출처는 H2로 보류되고
        (`plugin_config.directory_marketplaces`), `plugin_config.marketplace_arg`의
        docstring이 *"directory 출처는 여기 오지 않는다"*로 못 박는다. 즉 이 값은 계획이
        만들어 주지 않고 테스트가 직접 심어야 하는 로컬 상태다.

        1-b의 픽스처가 로컬 디렉토리 마켓플레이스였으므로 이 출처는 실재한다. 값의 모양은
        브리프에 기록돼 있지 않아 추정이었고, 스모크가 **가정과 정확히 같음을 확인했다** —
        **실측**(모듈 docstring 7번). `plugin_config._source_kind`가 읽는 형태다.
        """
        data = self.settings()
        data["extraKnownMarketplaces"][name] = {
            "source": {"source": "directory", "path": path}}
        self._write(self.settings_path, data)
        return 0

    # --- installed_plugins.json ---
    def _mark_installed(self, plugin_id, auto):
        """user 스코프 항목 하나를 갈아 끼운다 (N4 — 항목은 스코프별 배열이다).

        다른 스코프 항목은 보존한다. read_installed가 user 스코프만 보고 auto·설치를
        판정하므로(spec 3.4), 그 필터가 실제로 필터로 동작하는 입력을 만들 수 있어야 한다.
        보존 자체는 **실측 없음 — 추정**(모듈 docstring 8번): N4는 배열의 존재와 항목의
        필드를 쟀을 뿐 다른 스코프 항목의 운명은 재지 않았고, 2026-08-29 스모크도
        **스코프 하나만** 세워 닫지 못했다.
        """
        data = self.installed()
        entries = [e for e in data["plugins"].get(plugin_id, [])
                   if e.get("scope") != "user"]
        entries.append({"scope": "user", "auto": auto})
        data["plugins"][plugin_id] = entries
        self._write(self.installed_path, data)

    def _forget_installed(self, plugin_id):
        """설치 기록을 지운다. **실측**(모듈 docstring 2번)."""
        data = self.installed()
        data["plugins"].pop(plugin_id, None)
        self._write(self.installed_path, data)

    # --- 명령 ---
    def install(self, plugin_id, config=None):
        """키를 true로. **단 기존 값이 배열이면 보존**하고 객체는 평탄화한다 (1.2).

        이미 설치돼 있어도 exit 0(멱등). 명시적 설치는 auto 표식을 지운다(N6) —
        되돌릴 수 없다. config는 **부분 병합**이다(N2). 의존성은 매니페스트에서 읽는다
        (`set_manifest`) — 명령의 인자가 아니다.

        근거: C1 표(배열은 미설치·재설치 양쪽에서 보존, 객체는 `true`로 평탄화),
        1-b #2(멱등, exit 0), N2(`--config`가 pluginConfigs[id]["options"]에 평문 저장,
        지정하지 않은 키는 보존), N1(`dependencies` 배열의 자식이 직접 설치와 **똑같은
        모양**으로 enabledPlugins에 들어가고 구별 수단은 auto 플래그 하나뿐),
        N6(명시적 설치가 auto를 지운다).

        값이 `false`인 항목의 재설치가 `true`가 되는 것은 **실측**(모듈 docstring 3번),
        **이미 설치된** 항목의 객체 값이 `true`로 평탄화되는 것도 **실측**
        (모듈 docstring 9번)이다. 둘 다 2026-08-29 스모크가 닫았다.
        """
        dependencies = self._manifests.get(plugin_id, ())
        data = self.settings()
        current = data["enabledPlugins"].get(plugin_id)
        if not isinstance(current, list):
            data["enabledPlugins"][plugin_id] = True
        if config:
            entry = data["pluginConfigs"].setdefault(plugin_id, {})
            options = entry.setdefault("options", {})
            options.update(config)
        for child in dependencies:
            # N1 — 자식은 직접 설치와 구별되지 않는 모양으로 들어간다. 이미 값이 있으면
            # 건드리지 않는다(C1 표의 "그 플러그인을 건드리지 않음" 행).
            if child not in data["enabledPlugins"]:
                data["enabledPlugins"][child] = True
        self._write(self.settings_path, data)
        self._mark_installed(plugin_id, auto=False)
        for child in dependencies:
            # 이미 설치 기록이 있는 자식은 그대로 둔다 — N6의 "부모만 설치하면 자식이
            # auto: true인 채로 따라온다"의 반대편이다. 수동 설치를 auto로 되돌리는
            # 경로는 실측에 없다.
            if child not in self.installed()["plugins"]:
                self._mark_installed(child, auto=True)
        return 0

    def enable(self, plugin_id):
        return self._set_value(plugin_id, True)

    def disable(self, plugin_id):
        return self._set_value(plugin_id, False)

    def _set_value(self, plugin_id, value):
        """값만 변경한다. **이미 그 상태면 exit 1.**

        1-b #5 — `disable`/`enable`은 키를 유지한 채 값만 true↔false로 바꾸고,
        **멱등이 아니다**(이미 그 상태면 exit 1, `already disabled`).

        **현재 상태의 판정은 `is True` 하나다**(2026-08-29 스모크 3장 — 실측).
        CLI는 **비불리언 값을 「꺼짐」으로 읽는다**: `["1.0.0"]`·`{"version": …}`에
        `disable`을 내면 exit 1(`already disabled`)로 **값이 보존되고**, `enable`을 내면
        exit 0으로 **`true`가 덮어써 값이 사라진다.** 이것이 spec 7.3의 H3(값 보류)와
        `value_command`가 비불리언 레포 값에 언제나 `None`을 돌려주는 근거다 —
        명령을 낼 수 있는 방향은 값을 파괴하는 쪽뿐이다.

        **키가 아예 없으면 그 규칙 밖이다**(같은 문서 2장 — 추정 4번의 정정, 실측).
        미설치 id에 `disable`을 내면 exit 1이 아니라 **exit 0이고 키를 만든다**
        (`{"ghost@smoke-mkt": false}`). 즉 「부재」는 「꺼짐」과 같지 않다.
        측정된 것은 `disable` 방향이고 `enable` 방향은 대칭으로 둔다 — 이 에뮬레이터가
        둘을 한 메서드로 두는 한 갈라 둘 근거가 없다.

        **설치 기록은 만들지 않는다.** 스모크가 읽은 것은 `settings.json`의 키 하나뿐이고
        `installed_plugins.json`에 항목이 생겼다는 기록은 없다. 그래서 이 명령이 만드는
        것은 **설치 기록 없는 유령 키**다 — 복원 3단계가 미설치 id에 `disable`을 내면
        다음 백업의 next_base가 그 키를 전진시킨다.
        """
        data = self.settings()
        current = data["enabledPlugins"].get(plugin_id, _ABSENT)
        if current is not _ABSENT and (current is True) == value:
            return 1
        data["enabledPlugins"][plugin_id] = value
        self._write(self.settings_path, data)
        return 0

    def uninstall(self, plugin_id):
        """enabledPlugins·pluginConfigs에서 **키를 삭제**한다. 없으면 exit 1.

        1-b #6 — 활성·비활성 상태와 무관하게 키를 지우고 pluginConfigs의 같은 키도
        함께 지운다. 재실행은 exit 1(`not found in installed plugins`).
        설치 기록 삭제는 **실측**(모듈 docstring 2번).
        실패 갈래가 두 파일 어느 쪽도 건드리지 않는 것도 **실측**(모듈 docstring 11번) —
        스모크가 `uninstall ghost`(미설치)에서 두 파일의 불변을 읽었다.
        """
        data = self.settings()
        if plugin_id not in data["enabledPlugins"]:
            return 1
        data["enabledPlugins"].pop(plugin_id)
        data["pluginConfigs"].pop(plugin_id, None)
        self._write(self.settings_path, data)
        self._forget_installed(plugin_id)
        return 0

    def marketplace_add(self, name, source):
        """멱등. exit 0. source는 marketplace_arg가 만든 문자열이다.

        1-b #7 — 재실행도 exit 0(`Marketplace 'x' already on disk`).
        1-b #10 — `autoUpdate`를 설정하는 옵션이 CLI에 **없으므로** 여기서도 쓰지 않는다.
        값의 모양이 **언제나 github인 것은 이 에뮬레이터의 단순화다** — 실제 CLI는 인자
        하나에서 출처 종류를 판별한다(**실측**, 모듈 docstring 6번: 디렉토리 경로를 주니
        `directory` 출처로 썼다). 그래서 directory 갈래는 여기가 아니라 픽스처
        (`set_directory_marketplace`)가 심는다. **이 메서드에 경로를 넘기면 조용히 github
        출처가 된다** — url·git 출처도 마찬가지이므로 6번을 먼저 고칠 것.
        """
        data = self.settings()
        data["extraKnownMarketplaces"][name] = {
            "source": {"source": "github", "repo": source}}
        self._write(self.settings_path, data)
        return 0

    def marketplace_remove(self, name):
        """**소속 플러그인 키를 연쇄 삭제한다** — restore가 이 명령을 실행하지 않는 이유다.

        1-b #8 — 그 마켓플레이스 소속 플러그인이 enabledPlugins에서 전부 사라지고,
        비대화형에서 확인 프롬프트 없이 즉시 수행된다. 재실행은 exit 1.
        `extraKnownMarketplaces`·`enabledPlugins`·`installed_plugins.json` 셋 모두에서
        소속 항목이 사라지는 것은 **실측**(모듈 docstring 2번)이다.
        pluginConfigs 연쇄는 **실측 없음 — 추정**(모듈 docstring 1번).
        소속 판정 규칙(`endswith`)도 **실측 없음 — 추정**(모듈 docstring 10번).
        실패 갈래가 두 파일 어느 쪽도 건드리지 않는 것도 **실측 없음 — 추정**
        (모듈 docstring 11번) — 스모크가 잰 것은 `uninstall`의 실패 갈래뿐이다.
        """
        data = self.settings()
        if name not in data["extraKnownMarketplaces"]:
            return 1
        data["extraKnownMarketplaces"].pop(name)
        doomed = [pid for pid in data["enabledPlugins"] if pid.endswith("@" + name)]
        for plugin_id in doomed:
            data["enabledPlugins"].pop(plugin_id)
            data["pluginConfigs"].pop(plugin_id, None)
        self._write(self.settings_path, data)
        for plugin_id in doomed:
            self._forget_installed(plugin_id)
        return 0

    def prune(self):
        """부모가 사라진 auto 항목을 제거한다.

        N1 — `uninstall epsilon` 후에도 zeta는 enabledPlugins에 남고 `prune`이 그때서야
        `no longer needed`로 잡는다. N6 — 명시적으로 설치돼 auto가 지워진 항목은
        부모를 지워도 `Nothing to prune`이다(아래 auto 조건이 그것이다).

        부모 관계는 실제 CLI와 같은 자리 — 매니페스트의 `dependencies` — 에서 읽는다
        (`set_manifest`). exit code가 언제나 0인 것은 **실측**(모듈 docstring 5번)이다.
        N3의 `-y` 요구가 이 명령에도 걸리는지는 여전히 재지 않았고, 여기서는 `-y` 개념이
        없다.
        """
        data = self.settings()
        installed = self.installed()["plugins"]
        removed = []
        for plugin_id, entries in list(installed.items()):
            auto = any(e.get("scope") == "user" and e.get("auto") is True for e in entries)
            parents = [p for p, children in self._manifests.items()
                       if plugin_id in children and p in data["enabledPlugins"]]
            if auto and not parents:
                removed.append(plugin_id)
        for plugin_id in removed:
            data["enabledPlugins"].pop(plugin_id, None)
            data["pluginConfigs"].pop(plugin_id, None)
        self._write(self.settings_path, data)
        for plugin_id in removed:
            self._forget_installed(plugin_id)
        return 0
