#!/usr/bin/env python3
"""로컬 Claude 설정과 레포 백업 간 차이를 분석하여 출력한다."""
import json, os, datetime, sys

repo_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SYNC_REPO", "/tmp/claude-sync-repo")

HOME = os.path.expanduser("~")
META = os.path.join(repo_path, "sync-metadata.json")


def to_local(rel):
    if rel == "CLAUDE.md":
        return os.path.join(HOME, ".claude", "CLAUDE.md")
    if rel == "plugins.json":
        return None
    return os.path.join(HOME, ".claude", rel)


# 레포에 있는 파일 목록
repo_files = set()
for d in ["agents", "skills"]:
    p = os.path.join(repo_path, d)
    if os.path.isdir(p):
        for r, _, fs in os.walk(p):
            for f in fs:
                repo_files.add(os.path.relpath(os.path.join(r, f), repo_path))
if os.path.isfile(os.path.join(repo_path, "CLAUDE.md")):
    repo_files.add("CLAUDE.md")
if os.path.isfile(os.path.join(repo_path, "plugins.json")):
    repo_files.add("plugins.json")

# 로컬 파일 목록
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
file_times = {}
if has_meta:
    with open(META) as f:
        metadata = json.load(f)
    backup_ts = metadata.get("backup_timestamp")
    file_times = metadata.get("files", {})

print("=" * 60)
if has_meta:
    print("마지막 백업: " + metadata.get("backup_timestamp", ""))
else:
    print("메타데이터 없음 (단순 비교 모드)")
print("=" * 60)

# 상태 분류
added_local = []
added_repo = []
modified = []
conflict = []
unchanged = []

all_files = repo_files | local_files
for rel in sorted(all_files):
    if rel in ["sync-metadata.json", "plugins.json"]:
        continue
    local = to_local(rel)
    if local is None:
        continue
    repo_file = os.path.join(repo_path, rel)
    in_repo = rel in repo_files
    in_local = os.path.exists(local) if local else False

    if in_local and not in_repo:
        added_local.append(rel)
    elif in_repo and not in_local:
        added_repo.append(rel)
    elif in_repo and in_local:
        with open(repo_file, "rb") as a, open(local, "rb") as b:
            if a.read() == b.read():
                unchanged.append(rel)
                continue
        if has_meta and rel in file_times:
            backed_mtime = file_times[rel]
            local_mtime = datetime.datetime.fromtimestamp(
                os.path.getmtime(local), tz=datetime.timezone.utc
            ).isoformat()
            if local_mtime > backed_mtime:
                conflict.append(rel)
            else:
                modified.append(rel)
        else:
            modified.append(rel)

if conflict:
    print("\n⚠ 충돌 가능 (%d개) — 로컬과 레포 모두 변경됨:" % len(conflict))
    for f in conflict:
        print("  " + f)
if modified:
    print("\n↕ 차이 있음 (%d개) — 레포와 로컬이 다름:" % len(modified))
    for f in modified:
        print("  " + f)
if added_local:
    print("\n+ 로컬에만 있음 (%d개) — backup하면 레포에 추가됨:" % len(added_local))
    for f in added_local:
        print("  " + f)
if added_repo:
    print("\n+ 레포에만 있음 (%d개) — restore하면 로컬에 추가됨:" % len(added_repo))
    for f in added_repo:
        print("  " + f)
if unchanged:
    print("\n✓ 동일 (%d개)" % len(unchanged))
if not any([conflict, modified, added_local, added_repo]):
    print("\n모든 설정이 동기화 상태입니다.")

# plugins.json 비교
repo_plugins = os.path.join(repo_path, "plugins.json")
if os.path.exists(repo_plugins):
    with open(repo_plugins) as f:
        repo_p = json.load(f)
    settings_path = os.path.join(HOME, ".claude", "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path) as f:
            local_s = json.load(f)
        repo_set = set(repo_p.get("enabledPlugins", {}).keys())
        local_set = set(local_s.get("enabledPlugins", {}).keys())
        only_repo = repo_set - local_set
        only_local = local_set - repo_set
        if only_repo or only_local:
            print("\n플러그인 차이:")
            for p in only_repo:
                print("  + 레포에만: " + p)
            for p in only_local:
                print("  - 로컬에만: " + p)
        else:
            print("\n플러그인: 동일")

print()
