# plan ③ 실행 진행 기록

- plan 본문: `docs/superpowers/plans/2026-08-31-plugins-downgrade-compat.md`
- 분할 파일: `~/.claude/suberpowers/plan3-tasks/` (`split-plan.py --check` 초록)
- 착수: `e7831ba`, **963 passed**
- 방식: subagent-driven (task마다 implementer → spec review → quality review)

## 상태

| Task | 상태 | 커밋 | spec | quality |
|---|---|---|---|---|
| 1 `lib/compat.py`의 relpath별 형태 판정 | **완료** | `e3f6200`·`af09464`·`e39f88f`·`c82f6e1` | ✅ (r3) | **Yes** (r2) — Critical 0 / Important 0 / Minor 1 |
| 2 `detect_downgrade.py` relpath 맵 | **완료** | `d543feb`·`ea4c136`·`e92f721`·`687913b` | ✅ (1라운드) | **With fixes → 해소** |
| 3 v1→v2 승격이 사고를 삼키지 않는다 | **완료** | `a721e79` | ✅ (1라운드) | 〃 (2·3 합동) |
| 4 `generate_metadata.py`의 `schema` 맵 | 미착수 | | | |
| 5 세 `SKILL.md`의 다운그레이드 대화 | **완료** | `2e3f4a5`~`8dbf305` | ✅ (2라운드) | **With fixes → 해소** |
| 6 2.x 배포 순서 경고 + `.bak` 정리 안내 | **완료** | `761d2e0`~`3088625` | | |
| 7 3차 스모크 반영 | 미착수 | | | |
| 8 4단계가 로컬 확장 값을 평탄화하지 않는다 | 미착수 | | | |
| 9 비원자적 로컬 쓰기 + `.tmp` 위생 | 미착수 | | | |

현재 **1128 passed**. **갈래 ⓐ가 닫혔다** — Task 6이 배포 순서 경고 세 곳(파일로는 다섯)을 두 문서 모두 말하게 고쳤고, 그것이 이 plan의 유일한 **예방**이다(2.x는 표식을 읽지 못하므로 사고를 막을 코드가 없다). 리뷰 보고서는 `~/.claude/suberpowers/reviews/2026-08-31-claude-sync-task-1-*.md` 여섯 벌.

## Task 1이 남긴 것 — Task 2가 이어받을 자리

**Task 1의 리뷰 라운드가 실제 결함 셋을 잡았고 셋 다 닫혔다.** 형태별로 기록해 둔다 —
같은 형태가 남은 task에서 반복된다.

| 라운드 | 결함 | 형태 |
|---|---|---|
| spec r1 | 옛 arity 서술 둘(`version-compat-design.md:653`·`:975-976`) | **(b) 문장이 코드와 어긋난다** |
| spec r2 | 완전성 단정이 **선택자가 비면 루프 0회로 초록**(`VERSION_MARKED_BUT_NOT_V2 = {}` SURVIVE) | 공허해지는 형태 **②** |
| quality r1 | `detect_downgrade.py`의 relpath 인자 **둘이 테스트로 고정되지 않음** — 틀린 relpath를 꽂아도 1045 passed. 실제 다운그레이드가 조용히 "사고 없음"이 된다 | **훅 호출 계약** 축 + (c) |
| quality r1 | `compat.py`의 "순환 import" 근거가 **정적·실측 모두 거짓**(`lib/`는 순환 없는 DAG) | **(b)**, 결론은 맞고 근거가 틀림 |

**quality r1의 relpath 결함이 Task 2에 직접 걸린다.** 원인은 `tests/test_downgrade.py`의 픽스처가
전부 `{"version":2,"scope":"user","servers":{…}}`라 **두 규칙 모두에서 `v2_object`**여서 갈리지
않는 것이었다. Task 1이 갈리는 픽스처 둘을 넣어 닫았다:

| 픽스처 | mcp 규칙 | plugins 규칙 |
|---|---|---|
| `v2_without_version({…})` = `{"servers":{…}}` | `v2_object` | `v1_object` |
| `version_without_servers()` = `{"version":2}` | `unknown` | `v2_object` |

**Task 2는 이 둘을 그대로 relpath 맵 위로 옮겨 재사용한다.** 그리고 **Step 4b에 "호출부 relpath
오배선" 변조를 명시적으로 넣을 것** — plan 머리의 축 표가 "훅 호출 계약"을 1번 축으로 적어
두었는데 Task 1의 Step 4b 목록이 그 축을 세우지 않아 리뷰가 대신 잡았다.


## Task 1의 시간과 그 귀결 — plan 공통 절이 바뀐 이유

Task 1은 **1시간 53분**이 걸렸고 산출물은 프로덕션 코드 **+102/−22줄**, 테스트 +429/−39줄,
문서 +15/−7줄이다. 배분은 subagent 실행 100분 27초 + 오케스트레이션 12분 29초였고,
그 100분은 implementer 48분 · 리뷰어 다섯 52분으로 갈린다.

**라운드별 발견을 보면 무엇이 수렴하지 않았는지가 드러난다:**

| 라운드 | 프로덕션 로직 결함 | 그 외 |
|---|---|---|
| spec r1 | **0** | 문서 arity 2 |
| spec r2 | **0** | 완전성 단정이 공허함 1 |
| spec r3 | **0** | 0 |
| quality r1 | **0** | 테스트 공백 1, 거짓 근거 주석 1, Minor 5 |
| quality r2 | **0** | Minor 1 (선재) |

**로직은 첫 시도에 수렴했다. 수렴하지 않은 것은 「증명」이다.** 그래서 plan 공통 절에 세 절을
넣었다(`00-shared-context.md`로 배포되어 남은 task의 subagent가 읽는다):

1. **검증을 언제 멈추는가 — 명시적 기준 셋**(커버리지: 다섯 축 전부 CAUGHT / 깊이: 가드는
   스스로를 검사하고 가드의 가드를 만들지 않는다 / 라운드: ⑴⑵ 충족 + 로직 결함 0건이면 종료)
2. **검증 강도는 위험도로 나눈다** — 축은 「코드냐 문서냐」가 아니라 「조용히 틀리면 되돌릴 수
   없는 행동이 나가는가」다. 이 저장소에서는 `SKILL.md` 산문이 실행물이다
3. **변조는 실행을 공유하고 설계는 공유하지 않는다** — 리뷰어의 값은 전부 자기가 고안한 변조에서
   나왔고, implementer의 spec을 재실행한 데서는 새 정보가 0건이었다

**가장 값싼 절감은 ⑴이다.** quality r1이 잡은 실제 결함은 다섯 축 중 1번 축인데 Task 1의
Step 4b가 그 축을 세우지 않았다 — 세웠으면 1라운드에 나오고 두 라운드가 줄었다.

**Task 2부터는 각 task의 Step 4b가 다섯 축을 전부 인스턴스화해야 한다.**

## Task 1이 남긴 둘 — 이월이 아니라 **지금 닫는다**

사용자 결정(2026-08-31)으로 이 plan에는 이월이 없다. Task 1 리뷰가 남긴 둘은 **Task 2·3이
`test_downgrade.py`·`test_compat.py`를 손댈 때 함께 닫는다.** 둘 다 다운그레이드 탐지의 가드이므로
Goal에 직접 방해가 된다.

| 항목 | 왜 방해가 되는가 |
|---|---|
| **m6** — `test_compat.py`의 `parsable_rows`에서 `rp == relpath` 필터를 지우면 1047 전부 초록. 다른 변조와 겹치면 완전성 단정 셋이 함께 넓어진다 | 그 단정들이 **형태 판정표의 자기 축소**를 막는 유일한 장치다. 넓어지면 판정표가 줄어도 초록이 되고, 그러면 다운그레이드 탐지가 조용히 약해진다 |
| **R14** — mcp `{"servers":[]}` 행이 mcp v2 규칙(`servers`가 dict)을 재는 **유일한 입력**인데 짝지어진 완전성 단정이 없다 | 그 행이 사라지면 `isinstance(…, dict)` → `"servers" in obj` 약화가 **새어 나간다**. mcp 쪽 다운그레이드 판정이 헐거워진다 |

**m3·m4·m5**(가독성·이름·테스트 분할)는 **닫는다** — Goal에 방해가 되지 않는다. 특히 m4는 이 파일의
헬퍼 관례가 밑줄 없음이라 **바꾸면 오히려 파일 안에서 갈린다**(실측 확인).

---

## Task 2·3·5 완료 — 깨졌던 세 `SKILL.md` 계약은 **닫혔다** (아래는 그 이력)

Task 2가 `detect()`의 출력을 relpath 맵으로 바꾸면서 **세 `SKILL.md`의 계약을 깼다.**
plan(task-02.md)이 산문 수정을 Task 5로 미루라고 명시적으로 금지했으므로 **의도된 순서**지만,
**그 키를 산문에 묶는 테스트가 하나도 없어 아무 앵커도 빨개지지 않는다**(실측 재확인).
그래서 이 기록이 유일한 안전장치다.

**무엇이 깨졌나** — ① 최상위 `downgrade_suspected`·`newer_schema_seen`·`status`·`repo_shape`·
`base_shape`·`candidate`가 사라졌다(이제 전부 `files[relpath]` 아래) ② `candidate.server_count`·
`server_names`가 `entries: {버킷: [이름…]}`으로 대체됐다.

| 파일 | 아직 옛 계약을 읽는 자리 |
|---|---|
| `sync-backup/SKILL.md` | `:256`·`:258`·`:260`·`:263`·`:272` |
| `sync-status/SKILL.md` | `:92`·`:94`·`:96`·`:100` |
| `sync-restore/SKILL.md` | `:140`·`:142`·`:144`·`:154`·`:155` |
| `sync-restore/SKILL.md` (6-5) | `:490`·`:492`·`:497` — 2.5단계의 `downgrade_suspected`를 **최상위 값으로** 참조 |

**`version-compat` spec §9.3**(복구 UX — *"후보 커밋의 날짜·서버 수·서버 이름"*)도 같은 이유로
낡았고, 산문 결정과 붙어 있어 Task 5에 남겼다.

> **닫혔다 (Task 5, `2e3f4a5`~`bbc8008`).** 네 자리를 파일 맵 위에 다시 세웠고, **다섯째 자리**를
> 새로 발견해 세웠다 — `sync-restore` **5-5**절에도 같은 거짓(*"다른 기기가 지웠습니다"* → `uninstall`
> 권유)이 플러그인 쪽에 생기므로 `files["plugins.json"]`로 억제한다. `grep -rn "server_count\|server_names"
> plugins/` → 출력 없음.

**Task 5에 넘기는 추가 입력:** 「전역 skipped + 파일별 ok」 조합(git을 못 쓰는데 어느 문서도
suspected가 아닌 경우)을 산문이 어떻게 렌더링할지 정해야 한다. Task 2·3의 quality 리뷰 m5가
그 조합을 산출하는 테스트를 더한다.

---

## plan 개정 (2026-08-31, 사용자 결정)

- **Goal을 릴리즈 기준으로 다시 썼다** — *"3.0.0을 배포 가능한 상태로 만든다"*. 네 갈래(ⓐ 다운그레이드 · ⓑ 남은 로컬 손실 경로 · ⓒ 검증되지 않은 자리 · ⓓ 보고·산문 드리프트)로 묶었고 **task 번호는 재배열하지 않았다**(근거 참조가 깨진다).
- **이월 표를 폐지했다.** plan ②가 넘긴 14행을 한 줄씩 판정해 **10개를 Task 10~13으로 흡수**, **5개를 「닫은 것」 절에 이유와 함께 닫았다.**
- **Task 14(릴리즈 게이트)를 더했다** — 릴리즈 계획 5장의 범위가 코드에서 실제로 닫혔는지 **plan ②의 선언이 아니라 코드와 테스트로** 검증한다. 푸시·배포는 사용자가 실행한다.
- task가 9 → **14**가 됐다. Task 1 완료, **13 남음.**
