# 실환경 스모크 실측 — spec 14.5

- 측정: 2026-08-29
- CLI: `claude` **2.1.250** (Claude Code)
- 방법: **임시 HOME**(`HOME=<tmp>`)에 로컬 디렉토리 마켓플레이스 하나와 플러그인 하나(`demo@smoke-mkt`)를
  세우고 명령별로 `settings.json`·`installed_plugins.json`을 읽었다. **실제 `~/.claude`와 sync 레포는
  건드리지 않았다.**
- 배경: 이 측정은 plan ②의 **비목표**였다(plan 본문 착수 표). 그 유예의 대가가 감사에서 드러났다 —
  Task 11·12·13이 쌓은 검증 층 1,891줄이 이 표가 채웠어야 할 **추정** 위에 서 있었다.

---

## 1. spec 14.5가 물은 셋

| # | 물음 | 실측 |
|---|---|---|
| 1 | CLI가 "확장 포맷"으로 의도한 형태는 배열인가 객체인가 | **둘 다 아니다 — 이 버전은 확장 값을 만들지 않는다.** `install <id>@<mkt>@1.0.0`도 `true`를 쓴다. 배열·객체는 CLI가 **읽기는 하되 쓰지는 않는** 형태다 |
| 2 | 객체 평탄화는 정규화인가 손실인가 | **손실이다.** `enable`이 배열·객체를 **`true`로 갈아엎는다**(아래 3장) |
| 3 | `install`의 기본 스코프 | **`user`.** `--scope <scope> … (default: "user")` — help 원문 |

---

## 2. 에뮬레이터 추정 열하나의 판정

`tests/plugin_cli.py`의 모듈 docstring이 선언한 추정을 하나씩 대조했다.

| 추정 | 에뮬레이터가 가정한 것 | 실측 | 판정 |
|---|---|---|---|
| 1 | `marketplace remove`가 `pluginConfigs`까지 지운다 | `uninstall`이 지우는 것은 확인. `marketplace remove` 시점에 `pluginConfigs`가 비어 있어 **직접 확인 못 함** | 미확인 |
| 2 | 세 삭제 명령이 `installed_plugins.json` 항목을 지운다 | `uninstall`·`marketplace remove` 둘 다 **지운다** | **맞음** |
| 3 | `false`인 항목에 bare `install` → `true` | **`true`** | **맞음** |
| 4 | 미설치 id에 `enable`/`disable` → **exit 1, 아무것도 안 씀** | **exit 0이고 키를 만든다** (`ghost@smoke-mkt: false`) | **틀림** |
| 5 | `prune`의 exit code는 언제나 0 | **0** (`Nothing to prune…`) | **맞음** |
| 6 | `marketplace add`가 언제나 github 모양을 쓴다 | **인자에서 출처를 판별한다** — 디렉토리 경로를 주니 `directory` 출처로 썼다 | **틀림**(선언돼 있던 것) |
| 7 | directory 출처의 값 모양 | `{"source": {"source": "directory", "path": "<절대경로>"}}` — **가정과 정확히 같다** | **맞음** |
| 8 | `install`이 다른 스코프 항목을 보존한다 | 스코프 하나만 써서 **미측정** | 미확인 |
| 9 | 이미 설치된 것의 **객체 값**을 `install`이 어떻게 하는가 | **배열과 객체가 다르다** — bare `install`은 배열을 **보존**하고 객체만 **`true`로 평탄화**한다(재측정) | 측정됨 |
| 10 | `marketplace remove`의 소속 판정 규칙(`endswith`) | 소속 플러그인이 하나뿐이라 **규칙 자체는 미측정** | 미확인 |
| 11 | 삭제 명령의 실패 갈래가 두 파일 어느 쪽도 안 건드린다 | `uninstall ghost`(미설치) → exit 1, **상태 불변** | **맞음** |

**추가로 목록에 없던 것 하나 — 틀린 것은 에뮬레이터가 아니라 산문이었다:**

| | 실측 | 저장소는 뭐라고 적고 있었나 |
|---|---|---|
| `install` 재실행(이미 설치) | **exit 0** — `✔ Plugin "…" is already installed` | 에뮬레이터의 `PluginCLI.install`은 **처음부터 exit 0**이었다(브리프 1-b #2가 2026-08-24에 이미 그렇게 쟀다). **exit 1이라고 적고 있던 것은 프로덕션 산문 다섯 곳**이다 — `plan_plugins.py`(3), `plugin_config.py`, `sync-restore/SKILL.md`. spec 8.6 표(1004행)도 그렇다 |

*(이 표의 초판은 "에뮬레이터가 exit 1"이라고 적었다. 반영 작업에서 코드를 직접 돌려
확인한 결과 그렇지 않았고, 그 오기는 정정된 산문에서 옮겨온 것이었다.)*

---

## 3. 확장 값의 의미 — 이 스모크의 가장 무거운 결과

**CLI는 비불리언 값을 「꺼짐」으로 읽는다.** 네 값을 각각 심고 잰 결과:

| settings의 값 | `enable` | `disable` |
|---|---|---|
| `true` | exit 1 (already enabled) | exit 0 → `false` |
| `false` | exit 0 → `true` | exit 1 (already disabled) |
| `["1.0.0"]` | **exit 0 → `true`** (값 파괴) | **exit 1 (already disabled)**, 값 보존 |
| `{"version":"1.0.0"}` | **exit 0 → `true`** (값 파괴) | **exit 1 (already disabled)**, 값 보존 |

귀결 둘:

1. **확장 값 = disabled.** 레포가 `{"p@m": ["1.0.0"]}`를 싣고 있으면 그것을 그대로 받은 기기에서 그
   플러그인은 **꺼진 상태**다. "버전을 고정한 켜짐"이 아니다.
2. **`enable`이 확장 값을 파괴한다.** 그래서 spec 7.3이 H3를 **값 보류**로 두고 `value_command`가
   비불리언 레포 값에 **언제나 `None`**을 돌려주는 것이 **옳다** — 명령을 내면 값이 사라진다.
   구현의 보수적 선택이 실측으로 뒷받침됐다.

**배열과 객체는 `install`에서 갈린다(재측정).** 3장의 표는 `enable`/`disable`을 잰 것이고,
bare `install`은 다르게 행동한다:

| 값 | bare `install` | 결과 |
|---|---|---|
| `["1.0.0"]` | exit 0 | **보존** — 배열 그대로 |
| `{"version":"1.0.0"}` | exit 0 | **`true`로 평탄화**(파괴) |

즉 파괴 경로는 **`enable`(배열·객체 둘 다)**과 **`install`(객체만)**이다. spec 1.2의 C1 표와
`tests/plugin_cli.py:244`가 이 비대칭을 처음부터 옳게 적고 있었다.

> **이 절의 초판은 9번 행을 "bare install이 true로 평탄화한다"로 단정했다. 그것은 재지 않고
> 추론한 것이고 배열에 대해 거짓이다.** 저장소 안에 이미 반증이 있었다 — spec 14.3 표
> (`design.md:1451`)가 *"단 기존 값이 배열이면 보존"* 이라고 적는다. 측정 문서가 spec과
> 어긋났는데 그 어긋남을 이 문서가 알아채지 못했다. **(b) 계열이고, 이번에는 측정 기록이
> 만들었다.**

---

## 4. plan ③으로 이월했던 미확인 ⑴ — **확정: 갈래 (ㄱ)**

> 한 id가 `disable_after_install`과 `config_keys`에 **함께** 실릴 수 있다(spec 9.3.1이 두 단계 모두
> "설치 여부로 좁히지 않는다"로 못 박는다). 그때 4단계가 3단계를 되돌리는가?

**되돌린다.** disabled 상태에서:

```
before: enabledPlugins={"demo@smoke-mkt": false}  pluginConfigs=null
$ claude plugin install demo@smoke-mkt --config token=s3cr3t     → exit 0
after : enabledPlugins={"demo@smoke-mkt": true}
        pluginConfigs={"demo@smoke-mkt":{"options":{"token":"s3cr3t"}}}
```

**에뮬레이터의 추정 3번이 옳았고, 따라서 이것은 하네스의 결함이 아니라 spec 9.3.1의 순서 규정에서
나오는 설계상의 귀결이다.** 레포의 `false`가 그 기기에 영영 복원되지 않고 다음 백업이 로컬 `true`를
도로 민다 — **수렴이 깨진다.** plan ③이 spec부터 고쳐야 하는 자리다(순서를 바꾸거나 4단계를 값
보존형으로).

`pluginConfigs`의 모양도 함께 확인됐다: `{id: {"options": {k: v}}}` — 구현과 일치.

---

## 5. 부수 실측

- `installed_plugins.json`은 `{"version": 2, "plugins": {id: [ {scope, installPath, version, installedAt,
  lastUpdated} ]}}`. **명시적 설치에는 `auto` 키가 아예 없다**(`false`가 아니라 부재).
- `marketplace add` 재실행 → **exit 0** (`already on disk`). 멱등하다.
- `marketplace remove` → `extraKnownMarketplaces`·`enabledPlugins`·`installed_plugins.json` **셋 모두**에서
  소속 항목이 사라진다. 재실행은 **exit 1**.
- `enable`/`disable`은 **멱등하지 않다**(같은 상태에 재실행하면 exit 1).
- `userConfig` 스키마는 `title`을 요구한다(없으면 `install --config`가 검증 실패로 exit 1).

---

## 6. 무엇을 고쳐야 하는가

| 자리 | 왜 |
|---|---|
| ~~`tests/plugin_cli.py`의 `install` 재실행 exit code~~ | **고칠 것이 없었다** — 에뮬레이터는 이미 exit 0이다. 고쳐야 했던 것은 아래 산문 행이다 |
| 같은 파일의 추정 4번(미설치 id에 `enable`/`disable`) | 실제로는 **exit 0이고 키를 만든다.** 복원 3단계가 미설치 id에 `disable`을 내면 **유령 키가 생긴다** |
| 추정 6번(marketplace add의 값 모양) | 인자로 출처를 판별한다 — url·git 시나리오 전에 고쳐야 한다는 인계가 **옳았고**, 형태도 확인됐다 |
| Task 14 인계의 *"bare install은 이미 설치된 id에 exit 1이라 애초에 대안이 아니다"* | **거짓.** exit 0이다. 2단계/4단계를 가른 결정 자체는 여전히 옳지만(중복 명령을 줄인다) **그 근거는 다시 써야 한다** |
| spec 8.6의 url·git "복원 가능" 서술 | 미측정 표식이 없다(감사 ②가 지적) |
| 추정 1·8·10 | 여전히 미확인 — 다음 스모크에서 마켓플레이스 하나에 플러그인 **둘**, 스코프 **둘**로 세우면 닫힌다 |

**구현(프로덕션)에서 고칠 것은 이 스모크에서 나오지 않았다.** 틀린 것은 전부 **에뮬레이터와 그 위에
쓰인 문장**이고, 프로덕션의 보수적 선택(H3를 값 보류로 두고 명령을 내지 않는 것)은 3장이 실측으로
뒷받침한다.

---

# 스모크 2차 (같은 날, 픽스처 확장)

마켓플레이스 하나(`m2`)에 플러그인 둘 — `alpha`(**`defaultEnabled: false`** + `userConfig`)와
`beta`(기본값). 스코프 둘, 그리고 github 출처 하나.

## 7. `install`의 실제 규칙 — "언제나 `true`"가 아니다

| 매니페스트 | 기존 값 | `install` 후 |
|---|---|---|
| `defaultEnabled: false` | (키 없음) | **`false`** |
| `defaultEnabled: false` | `false` | **`false` 유지** |
| `defaultEnabled: false` | `true` | **`true` 유지** |
| 기본값(=true) | (키 없음) | `true` |
| 기본값(=true) | `false` | **`true`로 뒤집힘** |
| 기본값(=true) | `["1.0.0"]` | **배열 보존** |
| 기본값(=true) | `{"version":"1.0.0"}` | `true` |

**규칙: `install`은 기존 값이 배열이면 보존하고, 그 외에는 「기존 값이 참이면 `true`, 거짓이거나 없으면 매니페스트의 `defaultEnabled`」를 쓴다.**

> **이 요약의 초판은 "그 외에는 `defaultEnabled`를 쓴다"였고 표 3행과 어긋났다.** 3행은
> `defaultEnabled: false` + 기존 `true` → **`true` 유지**인데 초판대로면 `false`여야 한다.
> 측정한 일곱 행은 전부 옳았고 **요약만 넓혔다** — 이 문서에서 같은 형태가 두 번째다(9번 행).
> 구현자가 요약이 아니라 **표를 따라 구현**해서 걸렀다.
1차가 "언제나 `true`"로 읽은 것은 픽스처의 `defaultEnabled`가 전부 기본값(true)이었기 때문이다.

### 귀결 셋

1. **`defaultEnabled: false` 걱정은 존재하지 않는다.** CLI가 설치 시 키를 **명시적으로** 쓰므로
   `local_masked.get(k, True)`의 기본값에 도달하는 경로가 없다(설치된 플러그인에 대해).
2. **4단계가 3단계를 되돌리는 것은 `defaultEnabled: true`인 플러그인에만 해당한다** — 다만
   `defaultEnabled`는 선택 필드이고 기본이 true이므로 **대다수가 여기 해당한다.**
3. **새로 드러난 것 — 3단계가 거짓 실패를 낼 수 있다.** 레포가 `false`이고 매니페스트도
   `defaultEnabled: false`인 미설치 id는, 계획이 `local_masked.get(k, True)`로 "켜져 있다"고
   추정해 `disable_after_install`에 싣는다. 그런데 2단계 install이 이미 `false`를 써 두므로
   3단계 `disable`은 **exit 1(already disabled)** 로 죽는다. 최종 상태는 옳지만 사용자는
   실패를 본다.

## 8. 나머지 추정 셋 — 전부 에뮬레이터가 맞았다

| 추정 | 실측 | 판정 |
|---|---|---|
| 1 `marketplace remove`가 `pluginConfigs`까지 지우는가 | 지운다 (`cfg={}`) | **맞음** |
| 8 `install`이 다른 스코프 항목을 보존하는가 | 보존 — `["project", "user"]` 둘 다 남음 | **맞음** |
| 10 `marketplace remove`의 소속 판정 | 소속 **둘 다** 사라짐(`en={}`·`inst=[]`) | **맞음**(false-positive 규칙 자체는 여전히 미측정) |

## 9. 마켓플레이스 출처의 값 모양

| 인자 | 기록된 값 |
|---|---|
| 디렉토리 절대경로 | `{"source": {"source": "directory", "path": "<절대경로>"}}` |
| `anthropics/claude-code` | `{"source": {"source": "github", "repo": "anthropics/claude-code"}}` |
| `https://github.com/anthropics/claude-code` | **같은 github 값으로 정규화** |

**github 왕복은 닫혔다** — `marketplace_arg`가 내는 `"o/r"`와 CLI가 쓰는 `repo` 필드가 일치한다.
**`url` 출처는 여전히 미측정**이다(https github URL이 github으로 정규화되므로, url 갈래는 raw
`.json` URL이나 비-github 호스트에서만 나온다). 틀린 것이 **에뮬레이터뿐일 가능성이 높다** —
실제 CLI가 인자로 출처를 판별한다는 것은 확인됐으므로 프로덕션은 정상 왕복할 수 있다.

## 10. CLI에 `configure` 서브커맨드가 없다

`claude plugin --help`의 명령 목록에 `enable`·`disable`만 있고 `configure`는 없다.
`/plugin configure`는 **세션 안 슬래시 명령**이라 스킬이 부를 수 없다 —
**"4단계를 값 보존형으로 바꾼다"는 선택지는 존재하지 않는다.**

---

# 스모크 3차 (2026-08-31, plan ③ 착수)

- CLI: `claude` **2.1.251** — 1·2차는 2.1.250이었다. **이 표들은 2.1.251에서 잰 것이다.**
- 방법: 같은 임시 HOME 기법. 실제 `~/.claude`와 sync 레포는 건드리지 않았고 측정 뒤
  **오염이 없음을 확인**했다(실제 홈의 마켓플레이스는 `claude-sync`·`planning-with-files`·`suberpower` 셋 그대로).
- 목적: KICKOFF 3장의 **측정 둘** — 추정 10번(`marketplace remove`의 소속 판정)과 `url` 출처의 왕복.
  둘 다 닫혔고, **`git` 출처까지 함께 닫혔다.**

## 11. 추정 10번 — `marketplace remove`의 소속 판정 규칙

픽스처: **이름이 서로의 접미인 마켓플레이스 둘.** `m`(플러그인 `alpha`)과 `sub-m`(플러그인 `beta`),
둘 다 디렉토리 출처·user 스코프. `"beta@sub-m"`은 `endswith("m")`·`includes("m")`에 걸리고
`endswith("@m")`에는 걸리지 않는다 — **규칙의 세 후보를 이 하나의 픽스처가 가른다.**

| `marketplace remove m` 이후 | 값 |
|---|---|
| `extraKnownMarketplaces` | `{"sub-m": …}` — `m`만 사라짐 |
| `enabledPlugins` | `{"beta@sub-m": true}` — **`alpha@m`만 사라짐** |
| `installed_plugins.json` | `{"beta@sub-m": [...]}` — 같음 |
| `~/.claude/plugins/cache/` | `m`·`sub-m` **둘 다 남는다** — 디스크 캐시는 지우지 않는다 |

**판정: 에뮬레이터의 `pid.endswith("@" + name)`이 맞다.** false-positive 규칙이 아니다.
`tests/plugin_cli.py`의 모듈 docstring 10번은 이제 **[미확인]이 아니라 실측**이다.

## 12. 추정 11번의 나머지 절반 — 삭제 명령의 실패 갈래

1차가 잰 것은 `uninstall ghost`뿐이었다. `marketplace remove`의 실패 갈래를 마저 쟀다.

| 명령 | exit | `settings.json` | `installed_plugins.json` |
|---|---|---|---|
| `marketplace remove ghost-mkt` (미등록) | **1** | 불변(바이트 동일) | 불변(바이트 동일) |

**판정: 맞음.** 추정 11번도 이제 실측이다.

## 13. `url`·`git` 출처 — 값의 모양과 왕복

로컬에 http 서버를 세워 쟀다(네트워크 없이 비-github 호스트를 만드는 유일한 길이다).
`url`은 `python3 -m http.server`가 낸 raw `.json`, `git`은 `git-http-backend`를 감싼
**smart HTTP** 서버다 — dumb HTTP로는 CLI의 shallow clone이 실패한다(아래 14장).

| 인자 | 기록된 값 | `marketplace_arg`가 낼 문자열 | 재등록 결과 |
|---|---|---|---|
| `http://127.0.0.1:8731/marketplace.json` | `{"source":{"source":"url","url":"http://127.0.0.1:8731/marketplace.json"}}` | `url` 필드 → 인자와 **동일** | **바이트 동일** |
| `http://127.0.0.1:8733/gitmkt.git` | `{"source":{"source":"git","url":"http://127.0.0.1:8733/gitmkt.git"}}` | `url` 필드 → 인자와 **동일** | **바이트 동일** |

**둘 다 왕복이 닫혔다.** 그리고 **`git` 출처의 필드는 `repo`가 아니라 `url`이다** —
`plugin_config.py`의 `_SOURCE_ARG_FIELDS = {"git": ("url", "repo")}`가 후보 둘을 순서대로
훑는데 **첫 후보가 옳았다.** (둘째 후보 `repo`는 이 실측으로는 도달 경로가 없다.
지울지 방어로 남길지는 plan ③이 정한다 — 지우면 `repo`만 가진 값이 조용히 unrestorable이 된다.)

## 14. `marketplace add`의 출처 분류 규칙 (관측된 전부)

| 인자 모양 | 판별된 출처 | 근거 |
|---|---|---|
| 절대 디렉토리 경로 | `directory` | 1차 스모크 7번 |
| `owner/repo` | `github` | 2차 스모크 9장 |
| `https://github.com/owner/repo` | `github`(정규화) | 2차 스모크 9장 |
| `http(s)://…/x.git` | **`git`** | 이 측정 — `Cloning repository (timeout: 120s)`를 찍고 shallow clone을 시도한다 |
| 그 밖의 `http(s)://…` | **`url`** | 이 측정 — 본문을 마켓플레이스 JSON으로 파싱한다 |
| `file://…` | **거부, exit 1** | `✘ Invalid marketplace source format. Try: owner/repo, https://..., or ./path` |
| `.git`으로 끝나는 **로컬 경로** | `directory` | `Marketplace file not found at <경로>/.claude-plugin/marketplace.json`으로 실패 |

**여전히 미측정: `https://github.com/o/r.git`.** github 정규화와 `.git` 규칙 중 어느 쪽이
이기는지는 네트워크 없이 잴 수 없다. **프로덕션에는 도달 경로가 없다** — `marketplace_arg`가
github 출처에 내는 것은 `repo` 필드(`"o/r"`)이지 URL이 아니다.

부수 실측 둘:

- **dumb HTTP git 서버로는 등록되지 않는다** — `fatal: dumb http transport does not
  support shallow capabilities`. CLI가 `--depth`를 쓴다는 뜻이다.
- 디렉토리 목록 HTML을 `url`로 주면 `Invalid marketplace schema from URL: : Invalid input:
  expected object, received string`으로 exit 1이고 **`extraKnownMarketplaces`에 키를 만들지 않는다.**

## 15. 이 측정이 고칠 것을 지목하는 자리

| 자리 | 무엇을 |
|---|---|
| `tests/plugin_cli.py` 모듈 docstring 10·11번 | **[미확인] → 실측.** 11장·12장이 근거다 |
| 같은 파일 `marketplace_remove`·`_forget_installed`의 docstring | *"소속 판정 규칙만 실측 없음"* 문장이 낡았다 |
| `tests/plugin_cli.py::_marketplace_source` | url·git 인자에 `NotImplementedError`를 던진다. **이제 실측된 모양이 있다** — 14장의 표대로 판별하게 고친다 |
| `lib/plugin_config.py`의 `_SOURCE_ARG_FIELDS` 주석 | *"url·git의 필드 이름은 측정되지 않았으므로"* 가 거짓이 됐다. 둘 다 `url`이다 |
| spec 8.6의 url·git "복원 가능" 서술 | 미측정 표식을 **실측 표식으로** 바꾼다 |
| spec 14.5 #3·#4 | #3(소속 판정)이 닫혔다. #4(`defaultEnabled`를 되읽는 파일)는 **여전히 미측정** |

**프로덕션에서 고칠 것은 이 스모크에서도 나오지 않았다** — `marketplace_arg`가 url·git에
내는 인자가 실측과 일치했다. 틀린 것은 **에뮬레이터 하나와 그것을 인용한 문장들**이다.

> **위 여섯 자리는 전부 닫혔다** (plan ③ Task 7, 2026-09-01). 에뮬레이터가 다섯 모양을
> 판별하고, 항목 10·11이 [실측]이 됐으며, `_SOURCE_ARG_FIELDS` 주석과 spec 8.6·14.3·14.5가
> 이 문서를 인용해 갱신됐다. **남은 미측정은 14.5의 #4~#7**이다 — `defaultEnabled`를 되읽는
> 파일(#4), `install --config`의 `defaultEnabled: false` 조합(#5), 그리고 이 스모크가 새로
> 세운 둘: `https://github.com/o/r.git`의 판별 순서(#6)와 `a@b@m` 꼴 id의 연쇄 삭제(#7).
