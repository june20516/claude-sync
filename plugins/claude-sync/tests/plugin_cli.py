"""`claude plugin` CLI 에뮬레이터 (spec 14.3).

**이 파일이 곧 CLI 동작의 정의가 된다.** 브리프 1-b의 실측표를 그대로 구현하지 않으면
교대 테스트가 아무것도 검증하지 않는다. 실측되지 않은 갈래는 주석에 그렇게 적는다.

두 파일을 모두 재현한다 — settings.json(값)과 installed_plugins.json(auto 플래그).
후자를 빼면 hold가 항상 빈 집합이 되어 **H1을 교대 테스트가 전혀 검증하지 못한다.**

**출처.** `docs/superpowers/2026-08-20-plugins-sync-followup-BRIEF.md`의
1-b 실측 결과 표(항목 #2~#13, `claude 2.1.241`), 그 아래 발견 N1·N2·N4·N6,
1-c의 C1(확장 포맷 값 표). 메서드마다 근거 항목 번호를 적어 둔다 — 실제 CLI가 바뀌었을 때
드리프트가 보이게 하려는 것이다. **명령 메서드에 번호가 없는 동작은 아래 목록에 있어야
한다**(파일 입출력 헬퍼는 CLI 동작이 아니라 근거가 없다).

**실측 없음 — 추정으로 채운 갈래 일곱.** 실제 CLI와 어긋날 수 있고, 어긋나도 이 저장소
안에서는 드러나지 않는다(에뮬레이터가 곧 기준이므로).

  1. `marketplace remove`가 `pluginConfigs`까지 지우는가. 1-b #8은 `enabledPlugins`에서
     사라진다는 것만 쟀다. #6(`uninstall`)이 두 필드를 함께 지우므로 같은 규율을 폈다.
  2. 세 삭제 명령이 `installed_plugins.json` 항목을 지우는가. N1은 "`uninstall epsilon`
     후에도 zeta가 남고 `prune`이 그때서야 잡는다"로 **부모 항목의 소멸을 함의**할 뿐,
     그 파일의 내용을 직접 재지 않았다.
  3. 값이 `false`인 플러그인을 다시 `install` 했을 때의 값. #2의 멱등성은 켜진 항목에서
     쟀고 C1 표는 배열·객체만 쟀다. 여기서는 `true`로 쓴다 — spec 8.4가 "로컬에 키가
     없다"에 대해 두는 가정과 같은 방향이다.
  4. 설치되지 않은 id에 `enable`/`disable`을 냈을 때. `_set_value` 주석 참조.
  5. `prune`의 exit code, 그리고 N3의 `-y` 요구가 `prune`에도 걸리는 갈래. 여기서는
     언제나 0이고 `-y` 개념이 없다.
  6. `marketplace add`가 만드는 **값의 모양**. 이 에뮬레이터는 언제나 github 출처로 쓴다.
     실제 CLI는 인자에서 출처 종류를 판별하므로 url·git 출처를 복원하는 시나리오에서
     차이가 드러난다. 그런 시나리오를 쓸 때 이 자리를 먼저 고칠 것.
  7. directory 출처 값의 모양(`set_directory_marketplace`). 1-b의 픽스처가 로컬 디렉토리
     마켓플레이스였으므로 그 출처 자체는 실재하지만, 브리프에 JSON 모양이 기록돼 있지
     않다. `plugin_config._source_kind`가 읽는 형태에 맞췄다.

**재현하지 않는 것(의도).** `install --scope project|local`(이 동기화는 전부 user
스코프다 — spec 9.3.1), `plugin update`, `plugin tag`, `uninstall --keep-data`,
`~/.claude/plugins/cache/`(1-b #13 — uninstall 후에도 남고 한 플러그인의 버전 디렉토리가
여럿 쌓인다), `known_marketplaces.json`(1-b #9·N4 — 기기별 절대 경로 `installLocation`이
들어 있어 동기화 대상이 될 수 없다).
"""
import json
import os


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
        self._write(self.settings_path, {"enabledPlugins": {}, "extraKnownMarketplaces": {},
                                         "pluginConfigs": {}})
        # N4 — installed_plugins.json은 자체 "version": 2 스키마를 갖고, plugins[<id>]가
        # 배열이다. plugin_config.read_installed가 그 형태를 요구한다.
        self._write(self.installed_path, {"version": 2, "plugins": {}})
        self._parents = {}          # 부모 → 의존성으로 끌려온 자식들

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

    # --- installed_plugins.json ---
    def _mark_installed(self, plugin_id, auto):
        """user 스코프 항목 하나를 갈아 끼운다 (N4 — 항목은 스코프별 배열이다).

        다른 스코프 항목은 보존한다. read_installed가 user 스코프만 보고 auto·설치를
        판정하므로(spec 3.4), 그 필터가 실제로 필터로 동작하는 입력을 만들 수 있어야 한다.
        """
        data = self.installed()
        entries = [e for e in data["plugins"].get(plugin_id, [])
                   if e.get("scope") != "user"]
        entries.append({"scope": "user", "auto": auto})
        data["plugins"][plugin_id] = entries
        self._write(self.installed_path, data)

    def _forget_installed(self, plugin_id):
        """설치 기록을 지운다. **실측 없음 — 추정**(모듈 docstring 2번)."""
        data = self.installed()
        data["plugins"].pop(plugin_id, None)
        self._write(self.installed_path, data)

    # --- 명령 ---
    def install(self, plugin_id, config=None, dependencies=()):
        """키를 true로. **단 기존 값이 배열이면 보존**하고 객체는 평탄화한다 (1.2).

        이미 설치돼 있어도 exit 0(멱등). 명시적 설치는 auto 표식을 지운다(N6) —
        되돌릴 수 없다. config는 **부분 병합**이다(N2).

        근거: C1 표(배열은 미설치·재설치 양쪽에서 보존, 객체는 `true`로 평탄화),
        1-b #2(멱등, exit 0), N2(`--config`가 pluginConfigs[id]["options"]에 평문 저장,
        지정하지 않은 키는 보존), N1(`dependencies` 배열의 자식이 직접 설치와 **똑같은
        모양**으로 enabledPlugins에 들어가고 구별 수단은 auto 플래그 하나뿐),
        N6(명시적 설치가 auto를 지운다).

        **값이 `false`인 항목의 재설치는 미측정이다**(모듈 docstring 3번) — 여기서는
        배열이 아니므로 `true`가 된다.
        """
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
        if dependencies:
            self._parents[plugin_id] = list(dependencies)
        return 0

    def enable(self, plugin_id):
        return self._set_value(plugin_id, True)

    def disable(self, plugin_id):
        return self._set_value(plugin_id, False)

    def _set_value(self, plugin_id, value):
        """값만 변경한다. **이미 그 상태면 exit 1.**

        1-b #5 — `disable`/`enable`은 키를 유지한 채 값만 true↔false로 바꾸고,
        **멱등이 아니다**(이미 그 상태면 exit 1, `already disabled`).

        설치되지 않은 id에 대한 동작은 미측정이다 — 여기서는 exit 1로 둔다.
        복원 흐름은 설치 뒤에만 부르므로 이 갈래에 의존하지 않는다.
        """
        data = self.settings()
        if plugin_id not in data["enabledPlugins"]:
            return 1
        if data["enabledPlugins"][plugin_id] == value:
            return 1
        data["enabledPlugins"][plugin_id] = value
        self._write(self.settings_path, data)
        return 0

    def uninstall(self, plugin_id):
        """enabledPlugins·pluginConfigs에서 **키를 삭제**한다. 없으면 exit 1.

        1-b #6 — 활성·비활성 상태와 무관하게 키를 지우고 pluginConfigs의 같은 키도
        함께 지운다. 재실행은 exit 1(`not found in installed plugins`).
        설치 기록 삭제는 추정이다(모듈 docstring 2번).
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
        값의 모양(항상 github)은 추정이다(모듈 docstring 6번).
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
        **pluginConfigs 연쇄는 추정이다**(모듈 docstring 1번).
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

    def set_directory_marketplace(self, name, path):
        """로컬 디렉토리 출처를 심는다 (H2). `marketplace add <경로>`의 결과다.

        1-b의 픽스처가 로컬 디렉토리 마켓플레이스였으므로 이 출처는 실재한다. 다만
        **값의 모양은 브리프에 기록돼 있지 않아 추정이다**(모듈 docstring 7번) —
        plugin_config._source_kind가 읽는 형태에 맞췄다.
        """
        data = self.settings()
        data["extraKnownMarketplaces"][name] = {
            "source": {"source": "directory", "path": path}}
        self._write(self.settings_path, data)
        return 0

    def prune(self):
        """부모가 사라진 auto 항목을 제거한다.

        N1 — `uninstall epsilon` 후에도 zeta는 enabledPlugins에 남고 `prune`이 그때서야
        `no longer needed`로 잡는다. N6 — 명시적으로 설치돼 auto가 지워진 항목은
        부모를 지워도 `Nothing to prune`이다(아래 auto 조건이 그것이다).

        부모 관계는 실제 CLI가 매니페스트의 `dependencies`에서 읽지만 여기서는 install이
        기록해 둔 것을 본다. exit code는 추정이다(모듈 docstring 5번).
        """
        data = self.settings()
        installed = self.installed()["plugins"]
        removed = []
        for plugin_id, entries in list(installed.items()):
            auto = any(e.get("scope") == "user" and e.get("auto") is True for e in entries)
            parents = [p for p, children in self._parents.items()
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
