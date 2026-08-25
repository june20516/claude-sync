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
# semver 모양인 디렉토리만 본다 — 'unknown'이나 'latest'는 sort -V에서 릴리즈를 이긴다.
#   (이 기기에 실제로 cache/claude-plugins-official/skill-creator/unknown 이 있다.)
# 경로 전체가 아니라 버전 성분으로 정렬한다 — 그러지 않으면 마켓플레이스 이름이 정렬을
#   지배해, 이름이 뒤인 마켓플레이스의 낮은 버전이 선택된다.
# head -1은 임의 선택이므로 쓰지 않는다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' \
  | grep -E '/[0-9]+\.[0-9]+\.[0-9]+$' \
  | awk -F/ '{print $NF"\t"$0}' | sort -V | tail -1 | cut -f2-)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

# 못 찾았으면 비-0으로 끝낸다. echo만 하고 exit 0으로 끝나면 "판정 불가"가 "문제 없음"과
# 같은 모양이 되고, 뒤 단계의 rm -rf + clone + push가 어느 버전인지도 모른 채 먼저 돈다.
# exit이 아니라 false다 — 뒤 단계가 같은 셸 세션의 $SYNC_SCRIPTS를 쓰므로 세션을 끝내면 안 된다.
if [ -z "$SYNC_ROOT" ]; then
  echo "claude-sync 플러그인 설치 경로를 찾지 못했습니다. 진행하지 마세요." >&2
  false
else
  # 어느 버전을 쓰는지 눈에 보이게 한다. 불일치는 조용하면 안 된다.
  echo "Plugin root: $SYNC_ROOT"
  python3 -c 'import json,sys
try:
    print("Version:", json.load(open(sys.argv[1])).get("version", "unknown"))
except Exception as e:
    print("Version: 읽지 못함 (%s)" % e)' "$SYNC_ROOT/.claude-plugin/plugin.json"
fi
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

### 2.5 호환성 검사 (차단 지점)

**레포를 가져온 직후, 아무것도 쓰기 전에 검사한다.** 늦게 하면 이미 레포를 건드린 뒤가 된다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"
```

**먼저 검사가 성립했는지 본다.** 명령이 비-0으로 끝났거나, 출력이 JSON이 아니거나, `blocked` 키가 없으면 — **`blocked: true`와 같이 다룬다.** `compat.py`는 차단일 때도 종료 코드 0으로 JSON을 내도록 만들어져 있으므로, 그렇지 않다는 것은 판정 결과가 아니라 **검사 자체가 성립하지 않았다**는 뜻이다(`python3`이 없거나, `SYNC_ROOT`가 잘못 잡혔거나, 파일이 없는 경우). 이때만 SKILL.md가 문구를 직접 쓴다:

> "호환성 검사를 실행하지 못했습니다. 이 레포를 안전하게 다룰 수 있는지 판단할 수 없어 중단했습니다. 0단계에서 찾은 플러그인 루트가 올바른지, `python3`이 있는지 확인하세요."

출력 JSON의 `blocked`가 `true`면 **여기서 중단한다.** 파일 복사(4단계)도 `plugins.json`(5단계)도 MCP 수집(6단계)도 하지 않는다.

**`message` 필드를 그대로 보여준다. 명령을 직접 타자하지 않는다** — 안내 문구는 `compat.py`가 만드는 것이 계약이고, SKILL.md가 따로 쓰면 드리프트한다.

덧붙이는 한 문장은 **`blocked`가 아니라 `reason`으로 분기한다.** `blocked`는 "차단"이라는 뜻일 뿐 "업그레이드하면 풀린다"는 뜻이 아니다.

| `reason` | 덧붙일 문장 |
|---|---|
| `older_than_min_reader` / `my_version_unknown` / `min_reader_unparsable` | "백업을 중단했습니다. 위 명령으로 업데이트한 뒤 다시 실행하세요." |
| `metadata_unreadable` | "백업을 중단했습니다. 표식을 읽을 수 없어 이 레포를 안전하게 다룰 수 있는지 판단할 수 없기 때문입니다." |
| `repo_not_found` | "백업을 중단했습니다. 레포 경로를 찾지 못했습니다." |
| `check_failed` | "백업을 중단했습니다. 호환성 검사 자체가 실패했습니다." |

`metadata_unreadable`에 "업데이트하세요"를 붙이면 **틀린 해법**이다. 그 갈래의 `message`에는 업그레이드 명령이 의도적으로 빠져 있으므로 "위 명령"이 가리킬 것도 없다.

`pull_only` 가드가 1단계에서 하는 것과 같은 형태다. **차단은 이 명령에만 건다** — status를 막으면 진단 수단이 사라지고 restore를 막으면 업데이트 안내를 받을 경로가 사라진다.

`blocked`가 `false`면 조용히 다음 단계로 간다.

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

### 5.5 다운그레이드 사고 탐지

**MCP 수집보다 먼저 한다.** 6단계가 `mcp-servers.json`을 v2로 덮어쓰면 "레포가 v1 배열"이라는 증거가 사라져 탐지 자체가 불가능해진다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"
```

`status`가 `"skipped"`면 탐지만 건너뛰고 백업은 계속한다. 탐지는 부가 기능이다. 다만 **`reason`을 사용자에게 알린다** — "사고가 없다"가 아니라 "확인하지 못했다"이기 때문이다.

`newer_schema_seen`이 `true`면 히스토리에 **이 버전이 알아보지 못하는 백업**이 있다는 뜻이다. 그 사실을 알리고, 복구 후보로 제시된 커밋이 그보다 오래된 것임을 명시한다.

`downgrade_suspected`가 `true`면 레포의 `mcp-servers.json`이 v1 배열인데 이 기기의 base는 v2였다는 뜻이다 — **옛 버전 기기가 덮어썼다.** 사용자에게 다음을 보여주고 고르게 한다.

1. 사고 사실과 근거: "백업 레포의 MCP 파일이 옛 형식으로 되돌아가 있습니다. 이 기기가 마지막으로 본 것은 새 형식이었습니다."
2. `candidate`가 있으면 그 커밋의 `date`·`subject`·`server_count`·`server_names`
3. 선택지 셋:
   - **복구한다** — 후보 커밋의 파일을 레포 작업본에 되돌려 놓고 백업을 계속한다. 이어지는 6단계의 3-way 병합이 로컬과 정상적으로 합친다.
     ```bash
     git -C "$SYNC_REPO" show "<sha>:mcp-servers.json" > "$SYNC_REPO/mcp-servers.json"
     ```
   - **복구하지 않고 계속한다** — 현재 레포 상태 그대로 백업한다.
   - **중단한다** — 다른 기기의 상태를 확인한 뒤 다시 온다.

`candidate`가 `null`이면 히스토리에 v2 커밋이 없다는 뜻이다. 사고는 알리되 복구는 제안하지 않는다.

**자동으로 복구하지 않는다.** 옛 기기가 *의도적으로* 지운 서버까지 되살리기 때문이다.

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

`base_staging`이 `"failed"`이면 **레포는 갱신됐지만 base 스테이징이 실패한 것이다.** `base_staging_reason`을 그대로 보여준다. 이 실행에서는 base가 전진하지 않으므로 다음 백업이 같은 내용을 다시 계산해 복구한다. **`skipped`로 오해하지 않는다** — `skipped`의 표준 문구는 "레포 파일은 손대지 않았다"인데 이 경로에서는 그것이 거짓이다.

충돌이 있어도 백업 전체를 막지 않는다. 해당 서버만 건너뛴다.

### 7. sync-metadata.json 생성

백업 시점의 파일 해시와 **버전 표식**을 기록한다.

```bash
python3 "$SYNC_SCRIPTS/generate_metadata.py" "$SYNC_REPO/sync-metadata.json"
```

생성되는 파일 예시:

```json
{
  "files": {
    "CLAUDE.md": "1c2d3e4f5a6b...(sha256 64자)",
    "agents/code-reviewer.md": "a3f2c1d4e5b6...(sha256 64자)",
    "skills/investigate/SKILL.md": "9d8e7f6a5b4c...(sha256 64자)"
  },
  "min_reader_version": "3.0.0",
  "schema": { "mcp-servers.json": 2 },
  "written_by_version": "3.0.0"
}
```

- `written_by_version` — 이 백업을 쓴 플러그인 버전. 정보일 뿐 판정에 쓰지 않는다.
- `min_reader_version` — **이 백업을 읽는 데 필요한 최소 버전.** 2.5단계의 차단 근거가 이것 하나다.
- `schema` — 사람이 읽는 요약. 항목별 보류는 각 파일 자체의 `version` 필드로 판정하므로 이 맵은 판정에 쓰지 않는다.

이 파일은 매 백업마다 재생성되는 파생 산출물이며 **reconcile 대상이 아니다.** 시각·기기명은 넣지 않는다 — 매번 diff가 생겨 소음이 된다. 언제·누가는 git commit이 이미 기록한다.

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
# 스테이징 최종 파일은 collect_mcp.py가 레포 쓰기에 성공한 뒤 rename으로 만든다.
# 따라서 파일 존재가 곧 "레포까지 반영됨"이다 — status 값을 다시 읽을 필요가 없다.
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
- 기록을 건너뛰는 경우는 **푸시 실패**, **MCP 단계 skip**, **`base_staging` 실패** 셋이다 — 세 경우 모두 결과적으로 스테이징 최종 파일(`$MCP_STAGING/mcp-servers.json`)이 없으므로 게이트(`[ -f "$MCP_STAGING/mcp-servers.json" ]`)가 같은 방식으로 막는다. 충돌(`conflicts`)이나 `local_stale`이 있다고 해서 전역으로 막지 않는다 — `next_base`가 이름 단위로 이미 그 서버의 base를 고정하고 있고, 전역 게이트는 나머지 서버의 base까지 얼려 정확도를 떨어뜨린다.

### 12. 결과 보고

백업 완료 후 변경된 파일 목록과 결과를 사용자에게 요약해서 보여준다.

레포에 `sync-metadata.json`을 처음 쓴 경우(직전 커밋에 그 파일의 `min_reader_version`이 없었던 경우) 한 번만 알린다. 아래 명령으로 레포에서 직접 확인한다 — 짐작하지 않는다:

```bash
git -C "$SYNC_REPO" show HEAD~1:sync-metadata.json 2>/dev/null \
  | grep -q min_reader_version || echo "표식을 처음 기록했습니다"
```

> "이 백업은 claude-sync 3.0.0 이상을 요구하도록 기록되었습니다. **3.0.0 이상 기기는 이 표식을 읽고 스스로 멈춥니다. 그러나 2.x 기기는 멈추지 않습니다** — 2.x에는 이 가드가 없어, `/sync-backup`을 실행하면 레포를 옛 형식으로 되돌리고 명령에 공백이 든 서버를 누락시킵니다. 모든 기기를 3.0.0으로 올리고 재시작하기 전에는 다른 기기에서 `/sync-backup`을 실행하지 마세요."
