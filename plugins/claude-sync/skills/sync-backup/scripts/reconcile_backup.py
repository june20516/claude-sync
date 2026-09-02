#!/usr/bin/env python3
"""백업(push) 방향 파일별 판정.

사용: reconcile_backup.py <repo_path>  (~/.claude 기준 로컬을 레포로 push)
JSON 출력: {"push": [...], "in_sync": [...],
            "reject": {"remote_ahead": [...], "no_base": [...]}}
실제 파일 복사/커밋은 SKILL.md 흐름에서 수행하며, push된 파일과 in_sync 파일의 base는
로컬 내용으로 갱신한다(10단계).

**`reject`는 두 갈래다.** 어느 쪽도 push하지 않지만 사용자에게 할 말이 다르다 —
`remote_ahead`는 기준선이 있고 레포가 그 뒤로 바뀐 것이고(restore 먼저), `no_base`는
기준선이 없어 **방향을 모르는** 것이다. 한 버킷으로 내면 4단계가 후자에도 "리모트가
앞섰다"고 단정하고, 그 안내를 따라 restore에서 「백업 채택」을 고르면 로컬 변경이
사라진다(실측 — 2026-09-01 첫 실기기 백업의 `agents/code-reviewer.md`는 로컬이 앞서
있었다). 갈래 이름은 reconcile_restore.py의 충돌 사유(`no_base`)와 같다.

**`.syncignore`를 로컬 열거에 건다** — `check_status.py`와 같은 자리, 같은 규칙이다
(정본: lib/syncignore.py 모듈 docstring). 파일 결과는 걸든 안 걸든 같다(4단계 bash가
레포에서 지운다). 다른 것은 **보고**다 — 걸지 않으면 제외한 로컬 전용 파일이 `push`
아래 나열되고 SKILL.md가 그것을 "곧 업로드될 파일"로 렌더링하는데, 같은 세션의
`/sync-status`는 같은 파일에 침묵한다. 두 스킬이 같은 제외 파일을 다르게 설명한다.
덤으로 10단계의 base 갱신도 정확해진다 — 제외 파일은 레포에 도달하지 않으므로
그 base 항목은 "올렸다"는 거짓 기록이었다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402
import syncignore  # noqa: E402


def backup_action(local_hash, repo_hash, seen_hash):
    """반환: in_sync | push | reject. reject의 갈래는 reject_bucket이 정한다."""
    if repo_hash is None:
        return "push"  # 레포에 없음 → 새로 추가
    if local_hash == repo_hash:
        return "in_sync"
    if repo_hash == seen_hash:
        return "push"  # 로컬만 변경(local ahead)
    return "reject"    # 기준선이 없거나(no_base) remote가 base 이후 변경됨(remote_ahead)


def reject_bucket(seen_hash):
    """reject의 갈래. 기준선(S)이 없으면 방향을 모르는 것이지 리모트가 앞선 것이 아니다.

    입력이 seen_hash 하나뿐인 것이 계약이다 — backup_action이 reject를 낸 뒤 S 하나가
    갈래를 정하므로, 두 판정이 어긋날 자리가 없다.
    """
    return "no_base" if seen_hash is None else "remote_ahead"


def main():
    repo_path = sys.argv[1]
    home = os.path.expanduser("~/.claude")
    out = {"push": [], "in_sync": [], "reject": {"remote_ahead": [], "no_base": []}}
    patterns = syncignore.load_patterns(syncignore.default_path(home))
    for rel in sorted(syncignore.filter_relpaths(ss.iter_synced_relpaths(home), patterns)):
        L = ss.file_hash(os.path.join(home, rel))
        R = ss.file_hash(os.path.join(repo_path, rel))
        S = ss.base_hash(rel)
        action = backup_action(L, R, S)
        if action == "reject":
            out["reject"][reject_bucket(S)].append(rel)
        else:
            out[action].append(rel)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
