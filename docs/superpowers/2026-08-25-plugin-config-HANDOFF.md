# 다음 세션 인계 — plan ② 플러그인 동기화 본체

이 문서를 그대로 붙여넣으면 다음 세션이 이어받는다.

---

## 붙여넣을 프롬프트

```
claude-sync 저장소에서 plugins.json 동기화 작업을 이어간다.

현재 브랜치는 feat/plugin-config이고 release/3.0.0(커밋 0972b7d)에서 방금 땄다.
작업 트리 클린, 446 passed.

먼저 이 셋을 순서대로 읽어라. 다른 것을 먼저 하지 마라.

1. docs/superpowers/2026-08-24-plugins-sync-STATUS.md
   — 지금까지의 전 과정. 5장의 일곱 항목은 전부 실제로 데이터를 잃은 뒤에 쓰였다
2. docs/superpowers/plans/2026-08-24-keyed-sync-core.md 의 말미
   "다음 plan으로 넘길 것" 표 — 인계 12건이 거기 있다. plan ②가 그것을 흡수해야 한다
3. docs/superpowers/specs/2026-08-24-plugins-sync-design.md
   — 유일한 근거 문서. 3·5·6·7·8·9·10·13장이 plan ②의 범위다

그다음 plan ②(플러그인 동기화 본체)를 작성한다. 범위는
lib/plugin_config.py, collect_plugins.py, compare_plugins.py, plan_plugins.py,
세 SKILL.md 배선, 문서 정정 열 곳이다.

plan을 다 쓰면 subagent-driven으로 실행한다 — task마다 새 subagent를 띄우고
task 사이에 spec 준수 review와 code quality review를 건다.

작성 전에 아래 "반드시 알아야 할 것"을 읽어라. plan ①의 실행에서 나온 것들이고,
모르고 시작하면 그대로 재현된다.
```

---

## 반드시 알아야 할 것

프롬프트와 함께 넘길 내용. plan ① 실행에서 실측으로 확인된 것들이다.

### 1. `ADAPTERS`에 한 줄만 더하면 된다는 것은 사실이 아니다

`test_mcp_state_machine.py`가 어댑터 주입 형태로 파라미터화됐고 그 docstring이 원래
"한 줄만 더하면 열 시나리오가 그대로 돈다"고 적었는데, **최종 리뷰가 실측으로 반증했다.**

| 섹션 | 그대로 도는가 |
|---|---|
| `pluginConfigs` | 예 (20 passed) |
| `extraKnownMarketplaces` | 예 |
| **`enabledPlugins`** | **아니오** — 불리언이면 3 failed, 배열이면 5 failed |

불리언은 값이 둘뿐이라 판정표 **케이스 9(양쪽 변경)를 표현할 수 없고**, 배열이면 H3로
전부 보류된다. 그리고 훅이 섹션마다 다른 클로저이므로 실제로는 "섹션당 한 줄 × 3 +
클로저 구성"이다. `Adapter.__init__`이 세 값의 상호 불일치를 `assert`로 강제하므로
불리언 어댑터를 넣으면 **수집 시점에** 명확한 메시지로 실패한다.

### 2. 보류 상태 기계 커버리지가 0이다

열 시나리오 어디에도 보류 키가 없다. MCP는 `no_hold`라 정상이지만 플러그인은 보류가
넷이다(spec 7.3). 실측: 가짜 플러그인 어댑터를 붙이고 코어의 "보류 키는 레포 값을 그대로
싣는다"를 지워도 **20 passed 그대로**였다.

**왜 다회차여야 하는가.** 단발 테스트가 잡는 것은 1회차다. "레포가 그 키를 잃은 채로
고정점에 든다"는 다회차 결과를 보는 것이 그 파일의 존재 이유다. 게다가 spec 7.3이 스스로
경고한 **H3 탈출구의 착지 지점**(해제하면 케이스 9가 아니라 케이스 7이어야 한다)은
정의상 회차 사이에 상태가 변해야 표현되는데, 현재 `repeat_backup`은 회차마다 같은
`local`과 같은 `hold`를 넘기므로 **구조적으로 표현할 수 없다.**

plan ②에 명시적 task로 넣을 것:
1. 보류 시나리오 최소 셋 — 보류 유지 / 보류 해제 후 착지 / 보류 키가 레포에서 사라졌을 때
2. `repeat_backup`에 **회차별 상태 오버라이드 훅**
3. `enabledPlugins` 전용 값 도메인

### 3. MCP가 구조적으로 검증하지 못하는 경로가 있다

MCP 어댑터는 `hold=ks.no_hold`(두 축 항상 빈 집합)와 `normalize=redact`(키를 절대 안 지움)를
주입한다. 따라서 아래는 **446개를 전부 통과한 뒤 plan ②에서야 발현한다.**

- `hold`의 인자 순서·정규화 여부 (좌우 비대칭이다 — H3는 레포 값, H1·H2는 로컬)
- 두 축의 혼동 (`value`는 push 금지, `action`은 CLI 금지. `action`은 `restore_plan` 전용)
- `normalize`의 키 보존 위반 (코어의 `_normalized`가 `ValueError`로 막는다)

그래서 코드 안에 훅 계약 주석을 박고 소스 스캔 가드 둘을 넣었다 —
`hold` 소비 함수 전수 검사, `parse_backup` 호출 금지(AST 기반).
**`plugin_config`가 붙으면 `recognize` 공유 가드는 손으로 복제해야 한다**(m-3, 인계 표 참조).

### 4. 변조 확인 없이는 테스트를 믿지 마라

plan ①에서 Task 2~7 **매번** SURVIVE가 나왔고, 대부분 plan이 실어 온 결함이었다.

- `next_base`의 핵심 불변식(값 동의 검사)을 지워도 414개가 전부 통과
- `hold` 호출 계약이 세 함수 어디에도 미고정
- `BROKEN = None`으로 바꿔도, `same`을 `a == b`로 바꿔도 스위트가 조용
- Task 3에서 순수 함수 층 다섯은 전부 CAUGHT였는데 **I/O 층을 건드리자 둘이 SURVIVED**

**plan ②의 각 task에 `Step 4b: 변조 확인`을 체크박스로 넣고**, 그 task가 도입한 가드 절을
열거하라. 세 축은 템플릿이다 — **훅 호출 계약 / 축 분리 / `{}` vs `None`**. 여기에
**I/O 층**(`open` 모드·`except` 절·파일 부재 처리)을 반드시 더하라.

### 5. plan은 spec의 컴파일 산출물이다

전제가 깨지면 plan이 아니라 **spec부터** 고친다. 단 plan ① 실행에서는 리뷰가 plan 결함을
찾을 때마다 즉시 정정했다 — 남은 task가 같은 결함을 재생산하는 것을 막기 위해서다.
정정 이력은 커밋 메시지에 있다.

각 task 머리에 `**근거:** spec N.M`을 표기하라. spec 한 절이 바뀌었을 때 폭발 반경을
기계적으로 식별하기 위해서다.

### 6. 아직 안 고친 결함 둘 (사용자에게 보이는 것)

- **`dump_backup` 비원자성** (`lib/mcp_config.py`) — `open(path,"w")`로 먼저 truncate한다.
  쓰기 도중 실패하면 레포 파일이 잘린 채 남고, 다음 백업이 그것을 `{}`로 degrade해
  **모든 서버를 케이스 4로 판정**한다 → restore가 "다른 기기가 삭제했습니다"를 띄운다.
  Task 1이 막은 것과 **같은 거짓 문구로 가는 두 번째 문**이다. tmp+`os.replace` 4줄.
  `plan_mcp.apply_base`·`sync_state.write_base`도 같은 형태다
- **`base_staging:"failed"` 보고 배선** — `collect_mcp.py`가 이 키를 반환만 하고 소비하는
  곳이 없다. spec 7.4는 "보고한다"고 썼다. `SKILL.md:397`의 주석 근거도 낡았다

### 7. 배포 전 확인

- **이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이다. `/sync-backup`을 실행하지 마라 —
  레포가 파괴된다.**
- 배포 순서 규칙은 `docs/superpowers/2026-08-21-release-3.0.0-PLAN.md` 4장
- **`release/3.0.0`이 원격보다 45커밋 앞서 있다.** 푸시하지 않았다

---

## 브랜치 상태 (2026-08-25 기준)

```
release/3.0.0     0972b7d  [origin/release/3.0.0: 45개 앞]  ← plan ① 머지 완료
feat/plugin-config 0972b7d  ← 여기서 작업 (현재 브랜치)
feat/plugins-sync  602c5a3  ← plan ① 원본. 머지됐으므로 지워도 되고 두어도 된다
```

- 테스트 **446 passed** (plan ① 착수 시 383)
- 리뷰 보고서는 `~/.claude/suberpowers/reviews/2026-08-24-claude-sync-*.md`
  (task별 spec/quality/r2 + `final-review`). **14일 후 자동 삭제되므로 필요하면 지금 옮겨라**

## plan ③ (그다음)

다운그레이드·호환 확장 — `compat.py` shape, `detect_downgrade.py`,
`generate_metadata.py` schema 맵, 2.x 경고 네 곳. spec 11장.
plan ②가 끝난 뒤에 쓴다.
