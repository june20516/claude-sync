# plugins.json 동기화 — 후속 작업 브리프

- 작성: 2026-08-20
- 상태: **착수 전.** spec도 plan도 아직 없다. 이 문서는 "무엇부터 하고 무엇을 조심할지"만 정한다.
- 선행 작업: `fix/mcp-config-source` 브랜치 (PR #2), MCP 동기화 재설계 3.0.0
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
값에 무관하다.** 플러그인은 그 셋이 전부 필요 없으므로(비밀 없음, 이름 규칙 없음),
공용 코어 추출 여부가 3장 이후의 첫 설계 판단이 된다.

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
| 1 | CLI 표면 | `claude plugin --help`, `claude plugin marketplace --help` | 하위 명령 전수 |
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

9번은 이미 실제 데이터에서 드러났다 — `enabledPlugins`에 `swift-lsp@claude-plugins-official`이
있지만 `extraKnownMarketplaces`에는 `claude-plugins-official`이 없다. 의존성 검사에서
내장 마켓플레이스를 **항상 known으로 취급**하지 않으면 restore가 없는 마켓플레이스를
등록하려 든다.

---

## 4. 2단계 — 실측 결과가 설계를 가른다

측정이 끝나면 아래 표로 분기가 결정된다. **추측으로 채우지 말 것.**

| 실측 결과 | 설계 결론 |
|---|---|
| `install`이 멱등 | 채택은 1단계. MCP의 `remove`→`add-json` 위험 구간이 없다 |
| `install`이 `already exists`로 실패 | 2단계 필요. MCP 7.7의 순서 규칙(값 완성 → 제거 → 등록 → 실패 경고)을 그대로 이식 |
| `disable` CLI 있음 | `false`를 온전한 상태로 동기화. 3상태(true/false/부재) 유지 |
| `disable` CLI 없음 | **`false`를 복원할 수단이 없다.** `false`를 "부재"로 접어 2상태로 다루거나, 동기화 대상에서 제외한다. `settings.json` 직접 편집은 기본적으로 금지 후보 — CLI가 소유한 파일이다 |
| `uninstall`이 키를 삭제 | 삭제 전파 = 키 삭제로 정의 |
| `uninstall`이 `false`로 남김 | "제거"와 "끔"이 CLI상 구별 불가 → 3상태를 2상태로 접어야 한다 |
| `marketplace remove` 없음 | 마켓플레이스는 **additive only**로 고정하고 문서에 명시 |
| 내장 마켓플레이스 존재 | 의존성 검사에서 always-known 집합으로 분리 |

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
4. (마스킹 규율) 플러그인에는 **적용 대상이 없다.** 비밀이 없으므로 이 불변식만 빠진다.
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

### 플러그인에만 있는 함정 3가지

1. **키 간 의존성** — 마켓플레이스 먼저, 플러그인 나중. 내장 마켓플레이스는 예외.
2. **무거운 부작용** — 설치는 네트워크 I/O이고 실제로 실패한다. 느리고, 부분 실패가 정상이다.
3. **목록 ≠ 실체** — `settings.json`은 의도, `~/.claude/plugins/`는 실체. 어긋날 수 있다.

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
