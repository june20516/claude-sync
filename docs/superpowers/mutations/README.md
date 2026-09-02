# 변조 명세 corpus (plan ③·④)

각 task의 **Step 4b**가 돌린 변조 명세다. 여기 있는 이유는 하나다 — **이 plan의 완료
정의("Step 4b가 실제로 돌았다")를 검증할 수 있게 하려는 것**이다. plan ③ 착수 시점에는
명세가 세션 스크래치패드에만 있어 corpus가 휘발성이었고, 그래서 완료 주장을 되짚을 수
없었다(Task 13 Step 3).

## 돌리는 법

```bash
python3 ~/.claude/suberpowers/tools/mutate.py \
  --repo /path/to/claude-sync \
  --spec docs/superpowers/mutations/plan3-task-09.json --jobs 4
```

하네스는 무동작 대조군(`C0`)을 먼저 단독으로 돌린다. 대조군이 실패하면 나머지를 돌리지
않는다 — 거짓 CAUGHT를 낼 수 있는 상태에서 나온 판정은 전부 무효다.

## 형식

`{"id", "desc", "file", "old", "new"}` — 치환이 여럿이면 `"count"`. **`old`는 대상 파일에
정확히 한 번** 나타나야 하고, 실제 치환 횟수가 다르면 `APPLY_FAIL`로 보고된다.

> **`APPLY_FAIL`을 `SURVIVED`로 읽지 말 것.** 이름을 바꾸는 커밋은 기존 앵커를 낡게 만든다.
> 치환이 안 먹은 것을 "통과했으니 SURVIVED"로 읽으면 그 자리가 조용히 뚫린다.
> 실제로 두 번 났다 — Task 7의 `P5`(앵커가 두 자리에 매치)와 Task 13의 `T6`(동작이 같은
> **등가 변조**라 아무것도 재지 않았다). 둘 다 앵커·내용을 고쳐 다시 돌렸고, 이 디렉토리에
> 있는 것은 **고친 판**이다.

## 무엇이 있고 무엇이 없나

| 파일 | task | 변조 | 마지막 재실행 판정 |
|---|---|---|---|
| `plan3-task-04.json` | 4 `schema` 맵 | 6 | **S5만 SURVIVED — 등가 변조** (아래) |
| `plan3-task-07.json` | 7 3차 스모크 반영 | 6 | 전부 CAUGHT |
| `plan3-task-08.json` | 8 4단계의 로컬 확장 값 | 8 | 전부 CAUGHT |
| `plan3-task-09.json` | 9 비원자적 로컬 쓰기 | 8 | 전부 CAUGHT |
| `plan3-task-10.json` | 10 산문 층의 자기 축소 | 6 | 전부 CAUGHT |
| `plan3-task-11.json` | 11 사유를 구조로 | 7 | 전부 CAUGHT |
| `plan3-task-12.json` | 12 `excluded_in_repo`의 3-way | 6 | 전부 CAUGHT |
| `plan3-task-13.json` | 13 남은 측정과 corpus 위생 | 6 | 전부 CAUGHT |
| `plan4-task-01.json` | 1 `reject`의 두 갈래 | 5 | 전부 CAUGHT |
| `plan4-task-02.json` | 2 `in_sync`의 기준선 | 5 | 전부 CAUGHT |
| `plan4-task-03.json` | 3 표식이 레포 트리를 걷는다 | 5 | 전부 CAUGHT |
| `plan4-task-04.json` | 4 status의 `no_base` 묶음 | 5 | **M4만 SURVIVED — 등가 변조** (아래) |
| `plan4-task-05.json` | 5 README의 표식 문장 | 3 | 전부 CAUGHT |
| `plan4-task-06.json` | 6 MCP 계획의 `sections` 층 | 5 | 전부 CAUGHT (Task 8 뒤 앵커 갱신) |
| `plan4-task-07.json` | 7 복원 불가 사유 함수 | 5 | **M4만 SURVIVED — 등가 변조** (아래) |
| `plan4-task-08.json` | 8 세 스크립트의 `unrestorable` | 5 | 전부 CAUGHT |
| `plan4-task-09.json` | 9 `prune_mcp`와 고정점 | 5 | 전부 CAUGHT |
| `plan4-task-10.json` | 10 backup 6.5단계 | 5 | 전부 CAUGHT |
| `plan4-task-11.json` | 11 `broken_syntax` 진단 | 5 | **M4만 SURVIVED — 등가 변조** (아래) |
| `plan4-task-12.json` | 12 `broken_syntax` 문구 여섯 줄 | 5 | 전부 CAUGHT |
| `plan4-task-13.json` | 13 언어 스위치 | 5 | 전부 CAUGHT |
| `plan4-task-15.json` | 3.1.1 `mapfile` 이식성 | 5 | 전부 CAUGHT |

**`S5`는 등가 변조다(SURVIVED가 정상).** 완전성 단정의 기대 집합을 상수 대신 리터럴로
바꾸는 변조인데, 오늘 그 리터럴이 상수와 같아서 통과/실패가 **완전히 동일**하다. 그 규칙
(*"기대 집합을 상수에서 뽑는다"*)이 지키는 것은 오늘의 결함이 아니라 **`BACKUP_RELPATH`가
바뀌는 날의 거짓 실패**다. 이것을 잡는 가드를 더하는 것은 「가드의 가드」이므로 만들지 않는다.

**Task 1~3·5·6의 명세는 없다.** 그 세션들의 스크래치패드에 있었고 회수하지 못했다. 되살리려면
그 task들이 도입한 가드를 다시 읽고 명세를 새로 써야 하는데, 그것은 "그때 실제로 돌린
것"이 아니라 **새 corpus**다 — 그렇게 만든 파일을 옛 실행의 증거로 두면 이 디렉토리가
존재하는 이유가 무너진다. 그 판정의 근거는 `docs/superpowers/2026-08-31-plan3-progress.md`의
기록과 `~/.claude/suberpowers/reviews/`의 리뷰 보고서 열둘이다.

**검증 시점:** 2026-09-01, 네 명세 전부 재실행해 `SURVIVED`·`APPLY_FAIL` 0건.
대조군은 **1173 passed**였다. 명세는 그 시점의 트리에 대한 것이므로, 코드가 바뀌면
앵커가 낡는다 — `APPLY_FAIL`이 나오면 **앵커를 갱신하고 다시 돌린다.**

## plan ④ (3.1.0) — 열셋 전부 있다

plan ③과 달리 **task 열넷 중 코드·산문을 바꾸는 열셋 전부**의 명세가 여기 있다(Task 14는
릴리즈 게이트라 자기 변조가 없고, 대신 위 열셋을 전부 재실행하는 것이 그 task의 검증이다).

**등가 변조 셋(SURVIVED가 정상).**

- `plan4-task-04.json` `M4` — status 테스트의 대조군 절반(기준선을 쓰고 진짜 충돌을 확인하는
  쪽)을 삭제한다. 남은 절반이 여전히 참이므로 스위트는 초록이다. 이 변조가 재는 것은
  "대조군이 있는가"이고 그것은 테스트가 아니라 **리뷰**가 지키는 성질이다.
- `plan4-task-07.json` `M4` — `unrestorable_reason ⟺ restorable` 동치 픽스처에서 정상 케이스
  둘을 뺀다. 그러면 "항상 사유가 있다"는 구현으로도 단정이 참이 된다. 같은 이유로 등가다.
- `plan4-task-11.json` `M4` — `broken_syntax` 판정의 파라미터에서 `plugins` 케이스를 뺀다.
  두 문서에 같은 코드가 돌므로 오늘은 재는 것이 같다.

**보강한 자리 하나.** `plan4-task-09.json` `M4`(`if pruned:` 가드 제거)는 처음에 SURVIVED였다
— 같은 v2 문서를 다시 써도 바이트가 같아 기존 단정이 아무것도 재지 못했다. 규칙대로 구현이
아니라 **테스트를 보강했다**: `test_prune_does_not_rewrite_the_repo_document_when_it_prunes_nothing`이
v1 배열 문서를 픽스처로 써서, 지운 것이 없는데 다시 쓰면 문서가 v2로 승격되는 것을 잡는다.

**검증 시점:** 2026-09-02, 열세 명세 전부 재실행해 `APPLY_FAIL` 0건 · SURVIVED는 위 셋뿐.
대조군은 **1265 passed**였다. 마지막 재실행 커밋: `ff83930`.

## 3.1.1 — 스모크가 잡은 것 (2026-09-02)

`plan4-task-15.json`은 plan ④의 task가 아니라 **실기기 스모크가 찾은 결함**의 명세다.
10단계의 `mapfile`이 이 기기의 어느 셸에도 없어 base 갱신이 조용히 건너뛰어졌다.

`M1`(mapfile로 되돌리기)이 CAUGHT인 것이 이 수정의 핵심이고, `M5`는 프로세스 치환을
파이프로 바꾸면 **bash에서만** 죽고 zsh는 살아남는 것을 보인다 — 두 셸을 함께 재는 이유다.
`M4`(빈 줄 가드 제거)는 처음 SURVIVED였고, 규칙대로 구현이 아니라 **테스트를 보강**했다:
픽스처의 `in_sync`에 빈 문자열을 섞어, 걸러내지 않으면 `update_base.py`가 빈 relpath를
인자로 받는 것을 잡는다.

