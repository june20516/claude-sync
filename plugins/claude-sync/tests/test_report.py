"""보고 층(`lib/report.py`)의 계약.

**이 파일이 따로 있는 이유.** 보고 층은 여섯 스크립트가 공유하는 출력 모양이고 어느
어댑터에도 속하지 않는다 — `test_plugin_scripts.py`·`test_mcp_scripts.py` 어느 쪽에 넣어도
"그 어댑터의 계약"으로 읽히는데, 이 모듈의 요지는 **둘이 같은 모양을 쓴다**는 것이다.
"""
import builtins
import os
import re

import pytest

import keyed_sync as ks   # conftest.py가 lib를 sys.path에 넣는다
import report

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")

# `report.skipped`를 쓰는 여섯 스크립트. **손으로 고른 목록이지만 아래 첫 테스트가
# 디스크와 대조한다** — 스크립트가 늘면 그 목록이 조용히 좁아지는 것을 막는다.
SKIPPED_USERS = (
    "sync-backup/scripts/collect_mcp.py",
    "sync-backup/scripts/collect_plugins.py",
    "sync-backup/scripts/prune_mcp.py",
    "sync-restore/scripts/plan_mcp.py",
    "sync-restore/scripts/plan_plugins.py",
    "sync-status/scripts/compare_mcp.py",
    "sync-status/scripts/compare_plugins.py",
)

# except와 호출 사이에 주석 줄이 끼는 파일이 있다(collect_plugins·compare_plugins).
EXCEPT_TUPLE = re.compile(
    r"except \(([^)]*)\) as e:\n(?:[ \t]*#[^\n]*\n)*[ \t]*out = report\.skipped\(e\)", re.S)


def script_path(rel):
    return os.path.join(SKILLS_DIR, *rel.split("/"))


def test_the_script_list_matches_what_actually_calls_report_skipped():
    """목록이 디스크와 어긋나면 아래 가드가 그만큼 좁아진다 — 조용히.

    **`report.skipped(e)`를 부르는 파일을 직접 훑는다.** 새 스크립트가 그 함수를 쓰기
    시작했는데 목록에 없으면 그 파일의 except 튜플이 아래 검사에서 통째로 빠진다.
    """
    found = set()
    for skill in sorted(os.listdir(SKILLS_DIR)):
        scripts = os.path.join(SKILLS_DIR, skill, "scripts")
        if not os.path.isdir(scripts):
            continue
        for name in sorted(os.listdir(scripts)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(scripts, name), encoding="utf-8") as f:
                if "report.skipped(" in f.read():
                    found.add("%s/scripts/%s" % (skill, name))
    assert found == set(SKIPPED_USERS), sorted(found.symmetric_difference(SKIPPED_USERS))


def resolve(name):
    """`pc.LocalConfigUnavailable` 같은 이름을 실제 클래스로. 어댑터는 코어를 재수출한다."""
    leaf = name.strip().split(".")[-1]
    return getattr(ks, leaf, None) or getattr(builtins, leaf, None)


@pytest.mark.parametrize("rel", SKIPPED_USERS)
def test_every_exception_the_scripts_catch_has_a_kind(rel):
    """스크립트가 잡는 예외는 **전부** 갈래를 받아야 한다.

    받지 못하면 `"unknown"`으로 떨어지는데 그 값에는 SKILL.md의 처방이 없다 — 그 갈래는
    `reason` 문장만 보인다. 새 예외를 except 튜플에 더하면서 `_KINDS`를 잊는 순간 그
    상태가 되고, **아무 테스트도 실패하지 않는다**(그래서 이 단정이 있다).
    """
    with open(script_path(rel), encoding="utf-8") as f:
        src = f.read()
    m = EXCEPT_TUPLE.search(src)
    assert m, "%s에서 report.skipped를 부르는 except 튜플을 찾지 못했다" % rel
    names = [n for n in m.group(1).replace("\n", " ").split(",") if n.strip()]
    assert len(names) >= 2, names
    for name in names:
        cls = resolve(name)
        assert cls is not None, (rel, name)
        assert report.reason_kind(cls("x")) != "unknown", (rel, name)


def test_an_exception_outside_the_table_gets_its_own_kind():
    """목록 밖 예외는 `"unknown"`이다 — **아는 갈래로 접지 않는다.**

    접으면 그 예외에 틀린 처방이 붙는다(구문 깨짐에 *"플러그인을 업데이트하세요"* 는
    소용이 없다). 오늘 여섯 스크립트의 튜플로는 도달하지 않지만, 위 단정이 지키는 것이
    바로 "도달하게 되는 날"이다 — 그때 조용히 틀린 처방이 나가지 않게 한다.
    """
    assert report.reason_kind(KeyError("x")) == "unknown"
    assert "unknown" not in report.REASON_KINDS


def test_skipped_puts_the_sentence_and_the_kind_in_their_own_fields():
    """문장은 `reason`, 판정은 `reason_kind`. 맞바꾸면 이 모듈이 존재할 이유가 사라진다."""
    out = report.skipped(ks.BrokenBackupSyntax("레포 문서의 구문이 깨졌다"))
    assert out == {"status": "skipped",
                   "reason": "레포 문서의 구문이 깨졌다",
                   "reason_kind": "broken_syntax"}


@pytest.mark.parametrize("keys,merged,expected", [
    (["a", "b"], {"a": 1}, {"repo_kept": ["a"], "repo_absent": ["b"]}),
    ([], {}, {"repo_kept": [], "repo_absent": []}),
])
def test_split_conflicts(keys, merged, expected):
    assert report.split_conflicts(keys, merged) == expected


@pytest.mark.parametrize("keys,local,expected", [
    (["a", "b"], {"b": 1}, {"present": ["b"], "absent": ["a"]}),
    ([], {}, {"present": [], "absent": []}),
])
def test_split_repo_ahead(keys, local, expected):
    assert report.split_repo_ahead(keys, local) == expected
