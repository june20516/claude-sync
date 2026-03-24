---
name: sync-restore
description: Git 레포에서 Claude 설정 파일들(agents, skills, CLAUDE.md, 플러그인 목록)을 복원한다. 사용자가 /sync-restore 를 실행했을 때만 동작한다. 자동 호출하지 않는다.
disable-model-invocation: true
---

# sync-restore

Git 레포에서 Claude 설정 파일들을 복원하는 스킬이다.

## 안전 원칙

로컬 `~/.claude/` 디렉토리는 git으로 관리되지 않으므로, 잘못 덮어쓰면 되돌릴 방법이 없다. 따라서 이 스킬은 **충돌이 하나라도 있으면 전체 복원을 중단**한다. 부분 적용이나 파일별 선택은 하지 않는다.

## 설정 파일

동기화 설정은 `~/.claude/sync-config.json`에 저장된다:

```json
{
  "repo_url": "git@github.com:user/claude-sync.git"
}
```

최초 실행 시 이 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다.

## 실행 절차

### 1. 설정 확인

```bash
cat ~/.claude/sync-config.json
```

파일이 없으면 사용자에게 Git 레포 URL을 물어본다. URL을 받으면 `~/.claude/sync-config.json`에 저장한다.

### 2. 레포에서 최신 상태 가져오기

```bash
if [ -d ${TMPDIR:-/tmp}/claude-sync-repo/.git ]; then
  cd ${TMPDIR:-/tmp}/claude-sync-repo && git pull --rebase
else
  rm -rf ${TMPDIR:-/tmp}/claude-sync-repo
  git clone <repo_url> ${TMPDIR:-/tmp}/claude-sync-repo
fi
```

### 3. 충돌 분석 (sync-metadata.json 활용)

레포의 `sync-metadata.json`을 읽어 각 파일에 대해 충돌 가능성을 판단한다:

```bash
python3 ~/.claude/skills/sync-restore/scripts/analyze_conflicts.py ${TMPDIR:-/tmp}/claude-sync-repo
```

상태 분류:
- **safe**: 로컬 파일이 백업 이후 변경되지 않음 → 덮어쓰기 안전
- **conflict**: 로컬 파일이 백업 이후 수정됨 → 복원 불가
- **repo_only**: 레포에만 있는 파일 → 새로 추가 (안전)
- **local_only**: 로컬에만 있는 파일 → 건드리지 않음

### 4. 충돌 시: 중단

충돌 파일이 **하나라도** 있으면:

1. 충돌 파일 목록과 각각의 diff를 보여준다:
   ```bash
   diff ${TMPDIR:-/tmp}/claude-sync-repo/<path> ~/.claude/<path>
   ```

2. 복원을 **전체 중단**한다. 어떤 파일도 덮어쓰지 않는다.

3. 사용자에게 다음 해결 방법을 안내한다:
   - **로컬 우선**: `/sync-backup`을 먼저 실행하여 현재 로컬 상태를 레포에 저장한 뒤, 다시 `/sync-restore` 실행
   - **레포 우선**: 로컬에서 충돌 파일을 수동으로 백업(복사)해둔 뒤, 다시 `/sync-restore` 실행 — 이때 로컬 파일의 mtime이 갱신되지 않았으므로 충돌이 해소됨
   - **상태 확인**: `/sync-status`로 현재 차이를 먼저 확인

### 5. 충돌 없을 때: 변경 요약 및 확인

충돌이 없으면 변경 요약을 보여준다:
- 덮어쓸 파일 목록 (safe)
- 새로 추가될 파일 목록 (repo_only)
- 새로 설치될 플러그인 목록

사용자에게 진행 여부를 확인받는다.

### 6. 파일 복원

사용자가 확인하면 파일들을 복사한다:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"

# agents 복원 (레포에 있는 경우만) — 기존 디렉토리를 먼저 정리하여 삭제된 파일이 잔존하지 않게 한다
if [ -d "$SYNC_REPO/agents" ]; then
  rm -rf ~/.claude/agents
  cp -r "$SYNC_REPO/agents/" ~/.claude/agents/
fi

# skills 복원 (레포에 있는 경우만)
if [ -d "$SYNC_REPO/skills" ]; then
  rm -rf ~/.claude/skills
  cp -r "$SYNC_REPO/skills/" ~/.claude/skills/
fi

# CLAUDE.md 복원
[ -f "$SYNC_REPO/CLAUDE.md" ] && cp "$SYNC_REPO/CLAUDE.md" ~/.claude/CLAUDE.md
```

레포에 없는 디렉토리는 건너뛴다.

### 7. 플러그인 복원

`plugins.json`을 읽고 현재 설치된 플러그인과 비교한다.

#### 7-1. 마켓플레이스 추가

plugins.json의 `extraKnownMarketplaces`에 있지만 로컬 settings.json에 없는 마켓플레이스를 추가한다:

```bash
claude plugin marketplace add <marketplace-name> --source github --repo <owner/repo>
```

#### 7-2. 플러그인 설치

plugins.json의 `enabledPlugins`에 있지만 로컬에 설치되지 않은 플러그인을 설치한다:

```bash
claude plugin install <plugin-name>
```

플러그인 이름 형식은 `name@marketplace`이다 (예: `superpowers@claude-plugins-official`).

주의: `claude plugin` 명령어가 존재하지 않거나 실패하면, plugins.json 내용을 보여주고 수동 설치를 안내한다.

### 8. MCP 서버 복원

`mcp-servers.json`이 있으면 현재 등록된 MCP 서버와 비교하여 누락된 서버를 추가한다.

```bash
# 현재 등록된 서버 목록
claude mcp list 2>/dev/null
```

mcp-servers.json에 있지만 현재 등록되지 않은 서버를 추가한다:

```bash
claude mcp add <name> <url>
```

인증이 필요한 서버(예: Google Calendar)는 등록 후 별도 인증이 필요할 수 있다. 등록만 하고 인증은 사용자에게 안내한다.

주의: `claude mcp` 명령어가 실패하면, mcp-servers.json 내용을 보여주고 수동 등록을 안내한다.

### 9. 결과 보고

복원 완료 후 다음을 요약해서 보여준다:

- 복원된 파일 목록
- 새로 설치된 플러그인 목록
- 새로 등록된 MCP 서버 목록
- 인증이 필요한 MCP 서버 (있으면)
- 설치 실패한 항목 (있으면)
- 건너뛴 항목 (있으면)
