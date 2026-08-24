# plugins.json 동기화 설계

- 작성: 2026-08-24
- 브랜치: `feat/plugins-sync` (`release/3.0.0`에서 분기)
- 근거 문서: `2026-08-20-plugins-sync-followup-BRIEF.md` (실측 1-b·1-c, 결정 D1~D3)
- 선행 설계: `specs/2026-08-20-mcp-config-source-design.md` (판정표·base 규칙의 원본)
- 상태: **현행 설계.** plan은 이 문서가 굳은 뒤에 쓴다.

이 문서는 **무엇을 만들 것인가**를 정한다. 어떻게 나눠 구현할지는 plan이 정한다.

---

## 1. 배경 & 문제

`plugins.json`은 `~/.claude/settings.json`에서 두 필드를 뽑아 만드는 파생 산출물이다.
대응하는 로컬 파일이 없어 `iter_synced_relpaths`가 열거하지 못하므로 **파일 단위 3-way의
대상이 될 수 없다.** 그 결과 세 가지 결함이 있다.

| | 결함 | 위치 |
|---|---|---|
| A | 매 백업마다 레포 파일을 통째로 재생성 → 타 기기 플러그인 소실 | `extract_plugins.py` |
| B | status가 `enabledPlugins`의 **키 집합만** 비교 → 켬/끔 변경을 못 봄 | `check_status.py:63-65` |
| C | 예외 처리 부재 → `settings.json`이 없거나 깨지면 backup 전체가 중단 | `extract_plugins.py` |

MCP 재설계가 `mcp-servers.json`에 대해 고친 것과 **같은 결함**이다. 해법의 골격도 같다 —
키 단위 3-way 병합, "모르면 안 쓴다" 가드, 읽기 실패와 0개의 구별.

### 1.1 실측이 추가로 드러낸 것

브리프 1-b·1-c의 실측은 결함 세 건보다 **더 위험한 사실 다섯 가지**를 드러냈다.
이것들이 이 설계의 형태를 결정한다.

1. **값이 불리언이 아닐 수 있다.** `enabledPlugins`의 값 스키마는
   `union([array, boolean, object])`이고 버전 제약 표현이 실재한다. 배열 값은 CLI를 통과해도
   보존된다. `bool`로 좁히면 데이터를 파괴한다.
2. **`settings.json`에 평문 비밀이 있다.** `pluginConfigs`가 플러그인 `userConfig` 값을
   그대로 들고 있다. 동기화 대상에 넣으면 마스킹이 필수다.
3. **`additionalMarketplaces` 별칭 키가 있다.** 읽지 않으면 마켓플레이스를 통째로 놓친다.
4. **의존성으로 들어온 플러그인이 직접 설치와 구별되지 않는다.** `settings.json`만 보면
   구별할 수 없고, 명시적으로 설치하면 표식이 **되돌릴 수 없게** 지워진다.
5. **`marketplace remove`가 연쇄 삭제한다.** 마켓플레이스 하나가 사라지면 소속 플러그인
   키가 전부 사라진다. "타 기기가 지웠다"의 원인이 플러그인 단위가 아닐 수 있다.

---

## 2. 목표 / 비목표

### 목표

- **G1.** 한 기기의 백업이 다른 기기의 플러그인을 지우지 않는다 (결함 A).
- **G2.** 켬/끔 변경과 설정 값 변경이 status에 보고된다 (결함 B).
- **G3.** `settings.json`을 읽지 못해도 backup 흐름이 종료 코드 0으로 계속된다 (결함 C).
- **G4.** 알아볼 수 없는 `plugins.json`을 만나면 **쓰지 않는다.** 상위 버전의 백업을
  파괴하지 않는다.
- **G5.** 값 타입 셋(불리언·배열·객체)을 전 구간에서 보존한다.
- **G6.** `pluginConfigs`를 마스킹해 동기화하고, 복원 시 값 입력을 **건너뛸 수 있게** 한다.
- **G7.** 의존성으로 자동 설치된 플러그인이 타 기기로 승격 전파되지 않는다.
- **G8.** 상태 기계를 복사하지 않는다. MCP가 검증한 판정표를 **공유**한다.

### 비목표 (이번 범위 밖)

- project·local 스코프 플러그인. user 스코프만 다룬다.
- `~/.claude/plugins/cache`의 잔존 버전 디렉토리 정리. `prune`과 스윕은 CLI의 일이다.
- 플러그인 **버전 고정**. CLI에 버전 지정 설치 수단이 없다(브리프 1-a).
- `~/.claude/skills/`의 `@skills-dir` 자동 로드 플러그인. 마켓플레이스 개념 밖이다.
- 마켓플레이스 자동 업데이트 설정(`autoUpdate`). 7.2에서 제외 근거를 밝힌다.

---

## 3. 데이터 소스 — "로컬 상태"의 정의

브리프 5장 항목 5의 답이다. **두 파일에서 읽되 역할이 다르다.**

| 파일 | 읽는 것 | 역할 |
|---|---|---|
| `~/.claude/settings.json` | `enabledPlugins`, `extraKnownMarketplaces`, `additionalMarketplaces`, `pluginConfigs` | **동기화 대상 값의 유일한 원천** |
| `~/.claude/plugins/installed_plugins.json` | 각 항목의 `auto` 플래그 **하나만** | 백업에서 뺄 항목을 가리는 필터 |

`installed_plugins.json`을 값의 원천으로 삼지 않는 이유는 그것이 **`settings.json`에서
파생되기 때문**이다(바이너리 로그: *"Syncing installed_plugins.json with enabledPlugins from
all settings.json files"*). 파생물을 원천으로 쓰면 방향이 뒤집힌다.

`claude plugin list --json`을 쓰지 않는 이유는 **"키 부재"와 `false`를 구별하지 못하기
때문**이다. 3상태를 다루려면 파일을 읽어야 한다.

### 3.1 별칭 키

`extraKnownMarketplaces`와 `additionalMarketplaces`는 같은 뜻이다. 읽을 때 **둘 다 본다.**

- 둘 다 있으면 `additionalMarketplaces`를 무시한다 (CLI와 같은 규칙).
- 쓰는 쪽(복원)은 CLI를 통하므로 이 문제를 겪지 않는다.

### 3.2 `auto` 필터 (D3)

`installed_plugins.json`의 `plugins[<id>]`는 **배열**이다(스코프별 다중 설치).
user 스코프 항목 중 `auto`가 참인 것만 필터 대상이다.

```
auto_ids = { id
             for id, entries in installed.get("plugins", {}).items()
             if any(e.get("scope") == "user" and e.get("auto") is True for e in entries) }
```

이 집합에 든 id는 **백업 대상에서 뺀다.** `pluginConfigs`의 같은 id도 함께 뺀다.

**읽기 실패 시** — 파일이 없거나 깨졌거나 형태를 알아볼 수 없으면 `auto` 판정이 불가능하다.
불변식 6에 따라 통과로 접지 않고 **전량 포함 + 경고**로 처리한다.

> 백업에서 빠뜨리는 것은 되돌릴 수 없는 손실이고, `auto` 혼입은 복원 안내로 완화할 수 있다.
> 요점은 **조용히 넘어가지 않는 것**이다. 보고서에 한 줄이 반드시 남는다.

---

## 4. 스키마 v2 — `plugins.json`

### 4.1 형태

```json
{
  "version": 2,
  "scope": "user",
  "enabledPlugins": {
    "figma@claude-plugins-official": true,
    "superpowers@claude-plugins-official": false,
    "beta@some-marketplace": ["1.0.0"]
  },
  "extraKnownMarketplaces": {
    "suberpower": { "source": { "source": "github", "repo": "june20516/suberpower" } }
  },
  "pluginConfigs": {
    "delta@some-marketplace": { "options": { "apiKey": "<REDACTED>", "region": "kr" } }
  }
}
```

### 4.2 왜 최상위 필드 이름을 그대로 두는가

**구버전 리더가 계속 읽을 수 있기 때문이다.** v1은 `{"enabledPlugins": {...},
"extraKnownMarketplaces": {...}}`였다. 이 이름을 `sections` 같은 것으로 감싸면
2.x의 `check_status.py`가 `.get("enabledPlugins", {})`로 **빈 집합을 읽어**
"레포에만 있음"을 오보한다. 이름을 유지하면 그 오보가 없다.

MCP가 v1 배열 → v2 객체로 형태를 바꾼 것과 다른 선택인데, 이유가 있다 — MCP의 v1은
배열이라 키 단위 병합 자체가 불가능했지만, 여기는 **v1이 이미 올바른 모양**이다.
바꿀 이유가 없는 것을 바꾸지 않는다.

`version`과 `scope`는 새로 붙는다. 구버전은 이 키를 무시하므로 해가 없다.

### 4.3 인식 규칙 — "모르면 안 쓴다"

`mcp_config`의 `_recognized_servers`·`UnknownBackupSchema` 패턴을 그대로 옮긴다.

문서를 **인식한다**고 판정하는 조건은 전부 참일 때뿐이다:

1. 최상위가 객체다.
2. `version`이 없거나, `SCHEMA_VERSION`(=2) 이하다.
   숫자(int·float)로 더 높은 값을 주장하면 **인식하지 않는다.** bool은 버전 주장이 아니므로
   제외하고, 문자열은 손으로 고친 문서를 막지 않기 위해 통과시킨다. (MCP `_claims_newer_schema`와 동일)
3. `enabledPlugins` 또는 `extraKnownMarketplaces` 중 **적어도 하나가 존재하고 객체**다.

조건 3은 의도적으로 엄격하다. 최상위가 `{}`이거나 아는 필드가 하나도 없는 객체는
**인식하지 않는다.** `{"foo": 1}`을 "플러그인 0개"로 읽으면 그 파일을 덮어써 파괴하기
때문이다(불변식 6 — 판정 불가를 통과로 접지 않는다).

대가: 어쩌다 `plugins.json`이 `{}`가 되면 backup이 그 파일을 건드리지 못하고 계속 건너뛴다.
안내 문구에 **"파일을 지우면 다음 백업이 새로 만든다"**를 넣어 탈출구를 준다.

세 함수가 이 판정을 공유한다 — `parse_base`(이력), `load_backup`(레포), `parse_backup`(관대한 읽기).
**세 곳이 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고, 그 비대칭이 상위 버전
백업을 파괴한다.**

---

## 5. 공용 코어 추출 — `lib/keyed_sync.py`

브리프 5장의 판단을 **추출하는 쪽으로 확정한다.**

### 5.1 왜 추출하는가

브리프는 "플러그인은 `redact`·`secret_keys`·`restorable`이 전부 필요 없으므로 정규화가
항등함수"라고 적었으나 **실측이 반증했다** — 셋 다 필요하다(D1, 1-c C3).
즉 두 도메인이 **같은 훅을 같은 자리에서 쓴다.** 추출의 근거가 오히려 강해졌다.

그리고 브리프의 경고가 그대로 유효하다:

> **상태 기계를 복사하지 마라.** Critical 3건이 전부 거기서 나왔고, 복사하면 위험도 복사된다.

### 5.2 경계

```
lib/keyed_sync.py     ← 값에 무관한 키 단위 3-way 코어 (새로 만듦)
lib/mcp_config.py     ← MCP 어댑터 (기존 파일이 얇아짐)
lib/plugin_config.py  ← 플러그인 어댑터 (새로 만듦)
```

코어가 제공하는 것 — 전부 `normalize`를 주입받는다:

| 함수 | 계약 |
|---|---|
| `same(a, b)` | 키 정렬 JSON 지문 비교 |
| `diff(local, repo, normalize)` | `only_local` / `only_repo` / `changed` |
| `next_base(local, base, merged, normalize)` | 로컬이 동의한 키만 전진 |
| `merge(local, repo, base, normalize)` | 판정표 케이스 1~10, `next_base` 포함 |
| `restore_plan(local, repo, base, normalize, restorable, secret_keys)` | 버킷 9개 |

`normalize`의 계약은 **멱등**이다. 이미 정규화된 입력에 다시 적용해도 결과가 같아야 한다.
그렇지 않으면 로컬(원본)과 레포(정규화됨)가 수렴하지 않는다 — MCP Bug #2와 같은 형태.

`restorable`·`secret_keys`는 `restore_plan`에만 필요하다. 기본값은 각각
`lambda name, cfg: True`, `lambda cfg: []`다.

### 5.3 어댑터가 채우는 것

| 훅 | `mcp_config` | `plugin_config` |
|---|---|---|
| `normalize` | `redact` (headers/env 값 마스킹) | 7.2의 세 섹션별 정규화 |
| `restorable` | 이름 규칙 + command/url+type | 8장의 판정 |
| `secret_keys` | headers/env의 (field, key) | `pluginConfigs.options`의 키 |

### 5.4 테스트 승계

`tests/test_mcp_state_machine.py`(반복 적용 고정점)와 `tests/test_mcp_cycle.py`(교대 시나리오)를
**어댑터에 대해 파라미터화**한다. 두 어댑터가 같은 상태 기계 테스트를 통과해야 한다.

**이것이 추출의 실질적 이득이다.** 159개가 검증한 상태 기계를 플러그인이 그대로 물려받는다.
추출하지 않았다면 이 테스트를 전부 다시 써야 했다.

### 5.5 회귀 금지

`mcp_config`의 공개 함수 시그니처와 동작은 **바뀌지 않는다.** 어댑터가 코어를 호출하도록
내부만 바꾼다. 기존 367개 테스트가 수정 없이 통과해야 한다 — 통과하지 않으면 추출이 틀린 것이다.

---

## 6. 비밀 처리 — `pluginConfigs` (D1)

### 6.1 마스킹

`pluginConfigs[<id>].options`의 **값만** `<REDACTED>`로 치환하고 **키 이름은 보존**한다.
MCP의 `headers`/`env` 처리와 같은 규율이다.

키 이름을 보존하는 이유: 복원 시 **레포 파일만 보고 "어떤 값을 물어야 하는지"** 를 알 수 있어야 한다.

`options` 외의 필드가 있으면 그대로 둔다 — 모르는 필드를 지우지 않는다.
`options`가 객체가 아니면 필드 전체를 문자열 `<REDACTED>`로 바꾼다(MCP `_redact_field`와 동일).

마스킹은 **비교 직전 양쪽에 적용**한다. 로컬은 평문, 레포는 마스킹된 값이므로 원본끼리
비교하면 설정을 가진 플러그인이 영구히 "변경됨"으로 보고된다.

### 6.2 값이 없는 항목

`options`가 비었거나 `pluginConfigs`에 항목이 없는 플러그인은 물어볼 것이 없다.
`add` 버킷으로 간다.

### 6.3 건너뛰기는 1급 상태다

MCP와 다른 점이다. 사용자가 값을 지금 모를 수 있다.

- 값을 입력하지 않아도 **플러그인 자체는 설치한다.** 설정만 비운 채 둔다.
- 건너뛴 항목은 복원 보고서에 남고, 나중에 채우는 방법을 함께 안내한다:

  ```
  claude plugin install <id> --config <key>=<value>
  ```

  이미 설치된 플러그인에도 값이 갱신되고, 지정하지 않은 키는 보존된다(실측 확인).

### 6.4 건너뛴 상태의 탈출구

건너뛰면 로컬 `pluginConfigs`에 그 키가 없고 레포에는 `<REDACTED>`가 있다.
그대로 두면 **매번 `/sync-status`가 차이를 보고**해 소음이 된다. 불변식 3(모든 상태에
탈출구가 있어야 한다)에 걸린다.

해소 방법 — restore가 세 선택지를 준다:

1. **지금 값을 입력한다** → `install --config`로 채운다. 다음 status에서 in_sync.
2. **나중에 입력한다** → 이번에는 건너뛴다. 다음 status에서 다시 보고된다(의도된 알림).
3. **이 기기에서는 쓰지 않는다** → 레포 값을 그대로 base에 기록해 **차이를 해소된 것으로
   확정**한다. 이후 status는 조용하다. 레포 값이 바뀌면 다시 보고된다.

3번이 탈출구다. **선택지 3이 없으면 이 상태는 영원히 안정 상태로 남는다.**

---

## 7. 키 단위 3-way 병합

### 7.1 병합 단위 — 한 문서, 세 섹션 (브리프 5장 항목 1의 답)

`plugins.json`은 **하나의 relpath**이고 base 블롭도 하나다. 그 안에서 세 섹션이
**각각 독립적으로** 키 단위 3-way를 거친다.

- `enabledPlugins` — 키는 `<plugin>@<marketplace>` id
- `extraKnownMarketplaces` — 키는 마켓플레이스 이름
- `pluginConfigs` — 키는 플러그인 id

**섹션 간에 게이트를 두지 않는다.** 마켓플레이스 하나가 충돌 중이어도 플러그인의 base는
계속 전진한다. 전역 게이트를 되살리지 않는다는 불변식 1의 연장이다.

판정표(케이스 1~10)와 base 전진 규칙은 `specs/2026-08-20-mcp-config-source-design.md`
7.2·7.3을 그대로 따른다. **여기서 다시 적지 않는다** — 두 벌이 되면 갈라진다.

### 7.2 섹션별 정규화

**`enabledPlugins` — 항등함수.**
값이 불리언이든 배열이든 객체든 **그대로 비교하고 그대로 저장한다.** 좁히지 않는다.

**`extraKnownMarketplaces` — 두 가지를 제거한다.**

1. **`autoUpdate` 필드를 제거한다.** 값에는 실재하지만 **`marketplace add`에 이를 설정하는
   옵션이 없다**(실측). 비교 대상에 넣으면 한 기기가 켜고 다른 기기가 껐을 때
   **수렴시킬 CLI 수단이 없어** 영구히 "변경됨"으로 보고된다. 탈출구 없는 상태를 만들지
   않기 위해 비교·저장 양쪽에서 뺀다.
   → 문서에 "마켓플레이스 자동 업데이트 설정은 기기별 설정이며 동기화되지 않는다"를 명시한다.

2. **`source.source == "directory"`인 항목 전체를 제거한다.** 값이 그 기기의 절대 경로라
   다른 기기에서 의미가 없다. 실으면 복원할 수 없는 항목이 영구히 차이로 남는다.
   → 문서에 "로컬 디렉토리에서 등록한 마켓플레이스는 동기화되지 않는다"를 명시한다.

**`pluginConfigs` — `redact`.** 6.1 참조.

### 7.3 base 저장과 갱신 시점

MCP의 스테이징 계약을 **그대로** 쓴다. 새 스크립트를 만들지 않는다.

```
1. collect_plugins.py <레포> <스테이징>
     - 병합 결과 → 레포/plugins.json
     - next_base  → 스테이징/plugins.json
2. (SKILL.md) 커밋 · 푸시
3. update_base.py <스테이징> plugins.json
```

MCP가 같은 스테이징 디렉토리를 쓰므로 3단계는 한 번에 처리된다:

```
update_base.py <스테이징> mcp-servers.json plugins.json
```

**`update_base.py`에 레포 경로를 넘기지 않는다.** 넘기면 `base ← 레포 파일 바이트`가 되어
다음 백업이 타 기기 항목을 지운다. 브리프 6장의 "하지 말 것" 첫 줄이다.

**"커밋할 변경 없음" 경로에서도 base를 갱신한다.** 그래야 restore 없이 backup만 하는
기기에서 부트스트랩된다.

---

## 8. 복원 가능성 판정 (`restorable`)

`restore_plan`이 `add` 후보를 `unrestorable`로 걸러내는 기준이다.
**시도하면 반드시 실패하는 것**만 여기서 거른다. 실패할 수도 있는 것은 시도하고 실패를 수집한다.

### 8.1 플러그인

id가 `<plugin>@<marketplace>` 형태가 아니면 복원 불가.

마켓플레이스 부분이 **등록 가능한 출처가 아니면** 복원 불가:

| 이름 | 성격 | 처리 |
|---|---|---|
| `inline` | 의사 출처 | 복원 불가 |
| `skills-dir` | `~/.claude/skills/` 자동 로드 센티널 | 복원 불가 |
| `synced` | 의사 출처 | 복원 불가 |
| `builtin` | 내장 | 복원 불가 |
| `claude-plugins-official` | **내장 마켓플레이스** | **복원 가능**(등록은 건너뛰고 설치만) |

앞의 넷은 `marketplace add`로 만들 수 없고 `known_marketplaces.json`에도 들어가지 않는다.
백업에 실려 있더라도 다른 기기에서 재현할 수 없다.

### 8.2 always-known 집합

위 다섯 이름은 **마켓플레이스 등록 대상에서 제외**한다. 등록하려 들면
`claude-plugins-official`은 이미 자동 설치되어 있어 무의미하고, 나머지 넷은 실패한다.

### 8.3 예약 이름

공식 예약 13개(`claude-code-marketplace`, `claude-code-plugins`, `anthropic-marketplace`,
`anthropic-plugins`, `agent-skills`, `anthropic-agent-skills`, `life-sciences`,
`knowledge-work-plugins`, `claude-for-legal`, `claude-for-financial-services`,
`financial-services-plugins`, `first-party-plugins`, `claude-plugins-official`)와
커뮤니티 예약 3개(`claude-community`, `claude-plugins-community`, `healthcare`)는
소스가 공식 저장소가 아니면 등록이 거부된다.

**미리 거르지 않는다.** 정당한 소유자일 수 있으므로 시도하고, 실패하면 수집한다.
다만 안내 문구에서 이 갈래를 구별해 "예약된 이름이라 거부되었다"고 말한다.

### 8.4 값이 확장 포맷인 플러그인

값이 배열이나 객체(버전 제약)인 항목은 **설치는 되지만 값이 재현되지 않는다.**
`install`이 `true`로 평탄화하기 때문이다(실측).

`unrestorable`로 분류하지 않는다 — 설치 자체는 사용자에게 이득이다. 대신 복원 후
**"버전 제약은 재현되지 않았습니다"** 를 항목별로 보고한다.

### 8.5 command 소스 플러그인 (D2)

마켓플레이스가 명령으로 설치를 선언한 플러그인은 **세션 안에서 설치할 수 없다.**
`-y`를 붙여도 무시된다(실측). 이것은 우리가 우회할 대상이 아니라 **그대로 존중할 경계**다.

미리 알 수 없으므로 시도하고, 실패 시 CLI가 출력한 문구를 **그대로** 사용자에게 전달한다.
CLI가 이미 실행할 명령 전문과 승인 방법(`/plugin details` 창, 사용자 자신의 터미널)을
알려주므로 우리가 다시 쓸 필요가 없다.

### 8.6 마켓플레이스

`source.source`가 `github`(+`repo`)이면 복원 가능하다. `marketplace add <owner/repo>`.
`directory` 출처는 7.2에서 이미 제거되므로 여기 오지 않는다.
그 밖의 출처는 그대로 `marketplace add`에 넘겨 시도하고 실패를 수집한다.

---

## 9. 스킬별 동작

### 9.1 backup

새 스크립트 `sync-backup/scripts/collect_plugins.py <레포 경로> <스테이징 디렉토리>`.
`extract_plugins.py`는 **삭제한다** — 남겨두면 SKILL.md가 실수로 부를 수 있다.

```
1. 로컬 읽기
     settings.json         → 세 섹션
     installed_plugins.json → auto 필터 (실패 시 전량 포함 + 경고)
2. 레포 읽기   load_backup()  → UnknownBackupSchema면 status: skipped
3. 이력 읽기   parse_base()   → 못 믿으면 None (합집합으로 degrade)
4. 섹션별 merge
5. 스테이징에 next_base 기록  ← 먼저
6. 레포에 병합 결과 기록      ← 나중
```

5·6의 순서가 중요하다. 레포 쓰기가 실패하면 status가 skipped가 되고 SKILL.md가
`update_base.py`를 호출하지 않으므로 base가 전진하지 않는다.

**출력은 JSON**이다. `collect_mcp.py`와 같은 모양으로, 섹션별로 담는다.

```json
{
  "status": "ok",
  "auto_filter": "applied" ,
  "sections": {
    "enabledPlugins": {
      "conflicts": { "repo_kept": [], "repo_absent": [] },
      "deleted": [], "local_stale": [],
      "repo_ahead": { "present": [], "absent": [] }
    },
    "extraKnownMarketplaces": { "...": "같은 모양" },
    "pluginConfigs": { "...": "같은 모양" }
  }
}
```

`status`가 `skipped`이면 이유를 담고 **종료 코드는 0**이다 (결함 C 해소, 불변식 2).

`auto_filter`는 `applied` / `unavailable`(읽기 실패 → 전량 포함) 중 하나다.
`unavailable`이면 SKILL.md가 경고를 출력한다.

### 9.2 status

`check_status.py`의 63~65행(키 집합 비교)을 **삭제**하고,
`sync-status/scripts/compare_plugins.py`를 호출하도록 바꾼다.
`compare_mcp.py`와 같은 구조다.

보고 내용:

- 섹션별 `only_local` / `only_repo` / `changed`
- `changed`에는 **값 변경이 포함된다** — `true`→`false`가 보고된다 (결함 B 해소)
- 켬/끔 변경은 별도 문구로 구별한다: `⏻ 껐음(레포는 켜짐)` 같은 식으로.
  값이 확장 포맷이면 "버전 제약 변경"으로 말한다.

status는 **아무것도 바꾸지 않는다.** 읽기 실패는 경고로 보고하고 진행한다.

### 9.3 restore

`sync-restore/scripts/plan_plugins.py`가 `restore_plan`을 세 섹션에 적용해 계획을 낸다.
실행은 SKILL.md가 사용자 확인을 받아가며 한다.

**실행 순서는 의존성 순서다** (브리프 5장 항목 2의 답):

```
1. 마켓플레이스 등록    claude plugin marketplace add <source>
     - always-known 5개는 건너뛴다
2. 플러그인 설치        claude plugin install <id>
     - -y를 붙이지 않는다 (D2)
     - 의존성은 CLI가 알아서 끌어온다
3. 값 맞추기            claude plugin enable|disable <id>
     - 현재 상태와 다를 때만 호출한다 (멱등이 아니다)
4. 설정 채우기          claude plugin install <id> --config k=v
     - 사용자가 값을 준 항목만
```

**2단계 전에 마켓플레이스 등록 여부를 미리 확인한다.** 등록되지 않은 상태로 install하면
CLI가 "플러그인이 없다"와 **똑같은 문구**로 실패해(실측) 사용자가 원인을 알 수 없다.
미확인 시에는 우리가 원인을 말해 준다.

**3단계는 반드시 현재 상태를 읽고 조건부로 호출한다.** `disable`/`enable`은 멱등이 아니라
이미 그 상태면 exit 1이다. 무조건 호출하면 정상 항목이 실패로 보고된다.

#### 삭제 전파 (브리프 5장 항목 4의 답)

`uninstall`이 키를 지우고 `disable`이 `false`로 남기므로 **둘은 구별된다.**

| 레포 상태 | 뜻 | 처방 |
|---|---|---|
| 키가 있고 값이 `false` | 다른 기기가 **껐다** | `disable` 제안 |
| 키가 없고 base에 있었다 | 다른 기기가 **지웠다** | `uninstall` 제안 |

둘 다 **사용자 확인을 받고** 실행한다. 자동으로 하지 않는다.

#### 마켓플레이스 삭제는 제안하지 않는다

`marketplace remove`는 소속 플러그인 키를 **연쇄 삭제**한다(실측).
복원이 이것을 자동 실행하면 사용자가 예상하지 못한 대량 삭제가 일어난다.

→ **마켓플레이스 삭제는 명령만 안내하고 실행하지 않는다.**
`--scope`를 생략하면 모든 스코프에서 제거된다는 점도 함께 알린다.

#### 케이스 4·8의 3선택지

MCP와 같다. "다른 기기가 지웠는데 여기엔 있다"(4)와 "다른 기기가 바꿨는데 여긴 옛 값"(8)은
**안정 상태**이므로 사용자가 고르지 않으면 영원히 유지된다. 각각 3선택지를 준다
(레포 따르기 / 로컬 유지하고 다음 백업에 올리기 / 이번엔 넘어가기).

---

## 10. 실패 처리 (브리프 5장 항목 6의 답)

MCP의 `add-json`은 로컬 쓰기라 등록 자체는 항상 성공했다. **여기는 다르다** —
`install`은 네트워크로 코드를 받아오고 **실제로 실패한다.** 부분 실패가 정상이다.

### 10.1 수집 단위

항목마다 다음을 남긴다.

```
{ "id": "...", "step": "marketplace_add|install|enable|disable|config",
  "command": "실행한 명령 전문", "exit": 1, "stderr": "CLI가 낸 문구 전문" }
```

**stderr를 요약하지 않는다.** CLI의 문구가 사용자에게 가장 유용한 안내인 경우가 많다
(command 소스 플러그인이 대표적이다 — 8.5).

### 10.2 갈래별 안내

| 갈래 | 판별 | 안내 |
|---|---|---|
| 마켓플레이스 미등록 | 우리가 미리 확인 | "먼저 마켓플레이스를 등록해야 합니다" |
| 명령 기반 설치 | stderr에 명령 승인 문구 | CLI 문구 그대로 + 사용자 터미널에서 실행 안내 |
| 예약 이름 | stderr에 `reserved` | "이 이름은 공식 마켓플레이스용으로 예약되어 있습니다" |
| 네트워크·기타 | 그 외 | stderr 전문 + 재시도 안내 |

### 10.3 하나가 실패해도 나머지는 계속한다

항목 단위로 독립이다. 실패 하나로 복원 전체를 중단하지 않는다.
**종료 코드는 0이다** — 그래야 안내가 보인다. `lib/compat.py`가 차단 시에도 0을 내는 것과 같은 이유다.

### 10.4 실패한 항목의 base

**실패한 항목의 base는 전진하지 않는다.** 로컬이 그 값에 동의하지 않았기 때문이다.
`next_base`가 키 단위로 이미 이것을 보장하므로 별도 처리가 필요 없다 —
호출부가 전역 게이트를 두지 않기만 하면 된다.

---

## 11. 마이그레이션 & 하위호환

### 11.1 이 릴리즈에 함께 실린다

3.0.0은 이미 역호환이 없는 릴리즈이고, `lib/compat.py`의 표식·차단·복구가 이미 들어 있다.
`plugins.json` v2도 **같은 릴리즈에 실어** 사용자가 major 전환을 한 번만 겪게 한다.

### 11.2 `min_reader_version`

`sync-metadata.json`의 `min_reader_version`은 major에 묶인 상수다(3.0.0).
`plugins.json` v2는 그 안에 들어가므로 **새 상수가 필요 없다.**

v2.x 기기는 3.0.0 백업을 만나면 이미 차단된다. 그 기기가 `plugins.json`을 파괴하는 경로도
같은 차단으로 막힌다 — 단, **v2.x에는 우리가 가드를 넣을 수 없으므로** 릴리즈 계획 4장의
배포 순서 규칙이 여전히 유일한 확실한 방어다.

> **모든 기기를 3.0.0으로 올린 뒤에 어느 기기에서든 `/sync-backup`을 실행한다.**

### 11.3 v1 → v2 승격

v1 문서(`version` 없음, 두 필드만)는 4.3의 인식 규칙을 통과한다.
읽으면 `pluginConfigs`가 없는 v2로 취급되고, 다음 백업이 `version`·`scope`를 붙여 저장한다.
**마이그레이션 스크립트가 필요 없다.**

### 11.4 base 블롭

기존 base 블롭(`~/.claude/.sync-state/base/plugins.json`)은 애초에 없었다 —
`plugins.json`이 3-way 대상이 아니었기 때문이다. 첫 백업에서 부트스트랩된다.

base가 없으면 `merge`는 **삭제 없이 합집합으로 degrade**한다. "타 기기 추가"와 "내 삭제"를
구별할 수 없기 때문이다. 첫 백업이 아무것도 지우지 않는다는 뜻이고, 이것이 옳다.

---

## 12. 영향 파일 요약

| 파일 | 변경 |
|---|---|
| `lib/keyed_sync.py` | **신규.** 값 무관 키 단위 3-way 코어 |
| `lib/plugin_config.py` | **신규.** 플러그인 어댑터 |
| `lib/mcp_config.py` | 코어 호출로 내부 교체. **공개 시그니처 불변** |
| `skills/sync-backup/scripts/collect_plugins.py` | **신규** |
| `skills/sync-backup/scripts/extract_plugins.py` | **삭제** |
| `skills/sync-backup/SKILL.md` | 5단계 교체, `update_base.py` 인자에 `plugins.json` 추가 |
| `skills/sync-status/scripts/compare_plugins.py` | **신규** |
| `skills/sync-status/scripts/check_status.py` | 63~65행 삭제, 신규 스크립트 호출 |
| `skills/sync-status/SKILL.md` | 플러그인 절 갱신 |
| `skills/sync-restore/scripts/plan_plugins.py` | **신규** |
| `skills/sync-restore/SKILL.md` | 플러그인 복원 절 전면 교체 |
| `tests/test_keyed_sync.py` | **신규.** 코어 단위 |
| `tests/test_plugin_config.py` | **신규.** 어댑터 단위 |
| `tests/test_plugin_scripts.py` | **신규.** 스크립트 계약 |
| `tests/test_plugin_cycle.py` | **신규.** 교대 시나리오 |
| `tests/test_mcp_state_machine.py` | 두 어댑터로 파라미터화 |

---

## 13. 문서 정정 (다섯 곳 + α)

한 곳만 고치면 나머지가 옛 서술을 계속 말한다. MCP 때 이 함정에 걸렸다.

| 문서 | 고칠 것 |
|---|---|
| `README.md` / `README.ko.md` | **"로컬 파일은 절대 자동으로 덮어쓰지 않습니다" 옆의 `plugins.json` 예외 문구를 지운다.** 더 이상 예외가 아니다 |
| `backup-readme.md` / `.ko.md` | "`plugins.json`은 매 백업마다 새로 생성되어 덮어쓰입니다"를 **키 단위 병합**으로 고친다 |
| `sync-backup/SKILL.md` | 42행의 같은 서술. 5단계 절차 |
| `sync-status/SKILL.md` | 플러그인 비교가 값까지 본다는 것 |
| `sync-restore/SKILL.md` | 215행 "없는 것만 설치한다. 기존 플러그인은 제거하지 않는다" → 3상태·삭제 전파 |

새로 적어야 할 한계 (전부 처음 명시되는 것):

- 마켓플레이스 **자동 업데이트 설정은 동기화되지 않는다** (7.2)
- **로컬 디렉토리에서 등록한 마켓플레이스는 동기화되지 않는다** (7.2)
- **의존성으로 자동 설치된 플러그인은 백업하지 않는다** — 부모를 복원하면 따라온다 (D3)
- **명령으로 설치되는 플러그인은 세션 안에서 복원할 수 없다** — 사용자 터미널이 필요하다 (8.5)
- **버전 제약은 복원 시 재현되지 않는다** — CLI에 수단이 없다 (8.4)
- **플러그인 설정 값은 마스킹되어 저장되며, 복원 시 다시 입력한다** (6장)

---

## 14. 검증 방법

MCP의 교훈이 그대로 걸린다.

> **판정표를 100% 덮은 테스트가 전부 통과하는데도 시스템이 데이터를 잃을 수 있다.**

따라서 아래 넷을 모두 요구한다.

1. **판정표 단위 테스트** — 케이스 1~10을 세 섹션 각각에 대해.
2. **반복 적용 고정점** — 같은 로컬로 backup 3회. 2·3회차의 레포 파일과 base가 동일해야 한다.
3. **교대 시나리오** — backup ↔ restore를 실제 스크립트 서브프로세스로 교대 실행.
   기기 2대를 흉내 내어 한쪽 백업이 다른 쪽 항목을 지우지 않음을 확인한다.
4. **실환경 스모크** — 임시 HOME과 로컬 디렉토리 마켓플레이스로 설치·제거를 짝지어 실행.
   (브리프 1-b의 측정 하네스를 재사용한다.)

추가로 **불변식 7**(테스트는 의미 역전을 잡아야 한다)에 따라:

- 문서 계약 검사는 절 단위로 자르고, 순서는 실행 줄을 앵커로 앞뒤를 둘 다 건다.
- 열거형(always-known 5개, 예약 이름 16개)은 **원본에서 뽑아 대조**한다. 하드코딩한 목록을
  하드코딩한 기대값과 비교하면 아무것도 검증하지 않는다.

### 14.1 반드시 있어야 할 회귀 테스트

실측이 드러낸 함정마다 하나씩.

| 테스트 | 무엇을 막는가 |
|---|---|
| 값이 배열·객체인 항목이 왕복 후에도 보존된다 | 값 타입을 bool로 좁히는 회귀 |
| `additionalMarketplaces`만 있는 settings에서 마켓플레이스를 읽는다 | 별칭 누락 |
| `auto: true` 항목이 백업 결과에 없다 | D3 위반 |
| `installed_plugins.json`이 없으면 전량 포함되고 경고가 난다 | 판정 불가를 통과로 접는 회귀 |
| `pluginConfigs` 값이 레포 파일에 평문으로 나타나지 않는다 | 비밀 유출 |
| `version: 3`을 주장하는 문서를 만나면 레포 파일을 건드리지 않는다 | 상위 버전 백업 파괴 |
| always-known 5개가 마켓플레이스 등록 대상에 들어가지 않는다 | 실패할 등록 시도 |
| `enable`/`disable`이 현재 상태와 같으면 호출되지 않는다 | 멱등이 아닌 명령의 거짓 실패 |
| 복원 명령에 `-y`가 들어가지 않는다 | D2 위반 |

---

## 15. 오픈 이슈 (plan에서 확정)

1. **`lib/keyed_sync.py`의 정확한 시그니처.** `normalize`를 위치 인자로 둘지 키워드로 둘지,
   `restore_plan`의 훅 둘을 하나의 정책 객체로 묶을지.
2. **섹션별 보고를 하나로 합칠지.** 세 섹션의 충돌을 각각 보고하면 출력이 길다.
   사용자에게 의미 있는 단위로 묶는 방법.
3. **`pluginConfigs` 선택지 3(이 기기에서는 쓰지 않는다)의 base 기록 방식.**
   레포 값을 base에 쓰면 되지만, 그 항목만 선택적으로 전진시키는 인터페이스가 필요하다.
4. **`extract_plugins.py` 삭제 시점.** 스킬이 새 스크립트를 부르기 전에 지우면 그사이
   백업이 깨진다. 순서를 plan이 정한다.
5. **실환경 스모크를 CI에서 어떻게 돌릴지.** `claude` 바이너리가 없는 환경에서는 건너뛰어야 한다.

---

## 부록 A. 사용자 가치가 나오는 지점

MCP plan에서 가장 유효했던 표기다. **스킬이 새 모듈을 부르기 전까지 사용자 관점의 가치는 0이다.**

| 결함 | 해소되는 시점 |
|---|---|
| A (통째 덮어쓰기) | `collect_plugins.py`가 만들어지고 **`sync-backup/SKILL.md`가 그것을 부를 때** |
| B (켬/끔 미감지) | `compare_plugins.py`가 만들어지고 **`check_status.py`가 그것을 부를 때** |
| C (예외 처리 부재) | 위와 같은 시점 (같은 스크립트가 처리한다) |

코어 추출과 어댑터 작성만으로는 **사용자에게 아무 변화가 없다.** plan은 이 지점을 명시한다.
