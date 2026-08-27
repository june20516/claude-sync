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

## 사용자가 내린 결정 둘 (2026-08-26, Task 9 quality review 후)

**결정 1 — 어댑터가 설치 집합 전체를 읽는다.** Task 8이 유예한 사실을 Task 9의 P2가 다시
요구했다. 두 곳이 같은 사실을 필요로 한다:

- Task 8의 `absent_locally` — spec 9.2의 *"H3 항목은 '설치됨'과 '미설치'를 구별해 말한다"*
  를 글자대로 쓰려면 설치 집합이 필요하다. 지금은 "로컬 섹션 문서에 값이 없다"까지만
  말할 수 있어 이름을 그렇게 바꿨다.
- Task 9의 P2 — spec 9.3.1의 **2단계**(`plugin install <id>`)와 **4단계**
  (`plugin install <id> --config k=v`)를 계획이 `install` 하나로 합쳤다. 이미 설치된
  플러그인에 bare install이 나가 거짓 실패가 난다(실측 재현됨).

**`enabledPlugins`의 키 부재는 미설치가 아니다** — 매니페스트 기본값(`defaultEnabled`)에
위임하는 상태다. Task 9의 앞머리가 같은 사실을 `disable` 쪽에서 이미 명시한다. 그래서
로컬 문서만으로는 두 경우를 가를 수 없고, `installed_plugins.json`을 읽어야 한다.

`read_auto_ids`가 이미 그 파일을 파싱한다 — **auto 집합만** 뽑아 쓴다. 설치 집합 읽기를
더할 때 그 파일을 **두 번 파싱하지 말 것**(이 저장소가 반복해 막아 온 "파서 두 벌"이다).
예외 갈래도 `AutoFlagsUnavailable`과 같은 범위여야 한다 — 갈리면 부분 skip이 조용히
전체 skip이 된다.

파급: `lib/plugin_config.py`(신규 읽기) → `compare_plugins.py`(`absent_locally` 재검토)
→ `plan_plugins.py`(`install`을 2단계/4단계로 분리) → spec 9.2·9.3.1 문구 → Task 14 배선.

**결정 2 — 깨진 레포 JSON 문제(P1)는 기록만 하고 plan ③으로 넘긴다.**

`ks.load_backup`은 **구문이 깨진** 파일을 예외가 아니라 **빈 문서(`{}`)로 degrade**한다
(`decode`가 `BROKEN`이면 `return {}`). 그 degrade의 근거는 **backup 방향으로만** 쓰여 있다
— *"레포 파일 하나가 깨졌다고 백업 전체를 막지 않으며, 다음 백업이 그 파일을 정상
내용으로 되돌린다."* restore 방향에는 그 근거가 없다.

실측(레포 `plugins.json`이 `{ this is not json`, base는 정상):

```
top status: ok
enabledPlugins local_stale: ['a@m', 'b@m']
marketplaces  local_stale: ['m']
install: []
```

`local_stale`은 spec 9.3.3에 따라 **`uninstall --scope user` 제안**으로 이어진다. 파일
하나가 깨졌을 뿐인데 계획이 "이 기기의 플러그인을 전부 지웁시다"를 최상위 `ok`와 함께
낸다. 9.3.4의 3선택지와 사용자 확인이 완충하지만, 사용자가 보는 것은 **"다른 기기가
지웠다"는 거짓 근거**다.

**`plan_mcp.py`도 같은 구조다 — Task 9가 만든 문제가 아니라 선재하는 계열 문제다.**
그래서 plan ②의 범위를 늘리지 않고 plan ③(다운그레이드·호환 확장)에서 두 계열을 함께
고친다. 계약을 정할 자리는 spec이고, 갈래는 둘이다:

1. spec 9.3.6 표에 "레포 문서 **구문** 깨짐" 행을 넣고, restore에서는 backup과 달리
   접지 말고 **전체 skip**(또는 `local_stale` 억제)으로 규정한다
2. `load_backup`에 방향 인자를 두어 restore 호출부가 `BROKEN`을 예외로 받게 한다

---

## Task 14 인계 — 어떤 CLI 명령도 받지 않는 id (2026-08-27, Task 10.5)

`skipped_already_installed`에 들면서 `config_keys`·`disable_after_install` 어디에도 없는
id는 이번 restore에서 **아무 명령도 받지 않는다.** 손실은 아니다 — bare install은 이미
설치된 id에 exit 1이라 애초에 대안이 아니다. 다만 **SKILL.md가 무엇이라고 말할지**가
열려 있고, 모집단이 **둘**이다. 하나만 알고 문구를 만들면 나머지에 거짓이 나간다.

| 갈래 | 조건 | 판별 | 올바른 문구 |
|---|---|---|---|
| (b) | `enabledPlugins` 기여 + **H3 확장 포맷 값** + 이미 설치됨 | `repo_values[k]`가 **비불리언** | spec 8.4의 **"레포 값을 보존합니다"** |
| (c) | `pluginConfigs` 기여인데 되물을 option 키가 없음 | `repo_values`에 **키 부재** | 되물을 값이 없어 넘어간다 |

**(b)에 "이미 같은 상태입니다"라고 말하면 거짓이다.** `value_command`는 레포 값이
불리언이 아니면 **무조건 `None`**을 돌려주므로(`plugin_config.py`), 확장 포맷 키는 상태가
같은 것이 아니라 **아예 알려진 바가 없다.** 실행으로 재현했다 — repo
`{"enabledPlugins": {"ext@m": ["1.0.0"]}}` + installed `{"ext@m": [{"scope":"user"}]}` →
`install=[]`, `skipped_already_installed=["ext@m"]`, `disable_after_install=[]`,
`config_keys={}`.

**판별에 코드 변경은 필요 없다** — `repo_values`가 이미 계획에 실려 있다.

**`disable_after_install`이라는 이름도 재검토 대상이다.** 이제 절반만 맞다 — 이번 실행에서
설치하지 않는 id(이미 설치된 것)도 그 목록에 든다.

---

## plan ③으로 넘길 것 (2026-08-27 추가)

**`defaultEnabled: false`인 플러그인의 복원이 조용히 실패한다.** `disable_after_install`의
현재 상태 추정은 `local_masked.get(k, True)`이고, 그 기본값 `True`는 **매니페스트
`defaultEnabled`가 true라는 가정**이다(spec의 "기본 `true`"). 설치돼 있고 로컬 키가 없으며
매니페스트가 `defaultEnabled: false`인 플러그인은 **실제로 꺼져 있는데** 레포가 `true`면
`value_command(True, True) = None`이 되어 **아무 명령도 나가지 않는다.**

**로컬 문서만으로는 닫을 수 없다** — 매니페스트를 읽어야 알 수 있고, spec 9.3.1이 그
갈래를 규정하지 않는다. 구현으로 막을 수 없으므로 spec부터 정해야 한다.

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
