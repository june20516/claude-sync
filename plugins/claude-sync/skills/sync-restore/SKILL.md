---
name: sync-restore
description: Git 레포에서 Claude 설정 파일들(agents, skills, CLAUDE.md, 플러그인 목록)을 복원한다. 사용자가 /sync-restore 를 실행했을 때만 동작한다. 자동 호출하지 않는다.
disable-model-invocation: true
---

# sync-restore

Git 레포에서 Claude 설정 파일들을 복원하는 스킬이다.

## 모델 (git-like, pull-only)

restore는 `git pull`처럼 동작한다. **리모트에 자동 push하지 않는다.** 비교는 내용 해시 3-way(로컬 `L` / 레포 `R` / base `S` = 이 기기가 마지막으로 reconcile한 remote 내용, `~/.claude/.sync-state/base/<rel>`)로 한다. 파일 수정 시각은 비교에 사용하지 않는다.

파일별 판정:
- **skip** (in_sync): L=R — 이미 동일
- **add** (repo_only): 레포에만 있는 새 파일 — 로컬에 추가. **충돌과 무관하게 항상 적용된다.**
- **overwrite** (fast_forward): 레포만 변경 — R로 덮어씀
- **keep** (local_ahead / local_only): 로컬만 변경 또는 로컬 전용 — 그대로 유지
- **merge** (conflict): 양쪽 모두 base 이후 변경 — 3-way 시도 후 자동 병합 또는 충돌 격리

## 설정 파일

동기화 설정은 `~/.claude/sync-config.json`에 저장된다:

```json
{
  "repo_url": "git@github.com:user/claude-settings.git"
}
```

최초 실행 시 이 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다.

## 실행 절차

### 0. 스크립트 경로 확인

이 스킬에서 사용하는 스크립트들의 경로를 먼저 찾는다. 이후 모든 단계에서 `$SYNC_SCRIPTS`로 참조한다.

```bash
SYNC_SCRIPTS=$(find ~/.claude -path "*/sync-restore/scripts" -type d 2>/dev/null | head -1)
echo "Scripts: $SYNC_SCRIPTS"
```

이 경로를 찾지 못하면 플러그인이 제대로 설치되지 않은 것이므로 사용자에게 안내한다.

### 1. 설정 확인

```bash
cat ~/.claude/sync-config.json
```

파일이 없으면 사용자에게 Git 레포 URL을 물어본다. URL을 받으면 `~/.claude/sync-config.json`에 저장한다.

### 2. 레포에서 최신 상태 가져오기

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -d "$SYNC_REPO/.git" ]; then
  cd "$SYNC_REPO" && git pull --rebase
else
  rm -rf "$SYNC_REPO"
  git clone <repo_url> "$SYNC_REPO"
fi
```

### 3. 파일별 reconcile (비대화 적용)

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/reconcile_restore.py" "$SYNC_REPO" --apply
```

스크립트가 자동 처리하는 것 (사용자 개입 없음):
- **skip** (in_sync), **add** (레포에만 있는 새 파일), **overwrite** (fast-forward: 레포가 앞섬), **keep** (local_ahead/local_only: 로컬 유지), **auto_merge** (양쪽 변경이나 안 겹쳐 깨끗이 병합).
- 위 모두 base를 적절히 갱신한다.
- **additive(add)는 충돌과 무관하게 항상 적용된다.** 충돌이 있어도 새 파일 추가는 막히지 않는다.

출력 JSON의 `conflicts` (겹친 충돌 또는 base 없음)만 4단계로 넘어간다. `local_ahead` 목록은 "올리려면 /sync-backup" 안내용이다.

### 4. 충돌 해소 (스킬이 대신 수행 — 사용자는 선택만)

`conflicts`가 비어 있으면 이 단계를 건너뛴다.

`conflicts`의 각 파일에 대해:
1. 간결한 diff를 보여준다:
   ```bash
   diff <(cat $SYNC_REPO/<rel>) ~/.claude/<rel>
   ```
   `has_base: true`이면 base와의 차이도 함께 보여준다.
2. 사용자에게 선택지를 제시: **로컬 유지 / 백업 채택 / 병합 / 나중에**
3. 선택대로 스킬이 직접 적용한다 (사용자가 파일을 만지지 않는다):

   - **백업 채택** (theirs): 레포 파일을 로컬에 복사한 뒤 base를 레포 내용으로 갱신.
     ```bash
     cp "$SYNC_REPO/<rel>" "$HOME/.claude/<rel>"
     python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" <rel>
     ```

   - **로컬 유지** (ours): 로컬 파일은 그대로 두고 base를 레포 내용으로 갱신 (remote를 봤고 거부 → 재충돌 방지). 로컬은 local_ahead가 된다.
     ```bash
     python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" <rel>
     ```

   - **병합** (겹침 / base 없음): 에이전트가 로컬·레포(가능하면 base) 내용을 읽어 병합안을 만들어 사용자에게 보여주고 확인받은 뒤 `"$HOME/.claude/<rel>"`에 쓴다. 그 후 base를 레포 내용으로 갱신. 로컬은 local_ahead가 된다.
     ```bash
     python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" <rel>
     ```

   - **나중에** (defer): 아무것도 하지 않는다. base 불변 → 다음 restore에서 다시 표시된다.

모든 해소 방식(나중에 제외)은 base ← 레포 내용으로 갱신한다. `--set-base-from` 호출이 이를 담당한다.

### 5. 플러그인 복원 (additive)

레포 `plugins.json`의 `enabledPlugins` 중 로컬 `settings.json`에 없는 것만 설치한다. 기존 플러그인은 제거하지 않는다.

#### 5-1. 마켓플레이스 추가

`extraKnownMarketplaces`에 있지만 로컬에 없는 마켓플레이스를 추가한다:
```bash
claude plugin marketplace add <owner/repo>
```

#### 5-2. 플러그인 설치

```bash
claude plugin install <plugin-name@marketplace>
```

`claude plugin` 명령어가 없거나 실패하면 `plugins.json` 내용을 보여주고 수동 설치를 안내한다.

### 6. MCP 서버 복원 (additive, plugin: 제외)

`mcp-servers.json` 중 현재 미등록이고 **이름이 `plugin:`으로 시작하지 않는** 서버만 추가한다. `plugin:` 서버는 플러그인 설치로 자동으로 따라오므로 `mcp add`하지 않는다.

```bash
# 현재 등록된 서버 목록 확인
claude mcp list 2>/dev/null

# 미등록 서버 추가
claude mcp add <name> <url> --transport <http|stdio> --scope user
```

인증이 필요한 서버는 등록 후 사용자에게 인증 안내를 한다.

`claude mcp` 명령어가 실패하면 `mcp-servers.json` 내용을 보여주고 수동 등록을 안내한다.

### 7. 결과 보고

복원 완료 후 다음을 요약해서 보여준다:

- **적용 건수**: add / overwrite / auto_merge / skip 각각의 파일 수
- **해소한 충돌**: 파일명과 선택 방식 (나중에는 미해소로 표시)
- **local_ahead 파일** → "올리려면 /sync-backup을 실행하세요" 안내 (restore는 push하지 않음)
- **설치한 플러그인** (있으면)
- **추가한 MCP 서버** (있으면)
- **인증이 필요한 MCP 서버** (있으면)
- **설치/등록 실패한 항목** (있으면)
