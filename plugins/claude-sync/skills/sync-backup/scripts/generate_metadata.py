#!/usr/bin/env python3
"""백업 시점의 파일별 내용 해시(sha256) 메타데이터를 생성한다. mtime 미사용."""
import hashlib
import json
import os
import sys

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def collect(base, prefix):
    result = {}
    if os.path.isfile(base):
        result[prefix] = file_sha256(base)
        return result
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base)
                result[prefix + "/" + rel] = file_sha256(full)
    return result


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else "sync-metadata.json"
    claude_dir = os.path.expanduser("~/.claude")

    metadata = {"files": {}}
    metadata["files"].update(collect(os.path.join(claude_dir, "agents"), "agents"))
    metadata["files"].update(collect(os.path.join(claude_dir, "skills"), "skills"))
    metadata["files"].update(collect(os.path.join(claude_dir, "CLAUDE.md"), "CLAUDE.md"))

    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
