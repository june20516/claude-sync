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
| 9 | 이미 설치된 것의 **객체 값**을 `install`이 어떻게 하는가 | bare `install`이 **`true`로 평탄화한다** | 측정됨 |
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
