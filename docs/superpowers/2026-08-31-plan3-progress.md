# plan ③ 실행 진행 기록

- plan 본문: `docs/superpowers/plans/2026-08-31-plugins-downgrade-compat.md`
- 분할 파일: `~/.claude/suberpowers/plan3-tasks/` (`split-plan.py --check` 초록)
- 착수: `e7831ba`, **963 passed**
- 방식: subagent-driven (task마다 implementer → spec review → quality review)

## 상태

| Task | 상태 | 커밋 | spec | quality |
|---|---|---|---|---|
| 1 `lib/compat.py`의 relpath별 형태 판정 | **완료** | `e3f6200`·`af09464`·`e39f88f`·`c82f6e1` | ✅ (r3) | **Yes** (r2) — Critical 0 / Important 0 / Minor 1 |
| 2 `detect_downgrade.py` relpath 맵 | 미착수 | | | |
| 3 v1→v2 승격이 사고를 삼키지 않는다 | 미착수 | | | |
| 4 `generate_metadata.py`의 `schema` 맵 | 미착수 | | | |
| 5 세 `SKILL.md`의 다운그레이드 대화 | 미착수 | | | |
| 6 2.x 배포 순서 경고 + `.bak` 정리 안내 | 미착수 | | | |
| 7 3차 스모크 반영 | 미착수 | | | |
| 8 4단계가 로컬 확장 값을 평탄화하지 않는다 | 미착수 | | | |
| 9 비원자적 로컬 쓰기 + `.tmp` 위생 | 미착수 | | | |

현재 **1047 passed**. 리뷰 보고서는 `~/.claude/suberpowers/reviews/2026-08-31-claude-sync-task-1-*.md` 여섯 벌.

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

## 이월 (Task 1 시점에서 닫지 않기로 한 것)

| 항목 | 근거 | 판단 |
|---|---|---|
| **m6** — `test_compat.py:543` `parsable_rows`의 `rp == relpath` 필터가 어떤 테스트로도 고정되지 않는다. 그 줄을 지우면 1047 전부 초록이고, 다른 변조와 겹치면 완전성 단정 셋이 함께 넓어진다 | quality r2 Minor 1 | **선재 구멍**(접기 전 세 벌 모두 SURVIVED). m2 접기가 만든 약화가 **아니고** 고칠 자리를 셋에서 하나로 줄였다. 값싸게 닫히므로 Task 2·3에서 `test_downgrade.py`를 손댈 때 함께 볼 것 |
| **R14** — `test_compat.py`의 mcp `{"servers":[]}` 행이 mcp v2 규칙("`servers`가 dict")을 재는 **유일한 입력**인데 짝지어진 완전성 단정이 없다. 그 행을 지우면 초록 | spec r3 참고 A | **선재 구멍**(`af09464`에서도 동일). 그 행이 사라지면 `isinstance(…, dict)` → `"servers" in obj` 약화가 새어 나간다 |
| m3·m4·m5 (가독성·이름·테스트 분할) | quality r1 Minor | 넘김. m4는 이 파일의 헬퍼 관례가 밑줄 없음이라 **바꾸면 오히려 갈린다**(실측 확인) |

## 하네스 사용에서 배운 것 (실측)

**APPLY_FAIL을 SURVIVED로 읽지 말 것.** Task 1에서 `_rule_for` → `_for_relpath` 이름 변경이
기존 변조의 앵커를 낡게 만들었고, 재실행에서 그 변조가 `SURVIVED/APPLY_FAIL` 목록에 떴다.
실제로는 **치환이 안 먹은 것**이었다 — 하네스가 둘을 구별해 주지 않았다면 그 자리가 조용히
뚫린 채로 보고될 뻔했다. **이름을 바꾸는 커밋 뒤에는 기존 mutation spec의 앵커를 함께 갱신할 것.**
