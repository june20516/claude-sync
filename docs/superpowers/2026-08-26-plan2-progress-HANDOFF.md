# 다음 세션 인계 — plan ② 실행 중 (7.5 / 15)

- 갱신: 2026-08-26
- 브랜치: `feat/plugin-config` (푸시 안 됨), HEAD `f28d18f`
- 테스트: **612 passed** (착수 시 446)
- **상태: Task 1~7 완료, Task 8은 spec review ✅ 통과하고 quality review만 남았다.**

---

## 붙여넣을 프롬프트

```
claude-sync 저장소에서 plan ②(플러그인 동기화 본체) 실행을 이어간다.

먼저 이 문서를 읽어라: docs/superpowers/2026-08-26-plan2-progress-HANDOFF.md

Task 1~7이 완료됐고 Task 8은 spec review까지 끝났다. quality review부터 재개한다.
실행 방식은 subagent-driven이다 — task마다 새 subagent, task 사이에 spec 준수 review와
code quality review. 남은 것은 Task 8(quality) 그리고 Task 9~15다.
```

---

## 지금 어디인가

| Task | 상태 | 결과물 |
|---|---|---|
| 1 원자적 쓰기 | ✅ | `ks.dump_bytes`(+fsync), 세 경로 라우팅 고정 |
| 2 `base_staging` 배선 | ✅ | 게이트 두 축 명문화, spec의 `reason` 이름 충돌 제거 |
| 3 테스트 위생 | ✅ | root skip 마커, `recognize` 완전성 소스 스캔 |
| 4 어댑터 읽기·인식 | ✅ | `lib/plugin_config.py` 신규 |
| 5 정규화·보류 | ✅ | H1~H4 두 축, `held_context` |
| 6 복원 가능성 | ✅ | `restorable`·`reason`·`orphaned`, **어댑터 완성**(약 850줄) |
| 7 `collect_plugins.py` | ✅ | 첫 스크립트, `hooks_and_context`·`skipped_section` |
| **8 `compare_plugins.py`** | **spec ✅ / quality 남음** | 읽기 전용 비교 |
| 9~15 | ⬜ | `plan_plugins`(plan/apply-base), 검증 셋, 배선·문서 |

**다음 행동:** Task 8의 code quality review를 dispatch한다.
`git diff cf69c4f..c076a71 -- plugins/claude-sync`가 대상이고,
REPORT_FILE은 `~/.claude/suberpowers/reviews/2026-08-26-claude-sync-task-8-quality.md`.

---

## 작업 자산이 어디 있나

| 무엇 | 어디 |
|---|---|
| plan 본문 (15 task) | `docs/superpowers/plans/2026-08-25-plugins-sync-body.md` |
| **task별 분할 파일** | `~/.claude/suberpowers/plan2-tasks/task-01.md` ~ `task-15.md` |
| 리뷰 보고서 | `~/.claude/suberpowers/reviews/2026-08-2*-claude-sync-task-*.md` |
| spec (유일한 근거 문서) | `docs/superpowers/specs/2026-08-24-plugins-sync-design.md` |

**subagent에게는 task별 분할 파일만 주고 plan 본문(5,300줄)은 열지 말게 한다.**
스크래치패드는 세션이 바뀌면 사라진다 — 그래서 `~/.claude/suberpowers/` 아래로 옮겼다.
plan 본문이 바뀌면 분할 파일을 다시 만들어야 한다(헤딩 `^### Task \d+:`로 경계를 유도).

---

## 실행 중 확립된 방법론 (그대로 이어갈 것)

**1. 변조 확인(Step 4b)이 이 plan의 근간이다.** 각 task는 도입한 가드 절을 하나씩 뒤집어
대응 테스트가 실제로 FAIL하는지 확인한다. 여기서 나온 SURVIVE가 지금까지 **30건 이상**이고,
그중 상당수가 조용한 데이터 손실 경로였다.

**2. 무동작 대조군을 먼저 돌린다.** Task 7이 도입했다. 아무것도 바꾸지 않은 복사본에서
전체 스위트가 통과하는지 확인해야 하네스가 거짓 CAUGHT를 내지 않는다는 것이 증명된다.

**3. `.pyc` 캐시 함정.** 두 변조가 **같은 크기의 파일을 같은 초에** 쓰면 `.pyc`가 재사용되어
판정이 통째로 거짓이 된다(pyc 헤더는 mtime을 초 단위로 저장). 반드시
`PYTHONDONTWRITEBYTECODE=1` + 매회 `__pycache__` 삭제(lib·tests·scripts 전부).

**4. 변조가 많으면 배치 스크립트가 낫다.** 이 호스트는 절전으로 agent가 자주 죽는다
(실제로 4회). orchestrator가 python 배치로 돌리면 짧게 끝나 절전에 걸리지 않는다.
Task 5에서 그렇게 15종을 한 번에 돌렸다.

**5. reviewer 중단 시 REPORT_FILE 체크포인트를 먼저 읽는다.** 대부분 상당히 채워져 있어
확정된 항목의 재검증을 건너뛰고 이어받을 수 있다.

---

## 이 저장소에서 반복되는 실패 양식 셋

리뷰가 잡은 것을 종류로 묶으면 셋뿐이다. **남은 task에서도 이것들을 먼저 의심하라.**

**(a) 공허한 단정 — 단정이 참인데 그 참이 구현의 가드에서 나오지 않는다.** 아홉 번 나왔다.
전형적인 형태 셋:
- 실패 주입 지점이 정리 코드보다 **앞**이라 정리 여부와 무관하게 참 (Task 1에서 두 번)
- fixture가 **다른 케이스로 떨어져** 검증하려던 가드를 타지 않음 (Task 7, H1 보류가 죽어 있어도 통과했다)
- 단정은 있는데 **비지 않은 값을 만드는 fixture가 없어** 하드코딩과 구별 안 됨 (Task 7, 여덟 건)

**(b) 문장이 코드와 어긋난다.** 일곱 번. docstring·주석·SKILL.md가 코드가 하지 않는 일을
약속하거나, 결론은 맞는데 **근거가 틀린** 형태. 후자가 특히 위험하다 — 그 근거를 믿고
구조를 바꾸면 조용히 깨진다. (예: "hold를 레포 읽기 뒤에 계산해야 한다"의 근거가 H3·H4라고
적었는데 실제로는 H2·`restorable`·`reason`이었다.)

**(c) 조용한 fail-open.** 다섯 번. 읽기 실패·판정 불가를 "항목 0개"나 성공으로 접으면
상태 기계가 그것을 **삭제**로 읽는다. 특히 `auto` 판정이 빈 집합이 되면 되돌릴 수 없는
승격 전파(N6)가 다른 기기에서 일어난다.

**같은 값을 두 곳에서 만들면 갈리고, 갈려도 증상이 없다** — 이 계열은 전부 구조로 막았다
(`held_context` → `hooks_and_context` → `skipped_section`, 그리고 `value_held_for`).
남은 스크립트도 **조립을 한 번으로** 원칙을 따를 것.

---

## 어댑터 공개 표면 (Task 9~10이 쓸 것)

`lib/plugin_config.py` — 스크립트가 부르는 것만:

```
read_local_sections / read_auto_ids / read_held_state / read_hold_inputs
load_backup / parse_base / parse_backup / dump_backup
hooks_and_context(local, repo, *, auto_ids, held_state) -> (hooks, context)
    hooks[section] = {normalize, hold, restorable, secret_keys, reason}   # 코어 계약은 넷
held_kinds(section, keys, **context, repo_norm=...)
value_held_for(section, hooks, local, repo)     # next_base에 넘길 값 보류
skipped_section(reason)                          # 섹션 skip 보고의 공유 모양
orphaned / marketplace_arg / unrestorable_reason / value_fingerprint / marketplace_of
ALWAYS_KNOWN(5) / PSEUDO_SOURCES(4) / RESERVED_MARKETPLACE_NAMES(16) / SECTIONS(3)
```

**예외별 skip 범위**(모듈 docstring의 표):
`LocalConfigUnavailable`·`UnknownBackupSchema` → 전체 skip /
`AutoFlagsUnavailable` → `enabledPlugins`·`pluginConfigs` /
`HeldStateUnavailable` → `pluginConfigs`. **공통 기반 클래스로 묶지 말 것** —
한 줄로 전부 잡히면 부분 skip이 조용히 전체 skip이 된다.

---

## plan 문서에 이미 반영된 정정 (재실행해도 재생산되지 않는다)

실행 중 리뷰가 잡은 **plan·spec 결함 16건**을 전부 문서에 반영했다. 큰 것만:

- Task 1의 공허한 단정 둘, Task 2의 테스트 mock 조건(`endswith`가 레포 rename까지 가로챔)
- Task 2의 게이트 근거(푸시 실패는 `-f`가 아니라 `REPO_HAS_CONTENT=0`이 막는다)
- Task 3의 스캔 대상(Task 1이 `sync_state`를 코어 import로 만들었다)
- Task 6의 변조 주장(`@` 개수 완화는 판정이 아니라 **사유만** 바꾼다)
- **spec 9.1.1의 순서 근거** — H3·H4가 아니라 H2·`restorable`·`reason`이다
- spec 7.4의 `reason` → `base_staging_reason` (plan ②가 같은 충돌을 재생산할 뻔했다)

---

## 배포 전 확인 (변하지 않았다)

- **이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이다. `/sync-backup`을 실행하지 마라 —
  레포가 파괴된다.**
- `release/3.0.0`이 원격보다 앞서 있고 푸시하지 않았다.
- 배포 순서 규칙은 `docs/superpowers/2026-08-21-release-3.0.0-PLAN.md` 4장.

## 남은 것

Task 8(quality) → 9 `plan_plugins.py plan` → 10 `apply-base` →
11 보류 상태 기계 → 12 CLI 에뮬레이터 → 13 교대 시나리오 →
**14 세 스킬 배선(사용자 가치가 여기서 처음 나온다)** → 15 문서 정정 여덟 곳.

그다음 plan ③(다운그레이드·호환 확장, spec 11장). 완료 정의와 plan ③으로 넘길 것은
plan 본문 말미에 있다.
