#!/usr/bin/env python3
"""sync-metadata.json을 읽어 로컬 파일과의 충돌 여부를 분석한다."""
import json, os, datetime, sys

repo_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SYNC_REPO", "/tmp/claude-sync-repo")
meta_path = os.path.join(repo_path, "sync-metadata.json")

if not os.path.exists(meta_path):
    print("메타데이터 없음 — 전체 비교 모드로 전환")
    sys.exit(0)

with open(meta_path) as f:
    metadata = json.load(f)

file_times = metadata.get("files", {})
status = {"safe": [], "conflict": [], "repo_only": [], "local_only": []}

for repo_rel, backed_up_mtime in file_times.items():
    if repo_rel == "CLAUDE.md":
        local = os.path.expanduser("~/.claude/CLAUDE.md")
    elif repo_rel == "plugins.json":
        continue
    elif repo_rel.startswith("agents/") or repo_rel.startswith("skills/"):
        local = os.path.expanduser("~/.claude/" + repo_rel)
    else:
        continue

    if not os.path.exists(local):
        status["repo_only"].append(repo_rel)
        continue

    local_mtime = datetime.datetime.fromtimestamp(
        os.path.getmtime(local), tz=datetime.timezone.utc
    ).isoformat()
    if local_mtime > backed_up_mtime:
        status["conflict"].append((repo_rel, backed_up_mtime, local_mtime))
    else:
        status["safe"].append(repo_rel)

print(json.dumps(status, indent=2, default=str))
