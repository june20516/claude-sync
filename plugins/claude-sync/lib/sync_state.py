#!/usr/bin/env python3
"""claude-sync 공용 코어.

mtime을 일절 쓰지 않는다. 모든 판단은 내용 sha256과
base(이 기기가 마지막으로 reconcile한 remote 내용) 기준이다.
"""
import hashlib
import os
import subprocess
import tempfile

import keyed_sync as ks

SYNC_STATE_DIR = os.path.expanduser("~/.claude/.sync-state")
BASE_DIR = os.path.join(SYNC_STATE_DIR, "base")


def content_hash(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    """파일의 sha256 hex. 파일이 없으면 None. (PermissionError 등 그 외 OSError는 전파한다.)"""
    try:
        with open(path, "rb") as f:
            return content_hash(f.read())
    except FileNotFoundError:
        return None


def base_blob_path(relpath, base_dir=BASE_DIR):
    return os.path.join(base_dir, relpath)


def read_base(relpath, base_dir=BASE_DIR):
    """base(마지막 reconcile한 remote) 내용. 파일이 없으면 None. (PermissionError 등 그 외 OSError는 전파한다.)"""
    try:
        with open(base_blob_path(relpath, base_dir), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def base_hash(relpath, base_dir=BASE_DIR):
    data = read_base(relpath, base_dir)
    return content_hash(data) if data is not None else None


def write_base(relpath, data, base_dir=BASE_DIR):
    """base 블롭 기록(불변식 갱신). data가 None이면 삭제.

    쓰기는 ks.dump_bytes에 위임한다(원자적 교체 + fsync) — 잘린 base 블롭은
    parse_base가 None으로 읽어 합집합 degrade를 부르고, 그러면 삭제 전파가 조용히 죽는다.

    삭제는 dump_bytes가 남겼을 수 있는 <path>.tmp까지 함께 지운다. **현재 영향은
    없다(위생이다)** — base 디렉토리를 walk하는 코드가 없고(소비자는 전부 relpath 하나를
    read_base로 읽는다) data=None으로 부르는 프로덕션 호출자도 없다. 그러니 이 줄을
    "무슨 사고를 막은 수정"으로 읽지 말 것. .tmp는 os.replace 전에 SIGKILL로 죽었을 때만
    남는다(정상 실패 경로는 dump_bytes가 스스로 지운다).
    """
    path = base_blob_path(relpath, base_dir)
    if data is None:
        for target in (path, path + ".tmp"):
            try:
                os.remove(target)
            except FileNotFoundError:
                pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ks.dump_bytes(data, path)


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


def restore_action(local_hash, repo_hash, seen_hash, local_exists, repo_exists):
    """복원이 이 파일에 무엇을 하는가. 반환: skip | add | overwrite | keep | merge.

    **소비자가 둘이다.** `reconcile_restore.py`가 이 값으로 **실행**하고,
    `check_status.py`가 같은 값으로 `excluded_in_repo` 항목의 **처방을 설명한다**
    (`.syncignore`는 복원 방향에 적용되지 않으므로 제외 파일도 이 판정을 그대로 받는다).
    그래서 이 파일이 `lib/`에 있다 — 한쪽에만 있으면 설명과 실행이 갈리고, 갈려도
    증상이 없다(사용자는 틀린 문구를 볼 뿐이다).

    `check_status`의 처방표가 여기서 나올 수 있는 값 **전부**를 덮는지는
    `test_reconcile.py`의 완전성 단정이 건다.
    """
    cls = classify(local_hash, repo_hash, seen_hash, local_exists, repo_exists)
    return {
        "in_sync": "skip",
        "repo_only": "add",
        "fast_forward": "overwrite",
        "local_ahead": "keep",
        "local_only": "keep",
        "conflict": "merge",
    }[cls]


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
    # git merge-file: 0=clean, 1..127=N conflicts, 음수(시그널)/128+ (255 등)=치명적 오류
    if proc.returncode < 0 or proc.returncode > 127:
        raise RuntimeError("git merge-file 실패: %r" % proc.stderr)
    return proc.stdout, proc.returncode


SYNCED_DIRS = ("agents", "skills")
SYNCED_FILES = ("CLAUDE.md",)


def iter_synced_relpaths(root):
    """root(=~/.claude 또는 레포) 아래 동기화 대상 상대경로를 yield.

    **`.syncignore`를 적용하지 않는다(의도).** 이 함수는 레포 쪽 트리에도 쓰이는데
    제외 목록은 `~/.claude` 안에 있어 root 하나로는 어느 쪽 규칙인지 정할 수 없다.
    그래서 필터는 **소비자가 건다** — 규정의 정본과 세 소비자의 유도는
    lib/syncignore.py 모듈 docstring에 있다. 요약하면 `.syncignore`는 "올리지 않는다"
    하나이고 backup 방향 전용이라:
    - check_status.py(sync-status)는 **로컬 열거에만** 건다. 레포에도 있는 제외 파일은
      `excluded_in_repo`로 따로 보고한다.
    - reconcile_backup.py도 **로컬 열거에 건다.** 파일 결과는 걸든 안 걸든 같지만
      (4단계 bash가 레포에서 지운다) 보고가 갈린다 — 걸지 않으면 제외 파일이
      `/sync-backup`의 `push`에 "곧 업로드될 파일"로 나오고 `/sync-status`는 같은
      파일에 침묵해, 사용자가 한 세션에서 모순된 말을 듣는다.
    - reconcile_restore.py는 **걸지 않는다(결정).** 복원 방향에서 존중하면 다른 기기가
      올린 같은 경로 파일을 영영 받지 못한다.
    - generate_metadata.py는 **레포 작업 트리**를 걷는다 — 제외는 4단계가 그 트리에서
      이미 적용했으므로 걸지 않는다(spec 3.3).
    """
    for name in SYNCED_DIRS:
        d = os.path.join(root, name)
        if os.path.isdir(d):
            # followlinks=False(기본값): 동기 대상 디렉터리는 실제 디렉터리여야 하므로 심볼릭 링크 디렉터리는 의도적으로 따라가지 않는다.
            for r, _, files in os.walk(d):
                for f in files:
                    yield os.path.relpath(os.path.join(r, f), root)
    for name in SYNCED_FILES:
        if os.path.isfile(os.path.join(root, name)):
            yield name
