# plugins.json 동기화 설계

- 작성: 2026-08-24
- 개정: 2026-08-24 (리뷰 2회차 반영 — Critical 10건, 아래 0장)
- 브랜치: `feat/plugins-sync` (`release/3.0.0`에서 분기)
- 근거 문서: `2026-08-20-plugins-sync-followup-BRIEF.md` (실측 1-b·1-c, 결정 D1~D3)
- 선행 설계: `specs/2026-08-20-mcp-config-source-design.md` (판정표·base 규칙의 원본)
- 리뷰 보고서: `~/.claude/suberpowers/reviews/2026-08-24-claude-sync-plugins-spec-{statemachine,skills}.md`
- 상태: **현행 설계.** plan은 이 문서가 굳은 뒤에 쓴다.

이 문서는 **무엇을 만들 것인가**를 정한다. 어떻게 나눠 구현할지는 plan이 정한다.

---

## 0. 초판이 틀렸던 것 (개정 이유)

초판은 두 건의 설계 리뷰에서 Critical 10건을 받았고 판정은 "구현 착수 불가"였다.
**열 건 중 여덟이 한 뿌리에서 나왔다.**

> 초판은 **"이 키는 동기화하지 않는다"를 `normalize`가 키를 지우는 것으로 표현했다.**
> `normalize`는 로컬·레포·base 세 입력에 모두 적용되므로, 그 표현은 상태 기계에게
> **"로컬에서 그 키가 사라졌다"** 로 읽힌다. 그리고 그것은 판정표에서 **삭제**다.

키를 제거하는 것과 값을 마스킹하는 것은 상태 기계에 대해 전혀 다른 연산인데 초판은 둘을
같은 훅에 넣었다. 그 결과 네 종류의 항목(의존성 플러그인, 로컬 디렉토리 마켓플레이스,
확장 포맷 값, 건너뛴 설정)이 전부 **삭제 전파 경로**가 됐다.

이번 개정의 중심은 코어에 **`held`(판정 보류)** 개념을 넣는 것이다(5.3).
`normalize`는 값 층위 변환에만 쓰고, 키 층위 제외는 전부 `hold`가 맡는다.

그 밖에 초판이 틀렸던 것:

| | 초판 | 사실 |
|---|---|---|
| 8.4 | "배열·객체 값 모두 `install`이 `true`로 평탄화한다(실측)" | **거짓.** 배열은 보존된다. 평탄화는 **객체 형태 한 갈래**뿐이다. 배열에 대한 그 실측은 존재하지 않았다 (재측정으로 확정, 1.2) |
| 11.4 | "합집합 degrade는 아무것도 지우지 않는다" | **불완전.** 양쪽에 있는 키는 **로컬 값이 레포를 덮는다** (`mcp_config.py:317-320`) |
| 7.3 | "MCP의 스테이징 계약을 그대로 쓴다" | **실제 배선과 충돌.** `sync-backup/SKILL.md:285`의 `rm -rf`와 `:398`의 단일 파일 게이트 |
| 11.2 | "v2.x 기기는 3.0.0 백업을 만나면 이미 차단된다" | **거짓.** 가드는 3.0.0에서 처음 도입됐다. 2.x에는 없다 |
| 5.5 | "기존 367개 테스트" | **383개**이고, 5.4가 그중 한 파일의 수정을 요구해 자기모순이었다 |
| 5.4 | "`test_mcp_cycle.py`를 파라미터화한다" | **불가능.** 스크립트 경로·로컬 파일 구조·CLI 의미론에 묶여 있다 |

---

## 1. 배경 & 문제

`plugins.json`은 `~/.claude/settings.json`에서 두 필드를 뽑아 만드는 파생 산출물이다.
대응하는 로컬 파일이 없어 `iter_synced_relpaths`가 열거하지 못하므로 **파일 단위 3-way의
대상이 될 수 없다.** 그 결과 세 가지 결함이 있다.

| | 결함 | 위치 |
|---|---|---|
| A | 매 백업마다 레포 파일을 통째로 재생성 → 타 기기 플러그인 소실 | `extract_plugins.py` |
| B | status가 `enabledPlugins`의 **키 집합만** 비교 → 켬/끔 변경을 못 봄 | `check_status.py:60-76` |
| C | 예외 처리 부재 → `settings.json`이 없거나 깨지면 backup 전체가 중단 | `extract_plugins.py` |

MCP 재설계가 `mcp-servers.json`에 대해 고친 것과 **같은 결함**이다. 해법의 골격도 같다 —
키 단위 3-way 병합, "모르면 안 쓴다" 가드, 읽기 실패와 0개의 구별.

### 1.1 실측이 추가로 드러낸 것

브리프 1-b·1-c의 실측은 결함 세 건보다 **더 위험한 사실 다섯 가지**를 드러냈다.

1. **값이 불리언이 아닐 수 있다.** 값 스키마는 `union([array, boolean, object])`이고
   버전 제약 표현이 실재한다. `bool`로 좁히면 데이터를 파괴한다.
2. **`settings.json`에 평문 비밀이 있다.** `pluginConfigs`가 플러그인 `userConfig` 값을 그대로 들고 있다.
3. **`additionalMarketplaces` 별칭 키가 있다.** 읽지 않으면 마켓플레이스를 통째로 놓친다.
4. **의존성으로 들어온 플러그인이 직접 설치와 구별되지 않는다.** 명시적으로 설치하면
   `auto` 표식이 **되돌릴 수 없게** 지워진다.
5. **`marketplace remove`가 연쇄 삭제한다.** "타 기기가 지웠다"의 원인이 플러그인 단위가 아닐 수 있다.

### 1.2 확장 포맷 값의 실제 거동 (2026-08-24 재측정)

초판이 이 자리를 추측으로 채웠으므로 다시 측정했다. **측정된 것만 적는다.**

| 레포/로컬 값 | 그 플러그인을 `install` | 결과 |
|---|---|---|
| 배열 `["1.0.0"]` | 미설치 → 설치 | **보존됨** |
| 배열 `["1.0.0"]` | 이미 설치 → 재실행 | **보존됨** |
| 객체 `{"version": "1.0.0"}` | 미설치 → 설치 | **`true`로 평탄화됨** |
| 임의 형태 | 그 플러그인을 건드리지 않음 | 형태 무관 **보존됨** |

**아직 모르는 것:** CLI가 "확장 포맷"으로 의도한 형태가 배열인지 객체인지, 그리고 객체 평탄화가
정규화인지 손실인지. 스키마 설명문(`"Also supports extended format with version constraints."`)은
형태를 밝히지 않는다. → **14.2의 실환경 스모크 측정 항목으로 등록한다.**

설계에 필요한 규칙은 이것으로 충분하다:

> `install <id>`는 `enabledPlugins[<id>]`를 다시 쓸 수 있다. 배열은 살아남고 객체는 `true`가 된다.
> **우리 코드는 어느 쪽도 가정하지 않는다** — 건드리지 않은 값은 보존하고,
> 복원 후 로컬 값이 레포와 달라질 수 있다는 것을 전제로 판정한다.

---

## 2. 목표 / 비목표

### 목표

- **G1.** 한 기기의 백업이 다른 기기의 플러그인을 지우지 않는다 (결함 A).
- **G2.** 켬/끔 변경과 설정 값 변경이 status에 보고된다 (결함 B).
- **G3.** `settings.json`을 읽지 못해도 backup 흐름이 종료 코드 0으로 계속된다 (결함 C).
- **G4.** 알아볼 수 없는 `plugins.json`을 만나면 **쓰지 않는다.**
- **G5.** 값 타입 셋(불리언·배열·객체)을 전 구간에서 보존한다. **복원 구간을 포함한다.**
- **G6.** `pluginConfigs`를 마스킹해 동기화하고, 복원 시 값 입력을 **건너뛸 수 있게** 한다.
- **G7.** 의존성으로 자동 설치된 플러그인이 타 기기로 승격 전파되지 않는다.
- **G8.** 상태 기계를 복사하지 않는다. MCP가 검증한 판정표와 **인식 계층**을 공유한다.
- **G9.** 이 기기가 표현할 수 없는 항목은 **레포의 값을 보존**하고, 그 사실을 사용자에게
  해소 가능한 형태로 알린다. **어떤 상태에도 파괴적이지 않은 탈출구가 있다.**

### 비목표 (이번 범위 밖)

- project·local 스코프 플러그인. user 스코프만 다룬다.
- `~/.claude/plugins/cache`의 잔존 버전 디렉토리 정리.
- 플러그인 **버전 고정**. CLI에 버전 지정 설치 수단이 없다.
- `~/.claude/skills/`의 `@skills-dir` 자동 로드 플러그인.
- 마켓플레이스 자동 업데이트 설정(`autoUpdate`). 7.2에서 제외 근거를 밝힌다.

---

## 3. 데이터 소스 — "로컬 상태"의 정의

**두 파일에서 읽되 역할이 다르다.**

| 파일 | 읽는 것 | 역할 |
|---|---|---|
| `~/.claude/settings.json` | `enabledPlugins`, `extraKnownMarketplaces`, `additionalMarketplaces`, `pluginConfigs` | **동기화 대상 값의 유일한 원천** |
| `~/.claude/plugins/installed_plugins.json` | 각 항목의 `auto` 플래그 **하나만** | `hold` 집합을 계산하는 입력 |

`installed_plugins.json`을 값의 원천으로 삼지 않는 이유는 그것이 **`settings.json`에서
파생되기 때문**이다(바이너리 로그: *"Syncing installed_plugins.json with enabledPlugins from
all settings.json files"*).

`claude plugin list --json`을 쓰지 않는 이유는 **"키 부재"와 `false`를 구별하지 못하기 때문**이다.

### 3.1 세 스킬이 같은 로컬 정의를 쓴다

**backup·status·restore가 읽는 `local`은 동일하다.** 스킬마다 다른 필터를 적용하면
같은 기기에서 backup↔restore를 교대할 때 base가 두 정의 사이를 오간다
(restore도 `next_base`를 쓴다 — `plan_mcp.py:62`가 그 본이다).

`auto` 항목은 **로컬에서 빼지 않는다.** `local`에 그대로 두고 `hold` 집합에 넣는다(5.3).
그래야 restore가 "이미 있다"로 보고 재설치하지 않는다 — 재설치하면 `auto` 표식이 영구 소실된다(N6).

### 3.2 읽기 규칙 — 읽기 실패와 "0개"를 구별한다

`mcp_config.read_local_servers`가 세운 구별을 **섹션마다** 적용한다.

| 상태 | 판정 |
|---|---|
| 키가 **없다** | `{}` — 0개, 정상 |
| 키가 있는데 **객체가 아니다**(`null`·배열·문자열 포함) | `LocalConfigUnavailable` |
| `settings.json` 자체가 없거나 파싱 실패 | `LocalConfigUnavailable` |
| 최상위가 객체가 아니다 | `LocalConfigUnavailable` |

`PermissionError` 등 그 외 `OSError`는 전파한다(감싸지 않는다).

**이 규칙이 없으면 `{"enabledPlugins": null}`인 기기에서 "플러그인 0개"로 읽혀
base에 있던 항목 전부가 케이스 3(삭제)으로 판정되고 레포에서 전멸한다.**
결함 C를 고치겠다는 설계가 결함 C의 원인을 로컬 쪽에 남기는 셈이 된다.

### 3.3 별칭 키

`extraKnownMarketplaces`와 `additionalMarketplaces`는 같은 뜻이다. **둘 다 읽는다.**

- 둘 다 존재하면 `additionalMarketplaces`를 **무시한다** (CLI와 같은 규칙).
- 각각에 3.2의 판정을 적용한다. 채택한 쪽이 객체가 아니면 `LocalConfigUnavailable`.
- 쓰는 쪽(복원)은 CLI를 통하므로 이 문제를 겪지 않는다.

### 3.4 `auto` 집합

`installed_plugins.json`의 `plugins[<id>]`는 **배열**이다(스코프별 다중 설치).

```
auto_ids = { id
             for id, entries in installed.get("plugins", {}).items()
             if any(e.get("scope") == "user" and e.get("auto") is True for e in entries) }
```

이 집합은 `hold` 계산의 입력이다(7.2). **로컬에서 키를 지우는 데 쓰지 않는다.**

**읽기 실패 시** — 파일이 없거나 깨졌거나 형태를 알아볼 수 없으면 `auto` 판정이 불가능하다.
초판은 "전량 포함 + 경고"로 정했으나 **그 판단은 base 전진을 고려하지 않았다.**
포함된 `auto` 항목이 레포에 실리고 base가 전진하면, 타 기기 restore가 그것을 설치해
**되돌릴 수 없는 수동 승격**을 일으키고(N6), 이 기기가 복구된 뒤에는 케이스 3으로 삭제 전파한다.
경고 한 줄 뒤에 **다른 기기에서 되돌릴 수 없는 상태 변화**가 일어나므로 "완화 가능"이 성립하지 않는다.

→ **`auto` 판정 불가이면 `enabledPlugins`·`pluginConfigs` 두 섹션을 `skipped`로 처리한다**(9.1.2).
`extraKnownMarketplaces`는 `auto`와 무관하므로 계속 진행한다.

---

## 4. 스키마 v2 — `plugins.json`

### 4.1 형태

세 섹션 키를 **항상** 기록한다(빈 객체라도). 아래 예시는 그 자체로 정합하다 —
모든 플러그인의 마켓플레이스가 존재한다.

```json
{
  "version": 2,
  "scope": "user",
  "enabledPlugins": {
    "figma@claude-plugins-official": true,
    "superpowers@claude-plugins-official": false,
    "suberpower@suberpower": true
  },
  "extraKnownMarketplaces": {
    "suberpower": { "source": { "source": "github", "repo": "june20516/suberpower" } }
  },
  "pluginConfigs": {
    "suberpower@suberpower": { "options": { "apiKey": "<REDACTED>", "region": "kr" } }
  }
}
```

`figma`·`superpowers`의 마켓플레이스 `claude-plugins-official`은 내장이므로
`extraKnownMarketplaces`에 없는 것이 정상이다(8.2).

### 4.2 왜 최상위 필드 이름을 그대로 두는가

**구버전 리더가 계속 읽을 수 있기 때문이다.** `check_status.py:60-76`이
`.get("enabledPlugins", {}).keys()`(`:63-66`)로 읽으므로, 이름을 유지하면 2.x가 v2 문서에서도 같은 키 집합을 얻는다.
감싸면 빈 집합을 읽어 "레포에만 있음"을 오보한다.

MCP가 v1 배열 → v2 객체로 형태를 바꾼 것과 다른 선택인 이유가 있다 — MCP의 v1은 배열이라
키 단위 병합 자체가 불가능했지만, 여기는 **v1이 이미 올바른 모양**이다.

### 4.3 쓰기 규칙

- 세 섹션 키를 **항상 기록한다.** 빈 섹션도 `{}`로 쓴다.
  생략하면 플러그인 0개인 기기의 백업 결과가 `{"version": 2, "scope": "user"}`가 되고,
  다음 백업의 인식 규칙(4.4)에 걸려 **영구 skip**된다. 파일을 지워도 같은 모양이 다시 만들어져
  탈출구가 통하지 않는다.
- `sort_keys=True`, `indent=2`, `ensure_ascii=False`. `dump_backup`과 같은 직렬화 옵션을 쓴다
  (지문 비교와 디스크 표현을 일치시키기 위해서다).

### 4.4 인식 규칙 — "모르면 안 쓴다"

문서를 **인식한다**고 판정하는 조건은 전부 참일 때뿐이다:

1. 최상위가 객체다.
2. `version`이 없거나 `SCHEMA_VERSION`(=2) 이하다.
   숫자(int·float)로 더 높은 값을 주장하면 인식하지 않는다. `bool`은 버전 주장이 아니므로 제외하고,
   문자열은 손으로 고친 문서를 막지 않기 위해 통과시킨다.
3. **아는 섹션(`enabledPlugins`·`extraKnownMarketplaces`·`pluginConfigs`) 중 적어도 하나가 존재한다.**
4. **존재하는 모든 아는 섹션이 객체다.** 하나라도 객체가 아니면 인식하지 않는다.

조건 4가 없으면 `{"enabledPlugins": {...}, "extraKnownMarketplaces": "손상"}`이 인식되어
손상된 섹션이 "0개"로 읽히고 **로컬 값으로 덮인다.** 조건 3이 `{"foo": 1}`에 대해 막는 것과
같은 사고가 섹션 단위로 열리는 것이다.

**부재 섹션의 의미.** 인식된 문서에서 없는 섹션은 `{}`(이력이 비어 있었다)로 읽는다.
문서 자체를 인식하지 못하면 **세 섹션 모두 `None`**(신뢰할 수 없는 이력)이다.
이 구별이 불변식 2의 섹션 단위 판이다.

**탈출구.** 인식 실패로 backup이 계속 건너뛰면 사용자는 레포에서 파일을 지워야 한다.
임시 클론에서 지우면 다음 `git pull`이 되살리므로 안내 문구는 실행 가능한 형태여야 한다:

```
cd <레포> && git rm plugins.json && git commit -m "reset plugins.json" && git push
```

세 함수가 이 판정을 공유한다 — `parse_base`(이력), `load_backup`(레포), `parse_backup`(관대한 읽기).
**세 곳이 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고, 그 비대칭이 상위 버전 백업을 파괴한다.**

---

## 5. 공용 코어 추출 — `lib/keyed_sync.py`

### 5.1 왜 추출하는가

브리프는 "플러그인은 `redact`·`secret_keys`·`restorable`이 전부 필요 없다"고 적었으나
**실측이 반증했다** — 셋 다 필요하다(D1, 1-c C3). 두 도메인이 **같은 훅을 같은 자리에서 쓴다.**

추출의 실질적 이득은 셋이다:

1. **판정 로직 단일화.** 판정표 케이스 1~10이 한 벌만 존재한다.
2. **인식 계층 단일화.** `_claims_newer_schema`는 이 프로젝트가 **float 버전 우회**를 발견하고
   고친 함수다. 두 벌이 되면 다음 우회가 한쪽에만 반영된다.
3. **예외 클래스 단일화.** 현행 스크립트는
   `except (mc.LocalConfigUnavailable, mc.UnknownBackupSchema, OSError)`로 잡는다
   (`collect_mcp.py:62`, `compare_mcp.py:38`). 클래스가 두 벌이면 튜플을 늘려야 하고,
   **늘리는 것을 잊으면 traceback으로 죽어 결함 C가 되살아난다.**

(초판은 "테스트 승계"를 최대 이득으로 들었으나 과장이었다 — 실제 승계분은 고정점 테스트 한 파일이다.)

### 5.2 경계

```
lib/keyed_sync.py     ← 값 무관 키 단위 3-way 코어 + 인식 계층 (신규)
lib/mcp_config.py     ← MCP 어댑터 (기존 파일이 얇아짐)
lib/plugin_config.py  ← 플러그인 어댑터 (신규)
```

**코어가 제공하는 것:**

| 이름 | 계약 |
|---|---|
| `LocalConfigUnavailable` | 로컬 설정을 읽지 못했다. 어댑터가 **re-export**한다 |
| `UnknownBackupSchema` | 백업 문서를 알아볼 수 없다. 어댑터가 **re-export**한다 |
| `claims_newer_schema(version, schema_version)` | 상위 버전 주장 판정 (float 우회 포함) |
| `decode(data)` | JSON 디코드. 구문 오류면 `BROKEN` 센티널 |
| `load_backup(path, recognize)` | 레포 읽기. 인식 실패 시 `UnknownBackupSchema` |
| `parse_base(data, recognize)` | 이력 읽기. 못 믿으면 `None` |
| `parse_backup(data, recognize)` | 관대한 읽기. 실패는 빈 매핑 |
| `same(a, b)` | 키 정렬 JSON 지문 비교 (정규화를 받지 않는다) |
| `diff(local, repo, *, normalize, hold)` | `only_local`/`only_repo`/`changed`/**`held`** |
| `next_base(local, base, merged, *, normalize, hold)` | 로컬이 동의한 키만 전진. `held`는 이전 base 유지 |
| `merge(local, repo, base, *, normalize, hold)` | 판정표 케이스 1~10 + `held` 처리 |
| `restore_plan(local, repo, base, *, normalize, hold, restorable, secret_keys)` | 버킷 9개 + **`held`** |

`normalize`·`hold`·`restorable`·`secret_keys`는 **필수 키워드 인자다. 기본값을 두지 않는다.**
초판은 `restorable`의 기본값을 `True`로 뒀는데, 그것은 이 프로젝트가 아홉 번 반복해서 고친
형태("모르는 입력의 기본 갈래가 통과")와 같은 모양이다.

`normalize`의 계약은 **멱등**이다. 그렇지 않으면 로컬(원본)과 레포(정규화됨)가 수렴하지 않는다.

**`normalize`는 값 층위 변환만 한다.** 키를 추가하거나 제거해서는 안 된다.
키 층위 제외는 전부 `hold`가 맡는다. 이 분리가 이 개정의 핵심이다(0장).

### 5.3 `held` — 판정 보류 키

```
hold(local, repo, base) -> set[str]
```

**의미:** *"레포의 값은 옳다. 이 기기의 로컬은 그것을 표현할 수 없거나, 표현하지 않기로 했다."*

`held` 키 `k`에 대해:

| 연산 | 동작 |
|---|---|
| `merge` | 판정표를 타지 않는다. **레포에 `k`가 있으면 레포 값을 그대로 결과에 싣는다.** 없으면 결과에도 없다 |
| 삭제 판정 | 케이스 3·4·5에 **들어가지 않는다** |
| `next_base` | **이전 base 값을 그대로 유지한다.** 전진하지 않는다 |
| `diff` | 세 버킷 어디에도 넣지 않고 `held` 버킷에만 넣는다 |
| `restore_plan` | `held` 버킷에만 넣는다. **어떤 CLI 명령의 대상도 되지 않는다** |
| status 보고 | 별도 문구로 보고하거나 침묵한다. `only_local`/`changed`에 넣지 않는다 |

**MCP 어댑터의 `hold`는 항상 빈 집합이다.** 따라서 MCP 동작은 바뀌지 않고 5.5의 회귀 금지가 지켜진다.

### 5.4 어댑터가 채우는 것

| 훅 | `mcp_config` | `plugin_config` |
|---|---|---|
| `recognize` | v1 배열 + v2 `{servers}` | 4.4의 네 조건 |
| `normalize` | `redact` (headers/env 값 마스킹) | 7.2의 섹션별 값 층위 정규화 |
| `hold` | **항상 `set()`** | 7.3의 네 종류 |
| `restorable` | 이름 규칙 + command/url+type | 8장의 판정 |
| `secret_keys` | headers/env의 (field, key) | `pluginConfigs.options`의 키 |

### 5.5 회귀 금지 — 무엇이 바뀌지 않는가

- `mcp_config`의 **공개 시그니처·동작·예외 타입은 바뀌지 않는다.**
  `read_local_servers` `redact` `secret_keys` `parse_backup` `parse_base` `load_backup`
  `dump_backup` `same` `diff` `next_base` `merge` `restorable` `restore_plan`
  `SENTINEL` `SCHEMA_VERSION` `BACKUP_RELPATH` `LocalConfigUnavailable` `UnknownBackupSchema`.
- **위치 인자 순서는 현행 `mcp_config`를 따른다.** 특히 `next_base(local, base, servers)`의
  세 번째 인자는 코어에서 `merged`로 불리지만 **의미와 위치가 같다.** 순서를 바꾸면 조용히 깨진다.
- private 이름(`_recognized_servers`, `_claims_newer_schema`, `_redact_field`, `_fingerprint`, `_BROKEN`)을
  직접 참조하는 테스트·스크립트는 **없다**(전수 확인). 따라서 어댑터가 얇은 래퍼만 남겨도 안전하다.
- **`tests/test_mcp_config.py`·`test_mcp_scripts.py`·`test_mcp_cycle.py`는 수정 없이 통과해야 한다.**
- `tests/test_mcp_state_machine.py`는 **어댑터·값 픽스처를 주입받는 형태로 재작성**되며,
  재작성 전후로 MCP 어댑터에 대한 단정이 하나도 약해지지 않아야 한다.
- 현재 테스트 수는 **383개**다.

### 5.6 교대 시나리오 테스트는 승계할 수 없다

`tests/test_mcp_cycle.py`는 어댑터가 아니라 **MCP 스크립트와 MCP 로컬 파일 구조**에 묶여 있다 —
`collect_mcp.py`/`plan_mcp.py`의 절대 경로 상수(19-21행), `~/.claude.json`을 직접 쓰는
`Device.set_local`(38-41행), `add-json`을 dict 대입으로 흉내 내는 `Device.restore`(72-77행).

플러그인은 **두 파일**을 흉내 내야 하고, CLI 의미론이 훨씬 복잡하다 —
`install`은 멱등이지만 `enable`/`disable`은 **멱등이 아니고**(exit 1),
`uninstall`은 `pluginConfigs`까지 지우며, `marketplace remove`는 **연쇄 삭제**한다.

→ `tests/test_plugin_cycle.py`를 **새로 쓴다.** 하네스 구조만 본으로 삼는다.
에뮬레이터 계약은 14.1에 따로 규정한다.

---

## 6. 비밀 처리 — `pluginConfigs` (D1)

### 6.1 마스킹

`pluginConfigs[<id>].options`의 **값만** `<REDACTED>`로 치환하고 **키 이름은 보존**한다.
키 이름을 보존해야 복원 시 **레포 파일만 보고 "어떤 값을 물어야 하는지"** 를 알 수 있다.

`options` 외의 필드는 그대로 둔다. `options`가 객체가 아니면 필드 전체를 문자열 `<REDACTED>`로 바꾼다.
마스킹은 **비교 직전 양쪽에 적용**한다.

### 6.2 값이 없는 항목

`options`가 비었거나 `pluginConfigs`에 항목이 없는 플러그인은 물어볼 것이 없다. `add` 버킷으로 간다.

### 6.3 입력·건너뛰기·부분 입력

`install --config`는 **부분 병합**이다 — 지정하지 않은 키는 보존된다(N2).
따라서 세 가지 결과가 가능하고, 셋 다 1급 상태다.

| 결과 | 처리 |
|---|---|
| **전부 입력** | `install --config k=v ...` 실행. 다음 status에서 in_sync |
| **일부 입력** | 입력한 키만 `--config`로 채운다. **입력하지 않은 키 때문에 항목이 계속 `changed`가 되므로 그 항목을 `held`로 만든다**(6.4) |
| **전부 건너뜀** | 플러그인은 설치하고 설정만 비운다. 항목을 `held`로 만든다 |

**값을 입력하지 않아도 플러그인 자체는 설치한다.** 나중에 채우는 방법을 보고서에 안내한다:

```
claude plugin install <id> --config <key>=<value> --scope user
```

### 6.4 탈출구는 `held`다 — base를 건드리지 않는다

초판은 *"레포 값을 그대로 base에 기록해 확정한다"*를 탈출구로 제시했다. **그것은 파괴적이다.**

```
선택지 실행 후:  L(pluginConfigs) 에 delta 없음
                 R 에 delta = {"options": {"apiKey": "<REDACTED>"}}
                 S 에 delta = 레포 값        ← 방금 기록한 것
다음 backup:     L없음 / R있음 / S있음  →  케이스 3 = "로컬에서 삭제됨"
                 → 레포에서 delta 의 pluginConfigs 항목이 제거된다
```

기기 B가 "이 기기에서는 안 쓴다"고 말했을 뿐인데 **기기 A가 백업해 둔 "이 플러그인은 어떤 설정 키를
갖는가"라는 정보가 레포에서 사라진다.** 그것은 6.1이 지키려던 바로 그 자산이다.

MCP 7.7의 "로컬 유지"가 안전한 이유는 **그쪽은 로컬에 그 키가 존재하기 때문**이다 →
다음 백업이 케이스 7(로컬만 변경)이 되어 push된다. 플러그인의 건너뛰기는 로컬에 키가 아예 없으므로
같은 base 조작이 케이스 3(삭제)으로 착지한다. 초판은 형태만 옮기고 착지점을 확인하지 않았다.

**대신 `held`를 쓴다.** 사용자의 선택은 기기 로컬 상태 파일에 남는다:

```
~/.claude/.sync-state/plugins-held.json
{ "pluginConfigs": { "delta@mkt": "<레포 값의 sha256 지문>" } }
```

- `hold`가 이 파일을 읽어, **지문이 현재 레포 값과 일치하는 키만** `held`로 만든다.
- `held`이므로 push되지 않고, 삭제로 판정되지 않고, base가 전진하지 않는다. **레포 값은 그대로 보존된다.**
- **레포 값이 바뀌면 지문이 달라져 자동으로 해제된다** — 다시 보고된다. 초판이 약속한 동작 그대로다.
- 사용자가 마음을 바꾸면 restore에서 다시 값을 입력할 수 있다(그때 항목을 파일에서 지운다).

### 6.5 status도 `held`를 안다

초판 9.2는 *"`compare_mcp.py`와 같은 구조"*라고 적었는데, `compare_mcp.py`는 **base를 읽지 않는다**
(헤더: *"base는 읽지도 갱신하지도 않는다"*). 그 구조를 그대로 쓰면 6.4의 탈출구가
**status를 조용하게 만들지 못한다** — restore만 조용해지고 `/sync-status`는 매번 보고한다.

→ `compare_plugins.py`는 **`hold`를 계산해 `held` 키를 별도 버킷으로 보고하거나 침묵한다.**
`hold`는 `plugins-held.json`·`installed_plugins.json`·로컬/레포 값만 있으면 계산되므로
**base를 읽지 않아도 된다.** `compare_mcp.py`의 읽기 전용 성질은 유지된다.

---

## 7. 키 단위 3-way 병합

### 7.1 병합 단위 — 한 문서, 세 섹션

`plugins.json`은 **하나의 relpath**이고 base 블롭도 하나다. 그 안에서 세 섹션이
**각각 독립적으로** 키 단위 3-way를 거친다.

**섹션 간에 게이트를 두지 않는다.** 마켓플레이스 하나가 충돌 중이어도 플러그인의 base는 계속 전진한다.

판정표(케이스 1~10)와 base 전진 규칙은 `specs/2026-08-20-mcp-config-source-design.md`
7.2·7.3을 그대로 따른다. **여기서 다시 적지 않는다** — 두 벌이 되면 갈라진다.

**어휘 대응.** MCP 판정표는 L/R/S를 *서버 이름 → config*로 서술한다.
여기서는 **이름 → 각 섹션의 키, config → 각 섹션의 값**으로 읽는다.

| 섹션 | 키 | 값 |
|---|---|---|
| `enabledPlugins` | 플러그인 id (`<plugin>@<marketplace>`) | 불리언·배열·객체 |
| `extraKnownMarketplaces` | 마켓플레이스 이름 | `{"source": {...}}` |
| `pluginConfigs` | 플러그인 id | `{"options": {...}}` |

### 7.2 섹션별 정규화 (값 층위만)

**`enabledPlugins` — 항등함수.** 값을 좁히지 않는다.

**`extraKnownMarketplaces` — `autoUpdate` 필드를 제거한다.**
값에는 실재하지만 **`marketplace add`에 이를 설정하는 옵션이 없다**(실측).
비교에 넣으면 한 기기가 켜고 다른 기기가 껐을 때 **수렴시킬 CLI 수단이 없어** 영구 보고된다.
이것은 **필드 제거이지 키 제거가 아니므로** 값 층위에서 안전하다.
→ 문서에 "마켓플레이스 자동 업데이트 설정은 기기별 설정이며 동기화되지 않는다"를 명시한다.

**`pluginConfigs` — `redact`.** 6.1 참조.

### 7.3 `hold` — 네 종류

| # | 종류 | 섹션 | 근거 |
|---|---|---|---|
| H1 | `auto: true` 의존성 플러그인 | `enabledPlugins`, `pluginConfigs` | D3 / N6 |
| H2 | `source.source == "directory"`인 마켓플레이스 **와 그 소속 플러그인** | 세 섹션 모두 | 아래 |
| H3 | **레포 값이 객체 형태**인 플러그인 | `enabledPlugins` | 1.2 |
| H4 | 사용자가 보류를 선택한 `pluginConfigs` 항목 | `pluginConfigs` | 6.4 |

**H2가 소속 플러그인까지 포함하는 이유.** 초판은 마켓플레이스만 제외하고 `foo@mylocal` 같은
플러그인 키는 그대로 백업했다. 그러면 기기 B의 restore가 매번 그것을 `add` 버킷에 담고
"먼저 마켓플레이스를 등록해야 합니다"를 낸다 — **기기 B에는 등록할 소스 자체가 없다.**
사용자가 할 수 있는 일이 없고 status·restore가 영원히 반복한다.
제외가 정확히 그 "해소 불가 상태"를 플러그인 섹션에 새로 만든 것이다.
→ 생산 측(기기 A)에서 **플러그인 키까지 `held`**로 만들어 애초에 올리지 않는다.
소비 측(기기 B)의 안전망은 8.1의 `unrestorable` 규칙이다 — 이미 레포에 실린 옛 항목을 위해서다.

**H3이 "레포 값 기준"인 이유.** 로컬 값은 복원이 바꿔 놓았을 수 있다(1.2).
레포 값을 기준으로 하면 **상태가 없고**(stateless) 판정이 안정적이다.
레포에 객체 형태가 있는 한 이 기기는 그것을 표현할 수 없으므로 보류가 옳다.
배열은 보존되므로 `held`가 아니다 — 정상 동기화된다.

### 7.4 base 저장과 갱신 시점 — 스테이징 계약 (실제 배선 기준)

초판은 *"MCP의 스테이징 계약을 그대로 쓴다"*고 넘겼으나 **현행 SKILL.md와 어긋난다.**
확인된 충돌 셋:

1. `sync-backup/SKILL.md:285`가 `rm -rf "$MCP_STAGING"`를 **MCP 수집 직전에** 한다.
   플러그인 수집을 앞 단계에 두면 그 산출물이 지워진다.
2. `:398`의 게이트가 `[ -f "$MCP_STAGING/mcp-servers.json" ]` **한 파일에만** 걸려 있다.
   MCP가 skipped이고 플러그인이 ok인 실행에서는 블록 자체가 실행되지 않는다.
3. `update_base.py:27`은 파일이 없으면 **경고만 내고 조용히 건너뛴다.**

이 셋이 겹치면 `base/plugins.json`이 **영원히 생성되지 않는다.** 그러면 `merge`가 매번
`base=None` 합집합 degrade를 타고 **케이스 3·4가 영영 발생하지 않는다** — G1은 지켜지지만
삭제 전파가 죽고, 사용자가 어떤 명령으로도 해소할 수 없다. **그리고 이것은 조용하다.**

→ spec이 배선을 직접 정한다.

```bash
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"
rm -rf "$BASE_STAGING"                                   # 수집 단계들보다 앞에서 딱 한 번

python3 "$SYNC_SCRIPTS/collect_plugins.py" "$SYNC_REPO" "$BASE_STAGING" > …   # 5단계
python3 "$SYNC_SCRIPTS/collect_mcp.py"     "$SYNC_REPO" "$BASE_STAGING" > …   # 6단계 (rm -rf 없음)

# push 후 — 존재하는 rel 만 넘긴다 (파일 존재 = "그 단계가 skip 아님")
RELS=()
for rel in mcp-servers.json plugins.json; do
  [ -f "$BASE_STAGING/$rel" ] && RELS+=("$rel")
done
if [ "$REPO_HAS_CONTENT" = "1" ] && [ ${#RELS[@]} -gt 0 ]; then
  python3 "$SYNC_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"
fi
```

`sync-restore/SKILL.md:369`의 같은 자리도 함께 고친다 — `apply-base` 산출물이 같은 디렉토리를 쓴다.

**`update_base.py`에 레포 경로를 넘기지 않는다.** 넘기면 `base ← 레포 파일 바이트`가 되어
다음 백업이 타 기기 항목을 지운다.

**"커밋할 변경 없음" 경로에서도 base를 갱신한다.** 그래야 restore 없이 backup만 하는 기기에서
부트스트랩된다.

### 7.5 섹션 단위 보류의 base 처리

base 블롭은 하나인데 섹션 하나가 `skipped`일 수 있다(3.4). 그때
`collect_plugins.py`는 **이전 base의 그 섹션을 그대로 실어 다시 써야 한다.**

```
next_base 문서 = { 판정한 섹션: 새 next_base,
                   skipped 섹션: 이전 base의 같은 섹션 (pass-through) }
```

이것이 세 섹션이 서로 다른 정규화를 쓰는데 base 블롭이 하나인 조합의 **유일한 실질적 함정**이다.
정규화가 값 층위로 한정되기만 하면 나머지는 섹션 독립으로 안전하다.

### 7.6 병합 결과의 정합성 보고 (차단하지 않는다)

게이트를 두지 않으면 레포 문서가 이 상태에 도달할 수 있다:

```
enabledPlugins         = {"alpha@bar": true}     ← 기기 A 가 올림
extraKnownMarketplaces = {}                      ← 기기 B 에서 bar 가 케이스 3 으로 제거됨
```

런타임은 조용히 건너뛰고(*"Skipping orphaned enabledPlugins entry … marketplace not registered"*),
새 기기 restore는 **"플러그인이 없다"와 같은 문구**로 실패한다.

→ 병합 직후 검사 한 줄: 결과 `enabledPlugins` 각 id의 마켓플레이스 부분이
`결과 extraKnownMarketplaces ∪ always-known 5개`에 있는지 확인하고, 없으면 `orphaned`로 보고한다.
**차단하지 않는다.** 9.1의 출력 JSON에 최상위 `orphaned` 키를 둔다.

---

## 8. 복원 가능성 판정 (`restorable`)

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

그리고 **레포의 `extraKnownMarketplaces`에도 없고 always-known 5개도 아닌 마켓플레이스에
속한 id는 `unrestorable`이다.** 등록할 소스가 레포 어디에도 없으므로 시도해도 반드시 실패한다.
(H2의 소비 측 안전망 — 이미 레포에 실린 옛 항목을 위해서다.)

### 8.2 always-known 집합

위 다섯 이름은 **마켓플레이스 등록 대상에서 제외**한다.
`claude-plugins-official`은 이미 자동 설치되어 있어 등록이 무의미하고, 나머지 넷은 실패한다.

### 8.3 예약 이름 — always-known이 우선한다

공식 예약 13개: `claude-code-marketplace` `claude-code-plugins` `claude-plugins-official`
`anthropic-marketplace` `anthropic-plugins` `agent-skills` `anthropic-agent-skills`
`life-sciences` `knowledge-work-plugins` `claude-for-legal` `claude-for-financial-services`
`financial-services-plugins` `first-party-plugins`.
커뮤니티 예약 3개: `claude-community` `claude-plugins-community` `healthcare`.

두 집합은 `claude-plugins-official` 하나에서 교차한다. **always-known 판정이 우선한다** —
그 이름은 등록 대상에서 빠지므로 예약 갈래에 도달하지 않는다.

나머지 15개는 **미리 거르지 않는다.** 정당한 소유자일 수 있으므로 시도하고, 실패하면
"예약된 이름이라 거부되었다"로 갈래를 구별해 보고한다.

### 8.4 확장 포맷 값 — `held`로 보호한다

1.2의 재측정에 따라 초판을 다시 쓴다.

- **배열 값**은 `install`을 통과해도 보존된다. 특별 처리가 없다. 정상 동기화된다.
- **객체 값**은 그 플러그인을 `install`하면 `true`로 평탄화된다.
  → 레포 값이 객체 형태인 키는 **`held`**(H3)다. 설치는 하되 **push하지 않으므로
  레포의 객체 값이 보존된다.** 로컬은 `true`로 동작한다.
- restore는 이 항목을 `both_changed`(케이스 9)로 부르지 **않는다.**
  "양쪽이 모두 바뀌었습니다"는 사실이 아니다. **"이 기기는 버전 제약을 표현할 수 없어
  레포 값을 보존합니다"** 라는 별도 갈래로 보고한다.

이것이 G5를 복원 구간까지 지키는 방법이다. 초판은 비교·저장 구간에서만 지키고
복원 구간에서 깨뜨린 뒤 그 결과를 저장 구간으로 되돌려보냈다.

### 8.5 command 소스 플러그인 (D2)

마켓플레이스가 명령으로 설치를 선언한 플러그인은 **세션 안에서 설치할 수 없다.**
`-y`를 붙여도 무시된다(실측). 우회할 대상이 아니라 **그대로 존중할 경계**다.

미리 알 수 없으므로 시도하고, 실패 시 CLI가 출력한 문구를 **그대로** 전달한다.
CLI가 이미 실행할 명령 전문과 승인 방법을 알려준다.

### 8.6 마켓플레이스

`marketplace add`는 **문자열 인자**를 받는데 `extraKnownMarketplaces`의 값은 **객체**다.
출처 종류별로 인자를 만든다.

| `source.source` | 인자 | 비고 |
|---|---|---|
| `github` | `<repo>` (예: `june20516/suberpower`) | 복원 가능 |
| `url` / `git` | 해당 URL 문자열 | 복원 가능 |
| `directory` | — | H2로 `held`이므로 여기 오지 않는다 |
| 그 밖 / 인자를 만들 수 없음 | — | **`unrestorable`** |

"시도한다"가 실행 가능한 명령으로 번역되지 않으면 `unrestorable`이다.

---

## 9. 스킬별 동작

### 9.1 backup

새 스크립트 `sync-backup/scripts/collect_plugins.py <레포 경로> <스테이징 디렉토리>`.
`extract_plugins.py`는 삭제한다(12장·15장 오픈이슈 4).

#### 9.1.1 흐름

```
1. 로컬 읽기 (3.2 규칙)      settings.json         → 세 섹션
                             installed_plugins.json → auto 집합
2. hold 계산 (7.3)           plugins-held.json 포함
3. 레포 읽기  load_backup()  → UnknownBackupSchema면 status: skipped
4. 이력 읽기  parse_base()   → 못 믿으면 None (합집합 degrade)
5. 섹션별 merge
6. 정합성 검사 (7.6)         → orphaned 보고
7. 스테이징에 next_base 기록  ← 먼저 (7.5의 pass-through 포함)
8. 레포에 병합 결과 기록      ← 나중
```

7·8의 순서가 중요하다. 레포 쓰기가 실패하면 SKILL.md가 `update_base.py`를 호출하지 않으므로
base가 전진하지 않는다.

#### 9.1.2 섹션 단위 skip

| 조건 | 결과 |
|---|---|
| `settings.json` 읽기 실패 (3.2) | **전체** `status: skipped`. 레포·스테이징 모두 손대지 않는다 |
| 레포 문서 인식 실패 (4.4) | **전체** `status: skipped` |
| `installed_plugins.json` 판정 불가 (3.4) | `enabledPlugins`·`pluginConfigs` **두 섹션만** skipped. base는 pass-through(7.5) |

어느 경우든 **종료 코드는 0**이다 (결함 C 해소, 불변식 2).

#### 9.1.3 출력 JSON

```json
{
  "status": "ok",
  "orphaned": ["alpha@bar"],
  "sections": {
    "enabledPlugins": {
      "status": "ok",
      "conflicts": { "repo_kept": [], "repo_absent": [] },
      "deleted": [], "local_stale": [],
      "repo_ahead": { "present": [], "absent": [] },
      "held": { "auto": [], "local_marketplace": [], "extended_value": [] }
    },
    "extraKnownMarketplaces": { "...": "같은 모양" },
    "pluginConfigs": { "...": "같은 모양 + held.declined" }
  }
}
```

섹션이 skipped면 그 섹션은 `{"status": "skipped", "reason": "..."}`이다.

### 9.2 status

`check_status.py:60-76`(키 집합 비교)을 **삭제**하고 `sync-status/scripts/compare_plugins.py`를
호출하도록 바꾼다. `sync-status/SKILL.md`에 호출줄과 skipped 분기 문단을 새로 넣는다
(현행 116·120행이 MCP에 대해 하는 것과 같은 형태).

보고 내용:

- 섹션별 `only_local` / `only_repo` / `changed` / **`held`**
- `changed`에는 **값 변경이 포함된다** — `true`→`false`가 보고된다 (결함 B 해소)
- 켬/끔 변경은 별도 문구로 구별한다. 값이 확장 포맷이면 "버전 제약"으로 말한다
- **`held`는 `only_local`/`changed`에 넣지 않는다.** 종류별 문구로 보고하거나 침묵한다
  (의존성으로 설치된 플러그인이 매번 "backup 시 추가"로 보고되면 **거짓이고 해소 불가능하다** —
  3.1에 따라 백업하지 않으므로 다음 백업에도 추가되지 않는다)
- `only_repo`인데 `unrestorable`이면 **"restore 시 설치"가 아니라
  "이 기기에서는 복원할 수 없습니다"** 로 말한다

status는 **아무것도 바꾸지 않는다.** base를 읽지도 갱신하지도 않는다(6.5).

### 9.3 restore

`sync-restore/scripts/plan_plugins.py`가 `restore_plan`을 세 섹션에 적용해 계획을 낸다.
`plan_mcp.py`와 같이 **`apply-base` 서브명령**을 갖는다(9.3.4).

#### 9.3.1 실행 순서와 스코프

```
1. 마켓플레이스 등록   claude plugin marketplace add <인자> --scope user
                        - always-known 5개는 건너뛴다
2. 플러그인 설치        claude plugin install <id> --scope user
                        - -y를 붙이지 않는다 (D2)
                        - 의존성은 CLI가 알아서 끌어온다
3. 값 맞추기            claude plugin enable|disable <id> --scope user
                        - 현재 상태와 다를 때만 호출한다 (멱등이 아니다)
4. 설정 채우기          claude plugin install <id> --config k=v --scope user
                        - 사용자가 값을 준 항목만
```

**`--scope user`를 반드시 명시한다.** help는 기본값이 `user`라고 적고 실측 출력도 `(scope: user)`였지만,
스킬은 임시 레포 디렉토리에서 실행되고 기본값은 바뀔 수 있다. MCP restore가 같은 이유로
`--scope user`를 못 박아 두었다. 기본값에 기대면, 복원된 플러그인이 `~/.claude/settings.json`에
나타나지 않아 **backup이 못 보고 status가 `only_repo`를 영구 보고한다** — 조용히 아무것도
복원되지 않은 것과 같은 상태다.

**`held` 키는 어떤 CLI 명령의 대상도 되지 않는다.**

**2단계 전에 마켓플레이스 등록 여부를 미리 확인한다.** 등록되지 않은 상태로 install하면
CLI가 "플러그인이 없다"와 **똑같은 문구**로 실패해 사용자가 원인을 알 수 없다.

#### 9.3.2 단계 간 의존 실패

1단계가 실패한 마켓플레이스에 속한 플러그인은 **2단계를 시도하지 않는다.**
`blocked` 갈래로 수집하고 원인(1단계 실패)을 함께 보고한다.
시도하면 CLI가 모호한 문구로 실패해 **거짓 실패를 양산**하고, 사용자가 진짜 원인을 찾지 못한다.

같은 규칙이 3·4단계에도 적용된다 — 2단계가 실패한 id는 3·4단계를 건너뛴다.

#### 9.3.3 삭제 전파

`uninstall`이 키를 지우고 `disable`이 `false`로 남기므로 **둘은 구별된다.**

| 레포 상태 | 뜻 | 처방 |
|---|---|---|
| 키가 있고 값이 `false` | 다른 기기가 **껐다** | `disable` 제안 |
| 키가 없고 base에 있었다 | 다른 기기가 **지웠다** | `uninstall --scope user` 제안 |

둘 다 **사용자 확인을 받고** 실행한다.

**부재는 `false`가 아니다.** 레포에 키가 아예 없는 항목을 `disable` 대상으로 삼지 않는다 —
매니페스트 기본값(`defaultEnabled`, 기본 `true`)에 위임하는 상태이므로 의미가 반대다.

#### 9.3.4 케이스 4·5·8·9의 3선택지

`restore_plan`의 `local_stale`은 **케이스 4와 5를 모두** 담고, `both_changed`는 케이스 9다.
넷 다 **안정 상태**이므로 사용자가 고르지 않으면 영원히 유지된다. 문구를 갈라 적는다.

| 케이스 | 상황 | 문구 |
|---|---|---|
| 4 | 다른 기기가 지웠고 이 기기는 base와 같다 | "다른 기기가 지웠습니다" |
| 5 | 다른 기기가 지웠는데 이 기기에서 값을 바꿨다 | "다른 기기가 지웠는데 이 기기에서 바꿨습니다" |
| 8 | 다른 기기가 바꿨고 이 기기는 옛 값이다 | "다른 기기가 변경했습니다" |
| 9 | 양쪽이 다르게 바꿨다 | "양쪽이 모두 바뀌었습니다. 채택하면 이 기기의 변경이 사라집니다" |

세 선택지: **레포 따르기 / 로컬 유지(다음 백업에 올리기) / 이번엔 넘어가기.**
"로컬 유지"는 `base ← 레포 값`으로 구현한다 — 로컬에 키가 있으므로 다음 백업이
케이스 7(로컬만 변경)로 착지해 push된다. (키가 없는 상태에는 이 처방을 쓰지 않는다 — 6.4 참조.)

#### 9.3.5 마켓플레이스의 `local_stale`

마켓플레이스는 **삭제를 자동 실행하지 않는다.** `marketplace remove`가 소속 플러그인 키를
**연쇄 삭제**하기 때문이다. 그러나 선택지를 **전부** 없애면 케이스 4가 영원히 유지된다.

| 선택지 | 동작 |
|---|---|
| **유지** | `base ← 레포 값`으로 잊는다. 다음 백업이 이 마켓플레이스를 레포에 되돌린다 |
| **이번엔 넘어가기** | 아무것도 하지 않는다. 다음에 다시 묻는다 |
| ~~제거~~ | **실행하지 않는다.** 명령만 안내한다 |

제거를 안내할 때 함께 적는다:

- `--scope`를 생략하면 **모든 스코프**에서 제거된다
- 그 마켓플레이스 소속 플러그인 키가 **전부 사라진다**
- **손으로 실행하면 다음 백업이 그 삭제를 레포로 전파한다**

#### 9.3.6 restore의 base 전진

restore도 base를 전진시킨다(`plan_mcp.py apply-base`가 그 본이다).
`plan_plugins.py apply-base <레포 파일> <스테이징> <선택 결과>`가 사용자의 선택을 반영한
next_base를 스테이징에 쓰고, SKILL.md가 `update_base.py`로 옮긴다.
**스테이징 디렉토리와 게이트는 7.4와 같다.**

---

## 10. 실패 처리

`install`은 네트워크로 코드를 받아오고 **실제로 실패한다.** 부분 실패가 정상이다.

### 10.1 수집 단위

```json
{ "id": "...", "step": "marketplace_add|install|enable|disable|config",
  "command": "실행한 명령 전문", "exit": 1, "stderr": "CLI가 낸 문구 전문" }
```

**stderr를 요약하지 않는다.** CLI의 문구가 가장 유용한 안내인 경우가 많다(8.5).

### 10.2 갈래별 안내

| 갈래 | 판별 | 안내 |
|---|---|---|
| 마켓플레이스 미등록 | 우리가 미리 확인 | "먼저 마켓플레이스를 등록해야 합니다" |
| 선행 단계 실패로 차단 | 9.3.2의 `blocked` | "마켓플레이스 등록이 실패해 건너뛰었습니다" |
| 명령 기반 설치 | stderr에 명령 승인 문구 | CLI 문구 그대로 + 사용자 터미널 안내 |
| 예약 이름 | stderr에 `reserved` | "이 이름은 공식 마켓플레이스용으로 예약되어 있습니다" |
| 복원 불가 | `restorable`이 거짓 | 종류별 사유 (의사 출처 / 소스 없음 / 인자 생성 불가) |
| 네트워크·기타 | 그 외 | stderr 전문 + 재시도 안내 |

### 10.3 하나가 실패해도 나머지는 계속한다

항목 단위로 독립이다. **종료 코드는 0이다** — 그래야 안내가 보인다.

### 10.4 실패한 항목의 base

**실패한 항목의 base는 전진하지 않는다.** 로컬이 그 값에 동의하지 않았기 때문이다.
`next_base`가 키 단위로 보장하므로 호출부가 전역 게이트를 두지 않기만 하면 된다.
**이 성질은 단언이 아니라 테스트로 확인한다**(14.1).

---

## 11. 마이그레이션 & 하위호환

### 11.1 이 릴리즈에 함께 실린다

3.0.0은 이미 역호환이 없는 릴리즈이고 `lib/compat.py`의 표식·차단·복구가 들어 있다.
`plugins.json` v2도 같은 릴리즈에 실어 사용자가 major 전환을 한 번만 겪게 한다.

### 11.2 `min_reader_version`과 배포 순서

`min_reader_version`은 major에 묶인 상수(3.0.0)이므로 **새 상수가 필요 없다.**

**v2.x 기기는 이 표식을 읽지 않는다.** 가드는 3.0.0에서 처음 도입됐고 2.x에는 그 코드가 없다.
따라서 릴리즈 계획 4장의 배포 순서가 **유일한** 방어다.

> **모든 기기를 3.0.0으로 올린 뒤에 어느 기기에서든 `/sync-backup`을 실행한다.**

### 11.3 `sync-metadata.json`의 `schema` 맵

`version-compat` spec 5.3이 *"`plugins.json`에는 아직 자체 `version` 필드가 없다 …
후속 작업이 스키마 버전을 도입할 때 함께 추가한다"*고 약속했고,
`tests/test_metadata.py:93` `test_schema_map_omits_plugins_json`이 `assert "plugins.json" not in meta["schema"]`(`:98`)로 현 상태를 잠가 두었다.

이 spec이 `version: 2`를 도입하므로 **그 약속이 발동한다.**
`generate_metadata.py`가 `schema` 맵에 `plugins.json: 2`를 넣고, 위 테스트를
**"포함한다"로 뒤집는다.** 12장 참조.

### 11.4 v1 → v2 승격

v1 문서(`version` 없음, 두 필드만)는 4.4의 인식 규칙을 통과한다.
읽으면 `pluginConfigs`가 없는 v2로 취급되고(부재 섹션 = `{}`), 다음 백업이
`version`·`scope`·빈 `pluginConfigs`를 붙여 저장한다. **마이그레이션 스크립트가 필요 없다.**

### 11.5 base 블롭과 첫 백업

기존 base 블롭은 없다 — `plugins.json`이 3-way 대상이 아니었기 때문이다. 첫 백업에서 부트스트랩된다.

base가 없으면 `merge`는 합집합으로 degrade한다. **정확한 의미는
"양쪽에 있는 키는 로컬 값이 레포를 덮고, 한쪽에만 있는 키는 살아남는다"** 이다
(`mcp_config.py:317-320`). "아무것도 지우지 않는다"는 맞지만 **"아무것도 바꾸지 않는다"는 틀리다.**

이 성질 때문에 H3(확장 포맷 `held`)이 **base 없는 새 기기에서도** 필요하다 —
`held`가 아니면 복원 직후 첫 백업이 레포의 객체 값을 `true`로 덮는다.

---

## 12. 영향 파일 요약

| 파일 | 변경 |
|---|---|
| `lib/keyed_sync.py` | **신규.** 코어 — 판정 + 인식 계층 + 예외 클래스 |
| `lib/plugin_config.py` | **신규.** 플러그인 어댑터 |
| `lib/mcp_config.py` | 코어 호출로 내부 교체. **공개 시그니처·예외 타입 불변** (5.5) |
| `skills/sync-backup/scripts/collect_plugins.py` | **신규** |
| `skills/sync-backup/scripts/extract_plugins.py` | **삭제** (순서는 15장 오픈이슈 4) |
| `skills/sync-backup/scripts/generate_metadata.py` | `schema` 맵에 `plugins.json: 2` 추가 (11.3) |
| `skills/sync-backup/SKILL.md` | 5단계 교체, 스테이징 배선 교체(7.4), 33·36·42행 서술 정정 |
| `skills/sync-status/scripts/compare_plugins.py` | **신규** |
| `skills/sync-status/scripts/check_status.py` | 60~76행(플러그인 비교 블록) 삭제, 신규 스크립트 호출 |
| `skills/sync-status/SKILL.md` | 호출줄 + skipped 분기 문단 신규, 플러그인 절 갱신 |
| `skills/sync-restore/scripts/plan_plugins.py` | **신규** (`apply-base` 포함) |
| `skills/sync-restore/SKILL.md` | 5절 전면 교체, 스테이징 배선(7.4). **자기 업데이트 안내(206~212행)는 보존** |
| `tests/test_metadata.py` | `test_schema_map_omits_plugins_json` → **포함 검사로 뒤집는다** (11.3) |
| `tests/test_script_root.py` | `:240`의 `COMPAT_WIRING["sync-backup"]["before_calls"]` `extract_plugins.py` 리터럴을 **`collect_plugins.py`로 교체**(삭제 금지 — 앵커다). `sync-status`에 `compare_plugins.py` 추가. `:195`가 `"### 5. 플러그인 복원"`~`"### 6. MCP 서버 복원"`으로 절을 자르므로 **제목을 바꾸면 `index()`가 `ValueError`로 죽는다** — 앵커 갱신 |
| `tests/test_keyed_sync.py` | **신규.** 코어 단위 |
| `tests/test_plugin_config.py` | **신규.** 어댑터 단위 |
| `tests/test_plugin_scripts.py` | **신규.** 스크립트 계약 |
| `tests/test_plugin_cycle.py` | **신규.** 교대 시나리오 (5.6) |
| `tests/test_mcp_state_machine.py` | 어댑터·값 픽스처 주입 형태로 재작성 |

**`before_calls` 앵커를 지우지 말 것.** 그 항목은 "호환성 검사(2.5단계)가 이 실행줄보다 앞에 있어야
한다"를 거는 앵커다. 지우면 새 호출은 **아무 앵커도 없이** 남고 2.5단계가 뒤로 밀려도 아무도 못 잡는다.

---

## 13. 문서 정정

한 곳만 고치면 나머지가 옛 서술을 계속 말한다. `grep`으로 확인한 전수다.

| 파일:행 | 현재 서술 | 고칠 내용 |
|---|---|---|
| `README.md:94` / `README.ko.md:94` | "`plugins.json` is still overwritten wholesale … known limitation" / "여전히 매 백업마다 통째로 덮어쓰입니다" | **키 단위 병합**으로. 양쪽 README에 따로 있다 |
| `README.ko.md:98` | "로컬 파일은 절대 자동으로 덮어쓰지 않습니다" 옆의 `plugins.json` 예외 문구 | **지운다.** 더 이상 예외가 아니다 |
| `README.md:25` / `README.ko.md:25` | "Plugin/marketplace list (sensitive data excluded)" / "(민감 정보 제외)" | `pluginConfigs`를 **마스킹해서 싣는다.** "제외"는 거짓이 된다 |
| `README.md:99` / `README.ko.md:99` | "only the plugin list is extracted" | 세 필드 + 마스킹 사실 |
| `backup-readme.md:34` / `.ko.md:34` | "(no sensitive data)" | 위와 같은 이유 |
| `backup-readme.md:43` / `.ko.md:43` | "`plugins.json`은 매 백업마다 새로 생성되어 덮어쓰입니다" | 키 단위 병합 |
| `sync-backup/SKILL.md:33·36` | 동기화 대상 표 "플러그인/마켓플레이스 목록만" + "두 필드만 추출" | **세 필드 + 별칭 키 + `installed_plugins.json`의 `auto`** |
| `sync-backup/SKILL.md:42` | "매 백업마다 통째로 새로 생성되어 덮어쓰인다" | 키 단위 병합 |
| `sync-status/SKILL.md:116·120` | MCP 호출·skipped 분기 문단 | 플러그인용 **호출줄과 skipped 분기 문단 신규** |
| `sync-restore/SKILL.md:215` | "없는 것만 설치한다. 기존 플러그인은 제거하지 않는다" | 3상태·삭제 전파·`held` |

**영어 README를 빠뜨리지 말 것.** `README.ko.md:98`에 해당하는 문장이 영어판에는 없으므로,
한국어판 기준으로만 지시하면 **영어 README는 아무것도 고쳐지지 않는다.**

### 새로 적어야 할 한계

- 마켓플레이스 **자동 업데이트 설정은 동기화되지 않는다** (7.2)
- **로컬 디렉토리에서 등록한 마켓플레이스는 동기화되지 않으며, 그 소속 플러그인도 동기화되지 않는다** (H2)
- **의존성으로 자동 설치된 플러그인은 백업하지 않는다** — 부모를 복원하면 따라온다 (H1)
- **명령으로 설치되는 플러그인은 세션 안에서 복원할 수 없다** — 사용자 터미널이 필요하다 (8.5)
- **객체 형태의 버전 제약은 이 기기에서 표현할 수 없어 레포 값을 보존만 한다** (H3)
- **플러그인 설정 값은 마스킹되어 저장되며, 복원 시 다시 입력한다. 건너뛸 수 있다** (6장)

---

## 14. 검증 방법

> **판정표를 100% 덮은 테스트가 전부 통과하는데도 시스템이 데이터를 잃을 수 있다.**

따라서 아래 넷을 모두 요구한다.

1. **판정표 단위 테스트** — 케이스 1~10을 세 섹션 각각에 대해.
2. **반복 적용 고정점** — 같은 로컬로 backup 3회. 2·3회차의 레포 파일과 base가 동일해야 한다.
3. **교대 시나리오** — backup ↔ restore를 실제 스크립트 서브프로세스로 교대 실행.
4. **실환경 스모크** — 임시 HOME과 로컬 디렉토리 마켓플레이스로 설치·제거를 짝지어 실행.

### 14.1 반드시 있어야 할 회귀 테스트

| 테스트 | 무엇을 막는가 |
|---|---|
| 값이 배열·객체인 항목이 왕복 후에도 보존된다 | 값 타입을 bool로 좁히는 회귀 |
| `additionalMarketplaces`만 있는 settings에서 마켓플레이스를 읽는다 | 별칭 누락 |
| **두 별칭 키가 동시에 있으면 `additionalMarketplaces`를 무시한다** | 3.3의 두 번째 규칙 |
| `auto: true` 항목이 백업 결과에 없고 **`deleted`로도 판정되지 않는다** | H1 위반 + C2형 삭제 전파 |
| `installed_plugins.json`이 없으면 두 섹션이 **skipped**이고 레포가 그대로다 | 판정 불가를 통과로 접는 회귀 |
| **`enabledPlugins`가 `null`인 settings에서 backup이 skipped이고 레포가 그대로다** | 3.2 누락 → 전멸 |
| `pluginConfigs` 값이 레포 파일에 평문으로 나타나지 않는다 | 비밀 유출 |
| **세 키 중 두 개만 입력해도 레포의 세 번째 키가 사라지지 않는다** | 6.3 부분 입력 |
| `version: 3`을 주장하는 문서를 만나면 레포 파일을 건드리지 않는다 | 상위 버전 백업 파괴 |
| **최상위가 `{}`이거나 아는 필드가 없는 문서를 만나면 쓰지 않는다** | 4.4 조건 3 (`version:3`과 다른 갈래) |
| **한 섹션이 객체가 아니면 문서 전체를 인식하지 않는다** | 4.4 조건 4 |
| **플러그인 0개 상태로 backup 2회 — 2회차가 skipped가 아니다** | 4.3 빈 섹션 생략 |
| always-known 5개가 마켓플레이스 등록 대상에 들어가지 않는다 | 실패할 등록 시도 |
| **레포에 없는 마켓플레이스 소속 id가 `unrestorable`이다** | 8.1 (H2 소비 측) |
| `enable`/`disable`이 현재 상태와 같으면 호출되지 않는다 | 멱등 아닌 명령의 거짓 실패 |
| **레포에 키가 없는 항목이 `disable` 대상이 되지 않는다** | 부재 ≠ 꺼짐 (1-c C4) |
| 복원 명령에 `-y`가 들어가지 않는다 | D2 위반 |
| **복원 명령에 `--scope user`가 들어간다** | I6 |
| **복원이 `marketplace remove`를 실행하지 않는다** | 연쇄 삭제 방어 |
| **실패한 항목의 base가 전진하지 않는다** | 10.4의 단언을 테스트로 |
| **base에 `pluginConfigs`가 없으면 어떤 항목도 `deleted`로 판정되지 않는다** | 부재 섹션 = `{}` (4.4) |

### 14.2 상태 기계 스모크 (단위 테스트로는 잡히지 않는다)

위 표는 전부 `merge`를 직접 부르는 테스트로도 통과할 수 있다. 아래 셋은 그렇지 않다.

1. **부트스트랩 확인** — backup 3회 후 `~/.claude/.sync-state/base/plugins.json`이
   **존재하고** 세 섹션을 담고 있다. (7.4의 배선 결함을 잡는 유일한 테스트)
   현행 `test_mcp_cycle.py:247`의 플러그인 판이다.
2. **선택지 실행 후 2회 백업** — 6.4의 보류, 9.3.4의 세 선택지, 9.3.5의 "유지",
   8.4의 확장 포맷 복원을 각각 실행한 뒤 backup을 **두 번 더** 돌려
   **레포에서 사라진 항목이 없는지** 확인한다.
3. **보류 후 침묵 확인** — 6.4의 보류를 고른 뒤 `/sync-status`가 그 항목을 보고하지 않고,
   **레포 값이 바뀌면 다시 보고한다.**

### 14.3 CLI 에뮬레이터 계약

교대 테스트는 CLI를 흉내 낼 수밖에 없다. **에뮬레이터가 곧 CLI 동작의 정의가 되므로**,
1-b의 실측표를 그대로 구현하지 않으면 아무것도 검증하지 않는 테스트가 된다.

| 명령 | 에뮬레이터가 반드시 재현할 것 |
|---|---|
| `install` | 키를 `true`로. **단 기존 값이 배열이면 보존.** 이미 설치면 exit 0 |
| `install --config` | `pluginConfigs` 부분 병합 |
| `enable`/`disable` | 값만 변경. **이미 그 상태면 exit 1** |
| `uninstall` | `enabledPlugins`·`pluginConfigs`에서 **키 삭제**. 없으면 exit 1 |
| `marketplace add` | 멱등. exit 0 |
| `marketplace remove` | **소속 플러그인 키 연쇄 삭제** |

### 14.4 열거형 대조

*"열거형은 원본에서 뽑아 대조한다"*를 어댑터 상수 import로만 구현하면
**상수에서 이름 하나가 빠져도 테스트와 코드가 함께 바뀌어 통과한다.**
최소 한 곳은 **개수 + 이름 전수**를 리터럴로 적어 "목록이 줄어들면 실패"하게 만든다.

### 14.5 실환경 스모크의 미측정 항목

1.2의 남은 물음을 여기서 측정하고 결과를 브리프에 append한다:

- CLI가 "확장 포맷"으로 의도한 형태는 배열인가 객체인가
- 객체 평탄화는 정규화인가 손실인가
- `install`의 기본 스코프 (help는 `user`라고 적는다 — 임시 디렉토리에서 확인)

---

## 15. 오픈 이슈 (plan에서 확정)

1. **`lib/keyed_sync.py`의 정확한 시그니처.** 훅 넷을 개별 키워드 인자로 둘지 정책 객체로 묶을지.
   **위치 인자 순서는 현행 `mcp_config`를 따른다**(5.5)는 제약 안에서 정한다.
2. **섹션별 보고를 하나로 합칠지.** 세 섹션의 충돌을 각각 보고하면 출력이 길다.
3. **`plugins-held.json`의 스키마와 수명.** 지문 알고리즘, 항목이 사라지는 조건,
   손상 시 처리(불변식 6에 따라 "보류 없음"으로 접지 말 것).
4. **`extract_plugins.py` 삭제 시점.** 스킬이 새 스크립트를 부르기 전에 지우면 그사이 백업이 깨진다.
5. **실환경 스모크를 CI에서 어떻게 돌릴지.** `claude` 바이너리가 없으면 건너뛰어야 한다.

---

## 부록 A. 사용자 가치가 나오는 지점

**스킬이 새 모듈을 부르기 전까지 사용자 관점의 가치는 0이다.**

| 결함 | 해소되는 시점 |
|---|---|
| A (통째 덮어쓰기) | `collect_plugins.py`가 만들어지고 **`sync-backup/SKILL.md`가 그것을 부를 때** |
| B (켬/끔 미감지) | `compare_plugins.py`가 만들어지고 **`check_status.py`가 그것을 부를 때** |
| C (예외 처리 부재) | 위와 같은 시점 |

코어 추출과 어댑터 작성만으로는 사용자에게 아무 변화가 없다. plan은 이 지점을 명시한다.
