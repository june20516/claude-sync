#!/usr/bin/env python3
"""복원(pull) 방향 파일별 판정 + 비대화 적용.

사용:
  reconcile_restore.py <repo_path> [--apply]
    분류: skip|add|overwrite|keep|merge
    --apply 시 비대화 동작(add/overwrite/clean-merge/skip)을 수행하고 base를 갱신한다.
    merge 중 git merge-file이 충돌(>0)이거나 base가 없으면 적용하지 않고 conflicts에 남긴다.
    JSON 출력: {"applied":{...}, "conflicts":[{rel, reason, has_base}], "local_ahead":[...]}

  reconcile_restore.py --set-base-from <source_root> <rel> [<rel> ...]
    source_root/<rel>을 읽어 base 블롭을 기록한다. 충돌 해소 후 base←repo 갱신에 사용.
    rel별로 FileNotFoundError를 허용하고(stderr 경고 후 계속) 나머지를 처리한다.

**로컬 쓰기는 원자적이다.** `add`/`overwrite` 갈래와 clean `merge` 갈래 둘 다
`ks.dump_bytes`를 거친다(같은 디렉토리의 `.tmp`에 쓰고 `os.replace`). 직접
`open(local, "wb")`하면 선-truncate가 일어나 쓰기 도중 실패가 로컬 파일을 **잘린 채**
남기는데, 그때 예외가 traceback으로 서서 `write_base`가 실행되지 않아 base는 옛 값
그대로다. 다음 판정이 `L≠S, R==S` → `local_ahead`가 되어 **다음 백업이 잘린 로컬을
레포의 온전한 사본 위에 push한다** — 손실이 모든 기기로 퍼진다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import keyed_sync as ks  # noqa: E402
import sync_state as ss  # noqa: E402


def apply_set_base_from(source_root, rels, base_dir=ss.BASE_DIR):
    """각 rel에 대해 source_root/<rel> 내용을 base로 기록한다.

    FileNotFoundError 발생 시 stderr에 경고하고 계속한다.
    테스트에서 base_dir를 주입할 수 있도록 키워드 인자를 제공한다.
    """
    for rel in rels:
        path = os.path.join(source_root, rel)
        try:
            with open(path, "rb") as f:
                data = f.read()
            ss.write_base(rel, data, base_dir=base_dir)
        except FileNotFoundError:
            print(
                "경고: base 갱신 건너뜀 — 파일 없음: %s" % path,
                file=sys.stderr,
            )


def main():
    args = sys.argv[1:]

    # --set-base-from 모드
    if args and args[0] == "--set-base-from":
        if len(args) < 3:
            print(
                "사용법: reconcile_restore.py --set-base-from <source_root> <rel> [<rel> ...]",
                file=sys.stderr,
            )
            sys.exit(1)
        source_root = args[1]
        rels = args[2:]
        apply_set_base_from(source_root, rels)
        return

    # 일반 모드: <repo_path> [--apply]
    if not args:
        print("사용법: reconcile_restore.py <repo_path> [--apply]", file=sys.stderr)
        sys.exit(1)

    repo_path = args[0]
    apply = "--apply" in args[1:]
    home = os.path.expanduser("~/.claude")
    rels = sorted(set(ss.iter_synced_relpaths(repo_path)) | set(ss.iter_synced_relpaths(home)))
    result = {"applied": {}, "conflicts": [], "local_ahead": []}

    for rel in rels:
        local = os.path.join(home, rel)
        repo = os.path.join(repo_path, rel)
        L = ss.file_hash(local)
        R = ss.file_hash(repo)
        S = ss.base_hash(rel)
        action = ss.restore_action(L, R, S, L is not None, R is not None)

        if action == "keep":
            if L is not None and R is not None and L != R:
                result["local_ahead"].append(rel)
            continue

        if action == "skip":
            if apply and R is not None:
                with open(repo, "rb") as f:
                    ss.write_base(rel, f.read())
            result["applied"].setdefault("skip", []).append(rel)
            continue

        if action in ("add", "overwrite"):
            if apply:
                with open(repo, "rb") as f:
                    repo_bytes = f.read()
                os.makedirs(os.path.dirname(local), exist_ok=True)
                ks.dump_bytes(repo_bytes, local)
                ss.write_base(rel, repo_bytes)
            result["applied"].setdefault(action, []).append(rel)
            continue

        if action == "merge":
            base_bytes = ss.read_base(rel)
            if base_bytes is None:
                result["conflicts"].append({"rel": rel, "reason": "no_base", "has_base": False})
                continue
            with open(local, "rb") as f:
                lb = f.read()
            with open(repo, "rb") as f:
                rb_bytes = f.read()
            merged, nconf = ss.three_way_merge(lb, base_bytes, rb_bytes)
            if nconf == 0:
                if apply:
                    ks.dump_bytes(merged, local)
                    ss.write_base(rel, rb_bytes)
                result["applied"].setdefault("auto_merge", []).append(rel)
            else:
                result["conflicts"].append({"rel": rel, "reason": "overlap", "has_base": True})

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
