#!/usr/bin/env python3
"""로컬 ~/.claude 와 레포 백업의 차이를 3-way(내용 해시)로 분석해 출력한다. mtime 미사용."""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402

repo_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "SYNC_REPO", "/tmp/claude-sync-repo"
)
HOME_CLAUDE = os.path.expanduser("~/.claude")

rels = sorted(set(ss.iter_synced_relpaths(repo_path)) | set(ss.iter_synced_relpaths(HOME_CLAUDE)))

buckets = {
    "in_sync": [],
    "repo_only": [],      # restore 시 추가
    "local_only": [],     # backup 시 push
    "local_ahead": [],    # backup 시 push
    "fast_forward": [],   # restore 시 업데이트
    "conflict": [],       # 양쪽 변경
}

for rel in rels:
    local = os.path.join(HOME_CLAUDE, rel)
    repo = os.path.join(repo_path, rel)
    L = ss.file_hash(local)
    R = ss.file_hash(repo)
    S = ss.base_hash(rel)
    cls = ss.classify(L, R, S, local_exists=L is not None, repo_exists=R is not None)
    buckets[cls].append(rel)

print("=" * 60)
print("git-like 동기화 상태 (내용 해시 기준, mtime 미사용)")
print("=" * 60)

labels = [
    ("conflict", "⚠ 충돌 — 양쪽 변경 (restore 시 해소 필요)"),
    ("fast_forward", "↓ 업데이트 가능 — 레포가 앞섬 (restore 시 적용)"),
    ("repo_only", "+ 새 파일 — 레포에만 있음 (restore 시 추가)"),
    ("local_ahead", "↑ 로컬 앞섬 (backup 시 push)"),
    ("local_only", "+ 로컬 전용 (backup 시 push)"),
    ("in_sync", "✓ 동일"),
]
for key, label in labels:
    items = buckets[key]
    if items:
        print("\n%s (%d개):" % (label, len(items)))
        for f in items:
            print("  " + f)

if not any(buckets[k] for k in buckets if k != "in_sync"):
    print("\n모든 파일이 동기화 상태입니다.")

# 플러그인 비교 (enabledPlugins 키 집합)
repo_plugins = os.path.join(repo_path, "plugins.json")
settings = os.path.join(HOME_CLAUDE, "settings.json")
if os.path.exists(repo_plugins) and os.path.exists(settings):
    with open(repo_plugins) as f:
        rp = set(json.load(f).get("enabledPlugins", {}).keys())
    with open(settings) as f:
        lp = set(json.load(f).get("enabledPlugins", {}).keys())
    only_repo, only_local = rp - lp, lp - rp
    if only_repo or only_local:
        print("\n플러그인 차이:")
        for p in sorted(only_repo):
            print("  + 레포에만(restore 시 설치): " + p)
        for p in sorted(only_local):
            print("  - 로컬에만(backup 시 추가): " + p)
    else:
        print("\n플러그인: 동일")

print()
