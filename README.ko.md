# claude-sync

Claude Code 설정을 Git 레포를 통해 기기 간 동기화하는 플러그인.

## 설치

```bash
claude plugin marketplace add claude-sync --source github --repo june20516/claude-sync
claude plugin install claude-sync@claude-sync
```

## 스킬

| 명령어 | 설명 |
|--------|------|
| `/sync-backup` | 로컬 설정을 Git 레포에 백업 & push |
| `/sync-restore` | Git 레포에서 설정을 복원 (충돌 시 안전 중단) |
| `/sync-status` | 로컬과 레포 간 차이를 확인 (dry-run) |

## 동기화 대상

- `~/.claude/agents/` — 커스텀 에이전트
- `~/.claude/skills/` — 범용 스킬
- `~/.claude/CLAUDE.md` — 글로벌 규칙
- `~/.claude/settings.json` -> `plugins.json` — 플러그인/마켓플레이스 목록 (민감 정보 제외)
- `~/.claude.json` (user 스코프) -> `mcp-servers.json` — MCP 서버 설정 (비밀 값은 마스킹)

MCP 서버는 `~/.claude.json`의 top-level `mcpServers`(user 스코프)만 동기화합니다. 계정 레벨 커넥터(`claude.ai *`), 플러그인이 제공하는 서버(`plugin:*`), project·local 스코프 서버(`.mcp.json`, `projects[*].mcpServers`)는 그 객체에 없으므로 자동으로 제외됩니다. `headers`와 `env`의 **값만** `<REDACTED>`로 마스킹하고 키 이름은 남기므로, 복원할 때 어떤 자격 증명이 필요한지는 전달되고 값은 유출되지 않습니다. 다만 `args`나 URL 쿼리스트링에 담긴 키는 마스킹되지 않습니다.

## 사용 흐름

### 기존 기기에서 백업

```
/sync-backup
```

최초 실행 시 백업용 Git 레포 URL을 물어봅니다. 이후엔 자동으로 사용합니다.

### 새 기기에서 복원

**방법 1: 플러그인 설치 후 복원**

```bash
claude plugin marketplace add claude-sync --source github --repo june20516/claude-sync
claude plugin install claude-sync@claude-sync
```

Claude Code에서:

```
/sync-restore
```

다른 기기에서 서버를 지웠거나 바꿨다면 `/sync-restore`가 서버마다 물어봅니다(제거/유지/나중에, 레포 값 채택/로컬 유지/나중에).

**방법 2: bootstrap.sh (Claude Code 없이도 가능)**

```bash
git clone <백업-레포-url> /tmp/claude-sync-repo
bash /tmp/claude-sync-repo/bootstrap.sh
```

### 변경 전 확인

```
/sync-status
```

## 동작 모델 (v3.0.0+)

claude-sync는 **내용 해시(content-hash) 기반 git 3-way 방식**으로 동기화합니다. 수정 시각(mtime)은 일절 사용하지 않습니다.

- **복원(restore)은 pull 전용입니다.** `/sync-restore`는 절대로 로컬 변경사항을 레포에 자동 push하지 않습니다.
- **새 파일은 항상 추가됩니다.** 레포에만 있는 파일(새 에이전트, 스킬, 플러그인, MCP 서버)은 다른 파일에 충돌이 있어도 로컬에 항상 반영됩니다.
- **충돌은 양쪽 모두 변경된 파일에서만 발생합니다.** `git merge-file` 3-way 병합을 시도하여, 변경 범위가 겹치지 않으면 자동 병합(`auto_merge`)됩니다. 같은 줄이 양쪽에서 달라졌을 때만 `conflict`로 분류되며 로컬 파일은 그대로 보존됩니다. 이때 로컬 유지 / 백업 채택 / 수동 병합 / 나중에 처리 중 선택할 수 있습니다.
- **`pull_only` 기기는 백업하지 않습니다.** 읽기 전용으로 지정된 기기는 레포에 자신의 상태를 push하지 않습니다.
- **MCP 서버는 서버 이름 키 단위로 병합됩니다.** `mcp-servers.json`은 파일 통째로 덮어쓰지 않으므로, 한 기기의 백업이 다른 기기에만 있는 서버를 지우지 않습니다. 삭제는 전파되지만 로컬 제거는 `/sync-restore`가 서버마다 물어본 뒤에만 이루어집니다.
- **`plugins.json`은 여전히 매 백업마다 통째로 덮어쓰입니다.** 파일별 reconcile 대상이 아니라서 마지막에 백업한 기기의 플러그인 목록이 남습니다. 알려진 한계입니다.

## 안전 장치

- **충돌 감지**: 마지막 공유 base 이후 양쪽에서 변경된 파일만 충돌로 표시하며, 로컬 파일은 절대 자동으로 덮어쓰지 않습니다. **예외: `plugins.json`은 백업할 때마다 새로 생성되어 레포의 내용을 덮어씁니다.**
- **민감 정보 보호**: `settings.json` 원본은 레포에 올리지 않고 플러그인 목록만 추출하며, MCP 서버 설정은 `headers`/`env` 값을 `<REDACTED>`로 마스킹해 올립니다
- **메타데이터**: 백업마다 내용 해시 기반 base 스냅샷을 기록하여 정확한 3-way 충돌 판단에 활용

## 보안

CLAUDE.md나 에이전트 파일에 사내 URL, 내부 규칙 등 민감 정보가 포함될 수 있습니다. **백업 레포는 private으로 만드는 것을 권장합니다.**

특정 파일을 백업에서 제외하려면 `~/.claude/.syncignore`를 만드세요 (gitignore 형식):

```
# 사내 전용 에이전트 제외
agents/internal-*.md

# 특정 스킬 제외
skills/secret-tool/
```

다른 사람에게 설정을 공유할 때는 `.syncignore`로 민감 파일을 제외한 뒤 백업하면 됩니다.
