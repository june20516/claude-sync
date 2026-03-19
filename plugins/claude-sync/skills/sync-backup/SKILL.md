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
  "repo_url": "git@github.com:user/claude-sync.git"
}
```

최초 실행 시 이 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다.

## 동기화 대상

| 소스 | 레포 내 경로 | 비고 |
|------|-------------|------|
| `~/.claude/agents/` | `agents/` | 커스텀 에이전트 정의 |
| `~/.claude/skills/` | `skills/` | 범용 스킬들 |
| `~/.claude/CLAUDE.md` | `CLAUDE.md` | 글로벌 규칙 |
| `~/.claude/settings.json` → 추출 | `plugins.json` | 플러그인/마켓플레이스 목록만 |

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

### 3. 파일 수집

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

### 4. plugins.json 생성

settings.json에서 플러그인 관련 필드만 추출한다:

```bash
if command -v jq &>/dev/null; then
  jq '{enabledPlugins: .enabledPlugins, extraKnownMarketplaces: .extraKnownMarketplaces}' \
    ~/.claude/settings.json > plugins.json
else
  python3 -c "
import json
with open('$HOME/.claude/settings.json') as f:
    data = json.load(f)
result = {}
if 'enabledPlugins' in data:
    result['enabledPlugins'] = data['enabledPlugins']
if 'extraKnownMarketplaces' in data:
    result['extraKnownMarketplaces'] = data['extraKnownMarketplaces']
print(json.dumps(result, indent=2))
" > plugins.json
fi
```

### 5. sync-metadata.json 생성

백업 시점의 메타데이터를 기록한다. 이 파일은 restore나 status에서 충돌 판단에 사용된다.

```bash
python3 -c "
import json, os, datetime

def get_file_times(base_path, prefix=''):
    result = {}
    if not os.path.exists(base_path):
        return result
    if os.path.isfile(base_path):
        mtime = os.path.getmtime(base_path)
        result[prefix or os.path.basename(base_path)] = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
        return result
    for root, dirs, files in os.walk(base_path):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base_path)
            key = f'{prefix}/{rel}' if prefix else rel
            mtime = os.path.getmtime(full)
            result[key] = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
    return result

metadata = {
    'backup_timestamp': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
    'files': {}
}
metadata['files'].update(get_file_times(os.path.expanduser('~/.claude/agents'), 'agents'))
metadata['files'].update(get_file_times(os.path.expanduser('~/.claude/skills'), 'skills'))
metadata['files'].update(get_file_times(os.path.expanduser('~/.claude/CLAUDE.md'), 'CLAUDE.md'))
metadata['files'].update({'plugins.json': datetime.datetime.now(tz=datetime.timezone.utc).isoformat()})

print(json.dumps(metadata, indent=2))
" > sync-metadata.json
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

### 6. bootstrap.sh 생성

새 기기에서 Git과 이 레포 URL만으로 전체 설정을 복원할 수 있는 부트스트랩 스크립트를 생성한다. 이 스크립트는 레포에 함께 커밋된다.

```bash
cat > bootstrap.sh << 'BOOTSTRAP'
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$HOME/.claude"

echo "=== Claude 설정 복원 (bootstrap) ==="

# ~/.claude 디렉토리 생성
mkdir -p "$CLAUDE_DIR"

# agents 복원
if [ -d "$SCRIPT_DIR/agents" ]; then
  mkdir -p "$CLAUDE_DIR/agents"
  cp -r "$SCRIPT_DIR/agents/" "$CLAUDE_DIR/agents/"
  echo "✓ agents 복원됨"
fi

# skills 복원
if [ -d "$SCRIPT_DIR/skills" ]; then
  mkdir -p "$CLAUDE_DIR/skills"
  cp -r "$SCRIPT_DIR/skills/" "$CLAUDE_DIR/skills/"
  echo "✓ skills 복원됨"
fi

# CLAUDE.md 복원
if [ -f "$SCRIPT_DIR/CLAUDE.md" ]; then
  cp "$SCRIPT_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
  echo "✓ CLAUDE.md 복원됨"
fi

# sync-config.json 생성 (레포 URL 자동 감지)
REPO_URL=$(cd "$SCRIPT_DIR" && git remote get-url origin 2>/dev/null || echo "")
if [ -n "$REPO_URL" ] && [ ! -f "$CLAUDE_DIR/sync-config.json" ]; then
  cat > "$CLAUDE_DIR/sync-config.json" << EOF
{
  "repo_url": "$REPO_URL"
}
EOF
  echo "✓ sync-config.json 생성됨 (repo: $REPO_URL)"
fi

# 플러그인 복원 안내
if [ -f "$SCRIPT_DIR/plugins.json" ]; then
  echo ""
  echo "=== 플러그인 설치 ==="
  echo "plugins.json에 기록된 플러그인을 설치하려면"
  echo "Claude Code에서 /sync-restore 를 실행하세요."
  echo "(또는 수동으로 claude plugin install 명령을 사용하세요)"
fi

echo ""
echo "=== 완료 ==="
echo "Claude Code를 시작하면 복원된 설정이 적용됩니다."
BOOTSTRAP
chmod +x bootstrap.sh
```

### 7. README.md 생성

백업 레포의 내용을 설명하는 README를 생성한다. 매 백업마다 갱신되므로 항상 최신 상태를 반영한다.

```bash
cat > README.md << 'README'
# Claude Settings Backup

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
- `bootstrap.sh` — 새 기기용 복원 스크립트
README
```

### 8. 커밋 & 푸시

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

### 8. 결과 보고

백업 완료 후 변경된 파일 목록과 결과를 사용자에게 요약해서 보여준다.
