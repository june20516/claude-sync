# 다음 세션 인계 — plan ② **완료**, spec 4차 개정 반영됨

- 갱신: **2026-08-31**
- 브랜치: `feat/plugin-config` (푸시 안 됨), HEAD `63f87e5`
- 테스트: **898 passed** (착수 시 446)
- **상태: Task 1~15 전부 완료. plan ②는 끝났다.**
  그 뒤 전체 감사 2건 + 실환경 스모크 2회가 **spec을 고쳐야 하는 다섯**을 확정했고,
  **spec 4차 개정(0.3장)과 plan 본문 파급이 반영됐다**(`e1f4968`·`63f87e5`).
- **다음은 코드 라운드다** — spec 4차 개정을 코드에 반영한다. 목록은 **spec 12.1**.
- **task 수가 15 → 16이다** — 사용자 결정으로 Task 10.5(설치 집합 읽기)를 중간 삽입했다.

---

## 붙여넣을 프롬프트

```
claude-sync 저장소에서 spec 4차 개정(0.3장)을 코드에 반영하는 라운드를 시작한다.

먼저 이 문서를 읽어라: docs/superpowers/2026-08-26-plan2-progress-HANDOFF.md
그다음 spec 12.1(파일별 목록)과 0.3장(왜 바뀌었는가), 그리고
docs/superpowers/2026-08-29-plugin-cli-smoke.md(모든 근거가 여기 있다).

plan ②는 끝났다. 이 라운드가 고칠 것은 프로덕션 코드·에뮬레이터·세 SKILL.md다.
/sync-backup과 세 스킬을 실행하지 마라 — 이 기기의 캐시가 옛 버전이라 레포가 파괴된다.
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
| **15** | ✅ | 문서 정정 여덟 곳 + `tests/test_user_docs.py` (새 한계 일곱을 네 문서에 잠갔다) |
| — | ✅ | **감사 3건 + 실환경 스모크 2회** → **spec 4차 개정**(0.3장)과 plan 본문 파급 |

**다음 행동:** spec 4차 개정을 **코드에 반영**한다. 파일별 목록은 **spec 12.1**이고,
왜 바뀌었는지는 **spec 0.3장**, 근거 실측은 `docs/superpowers/2026-08-29-plugin-cli-smoke.md`다.
plan 본문의 해당 task에는 `[2026-08-31 갱신]` 블록이 붙어 있다(Task 5·6·7·8·9·10.5·12·14).

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

## Task 15가 밟을 지뢰 (전부 실측) — **Task 15는 끝났다. 아래는 이력이다**

**① `sync-backup/SKILL.md:33·36·42`가 같은 파일의 5단계와 정면으로 어긋난다.**
앞머리는 아직 *"두 필드만 추출"*, *"매 백업마다 통째로 새로 생성되어 덮어쓰인다"*라고 말하는데
5단계는 전체를 수집하고 키 단위로 병합한다. **Task 15의 첫 대상이고, 그때까지 이 파일은
자기모순 상태다.** spec 13장 첫 표 7·8행이며 `task-15.md`의 Files·Step 1이 명시적으로 가져갔다.

**② `task-15.md` Step 1의 가드 셋 중 둘이 공허하다.**
`assert "두 필드만" not in text`와 세 토큰 존재 단정. 위 4번(바늘이 틀려도 초록)과 같은 형태다.

**③ 모듈 docstring의 "관심사 **둘**" — 처리 완료(2026-08-31).**
Task 15는 사용자 문서 가드를 이 파일에 얹지 않고 `tests/test_user_docs.py`로 갈랐고,
그 뒤 유지보수 라운드가 남은 둘을 실제로 갈랐다 — `tests/test_script_root.py`(0단계 bash를
**실행해서** 잰다, 175줄)와 `tests/test_skill_wiring.py`(세 SKILL.md의 **배선 계약**을 읽어서
잰다, 1,516줄), 공유 상수는 `tests/skill_paths.py`. **순수 이동이었다**(수집 115 → 115,
스위트 954 그대로).

**④ Task 14가 남긴 무가드/약가드 (전부 테스트 파일 내부, 사용자 경로에 닿지 않는다)**

아래 네 자리는 **2026-08-31 분리 이후 `tests/test_skill_wiring.py`에 있다**(행 번호는
분리 전 `test_script_root.py` 기준이므로 이름으로 찾을 것).

| 자리 | 변조 | 판정 |
|---|---|---|
| `REDIRECT` | 넓히기 | SURVIVED — 단사 대응이 통째로 공허 |
| 생산자 튜플 | 축소 | SURVIVED — 순서 축 반쪽 사망 (**외부 진실 원천이 있다**) |
| 바늘 추출기 | 틀린 값 반환 | SURVIVED — 용어집 가드 공허 |
| `FOREIGN_MCP_CALL` 값 | 파일 내 무관 문자열 | SURVIVED — 절 경계 가드 공허 |
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

## 미확인 둘 — 스모크 1·2차가 ⑴을 닫았고 ⑵의 절반을 닫았다

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

**⑵ url·git 출처의 왕복 — 여전히 미측정. 다만 github 갈래는 닫혔다** (2차 스모크 9장).

| 인자 | CLI가 기록한 값 |
|---|---|
| 디렉토리 절대경로 | `{"source": {"source": "directory", "path": "<절대경로>"}}` |
| `anthropics/claude-code` | `{"source": {"source": "github", "repo": "anthropics/claude-code"}}` |
| `https://github.com/anthropics/claude-code` | **같은 github 값으로 정규화** |

**github 왕복은 닫혔다** — `marketplace_arg`가 내는 `"o/r"`와 CLI가 쓰는 `repo` 필드가 일치한다.
**`url` 갈래는 여전히 미측정이다**: https github URL이 github으로 정규화되므로 그 갈래는
**raw `.json` URL이나 비-github 호스트**에서만 나오고, 2차 픽스처로도 만들 수 없었다.
실제 CLI가 **인자에서 출처를 판별한다**는 것은 확인됐으므로 **틀린 것은 프로덕션이 아니라
에뮬레이터일 가능성이 높다**(`marketplace_add`가 여전히 언제나 github 모양을 쓴다).
spec 8.6이 이제 그 행에 **미측정 표식**을 달고, 정본 목록은 **spec 14.5**다.

**2차 스모크가 추정 1·8·10을 닫았다** — 셋 다 **에뮬레이터가 맞았다**:
`marketplace remove`가 `pluginConfigs`까지 지우고(추정 1), `install`이 다른 스코프 항목을
보존하며(추정 8), 소속 플러그인이 **둘 다** 사라진다(추정 10 — false-positive 규칙 자체는
여전히 미측정). `tests/plugin_cli.py`의 모듈 docstring이 아직 1·10을 *"추정"* 이라 적으므로
**다음 라운드가 정정한다.**

---

## 다음 라운드로 넘길 것 — **셋 다 spec에서 결론이 났다. 남은 것은 코드다.**

`99-completion.md`의 "다음 plan으로 넘길 것"이 정본이고, 파일별 목록은 **spec 12.1**이다.

**① 깨진 레포 JSON의 restore 취급 — spec 9.3.6이 규정했다(4차 개정 ①).**
`ks.load_backup`은 구문이 깨진 파일을 **빈 문서(`{}`)로 degrade**하는데, 그 근거는
**backup 방향으로만** 쓰여 있었다. restore에서는 `local_stale`이 **`uninstall --scope user`
제안**으로 이어져, 파일 하나가 깨졌을 뿐인데 계획이 "이 기기의 플러그인을 전부 지웁시다"를
최상위 `ok`와 함께 낸다(실측 재현됨).
→ 당시 **사용자 결정: restore는 전체 skip, backup은 지금대로 유지.**
**[2026-08-31 갱신 — 처리 완료, 결정이 뒤집혔다]** ④의 실측을 받아 사용자가
**backup도 문서 단위 skip**으로 정했다(spec 0.4 · 5차 개정 ⑥). `ks.load_backup`이
구문 깨짐에 `BrokenBackupSyntax`를 던지고, **여섯 스크립트**(`collect_*`·`compare_*`·
`plan_*`, MCP·플러그인 양쪽)가 그것을 `{"status": "skipped"}`로 접는다. 세 `SKILL.md`에
"그 문서만 건너뛰고 나머지는 진행한다"와 구문 깨짐용 안내(레포 파일 수정)가 들어갔다.

**② `defaultEnabled` 걱정은 대부분 사라졌다 — 2차 스모크가 없앴다(7장 귀결 1).**
`install`이 설치 시 키를 **명시적으로** 쓰므로, **설치된 플러그인**에 대해서는
`local_masked.get(k, True)`의 기본값에 도달하는 경로가 없다. 남은 것은 좁은 갈래 하나다:
**2·4단계 어느 명령의 대상도 아니면서 로컬 `enabledPlugins`에 키가 없는 id.**
그 갈래의 `disable` exit 1은 **상태를 파괴하지 않는 거짓 실패**이고, spec 10.2가
*"이미 그 상태입니다"* 로 구별해 실패로 렌더링하지 않게 규정했다.
완전히 닫으려면 설치된 플러그인의 `defaultEnabled`를 되읽어야 하는데 **그 파일이 미측정**이다
(spec 14.5 #4).

**③ 「미확인」 ⑴ — spec 9.3.1이 규정했다(4차 개정 ②③).**
복원 실행 순서를 **`1 → 2 → 4 → 3`**으로 바꾸고 **번호는 유지한다**(9.3.2가 번호로
`depends_on`을 참조한다). 3단계의 *"현재 상태와 다를 때만"* 판정은 **실행 시점의 로컬 값**을
본다. *"4단계를 값 보존형으로"* 는 **CLI에 `configure` 서브커맨드가 없어**(스모크 10장)
존재하지 않는 선택지였다.

**④ ~~새로 열린 것~~ — backup 방향의 `{}` degrade**(spec 15장 오픈이슈 6). **닫혔다(2026-08-31).**
그 degrade의 근거(*"다음 백업이 되돌린다"*)는 **base가 없을 때만 참이다**(실측). base가 있으면
레포의 모든 키가 **케이스 4**로 떨어져 병합 결과가 `{}`가 되고 그것이 레포에 쓰인다 —
`status: "ok"`인 채로, 그리고 다음 백업도 같은 판정을 반복하므로 **자기 회복이 아니라 안정된
소실**이다. 4차 개정은 사용자 결정("유지")에 따라 **근거만 좁혔고**, 그 실측을 다시 받은
사용자가 **결정을 뒤집어** 5차 개정이 backup·status도 문서 단위 skip으로 돌렸다(①에 반영).
**재현이 테스트로 고정됐다** — 정상/깨짐 두 갈래가 같은 픽스처를 공유하고 마지막 단정이
*"레포에만 있던 항목이 살아남는가"* 로 같다(`test_plugin_scripts.py`·`test_mcp_scripts.py`).

**⑤ 같은 언어의 두 문서를 똑같이 고치는 산문 편집은 아직 잡히지 않는다**
(plan 본문 Task 15 Step 4b에서 옮겨 왔다 — 그 자리에는 독자가 없었다).
짝 비교는 두 문서가 같아지므로 통과하고, 한↔영 토큰 서명은 백틱이 없는 문장을 보지
못한다(영어 둘·한국어 둘·**네 문서 전부 SURVIVED** — 실측).

**"잡을 방법이 없다"는 아니다.** 한국어 절반은 **spec 13장의 한국어 불릿 일곱**이라는
저장소 안 원천에 같은 순번으로 묶으면 닫힌다 — 같은 순번 불릿의 최장 공통 구간이 clean에서
최소 9자, 보안 뒤집기에서 7자, 복제에서 2자로 갈린다(리뷰가 약 40줄 프로토타입으로
clean 통과 / KO·EN·네 문서 변조 전부 CAUGHT를 실측했다). 한국어 쪽은 **손으로 고른 진실이
하나도 늘지 않는다** — 값이 전부 spec에서 나오고, `test_user_docs.py`가 `NEEDLE_SOURCES`로
이미 쓰는 idiom이다. 영어 절반은 저장소 안에 원천이 없어 `CORRECTIONS`와 같은 개수-잠금
핀 문구가 따로 필요하다. **시도할 값이 있다** — 이 구멍의 대표 사례가 *"플러그인 설정 값이
평문으로 동기화된다"* 는 **보안 서술의 정반대**이고, 그것이 사용자의 백업 레포로 복사되는
파일에 들어간다.

---

## Task 15 변조 라운드 셋 — **이력** (plan 본문에서 옮겨 왔다)

점수는 그때의 스위트 크기(844~849 passed)에 묶여 있어 **재현되지 않는다.** 규정(무엇을
어느 자리에 돌리는가)은 plan 본문 Task 15 Step 4b에 남겼고, 여기 있는 것은 라운드가
어떻게 흘렀는지의 기록이다.

| 라운드 | 결과 | 대조군 |
|---|---|---|
| 1 | 19종 중 18 CAUGHT, 1 SURVIVED | CONTROL_OK (844 passed) |
| 2 (spec 준수 review 뒤) | 14종 중 13 CAUGHT, 1 SURVIVED | CONTROL_OK (845 passed) |
| 3 (quality review 뒤) | 14종 전부 CAUGHT, SURVIVED 0 | CONTROL_OK (849 passed) |

2라운드의 review가 1라운드가 놓친 SURVIVE 둘을 찾았고(공허한 `pc.SENTINEL in sec`,
positive 대응이 없던 `"두 필드만" not in sec`) 둘 다 닫았다. 3라운드는 review가 SURVIVED로
신고한 셋(Q1·Q2·Q5)을 축자로 재현해 전부 뒤집었다.

**대조군이 실제로 일했다.** 3라운드 첫 실행이 `CONTROL_BROKEN`으로 멈췄는데, M3 검증
중에 돌린 `git checkout README.md`가 **아직 커밋하지 않은 편집을 되돌린 것**이었다.
로컬 스위트는 그 편집 **전에** 마지막으로 돌아 초록이었으므로, 대조군이 없었으면 그
상태로 커밋됐다. **`git checkout`으로 변조를 되돌리지 말 것**이 여기서 나왔다.

**"닫을 수 없다"는 이 plan에서 여섯 번 과장으로 판정됐다.** 마지막 것은 *"산문을 언어를
가로질러 비교할 방법이 없다"* 였고, 바로 위 ⑤가 그것을 뒤집었다 — *"예외를 인정하기 전에
원천을 전수로 훑는다"* 를 교훈으로 적은 **같은 커밋**에서 나온 과장이었다.

---

## 다음 라운드가 고칠 자리 (전수 — spec 개정을 인용하는 자리를 훑었다)

**세 `SKILL.md`는 spec 절 번호를 하나도 인용하지 않는다**(전수 grep 0건). 절 번호가 아니라
**규정 문장**이 어긋나므로 아래는 문장 단위 목록이다.

| 파일:행 | 지금 뭐라고 하는가 | 무엇으로 |
|---|---|---|
| `sync-restore/SKILL.md:255-266` | `5-3 값 맞추기` → `5-4 설정 채우기` 순서 | **실행을 `5-4 → 5-3`으로.** 절 번호는 유지 (spec 9.3.1) |
| `sync-restore/SKILL.md:257` | *"설치 직후 값은 `true`이므로 그 외에는 부를 것이 없다"* | `install`은 매니페스트 `defaultEnabled`를 쓴다. **5-3 직전에 로컬 `settings.json`을 다시 읽어** 그 값으로 판정한다 |
| ~~`sync-restore/SKILL.md:229` 부근~~ **완료(5차 개정)** | 최상위 `status` 분기 | 구문 깨짐이 `"skipped"`로 오는 갈래를 함께 안내 (spec 9.3.6). `sync-backup`·`sync-status`도 같은 형태로 함께 넣었다 |
| `sync-restore/SKILL.md:302-315` (5-6) | *"이 기기는 버전 제약을 표현할 수 없어 레포의 값을 보존합니다"* | **"그리고 이 기기에서 그 플러그인은 꺼진 상태입니다"** 를 더한다 (스모크 3장) |
| ~~`lib/keyed_sync.py:146-168` `load_backup`~~ **완료(5차 개정)** | 구문 깨짐을 `{}`로 degrade. docstring이 *"다음 백업이 정상 내용으로 되돌린다"* | **`BrokenBackupSyntax`를 던진다.** degrade 갈래는 남기지 않았다 — backup 방향도 skip이 되어 프로덕션 호출부가 없어졌고, 아무도 부르지 않는 fail-open을 가장 눈에 띄는 이름으로 남기지 않는다 |
| ~~`plan_plugins.py:143·390`·`plan_mcp.py:34·66`·`collect_*`·`compare_*`~~ **완료(5차 개정)** | `load_backup`의 `{}`를 그대로 받는다 | 여섯 스크립트가 문서 단위 `{"status": "skipped"}`로 접는다 |
| `plan_plugins.py:129-145` docstring | *"3단계가 되돌려 주지도 않는다 — 그 목록은 **계획 시점의** 로컬 값으로 정해진다"* | 순서가 바뀌면 이 문장이 반대가 된다. 함께 고칠 것 |
| `lib/plugin_config.py:961` `value_command` | *"9.3.1의 3단계"* | 판정 시점(실행 시점)을 명시 |
| `lib/plugin_config.py:351` `read_hold_inputs` | *"두 실패는 범위가 다르다(spec 9.1.2·9.3.6)"* | **spec 3.5**를 함께 가리킨다 — 그 절이 이제 *"접는 값 × 그 값을 읽는 자리"* 표의 정본이다(지금은 이 docstring이 유일한 정본이었다) |
| `tests/plugin_cli.py` `install` | 언제나 `True` | **매니페스트 `defaultEnabled` 규칙.** 이것이 없으면 교대 테스트가 "4단계가 3단계를 되돌린다"를 재현할 수 없다 |
| `tests/plugin_cli.py` `marketplace_add` | 언제나 github 모양 | 인자에서 출처 판별 (url·git 시나리오의 선행 조건) |
| `tests/plugin_cli.py` 모듈 docstring 1·10 | *"실측 없음 — 추정"* | **2차 스모크가 닫았다**(추정 1·8·10 전부 에뮬레이터가 맞았다) |
| `tests/plugin_cli.py:340-352` docstring | *"url·git 출처도 마찬가지이므로 6번을 먼저 고칠 것"* | 그대로 유효 — github 갈래만 닫혔다 |

**spec 14.1이 회귀 테스트 다섯 줄을 새로 요구한다**(4차 개정 ①②③⑤). 그 다섯이 없으면
이 개정은 되돌릴 수 있는 상태로 남는다.

---

## 배포 전 확인 (변하지 않았다)

- **이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이다. `/sync-backup`을 실행하지 마라 —
  레포가 파괴된다.** subagent 지시마다 이 문장을 넣을 것. Task 14부터는 스킬 자체를 실행하는
  것도 금지다(배선이 실제로 새 스크립트를 부른다).
- `release/3.0.0`이 원격보다 앞서 있고 푸시하지 않았다.
- 배포 순서 규칙은 `docs/superpowers/2026-08-21-release-3.0.0-PLAN.md` 4장.
