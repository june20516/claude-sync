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
- `plugins.json` — 플러그인/마켓플레이스 목록 (settings.json에서 추출, 민감 정보 미포함)
- `sync-metadata.json` — 파일별 수정 시각 (충돌 감지용)
- `mcp-servers.json` — `~/.claude.json`(user 스코프)의 MCP 서버 설정, 서버 이름 키 단위 병합
- `bootstrap.sh` — 새 기기용 복원 스크립트

### `mcp-servers.json`에 대하여

`headers`와 `env`의 값은 `<REDACTED>`로 저장되고 키 이름은 남습니다 — 복원할 때 무엇을 물어야 하는지 알기 위해서입니다. **`args`나 URL 쿼리스트링에 담긴 비밀은 마스킹되지 않으므로** 이 레포는 private으로 두세요. 복원 시 `/sync-restore`가 마스킹된 값을 하나씩 물어보며, 입력을 건너뛰면 인증이 깨진 서버를 만들지 않고 그 서버를 등록하지 않습니다.

이 파일은 **서버 이름 키 단위로 병합**되므로 한 기기에서 백업해도 다른 기기에만 있는 서버가 사라지지 않습니다. 반면 `plugins.json`은 매 백업마다 새로 생성되어 덮어쓰입니다.
