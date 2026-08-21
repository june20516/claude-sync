# 버전 호환성 — 후속 작업 브리프

- 작성: 2026-08-21
- 상태: **착수 전.** 조사·결정이 선행되어야 한다.
- **작업 브랜치: `release/3.0.0`에서 분기하고, PR도 `release/3.0.0`을 target으로 연다.**
- 선행: `fix/mcp-config-source` (PR #2, `release/3.0.0`에 머지됨). 그 안에서
  **"모르면 안 쓴다" 가드는 이미 구현**되었다.
- 관련: `2026-08-20-plugins-sync-followup-BRIEF.md` (같은 결함의 다른 사례)

> **이 작업은 3.0.0 릴리즈에 함께 실린다.** `main`에는 아직 아무것도 머지되지 않았고,
> MCP 재설계와 이 작업이 모두 `release/3.0.0`에 모인 뒤에 한꺼번에 배포한다.
> 자세한 절차는 `2026-08-21-release-3.0.0-PLAN.md`를 볼 것.

---

## 1. 배경 — 실측으로 확인된 것

### 1.1 v2.0.0 기기가 v3 백업을 만나면

| 경로 | 결과 | 성질 |
|---|---|---|
| `/sync-status` | `TypeError: string indices must be integers` | 시끄럽게 죽음. 데이터는 안전 |
| `/sync-backup` | **v2 파일을 v1 배열로 덮어쓰고, 공백 든 `command`를 가진 서버를 누락** | 조용한 파괴 |
| `/sync-restore` | 산문 기반이라 LLM이 임의 대응 | 비결정적, additive라 손실은 없음 |

옛 `parse_mcp.py`가 **레포 파일을 읽지 않고** `claude mcp list` 출력만으로 통째 재생성하는 것이 원인이다. 스키마 호환성 문제가 아니라 **쓰기 방식**의 문제다.

### 1.2 소급 적용은 불가능하다

"낮은 버전을 먼저 올려 완화"(expand/contract — 관용적 리더를 스키마 변경보다 한 릴리스 먼저 배포)는 정석이지만 **이번엔 쓸 수 없다.** 그 준비를 이미 배포된 2.0.0에 넣을 수 없기 때문이다. 안내·차단·복구 제안은 전부 *낮은 버전 기기에서* 실행되어야 하는데 그 코드를 우리가 못 바꾼다.

지금도 통하는 유일한 변형은 **"파일을 바꾸지 말고 새로 추가"**(`mcp-servers-v2.json`을 따로 만들기)인데, 레포에 파일이 영구히 하나 더 남고 옛 기기의 MCP 백업은 계속 망가진 채다. 개인 기기 두세 대 규모에선 "전부 올리고 그 전엔 backup 금지"가 더 싸다고 판단해 채택하지 않았다.

### 1.3 이번 PR에서 이미 한 것

- **가드**: `load_backup`이 알아볼 수 없는 문서를 만나면 `UnknownBackupSchema`. 세 스크립트가 `skipped`로 처리하고 **레포 파일을 건드리지 않는다.** → 3.0.0 이후 버전에서는 1.1의 파괴가 구조적으로 불가능하다.
- **문서**: README 2종 + 백업 레포 README 2종에 "v2.x 기기로 백업 금지" 명시.

**남은 것은 "표식"과 "능동적 판정"이다.** 지금은 3.0.0이 *모른다는 사실*만 알 수 있고, *상대가 몇 버전인지*는 모른다.

---

## 2. 먼저 조사할 것

### 2.1 `autoUpdate`의 의미 — **확인 완료 (2026-08-21)**

`~/.claude/settings.json`의 `extraKnownMarketplaces.<name>.autoUpdate: true`가 무엇을 하는지가
나머지 작업의 가치를 좌우한다. 브리프는 두 갈래를 상정했다 — 플러그인까지 갱신하는가,
마켓플레이스 메타데이터만 갱신하는가.

**결론: 플러그인까지 갱신한다. 그러나 그것이 차단 로직의 가치를 낮추지는 않는다.**

측정은 두 갈래로 했다. (A) 이 기기의 실제 상태 관찰 — 어떤 파일도 변경하지 않았다.
(B) `claude` 2.1.238 번들 정적 분석. 임시 HOME(`HOME=$T`)으로 격리가 성립함을 먼저 확인했고
(`claude plugin marketplace list`가 `$T` 안에만 파일을 만들었다), 실제
`~/.claude/settings.json`·`~/.claude.json`은 읽기만 했다.

#### 증거 1 — 사용자 조작 없이 플러그인 버전이 올라갔다 (관찰)

2026-08-21T02:29:26~32Z, 이 기기에서 아무 명령도 실행하지 않은 채:

| 대상 | 시각(UTC) | 결과 |
|---|---|---|
| 마켓플레이스 `claude-plugins-official` | 02:29:26.456 | 갱신 |
| 마켓플레이스 `claude-sync` | 02:29:30.264 | 갱신 |
| 마켓플레이스 `suberpower` | 02:29:30.494 | 갱신 |
| 플러그인 `frontend-design` / `skill-creator` | 02:29:30.54x | 갱신 |
| 플러그인 **`figma` 2.2.95 → 2.2.96** | 02:29:32.464 | **버전 상승** |

`autoUpdate`가 없는 `planning-with-files`는 마켓플레이스도 플러그인도
2026-03-18 이후 다섯 달째 그대로다. **게이트는 `autoUpdate`다.**

#### 증거 2 — 문언 (번들)

`known_marketplaces.json` 스키마의 필드 설명, 그리고 `/plugin` UI 문구:

> `autoUpdate`: "Whether to automatically update this marketplace **and its installed plugins** on startup"
>
> "Auto-update enabled. Claude Code will automatically update this marketplace **and its installed plugins**."

#### 증거 3 — 코드 경로 (번들)

`startBackgroundHousekeeping`이 세션 시작 시 오토업데이트 pass를 띄운다. 순서는:

1. 자동 업데이터가 꺼져 있으면 **전체 skip** (`DISABLE_UPDATES`·`DISABLE_AUTOUPDATER` 등)
2. 효력 있는 `autoUpdate`가 켜진 마켓플레이스 **집합**을 만든다
3. **0~600,000ms(0~10분) 균등 랜덤 지연**
4. 그 집합의 마켓플레이스를 각각 refresh
5. **같은 집합**의 설치된 플러그인을 update — 로그 `Plugin autoupdate: updated {plugin} from {old} to {new}`

4와 5는 같은 pass의 연속된 두 단계이고 같은 집합을 쓴다. 공식/비공식으로 갈리는 분기는 없다.
즉 **"메타데이터만 갱신" 갈래는 존재하지 않는다.**

---

### 2.1.1 그런데도 불일치 창은 닫히지 않는다

네 가지 이유가 있고, 전부 측정으로 확인됐다.

**(1) 서드파티 마켓플레이스의 기본값은 꺼짐이다. — 가장 중요하다**

효력 있는 값은 `settings.json`의 명시값 > `known_marketplaces.json`의 명시값 > 기본값 순이다.
기본값이 켜짐인 것은 Anthropic 예약 이름 집합뿐이다 —
`claude-plugins-official`, `claude-code-plugins`, `anthropic-marketplace`, `agent-skills` 등.
**`june20516/claude-sync`는 여기 없다.** 이 기기에 `autoUpdate: true`가 있는 것은 사용자가
`/plugin` UI에서 직접 켰기 때문이다.

그리고 **`settings.json`은 claude-sync의 동기화 대상이 아니다**(동기화 대상은 agents·skills·
CLAUDE.md·plugins.json·mcp-servers.json). 즉 이 설정은 다른 기기로 전파되지 않는다.
새 기기, 또는 켜 두지 않은 기기는 **사용자가 `plugin update`를 칠 때까지 영구히 옛 버전이다.**

**(2) 갱신은 세션 시작 시에만, 그것도 0~10분 지연 뒤에 일어난다.**
세션을 열자마자 `/sync-backup`을 실행하면 지연 구간에 걸려 옛 코드가 돈다.

**(3) 갱신되어도 그 세션은 옛 코드를 계속 쓴다.**
설치 경로가 버전별로 갈리고 옛 디렉토리가 지워지지 않는다 — 실측으로
`figma/2.2.90`, `2.2.91`, `2.2.95`, `2.2.96`이 모두 남아 있다. 실행 중인 세션의
`CLAUDE_PLUGIN_ROOT`는 옛 버전 디렉토리에 고정된 채다.
알림은 `Plugins updated: figma · Run /reload-plugins to apply` 한 줄이며
**priority가 low이고 10초 뒤 사라진다.** 놓치기 쉽다.

**(4) 기기를 켜지 않으면 갱신도 없다.** 온라인이어야 하고 Claude Code를 실행해야 한다.

### 2.1.2 설계에 주는 함의

- **(b) 가드의 가치는 낮아지지 않는다. (1) 때문에 오히려 높다.**
  다른 기기의 `autoUpdate` 상태를 우리는 알 수도 없고 켤 수도 없다. "자동으로 따라잡을 것"을
  전제한 설계는 세울 수 없다.
- **(c) 다운그레이드 사고의 빈도는 낮아진다.** `autoUpdate`를 켠 기기라면 며칠 안에 따라잡는다.
  하지만 (1)에 해당하는 기기가 하나라도 있으면 사고는 계속 가능하다. **(c)를 버릴 근거는 아니고,
  (a)·(b) 뒤로 미룰 근거는 된다.**
- **안내 문구에 `/reload-plugins` 또는 재시작을 반드시 넣는다.** `claude plugin update`의
  "restart required to apply"와 같은 이유이며, 자동 갱신 경로에서도 똑같이 필요하다.
- **3.0.0 배포 자체에는 `autoUpdate`가 도움이 되지 않는다.** 2.0.0 기기가 3.0.0을 받기 전에
  `/sync-backup`을 실행하면 레포가 파괴되고, 그것을 막을 코드는 2.0.0 안에 없다.
  릴리즈 계획의 "모든 기기를 올린 뒤에 backup" 순서는 그대로 유효하다.

### 2.1.3 부수 실측

- **대상 설치분**: scope가 `user` 또는 `managed`면 항상 대상. `project` 스코프는 현재
  프로젝트일 때만. claude-sync는 user 스코프이므로 대상이다.
- **소스 필터**: 로컬 경로를 가리키는 git URL은 제외된다. 관리 정책(허용/차단 목록)이 설정돼 있으면 그것도 적용된다.
- **관리 설정 우선**: 효력 있는 `autoUpdate`를 managed-settings.json이나 `--settings`가 정하면
  `/plugin` UI에서 바꿀 수 없다.
- `claude plugin marketplace add`에 `autoUpdate` 플래그는 여전히 없다. 켜는 경로는
  `/plugin` UI의 토글, 또는 `settings.json`의 `extraKnownMarketplaces.<name>.autoUpdate`다.
  후자는 세션 시작 시 `known_marketplaces.json`으로 동기화된다.

### 2.2 semver가 Claude Code 동작에 주는 영향 — **확인 완료 (2026-08-21)**

`claude --version 2.1.237` 기준 CLI 전수 조사 결과:

| 명령 | 버전 관련 |
|---|---|
| `plugin install <plugin>` | `--version`도 범위 문법도 **없음**. 옵션은 `--config`/`--scope`/`--yes` |
| `plugin update <plugin>` | "to the **latest** version (restart required to apply)" |
| `marketplace add <source>` | `--scope`, `--sparse`뿐 |
| `marketplace update [name]` | 소스에서 메타데이터 갱신 |
| `plugin list` | 설치된 버전을 표시 (`Version: unknown`인 플러그인도 있다 — 선택 필드) |
| `plugin tag [path]` | `{name}--v{version}` git 태그 생성, `plugin.json` ↔ marketplace entry 일치 검증 |

**결론: semver 비교나 제약 해석이 어디에도 없다.** major/minor/patch에 따라 동작이 갈리지 않고 전부 "소스의 최신"이다. 즉 **이 프로젝트에서 버전 숫자는 사람에게 주는 신호이자 우리 코드가 스스로 판정하는 근거일 뿐, 툴이 강제하는 것이 아니다.**

부수 확인: `plugin tag`가 `{name}--v{version}` 태그 규약을 이미 갖고 있으므로, "호환 경계 커밋에 태그" 아이디어는 기성 도구로 구현할 수 있다.

---

## 3. 결정해야 할 것

조사가 끝나면 아래를 **spec에 문언으로 확정**한다. 추측으로 코딩하지 않는다.

1. **이 프로젝트의 semver 정책.** 무엇을 major로 볼 것인가. 툴이 강제하지 않으므로 순수히 우리 규약이다. 제안: *레포에 쓰는 문서의 스키마가 하위 호환되지 않게 바뀌면 major*. minor는 읽는 쪽 확장, patch는 버그 수정.
2. **차단 기준.** `min_reader_version` 단일 게이트인가, 파일별 스키마 버전인가, 둘 다인가. 파일별이 더 정확하지만(한 파일이 앞서도 나머지는 동기화 가능) 복잡하다.
3. **차단 대상.** backup만 막는가. restore·status는 읽기 전용이니 경고만 하는가.
4. **표식 없는 백업의 해석.** 3.0.0 이전 백업에는 표식이 없다. 규칙: *표식 없음 = 3.0.0 이하*. `mcp-servers.json`이 v1 배열이냐 v2 객체냐로 2.0.0과 3.0.0은 이미 구별된다.
5. **복구 UX.** 자동인가 확인 후인가. **자동은 위험하다** — 옛 기기가 *의도적으로* 지운 서버까지 되살린다.
6. **태그를 쓸 것인가.** 매 백업마다 태그를 옮기는 것은 과하다. 호환 경계 커밋에 한 번만 남기는 정도(`schema-v2-start`)가 적당하다.

---

## 4. 설계안

### (a) 레포 수준 표식

`sync-metadata.json`을 되살린다. 지금은 **어떤 스크립트도 읽지 않는 유물**이라 필드 추가가 안전하다.

```jsonc
{
  "files": { ... },
  "written_by_version": "3.0.0",
  "schema": { "mcp-servers.json": 2, "plugins.json": 1 },
  "min_reader_version": "3.0.0"
}
```

**시각·기기명은 넣지 않는다.** 2026-06-10 설계가 시간 의존을 제거했고, 매 백업마다 diff가 생겨 소음이 된다. 언제·누가는 git commit이 이미 기록한다.

자기 플러그인 버전은 `$SYNC_SCRIPTS/../../../.claude-plugin/plugin.json`에서 읽는다.

### (b) 읽을 때의 가드

`lib/compat.py` 신설. semver 비교는 표준 라이브러리에 없으므로 튜플 비교를 직접 구현한다(`"3.10.0" > "3.9.0"`이 문자열 비교로는 거짓이 되는 함정에 주의).

- `min_reader_version` > 내 버전 → **backup 차단**
- 파일별 `schema`가 내가 아는 것보다 높으면 **그 항목만** 건너뛴다(전체 실패 아님) — 이미 구현된 `UnknownBackupSchema` 경로와 합류시킨다

### (c) 다운그레이드 사고 탐지·복구

3.0.0+가 backup·status에서 이 조건을 만나면 확정적 신호다:

> 레포 `mcp-servers.json`이 **v1 배열**인데 내 base는 **v2였다** → 옛 버전 기기가 덮어썼다

git 히스토리에서 마지막 v2 커밋을 찾아 복구를 제안한다:

```bash
git log --format=%H -- mcp-servers.json | while read c; do
  git show "$c:mcp-servers.json" | python3 -c \
    'import json,sys; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,dict) and d.get("version")==2 else 1)' \
    && echo "$c" && break
done
```

---

## 5. 명령어 3종에 반영되어야 할 것

이 작업은 스크립트만 고쳐서 끝나지 않는다. **세 SKILL.md가 각각 다른 책임을 진다.**

### `/sync-backup` — 유일하게 **차단**하는 명령

| 단계 | 추가/변경 |
|---|---|
| 2. 레포 준비 (clone/pull) **직후** | **호환성 검사를 여기 넣는다.** `sync-metadata.json`을 읽어 `min_reader_version`과 내 버전을 비교. 앞서면 **파일 복사·MCP 수집 전에 중단**하고 `claude plugin update claude-sync`를 안내한다. 늦게 검사하면 이미 레포를 건드린 뒤가 된다 |
| 6. MCP 수집 | `status: skipped` + `reason`이 스키마 문제일 때의 안내 — **이미 반영됨** |
| 6.5 (신설) | 다운그레이드 탐지: 레포는 v1인데 base는 v2 → 경고 + 복구 제안. 백업을 계속할지 물어본다 |
| 7. `sync-metadata.json` 생성 | `written_by_version`·`schema`·`min_reader_version` 기록 (a) |
| 10. 커밋 & 푸시 | 변경 없음. 단 (c)에서 사용자가 복구를 택했다면 그 결과가 커밋에 포함된다 |
| 12. 결과 보고 | "이 백업은 v3.0.0으로 기록되었습니다. 다른 기기가 이보다 낮으면 backup이 차단됩니다"를 처음 한 번 알린다 |

**주의: 차단은 backup에만 건다.** pull_only 가드가 이미 1단계에서 같은 형태로 중단하므로 그 패턴을 따른다.

### `/sync-status` — **경고만**, 아무것도 막지 않는다

| 단계 | 추가/변경 |
|---|---|
| 1. 레포 준비 직후 | `min_reader_version` 확인. 앞서면 **맨 위에 크게 경고**하되 분석은 계속한다. 읽기 전용이라 위험이 없고, 사용자가 "무엇이 문제인지" 보러 오는 명령이기 때문이다 |
| 2. MCP 비교 | `skipped` + 스키마 사유 안내 — **이미 반영됨** |
| 3. 결과 요약 | 버전 불일치를 **첫 줄에** 넣는다. "이 기기 3.0.0 / 백업 3.1.0 — `/sync-backup`이 차단됩니다" (다음 major 이후의 예) |

status가 차단하면 안 되는 이유: 버전이 안 맞을 때 사용자가 가장 먼저 실행할 명령이 status다. 그것마저 막으면 진단 수단이 사라진다.

### `/sync-restore` — **경고 후 진행 여부를 묻는다**

| 단계 | 추가/변경 |
|---|---|
| 2. 레포에서 가져오기 직후 | `min_reader_version` 확인. 앞서면 경고하고 **계속할지 묻는다.** restore는 pull-only라 레포를 훼손하지 않지만, 모르는 스키마의 항목을 건너뛴 부분 복원이 된다는 점을 명시한다 |
| 3. 파일 reconcile | 변경 없음. 파일 동기화는 스키마와 무관하다 |
| 5. 플러그인 복원 | **여기가 탈출구다.** 버전이 낮아 막혔다면 사용자가 필요한 것은 `claude plugin update claude-sync`다. 복원 절차 안에서 이 안내를 우선 노출한다 |
| 6. MCP 복원 | `skipped` + 스키마 사유 안내 — **이미 반영됨** |
| 6-6. base 갱신 | **스키마를 알아보지 못했으면 base를 전진시키지 않는다.** 이미 `apply_base`가 `UnknownBackupSchema`로 막지만, SKILL.md에도 이유를 적어 둔다 |
| 7. 결과 보고 | 버전 때문에 건너뛴 항목을 **"실패"가 아니라 "보류"로** 보고한다 |

### 세 명령 공통

- 호환성 검사는 **레포를 가져온 직후, 아무것도 쓰기 전에** 한다. 세 스킬 모두 같은 위치다.
- 판정은 `lib/compat.py` **하나**를 통한다. 세 SKILL.md가 각자 버전을 비교하면 이 프로젝트가 없애려는 파서 드리프트가 그대로 재현된다.
- 안내 문구의 명령은 항상 두 줄이다: `claude plugin marketplace update claude-sync` → `claude plugin update claude-sync`. 마켓플레이스 갱신 없이 `plugin update`만 하면 새 버전을 못 본다.
- **재시작 필요**를 반드시 알린다 — `plugin update`가 "restart required to apply"라고 명시한다.

---

## 6. 작업 사이즈

| | 코드 | 테스트 | SKILL.md | 난이도 |
|---|---|---|---|---|
| (a) 표식 쓰기 | ~30줄 (`generate_metadata.py`) | 5 | 1곳 | 낮음 |
| (b) 가드 | ~80줄 (`lib/compat.py` 신설) | 15 | 3곳 | 중간 |
| (c) 탐지·복구 | ~100줄 + **실제 git 레포 픽스처 테스트** | 10 | 2곳 | 높음 |

합계 대략 **코드 210줄 / 테스트 30개 / SKILL.md 3곳**. MCP 재설계(13 task·159 테스트)의 1/3 규모다. **코딩보다 3장의 결정이 비싸다.**

권장 순서: **(a) → (b) → (c).** (a) 없이는 (b)가 판정할 근거가 없고, (c)는 (a)·(b)와 독립이지만 가장 비싸다. (a)+(b)만으로도 "다음 major에서 사용자가 영문 모를 파괴를 겪지 않는다"는 목표는 달성된다.

---

## 7. 유의사항

- **차단은 backup에만.** status를 막으면 진단 수단이 사라지고, restore를 막으면 업데이트 안내를 받을 경로가 사라진다.
- **`min_reader_version`을 올리는 것은 되돌릴 수 없다.** 한 번 올려 푸시하면 그 미만 기기는 전부 막힌다. 스키마가 실제로 깨질 때만 올린다.
- **semver 비교를 문자열로 하지 말 것.** `"3.10.0" > "3.9.0"`이 거짓이 된다.
- **복구를 자동으로 하지 말 것.** 옛 기기가 의도적으로 지운 서버를 되살릴 수 있다.
- **표식 파일 자체가 충돌 대상이 되지 않게 할 것.** `sync-metadata.json`은 매 백업마다 재생성되는 파생 산출물이며 reconcile 대상이 아니다. 시각을 넣으면 매번 diff가 생긴다.
- **`plugins.json`에도 같은 결함이 있다.** 그쪽 작업의 첫 task는 스키마 설계가 아니라 `extract_plugins.py`가 파괴하지 않게 만드는 것이다 — 자세한 것은 `2026-08-20-plugins-sync-followup-BRIEF.md`.

---

## 8. 이어받는 방법

```bash
cd /Users/bran/personal/claude-sync
git fetch origin
git checkout release/3.0.0 && git pull
git checkout -b feat/version-compat          # 여기서 작업한다
uv run --with pytest pytest plugins/claude-sync/tests -q   # 166 passed 확인
```

**버전은 올리지 않는다.** `plugin.json`·`marketplace.json`은 이미 `3.0.0`이고 이 작업도
같은 릴리즈에 실린다. 끝나면 `release/3.0.0`을 target으로 PR을 연다.

읽을 순서: 이 문서 → `2026-08-20-mcp-redesign-STATUS.md` 5장(불변식) → `lib/mcp_config.py`의 `UnknownBackupSchema`·`_recognized_servers`(이미 구현된 가드).

그다음 **2.1 `autoUpdate` 실측부터** 시작한다. 결과를 이 문서에 append하고 3장을 확정한 뒤 spec을 쓴다.
