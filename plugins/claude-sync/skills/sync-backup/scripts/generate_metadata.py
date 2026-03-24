#!/usr/bin/env python3
"""백업 시점의 파일별 수정 시각 메타데이터를 생성한다."""
import json, os, datetime, sys

output_path = sys.argv[1] if len(sys.argv) > 1 else "sync-metadata.json"


def get_file_times(base_path, prefix=""):
    result = {}
    if not os.path.exists(base_path):
        return result
    if os.path.isfile(base_path):
        mtime = os.path.getmtime(base_path)
        key = prefix or os.path.basename(base_path)
        result[key] = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
        return result
    for root, dirs, files in os.walk(base_path):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base_path)
            key = prefix + "/" + rel if prefix else rel
            mtime = os.path.getmtime(full)
            result[key] = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
    return result


now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
claude_dir = os.path.expanduser("~/.claude")

metadata = {
    "backup_timestamp": now,
    "files": {}
}
metadata["files"].update(get_file_times(os.path.join(claude_dir, "agents"), "agents"))
metadata["files"].update(get_file_times(os.path.join(claude_dir, "skills"), "skills"))
metadata["files"].update(get_file_times(os.path.join(claude_dir, "CLAUDE.md"), "CLAUDE.md"))
metadata["files"]["plugins.json"] = now

with open(output_path, "w") as f:
    json.dump(metadata, f, indent=2)
    f.write("\n")
