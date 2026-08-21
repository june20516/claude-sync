# 버전 호환성 — 후속 작업 브리프

- 작성: 2026-08-21
- 상태: **착수 전.** 조사·결정이 선행되어야 한다.
- 선행: `fix/mcp-config-source` (PR #2). 그 안에서 **"모르면 안 쓴다" 가드는 이미 구현**되었다.
- 관련: `2026-08-20-plugins-sync-followup-BRIEF.md` (같은 결함의 다른 사례)

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

### 2.1 `autoUpdate`의 의미 — 최우선

`~/.claude/settings.json`의 `extraKnownMarketplaces.<name>.autoUpdate: true`가 무엇을 하는지 확정해야 한다. **이 하나가 나머지 작업의 가치를 절반 이상 좌우한다.**

- 플러그인까지 자동 갱신 → 버전 불일치 창이 짧다 → 차단 로직의 가치가 낮다
- 마켓플레이스 메타데이터만 갱신 → 사용자가 명시적으로 `plugin update`를 할 때까지 불일치가 지속된다 → 차단·안내의 가치가 높다

측정 방법: 버전을 올려 푸시한 뒤, 다른 기기(또는 임시 HOME)에서 아무 조작 없이 캐시 디렉토리 버전이 바뀌는지 관찰한다. `claude plugin marketplace add --help`에 `autoUpdate` 플래그가 없으므로 기본값이거나 대화형 `/plugin` UI가 설정하는 것으로 보인다 — 어느 쪽인지도 함께 확인한다.

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
  "written_by_version": "3.1.0",
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
| 12. 결과 보고 | "이 백업은 v3.1.0으로 기록되었습니다. 다른 기기가 이보다 낮으면 backup이 차단됩니다"를 처음 한 번 알린다 |

**주의: 차단은 backup에만 건다.** pull_only 가드가 이미 1단계에서 같은 형태로 중단하므로 그 패턴을 따른다.

### `/sync-status` — **경고만**, 아무것도 막지 않는다

| 단계 | 추가/변경 |
|---|---|
| 1. 레포 준비 직후 | `min_reader_version` 확인. 앞서면 **맨 위에 크게 경고**하되 분석은 계속한다. 읽기 전용이라 위험이 없고, 사용자가 "무엇이 문제인지" 보러 오는 명령이기 때문이다 |
| 2. MCP 비교 | `skipped` + 스키마 사유 안내 — **이미 반영됨** |
| 3. 결과 요약 | 버전 불일치를 **첫 줄에** 넣는다. "이 기기 3.0.0 / 백업 3.1.0 — `/sync-backup`이 차단됩니다" |

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
git checkout fix/mcp-config-source          # 또는 머지 후 main
uv run --with pytest pytest plugins/claude-sync/tests -q   # 166 passed 확인
```

읽을 순서: 이 문서 → `2026-08-20-mcp-redesign-STATUS.md` 5장(불변식) → `lib/mcp_config.py`의 `UnknownBackupSchema`·`_recognized_servers`(이미 구현된 가드).

그다음 **2.1 `autoUpdate` 실측부터** 시작한다. 결과를 이 문서에 append하고 3장을 확정한 뒤 spec을 쓴다.
