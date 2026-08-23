# plugins.json 동기화 — 후속 작업 브리프

- 작성: 2026-08-20
- 상태: **3장 실측 완료(2026-08-24). spec 착수 가능.** plan은 아직 없다.
  실측 결과는 1-b·1-c에 있고 4장 결정표가 그것으로 채워졌다. **2장·6장의 일부 전제는 실측이 반증했다 — 본문에 표시했다.**
- 선행 작업: `fix/mcp-config-source` 브랜치 (PR #2), MCP 동기화 재설계 3.0.0
- 관련: `2026-08-21-version-compat-BRIEF.md` (버전 표식·가드 — 같은 결함의 다른 축)
- 등록 근거: `specs/2026-08-20-mcp-config-source-design.md` 15장 오픈 이슈
  — "`plugins.json`의 동일 결함을 후속 과제로 등록할지"

이 문서만 읽고 이어받을 수 있게 쓴다.

---

## 1. 무엇이 문제인가

`plugins.json`은 `~/.claude/settings.json`에서 `enabledPlugins`·`extraKnownMarketplaces`
두 필드만 뽑아 만드는 **파생 산출물**이다. 대응하는 로컬 파일(`~/.claude/plugins.json`)이
존재하지 않으므로 `iter_synced_relpaths`가 열거하지 못하고, 따라서 **파일 단위 3-way의
대상이 될 수 없다.** 의도적 배제가 아니라 구조적 사각지대다.

### 확인된 결함 3건

**(A) 백업이 통째로 덮어쓴다 — 기기 간 손실.**
`extract_plugins.py`가 매 백업마다 레포 파일을 새로 생성한다. 기기 B에만 설치된 플러그인이
기기 A의 백업에서 사라진다. `mcp-servers.json`이 이번에 고친 것과 **같은 결함**이다.

**(B) status가 켬/끔을 보지 못한다.**
`sync-status/scripts/check_status.py:63-65`가 `enabledPlugins`의 **키 집합만** 비교한다.

```python
rp = set(json.load(f).get("enabledPlugins", {}).keys())
lp = set(json.load(f).get("enabledPlugins", {}).keys())
```

`true` → `false`로 바뀌어도 차이로 보고되지 않는다. MCP Bug #2("이름만 비교해서 설정 변경을
놓친다")와 같은 계열이며, 이번 작업에서 MCP 쪽만 고쳤다.

**(C) 읽기 실패와 "플러그인 0개"를 구별하지 않는다.**
`extract_plugins.py`에는 예외 처리가 없다. `settings.json`이 없거나 깨지면 traceback으로
죽어 backup 흐름 전체가 중단된다. MCP는 `LocalConfigUnavailable` → `status: skipped` →
**종료 코드 0**으로 처리한다(불변식 2). 같은 규율이 적용되어 있지 않다.

### 히스토리 (왜 이렇게 됐나)

`specs/2026-06-10-git-like-sync-design.md` 4.4절이 플러그인/MCP를 파일 3-way에서 떼어내
**additive only**로 규정했다:

> 로컬에만 있는 플러그인/서버는 제거하지 않는다(non-destructive). **충돌 개념 없음(존재 여부만).**

restore 방향(로컬에서 사라질 일 없음)만 보면 일관된 선택이었으나, **backup 방향의 손실은
다루지 않았다.** 그 부작용이 어느 문서에도 적히지 않은 채 두 달간 유지되었고,
`README.ko.md`는 "로컬 파일은 절대 자동으로 덮어쓰지 않습니다"라고 실제보다 강한 보장을
약속하고 있었다. 2026-08-20 MCP 작업의 Task 11에서 한계를 문서에 명시했으나,
**동작은 그대로다.**

---

## 2. 선행 작업에서 그대로 가져올 것

새로 발명할 것이 많지 않다. MCP 작업의 산출물이 본이 된다.

| 자산 | 위치 | 재사용 방식 |
|---|---|---|
| 키 단위 3-way 판정표(케이스 1~10) | `lib/mcp_config.py` `merge` | 값에 무관 — 그대로 |
| base 전진 규칙 | `lib/mcp_config.py` `next_base` | 그대로 |
| 복원 버킷 분리(7·8·9) | `lib/mcp_config.py` `restore_plan` | 버킷 수만 줄여서 |
| 스테이징 계약 | `sync-backup/scripts/collect_mcp.py` | 그대로 (커밋 전 계산 → 스테이징 → 푸시 후 `update_base.py`) |
| base 기록 주체 | `sync-backup/scripts/update_base.py` | **새로 만들지 말 것.** 그대로 재사용 |
| 반복 적용 고정점 테스트 | `tests/test_mcp_state_machine.py` | 어댑터만 갈아끼우면 그대로 |
| 교대 시나리오 테스트 | `tests/test_mcp_cycle.py` | 하네스 구조 그대로 |

**`merge`·`next_base`·`restore_plan`은 `redact`·`secret_keys`·`restorable` 세 곳만 빼면
값에 무관하다.** 공용 코어 추출 여부가 3장 이후의 첫 설계 판단이 된다.

> **[2026-08-24 실측이 반증함]** 원문은 "플러그인은 그 셋이 전부 필요 없다(비밀 없음, 이름 규칙 없음)"고
> 적었으나 **셋 다 필요할 수 있다.**
> - `redact`·`secret_keys` — `settings.json`의 `pluginConfigs`에 `userConfig` 값이 **평문으로** 저장된다(1-b N2).
>   동기화 대상에 넣는 순간 마스킹이 필수다.
> - `restorable` — 등록 불가한 의사 출처 5개와 예약 이름 16개가 있어 "복원할 수 있는 항목인가" 판정이 필요하다(1-c C3).
>
> 따라서 "플러그인 어댑터의 정규화 = 항등함수"라는 전제로 코어 추출을 결정하면 안 된다.
> 오히려 **두 어댑터가 같은 훅을 쓰므로 추출의 근거가 강해졌다.**

---

## 3. 1단계 — 실측이 먼저다

**spec을 쓰기 전에 `claude plugin` CLI를 실측한다.** MCP 설계에서 `add-json`의 제약
(이름 규칙, 기존 이름 덮어쓰기 불가)은 실측으로 얻은 것이고, 그게 없었으면 설계가
틀렸을 것이다. 같은 이유로 여기서도 실측이 0순위다.

### 안전 규칙

- **먼저 임시 HOME으로 시도한다**: `HOME=$T claude plugin ...`.
  *임시 HOME에서 플러그인 설치가 되는지(인증이 필요한지) 자체가 측정 항목이다.*
- 임시 HOME이 불가하면 실제 환경에서 하되, **설치와 제거를 반드시 한 호출 안에서 짝지어
  실행한다**(MCP Task 13의 `trap cleanup EXIT` 방식).
- 측정 전 `cp ~/.claude/settings.json <백업>`, 측정 후 `diff`로 원복을 확인한다.
- 측정용 플러그인은 작고 안전한 것 하나로 고정한다.

### 측정 항목

| # | 무엇을 | 어떻게 | 기록할 것 |
|---|---|---|---|
| ~~1~~ | ~~CLI 표면~~ | **2026-08-21 확인 완료** — 아래 1-a 참조 | — |
| 2 | install 멱등성 | 이미 설치·활성인 플러그인에 `install` 재실행 | exit code, stderr 문구 |
| 3 | 마켓플레이스 미등록 상태의 install | 등록 없이 `install foo@bar` | 실패 방식(자동 등록? 에러?) |
| 4 | 없는 플러그인 install | 오타 이름 | exit code, stderr |
| 5 | **비활성화 수단** | `disable`/`enable` 하위 명령 존재 여부 | 없으면 `false` 상태를 CLI로 만들 수 없다 |
| 6 | **제거 수단** | `uninstall`/`remove` 존재 여부와 결과 | settings.json에서 **키가 사라지는가, `false`가 되는가** |
| 7 | marketplace add 멱등성 | 같은 마켓플레이스 재등록 | exit code |
| 8 | marketplace remove | 존재 여부, 실행 시 그 마켓플레이스의 플러그인은 어떻게 되는가 | 연쇄 효과 |
| 9 | **내장 마켓플레이스** | `claude-plugins-official`은 `extraKnownMarketplaces`에 **없다** | 등록 대상에서 빼야 할 내장 목록 전수 |
| 10 | `autoUpdate` 필드 | 언제 붙는가(`add` 옵션? 기본값?) | 동기화 대상에 넣을지 판단 근거 |
| 11 | settings.json 반영 시점 | install 직후 파일이 갱신되는가, 세션 재시작이 필요한가 | 복원 직후 다시 읽어도 되는지 |
| 12 | 동시 쓰기 | 실행 중인 세션이 settings.json을 덮어쓸 수 있는가 | 있으면 읽기-수정-쓰기 경합 대비 필요 |
| 13 | 목록 ↔ 실체 괴리 | `~/.claude/plugins/` 구조. 목록에 있는데 디렉토리가 없는 경우 / 그 반대 | "로컬 상태"의 정의를 무엇으로 할지 |

### 1-a. CLI 표면 — 확인 완료 (2026-08-21, `claude 2.1.237`)

`claude plugin` 하위 명령: `details` `disable` `enable` `eval` `init` `install` `list`
`marketplace` `prune|autoremove` `tag` `uninstall|remove` `update` `validate`.
`claude plugin marketplace`: `add` `list` `remove|rm` `update`.

여기서 곧바로 확정되는 것:

- **`disable`/`enable`이 존재한다** → `enabledPlugins`의 `false` 상태를 CLI로 만들 수 있다.
  4장 결정표의 "disable CLI 없음" 분기는 **폐기**한다. 3상태(true/false/부재)를 그대로 다룬다.
- **`uninstall|remove`가 존재한다** → 제거 수단이 있다. 다만 settings.json에서 **키가 사라지는지
  `false`가 되는지**는 여전히 측정 대상(항목 6)이다.
- **`marketplace remove`가 존재한다** → 마켓플레이스를 additive only로 고정할 필요가 없다.
- **`prune|autoremove`가 있다** → *플러그인 간 의존성이 실재한다.* 브리프에 없던 항목이며,
  삭제 전파 설계에서 "자동 설치된 의존 플러그인"을 어떻게 볼지 결정해야 한다. **(신규 측정 항목)**
- `install --scope user|project|local`, `install --config <key=value>`(플러그인 `userConfig`) →
  MCP와 같은 스코프 문제가 여기도 있고, 동기화 대상에 `userConfig`를 넣을지 판단이 필요하다. **(신규 측정 항목)**
- **버전 제약 개념이 없다.** `install`에 `--version`도 범위 문법도 없고 `update`는 "최신"이다.
  `plugin list`가 설치 버전을 보여주고 `plugin tag`가 `{name}--v{version}` 태그 규약을 갖는다.

9번은 이미 실제 데이터에서 드러났다 — `enabledPlugins`에 `swift-lsp@claude-plugins-official`이
있지만 `extraKnownMarketplaces`에는 `claude-plugins-official`이 없다. 의존성 검사에서
내장 마켓플레이스를 **항상 known으로 취급**하지 않으면 restore가 없는 마켓플레이스를
등록하려 든다.

### 1-b. 실측 결과 — 확정 (2026-08-24, `claude 2.1.241`)

**측정 방법.** 전량 임시 HOME(`HOME=$T claude plugin ...`)에서 수행했다. 첫 측정 항목이었던
"임시 HOME에서 플러그인 설치가 되는가"의 답은 **된다** — 인증 없이 모든 하위 명령이 동작한다.
따라서 실제 환경은 한 번도 건드리지 않았고, `~/.claude/settings.json`은 측정 전후 SHA-256이
동일함을 확인했다. 픽스처는 네트워크를 타지 않는 로컬 디렉토리 마켓플레이스 4개
(`testmkt-a`~`d`)와 플러그인 6개(alpha, beta, gamma, delta, epsilon, zeta)다.

| # | 항목 | 결과 |
|---|---|---|
| 2 | install 멱등성 | **멱등.** 재실행 exit 0, `Plugin "x" is already installed`, settings.json 불변 |
| 3 | 미등록 마켓플레이스 install | **자동 등록하지 않는다.** exit 1. settings.json을 만들지도 않는다 |
| 4 | 없는 플러그인 install | exit 1. **3번과 문구가 같다** — `Plugin "x" not found in marketplace "y"`. 마켓플레이스 부재와 플러그인 부재를 stderr로 구별할 수 없다. `@` 없이 이름만 주면 등록된 마켓플레이스에서 탐색해 설치한다(exit 0) |
| 5 | 비활성화 수단 | `disable`/`enable`이 **키를 유지한 채 값만 `true`↔`false`로 바꾼다.** 단 **멱등이 아니다** — 이미 그 상태면 exit 1(`already disabled`) |
| 6 | 제거 수단 | `uninstall`은 **`enabledPlugins`에서 키를 삭제한다.** 활성·비활성 상태 무관. `pluginConfigs`의 같은 키도 함께 지운다. 재실행은 exit 1(`not found in installed plugins`) |
| 7 | marketplace add 멱등성 | **멱등.** exit 0, `Marketplace 'x' already on disk` |
| 8 | marketplace remove | **연쇄 삭제한다.** 그 마켓플레이스 소속 플러그인이 `enabledPlugins`에서 **전부 사라진다.** 비대화형에서 확인 프롬프트 없이 즉시 수행된다. 재실행은 exit 1 |
| 9 | 내장 마켓플레이스 | `claude-plugins-official`은 `extraKnownMarketplaces`에 **없고** `~/.claude/plugins/known_marketplaces.json`에만 있다. 이 기기의 `enabledPlugins` 8개 중 5개가 이 마켓플레이스 소속이다 |
| 10 | `autoUpdate` 필드 | `extraKnownMarketplaces` 값에 **실재한다**(이 기기의 `claude-sync`·`suberpower`에 `true`). 그런데 **`marketplace add`에 이를 설정하는 옵션이 없다**(`--scope`, `--sparse`뿐). CLI로 복원할 수단이 없는 필드다 |
| 11 | settings.json 반영 시점 | **즉시.** 명령이 끝난 시점에 파일이 이미 갱신되어 있다. 세션 재시작은 파일 반영과 무관하다 |
| 12 | 동시 쓰기 | settings.json 전용 lock 파일은 없다(`~/.claude.json.lock`만 존재). CLI는 읽기-수정-쓰기를 하며 **모르는 필드도 보존한다**(`customUnknownField` 원형 유지). 다만 부수효과가 있다 — `"model": "opus"`가 `"opus[1m]"`으로 정규화됐다. **우리 대상 두 필드 밖에서도 파일이 재작성된다** |
| 13 | 목록 ↔ 실체 | `uninstall` 후에도 `~/.claude/plugins/cache/<마켓>/<플러그인>/<버전>/` 디렉토리는 **남는다.** 반대로 `enabledPlugins`에 설치되지 않은 플러그인의 키가 있어도 CLI는 지우지 않는다 — 양방향 괴리가 모두 가능하다 |

#### 브리프에 없던 발견 4건

**N1. 플러그인 간 의존성이 `enabledPlugins`에서 직접 설치와 구별되지 않는다.**
`plugin.json`의 `dependencies`는 **배열**(`["zeta@testmkt-d"]`)이다. `install epsilon`은
`(+ 1 dependency: zeta)`와 함께 zeta를 자동 설치하고, **`enabledPlugins`에 `zeta@testmkt-d: true`를
직접 설치와 똑같은 모양으로 넣는다.** 구별 수단은 `installed_plugins.json`의 **`"auto": true`**
플래그 하나뿐이다. `uninstall epsilon` 후에도 zeta는 `enabledPlugins`에 남고, `prune`이 그때서야
`no longer needed`로 잡는다.
→ `enabledPlugins`만 동기화하면 **자동 설치된 의존 플러그인이 사용자가 고른 플러그인으로 승격되어**
타 기기에 전파되고, 원 기기에서 부모를 지워도 타 기기에서는 영원히 고아로 남는다.

**N2. `settings.json`에 비밀이 들어갈 수 있다 — 6장 불변식 4의 "적용 대상 없음"은 틀렸다.**
`install --config <k=v>`가 플러그인 `userConfig` 값을 **`settings.json`의 세 번째 필드
`pluginConfigs`에 평문으로** 저장한다(`{"delta@testmkt-c": {"options": {"apiKey": "SECRET123"}}}`).
이미 설치된 플러그인에 `--config`만 다시 주면 값이 갱신되고, 지정하지 않은 키는 보존된다(부분 병합).
현재 `extract_plugins.py`는 이 필드를 뽑지 않으므로 **지금 유출은 없다.** 그러나 플러그인을
온전히 복원하려면 필요한 값이고, 넣는 순간 **MCP와 같은 마스킹 규율이 필요해진다.**
"플러그인은 `redact`·`secret_keys`가 필요 없으므로 정규화가 항등함수"라는 2장의 전제도
함께 흔들린다 — 공용 코어 추출 판단의 입력이 바뀐다.

**N3. 비대화형 호출에서 `-y`가 필요한 경로가 있다.**
`install --help`: `-y, --yes` — *"required when stdin or stdout is not a TTY"*. 마켓플레이스가
선언한 명령으로 설치되는 플러그인, 또는 `headersHelper`로 아카이브를 받는 플러그인이 대상이다.
`prune`도 같다. 스킬은 항상 비TTY로 호출되므로 **이 플래그가 없으면 해당 플러그인은 복원 불가**다.

**N4. 진실 원천이 하나가 아니다.**
`~/.claude/plugins/` 아래에 `installed_plugins.json`(자체 `"version": 2` 스키마)과
`known_marketplaces.json`이 있다. 전자는 플러그인 키마다 **배열**을 갖는다 — 같은 플러그인이
스코프별로 여러 벌 설치될 수 있다는 뜻이고, 각 항목에 `scope`·`installPath`·`version`·
`installedAt`·`lastUpdated`·`gitCommitSha`·`auto`가 있다. 후자에는 `installLocation`(기기별
절대 경로)이 있어 **동기화 대상이 될 수 없다.** 다행히 `settings.json`의 두 필드는 기기 독립적이다.
5장의 "로컬 상태의 정의"는 2지선다가 아니라 3지선다다.


### 1-c. 읽기 전용 조사·정적 분석 — 스키마 가정을 뒤집는 5건 (2026-08-24)

1-b와 병행해 변경 없는 조사를 돌렸다(help 전문, `list --json`, `~/.claude/plugins/` 레이아웃,
바이너리 문자열). 아래 주장은 **전부 바이너리에서 직접 재확인했고**, 값 보존 여부는 임시 HOME
실측으로 검증했다. 1-b보다 이쪽이 설계에 더 위험하다.

**C1. `enabledPlugins`의 값은 불리언이 아닐 수 있다. — 스키마 최대 위험**

설정 스키마 원문: *"Also supports extended format with version constraints."* 값 스키마는
`union([array, boolean, object])`다. 설치 실패 사유에 `range-conflict`·`no-matching-tag`·
`installed-unsatisfied`가 있고, `installed_plugins.json`에 `resolvedVersion`
(*"Tag-derived semver this install resolved to (when fetched via a version constraint)"*)이 있다.

실측으로 확인한 것:

- `{"beta@testmkt-a": ["1.0.0"]}`을 심어 두고 다른 플러그인을 install해도 **그 값은 그대로 보존된다.**
- 반면 `{"alpha@testmkt-a": {"version": "1.0.0"}}`은 그 플러그인을 install하는 순간 **`true`로 평탄화된다.**

→ **`plugins.json`이 값을 `bool`로 가정하면 확장 포맷을 쓰는 기기의 버전 제약을 파괴한다.**
켬/끔 비교(결함 B)를 "값 동등 비교"로 고치는 것만으로는 부족하고, 정규화·비교·복원이
세 가지 값 타입을 모두 통과시켜야 한다. 5장 "파괴 방지 먼저"가 여기에도 그대로 걸린다.

**C2. `additionalMarketplaces`라는 별칭 키가 있고, Claude Code가 이를 재작성한다.**

스키마 원문: *"Alias for extraKnownMarketplaces: this key is read exactly as if it were spelled
extraKnownMarketplaces. Do not set both in one file — if both appear, this key is ignored with a
warning. Claude Code may rewrite this key as extraKnownMarketplaces when it updates the file."*

실측: `additionalMarketplaces`만 있는 `settings.json`에 `marketplace add`를 실행하자
**별칭 키가 사라지고 `extraKnownMarketplaces`로 재작성됐다.**
→ **추출기가 `extraKnownMarketplaces`만 읽으면, 아직 재작성되지 않은 기기의 마켓플레이스를
통째로 놓친다.** 두 키를 모두 읽어야 한다.

**C3. always-known 집합은 1개가 아니라 최소 5개다.**

`claude-plugins-official` 외에 **마켓플레이스가 아닌 의사 출처 4개**가 있다 —
`inline`, `skills-dir`, `synced`, `builtin`. 바이너리 상수로 확인된다.
이 넷은 `marketplace add`로 만들 수 없고 `known_marketplaces.json`에도 들어가지 않는다.
`@skills-dir`는 `~/.claude/skills/` 자동 로드용 센티널이며 *"known_marketplaces.json /
marketplace add etc. ignore it"*이라고 명시돼 있다.
→ restore의 마켓플레이스 등록 대상에서 이 5개를 **반드시 빼야** 한다.

추가로 **제3자가 쓸 수 없는 예약 이름 16개**가 있다(`claude-code-marketplace`,
`anthropic-plugins`, `agent-skills`, `claude-community` 등). 이 이름으로 등록을 시도하면
소스가 `anthropics/` 아래가 아닌 한 거부된다 — 실패 수집 규칙에 이 갈래가 필요하다.

**C4. "부재"는 "꺼짐"이 아니다. 매니페스트 기본값에 위임하는 상태다.**

매니페스트 스키마 원문: *"Whether the plugin starts enabled when the user has no explicit
enabled/disabled setting for it (default: true). Explicit enabledPlugins values always win, and a
plugin required by an enabled dependent is enabled regardless of this value."*
→ 3상태 처리에서 **부재를 `false`와 같게 접으면 의미가 뒤집힌다.** 부재의 기본은 오히려 켜짐이다.

**C5. 동기화 대상은 `settings.json`이 맞다 — 다만 로컬 상태 조회는 `list --json`이 낫다.**

바이너리 로그: *"Syncing installed_plugins.json with enabledPlugins from all settings.json files"*.
**`installed_plugins.json`이 `settings.json`에서 파생된다**(그 반대가 아니다). 동기화 대상 선정은
현행이 옳다. 한편 `claude plugin list --json`은 `id`·`version`·`scope`·`enabled`·`installPath`·
`mcpServers`를 한 번에 준다 — 로컬 상태 조회에 파일 파싱보다 안전하다. 다만
**"키 부재"와 `false`를 이 출력으로 구별할 수 없다**(둘 다 나타나지 않거나 `enabled:false`).

그리고 `list --json`이 플러그인 항목에 **`mcpServers`를 함께 반환한다.**
→ **플러그인 설치가 MCP 서버 목록을 바꾼다. `plugins.json`과 `mcp-servers.json` 동기화는
서로 독립이 아니다.** (현행 `mcp_config`는 `~/.claude.json`의 user 스코프만 보므로 플러그인
제공 서버는 자동 제외된다 — 이 분리가 유지되는지 spec이 확인해야 한다.)

#### 그 밖에 기록해 둘 표면

- `uninstall`에 `--keep-data`(`~/.claude/plugins/data/{id}/` 보존)와 `--prune`이 있다.
  **제거는 설정 키·캐시·data 디렉토리 세 층을 건드린다.**
- `marketplace remove --scope`를 **생략하면 모든 스코프에서 제거**된다. 그게 기본값이다.
- `disable`은 플러그인 인자가 선택적이고 `-a, --all`이 있다.
- `data/` 디렉토리 결합자는 `@`가 아니라 `-`다(`data/swift-lsp-claude-plugins-official`).
  플러그인 이름 자체에 하이픈이 있으므로 **역파싱이 모호하다** — 키로 삼지 말 것.
- 캐시에는 **한 플러그인의 버전 디렉토리가 여럿 남는다**(이 기기: figma 3벌, superpowers 2벌,
  suberpower 2벌). `.in_use`·`.orphaned_at` 마커로 관리되며, 둘이 동시에 붙은 것도 있다.
  → `~/.claude/plugins/`만으로는 "무엇이 현재 설치본인가"를 답할 수 없다.
- 마켓플레이스가 없는 `enabledPlugins` 항목을 런타임은 **조용히 건너뛴다**
  (`Skipping orphaned enabledPlugins entry ...: marketplace not registered`) — 에러가 아니다.
  restore가 마켓플레이스 등록에 실패해도 Claude Code는 죽지 않지만, 사용자에게는
  "복원했는데 없다"로 보인다.
- 이 기기에 **목록에 없는데 로드되는 플러그인이 실재한다** — `~/.claude/skills/investigate/`가
  다음 세션에 `investigate@skills-dir`로 자동 로드되지만 `enabledPlugins`에 없다.


---

## 4. 2단계 — 실측이 가른 설계 분기 (확정)

1-b의 측정으로 아래 분기가 **전부 확정됐다.** 남은 추측은 없다.

| 확정된 실측 | 설계 결론 |
|---|---|
| `install`이 **멱등** | 채택은 **1단계**다. MCP 7.7의 `remove`→`add-json` 위험 구간을 이식할 필요가 없다 |
| `disable`/`enable`이 **존재하고 키를 유지** | `false`를 온전한 상태로 동기화한다. **3상태(true/false/부재)를 그대로 다룬다** |
| `disable`/`enable`이 **멱등이 아님** | 복원은 "원하는 상태로 만들기"를 **현재 상태를 읽고 필요한 경우에만** 호출해야 한다. 무조건 호출하면 이미 맞는 항목이 exit 1로 실패해 거짓 실패가 보고된다 |
| `uninstall`이 **키를 삭제** | **삭제 전파 = 키 삭제**로 정의한다. "제거"와 "끔"이 CLI상 구별 가능하므로 3상태를 접을 이유가 없다 |
| `marketplace remove`가 **존재** | 마켓플레이스를 additive only로 고정할 필요는 없다. **다만 연쇄 삭제**이므로 마켓플레이스 제거는 플러그인 다수의 삭제와 같은 무게로 다뤄야 한다 — 자동 실행 후보에서 뺀다 |
| 내장 마켓플레이스 **존재** | 의존성 검사에서 `claude-plugins-official`을 **always-known** 집합으로 분리한다. 없으면 restore가 등록할 수 없는 마켓플레이스를 등록하려 든다 |
| `autoUpdate`에 **CLI 설정 수단 없음** | 동기화 대상에 넣으면 **복원할 수 없는 필드**가 된다. 값 비교에서 제외하거나(정규화 시 제거), 넣되 "복원 불가, 안내만" 버킷으로 분리한다. **spec이 문언으로 확정해야 한다** |
| `pluginConfigs`에 **평문 비밀** | 동기화 대상에 넣는다면 마스킹이 **필수**다. 넣지 않는다면 "플러그인은 복원해도 설정은 복원되지 않는다"를 문서 다섯 곳에 명시해야 한다 |
| 의존성이 `enabledPlugins`에서 **구별 불가** | `auto: true` 항목을 동기화 대상에서 **뺄지** spec이 정해야 한다. 빼려면 `installed_plugins.json`을 읽어야 하고, 그러면 로컬 상태의 정의가 `settings.json` 단독이 아니게 된다 |
| `enabledPlugins` 값이 **bool이 아닐 수 있음**(C1) | 값 타입을 `bool`로 좁히지 않는다. 병합·비교·복원이 배열·객체·불리언을 모두 통과시켜야 하고, 알아볼 수 없는 값 타입은 **덮어쓰지 않고 보존**한다 |
| `additionalMarketplaces` **별칭 존재**(C2) | 추출기가 **두 키를 모두 읽는다.** 하나만 읽으면 재작성 전 기기의 마켓플레이스를 통째로 잃는다 |
| always-known이 **5개**(C3) | `claude-plugins-official`·`inline`·`skills-dir`·`synced`·`builtin`을 등록 대상에서 제외한다. 예약 이름 16개는 등록 실패 갈래로 분리한다 |
| **부재 ≠ 꺼짐**(C4) | 3상태의 "부재"를 `false`로 접지 않는다. 부재의 실제 기본값은 매니페스트의 `defaultEnabled`(기본 `true`)다 |
| 비TTY에서 **`-y` 필요 경로 존재** | 복원 스크립트의 `install` 호출에 `-y`를 넣을지 spec이 정한다. 넣지 않으면 해당 플러그인은 조용히 실패하고, 넣으면 마켓플레이스가 선언한 명령을 확인 없이 실행한다 — **보안 판단이 필요한 지점이다** |

---

## 5. 3단계 — 계획 수립 기준

**순서: 실측 → spec 확정 → plan 작성 → 구현.** MCP 작업의 교훈이 명확하다 —
*"정확한 코드까지 박힌 plan을 설계가 굳기 전에 쓰지 마라. Task 1~5 동안 spec이 여섯 번
바뀌었고 그때마다 plan 후반부가 낡았다."*

### spec이 반드시 확정해야 하는 것

1. **동기화 단위.** `enabledPlugins`의 키 하나 = 한 항목. `extraKnownMarketplaces`는
   별도 네임스페이스인가, 같은 문서 안의 두 섹션인가.
2. **의존성 순서.** 마켓플레이스가 거부·충돌 중인데 그 플러그인은 채택된 조합을
   어떻게 다루는가. (MCP에는 키 간 의존이 없었다 — 여기만의 문제다.)
3. **3상태 처리.** 4장 결정표의 결과를 문언으로 확정한다.
4. **삭제 전파의 의미.** "다른 기기가 지웠다"가 *비활성화*인지 *제거*인지.
5. **로컬 상태의 정의.** `settings.json`의 목록인가, `~/.claude/plugins/`의 실체인가,
   둘의 교집합인가. (측정 13번의 결과에 달렸다.)
6. **실패 처리.** `plugin install`은 네트워크로 코드를 받아오므로 **실제로 실패한다.**
   MCP `add-json`은 로컬 쓰기라 등록 자체는 항상 성공했다. 항목별 실패 수집·보고 규칙이 필요하다.
7. **공용 코어 추출 여부.** 아래 기준 참고.
8. **스키마 버전과 역호환.** 현재 `plugins.json`은 `{"enabledPlugins":{...},
   "extraKnownMarketplaces":{...}}`다. 구버전 `check_status.py`는
   `.get("enabledPlugins", {})`로 읽으므로, v2로 감싸면 **죽지는 않지만 빈 집합으로 읽어
   "레포에만 있음"을 오보한다.** MAJOR 상승이 필요한지 판단해 기록한다.

### 공용 코어 추출 판단 기준

> **상태 기계를 복사하지 마라.** Critical 3건이 전부 거기서 나왔고, 복사하면 위험도 복사된다.

권장안: `lib/mcp_config.py`의 판정 부분을 값에 무관한 코어로 분리하고
(`merge`/`next_base`/`restore_plan`에서 `redact`를 주입 가능한 정규화 함수로),
`mcp_config`는 얇은 어댑터로 남긴다. 플러그인은 정규화 = 항등함수인 두 번째 어댑터가 된다.
그러면 `test_mcp_state_machine.py`를 두 어댑터에 대해 파라미터화할 수 있고,
159개가 검증한 상태 기계를 그대로 물려받는다.

**추출하지 않기로 한다면** 그 이유를 spec에 적고, 반복·교대 테스트를 플러그인 쪽에도
**전부 다시** 쓴다. 둘 중 하나는 반드시 해야 한다.

### 첫 task는 스키마 설계가 아니다

**`extract_plugins.py`가 레포 파일을 읽지 않고 통째로 덮어쓴다.** 이 성질이 남아 있는 한
스키마를 어떻게 설계하든 미래 버전의 `plugins.json`이 파괴된다 — MCP에서 옛 버전이
저지른 사고와 정확히 같은 형태다. 스키마 호환성은 부차적이고 진짜 문제는 쓰기 방식이다.

따라서 순서는:

1. **파괴 방지 먼저** — 알아볼 수 없는 `plugins.json`을 만나면 쓰지 않는다.
   `mcp_config`의 `UnknownBackupSchema`·`_recognized_servers` 패턴을 그대로 옮긴다.
   결함 (C)의 예외 처리도 여기서 함께 고친다.
2. **그 다음 병합** — 키 단위 3-way.
3. **스키마 변경은 마지막.** 필요하다면.

1번만으로도 "다음 변경이 사용자 데이터를 파괴하지 않는다"는 목표는 달성된다.

### task 분할 기준

MCP plan에서 가장 유효했던 것은 **"사용자 가치가 나오는 지점"을 명시한 것**이었다
(Task 5·6·10이 끝나야 버그가 실제로 고쳐진다). 같은 표기를 넣는다 —
스킬이 새 모듈을 호출하기 전까지 사용자 관점의 가치는 0이다.

### 완료 정의

- 반복 적용 고정점 테스트(같은 로컬로 backup 3회 → 2·3회차 동일)
- 교대 시나리오 테스트(backup ↔ restore, 실제 스크립트 서브프로세스 경유)
- 실환경 스모크(실제 `settings.json` 사본, 임시 플러그인 설치·제거 짝)
- 문서 다섯 곳 동기화 (아래 6장)

---

## 6. 유의사항

### 그대로 지킬 것 — MCP의 다섯 불변식

1. **base는 로컬이 동의한 값만 전진한다.** `base ← 레포 파일 전체`는 폐기된 규칙이다.
   **전역 게이트를 되살리지 말 것.**
2. **신뢰할 수 없는 이력은 `{}`가 아니라 `None`이다.** 읽기 실패를 "0개"로 읽으면
   삭제 판정의 근거가 된다. 결함 (C)가 정확히 이 규율의 부재다.
3. **모든 상태에 탈출구가 있어야 한다.** "다른 기기가 껐는데 여기선 켜져 있다"는
   안정 상태다 — 사용자가 선택하지 않으면 영원히 유지된다. 3선택지를 준다.
4. **(마스킹 규율) 적용 대상이 있다.** ~~플러그인에는 적용 대상이 없다~~ — **2026-08-24 실측이 반증했다.**
   `settings.json`의 `pluginConfigs`가 `userConfig` 값을 평문으로 들고 있다(1-b N2). 이 필드를
   동기화 대상에 넣는다면 MCP와 **동일한** 마스킹 규율(양쪽에 적용한 뒤 비교, 멱등)이 그대로 필요하다.
   넣지 않기로 한다면 그 결정과 사용자 영향("플러그인은 복원돼도 설정은 복원되지 않는다")을 spec과 문서 다섯 곳에 적는다.
5. **CLI 제약은 실측으로 확정한다.** 3장 참조.

### 하지 말 것

- `update_base.py`에 **레포 경로를 넘기지 말 것.** `base ← 레포 파일 바이트`가 되어
  다음 백업이 타 기기 항목을 지운다.
- base 기록용 스크립트를 **새로 만들지 말 것.** 기록 주체는 하나다.
- 커밋·푸시 흐름에서 **"커밋할 변경 없음" 경로를 빠뜨리지 말 것.** 그 경로에서도
  base를 갱신해야 restore 없이 backup만 하는 기기에서 부트스트랩된다.
- 충돌 하나로 **전체 base를 얼리지 말 것.** 키 단위로 이미 고정된다.
- **단발 호출 테스트만으로 완료를 선언하지 말 것.** 판정표를 100% 덮고도 데이터를 잃은
  전례가 있다.

### 플러그인에만 있는 함정 (실측 후 6가지)

1. **키 간 의존성** — 마켓플레이스 먼저, 플러그인 나중. 등록 불가한 출처 5개는 예외(1-c C3).
   마켓플레이스 선언만으로는 부족하다 — `marketplace add`로 실체를 받아와야 install이 성공한다.
2. **무거운 부작용** — 설치는 네트워크 I/O이고 실제로 실패한다. 느리고, 부분 실패가 정상이다.
   비TTY에서는 `-y` 없이 실패하는 경로가 따로 있다(1-b N3).
3. **목록 ≠ 실체** — `settings.json`은 의도, `installed_plugins.json`은 실체, `~/.claude/plugins/`는
   잔존물. **셋이다**(1-b N4). 한 플러그인에 캐시 버전 디렉토리가 여럿 남는다.
4. **삭제가 연쇄한다** — `marketplace remove` 하나가 소속 플러그인 키를 전부 지운다(1-b 항목 8).
   "타 기기가 지웠다"의 원인이 플러그인 단위가 아니라 마켓플레이스 단위일 수 있다.
5. **자동 설치가 수동 설치로 위장한다** — 의존 플러그인이 `enabledPlugins`에 `true`로 들어가고
   `settings.json`만으로는 구별할 수 없다(1-b N1). 그대로 백업하면 타 기기에서 고아가 영구화된다.
6. **값 타입이 셋이다** — `bool`뿐 아니라 배열·객체(버전 제약)가 실재한다(1-c C1).

### 문서 동기화 대상 (다섯 곳)

한 곳만 고치면 나머지가 옛 서술을 계속 말한다. MCP 때 이 함정에 걸렸다.

- `README.md`, `README.ko.md`
- `skills/sync-backup/scripts/backup-readme.md`, `backup-readme.ko.md`
- `skills/sync-backup/SKILL.md` (+ 이번엔 `sync-status`·`sync-restore` SKILL.md도)

특히 README의 **"로컬 파일은 절대 자동으로 덮어쓰지 않습니다"** 옆에 붙은
`plugins.json` 예외 문구를 — 고치고 나면 **지워야 한다.**

---

## 7. 이어받는 방법

```bash
cd /Users/bran/personal/claude-sync
git checkout fix/mcp-config-source          # 또는 머지 후 main
uv run --with pytest pytest plugins/claude-sync/tests -q   # 159 passed 확인
```

읽을 순서:

1. 이 문서
2. `docs/superpowers/2026-08-20-mcp-redesign-STATUS.md` 5·6장 (불변식과 교훈)
3. `docs/superpowers/specs/2026-08-20-mcp-config-source-design.md` 7장 (판정표·base 규칙)
4. `plugins/claude-sync/lib/mcp_config.py` (재사용할 코어)

그다음 **3장의 실측부터** 시작한다. 실측 결과를 이 문서에 append하고, 4장 결정표를 채운 뒤
spec을 작성한다.
