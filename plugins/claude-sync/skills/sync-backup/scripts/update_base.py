#!/usr/bin/env python3
"""push된 파일과 in_sync 파일의 base를 로컬 내용으로 갱신한다.

사용: update_base.py <source_root> <rel> [<rel> ...]
  source_root: 로컬 기준 루트 (예: ~/.claude)
  rel...: 갱신할 파일들의 상대 경로

레포가 이번 결과와 정합한 뒤(푸시 성공, 또는 커밋할 변경 없음) SKILL.md 10단계에서
호출한다. 핵심 계약:
  push된 파일과 in_sync 파일의 base ← 로컬 내용 (다음 sync의 merge-base)

`in_sync`가 대상인 이유는 로컬 == 레포이므로 base ← 로컬이 곧 base ← 레포이기
때문이다. 이것을 빼면 백업만 하는 기기에는 파일 기준선이 영영 생기지 않고, 기준선
없는 파일이 매번 `reject.no_base`로 뜬다(spec 3.2).
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402


def update_base_for_pushed(source_root, rels):
    """각 rel 파일의 base를 source_root/<rel>의 내용으로 갱신한다."""
    for rel in rels:
        path = os.path.join(source_root, rel)
        try:
            with open(path, "rb") as f:
                ss.write_base(rel, f.read())
        except FileNotFoundError:
            print("경고: %s 이(가) push 직후 사라짐, base 갱신 건너뜀" % rel, file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("사용: update_base.py <source_root> <rel> [<rel> ...]", file=sys.stderr)
        sys.exit(1)
    source_root = sys.argv[1]
    rels = sys.argv[2:]
    if not rels:
        return
    update_base_for_pushed(source_root, rels)


if __name__ == "__main__":
    main()
