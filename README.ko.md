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
| `/sync-restore` | Git 레포에서 설정을 복원 (충돌한 파일은 그대로 보존하고 대화로 해소) |
| `/sync-status` | 로컬과 레포 간 차이를 확인 (dry-run) |

## 동기화 대상

- `~/.claude/agents/` — 커스텀 에이전트
- `~/.claude/skills/` — 범용 스킬
- `~/.claude/CLAUDE.md` — 글로벌 규칙
- `~/.claude/settings.json` -> `plugins.json` — 플러그인 목록, 마켓플레이스, 플러그인 설정 **키 이름** (설정 값은 마스킹)
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

다른 기기에서 항목을 지웠거나 바꿨다면 `/sync-restore`가 항목마다 물어봅니다(제거/유지/나중에, 레포 값 채택/로컬 유지/나중에). 같은 세 선택지가 MCP 서버·플러그인·마켓플레이스·플러그인 설정 키에 모두 적용됩니다.

**방법 2: bootstrap.sh (Claude Code 없이도 가능)**

```bash
git clone <백업-레포-url> /tmp/claude-sync-repo
bash /tmp/claude-sync-repo/bootstrap.sh
```

### 변경 전 확인

```
/sync-status
```

## v3.0.0으로 올릴 때 (먼저 읽으세요)

v3.0.0은 `mcp-servers.json`의 스키마를 바꾸며 **역호환되지 않습니다.**

> **아직 v2.x인 기기가 하나라도 남아 있다면, 그 기기에서 `/sync-backup`을 실행하지 마세요.** v2의 백업 단계는 레포 파일을 읽지 않고 `mcp-servers.json`을 통째로 다시 만들기 때문에, 한 번만 실행해도 v3 파일이 옛 배열 형식으로 되돌아가고 **명령에 공백이 든 서버는 아예 사라집니다.** v2의 `/sync-status`도 `TypeError`로 중단됩니다.

모든 기기를 먼저 올린 뒤에 백업하세요:

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync    # 적용하려면 재시작이 필요합니다
```

v3.0.0부터는 알아볼 수 없는 백업을 만난 기기가 그 단계를 건너뛰고(MCP 단계와 플러그인 단계가 같은 규율을 따릅니다) 레포 파일을 그대로 둔 채 플러그인 업데이트를 안내하므로, 이후 업그레이드에서는 같은 사고가 반복되지 않습니다.

## 동작 모델 (v3.0.0+)

claude-sync는 **내용 해시(content-hash) 기반 git 3-way 방식**으로 동기화합니다. 수정 시각(mtime)은 일절 사용하지 않습니다.

- **복원(restore)은 pull 전용입니다.** `/sync-restore`는 절대로 로컬 변경사항을 레포에 자동 push하지 않습니다.
- **새 파일은 항상 추가됩니다.** 레포에만 있는 파일(새 에이전트, 스킬)은 다른 파일에 충돌이 있어도 로컬에 항상 반영됩니다. 플러그인과 MCP 서버도 같은 방침이지만 무조건은 아닙니다 — 마켓플레이스 등록에 실패한 플러그인은 건너뛴 것으로 보고되고, 이 기기가 재현할 수 없는 항목은 복원 불가로 보고되며, 비밀 값 입력을 건너뛴 MCP 서버는 등록하지 않습니다.
- **충돌은 양쪽 모두 변경된 파일에서만 발생합니다.** `git merge-file` 3-way 병합을 시도하여, 변경 범위가 겹치지 않으면 자동 병합(`auto_merge`)됩니다. 같은 줄이 양쪽에서 달라졌을 때만 `conflict`로 분류되며 로컬 파일은 그대로 보존됩니다. 이때 로컬 유지 / 백업 채택 / 수동 병합 / 나중에 처리 중 선택할 수 있습니다.
- **`pull_only` 기기는 백업하지 않습니다.** 읽기 전용으로 지정된 기기는 레포에 자신의 상태를 push하지 않습니다.
- **MCP 서버는 서버 이름 키 단위로 병합됩니다.** `mcp-servers.json`은 서버마다 따로 판정되므로, 한 기기의 백업이 다른 기기에만 있는 서버를 지우지 않습니다. 삭제는 전파되지만 로컬 제거는 `/sync-restore`가 서버마다 물어본 뒤에만 이루어집니다.
- **`plugins.json`은 키 단위로 병합됩니다.** 플러그인 항목·마켓플레이스·설정 키가 각각 판정되므로, 한 기기의 백업이 다른 기기에만 있는 항목을 지우지 않습니다. 삭제는 전파되지만 로컬 제거는 `/sync-restore`가 물어본 뒤에만 이루어집니다.

동기화되지 않는 것:

- 마켓플레이스 **자동 업데이트 설정**(`autoUpdate`) — CLI에 이를 설정할 수단이 없습니다. 필요하면 기기마다 `~/.claude/settings.json`을 직접 고치세요
- **로컬 디렉토리에서 등록한 마켓플레이스와 그 소속 플러그인** — 다른 기기에는 등록할 소스가 없습니다. 그 기기에서 `claude plugin marketplace add`를 직접 실행하세요
- **의존성으로 자동 설치된 플러그인** — 부모를 복원하면 따라옵니다
- **마켓플레이스가 명령으로 설치하는 플러그인** — 세션 안에서 설치할 수 없어 사용자 터미널이 필요합니다
- **버전 제약(배열·객체)의 값** — 설치는 되지만 그 값이 이 기기에 재현되지 않습니다. 레포의 값은 보존되며, 포기하려면 복원에서 "이 기기 값으로 통일"을 골라야 합니다. **지우려면 그것이 먼저입니다**
- **플러그인 설정 값** — 마스킹되어 저장되며 복원 시 다시 입력합니다. 건너뛸 수 있습니다
- **보류 선택**(`~/.claude/.sync-state/plugins-held.json`) — 이 기기에만 남고 다른 기기로 번지지 않습니다. 지우면 다시 묻습니다

## 안전 장치

- **충돌 감지**: 마지막 공유 base 이후 양쪽에서 변경된 파일만 충돌로 표시하며, 로컬 파일은 절대 자동으로 덮어쓰지 않습니다.
- **민감 정보 보호**: `settings.json` 원본은 레포에 올리지 않고 세 필드만 추출하며, `pluginConfigs`의 값은 `<REDACTED>`로 마스킹합니다(키 이름은 복원 시 무엇을 물어야 하는지 알기 위해 남깁니다). MCP 서버 설정도 `headers`/`env` 값을 같은 방식으로 마스킹해 올립니다
- **메타데이터**: 백업마다 내용 해시 기반 base 스냅샷을 기록하여 정확한 3-way 충돌 판단에 활용

## 보안

CLAUDE.md나 에이전트 파일에 사내 URL, 내부 규칙 등 민감 정보가 포함될 수 있습니다. **백업 레포는 private으로 만드는 것을 권장합니다.**

특정 파일을 백업에서 제외하려면 `~/.claude/.syncignore`를 만드세요 — **한 줄에 하나씩 glob 패턴**을 적고, 레포 루트 기준 상대 경로와 대조합니다(`#`으로 시작하면 주석). gitignore 형식이 아닙니다 — 부정(`!`)이 없고 **후행 슬래시를 붙이면 아무것도 걸리지 않으므로** 디렉토리는 슬래시 없이 적습니다.

```
# 사내 전용 에이전트 제외
agents/internal-*.md

# 특정 스킬 제외 (후행 슬래시를 붙이지 않는다)
skills/secret-tool
```

다른 사람에게 설정을 공유할 때는 `.syncignore`로 민감 파일을 제외한 뒤 백업하면 됩니다.
