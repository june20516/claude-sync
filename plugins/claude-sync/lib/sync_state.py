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
