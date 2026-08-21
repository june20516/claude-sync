# MCP 백업 재설계 — 현재 지점과 재개 방법

- 갱신: 2026-08-20
- 브랜치: `fix/mcp-config-source` (푸시 안 됨, 로컬 전용)
- 기준 커밋: `c99d5a4` (작업 시작 직전)
- **상태: plan의 13개 task 전부 완료 + 스키마 가드 추가. `release/3.0.0`에 머지됨.**
- **배포는 버전 호환성 작업과 함께 한다 — `2026-08-21-release-3.0.0-PLAN.md` 참조.**

이 문서만 읽으면 새 세션에서 이어받을 수 있도록 쓴다.

## 1. 무엇을 하고 있나

`claude-sync` 플러그인의 MCP 서버 백업이 사실상 동작하지 않는다는 이슈가 보고되었다.
조사 결과 보고된 4개 결함과 추가로 발견한 2개가 **단일 근본 원인**에서 나왔다:
`claude mcp list`의 사람이 읽는 텍스트 출력을 기계 파싱의 데이터 소스로 삼은 것.

해결책은 데이터 소스를 `~/.claude.json`의 top-level `mcpServers`(user 스코프)로 바꾸고,
backup·status·restore가 `lib/mcp_config.py` 단일 모듈만 통해 MCP를 다루게 하는 것.

측정된 출발점: 이 환경의 user 스코프 서버 3개(`playwright`, `context7`, `safari-mcp-stp`) 중
**복원 가능한 형태로 백업된 것은 0개**였다.

## 2. 읽어야 할 문서

| 문서 | 상태 |
|---|---|
| `docs/superpowers/specs/2026-08-20-mcp-config-source-design.md` | **현행 설계. 유일한 근거 문서.** |
| `docs/superpowers/plans/2026-08-20-mcp-integration.md` | **완료됨.** 13개 task 전부 구현·커밋 |
| `docs/superpowers/plans/2026-08-20-mcp-config-source.md` | **폐기됨.** Task 1~5의 기록으로만 |
| `~/.claude/suberpowers/reviews/2026-08-20-claude-sync-*.md` | 리뷰·감사 보고서 (14일 후 자동 삭제) |
| `docs/superpowers/2026-08-20-plugins-sync-followup-BRIEF.md` | **후속 과제.** `plugins.json`의 동일 결함 — 실측·설계 기준·유의사항 |
| `docs/superpowers/2026-08-21-version-compat-BRIEF.md` | **후속 과제.** 버전 표식·차단·복구, 명령어 3종별 반영 사항 |
| `docs/superpowers/2026-08-21-release-3.0.0-PLAN.md` | **3.0.0 릴리즈 전체 계획.** 무엇이 실리고 어떤 순서로 배포하는지 |

## 3. 완료된 것

**`2026-08-20-mcp-integration.md`의 13개 task를 전부 구현·검증했다. 테스트 159개 통과.**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q   # 159 passed
```

| 영역 | 결과 |
|---|---|
| `lib/mcp_config.py` | `next_base`에 redact 내부 적용, `restorable`·`restore_plan`(버킷 9개) 신설 |
| `sync-backup` | `collect_mcp.py` 신설, SKILL.md 재작성, `parse_mcp.py` 삭제 |
| `sync-status` | `compare_mcp.py`를 `mcp_config.diff` 기반으로 재작성, MCP 어휘 분리 |
| `sync-restore` | `plan_mcp.py`(`plan`/`apply-base`) 신설, SKILL.md 6단계를 `add-json` 흐름으로 재작성 |
| 테스트 | `test_mcp_state_machine.py`(반복 적용 10종), `test_mcp_scripts.py`(스크립트 계약 25종), `test_mcp_cycle.py`(backup↔restore 교대 12종) |
| 문서·버전 | README 4종 정정, 2.0.0 → **3.0.0** (스키마 v2는 역호환 없음) |

**세 스킬이 모두 `lib/mcp_config.py`만 통해 MCP를 다룬다.** 옛 정규식 파서는 삭제되었다.

### 실환경 스모크 결과 (Task 13)

이 기기의 실제 `~/.claude.json`(사본)으로 확인했다:

- user 스코프 서버 3개(`context7`·`playwright`·`safari-mcp-stp`)가 **전부 복원 가능한 형태로 기록**되었다.
  이슈 보고 당시 0개였다. 공백이 든 `command`(Safari)가 보존되고, `headers` 값은 `<REDACTED>`,
  키 이름(`CONTEXT7_API_KEY`)은 남는다.
- 백업 직후 `compare_mcp.py`가 `only_local/only_repo/changed` 전부 빈 배열 — **Bug #2(영구 미수렴) 해소.**
- local 스코프 서버(`atlassian`)가 있는 프로젝트 디렉토리에서 실행해도 출력이 동일 — **Bug #5(cwd 의존) 해소.**
- `claude mcp add-json ... --scope user`로 임시 서버 등록·제거가 정상 동작했다(`unrestorable` 0건).
  실제 설정은 스모크 전후가 동일하다.

## 4. 남은 것

**이 작업(MCP 재설계)의 코드는 끝났다.** 3.0.0 릴리즈에는 **버전 호환성 대처**가 함께
실려야 완결되며, 그 작업은 별도 세션에서 진행한다.

- 릴리즈 전체 계획: `2026-08-21-release-3.0.0-PLAN.md`
- 남은 작업의 착수 문서: `2026-08-21-version-compat-BRIEF.md`

`main`에는 아직 아무것도 머지하지 않았다. 두 작업이 `release/3.0.0`에 모인 뒤
한꺼번에 배포한다. **배포는 외부 동작이므로 사용자 승인을 받고 실행한다.**

## 5. 설계에서 반드시 알아야 할 것

구현 도중 code review가 **설계 결함 세 건**을 찾아냈다. 전부 "상태 기계를 반복 적용하면
발산하거나 탈출구가 없는" 종류였고, 전부 구현자가 아니라 설계가 틀린 것이었다.
같은 실수를 되풀이하지 않으려면 다음을 기억해야 한다.

**(1) base는 로컬이 동의한 값만 전진한다.**
초기 설계는 "푸시 성공 && 충돌 없음 → base ← 레포 파일 전체"였다. 이 규칙은 타 기기가
추가·변경한 값까지 base에 기록해, **다음 백업이 그것을 "내가 삭제했다"로 오독**한다.
새 기기에서 restore 없이 backup을 두 번 하면 다른 기기 서버가 경고 없이 전멸했다.
`update_base.py`가 파일 단위로 이미 지키던 불변식을 키 단위로 옮겨 해결했다(`next_base`).
**전역 게이트는 제거되었다. 되살리지 말 것.**

**(2) 신뢰할 수 없는 이력은 `{}`가 아니라 `None`이다.**
손상된 base 블롭을 `{}`로 읽으면 "이력이 비어 있었다"로 오인되어 삭제·충돌 판정의 근거가 된다.
`parse_base`가 이 구별을 담당한다. 같은 이유로 `read_local_servers`는 파일을 못 읽으면
`{}`가 아니라 예외를 던진다.

**(3) 모든 상태에 탈출구가 있어야 한다.**
케이스 4(타 기기가 삭제, 로컬 잔존)와 케이스 8(타 기기가 변경, 로컬은 옛 값)은
안정 상태이므로 사용자가 명시적으로 선택하지 않으면 영원히 유지된다.
그래서 restore가 각각 3선택지를 제시한다. **안정적인 것과 해소 가능한 것은 다르다.**

**(4) 마스킹은 양쪽에 적용한 뒤 비교한다.**
로컬은 평문, 레포는 `<REDACTED>`이므로 원본끼리 비교하면 비밀을 가진 서버가 영구히
"변경됨"으로 보고된다 — 원래 이슈의 미수렴 증상과 같은 종류다.
`diff`·`merge`·`restore_plan`·`next_base` 모두 내부에서 `redact`를 적용한다.

**(5) `claude mcp add-json`의 실제 제약** (실측 확인)
- 이름은 영숫자·하이픈·언더스코어만. 공백 든 이름은 거부된다.
- 기존 이름을 덮어쓰지 못한다(`already exists`). 바꾸려면 `remove` → `add-json` 2단계.

## 6. 작업 방식에 대한 교훈

- **판정표를 100% 덮은 테스트가 전부 통과하는데도 시스템이 데이터를 잃을 수 있다.**
  단발 호출 테스트만으로는 상태 기계 결함을 잡지 못한다. 반복 적용·교대 적용 테스트가 필요하다.
- **설계 단계에서 상태 전이를 코드로 시뮬레이션하라.** 머릿속으로 고른 시나리오만 보면
  놓친다. 이 프로젝트에서 Critical을 잡은 것은 전수 시뮬레이션이었다.
- **정확한 코드까지 박힌 plan을 설계가 굳기 전에 쓰지 마라.** Task 1~5 동안 spec이 여섯 번
  바뀌었고 그때마다 plan 후반부가 낡았다.
- subagent에게 작업을 맡길 때 커밋은 경로를 명시하라(`git commit -m "..." -- <paths>`).
  경로를 안 주면 subagent가 staging해둔 파일이 섞인다.

## 7. 재개 방법

```bash
cd /Users/bran/personal/claude-sync
git checkout release/3.0.0
uv run --with pytest pytest plugins/claude-sync/tests -q   # 159 passed 확인
```
MCP 재설계 구현은 끝났다. 이어받을 것은 버전 호환성 작업이며, 착수 방법은
`2026-08-21-release-3.0.0-PLAN.md` 3장에 있다.
