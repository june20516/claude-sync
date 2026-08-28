# 다음 세션 인계 — plan ② 실행 중 (15 / 16)

- 갱신: 2026-08-28
- 브랜치: `feat/plugin-config` (푸시 안 됨), HEAD `13812c6`
- 테스트: **817 passed** (착수 시 446)
- **상태: Task 1~14 완료. 남은 것은 Task 15(문서 정정) 하나다.**
- **task 수가 15 → 16이다** — 사용자 결정으로 Task 10.5(설치 집합 읽기)를 중간 삽입했다.

---

## 붙여넣을 프롬프트

```
claude-sync 저장소에서 plan ②(플러그인 동기화 본체) 실행을 이어간다.

먼저 이 문서를 읽어라: docs/superpowers/2026-08-26-plan2-progress-HANDOFF.md

Task 1~14가 완료됐다. 마지막 Task 15(문서 정정 여덟 곳)부터 재개한다.
실행 방식은 subagent-driven이다 — task마다 새 subagent, task 사이에 spec 준수 review와
code quality review.
```

---

## 지금 어디인가

| Task | 상태 | 결과물 |
|---|---|---|
| 1~7 | ✅ | 원자적 쓰기 · base_staging · 테스트 위생 · 어댑터 · 정규화·보류 · 복원 가능성 · `collect_plugins.py` |
| 8~10 | ✅ | `compare_plugins.py` · `plan_plugins.py plan` · `apply-base` |
| 10.5 | ✅ | `read_installed`, `not_installed`, 2단계/4단계 분리 |
| 11 | ✅ | 상태 기계 — 보류의 다회차 커버리지 7종 |
| 12 | ✅ | CLI 에뮬레이터 `tests/plugin_cli.py` (품질 4라운드) |
| 13 | ✅ | 교대 시나리오 열둘 + `tests/test_plugin_cli.py` 분리 (품질 3라운드) |
| **14** | ✅ | **세 스킬 배선 — 사용자 가치가 여기서 나왔다** (spec 2 + 품질 3라운드) |
| **15** | ⬜ | **문서 정정 여덟 곳 — 마지막** |

**다음 행동:** Task 15의 implementer를 dispatch한다. 규정은
`~/.claude/suberpowers/plan2-tasks/task-15.md`.

---

## 작업 자산이 어디 있나

| 무엇 | 어디 |
|---|---|
| plan 본문 (16 task) | `docs/superpowers/plans/2026-08-25-plugins-sync-body.md` |
| **task별 분할 파일** | `~/.claude/suberpowers/plan2-tasks/task-01.md` ~ `task-15.md` |
| **공통 절 (모든 task가 읽는다)** | `~/.claude/suberpowers/plan2-tasks/00-shared-context.md` |
| **완료 정의·다음 plan** | `~/.claude/suberpowers/plan2-tasks/99-completion.md` |
| 리뷰 보고서 (148개) | `~/.claude/suberpowers/reviews/2026-08-2*-claude-sync-task-*.md` |
| spec (유일한 근거 문서) | `docs/superpowers/specs/2026-08-24-plugins-sync-design.md` |

**subagent에게는 위 분할 파일 셋만 주고 plan 본문(5,300줄)은 열지 말게 한다.**

드리프트 검사(매 task 끝에 반드시):
```bash
python3 ~/.claude/suberpowers/tools/split-plan.py docs/superpowers/plans/2026-08-25-plugins-sync-body.md ~/.claude/suberpowers/plan2-tasks --check
```

---

## 이번 세션에서 바뀐 방법론 넷 (이어갈 것)

**1. 변조 축이 넷 → 다섯이다. 다섯째가 「입력 축」이다.**
공통 절의 표에 있다. 앞의 넷은 **프로덕션 가드**를 뒤집는데, 그 축에서는
*"테스트가 준 입력이 단정을 좌우하지 않는다"* 는 결함이 **원리적으로 나오지 않는다.**
다섯째는 **선택 인자·픽스처 값·회차·에뮬레이터가 만드는 상태·명령의 규약**을 뺀다.

이 축을 세운 뒤 실제로 드러난 SURVIVE: Task 13 초판에 다섯, **Task 14에 열둘**
(세 라운드 연속으로 같은 자리에서 넘어졌다 — 새로 세운 가드 자체가 자기 축소에 무방비였다).
**Task 15의 새 가드에도 반드시 적용할 것.**

**2. `split-plan.py`가 머리·꼬리까지 배포·검사한다.**
공통 절(`00-shared-context.md`)이 배포 경로에 도달하지 않은 채 `--check`가 **초록**이던
사고가 있었다 — 도구가 `^### Task N:` 절만 대조해서 머리 부분의 드리프트를 **구조적으로
볼 수 없었다.** 지금은 머리를 `00-shared-context.md`로, 꼬리를 `99-completion.md`로 내고
둘 다 `--check`에 포함한다. 헤딩을 하나도 못 찾으면 exit 1로 죽는다(옛 도구는 조용히 초록이었다).

**3. agent 간 스크래치패드가 공유된다 — 변조 spec 파일에 고유한 이름을 쓸 것.**
구현자의 `mut2.json`이 리뷰어 것과 겹쳐 덮였고 한 배치가 **빈 spec으로** 돌았다.
dispatch 프롬프트마다 `t15-<주제>.json` 같은 규칙을 넣는다.

**4. `not in` 가드는 바늘이 틀려도 초록이다.**
금지 문구를 **상수**로 두면 그 값을 바꾸는 것만으로 가드가 공허해지고 테스트는 계속 통과한다.
바늘을 **파일에서 뽑는** 형태로 써야 한다. 다만 추출기가 **틀린 비어있지 않은 값**을 내면
여전히 조용히 초록이다(Task 14 R3-M4 — 미해결). (c) 계열이 **테스트 층에서** 나온 형태다.

### 그대로 유지되는 것

- **무동작 대조군을 먼저 돌린다.** 하네스가 스스로 넣으므로 spec에 `C0`을 직접 넣지 말 것.
- **하네스를 쓴다:** `~/.claude/suberpowers/tools/mutate.py --repo <저장소> --spec <json> --jobs 6`.
  치환 횟수가 기대와 다르면 `SURVIVED`가 아니라 `APPLY_FAIL`로 갈라낸다.
- **`.pyc` 캐시 함정** — 같은 크기 파일을 같은 초에 쓰면 판정이 통째로 거짓이 된다.
- **CAUGHT가 결정적인지 확률적인지 구별한다.** set 정렬 자리는 catch가 `1 - 1/n!`.
- **하네스를 구현자에게도 준다.** "Step 4b는 최소치다 — 새 가드가 목록에 없으면 변조를
  추가하고 SURVIVE는 인계 전에 닫아라"를 지시에 반드시 넣을 것.
- **규정에 "유일한 검출자" 같은 예측을 쓰지 않는다.** 이 plan에서 **일곱 번** 반증됐다.
- **reviewer 중단 시 REPORT_FILE 체크포인트를 먼저 읽는다.**

---

## 반복되는 실패 양식 셋 (남은 task에서도 먼저 의심하라)

**(a) 공허한 단정 — 단정이 참인데 그 참이 구현의 가드에서 나오지 않는다.** 아홉 번 이상.
전형: 실패 주입 지점이 정리 코드보다 **앞** / fixture가 **다른 케이스로 떨어져** 가드를 안 탐 /
비지 않은 값을 만드는 fixture가 없어 하드코딩과 구별 안 됨.
**Task 14의 변형:** 형태는 잠갔는데 **도달성**을 안 잼 — 루프의 모양은 고정했지만 그 루프에
도달하는지는 아무도 재지 않았다.

**(b) 문장이 코드와 어긋난다.** 여덟 번 이상. **결론은 맞는데 근거가 틀린** 형태가 특히 위험하다.
**Task 14의 변형:** 새 가드의 docstring이 **자기가 못 잡는 변조를 자기 존재 이유로 인용**했다.

**(c) 조용한 fail-open.** 다섯 번 이상. 읽기 실패·판정 불가를 "항목 0개"나 성공으로 접으면
상태 기계가 그것을 **삭제**로 읽는다.

**"닫을 수 없다"는 이 세션에서 세 번 과장으로 판정됐다.** 전부 저장소의 기존 idiom
(완전성 단정 짝짓기, 뒤집으면 사라지는 어휘 걸기)으로 닫을 수 있었다. **그 주장을 받기 전에
한 번 더 의심할 것.**

---

## Task 15가 밟을 지뢰 (전부 실측)

**① `sync-backup/SKILL.md:33·36·42`가 같은 파일의 5단계와 정면으로 어긋난다.**
앞머리는 아직 *"두 필드만 추출"*, *"매 백업마다 통째로 새로 생성되어 덮어쓰인다"*라고 말하는데
5단계는 전체를 수집하고 키 단위로 병합한다. **Task 15의 첫 대상이고, 그때까지 이 파일은
자기모순 상태다.** spec 13장 첫 표 7·8행이며 `task-15.md`의 Files·Step 1이 명시적으로 가져갔다.

**② `task-15.md` Step 1의 가드 셋 중 둘이 공허하다.**
`assert "두 필드만" not in text`와 세 토큰 존재 단정. 위 4번(바늘이 틀려도 초록)과 같은 형태다.

**③ 모듈 docstring의 "관심사 **둘**"을 Task 15가 셋으로 만든다.**
`tests/test_script_root.py:31`이 *"이 파일은 관심사를 둘 담는다"*라고 적는데 Task 15 Step 1이
`USER_DOCS`·`BACKUP_READMES` 기반 사용자 문서 가드를 이 파일 끝에 더한다. **함께 갱신하지 않으면
Task 14 품질 리뷰의 I4가 그대로 재발한다.** 파일이 이미 **1,232줄에 두 관심사**다 —
분리(`tests/test_skill_wiring.py`)는 Task 15 **뒤**로 미뤄 두었다.

**④ Task 14가 남긴 무가드/약가드 (전부 테스트 파일 내부, 사용자 경로에 닿지 않는다)**

| 자리 | 변조 | 판정 |
|---|---|---|
| `test_script_root.py:1027` `REDIRECT` | 넓히기 | SURVIVED — 단사 대응이 통째로 공허 |
| `:948-950` 생산자 튜플 | 축소 | SURVIVED — 순서 축 반쪽 사망 (**외부 진실 원천이 있다**) |
| `:1130-1135` 바늘 추출기 | 틀린 값 반환 | SURVIVED — 용어집 가드 공허 |
| `:1213` `FOREIGN_MCP_CALL` 값 | 파일 내 무관 문자열 | SURVIVED — 절 경계 가드 공허 |
| 세 SKILL.md 섹션-status 문단 | 어휘를 남긴 부정 흡수 | SURVIVED |
| `sync-status/SKILL.md` 3단계 | `*` 불릿 + 문구 변경 | SURVIVED |

**⑤ 절 번호는 움직이지 않았다.** `RESTORE_BASE_SECTION`이 `"6.5 base 갱신 (스테이징 → base)"`
제목을 잠그고 있고 Task 15는 restore SKILL.md를 Modify 목록에 넣지 않았다.

---

## Task 14가 만든 것 (사용자 가치)

배선 셋의 충돌을 풀어 **삭제 전파를 되살렸다.** 그전에는 `base/plugins.json`이 영원히 생성되지
않아 `merge`가 매번 `base=None` 합집합 degrade를 타 **케이스 3·4가 영영 발생하지 않았고, 조용했다.**

- 스테이징을 `BASE_STAGING` 하나로 합치고 `rm -rf`를 두 수집 단계보다 **앞에서 한 번만** 돌린다
- base 게이트를 `for rel in plugins.json mcp-servers.json` 루프로 (backup 10단계 / restore)
- **base 이동을 `### 6.5`로 올려 어느 단계에도 속하지 않게 했다** — 그전에는 `### 6` 안에 있어서
  MCP가 skipped면(레포의 `mcp-servers.json`이 **상위 버전 형식**일 때 그렇다) 플러그인 base가
  전진하지 않았고, `keep_stale`·`keep_local`·`release` 선택이 **조용히 무효**가 됐다
- `extract_plugins.py` 삭제 (호출자 0 확인)

---

## 미확인 둘 — 2026-08-29 실환경 스모크가 하나를 닫았다

이 plan 전체에서 **실제 `claude plugin` CLI로는 아무것도 재지 않았다**(검증은 에뮬레이터·
하네스·테스트뿐이었다). 그 유예를 `docs/superpowers/2026-08-29-plugin-cli-smoke.md`가
`claude 2.1.250`으로 메웠다. 아래 둘 중 ⑴이 닫혔다.

**⑴ 4단계가 3단계를 되돌리는가 — 닫혔다. 갈래 (ㄱ)이다.** 한 id가 `disable_after_install`과
`config_keys`에 **함께** 실릴 수 있다(spec 9.3.1이 두 단계 모두 *"설치 여부로 좁히지 않는다"*로
못 박는다). 그때 사용자가 값을 입력하면 에뮬레이터에서는 복원 후 로컬 값이 **`true`**가 된다 —
레포가 `false`인데도. **실제 CLI도 그렇다**(스모크 4장 실측):

```
before: enabledPlugins={"demo@smoke-mkt": false}  pluginConfigs=null
$ claude plugin install demo@smoke-mkt --config token=s3cr3t     → exit 0
after : enabledPlugins={"demo@smoke-mkt": true}
        pluginConfigs={"demo@smoke-mkt":{"options":{"token":"s3cr3t"}}}
```

따라서 **에뮬레이터의 추정 3번이 옳았고**(갈래 (ㄴ)이 아니다), 이것은 하네스의 결함이 아니라
spec 9.3.1의 순서 규정에서 나오는 **설계상의 귀결**이다. 레포의 `false`가 그 기기에 영영
복원되지 않고 다음 백업이 로컬 `true`를 도로 민다 — **수렴이 깨진다.** spec부터 고쳐야 한다
(순서를 바꾸거나 4단계를 값 보존형으로) → **plan ③.** `pluginConfigs`의 모양
`{id: {"options": {k: v}}}`도 구현과 일치함이 함께 확인됐다.

**⑵ url·git 출처의 왕복 — 여전히 미확인. 다만 절반이 좁혀졌다.** 에뮬레이터의
`marketplace add`는 언제나 github 모양을 쓴다(6번). `marketplace_arg`는 url·git에 대해 URL
문자열을 내는데 에뮬레이터가 그것을 **github 값의 `repo` 필드**에 담는다. 복원 직후 로컬 값이
레포 값과 달라 `_next_base_sections`의 "로컬과 merged가 같은 키만 전진"에 걸리고 다음 백업이
같은 차이를 다시 보고한다 — **수렴 자체가 깨진다**(코드를 따라간 귀결, 실측 없음).
스모크가 확인한 것은 둘이다 — **실제 CLI가 인자에서 출처 종류를 판별한다**는 것(디렉토리
경로를 주니 `directory` 출처로 썼다)과 **directory 출처 값의 모양**이 가정과 정확히 같다는 것
(`{"source": {"source": "directory", "path": "<절대경로>"}}`). **url·git 두 출처의 값 모양은
재지 않았다** — 그 픽스처는 네트워크를 타지 않는 로컬 마켓플레이스 하나뿐이었다. 시나리오를
쓰려면 `plugin_cli.marketplace_add`를 **먼저 고쳐야 한다**는 인계는 그대로다.

**스모크가 닫지 못한 셋**(에뮬레이터 추정 1·8·10)은 `tests/plugin_cli.py` 모듈 docstring에
"미확인 셋을 닫는 방법"으로 픽스처 설계까지 적어 인계했다.

---

## plan ③으로 넘길 것

`99-completion.md`의 "다음 plan으로 넘길 것"이 정본이다. 큰 것 셋:

**① 깨진 레포 JSON의 restore 취급.** `ks.load_backup`은 구문이 깨진 파일을 예외가 아니라
**빈 문서(`{}`)로 degrade**한다. 그 degrade의 근거는 **backup 방향으로만** 쓰여 있다.
restore에서는 `local_stale`이 **`uninstall --scope user` 제안**으로 이어져, 파일 하나가 깨졌을
뿐인데 계획이 "이 기기의 플러그인을 전부 지웁시다"를 최상위 `ok`와 함께 낸다(실측 재현됨).
`plan_mcp.py`도 같은 구조다 — 선재하는 계열 문제다.

**② `defaultEnabled: false`인 플러그인의 복원이 조용히 실패한다.** `disable_after_install`의
현재 상태 추정 `local_masked.get(k, True)`의 기본값 `True`가 **매니페스트 가정**이다. 설치돼
있고 로컬 키가 없으며 매니페스트가 `defaultEnabled: false`면 실제로 꺼져 있는데 레포가 `true`면
`value_command(True, True) = None`이라 **아무 명령도 나가지 않는다.** 로컬 문서만으로는 닫을 수 없다.

**③ 위 「미확인」 ⑴** — **(ㄱ)으로 판명됐다**(2026-08-29 스모크 4장). 조건부가 아니라
확정된 항목이다. spec 9.3.1의 단계 순서 자체를 고쳐야 한다.

---

## 배포 전 확인 (변하지 않았다)

- **이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이다. `/sync-backup`을 실행하지 마라 —
  레포가 파괴된다.** subagent 지시마다 이 문장을 넣을 것. Task 14부터는 스킬 자체를 실행하는
  것도 금지다(배선이 실제로 새 스크립트를 부른다).
- `release/3.0.0`이 원격보다 앞서 있고 푸시하지 않았다.
- 배포 순서 규칙은 `docs/superpowers/2026-08-21-release-3.0.0-PLAN.md` 4장.
