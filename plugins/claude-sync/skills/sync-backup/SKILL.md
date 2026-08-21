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
| `~/.claude.json` (user 스코프) → 추출 | `mcp-servers.json` | MCP 서버 설정 (비밀 값은 마스킹) |

settings.json에는 API 키 등 민감 정보가 포함될 수 있으므로, `enabledPlugins`와 `extraKnownMarketplaces` 필드만 추출하여 `plugins.json`으로 관리한다. settings.json 원본은 레포에 올리지 않는다.

MCP 서버는 `~/.claude.json`의 top-level `mcpServers`(user 스코프)만 대상으로 한다. 계정 레벨 커넥터(`claude.ai *`), 플러그인이 제공하는 서버(`plugin:*`), project(`.mcp.json`)·local 스코프 서버는 애초에 그 객체에 없으므로 자동으로 제외된다. `headers`와 `env`의 **값만** `<REDACTED>`로 마스킹하고 키 이름은 보존한다.

`mcp-servers.json`은 파일 통째로 덮어쓰지 않고 **서버 이름 키 단위 3-way 병합** 대상이다. 다른 기기가 추가·변경한 서버는 이 기기의 백업으로 사라지지 않는다.

반면 `plugins.json`은 여전히 매 백업마다 통째로 새로 생성되어 덮어쓰인다(reconcile 대상이 아니다). 여러 기기에서 서로 다른 플러그인을 쓰면 마지막에 백업한 기기의 목록이 남는다.

`~/.claude/.sync-state/`는 기기별 로컬 상태(merge-base)이므로 백업/복원 대상이 아니며 레포에 올리지 않는다.

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

### 0. 플러그인 루트 확인

**실행 중인 플러그인과 같은 버전의 스크립트를 써야 한다.** 옛 버전 디렉토리가 지워지지 않고 남으므로, 아무거나 고르면 3.0.0 세션이 2.0.0의 스크립트를 실행해 버전 표식이 조용히 안 써진다.

```bash
# plugins/cache 아래만 본다 — plugins/marketplaces는 레포 클론이지 설치본이 아니다.
# 여러 버전이 남아 있으므로 sort -V로 가장 높은 것을 고른다. head -1은 임의 선택이다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' | sort -V | tail -1)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

# 빈 값 확인이 먼저다. 비어 있는데 아래 python3를 부르면 "/.claude-plugin/plugin.json"을
# 열려다 트레이스백이 난다 — 원인이 "플러그인을 못 찾았다"임이 가려진다.
if [ -z "$SYNC_ROOT" ]; then
  echo "claude-sync 플러그인 설치 경로를 찾지 못했습니다." >&2
fi

# 어느 버전을 쓰는지 눈에 보이게 한다. 불일치는 조용하면 안 된다.
echo "Plugin root: $SYNC_ROOT"
python3 -c 'import json,sys
try:
    print("Version:", json.load(open(sys.argv[1])).get("version", "unknown"))
except Exception as e:
    print("Version: 읽지 못함 (%s)" % e)' "$SYNC_ROOT/.claude-plugin/plugin.json"
```

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 **즉시 중단하고** 사용자에게 안내한다. 어떤 버전을 실행할지 모르는 채로 진행해서는 안 된다.

버전을 읽지 못했다고 해서 중단하지는 않는다 — 그것은 표시용이고, 실제 판정은 `compat.py`가 맡는다.

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

설정에 `"pull_only": true`가 있으면 이 기기는 백업 금지다. 즉시 중단하고 안내한다:
> "이 기기는 pull_only로 지정되어 있어 로컬→리모트 백업을 수행하지 않습니다. 설정을 바꾸려면 sync-config.json에서 pull_only를 제거하세요."

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

### 4. 파일별 reconcile (push 판정)

무차별 복사 대신 파일별로 판정한다:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 $SYNC_SCRIPTS/reconcile_backup.py "$SYNC_REPO"
```

출력 JSON의 세 키를 확인한다:
- `reject`가 하나라도 있으면: "리모트가 앞선 변경이 있습니다. 먼저 /sync-restore 하세요" 안내 후 그 파일은 건너뛴다(push하지 않는다).
- `push` 파일만 `~/.claude/<rel>` → `$SYNC_REPO/<rel>`로 복사한다:

```bash
# reconcile 결과를 임시 파일에 저장
python3 $SYNC_SCRIPTS/reconcile_backup.py "$SYNC_REPO" > /tmp/claude-sync-reconcile.json

# push 목록 파일만 복사 (Python으로 처리)
python3 - <<'PY'
import json, os, shutil
data = json.load(open("/tmp/claude-sync-reconcile.json"))
repo = os.environ.get("SYNC_REPO", "/tmp/claude-sync-repo")
for rel in data.get("push", []):
    src = os.path.join(os.path.expanduser("~/.claude"), rel)
    dst = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
PY
```

`.syncignore`가 있으면 해당 패턴은 push 목록에서 제외한다:

```bash
if [ -f ~/.claude/.syncignore ]; then
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    [[ -z "$pattern" || "$pattern" == \#* ]] && continue
    find "$SYNC_REPO" -path "$SYNC_REPO/.git" -prune -o -path "$SYNC_REPO/$pattern" -print | while IFS= read -r f; do rm -rf "$f"; done
  done < ~/.claude/.syncignore
  echo ".syncignore 적용됨"
fi
```

### 5. plugins.json 생성

settings.json에서 플러그인 관련 필드만 추출한다:

```bash
python3 $SYNC_SCRIPTS/extract_plugins.py plugins.json
```

### 6. mcp-servers.json 생성 (키 단위 3-way 병합)

`~/.claude.json`의 user 스코프 `mcpServers`를 읽어 레포의 `mcp-servers.json`과 서버 이름 키 단위로 병합한다. `claude mcp list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"
rm -rf "$MCP_STAGING"
python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$MCP_STAGING" > /tmp/claude-sync-mcp.json
cat /tmp/claude-sync-mcp.json
```

출력 JSON의 `status`로 분기한다.

- `"skipped"`: `~/.claude.json`을 읽지 못했거나, **레포 파일의 형식을 알아볼 수 없다**(상위 버전이 쓴 백업일 수 있다). 어느 쪽이든 **레포의 `mcp-servers.json`은 손대지 않았고 base도 전진시키지 않는다.** `reason`을 사용자에게 알리고 MCP 단계만 건너뛴다. **파일 동기화는 그대로 진행한다.**

  `reason`이 "형식을 알아볼 수 없다"이면 이 기기의 플러그인이 낡은 것이므로 **업데이트를 안내한다**: `claude plugin marketplace update claude-sync && claude plugin update claude-sync`. 모르는 문서를 "서버 0개"로 읽어 덮어쓰면 상위 버전의 백업이 파괴되므로 건너뛰는 것이 옳다.
- `"ok"`: 아래 항목을 결과 보고(12단계)에 포함하고 각각 다음 행동을 안내한다.

| 키 | 의미 | 안내 |
|---|---|---|
| `conflicts.repo_kept` | 케이스 9 — 양쪽이 바뀜 | "양쪽이 바뀌었습니다. 레포 값을 그대로 두었습니다. `/sync-restore`에서 해소하세요" |
| `conflicts.repo_absent` | 케이스 5 — 타 기기 삭제 + 로컬 수정 | "다른 기기가 삭제했는데 이 기기에서 수정했습니다. `/sync-restore` 먼저 실행하세요" |
| `local_stale` | 케이스 4 — 타 기기가 삭제, 로컬 잔존 | "`/sync-restore`에서 로컬을 정리하세요" |
| `repo_ahead.absent` | 케이스 2 — 타 기기가 추가 | "다른 기기가 추가했습니다. `/sync-restore`가 이 기기에 설치합니다" |
| `repo_ahead.present` | 케이스 8 — 타 기기가 **변경** | "다른 기기가 이 서버를 **변경**했습니다. `/sync-restore`에서 채택할지 선택이 필요합니다" |
| `deleted` | 이 기기에서 지운 서버 | 레포에서도 제거되었음을 알린다 |

`repo_ahead.present`(케이스 8)에 케이스 2와 같은 문구("restore를 실행하면 반영됩니다")를 쓰면 안 된다. restore는 케이스 8을 자동 반영하지 않으므로 그 안내는 사실이 아니고, 사용자가 빠져나갈 수 없는 루프에 갇힌다. 실제로 필요한 것은 사용자의 선택이다.

충돌이 있어도 백업 전체를 막지 않는다. 해당 서버만 건너뛴다.

### 7. sync-metadata.json 생성

백업 시점의 메타데이터를 기록한다. 이 파일은 restore나 status에서 충돌 판단에 사용된다.

```bash
python3 $SYNC_SCRIPTS/generate_metadata.py sync-metadata.json
```

생성되는 파일 예시:

```json
{
  "files": {
    "agents/code-reviewer.md": "a3f2c1d4e5b6...(sha256 64자)",
    "skills/investigate/SKILL.md": "9d8e7f6a5b4c...(sha256 64자)",
    "CLAUDE.md": "1c2d3e4f5a6b...(sha256 64자)"
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
cd "${TMPDIR:-/tmp}/claude-sync-repo"
git add -A
git diff --cached --stat
```

변경 내용을 간단히 요약한 뒤, 아래 블록을 그대로 실행한다. **MCP base 갱신 호출이 "푸시 성공"과 "커밋할 변경 없음" 두 경로 모두에 있어야 한다** — 하나라도 빠지면 그 경로의 기기에서 base가 전진하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"
cd "$SYNC_REPO"
REPO_HAS_CONTENT=0

if git diff --cached --quiet; then
  echo "변경사항이 없습니다. 모든 설정이 최신 상태입니다."
  REPO_HAS_CONTENT=1          # 레포가 이미 이번 결과와 정합하다
elif git commit -m "sync: backup claude settings ($(date '+%Y-%m-%d %H:%M'))" && git push; then
  REPO_HAS_CONTENT=1
  mapfile -t PUSHED_RELS < <(python3 -c "
import json
data = json.load(open('/tmp/claude-sync-reconcile.json'))
for r in data.get('push', []):
    print(r)
")
  if [ "${#PUSHED_RELS[@]}" -gt 0 ]; then
    python3 "$SYNC_SCRIPTS/update_base.py" "$HOME/.claude" "${PUSHED_RELS[@]}"
  fi
else
  echo "푸시에 실패했습니다. base를 갱신하지 않습니다."
fi

# MCP base: 레포가 실제로 그 내용을 갖게 된 뒤에만 기록한다.
# 스테이징 파일은 collect_mcp.py가 status=ok일 때만 쓰므로, 파일 존재가 곧 'skip 아님'이다.
if [ "$REPO_HAS_CONTENT" = "1" ] && [ -f "$MCP_STAGING/mcp-servers.json" ]; then
  python3 "$SYNC_SCRIPTS/update_base.py" "$MCP_STAGING" mcp-servers.json
  echo "MCP base 갱신됨"
fi
```

### 11. base(.sync-state) 갱신 규칙

**파일**: 커밋 & 푸시에 성공한 경우에만 push된 각 파일의 base를 방금 올린 로컬 내용으로 갱신한다. **핵심 계약: push 성공 파일의 base ← 로컬 내용.**

**MCP 서버**: base는 레포 파일의 사본이 아니라 **"이 기기의 로컬이 동의한 부분"만 담는 파생 문서**다. `collect_mcp.py`가 계산한 `next_base`를 스테이징 디렉토리에 써 두었다가 여기서 옮긴다.

- `update_base.py "$MCP_STAGING" mcp-servers.json` — 올바른 호출.
- `update_base.py "$SYNC_REPO" mcp-servers.json` — **금지.** `base ← 레포 파일 바이트`가 되어, 타 기기가 추가·변경한 서버(케이스 2·8)의 값이 base에 실린다. 그러면 다음 백업이 그것을 "이 기기가 삭제했다"로 오독해 **다른 기기의 서버를 경고 없이 지운다.**
- 기록을 건너뛰는 경우는 **푸시 실패**와 **MCP 단계 skip** 둘뿐이다. 충돌(`conflicts`)이나 `local_stale`이 있다고 해서 전역으로 막지 않는다 — `next_base`가 이름 단위로 이미 그 서버의 base를 고정하고 있고, 전역 게이트는 나머지 서버의 base까지 얼려 정확도를 떨어뜨린다.

### 12. 결과 보고

백업 완료 후 변경된 파일 목록과 결과를 사용자에게 요약해서 보여준다.
