---
name: sync-backup
description: Claude 설정 파일들(agents, skills, CLAUDE.md, 플러그인 목록)을 Git 레포에 백업한다. 사용자가 /sync-backup 을 실행했을 때만 동작한다. 자동 호출하지 않는다.
disable-model-invocation: true
---

# sync-backup

Claude 설정 파일들을 Git 레포에 백업하는 스킬이다.

## 설정 파일

동기화 설정은 `~/.claude/sync-config.json`에 저장된다:

```json
{
  "repo_url": "git@github.com:user/claude-sync.git",
  "git_user_name": "Your Name",
  "git_user_email": "you@example.com"
}
```

- 최초 실행 시 이 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다.
- `git_user_name`과 `git_user_email`은 선택 사항이다. 설정하면 백업 레포에 로컬 git config로 적용된다. 설정하지 않으면 글로벌 git config를 그대로 사용한다. 임시 디렉토리에 클론하므로 `includeIf` 기반 설정이 적용되지 않을 수 있어 필요한 경우 여기에 명시한다.

## 동기화 대상

| 소스 | 레포 내 경로 | 비고 |
|------|-------------|------|
| `~/.claude/agents/` | `agents/` | 커스텀 에이전트 정의 |
| `~/.claude/skills/` | `skills/` | 범용 스킬들 |
| `~/.claude/CLAUDE.md` | `CLAUDE.md` | 글로벌 규칙 |
| `~/.claude/settings.json` → 추출 | `plugins.json` | 플러그인/마켓플레이스 목록만 |
| `claude mcp list` → 추출 | `mcp-servers.json` | MCP 서버 이름과 URL |

settings.json에는 API 키 등 민감 정보가 포함될 수 있으므로, `enabledPlugins`와 `extraKnownMarketplaces` 필드만 추출하여 `plugins.json`으로 관리한다. settings.json 원본은 레포에 올리지 않는다.

## 보안

백업 레포에는 CLAUDE.md나 에이전트 파일에 사내 URL, 내부 규칙 등 민감 정보가 포함될 수 있다. 따라서:

- **백업 레포는 private 권장**. 최초 실행 시 사용자에게 이 점을 안내한다.
- **`.syncignore`** 파일로 특정 파일을 백업에서 제외할 수 있다. `~/.claude/.syncignore`에 gitignore 형식으로 패턴을 작성한다.

`.syncignore` 예시:
```
# 사내 전용 에이전트 제외
agents/internal-*.md

# 특정 스킬 제외
skills/secret-tool/
```

## 실행 절차

### 0. 스크립트 경로 확인

이 스킬에서 사용하는 스크립트들의 경로를 먼저 찾는다. 이후 모든 단계에서 `$SYNC_SCRIPTS`로 참조한다.

```bash
SYNC_SCRIPTS=$(find ~/.claude -path "*/sync-backup/scripts" -type d 2>/dev/null | head -1)
echo "Scripts: $SYNC_SCRIPTS"
```

이 경로를 찾지 못하면 플러그인이 제대로 설치되지 않은 것이므로 사용자에게 안내한다.

### 1. 설정 확인

```bash
cat ~/.claude/sync-config.json
```

파일이 없으면 사용자에게 Git 레포 URL을 물어본다. URL을 받으면:

```bash
cat > ~/.claude/sync-config.json << 'EOF'
{
  "repo_url": "<사용자가 입력한 URL>"
}
EOF
```

### 2. 레포 준비

작업 디렉토리는 `${TMPDIR:-/tmp}/claude-sync-repo`를 사용한다.

```bash
if [ -d ${TMPDIR:-/tmp}/claude-sync-repo/.git ]; then
  cd ${TMPDIR:-/tmp}/claude-sync-repo && git pull --rebase
else
  rm -rf ${TMPDIR:-/tmp}/claude-sync-repo
  git clone <repo_url> ${TMPDIR:-/tmp}/claude-sync-repo
fi
```

레포가 비어 있으면(최초) 초기 커밋을 생성한다:

```bash
cd ${TMPDIR:-/tmp}/claude-sync-repo
git commit --allow-empty -m "initial commit"
git push -u origin main
```

### 3. Git User 설정

`sync-config.json`에 `git_user_name`과 `git_user_email`이 있으면 레포에 로컬 설정을 적용한다. 없으면 이 단계를 건너뛴다(글로벌 설정 사용).

```bash
cd ${TMPDIR:-/tmp}/claude-sync-repo
# sync-config.json에서 git_user_name, git_user_email 읽기
GIT_USER_NAME=$(python3 -c "import json; c=json.load(open('$HOME/.claude/sync-config.json')); print(c.get('git_user_name',''))")
GIT_USER_EMAIL=$(python3 -c "import json; c=json.load(open('$HOME/.claude/sync-config.json')); print(c.get('git_user_email',''))")

if [ -n "$GIT_USER_NAME" ]; then
  git config user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
  git config user.email "$GIT_USER_EMAIL"
fi
```

만약 `git_user_name`/`git_user_email`이 없고, 레포에서 `git config user.email`도 비어있으면(글로벌 설정도 없는 상태), 사용자에게 안내한다:

> "백업 레포가 임시 디렉토리에 있어 gitconfig의 includeIf 조건에 매칭되지 않을 수 있습니다. `~/.claude/sync-config.json`에 `git_user_name`과 `git_user_email`을 추가하면 이 레포에 로컬로 적용됩니다."

사용자가 이름/이메일을 알려주면 `sync-config.json`에 저장하고 레포에 적용한다. 스킵하겠다고 하면 그대로 진행한다.

### 4. 파일 수집

`.syncignore`가 있으면 해당 패턴에 매칭되는 파일을 제외한다.

```bash
cd ${TMPDIR:-/tmp}/claude-sync-repo

# agents 복사
rm -rf agents/
cp -r ~/.claude/agents/ agents/ 2>/dev/null || true

# skills 복사
rm -rf skills/
cp -r ~/.claude/skills/ skills/ 2>/dev/null || true

# CLAUDE.md 복사
cp ~/.claude/CLAUDE.md CLAUDE.md 2>/dev/null || true

# .syncignore 적용
if [ -f ~/.claude/.syncignore ]; then
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    # 빈 줄과 주석 건너뛰기
    [[ -z "$pattern" || "$pattern" == \#* ]] && continue
    # 매칭되는 파일 삭제 (레포 작업 디렉토리에서)
    find . -path "./.git" -prune -o -path "./$pattern" -print | while IFS= read -r f; do rm -rf "$f"; done
  done < ~/.claude/.syncignore
  echo ".syncignore 적용됨"
fi
```

### 5. plugins.json 생성

settings.json에서 플러그인 관련 필드만 추출한다:

```bash
python3 $SYNC_SCRIPTS/extract_plugins.py plugins.json
```

### 6. mcp-servers.json 생성

`claude mcp list`의 출력을 파싱하여 MCP 서버 목록을 추출한다. 복원에 필요한 name, url, type만 저장한다.

```bash
claude mcp list 2>/dev/null | python3 $SYNC_SCRIPTS/parse_mcp.py mcp-servers.json
```

### 7. sync-metadata.json 생성

백업 시점의 메타데이터를 기록한다. 이 파일은 restore나 status에서 충돌 판단에 사용된다.

```bash
python3 $SYNC_SCRIPTS/generate_metadata.py sync-metadata.json
```

생성되는 파일 예시:

```json
{
  "backup_timestamp": "2026-03-19T15:30:00",
  "files": {
    "agents/code-reviewer.md": "2026-03-18T15:41:00",
    "skills/investigate/SKILL.md": "2026-03-18T17:15:00",
    "CLAUDE.md": "2026-03-19T10:00:00",
    "plugins.json": "2026-03-19T15:30:00"
  }
}
```

### 8. bootstrap.sh 복사

새 기기에서 Git과 이 레포 URL만으로 전체 설정을 복원할 수 있는 부트스트랩 스크립트를 레포에 복사한다.

```bash
cp $SYNC_SCRIPTS/bootstrap.sh bootstrap.sh
chmod +x bootstrap.sh
```

### 9. README.md 복사

백업 레포의 내용을 설명하는 README(영어)를 레포에 복사한다. 한국어 README가 필요한지 사용자에게 물어보고, 필요하면 함께 복사한다.

```bash
cp $SYNC_SCRIPTS/backup-readme.md README.md
```

사용자가 한국어 README도 원하면:

```bash
cp $SYNC_SCRIPTS/backup-readme.ko.md README.ko.md
```

### 10. 커밋 & 푸시

```bash
cd ${TMPDIR:-/tmp}/claude-sync-repo
git add -A
git diff --cached --stat
```

- **변경사항이 없으면**: "변경사항이 없습니다. 모든 설정이 최신 상태입니다." 라고 알려준다.
- **변경사항이 있으면**: 변경 내용을 간단히 요약하고, 커밋 & 푸시한다:

```bash
git commit -m "sync: backup claude settings ($(date +%Y-%m-%d %H:%M))"
git push
```

### 11. 결과 보고

백업 완료 후 변경된 파일 목록과 결과를 사용자에게 요약해서 보여준다.
