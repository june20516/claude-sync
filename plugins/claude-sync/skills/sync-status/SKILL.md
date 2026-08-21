---
name: sync-status
description: 로컬 Claude 설정과 Git 레포 백업 간의 차이를 보여주는 dry-run 도구. 아무것도 변경하지 않고 상태만 확인한다. 사용자가 /sync-status 를 실행했을 때만 동작한다. 자동 호출하지 않는다.
disable-model-invocation: true
---

# sync-status

로컬 Claude 설정과 Git 레포 백업 간의 차이를 보여준다. 아무것도 변경하지 않는 읽기 전용 명령이다.

backup이나 restore 전에 "지금 상태가 어떤지" 확인하고 싶을 때 사용한다.

## 설정 파일

동기화 설정은 `~/.claude/sync-config.json`에 저장된다. 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다 (이것만 유일하게 쓰기 동작이 발생할 수 있다).

## 실행 절차

### 0. 플러그인 루트 확인

**실행 중인 플러그인과 같은 버전의 스크립트를 써야 한다.** 옛 버전 디렉토리가 지워지지 않고 남으므로, 아무거나 고르면 이 세션이 다른 버전의 스크립트를 실행하게 된다.

```bash
# plugins/cache 아래만 본다 — plugins/marketplaces는 레포 클론이지 설치본이 아니다.
# 여러 버전이 남아 있으므로 sort -V로 가장 높은 것을 고른다. head -1은 임의 선택이다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' | sort -V | tail -1)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-status/scripts"
SYNC_BACKUP_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

if [ -z "$SYNC_ROOT" ]; then
  echo "claude-sync 플러그인 설치 경로를 찾지 못했습니다." >&2
fi

echo "Plugin root: $SYNC_ROOT"
python3 -c 'import json,sys
try:
    print("Version:", json.load(open(sys.argv[1])).get("version", "unknown"))
except Exception as e:
    print("Version: 읽지 못함 (%s)" % e)' "$SYNC_ROOT/.claude-plugin/plugin.json"
```

`SYNC_BACKUP_SCRIPTS`는 다운그레이드 탐지(`detect_downgrade.py`)를 부르기 위해 필요하다. 읽기 전용 스크립트이므로 status가 불러도 안전하며, 복사본을 만들지 않는다.

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 즉시 중단하고 사용자에게 안내한다.

### 1. 설정 확인 및 레포 준비

```bash
cat ~/.claude/sync-config.json
```

레포를 최신 상태로 가져온다 (clone 또는 pull):

```bash
if [ -d ${TMPDIR:-/tmp}/claude-sync-repo/.git ]; then
  cd ${TMPDIR:-/tmp}/claude-sync-repo && git pull --rebase
else
  rm -rf ${TMPDIR:-/tmp}/claude-sync-repo
  git clone <repo_url> ${TMPDIR:-/tmp}/claude-sync-repo
fi
```

### 2. 메타데이터 기반 상태 분석

`sync-metadata.json`이 있으면 이를 활용해 정밀하게 분석하고, 없으면 단순 diff로 비교한다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 $SYNC_SCRIPTS/check_status.py "$SYNC_REPO"
```

파일/플러그인 분석 이후, MCP 서버 비교도 수행한다:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"
fi
```

출력 JSON의 `status`가 `"skipped"`면 `~/.claude.json`을 읽지 못했거나 레포 파일의 형식을 알아볼 수 없는 것이다. `reason`을 알리고 MCP 비교만 생략한다 — 읽기 실패를 "서버 0개"로 오인해 레포의 서버를 전부 `only_repo`로 보고하지 않기 위해서다. `reason`이 형식 문제이면 **이 기기의 플러그인이 낡은 것**이므로 `claude plugin update claude-sync`를 안내한다. 세 목록이 모두 비어 있으면 "MCP 서버: 동일"이라고 보고한다.

### 3. 결과 요약

상태 분류 (내용 해시 3-way, mtime 미사용):
- **in_sync**: 로컬과 레포 내용 동일
- **fast_forward**: 레포가 앞섬 → restore 시 자동 업데이트
- **repo_only**: 레포에만 있는 새 파일 → restore 시 추가
- **local_ahead / local_only**: 로컬이 앞섬 → backup 시 push
- **conflict**: 양쪽 모두 base 이후 변경 → restore 시 해소 필요

**MCP 서버의 어휘는 파일과 다르다.** 위의 "local_ahead / local_only: 로컬이 앞섬 → backup 시 push"는 MCP에 적용되지 않는다.

- **only_local**: 로컬에만 있음 — 신규이거나, 다른 기기가 삭제한 뒤 남은 것일 수 있습니다. `/sync-backup`이 판정합니다.
- **only_repo**: 레포에만 있음 — `/sync-restore`가 이 기기에 설치합니다.
- **changed**: 양쪽에 있으나 설정이 다름 — 어느 쪽이 앞선 것인지는 `/sync-backup`이 base를 읽어 판정합니다.

status는 base를 읽지 않으므로 케이스를 확정하지 않는다. 판정의 단일 진입점은 backup의 `merge` 하나다.

이 명령은 아무것도 바꾸지 않는다. MCP 서버 비교 대상은 `~/.claude.json`의 user 스코프뿐이다. 계정 커넥터(`claude.ai *`), 플러그인 제공 서버(`plugin:*`), project·local 스코프 서버는 그 객체에 없으므로 자동으로 제외된다.

분석 결과를 사용자에게 보여준다. 이 스킬은 아무것도 변경하지 않으므로, 필요한 다음 단계를 안내한다:

- 로컬 변경사항을 레포에 반영하려면 → `/sync-backup`
- 레포 내용을 로컬에 적용하려면 → `/sync-restore`
