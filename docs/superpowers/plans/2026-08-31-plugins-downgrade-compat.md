# 다운그레이드·호환 확장 Implementation Plan (plan ③)

> **agentic worker에게:** REQUIRED SUB-SKILL: 이 plan을 task 단위로 구현하려면 suberpower:subagent-driven-development(권장) 또는 suberpower:executing-plans를 사용하세요. Step은 추적을 위해 checkbox(`- [ ]`) 문법을 사용합니다.

**Goal:** `mcp-servers.json` 전용이던 다운그레이드 보호를 `plugins.json`까지 넓힌다. 형태 판정이 relpath별로 갈라지고, 탐지 출력이 파일 맵이 되며, 세 스킬의 대화가 파일마다 옳은 명령을 낸다. **2.x 기기 한 번의 백업이 타 기기 항목을 지우는 사고를 사용자가 볼 수 있게 된다**(spec 11.6).

**Architecture:** 형태 판정은 `lib/compat.py`에 산다 — relpath를 **필수 인자**로 받는 `shape_of`와 `downgrade_suspected`. `detect_downgrade.py`는 그 판정을 파일 둘에 돌려 `{"files": {relpath: {...}}}`를 낸다. 세 `SKILL.md`는 그 맵을 **돌면서** 대화를 낸다 — 파일별 문단을 손으로 두 벌 쓰지 않는다.

**Tech Stack:** Python 3.13 표준 라이브러리만. 테스트는 pytest (`uv run --with pytest pytest`).

---

## 이 plan의 범위

| 포함 | 제외 |
|---|---|
| `lib/compat.py`의 relpath별 shape 상수·판정 (spec 11.6) | 코어(`lib/keyed_sync.py`)의 판정 로직 — 건드리지 않는다 |
| `detect_downgrade.py`의 파라미터화와 출력 스키마 교체 (spec 11.6) | 다운그레이드 **자동 복구** — 지금도 안 하고 이 plan도 안 한다 |
| v1 → v2 승격이 다운그레이드를 삼키지 않는다 (spec 11.4) | `.syncignore`의 레포 선재 파일 삭제 — **사용자가 "의도다"로 결정**(2026-08-31). 무조치 |
| `generate_metadata.py`의 `schema` 맵 (spec 11.3) | `unrestorable_reasons`의 status 노출 (spec 9.2 개정이 먼저다) |
| 다운그레이드 대화 문단 셋 + 2.x 배포 순서 경고 네 곳 (spec 13장) | 고정 `.tmp` 이름의 동시 실행 안전성 (M3 — 역효과가 있다) |
| 3차 스모크 반영 — 에뮬레이터와 그 위의 문장 (2026-08-31) | `SKILL.md`의 `reason` 문자열 분기 → `reason_kind` (유지보수 이월) |
| 4단계가 로컬 확장 값을 평탄화하지 않는다 (**사용자 결정** 2026-08-31) | `SYNCIGNORE_MEANING`·`CORRECTIONS`의 손으로 고른 목록 (외부 진실 원천 없음) |
| spec 4.4 탈출구의 `~/plugins.json.bak` 정리 안내 (**사용자 결정**) | 산문 층의 "같은 언어 두 문서 동시 편집" 탐지 (원천 없음) |
| `reconcile_restore.py`의 비원자적 로컬 쓰기 둘 (Task 1 리뷰 I3) | |

**착수 시점:** 브랜치 `feat/plugin-config`, HEAD `e574e84`, **963 passed**. `main`은 `67ab092`이고 이 브랜치는 아직 merge되지 않았다 — **브랜치 마무리는 사용자가 직접 한다.**

**근거 절 표기.** 각 task 머리에 `**근거:** spec N.M`을 적었다. spec의 그 절이 바뀌면 그 task는 무효다. **전제가 깨지면 plan이 아니라 spec부터 고친다.**

---

## 착수 전에 정해진 것 — 열린 결정 셋과 측정 둘

이 plan은 KICKOFF(`docs/superpowers/2026-08-29-plan3-KICKOFF.md`)의 2장·3장을 닫고 시작한다.

| 항목 | 결과 | 이 plan에서 |
|---|---|---|
| 2.1 `.syncignore`가 타 기기 사본을 지우는 것 | **의도다 — 유지** (사용자 결정) | **무조치.** 문서는 이미 정확하다(`27eff58`) |
| 2.2 4단계가 로컬 객체 값을 평탄화 | **건너뛰고 보고** (사용자 결정) | **Task 8** |
| 2.3 `~/plugins.json.bak`의 정리 | **안내를 넣는다** (사용자 결정) | **Task 6** |
| 3.1 `marketplace remove`의 소속 판정 | **실측 — 에뮬레이터가 맞다**(`endswith("@"+name)`) | **Task 7**(추정 → 실측 표기) |
| 3.2 `url` 출처의 왕복 | **실측 — 닫혔다.** `git`까지 함께 닫혔고 **둘 다 필드는 `url`** | **Task 7** |

측정 기록은 `docs/superpowers/2026-08-29-plugin-cli-smoke.md`의 **11~15장**(3차)이다. **요약이 아니라 그 표를 따라 구현할 것** — 이 저장소에서 요약이 자기 표보다 넓어 틀린 사고가 두 번 났다.

---

## 이 plan이 정한 것 — spec 11.6이 plan에 맡긴 자리

spec 11.6은 *"`detect()`의 출력을 relpath 맵으로 바꿀지, 파일별 대화 문단을 가를지는 plan이 정한다"*고 적었다.

**결정: relpath 맵.** 근거는 산문 쪽이다 — 파일별로 스크립트를 두 번 부르면 세 `SKILL.md`에 **거의 같은 문단이 두 벌씩** 생기고, 이 저장소에는 그 종류의 드리프트를 잡는 장치가 없다(KICKOFF 5장의 "같은 언어의 두 문서를 똑같이 고치는 산문 편집"이 바로 그 미해결 항목이다). 맵이면 대화가 **파일을 도는 루프 하나**다.

**결정: `relpath`는 기본값 없는 필수 인자.** `shape_of(data)`처럼 기본값을 두면 갱신되지 않은 호출자가 **조용히 mcp 규칙으로 `plugins.json`을 판정한다** — `{"version":2,...}`에 `servers`가 없으니 `SHAPE_UNKNOWN`이 되고, 다운그레이드가 영영 탐지되지 않는데 아무 증상이 없다. 필수 인자면 그 호출자가 `TypeError`로 즉시 죽는다.

---

## 형태 판정표 (Task 1·2가 공유하는 정본)

| relpath | 옛 형식(v1) | v2 | 그 외 |
|---|---|---|---|
| `mcp-servers.json` | 최상위가 **배열** → `v1_array` | 객체이고 `servers`가 객체 → `v2_object` | `unknown` |
| `plugins.json` | 최상위가 객체인데 **`version` 키가 없다** → `v1_object` | 객체이고 `version` 키가 **있다** → `v2_object` | `unknown` |

**`plugins.json`의 v2 판정은 `version`의 *값*을 보지 않는다 — *존재*만 본다.** 값을 보면 `version: 3`(상위 버전)이 `unknown`으로 떨어져 `downgrade_suspected`가 조용히 `False`가 되는데, 그것은 이 함수가 답할 질문이 아니다("v1이냐 v2냐"이지 "읽어도 되느냐"가 아니다 — 후자는 `_recognized_sections`의 조건 2가 답한다).

**`{}`는 `v1_object`다.** 2.x의 `extract_plugins.py`는 로컬 settings에 두 키가 다 없으면 `{}`를 쓴다(`git show main:…/extract_plugins.py`로 확인 — 실측). base가 v2였다면 그것은 정확히 다운그레이드 사고다.

**`plugins.json`에 배열이 오면 `unknown`이다.** `v1_array`가 아니다 — 그 relpath에서 배열은 옛 형식이 아니라 알 수 없는 문서다. 두 relpath가 상수를 공유하면 mcp의 옛 형식이 plugins의 옛 형식으로 읽힌다.

---

## 변조 확인은 각 task의 필수 스텝이다

각 task의 `Step 4b`에서 **그 task가 도입한 가드 절을 하나씩** 뒤집고 대응 테스트가 FAIL하는지 임시 복사본에서 확인한다. 원본 작업 트리를 오염시키지 말 것. **다섯 축이 템플릿이다:**

| 축 | 이 plan에서의 형태 |
|---|---|
| **훅 호출 계약** | `shape_of(data, relpath)`의 인자 순서, `find_last_v2_commit`이 v2 판정에 `shape_of`가 아니라 `parse_base`를 쓰기, `detect`가 파일마다 **같은** base를 읽기 |
| **축 분리** | 옛 형식 상수를 relpath 사이에서 맞바꾸기, `v1_object`를 `v1_array`로, `unreadable`을 `absent`로 |
| **`{}` vs `None`** | `{}`를 `unknown`으로(= 사고를 놓친다), 후보 없음을 `newer_schema_seen`으로, 파일별 `skipped`를 전역 `skipped`로 |
| **I/O 층** | `except FileNotFoundError`→`except OSError`, `open` 모드, `os.replace` 제거, git 실패를 빈 결과로 |
| **입력 축** | **테스트가 준 입력을 뺀다** — 픽스처에서 relpath 하나를 빼기, 히스토리 회차를 줄이기, 표의 행을 빼기(특히 `{}` 행과 `version: 3` 행), 선택자가 뽑는 목록을 비우기, 에뮬레이터가 만드는 **상태**와 명령의 **규약**(exit code·값의 모양) |

**다섯째 축이 이 plan에서 특히 위험한 자리:** 형태 판정표는 **행이 여섯**이고(absent·broken·unreadable·v1·v2·unknown) 두 relpath에 각각 존재한다. 픽스처에서 행 하나를 빼도 나머지가 초록이면 그 행은 아무것도 재지 않는다. **완전성 단정을 짝지을 것** — 판정표의 키 집합이 `_SHAPES`와, relpath 맵의 키 집합이 `{mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}`와 같은지 거는 테스트를 함께 쓴다(6.2의 세 번째 형태).

**새 가드가 스스로 공허해지는 형태 셋을 매번 확인할 것:**
1. **`not in` 가드는 바늘이 틀려도 초록** — 바늘을 파일·spec·코드에서 **뽑을 것**
2. **선택자가 빈 값을 내면 루프가 0회 돌아 초록** — 추출기 실패가 곧 성공이 된다
3. **목록이 자기 축소를 탐지 못 함** — 완전성 단정을 **짝지을 것**

**SURVIVE하면 구현이 아니라 테스트를 보강한다.** 보강한 줄 옆에 어떤 변조를 잡는지 주석으로 남긴다.

**변조 하네스:** `~/.claude/suberpowers/tools/mutate.py`. 대조군(`C0`)은 하네스가 스스로 넣는다. spec 형식 `{"id","file","old","new","desc"}`(치환 여럿이면 `"count"`). **agent 간 스크래치패드가 공유되므로 고유한 파일 이름을 쓸 것**(빈 spec으로 돈 사고가 있었다).

---

## 코드를 고치면 docstring도 함께 점검한다 (모든 task의 필수 스텝)

이 지시로 결론이 뒤집힌 자리가 plan ②에서 여럿 나왔다. **네 형태를 매번 본다:**

1. **인용한 실측이 여전히 참인가** — 이 plan은 3차 스모크가 추정 둘을 실측으로 바꿨다. *"실측 없음 — 추정"*이라 적힌 문장이 낡는다
2. **사실 진술이 낡지 않았는가** — *"호출자는 하나다"*, *"`mcp-servers.json` 전용이다"*, *"url·git의 필드 이름은 측정되지 않았다"* 류
3. **고친 것을 인용하는 다른 파일의 docstring** — `shape_of`를 고치면 `detect_downgrade.py`·`test_compat.py`·spec 11.6이 그것을 인용한다
4. **"실측"이라 적힌 것이 정말 실측인가**

**`grep`으로 전수를 뜰 것.** 한 곳만 고치면 나머지가 옛 서술을 계속 말한다.

---

## 배포 전 확인 (변하지 않았다)

> **이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이다. `/sync-backup`을 실행하지 마라 — 레포가 파괴된다.** 배선이 실제 스크립트를 부르므로 **세 스킬(`/sync-backup`·`/sync-restore`·`/sync-status`) 실행도 전부 금지**다. `claude plugin`을 **임시 HOME**에서 재는 것만 안전하다.

---

### Task 1: `lib/compat.py`의 형태 판정을 relpath별로 가른다

**근거:** spec 11.6 (형태 판정은 `detect_downgrade.py`가 아니라 `lib/compat.py`에 산다)

**의존:** 없음. **이 task가 2·3의 전제다.**

현행은 셋 다 `mcp-servers.json` 전용이다 — `shape_of`(객체는 `servers`가 dict일 때만 v2), `downgrade_suspected`(`v1_array and v2_object` 하드코딩), `_SHAPES`.

- [ ] **Step 1.** `SHAPE_V1_OBJECT = "v1_object"`를 더하고 `_SHAPES`에 넣는다. 위 **형태 판정표**가 정본이다 — 요약을 읽지 말고 표를 구현한다.
- [ ] **Step 2.** `shape_of(data, relpath)` — `relpath`를 **두 번째 위치 인자, 기본값 없음**으로. 내부는 relpath → 판정 함수의 dict(`_SHAPE_RULES`)로 가른다. 모르는 relpath는 **`ValueError`**다(조용한 fail-open 금지 — 같은 파일의 `_upgrade_message`·`downgrade_suspected`가 이미 그 관례다).
- [ ] **Step 3.** `downgrade_suspected(repo_shape, base_shape, relpath)` — 옛 형식 상수를 relpath에서 뽑는다(`_OLD_SHAPE = {…}`). 규칙 자체는 하나다: `repo_shape == 옛 형식 and base_shape == SHAPE_V2_OBJECT`. 기존의 shape 검증(`_SHAPES` 밖이면 `ValueError`)은 **유지**한다.
- [ ] **Step 4.** `tests/test_compat.py`의 shape 표를 **두 relpath 각각**으로 넓힌다. 여섯 행(absent·broken·unreadable·v1·v2·unknown)이 relpath마다 있어야 한다. **아래 다섯 행을 반드시 포함**한다 — 빠지면 그 자리가 조용히 틀린다:
  - `plugins.json` + `b"{}"` → `v1_object` (2.x가 쓰는 실제 값이다)
  - `plugins.json` + `b'{"version":3,"enabledPlugins":{}}'` → `v2_object` (**값이 아니라 존재를 본다**)
  - `plugins.json` + `b"[]"` → `unknown` (`v1_array`가 **아니다**)
  - `mcp-servers.json` + `b'{"version":2}'`(`servers` 없음) → `unknown` (현행 규칙이 바뀌지 않았다)
  - 모르는 relpath → `ValueError`
- [ ] **Step 5.** **완전성 단정 둘을 짝짓는다.** (a) `_SHAPE_RULES`·`_OLD_SHAPE`의 키 집합이 `{mc.BACKUP_RELPATH, pc.BACKUP_RELPATH}`와 같다 — **두 모듈에서 import해서 뽑는다**(리터럴을 손으로 적으면 relpath 상수가 바뀌어도 초록이다). (b) 표가 내는 shape 값 전부가 `_SHAPES`에 있다.
- [ ] **Step 4b (변조).** 최소 여섯: ① `_OLD_SHAPE`의 두 값 맞바꾸기 ② `plugins`의 v2 판정을 `version` 값 비교(`== 2`)로 ③ `{}`를 `unknown`으로 ④ `relpath`에 기본값 `mc.BACKUP_RELPATH` 부여 ⑤ 모르는 relpath에 `ValueError` 대신 mcp 규칙 fallback ⑥ **입력 축** — Step 4 표에서 `{}` 행을 빼고 나머지가 여전히 초록인지(초록이면 그 행이 아무것도 안 재는 것이 아니라 **표가 그 행 없이도 충분한지** 확인해야 한다. 다른 단정이 그 자리를 덮고 있지 않다면 SURVIVE다).
- [ ] **Step 5b (docstring).** `shape_of`·`downgrade_suspected`의 docstring이 *"레포의 mcp-servers.json이"*, *"mcp_config는 파싱해서 매핑만 주므로"* 같은 단일 파일 전제를 말한다. **전수 grep**: `grep -rn "v1 배열\|v1_array\|shape_of\|downgrade_suspected" plugins/ docs/superpowers/specs/`.

**완료:** `uv run --with pytest pytest plugins/claude-sync/tests -q` → 0 failed. `detect_downgrade.py`는 아직 두 인자 호출로 고치지 않았으므로 **이 task 안에서 그 호출부도 함께 고친다**(필수 인자라 `TypeError`가 난다). 출력 스키마 교체는 Task 2다.

---

### Task 2: `detect_downgrade.py`를 파일 둘로 넓히고 출력을 relpath 맵으로 바꾼다

**근거:** spec 11.6 (`find_last_v2_commit`의 형태 판정을 relpath별로 파라미터화)

**의존:** Task 1.

- [ ] **Step 1.** `detect(repo_path, base_dir)`의 출력을 바꾼다:

```json
{"status": "ok",
 "files": {"<relpath>": {"downgrade_suspected": bool, "repo_shape": "...",
                         "base_shape": "...", "candidate": null,
                         "newer_schema_seen": false,
                         "status": "ok|skipped", "reason": null}}}
```

  **전역 `status`와 파일별 `status`는 다른 것을 말한다.** 전역은 git 자체가 없거나 레포가 git이 아닌 경우(파일 어느 쪽도 판정할 수 없다), 파일별은 그 파일의 히스토리 훑기가 실패한 경우다. 한쪽으로 합치면 *"탐지할 수 없었다"*와 *"사고가 없다"*의 구별(불변식 6)이 파일 단위에서 무너진다.

- [ ] **Step 2.** `find_last_v2_commit(repo_path, relpath)` — **v2 판정을 `parse_base`가 아니라 `compat.shape_of(blob, relpath) == SHAPE_V2_OBJECT`로 한다.**

  > **여기가 이 task에서 가장 조용히 틀리는 자리다.** mcp에서는 `mc.parse_base`가 v2 판정을 겸했다 — v1 배열은 dict가 아니라 인식이 `None`이었기 때문이다. **`plugins.json`은 다르다**: `_recognized_sections`의 조건 2가 *"version이 **없거나** SCHEMA_VERSION 이하"* 이므로 **v1 문서도 인식된다.** mcp 패턴을 그대로 옮기면 `find_last_v2_commit`이 **2.x가 쓴 v1 커밋을 "마지막 정상 판본"으로 제시**하고, 대화가 그 sha를 `git checkout`하라고 지시한다 — **탐지가 사고를 복구하는 대신 고착시킨다.**

  `parse_base`는 계속 쓰되 역할을 나눈다: `shape_of`가 **v2인가**를, `parse_base`가 **항목을 셀 수 있는가**(`None`이면 `newer_schema_seen`)를 답한다.

- [ ] **Step 3.** 후보 요약을 relpath 중립으로 바꾼다. `server_count`·`server_names` → `entries: {<버킷>: [이름…]}`. mcp는 `{"servers": [...]}`, plugins는 세 섹션(`enabledPlugins`·`extraKnownMarketplaces`·`pluginConfigs`)이다. **버킷 이름을 손으로 적지 말고** `mc`/`pc`가 내는 매핑의 키에서 뽑는다.
- [ ] **Step 4.** `_shape_of_file`·`_base_shape`가 relpath를 받는다. **base는 파일마다 따로 읽는다** — 한 번 읽어 두 판정에 돌려 쓰면 `plugins.json`의 base 부재가 mcp의 base로 가려진다.
- [ ] **Step 5.** `tests/test_downgrade.py`에 `plugins.json` 갈래를 더한다. **최소 다섯 시나리오:**
  - v1 레포 + v2 base → `downgrade_suspected: true`, 후보가 **v2 커밋**이다
  - 히스토리에 v1 커밋이 v2 커밋보다 **나중**에 있는 픽스처 → 후보가 v1을 가리키지 **않는다**(Step 2의 함정을 정면으로 건다)
  - v2 레포 + v2 base → `false`
  - 레포 파일 부재(`absent`) + v2 base → `false`(사고가 아니라 첫 백업 전이다)
  - 두 파일이 **서로 다른 판정**을 내는 픽스처 → 맵의 두 항목이 독립이다
- [ ] **Step 4b (변조).** 최소 여섯: ① Step 2의 v2 판정을 `parse_base is not None`으로 되돌리기 ② `relpath` 인자를 무시하고 `mc.BACKUP_RELPATH` 고정 ③ 파일별 `status`를 전역으로 접기 ④ base를 한 번만 읽어 공유 ⑤ 후보 없음을 `newer_schema_seen: true`로 ⑥ **입력 축** — 픽스처에서 "v1이 v2보다 나중" 회차를 빼기, 그리고 `files` 맵에서 `plugins.json` 항목을 빼기(단정이 죽는가).
- [ ] **Step 5b (docstring).** 모듈 docstring이 *"레포의 mcp-servers.json이 v1 배열인데"*로 시작한다. `detect`·`_skipped`·`find_last_v2_commit` 전부. **`grep -rn "server_count\|server_names\|find_last_v2_commit" plugins/ docs/`로 전수를 뜬다** — 세 `SKILL.md`가 이 키를 읽는다(Task 5가 그 산문을 고친다).

**완료:** 0 failed.

> **경고 — 이 task는 초록인 채로 산문을 낡게 만든다.** 세 `SKILL.md`가 옛 키(`server_count`·`server_names`)를 읽는데 **그 키를 산문에 묶는 테스트가 하나도 없다**(2026-08-31 실측: `grep -rn "server_count\|server_names" plugins/claude-sync/tests/` → `test_downgrade.py` 셋뿐이고 전부 **스크립트 출력**만 본다). 즉 **아무 앵커도 빨개지지 않는다.** 이 plan에서 그 자리를 닫는 것은 **Task 5 Step 4 하나뿐이므로 Task 5는 선택이 아니다.**
>
> **이 task 안에서 산문을 고치지 말 것** — 고치면 Task 5의 범위를 삼키고 네 번째 자리(`sync-restore:490-497`)가 조용히 빠진다. 대신 **Task 2의 완료 기록에 "산문 넷이 아직 옛 키를 읽는다"를 명시적으로 적어** 넘긴다.

---

### Task 3: v1 → v2 승격이 다운그레이드 사고를 삼키지 않는다

**근거:** spec 11.4

**의존:** Task 1·2.

spec 11.4의 규칙 *"레포에 `version`이 없는데 이 기기의 base에는 `version: 2`가 있었다면 승격이 아니라 다운그레이드 사고다"* 는 **Task 1·2의 형태 판정이 이미 계산하는 것과 같다**(`v1_object` + `v2_object`). 이 task가 더하는 것은 **그 계산이 사용자에게 도달하는 경로가 실제로 있다는 회귀 층**이다.

- [ ] **Step 1.** 순서 가드는 **이미 있다 — 새로 만들지 말 것.** `tests/test_skill_wiring.py`의 `DOWNGRADE_BEFORE["sync-backup"]`가 이미 `COLLECT_PLUGINS_CALL`(가장 앞선 수집 단계)을 앵커로 쓰고, 그 주석이 *"plan ③이 탐지를 plugins.json으로 넓히면 그 순서가 곧 정확도가 된다"*고 이 task를 예고한다. **확인만 하고, 확인했다는 사실과 근거 줄을 이 task의 완료 기록에 남긴다.** 중복 가드를 세우면 한쪽만 갱신되는 자리가 하나 더 생긴다.
- [ ] **Step 2.** 종단 회귀: 레포 `plugins.json`이 2.0.0 형식(`{"enabledPlugins":{…},"extraKnownMarketplaces":{…}}`, `version` 없음)이고 base 블롭이 v2일 때 `detect`가 `downgrade_suspected: true`를 낸다. **`extract_plugins.py`의 실제 출력 모양을 픽스처의 근거로 삼는다** — `git show main:plugins/claude-sync/skills/sync-backup/scripts/extract_plugins.py`가 그 원천이다(손으로 지어낸 v1 모양을 쓰면 2.x가 실제로 쓰는 것과 갈려도 초록이다).
- [ ] **Step 3.** 반대 방향 회귀: **정당한 v1 승격**(레포 v1 + base **없음**)은 `false`이고 백업이 정상 진행한다. 이 행이 없으면 Task 1·2가 승격 경로 전체를 막아도 초록이다.
- [ ] **Step 4b (변조).** 최소 넷: ① base 부재를 `v2_object`로 ② `downgrade_suspected`를 항상 `false`로 ③ 탐지 호출을 수집 뒤로 옮기기 ④ **입력 축** — Step 3의 반대 방향 행을 빼기.
- [ ] **Step 5b (docstring).** spec 11.4의 *"마이그레이션 스크립트가 필요 없다"* 옆 문단이 이 판정을 인용한다. 구현과 어긋나면 **spec을 고친다**(plan이 아니라).

**완료:** 0 failed.

---

### Task 4: `sync-metadata.json`의 `schema` 맵에 `plugins.json: 2`

**근거:** spec 11.3

**의존:** 없음(1·2·3과 병렬 가능).

`version-compat` spec 5.3이 *"후속 작업이 스키마 버전을 도입할 때 함께 추가한다"*고 약속했고 `tests/test_metadata.py`의 `test_schema_map_omits_plugins_json`이 현 상태를 잠가 두었다. **이 spec이 `version: 2`를 도입하므로 그 약속이 발동한다.**

- [ ] **Step 1.** `generate_metadata.py:93`의 `metadata["schema"] = {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION}`에 `pc.BACKUP_RELPATH: pc.SCHEMA_VERSION`을 더한다. **두 상수를 각 모듈에서 뽑는다** — 리터럴 `"plugins.json": 2`를 적으면 상수가 바뀌어도 조용하다.
- [ ] **Step 2.** `test_metadata.py`의 `test_schema_map_omits_plugins_json`을 **포함 검사로 뒤집는다.** 이름도 함께 바꾼다(`test_schema_map_carries_both_documents` 등) — 이름이 단정과 반대면 다음 독자가 단정을 의심하지 않는다.
- [ ] **Step 3.** **완전성 단정을 짝짓는다** — `schema` 맵의 키 집합이 백업 문서 둘과 정확히 같다. 없으면 셋째 문서가 생겼을 때 조용히 빠진다(6.2의 세 번째 형태).
- [ ] **Step 4b (변조).** 최소 넷: ① `pc.SCHEMA_VERSION` 대신 리터럴 `1` ② 새 항목을 지우기 ③ 완전성 단정의 기대 집합을 손으로 적은 리터럴로 ④ **입력 축** — 완전성 단정에서 `mcp-servers.json`을 빼고도 초록인지.
- [ ] **Step 5b (docstring).** `generate_metadata.py:17`의 *"schema: 사람이 읽는 요약. 판정 근거가 아니다"*가 여전히 참인지 확인한다. `sync-backup/SKILL.md:377`이 이 맵의 **예시 JSON을 리터럴로** 싣는다 — 함께 고칠 것.

**완료:** 0 failed.

---

### Task 5: 세 `SKILL.md`의 다운그레이드 대화를 파일 맵 위에 다시 세운다

**근거:** spec 13장. **단 spec의 행 번호는 낡았고 자리도 하나 빠져 있다** — 2026-08-31 실측한 현재 위치는 아래 표다.

**의존:** Task 2 (출력 스키마).

| 파일 | 자리 | 무엇이 리터럴인가 |
|---|---|---|
| `sync-backup/SKILL.md` | `:253` 호출, `:258`·`:260`·`:263`·`:272` 대화 (절 `4.5 다운그레이드 사고 탐지`) | `mcp-servers.json`, `git show "<sha>:mcp-servers.json"`, `server_count`·`server_names` |
| `sync-restore/SKILL.md` | `:106` 호출, `:142`·`:144`·`:154`·`:155` 대화 (절 `2.5 호환성·다운그레이드 검사`) | 같음 |
| `sync-restore/SKILL.md` | **`:490-497`** — 6-5의 `local_stale` 안내가 `downgrade_suspected`로 갈라지는 **네 번째 자리** | `downgrade_suspected`가 **최상위 단일 값**이라는 전제 |
| `sync-status/SKILL.md` | `:81` 호출, `:94`·`:96`·`:100` 대화 (절 `1.5 호환성 검사`) | "서버 수" |

> **`sync-restore:490-497`은 spec 13장의 목록에 없다.** 그 자리는 *"다른 기기가 삭제했습니다"* 라는 **거짓 문구**를 다운그레이드 시에 억제하는 갈래이고, `plugins.json`이 탐지 대상이 되는 순간 **플러그인 쪽 `local_stale` 안내에도 같은 거짓이 생긴다.** spec 13장 표를 이 행으로 보강할 것.

- [ ] **Step 1.** 위 표의 네 자리를 **파일을 도는 형태**로 바꾼다. 파일마다 **그 파일의** relpath와 sha가 나가야 한다.
- [ ] **Step 2.** `sync-restore:490-497`의 갈래를 **문서별로** 가른다 — `files["mcp-servers.json"].downgrade_suspected`가 MCP 서버 안내를, `files["plugins.json"]`이 플러그인 안내를 억제한다. **한 값이 둘을 함께 억제하면** MCP만 사고가 났을 때 멀쩡한 플러그인 안내가 사라진다(반대도 같다). **restore는 막지 않고 경고만 한다**(현행 규정 유지).
- [ ] **Step 3.** 후보 요약 렌더링이 `entries` 맵을 읽게 한다(Task 2 Step 3). 서버 이름만 보여 주던 자리가 **버킷별 개수**를 보여 준다.
- [ ] **Step 4.** 산문 결속 층은 **이미 있다 — 넓히는 것이지 새로 만드는 것이 아니다.** `tests/test_skill_wiring.py`의 `DOWNGRADE_SECTION`·`DOWNGRADE_CALL`·`test_downgrade_detection_precedes_what_it_informs`와, `:556-587`의 restore 갈래 문구 테스트가 그것이다. 거기에 더한다: 네 자리의 대화가 **`detect`가 실제로 내는 키만** 읽는지. 키를 **`detect`의 출력에서 뽑아** 쓴다 — 손으로 적으면 스키마가 바뀌어도 초록이다.
- [ ] **Step 4b (변조).** 최소 여섯: ① `entries` 대신 `server_names`를 읽기 ② 루프를 첫 파일에서 `break` ③ `git show`의 relpath를 리터럴 `mcp-servers.json`으로 되돌리기 ④ Step 4의 키 추출기가 빈 집합을 내게 하기(**루프 0회 → 초록**인가 — 6.2의 두 번째 형태) ⑤ **Step 2를 되돌려** 한 값이 두 안내를 함께 억제하게 하기 ⑥ **입력 축** — 픽스처의 `files` 맵에서 항목 하나를 빼고 단정이 죽는지.
- [ ] **Step 5b (docstring).** `sync-backup/SKILL.md:249`(*"수집 단계들보다 먼저 한다. 6단계가 `mcp-servers.json`을 v2로 덮으면"*)가 이제 **5단계에도** 걸린다. **절 제목은 앵커다** — `test_skill_wiring.py`의 `DOWNGRADE_SECTION`·`RESTORE_CHECK_SECTION`과 `section()`이 제목으로 절을 자르므로 **제목을 바꾸면 `index()`가 `ValueError`로 죽는다.** 제목을 바꿔야 한다면 앵커를 같은 커밋에서 갱신할 것.

**완료:** 0 failed. `grep -rn "server_count\|server_names" plugins/` → **출력 없음**.

---

### Task 6: 2.x 배포 순서 경고 네 곳 + spec 4.4의 사본 정리 안내

**근거:** spec 13장 두 번째 표 · spec 4.4 (**사용자 결정** 2026-08-31)

**의존:** 없음.

11.2가 *"배포 순서가 유일한 방어"*라고 선언하는데 **그 순서를 말하는 문구 넷이 전부 `mcp-servers.json` 이야기만 한다.** MCP를 쓰지 않는 사용자는 "나에겐 해당 없음"으로 읽는다.

- [ ] **Step 1.** 네 곳을 고친다 — `README.md:74` / `README.ko.md:74`, `backup-readme.md:45` / `.ko.md:45`, `sync-backup/SKILL.md:481`, `sync-restore/SKILL.md:148`. **`plugins.json`도 함께**: 타 기기의 플러그인·마켓플레이스·설정 키 목록이 사라진다.
- [ ] **Step 2.** **영어 README를 빠뜨리지 말 것.** spec 13장이 명시적으로 경고한다 — 한국어판 기준으로만 지시하면 영어판은 아무것도 고쳐지지 않는다. `backup-readme.md`도 두 벌이다.
- [ ] **Step 3.** spec 4.4의 탈출구에 **사본 정리 안내**를 넣는다(사용자 결정). 지금은 `cp plugins.json ~/plugins.json.bak`만 있고 정리를 말하지 않는다. 넣을 것 셋: **언제 지워도 되는가**(모든 기기에서 `keep_stale` + `/sync-backup`을 마쳐 레포가 각 기기 항목을 되받은 것을 확인한 뒤), **왜 그 전에는 안 되는가**(어느 기기에도 로컬로 없는 항목은 이 사본이 유일한 근거다), **어떻게 확인하는가**. 사본에는 마스킹된 값만 들어 있어 **평문 비밀은 없다** — 그 사실도 함께 적어 사용자가 급히 지우지 않게 한다.
- [ ] **Step 4.** 산문 결속: 배포 순서 경고 넷이 **두 relpath를 모두** 말하는지 거는 테스트. **바늘을 손으로 적지 말고** `mc.BACKUP_RELPATH`·`pc.BACKUP_RELPATH`에서 뽑는다(6.2의 첫 번째 형태 — `not in` 가드는 바늘이 틀려도 초록이다).
- [ ] **Step 4b (변조).** 최소 다섯: ① 네 곳 중 하나를 옛 문구로 되돌리기(**넷 각각**을 따로 돌린다 — 하나만 걸리고 셋이 안 걸리는 것이 이 종류의 전형적 결함이다) ② 영어판만 되돌리기 ③ Step 4의 선택자가 빈 목록을 내게 하기 ④ **입력 축** — 결속 테스트의 파일 목록에서 `backup-readme.md`를 빼기.
- [ ] **Step 5b (docstring).** spec 4.4를 고쳤으므로 `load_backup`·`_recognized_sections`의 docstring이 인용하는 4.4 서술이 여전히 맞는지 본다. `sync-backup/SKILL.md:57`의 `.syncignore` 예외 문단은 **건드리지 않는다**(2.1 결정 — 무조치).

**완료:** 0 failed. `grep -rn "mcp-servers.json" README.md README.ko.md` 결과의 각 행이 `plugins.json`도 말하는지 눈으로 확인.

---

### Task 7: 3차 스모크를 코드와 산문에 반영한다

**근거:** 2026-08-31 3차 스모크 11~15장 · spec 8.6 · 14.5 #3

**의존:** 없음.

- [ ] **Step 1.** `tests/plugin_cli.py`의 `_marketplace_source`가 url·git 인자에 `NotImplementedError`를 던진다. **이제 실측된 모양이 있다** — 3차 스모크 **14장의 표**대로 판별하게 고친다:

| 인자 | 출처 |
|---|---|
| 절대 경로(`/`로 시작) | `{"source":"directory","path":<인자>}` |
| `owner/repo` · `https://github.com/owner/repo` | `{"source":"github","repo":"owner/repo"}` |
| `.git`으로 끝나는 `http(s)://…` | `{"source":"git","url":<인자>}` |
| 그 밖의 `http(s)://…` | `{"source":"url","url":<인자>}` |
| 그 외 | **`NotImplementedError` 유지** — 미측정 모양에 조용히 github을 쓰지 않는다 |

  **순서가 규칙이다** — github 정규화가 `.git` 규칙보다 **먼저**다. `https://github.com/o/r.git`는 **여전히 미측정**이고(네트워크가 필요하다) 프로덕션에 도달 경로가 없다(`marketplace_arg`가 github에 내는 것은 `repo` 필드다). 그 사실을 docstring에 적을 것.

- [ ] **Step 2.** 같은 파일 모듈 docstring의 추정 **10번·11번**을 `[미확인]`에서 **실측**으로 바꾼다. `marketplace_remove`의 docstring도 *"소속 판정 규칙(`endswith`)만 실측 없음 — 추정"*을 고친다. **근거 문서와 장 번호를 적을 것**(3차 스모크 11·12장).
- [ ] **Step 3.** `lib/plugin_config.py`의 `_SOURCE_ARG_FIELDS` 주석이 *"url·git의 필드 이름은 측정되지 않았으므로 후보를 순서대로 훑고"*라고 적는다. **거짓이 됐다 — 둘 다 `url`이다.** 주석을 실측으로 바꾸되 **`git`의 둘째 후보 `repo`는 남긴다**: 지우면 `repo`만 가진 값이 조용히 unrestorable이 되고, 남기는 비용은 0이다. **그 근거를 주석에 적을 것**(지금은 *"어느 쪽이 옳은 필드인지 모르므로"* 가 근거인데 그 근거가 사라졌다).
- [ ] **Step 4.** spec 8.6의 url·git "복원 가능" 서술에 **실측 표식**을 단다(감사 ②가 지적한 자리). spec 14.5 #3을 닫고, **#4(`defaultEnabled`를 되읽는 파일)는 미측정으로 남긴다** — 이 plan도 재지 않는다.
- [ ] **Step 5.** 왕복 테스트: url·git 출처의 레포 값 → `marketplace_arg` → 에뮬레이터 `marketplace_add` → 같은 값. **3차 스모크 13장의 두 행을 픽스처의 근거로 삼는다.**
- [ ] **Step 4b (변조).** 최소 여섯: ① `.git` 판별과 github 판별의 **순서 뒤집기** ② `git` 출처를 `{"repo": …}`로 쓰기 ③ 그 외 인자에 `NotImplementedError` 대신 github fallback ④ `_SOURCE_ARG_FIELDS["git"]`에서 `"url"`을 빼기(`repo`만 남기기 — 왕복이 죽는가) ⑤ **입력 축** — Step 5 픽스처에서 git 행을 빼기 ⑥ **입력 축** — 에뮬레이터 명령의 **규약**: `marketplace_add`의 멱등성(재실행 exit 0)을 exit 1로 바꾸기.
- [ ] **Step 5b (docstring).** *"실측 없음 — 추정"*·*"미측정"*을 **전수 grep**한다: `grep -rn "미측정\|실측 없음\|추정" plugins/claude-sync/tests/plugin_cli.py plugins/claude-sync/lib/plugin_config.py docs/superpowers/specs/`. 3차 스모크가 닫은 것만 고치고 **남은 것은 그대로 둔다** — 한꺼번에 지우면 아직 추정인 자리가 실측으로 승격된다.

**완료:** 0 failed. `grep -n "NotImplementedError" plugins/claude-sync/tests/plugin_cli.py` → **여전히 존재**(모르는 모양의 fail-closed는 유지된다).

---

### Task 8: 복원 4단계가 로컬 확장 값을 평탄화하지 않는다

**근거:** spec 9.3.1 · 7.3 (H3) · **사용자 결정** 2026-08-31 ("건너뛰고 보고")

**의존:** 없음.

`install --config`는 **로컬** `enabledPlugins` 값이 객체면 그것을 `true`로 평탄화한다(1차 스모크 3장 — 배열은 보존, 객체만 파괴). 레포 오염은 아니다(H3가 값 축을 잡는다). **사용자가 요청하지 않은 로컬 상태 변경**이고, 사용자 결정은 **그 id의 4단계를 건너뛰고 보고**다.

- [ ] **Step 1.** `plan_plugins.py`의 `build_plan`에서 `config_keys`를 만들 때, **로컬 `enabledPlugins` 값이 비불리언인 id를 뺀다.** 판정 입력은 이미 있는 `local_masked`다(`hooks["enabledPlugins"]["normalize"]`를 통과한 값 — 계획이 값을 실을 때 쓰는 **같은 표**를 써야 한다. 한쪽만 정규화하면 마스킹이 도입되는 날 두 값이 갈린다).
- [ ] **Step 2.** 뺀 것을 **보고한다.** 새 키(예: `config_skipped_local_extended`)를 `{id: 로컬 값}`으로 싣는다. **값을 함께 싣는 이유**: 사용자가 "무엇을 지키려고 건너뛰었는지"를 봐야 "이 기기 값을 포기하겠다"를 고를 수 있다. 값은 정규화된 것이므로 비밀이 아니다(`pluginConfigs`가 아니라 `enabledPlugins`다).
- [ ] **Step 3.** `sync-restore/SKILL.md`의 4단계 문단이 그 키를 읽어 보고한다. **"실패"로 렌더링하지 않는다** — 건너뛴 것이지 실패한 것이 아니다(10.2의 갈래 구분과 같은 종류다).
- [ ] **Step 4.** 배열은 어떻게 하는가 — **배열도 함께 건너뛴다.** 근거: `install`이 배열을 보존하는 것은 실측이지만(2차 스모크 7장 6행) `config_keys`의 판정을 값 종류로 가르면 표가 하나 더 생기고, **H3가 배열·객체를 구분하지 않는다**(`value_command`가 비불리언 전부에 `None`이다). 한 규칙으로 통일하는 편이 좁고 안전하다. **이 근거를 코드 주석에 적을 것** — 다음 독자가 "배열은 보존되는데 왜 건너뛰나"를 반드시 묻는다.
- [ ] **Step 5.** 테스트 넷: 로컬 객체 값 → 건너뛰고 보고 / 로컬 배열 값 → 같음 / 로컬 불리언 → **정상 진행**(과하게 좁히지 않았다) / **로컬 키 부재** → 정상 진행(부재는 확장 값이 아니다).
- [ ] **Step 4b (변조).** 최소 여섯: ① 판정을 `isinstance(v, dict)`로 좁히기(배열이 새는가) ② 정규화되지 않은 `local`을 보기 ③ 로컬 키 부재를 확장 값으로 보기 ④ 건너뛰되 **보고하지 않기**(조용한 누락 — 잡히는가) ⑤ 판정을 **레포** 값으로 하기(H3와 헷갈리는 자리다 — 좌우 비대칭) ⑥ **입력 축** — Step 5에서 "로컬 불리언 → 정상 진행" 행을 빼기(가드가 과하게 넓어져도 초록인가).
- [ ] **Step 5b (docstring).** `build_plan`의 `config_keys` 옆 주석이 *"**설치 집합으로 좁히지 않는다**"*를 말한다 — **이 task가 다른 축으로 좁히므로 그 문장에 단서를 단다**(설치 여부로는 여전히 좁히지 않는다). `recheck_values`의 docstring이 4단계를 인용하는 자리도 함께 본다. spec 9.3.1에 이 예외를 적을 것 — **spec에 없는 동작을 코드가 하면 다음 감사가 결함으로 읽는다.**

**완료:** 0 failed.

---

### Task 9: 비원자적 로컬 쓰기 둘과 `.tmp` 위생

**근거:** Task 1 quality review I3·M4 (plan ②) · `keyed_sync.dump_bytes`가 이미 있다

**의존:** 없음.

`reconcile_restore.py`의 `open(local,"wb")` 두 곳이 **선-truncate**한다. ENOSPC로 중간에 죽으면 `~/.claude/agents/foo.md`가 **잘린 채** 남고, 예외가 traceback으로 서서 `write_base`가 실행되지 않아 base는 옛 값 그대로다. 다음 판정이 `L≠S, R==S` → `local_ahead` → **다음 백업이 잘린 로컬을 레포의 온전한 사본 위에 push한다.**

- [ ] **Step 1.** 두 곳(`add`/`overwrite` 갈래와 `merge` 갈래)을 `ks.dump_bytes`로 교체한다. `dump_bytes`가 `os.replace`까지 하는지 **읽고 확인할 것** — 이름만 보고 가정하지 말 것.
- [ ] **Step 2.** `sync_state.write_base`의 `data is None` 삭제 분기가 `<path>.tmp`를 지우지 않는다(M4). 지우게 한다. **현재 영향은 없다**(base 디렉토리를 walk하는 코드가 없다) — 그 사실을 주석에 적어 다음 독자가 이 변경을 "버그 수정"으로 오해하지 않게 한다.
- [ ] **Step 3.** `bootstrap.sh`가 백업 레포에 `.gitignore`를 만들지 않는다. `*.tmp` 한 줄을 넣는다. **이미 존재하는 레포에는 소급되지 않는다** — 그 한계를 적을 것.
- [ ] **Step 4.** 회귀 테스트: 쓰기 도중 실패해도 로컬 파일이 **옛 내용 그대로**다(잘린 상태가 아니다). 실패 주입은 `dump_bytes`가 부르는 자리를 몽키패치하는 형태로 — **디스크를 실제로 채우지 말 것**.
- [ ] **Step 4b (변조).** 최소 다섯: ① `dump_bytes`를 다시 `open(...,"wb")`로 ② `os.replace`를 `shutil.move`로(같은 파일시스템 밖에서 원자성이 깨진다) ③ 두 곳 중 **하나만** 고치기(테스트가 둘 다 거는가 — 이것이 이 task의 전형적 결함이다) ④ `.tmp` 삭제를 지우기 ⑤ **입력 축** — Step 4에서 `merge` 갈래 시나리오를 빼기.
- [ ] **Step 5b (docstring).** `reconcile_restore`의 모듈 docstring이 원자성에 대해 무엇을 약속하는지 본다. `keyed_sync.dump_bytes`의 docstring이 *"호출자는 하나다"* 류의 사실을 말하면 **낡는다**(이 task가 호출자를 둘 더한다).

**완료:** 0 failed.

---

## 완료 정의

- [ ] `uv run --with pytest pytest plugins/claude-sync/tests -q` → **0 failed.** 개수는 게이트가 아니다 — 리뷰 후속 커밋이 테스트를 더한다
- [ ] **`PLAN_SHA`를 정한다** — 이 plan 문서를 커밋한 지점의 sha다. `git log --oneline -1 -- docs/superpowers/plans/2026-08-31-plugins-downgrade-compat.md`로 확인한다. **`main..HEAD`를 쓰면 안 된다** — plan ②의 파일들이 `main`에 없어 전부 신규 추가로 잡힌다
- [ ] `git diff --stat $PLAN_SHA..HEAD -- plugins/claude-sync/lib/keyed_sync.py` → **출력 없음.** 코어의 판정 로직은 이 plan의 범위가 아니다
- [ ] `python3 -c "import sys; sys.path.insert(0,'plugins/claude-sync/lib'); import compat; compat.shape_of(b'{}')"` → **`TypeError`**(relpath가 필수 인자다). 이것이 통과하면 기본값이 남아 있는 것이고, 갱신되지 않은 호출자가 조용히 mcp 규칙을 쓴다
- [ ] `grep -rn "server_count\|server_names" plugins/` → **출력 없음**
- [ ] `grep -n "NotImplementedError" plugins/claude-sync/tests/plugin_cli.py` → **출력 있음.** 모르는 인자 모양의 fail-closed는 유지된다
- [ ] `grep -rn "mcp-servers.json" README.md README.ko.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme*.md` → 배포 순서 경고에 해당하는 행이 **`plugins.json`도 말한다**
- [ ] spec 11.6의 relpath 표 두 행 각각에 대응하는 테스트를 짚을 수 있다. 짚지 못하는 행이 있으면 **그 행이 이 plan의 누락이다**
- [ ] 각 task의 Step 4b가 **실제로 돌았고** SURVIVE가 남아 있지 않다. 남겼다면 그 이유가 task 절에 적혀 있다
- [ ] **`/sync-backup`·`/sync-restore`·`/sync-status`를 실행하지 않았다** — 이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이고, 실행하면 레포가 파괴된다

## 다음 plan으로 넘길 것

| 항목 | 근거 |
|---|---|
| **`defaultEnabled`를 되읽는 파일** — 설치된 플러그인의 그 필드를 어느 파일에서 읽는지 미측정. 닫히면 `recheck_values`의 `assumed` 갈래가 사라진다 | spec 14.5 #4 |
| `https://github.com/o/r.git`가 github인지 git인지 — 네트워크가 필요하다. **프로덕션에 도달 경로는 없다** | 3차 스모크 14장 |
| `/sync-status`의 `unrestorable`에 사유를 싣기 — **spec 9.2가 사유를 요구하지 않으므로 spec부터 고쳐야 한다** | Task 8 관찰(plan ②) |
| `SKILL.md`가 `reason` **문자열**로 분기한다 — 구조적으로는 `reason_kind` 필드가 옳다 | 유지보수 이월 |
| `SYNCIGNORE_MEANING`·`CORRECTIONS`의 손으로 고른 목록 — 양 언어에서 같은 항목을 개수와 함께 지우면 조용히 줄어든다(외부 진실 원천 없음) | 유지보수 이월 |
| `excluded_in_repo`가 3-way 분류를 하지 않는다 — 항목별 처방을 적으려면 `reconcile_restore.py`의 매핑을 `lib/`로 옮겨야 한다 | 유지보수 이월 |
| **같은 언어의 두 문서를 똑같이 고치는 산문 편집**이 잡히지 않는다 — 한국어 절반은 spec 13장의 한국어 불릿에 같은 순번으로 묶으면 닫힌다(리뷰가 40줄 프로토타입으로 실측). 영어 절반은 원천이 없다 | 유지보수 이월 |
| 옛 앵커 둘: `plans/2026-08-21-version-compat.md:2310`, `specs/…plugins-sync-design.md:1641` | 유지보수 이월 |
| **변조 명세(`*.json`)가 세션 스크래치패드에만 있다** — corpus가 휘발성이다 | 유지보수 이월 |
| 고정 `.tmp` 이름은 동시 실행에서 원자성이 무력화된다. 코드베이스에 락이 하나도 없어 동시 실행을 전제하지 않는 설계와는 일관된다. `mkstemp`는 잔존 파일 이름을 무작위로 만들어 `.gitignore` 대응이 어려워지는 **역효과**가 있다 | Task 1 리뷰 M3(plan ②) |
| `conflicts`·`repo_ahead`의 보고 분할이 `collect_mcp.py`·`collect_plugins.py`에 축자 중복. 코어에 넣는 것은 계층이 어긋난다. 현재는 **양쪽 다 테스트로 잠겨** 표류 위험이 낮다 | Task 7 리뷰 I-3(plan ②) |
| 보류 종류를 하나 더하려면 네 곳을 동시에 고쳐야 하고 어긋나면 런타임 `ValueError`로만 드러난다. 그 `ValueError`가 fail-closed 가드로 설계된 것이다 | Task 5 리뷰 I-2(plan ②) |
| `test_keyed_sync.py`의 `RECOGNIZE_HOOK_CALL`이 별칭 `ks.`를 하드코딩. 면제 목록이 커지면 AST로 올릴 것 | Task 3 리뷰 M-1(plan ②) |
| `test_mcp_state_machine.py`의 이름이 더 이상 내용과 맞지 않는다 | Task 11(plan ②) |
