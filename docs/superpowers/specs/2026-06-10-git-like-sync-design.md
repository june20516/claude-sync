# claude-sync: git-like 동기화 재설계

- 작성일: 2026-06-10
- 상태: 설계 확정 (구현 계획 대기)
- 대상 레포: `june20516/claude-sync` (플러그인), 데이터 레포: `june20516/claude-settings`

## 1. 배경 & 문제

현행 claude-sync는 `~/.claude/`의 설정(agents, skills, CLAUDE.md, 플러그인 목록, MCP 서버)을 Git 데이터 레포를 통해 기기 간 백업/복원/상태확인한다. 실사용 중 다음이 드러났다.

### 1.1 Bug #1 — mtime 기반 충돌 검출 (오탐 + 구조적 결함)
- `sync-restore/scripts/analyze_conflicts.py`는 파일 내용을 보지 않고 mtime만 비교한다 (`local_mtime > backed_mtime` → conflict).
- 그런데 restore는 `cp -r`로 파일을 복사하므로 로컬 mtime이 복사 시각으로 갱신된다. 따라서 **한 번 restore하고 나면 이후 모든 파일이 영구적으로 conflict로 오탐**된다.
- `sync-status/scripts/check_status.py`는 내용 해시로 비교(정상)하는데, restore는 mtime으로 비교 → **두 스킬이 서로 다른 기준**을 쓰는 비일관.

### 1.2 Bug #2 — `plugin:` MCP 서버 오처리
- `plugin:figma:figma`처럼 플러그인이 제공하는 MCP 서버는 플러그인 설치로 따라오는 것인데,
- backup(`parse_mcp.py`)이 이를 저장하고, status(`compare_mcp.py`)가 diff로 표시하고, restore 8단계가 `claude mcp add`로 수동 등록을 시도한다 → 중복/오류.

### 1.3 더 근본적인 설계 공백
- restore가 "새로 추가(additive)"와 "덮어쓰기(overwrite)"를 구분하지 않고 **충돌 1건이면 전체 중단**한다. 그래서 기기 B가 항목 1을 가진 채 restore하면, 1이 충돌할 때 새 항목 2·3까지 막힌다.
- **충돌 판정 후 사용자가 무엇을 해야 하는지**가 정의되어 있지 않다. 스킬이 "로컬에서 직접 고쳐라"고 떠넘기는데, 그 수작업을 없애려고 만든 도구이므로 모순이다.
- 기기마다 정책이 다를 수 있다(B는 양방향, C는 pull-only로 절대 push 금지)는 요구가 반영되어 있지 않다.

## 2. 목표 / 비목표

### 목표
1. mtime 비교를 **완전히 제거**하고, 내용 해시(sha256) 기반 **3-way 비교**로 통일한다.
2. additive(새 항목)는 충돌과 무관하게 **항상 적용**, 충돌은 해당 파일만 격리한다.
3. 충돌 해소를 **스킬이 대신 수행**(사용자는 선택만)하고, 그 결과가 향후 backup↔restore 순환에서 **정합성을 깨지 않게** 한다.
4. **pull-only 기기**(절대 push 안 함)를 지원한다.
5. `plugin:` MCP 서버를 동기화 대상에서 제외한다.
6. 변경을 CC가 인식해 업데이트할 수 있게 배포한다(버전 bump + 푸시 + update).

### 비목표 (이번 범위 밖)
- 파일 **삭제 전파**: restore는 로컬 파일을 삭제하지 않는다(non-destructive). 삭제 동기화는 후속 과제.
- 풀 git 히스토리/브랜치/리베이스 흉내.
- 바이너리 파일 머지(설정은 전부 텍스트/JSON).

## 3. 핵심 모델 (git-like 3-way)

### 3.1 개념 매핑
| git | claude-sync |
|-----|-------------|
| working tree | `~/.claude/`의 실제 파일 |
| remote | 백업 데이터 레포(claude-settings) |
| origin/main (remote-tracking) = merge-base | 이 기기가 **마지막으로 reconcile한 remote 내용** = 로컬 `~/.claude/.sync-state/` |
| `git pull` (fetch+merge) | `/sync-restore` (pull-only, **자동 push 안 함**) |
| `git push` | `/sync-backup` (사용자가 명시 실행할 때만) |

### 3.2 상태 저장: `~/.claude/.sync-state/`
- `~/.claude/.sync-state/base/<relpath>` : 그 파일을 **마지막으로 reconcile했을 때의 remote 내용(bytes)**을 그대로 보관.
- 이 base 블롭이 단일 진실원천이다:
  - `seen` 해시 `S` = `sha256(base blob)` — 검출용 (on-demand 계산).
  - base **내용** — 3-way 머지용.
- 블롭 존재 여부 = 그 파일을 이 기기에서 sync한 적이 있는가(=`S`가 존재하는가).
- 작은 텍스트 파일들이라 저장 부담 없음. (성능 필요 시 `manifest.json`으로 해시 인덱스 캐시 가능 — 선택.)

**불변식(invariant): base = "이 기기가 마지막으로 reconcile한 remote 내용".** 모든 동작은 끝날 때 이 불변식을 유지하도록 base를 갱신한다.

### 3.3 비교 방법
파일마다 세 해시:
- `L` = sha256(로컬 파일)
- `R` = sha256(레포 파일)
- `S` = sha256(base 블롭) — 없으면 ∅

파생:
- `changed_local = (L ≠ S)`
- `changed_remote = (R ≠ S)`

**시각/mtime은 일절 쓰지 않는다. "어느 쪽이 최신인가"를 시간으로 판단하지 않고, base `S` 기준으로 "어느 쪽이 변했는가"로 방향을 정한다.**

## 4. restore 동작 (pull-only)

### 4.1 파일별 판정
| changed_local | changed_remote | L vs R | 판정 | 동작 | 끝난 후 base |
|:---:|:---:|:---:|---|---|---|
| N | N | L=R | in-sync | skip | ←R |
| (로컬에 없음) | — | — | 새 파일(additive) | 로컬에 추가 | ←R |
| Y | N | — | local ahead | 로컬 유지(skip) | =R(불변) |
| N | Y | — | behind | **fast-forward**: R로 덮어씀 | ←R |
| Y | Y | L=R | 우연히 동일 | skip | ←R |
| Y | Y | L≠R | **양쪽 변경** | 3-way 머지 시도(4.2) | (4.3) |
| (레포에 없음) | — | — | local_only | 건드리지 않음 | 불변 |
| `S` 없음 & L≠R(둘 다 존재) | — | — | base 없음 | 자동 머지 불가 → conflict 처리(4.3) | (4.3) |

핵심: **`changed_local && !changed_remote`(local ahead)와 `repo_only`(새 파일)는 절대 conflict가 아니다.** 그래서 B가 1을 가진 채 restore해도 2·3(새 파일/항목)은 항상 추가되고, 1이 양쪽 변경일 때만 머지/충돌로 간다.

### 4.2 자동 병합 — `git merge-file` (diff3)
`L≠S, R≠S, L≠R`인 파일은 base 내용 `S`로 3-way 텍스트 머지를 시도한다. 직접 구현하지 않고 git에 위임:

```bash
git merge-file -p --diff3 <local> <base> <repo>   # stdout = 머지 결과
# exit code 0  → 깨끗한 자동 병합
# exit code >0 → 그 수만큼 충돌 영역(겹침) 존재
```

**겹침/안겹침 판단 = diff3의 청크 분할**:
- 세 쪽 모두 동일한 라인을 앵커로 파일을 청크로 나눈다.
- 한 청크에서 local만/remote만 변경 → 그쪽 채택. 둘 다 같은 변경 → 충돌 아님.
- **두 수정 사이에 "세 쪽이 다 같은 라인"이 하나라도 있으면 다른 청크 → 안 겹침(자동 병합)**. 없어서 같은 청크에 들어가고 값이 다르면 **겹침(conflict)**.
- exit 0이면 결과를 로컬에 쓴다(로컬은 "local ahead"가 됨). exit>0이면 충돌 영역만 4.3로.

### 4.3 충돌 해소 UX (스킬이 대신 수행)
사용자는 파일시스템을 직접 만지지 않는다. 스킬이 간결한 diff를 보여주고, 사용자는 선택만 한다. 파일별(또는 일괄):

| 선택 | 로컬 | remote | base(=S) | 다음 restore | push |
|---|---|---|---|---|---|
| **백업 채택**(theirs) | ←R | 그대로 | ←R | in-sync | 불필요 |
| **로컬 유지**(ours) | 그대로 | 그대로 | **←R** | local ahead(충돌 아님) | 안 함(원하면 backup) |
| **병합**(겹친 hunk를 에이전트가 합쳐 제안→확인) | ←M | 그대로 | **←R** | local ahead | 안 함 |
| **나중에**(defer) | 그대로 | 그대로 | **불변** | **또 conflict** | 안 함 |

- **로컬 유지 vs 나중에의 차이 = base(`seen`) 갱신 여부.** 로컬 유지는 base를 현재 R로 올려 "remote 봤고 거부"를 기록 → 재충돌 안 함. 나중에는 base를 그대로 둬 다음에 또 묻는다.
- 어느 선택도 restore는 **push하지 않는다.** "로컬 유지/병합"으로 로컬이 ahead가 되면, restore는 git처럼 "로컬이 N개 앞섬 → 올리려면 `/sync-backup`"이라고 **안내만** 한다.

### 4.4 플러그인 / MCP (additive only)
- 레포 `plugins.json`의 `enabledPlugins` 중 로컬에 없는 것 → `claude plugin install`로 설치.
- 레포 `mcp-servers.json` 중 로컬에 없고 **이름이 `plugin:`으로 시작하지 않는** 것 → `claude mcp add`.
- 로컬에만 있는 플러그인/서버는 **제거하지 않는다**(non-destructive). 충돌 개념 없음(존재 여부만).

### 4.5 정합성 순환 보장
해소(나중에 제외)가 끝나면 모든 파일이 `(L, R, S)` 기준으로 **결정적 단일 분류**(in-sync / ahead / behind / conflict)에 떨어지며 진동하지 않는다. 예:
- 로컬 유지 후 상태: `R=S, L≠S` → 항상 "local ahead"로 안정. 재충돌 없음. push는 사용자가 원할 때만.
- 다른 기기는 그 변경이 push된 뒤 다음 restore에서 fast-forward로 자동 수렴.

## 5. backup 동작 (push, 명시 실행 시에만)
restore와 대칭. 각 로컬 파일에 대해:
| 조건 | 판정 | 동작 |
|---|---|---|
| L=R | in-sync | base←R |
| L≠R, R=S | local ahead | 레포에 push(레포←L), base←L |
| L≠R, R≠S | **remote가 앞섬**(누가 먼저 backup함) | **push 거부**: "restore 먼저" 안내 (git push rejected) |

- 푸시 성공 후 base←L(=새 remote).
- **`pull_only` 가드**: `~/.claude/sync-config.json`에 `"pull_only": true`이면 `/sync-backup`은 즉시 거부한다(C 기기 보호). 툴은 어떤 경우에도 자동 push하지 않으므로, 가드가 없어도 backup을 호출하지 않는 한 로컬→리모트 이동은 없다. 가드는 실수 방지용 강제 장치.
- `plugin:` MCP 서버는 저장하지 않는다(7장).

## 6. status 동작
- restore와 동일한 3-way 분류를 수행하되 **아무것도 바꾸지 않고 보고만** 한다.
- 카테고리: in-sync / 새 파일(restore 시 추가) / local ahead(backup 시 push) / behind(restore 시 ff) / conflict(양쪽 변경).
- mtime 제거. `plugin:` MCP 서버는 비교에서 제외.
- pull_only 기기에서는 "local ahead" 항목에 "이 기기는 pull-only라 push되지 않음" 주석.

## 7. `plugin:` MCP 필터 (Bug #2)
세 곳에서 일관되게 `name.startswith("plugin:")`를 제외:
- `sync-backup/scripts/parse_mcp.py` — 저장 생략.
- `sync-status/scripts/compare_mcp.py` — 현재 목록·백업 목록 양쪽에서 제외 후 비교.
- `sync-restore/SKILL.md` 8단계(산문) — `plugin:` 서버는 플러그인 설치로 복원되므로 `mcp add` 하지 않음을 명시.

## 8. 첫 sync / 마이그레이션
- 기존 `sync-metadata.json`의 mtime 필드는 **더 이상 사용하지 않는다.** `generate_metadata.py`는 mtime 대신 파일 내용 sha256을 기록(레포측 manifest/무결성용; 알고리즘은 레포 파일을 직접 해시).
- 기존 사용자는 `~/.claude/.sync-state/`가 없다(=`S` 전부 ∅). 첫 restore:
  - `L=R` → in-sync로 보고 base 기록(무충돌). (대부분의 기존 동일 파일이 여기 해당 → 깔끔히 정착.)
  - 로컬에 없음 → 추가.
  - `L≠R`(둘 다 존재, base 없음) → 안전하게 conflict 1회(사용자 해소) 후 base 기록.
- 즉 첫 실행에서 base를 세우고 나면 이후는 완전한 3-way로 동작.

## 9. 영향 파일 요약
| 파일 | 변경 |
|---|---|
| `sync-restore/scripts/analyze_conflicts.py` | **재작성**: mtime 제거, 3-way(L/R/S) 분류 + git merge-file 자동 병합 판정 |
| `sync-status/scripts/check_status.py` | **재작성**: 3-way 분류로 통일(mtime 제거), `plugin:` 제외 |
| `sync-status/scripts/compare_mcp.py` | `plugin:` 필터 |
| `sync-backup/scripts/parse_mcp.py` | `plugin:` 필터 |
| `sync-backup/scripts/generate_metadata.py` | mtime → sha256 |
| `~/.claude/.sync-state/` (신규 개념) | base 블롭 읽기/쓰기 로직 (restore·backup 성공 시 갱신) |
| `sync-restore/SKILL.md` | pull-only·additive·3-way·충돌 해소 UX·base 갱신·`plugin:` 제외 반영(재작성) |
| `sync-backup/SKILL.md` | push-rejected 가드·`pull_only` 가드·base 갱신 반영 |
| `sync-status/SKILL.md` | 새 카테고리 보고 반영 |
| `sync-config.json` 스키마 | `"pull_only": bool` 추가 문서화 |
| `.claude-plugin/marketplace.json`, `plugins/claude-sync/.claude-plugin/plugin.json` | version 1.0.0 → 1.0.1 |
| `README.md` / `README.ko.md` | 동작 모델 갱신 |

> base 블롭 읽기/쓰기는 공통 로직이므로, 스크립트 중복을 피하기 위해 작은 공용 모듈(예: `lib/sync_state.py`)로 두고 세 스킬에서 재사용하는 안을 구현 계획에서 검토한다.

## 10. 배포 & CC 인식 (완성 조건)
1. `~/dev/claude-sync`에서 위 변경 적용.
2. 검증(11장) 통과.
3. **사용자 승인 후** `origin`(june20516/claude-sync)에 커밋·푸시. (외부 동작 — 푸시 직전 확인.)
4. `claude plugin marketplace update claude-sync` → `claude plugin update claude-sync`.
5. 캐시 디렉토리가 `1.0.1` 신코드로 교체됐는지 확인.

## 11. 검증 방법
- **단위**: 픽스처(임시 디렉토리에 base/local/repo 조합)를 만들어 각 스크립트의 분류·머지 결과를 검증.
  - in-sync / 새 파일 / local ahead / fast-forward / 자동 병합(안 겹침) / conflict(겹침) 각 케이스.
  - `plugin:` 서버가 parse/compare에서 제외되는지.
- **시나리오(통합)**:
  - 내용 동일한데 conflict 뜨던 케이스 → in-sync(무충돌) 확인.
  - B가 1 보유 + restore → 2·3 추가됨 확인(1 충돌과 무관).
  - 양쪽 변경 안 겹침 → 자동 병합, 겹침 → conflict 후 해소 → 재실행 시 재충돌 없음(순환 정합).
  - pull_only 기기에서 backup 거부 확인.
- **CC 인식**: `claude plugin` 목록·캐시에 1.0.1 신코드 반영 확인.

## 12. 오픈 이슈 (구현 계획에서 확정)
- base 블롭 저장 형식: 디렉토리 미러 vs 단일 매니페스트+블롭. (현 안: `base/<relpath>` 미러.)
- 공용 모듈 도입 범위(`lib/sync_state.py`).
- 커밋되는 테스트 추가 여부(현 안: 픽스처 수동 검증, 커밋 없음 — 사용자 확인 필요).
