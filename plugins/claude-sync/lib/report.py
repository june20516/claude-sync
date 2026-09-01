#!/usr/bin/env python3
"""보고 층 — 여섯 스크립트가 공유하는 **출력 모양** 한 벌.

**코어(`keyed_sync`)에 넣지 않는다.** 코어는 값 무관 판정이고 여기는 사용자에게 보이는
형태다. 섞으면 판정이 보고 형식 변경에 끌려다니고, 그 반대로 보고를 고치려다 판정을
건드리게 된다. 그렇다고 스크립트마다 두면 **같은 모양이 축자로 복제된다** — 실제로
`collect_mcp.py`와 `collect_plugins.py`에 `conflicts`·`repo_ahead` 분할이 변수 이름만
다른 채 두 벌 있었다(plan ③ Task 11).

**소비자는 세 SKILL.md다.** 그쪽이 이 모양을 읽어 사용자에게 문장을 만든다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keyed_sync as ks  # noqa: E402

# skipped의 **갈래**. 구체적인 것부터 본다 — OSError·ValueError가 넓어서 뒤에 둔다.
#
# **왜 필요한가.** 앞 판은 `reason` 문장 하나만 실었고 세 SKILL.md가 그 **한국어 부분
# 문자열**로 분기했다(*"구문이 깨졌다"*·*"형식을 알아볼 수 없다"*). 문구를 다듬는 편집이
# 스킬의 경로를 **조용히** 바꾼다 — 예외도 빈 결과도 나지 않고, 사용자는 틀린 처방을 받는다
# (구문 깨짐에 "플러그인을 업데이트하세요"는 소용이 없다). 판정은 이 값이 하고 `reason`
# 문장은 **표시만** 한다.
_KINDS = (
    (ks.BrokenBackupSyntax, "broken_syntax"),
    (ks.UnknownBackupSchema, "unknown_schema"),
    (ks.LocalConfigUnavailable, "local_unreadable"),
    (OSError, "io_error"),
    (ValueError, "contract_violation"),
)

# 여섯 스크립트의 `except` 튜플이 잡는 것 전부. 이 목록과 그 튜플이 갈리면 어떤 예외가
# `"unknown"` 갈래로 떨어지는데, 그 갈래에는 SKILL.md의 처방이 없다.
REASON_KINDS = tuple(kind for _, kind in _KINDS)


def reason_kind(exc):
    """예외 하나의 갈래. 목록 밖이면 `"unknown"`.

    **`"unknown"`을 조용히 다른 갈래로 접지 않는다** — 모르는 갈래에 아는 처방을 붙이면
    그것이 곧 이 필드가 없애려던 결함이다. SKILL.md는 그 값에 대해 `reason` 문장만 보인다.
    """
    for cls, kind in _KINDS:
        if isinstance(exc, cls):
            return kind
    return "unknown"


def skipped(exc):
    """문서 단위 skip의 표준 출력.

    `reason`은 사람이 읽는 문장이고 `reason_kind`가 **판정용**이다. 둘을 맞바꿔 쓰면
    (문장으로 분기, 갈래를 표시) 이 함수가 존재할 이유가 사라진다.
    """
    return {"status": "skipped", "reason": str(exc), "reason_kind": reason_kind(exc)}


def split_conflicts(keys, merged):
    """`conflicts`를 레포에 남은 것과 사라진 것으로 가른다.

    사용자가 할 일이 둘에서 다르다 — `repo_kept`는 이번 백업이 레포 값을 유지했다는
    뜻이고, `repo_absent`는 그 키가 레포에서 사라졌다는 뜻이다.
    """
    return {"repo_kept": [k for k in keys if k in merged],
            "repo_absent": [k for k in keys if k not in merged]}


def split_repo_ahead(keys, local):
    """`repo_ahead`를 로컬에 값이 있는 것과 없는 것으로 가른다.

    `absent`는 "레포 값을 보존합니다"가 참인 쪽이다(spec 8.4).
    """
    return {"present": [k for k in keys if k in local],
            "absent": [k for k in keys if k not in local]}
