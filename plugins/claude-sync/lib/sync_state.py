#!/usr/bin/env python3
"""claude-sync 공용 코어.

mtime을 일절 쓰지 않는다. 모든 판단은 내용 sha256과
base(이 기기가 마지막으로 reconcile한 remote 내용) 기준이다.
"""
import hashlib
import os
import subprocess
import tempfile

SYNC_STATE_DIR = os.path.expanduser("~/.claude/.sync-state")
BASE_DIR = os.path.join(SYNC_STATE_DIR, "base")


def content_hash(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    """파일의 sha256 hex. 없으면 None."""
    try:
        with open(path, "rb") as f:
            return content_hash(f.read())
    except FileNotFoundError:
        return None


def base_blob_path(relpath, base_dir=BASE_DIR):
    return os.path.join(base_dir, relpath)


def read_base(relpath, base_dir=BASE_DIR):
    """base(마지막 reconcile한 remote) 내용. 없으면 None."""
    try:
        with open(base_blob_path(relpath, base_dir), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def base_hash(relpath, base_dir=BASE_DIR):
    data = read_base(relpath, base_dir)
    return content_hash(data) if data is not None else None


def write_base(relpath, data, base_dir=BASE_DIR):
    """base 블롭 기록(불변식 갱신). data가 None이면 삭제."""
    path = base_blob_path(relpath, base_dir)
    if data is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def classify(local_hash, repo_hash, seen_hash, local_exists, repo_exists):
    """3-way 분류.

    반환: in_sync | repo_only | local_only | local_ahead | fast_forward | conflict
    seen_hash는 base가 없으면 None.
    """
    if not repo_exists:
        return "local_only"
    if not local_exists:
        return "repo_only"
    if local_hash == repo_hash:
        return "in_sync"
    changed_local = local_hash != seen_hash
    changed_remote = repo_hash != seen_hash
    if changed_local and not changed_remote:
        return "local_ahead"
    if changed_remote and not changed_local:
        return "fast_forward"
    if changed_local and changed_remote:
        return "conflict"
    return "in_sync"  # L==S and R==S면 L==R이라 도달 불가 — 방어


def three_way_merge(local_bytes, base_bytes, repo_bytes):
    """git merge-file로 3-way 머지.

    반환 (merged_bytes, conflict_count).
    conflict_count == 0 이면 깨끗한 자동 병합(안 겹침).
    > 0 이면 그 수만큼 겹친 충돌 영역.
    """
    with tempfile.TemporaryDirectory() as d:
        lp = os.path.join(d, "local")
        bp = os.path.join(d, "base")
        rp = os.path.join(d, "repo")
        with open(lp, "wb") as f:
            f.write(local_bytes)
        with open(bp, "wb") as f:
            f.write(base_bytes)
        with open(rp, "wb") as f:
            f.write(repo_bytes)
        proc = subprocess.run(
            ["git", "merge-file", "-p", "--diff3", lp, bp, rp],
            capture_output=True,
        )
    if proc.returncode < 0:
        raise RuntimeError("git merge-file 실패: %r" % proc.stderr)
    return proc.stdout, proc.returncode
