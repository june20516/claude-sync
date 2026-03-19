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
python3 << 'PYEOF'
import json, os, datetime

HOME = os.path.expanduser("~")
REPO = "${TMPDIR:-/tmp}/claude-sync-repo"
META = os.path.join(REPO, "sync-metadata.json")

# 경로 매핑: 레포 상대경로 → 로컬 절대경로
def to_local(rel):
    if rel == "CLAUDE.md":
        return os.path.join(HOME, ".claude", "CLAUDE.md")
    if rel == "plugins.json":
        return None  # 별도 처리
    return os.path.join(HOME, ".claude", rel)

def collect_files(base):
    """디렉토리 내 모든 파일의 상대 경로 수집"""
    result = set()
    if not os.path.exists(base):
        return result
    if os.path.isfile(base):
        return {os.path.basename(base)}
    for root, _, files in os.walk(base):
        for f in files:
            result.add(os.path.relpath(os.path.join(root, f), base))
    return result

# 레포에 있는 파일 목록
repo_files = set()
for d in ["agents", "skills"]:
    p = os.path.join(REPO, d)
    if os.path.isdir(p):
        for r, _, fs in os.walk(p):
            for f in fs:
                repo_files.add(os.path.relpath(os.path.join(r, f), REPO))
if os.path.isfile(os.path.join(REPO, "CLAUDE.md")):
    repo_files.add("CLAUDE.md")
if os.path.isfile(os.path.join(REPO, "plugins.json")):
    repo_files.add("plugins.json")

# 로컬 파일 목록 (동기화 대상만)
local_files = set()
for d in ["agents", "skills"]:
    p = os.path.join(HOME, ".claude", d)
    if os.path.isdir(p):
        for r, _, fs in os.walk(p):
            for f in fs:
                local_files.add(os.path.relpath(os.path.join(r, f), os.path.join(HOME, ".claude")))
if os.path.isfile(os.path.join(HOME, ".claude", "CLAUDE.md")):
    local_files.add("CLAUDE.md")

# 메타데이터 로드
has_meta = os.path.exists(META)
metadata = {}
backup_ts = None
if has_meta:
    with open(META) as f:
        metadata = json.load(f)
    backup_ts = metadata.get("backup_timestamp")
    file_times = metadata.get("files", {})

print("=" * 60)
if has_meta:
    print(f"마지막 백업: {backup_ts}")
else:
    print("메타데이터 없음 (단순 비교 모드)")
print("=" * 60)

# 상태 분류
added_local = []     # 로컬에만 있음 (backup하면 추가됨)
added_repo = []      # 레포에만 있음 (restore하면 추가됨)
modified = []        # 양쪽 다 있지만 내용이 다름
conflict = []        # 양쪽 다 백업 이후 변경됨
unchanged = []       # 동일

all_files = repo_files | local_files
for rel in sorted(all_files):
    if rel in ["sync-metadata.json", "plugins.json"]:
        continue

    local = to_local(rel)
    if local is None:
        continue
    repo_path = os.path.join(REPO, rel)
    in_repo = rel in repo_files
    in_local = os.path.exists(local) if local else False

    if in_local and not in_repo:
        added_local.append(rel)
    elif in_repo and not in_local:
        added_repo.append(rel)
    elif in_repo and in_local:
        # 내용 비교
        with open(repo_path, "rb") as a, open(local, "rb") as b:
            if a.read() == b.read():
                unchanged.append(rel)
                continue

        # 메타데이터 있으면 충돌 분석
        if has_meta and rel in file_times:
            backed_mtime = file_times[rel]
            local_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(local), tz=datetime.timezone.utc).isoformat()
            if local_mtime > backed_mtime:
                conflict.append(rel)
            else:
                modified.append(rel)
        else:
            modified.append(rel)

# 출력
if conflict:
    print(f"\n⚠ 충돌 가능 ({len(conflict)}개) — 로컬과 레포 모두 변경됨:")
    for f in conflict:
        print(f"  {f}")

if modified:
    print(f"\n↕ 차이 있음 ({len(modified)}개) — 레포와 로컬이 다름:")
    for f in modified:
        print(f"  {f}")

if added_local:
    print(f"\n+ 로컬에만 있음 ({len(added_local)}개) — backup하면 레포에 추가됨:")
    for f in added_local:
        print(f"  {f}")

if added_repo:
    print(f"\n+ 레포에만 있음 ({len(added_repo)}개) — restore하면 로컬에 추가됨:")
    for f in added_repo:
        print(f"  {f}")

if unchanged:
    print(f"\n✓ 동일 ({len(unchanged)}개)")

if not any([conflict, modified, added_local, added_repo]):
    print("\n모든 설정이 동기화 상태입니다.")

# plugins.json 비교
repo_plugins = os.path.join(REPO, "plugins.json")
if os.path.exists(repo_plugins):
    with open(repo_plugins) as f:
        repo_p = json.load(f)
    settings_path = os.path.join(HOME, ".claude", "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            local_s = json.load(f)
        local_p = {
            "enabledPlugins": local_s.get("enabledPlugins", {}),
            "extraKnownMarketplaces": local_s.get("extraKnownMarketplaces", {})
        }
        repo_set = set(repo_p.get("enabledPlugins", {}).keys())
        local_set = set(local_p.get("enabledPlugins", {}).keys())
        only_repo = repo_set - local_set
        only_local = local_set - repo_set
        if only_repo or only_local:
            print("\n플러그인 차이:")
            for p in only_repo:
                print(f"  + 레포에만: {p}")
            for p in only_local:
                print(f"  - 로컬에만: {p}")
        else:
            print("\n플러그인: 동일")

print()
PYEOF
```

### 3. 결과 요약

분석 결과를 사용자에게 보여준다. 이 스킬은 아무것도 변경하지 않으므로, 필요한 다음 단계를 안내한다:

- 로컬 변경사항을 레포에 반영하려면 → `/sync-backup`
- 레포 내용을 로컬에 적용하려면 → `/sync-restore`
