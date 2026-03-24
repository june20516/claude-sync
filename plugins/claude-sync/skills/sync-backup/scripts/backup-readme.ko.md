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
- `mcp-servers.json` — MCP 서버 목록 (이름, URL, 타입)
- `bootstrap.sh` — 새 기기용 복원 스크립트
