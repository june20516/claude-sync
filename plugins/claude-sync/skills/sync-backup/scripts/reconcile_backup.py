#!/usr/bin/env python3
"""백업(push) 방향 파일별 판정.

사용: reconcile_backup.py <repo_path>  (~/.claude 기준 로컬을 레포로 push)
JSON 출력: {"push":[...], "reject":[...], "in_sync":[...]}
실제 파일 복사/커밋은 SKILL.md 흐름에서 수행하며, push된 파일의 base는 로컬 내용으로 갱신한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402


def backup_action(local_hash, repo_hash, seen_hash):
    """반환: in_sync | push | reject"""
    if repo_hash is None:
        return "push"  # 레포에 없음 → 새로 추가
    if local_hash == repo_hash:
        return "in_sync"
    if repo_hash == seen_hash:
        return "push"  # 로컬만 변경(local ahead)
    return "reject"    # remote가 base 이후 변경됨 → restore 먼저


def main():
    repo_path = sys.argv[1]
    home = os.path.expanduser("~/.claude")
    out = {"push": [], "reject": [], "in_sync": []}
    for rel in sorted(ss.iter_synced_relpaths(home)):
        L = ss.file_hash(os.path.join(home, rel))
        R = ss.file_hash(os.path.join(repo_path, rel))
        S = ss.base_hash(rel)
        out[backup_action(L, R, S)].append(rel)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
