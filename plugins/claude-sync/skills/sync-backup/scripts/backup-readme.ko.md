# Claude 설정 백업

이 레포는 Claude Code 설정의 백업본입니다.

## 복원 방법

### 방법 1: bootstrap.sh (빠른 복원)

```bash
git clone <이 레포 URL> ${TMPDIR:-/tmp}/claude-sync-repo
bash ${TMPDIR:-/tmp}/claude-sync-repo/bootstrap.sh
```

Git만 있으면 동작합니다. 파일 복원 후 플러그인 설치가 필요하면 Claude Code에서 `/sync-restore`를 실행하세요.

### 방법 2: claude-sync 플러그인

```bash
claude plugin marketplace add claude-sync --source github --repo june20516/claude-sync
claude plugin install claude-sync@claude-sync
```

Claude Code에서:

```
/sync-restore
```

## 포함된 내용

- `agents/` — 커스텀 에이전트 정의
- `skills/` — 범용 스킬
- `CLAUDE.md` — 글로벌 규칙
- `plugins.json` — 플러그인 목록·마켓플레이스·설정 키 이름 (settings.json에서 추출, 설정 값은 마스킹), 키 단위 병합
- `sync-metadata.json` — 버전 표식과, 이 백업에 담긴 파일별 내용 해시. 그 해시는 기록일 뿐 판정 입력이 아닙니다 — 충돌 판정은 이 파일이 아니라 기기마다 자기 `.sync-state/` base와 대조합니다. 되읽히는 것은 `min_reader_version`이며, 이 백업을 이해하지 못하는 낮은 버전 기기를 막습니다.
- `mcp-servers.json` — `~/.claude.json`(user 스코프)의 MCP 서버 설정, 서버 이름 키 단위 병합
- `bootstrap.sh` — 새 기기용 복원 스크립트

### 백업하기 전에: 모든 기기가 v3.0.0이어야 합니다

> **아직 claude-sync v2.x인 기기에서는 `/sync-backup`을 실행하지 마세요** — 그 기기가 MCP 서버를 하나도 쓰지 않더라도 마찬가지입니다. v2는 이 레포에 무엇이 있는지 읽지 않고 **백업 문서 둘을 모두** 그 기기 것만으로 다시 만들기 때문에, 한 번만 실행해도 각 문서의 레포 사본이 되돌려집니다.
>
> - `mcp-servers.json` — 옛 배열 형식으로 다시 쓰이고, 명령에 공백이 든 서버는 아예 사라집니다.
> - `plugins.json` — 그 기기의 `settings.json`에서 다시 만들어지는데, v2가 옮기는 것은 `enabledPlugins`와 `extraKnownMarketplaces` 둘뿐입니다. **다른 기기에만 있는** 플러그인·마켓플레이스가 사라지고, `pluginConfigs`와 `additionalMarketplaces`는 v2가 그 키를 아예 모르므로 **그 기기 것까지** 사라집니다.
>
> v3 기기는 `sync-metadata.json`의 `min_reader_version` 표식을 읽고 스스로 멈춥니다. **v2.x 기기에는 그 가드가 없어 표식 자체를 읽지 못하므로**, 배포 순서가 유일한 방어입니다. 이미 벌어진 뒤에 되돌리려면 이 레포의 git 이력에서 그 파일을 복원해야 합니다.

### `mcp-servers.json`에 대하여

`headers`와 `env`의 값은 `<REDACTED>`로 저장되고 키 이름은 남습니다 — 복원할 때 무엇을 물어야 하는지 알기 위해서입니다. **`args`나 URL 쿼리스트링에 담긴 비밀은 마스킹되지 않으므로** 이 레포는 private으로 두세요. 복원 시 `/sync-restore`가 마스킹된 값을 하나씩 물어보며, 입력을 건너뛰면 인증이 깨진 서버를 만들지 않고 그 서버를 등록하지 않습니다.

이 파일은 **서버 이름 키 단위로 병합**되므로 한 기기에서 백업해도 다른 기기에만 있는 서버가 사라지지 않습니다.

이 파일은 claude-sync v3.0.0 이상이 스키마 v2(`{"version": 2, "scope": "user", "servers": {...}}`)로 씁니다. **아직 v2.x인 기기는 이 파일을 옛 배열 형식으로 덮어쓰고 명령에 공백이 든 서버를 누락시킵니다** — 위의 *백업하기 전에: 모든 기기가 v3.0.0이어야 합니다* 절을 보세요. 그 절은 `plugins.json`까지 함께 다룹니다.

### `plugins.json`에 대하여

`plugins.json`도 세 섹션 각각에 대해 같은 방식으로 키 단위 병합됩니다 — 플러그인 항목·마켓플레이스·설정 키가 각각 판정되므로 한 기기에서 백업해도 다른 기기에만 있는 항목이 사라지지 않습니다.

동기화되지 않는 것:

- 마켓플레이스 **자동 업데이트 설정**(`autoUpdate`) — CLI에 이를 설정할 수단이 없습니다. 필요하면 기기마다 `~/.claude/settings.json`을 직접 고치세요
- **로컬 디렉토리에서 등록한 마켓플레이스와 그 소속 플러그인** — 다른 기기에는 등록할 소스가 없습니다. 그 기기에서 `claude plugin marketplace add`를 직접 실행하세요
- **의존성으로 자동 설치된 플러그인** — 부모를 복원하면 따라옵니다
- **마켓플레이스가 명령으로 설치하는 플러그인** — 세션 안에서 설치할 수 없어 사용자 터미널이 필요합니다
- **버전 제약(배열·객체)의 값** — 설치는 되지만 그 값이 이 기기에 재현되지 않습니다. 레포의 값은 보존되며, 포기하려면 복원에서 "이 기기 값으로 통일"을 골라야 합니다. **지우려면 그것이 먼저입니다**
- **플러그인 설정 값** — 마스킹되어 저장되며 복원 시 다시 입력합니다. 건너뛸 수 있습니다
- **보류 선택**(`~/.claude/.sync-state/plugins-held.json`) — 이 기기에만 남고 다른 기기로 번지지 않습니다. 지우면 다시 묻습니다
