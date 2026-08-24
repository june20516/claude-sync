# plugins.json 동기화 — 현재 지점과 재개 방법

- 갱신: 2026-08-24
- 브랜치: `feat/plugins-sync` (`release/3.0.0`에서 분기, 푸시 안 됨)
- 분기 커밋: `1a60115`
- **상태: 실측·설계·1차 plan 완료. 다음은 `2026-08-24-keyed-sync-core.md`의 Task 1부터 구현.**
- 테스트: **383 passed** (코드 변경 없음 — 지금까지 전부 문서 작업)

이 문서만 읽으면 새 세션에서 이어받을 수 있도록 쓴다.

---

## 1. 무엇을 하고 있나

`plugins.json`이 매 백업마다 통째로 덮어써져 **기기 간 플러그인이 소실**되고, status가
켬/끔을 못 보며, 읽기 실패가 백업 전체를 중단시킨다. MCP 재설계가 `mcp-servers.json`에
대해 고친 것과 같은 결함이고, 해법의 골격도 같다 — 키 단위 3-way, "모르면 안 쓴다" 가드,
읽기 실패와 0개의 구별.

**3.0.0 릴리즈에 포함하기로 결정했다**(2026-08-24). 스키마를 또 바꿔야 하므로
사용자가 major 전환을 두 번 겪을 이유가 없다.

## 2. 읽어야 할 문서 (순서대로)

| 문서 | 상태 |
|---|---|
| `specs/2026-08-24-plugins-sync-design.md` (1434줄) | **현행 설계. 유일한 근거 문서.** 0·0.1·0.2장에 세 차례 개정 이유가 있다 |
| `plans/2026-08-24-keyed-sync-core.md` (1332줄) | **다음에 실행할 것.** Task 9개 |
| `2026-08-20-plugins-sync-followup-BRIEF.md` | 실측 기록(1-b·1-c)과 확정된 결정(5-a D1~D3) |
| `2026-08-20-mcp-redesign-STATUS.md` 5장 | 일곱 불변식. **전부 실제로 데이터를 잃은 뒤에 만들어졌다** |
| `2026-08-21-release-3.0.0-PLAN.md` | 이 작업이 3.0.0 범위임을 기록 |

## 3. 완료된 것

**실측 (브리프 1-b·1-c).** `claude 2.1.241`을 임시 HOME에서 19개 항목 측정.
실제 환경은 SHA-256으로 미변경 확인. 측정 하네스는 세션 scratchpad에 있었으므로 사라졌다 —
재현이 필요하면 브리프 1-b의 픽스처 설명대로 다시 만든다.

**설계.** spec 3차 개정까지 완료. 리뷰 6건(2관점 × 3라운드)을 받았고
Critical 10 → 4 → 5를 전부 반영했다. 3차 리뷰 두 건이 **"4차 설계 라운드는 불필요, 다음은 plan"**
으로 판정했다.

**plan.** 서브시스템 셋 중 첫 번째(공용 코어 추출)만 작성했다. 나머지 둘은 6장 참조.

## 4. 커밋

```
c2a0cd7  docs(plugins): 코어 추출 구현 plan
98b9806  docs(plugins): 3차 리뷰 — 국소 수정 잔재 다섯을 닫는다
b32dd9a  docs(plugins): 2차 리뷰 Critical 4건 — held의 경계를 정의한다
96151cf  docs(plugins): 리뷰 Critical 10건을 반영해 설계를 개정한다
278d8de  docs(plugins): 설계를 확정한다
9ee0b25  docs(plugins): -y는 세션 안에서 무시되고, auto 표식은 명시 설치로 지워진다
2111113  docs(plugins): 실측이 브리프의 전제 셋을 반증했다
```

## 5. 설계에서 반드시 알아야 할 것

**(1) "동기화하지 않는 키"를 로컬에서 지우면 안 된다.**
초판이 `normalize`에 키 제거를 넣었고, `normalize`는 로컬·레포·base 셋에 다 적용되므로
상태 기계가 그것을 **삭제**로 읽었다. 데이터 손실 경로 넷이 여기서 나왔다.
→ `held`(판정 보류)로 분리했다.

**(2) `held`는 두 축이다.** 값 보류(push 금지)와 행동 보류(CLI 명령 금지)는 다른 연산이다.
하나로 묶었더니 (1)과 **같은 형태의 실수**가 반복됐다. H1·H2·H4는 둘 다, **H3는 값만**
— H3는 설치해야 하기 때문이다.

**(3) 값 보류 키는 base에서 제거한다.** "이전 base 유지"로 두면 보류가 풀리는 순간
얼어붙은 base로 케이스 3(삭제)이 난다. `in_s`가 거짓이면 삭제 경로가 성립하지 않는다.

**(4) 측정된 조건과 적용할 조건을 구별하라.** "배열은 install을 통과해도 보존된다"는
**이미 그 값을 가진 키**에 대한 측정이었다. 새 기기엔 키가 없으므로 `install`이 `true`를 쓴다.
이 혼동으로 spec이 두 번 걸렸다.

**(5) 국소 수정은 잔재를 남긴다.** 3차 리뷰 Critical 5건이 **전부** 2차 개정의 패치 잔재였다
(고친 자리 옆의 안 고친 자리). 문서를 부분 수정할 때마다 용어·표·상호참조를 `grep`으로 전수하라.

**(6) 릴리즈 브랜치에 잠재 결함이 하나 있다.** `collect_mcp.py:38-40`이 스테이징을 레포보다
먼저 써서, 레포 쓰기가 실패해도 `SKILL.md:398`의 게이트가 통과해 base가 전진한다.
그 결과가 "다른 기기가 지웠습니다"라는 거짓 문구다. **plan Task 1이 이것을 고친다.**

## 6. 다음에 할 일

### 즉시 — plan 실행

```bash
cd /Users/bran/personal/claude-sync
git checkout feat/plugins-sync
uv run --with pytest pytest plugins/claude-sync/tests -q   # 383 passed 확인
```

그다음 `plans/2026-08-24-keyed-sync-core.md`의 **Task 1부터** 순서대로.
실행 방식은 **subagent-driven**(task마다 새 subagent + task 사이 review)으로 정했다.

**Task 8이 이 plan의 핵심이다** — `mcp_config`를 어댑터로 바꾼 뒤
`test_mcp_config.py`·`test_mcp_scripts.py`·`test_mcp_cycle.py`가 **한 줄도 수정 없이**
통과해야 한다. 이것이 세 차례 리뷰가 "주장만 하고 검증되지 않았다"고 지목한 유일한 전제이고,
실패하면 코어 시그니처가 바뀌어 아래 두 plan을 쓸 수 없다.

### 그다음 — 남은 plan 둘

| plan | 범위 | spec 근거 |
|---|---|---|
| 플러그인 동기화 본체 | `plugin_config.py`, `collect_plugins.py`, `compare_plugins.py`, `plan_plugins.py`, 세 SKILL.md, 문서 정정 열 곳 | 3·6·7·8·9·10·13장 |
| 다운그레이드·호환 확장 | `compat.py` shape, `detect_downgrade.py`, `generate_metadata.py` schema 맵, 2.x 경고 네 곳 | 11장 |

**첫 plan이 끝나야 나머지를 쓸 수 있다.** Task 8의 결과가 코어 시그니처를 확정한다.

### 배포 전 확인

- **이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이다.** `/sync-backup`을 실행하지 말 것 —
  레포가 파괴된다.
- 배포 순서 규칙은 `2026-08-21-release-3.0.0-PLAN.md` 4장.

## 7. 작업 방식에 대한 합의

- **plan은 자산이 아니라 spec의 컴파일 산출물이다.** 패치하지 말고 다시 만든다.
- **전제가 깨지면 plan이 아니라 spec부터 고친다.** plan을 먼저 손보면 spec이 조용히 거짓이 되고,
  이 레포는 이미 그 대가를 치렀다(`git-like-sync-design.md` 4.4절의 부작용이 두 달간
  어느 문서에도 없었다).
- **plan의 각 task에 근거 절을 표기한다.** spec 한 절이 바뀌었을 때 폭발 반경을
  기계적으로 식별하기 위해서다.
