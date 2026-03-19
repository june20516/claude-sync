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
- `~/.claude/settings.json` → `plugins.json` — 플러그인/마켓플레이스 목록 (민감 정보 제외)

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

**방법 2: bootstrap.sh (Claude Code 없이도 가능)**

```bash
git clone <백업-레포-url> /tmp/claude-sync-repo
bash /tmp/claude-sync-repo/bootstrap.sh
```

### 변경 전 확인

```
/sync-status
```

## 안전 장치

- **충돌 감지**: 백업 시점 이후 로컬에서 수정된 파일이 있으면 restore를 전체 중단
- **민감 정보 보호**: `settings.json` 원본은 레포에 올리지 않고, 플러그인 목록만 추출
- **메타데이터**: 백업마다 파일별 수정 시각을 기록하여 충돌 판단에 활용

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
