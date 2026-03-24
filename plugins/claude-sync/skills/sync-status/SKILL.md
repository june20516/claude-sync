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
python3 ~/.claude/skills/sync-status/scripts/check_status.py "$SYNC_REPO"
```

파일/플러그인 분석 이후, MCP 서버 비교도 수행한다:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  claude mcp list 2>/dev/null | python3 ~/.claude/skills/sync-status/scripts/compare_mcp.py "$SYNC_REPO/mcp-servers.json"
fi
```

### 3. 결과 요약

분석 결과를 사용자에게 보여준다. 이 스킬은 아무것도 변경하지 않으므로, 필요한 다음 단계를 안내한다:

- 로컬 변경사항을 레포에 반영하려면 → `/sync-backup`
- 레포 내용을 로컬에 적용하려면 → `/sync-restore`
