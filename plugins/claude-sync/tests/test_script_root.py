"""SKILL.md 0단계의 플러그인 루트 해석.

**사본을 검사하지 않는다. SKILL.md에서 블록을 꺼내 실제로 실행한다.**
사본 기반 검사는 가짜 안전망이었다 — 실측으로, sort -V | tail -1을 head -1로 바꾼
트리에서도 검사 13개가 전부 통과했다. head -1은 임의의 버전을 고르는,
이 작업이 없애려던 바로 그 동작이다.

**블록을 실행하는 것만으로는 부족하다.** `head -1`은 find의 첫 출력을 고르고 그 순서는
파일시스템이 정한다. 최고 버전이 우연히 맨 앞에 오는 픽스처에서는 실행 기반 검사도
두 동작을 구별하지 못한다 — 실측으로 정확히 그 상태였고, 그때 이 docstring은 구멍이
닫혔다고 적고 있었다. 그래서 VERSIONS는 세 가지를 동시에 만족하도록 고른다.

- 숫자 최대(`12.0.0`)가 find의 첫 출력이 아니다      -> `head -1`을 잡는다
- 숫자 최대가 사전순 최대가 아니다(사전순은 `3.9.0`) -> `sort`(비-V)를 잡는다
- `3.9.0`/`3.10.0`이 함께 있다                        -> 자릿수 비교를 잡는다

이 조건이 유지되는지는 test_fixture_distinguishes_sort_v_from_head가 매번 확인한다.
깨지면 픽스처가 무의미해진 것이므로 VERSIONS를 바꾼다.

실제 ~/.claude는 건드리지 않는다. HOME을 픽스처 트리로 바꿔 실행한다.

**이 파일은 SKILL.md를 실행해서 잰다.** 읽어서 재는 쪽 — 세 SKILL.md의 배선 계약 —
은 `test_skill_wiring.py`에 있다. 한 파일에 있던 그 둘을 갈랐고, 분량으로는 그쪽이
훨씬 크다. 두 파일이 함께 쓰는 `SKILLS_DIR`·`SKILLS`는 `skill_paths.py` 한 곳에 있다.

**사용자 문서(README·backup-readme)는 `test_user_docs.py`에 있다** — 스킬도 스크립트도
아니어서 이 파일에도 배선 계약 파일에도 속하지 않는다.
"""
import os
import re
import subprocess

import pytest

from skill_paths import SKILLS, SKILLS_DIR   # 목록은 한 벌이다 — 그 파일의 docstring 참조

# 모듈 docstring의 세 조건을 만족하는 조합이다. 손대기 전에 그 설명을 읽을 것.
VERSIONS = ["2.0.0", "3.0.0", "3.9.0", "3.10.0", "12.0.0"]
HIGHEST = "/12.0.0"
SORT_PIPE = "| sort -V | tail -1 |"


def step0_block(skill):
    """SKILL.md의 0단계 bash 블록을 파일에서 그대로 꺼낸다."""
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    i = text.index("### 0. 플러그인 루트 확인")
    m = re.search(r"```bash\n(.*?)```", text[i:], re.S)
    assert m, "0단계에 bash 블록이 없다: %s" % skill
    return m.group(1)


def run_step0(skill, home, block=None):
    return subprocess.run(
        ["bash", "-c", step0_block(skill) if block is None else block],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )


def naive_head_block(skill):
    """0단계 블록에서 정렬만 `head -1`로 바꾼 변종. 픽스처 판별력 확인 전용이다."""
    block = step0_block(skill)
    naive = block.replace(SORT_PIPE, "| head -1 |")
    assert naive != block, (
        "0단계 파이프라인에서 %r를 찾지 못했다 — 이 변종이 더는 유효하지 않다: %s"
        % (SORT_PIPE, skill)
    )
    return naive


def picked_root(proc):
    for line in proc.stdout.splitlines():
        if line.startswith("Plugin root:"):
            return line.split(":", 1)[1].strip()
    return None


def make_home(tmp_path, versions, marketplace="claude-sync", extra=None,
              with_clone=False):
    """캐시 픽스처. extra는 (마켓플레이스, 버전) 목록."""
    home = tmp_path / "home"
    for v in versions:
        (home / ".claude" / "plugins" / "cache" / marketplace / "claude-sync" / v
         / ".claude-plugin").mkdir(parents=True)
    for mk, v in (extra or []):
        (home / ".claude" / "plugins" / "cache" / mk / "claude-sync" / v
         / ".claude-plugin").mkdir(parents=True)
    if with_clone:
        clone = (home / ".claude" / "plugins" / "marketplaces" / "claude-sync"
                 / "plugins" / "claude-sync")
        # 실제 클론의 모양: 버전 디렉토리가 없다.
        (clone / ".claude-plugin").mkdir(parents=True)
        # 판별력 있는 미끼. 실제 클론에는 없는 모양이지만, 이것이 없으면 semver 필터가
        # 혼자 클론을 걸러내므로 `plugins/cache` 한정이 일을 하는지 알 수 없다.
        # 실측으로, 이 미끼 없이는 `cache` 한정을 지워도 검사가 전부 통과했다.
        (clone / "99.0.0" / ".claude-plugin").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return home


@pytest.mark.parametrize("skill", SKILLS)
def test_picks_highest_version(tmp_path, skill):
    """숫자로 가장 높은 것을 고른다. head -1도 사전순 정렬도 여기서 걸린다."""
    home = make_home(tmp_path, VERSIONS)
    assert picked_root(run_step0(skill, home)).endswith(HIGHEST)


@pytest.mark.parametrize("skill", SKILLS)
def test_fixture_distinguishes_sort_v_from_head(tmp_path, skill):
    """픽스처가 `sort -V | tail -1`과 `head -1`을 실제로 구별하는가.

    구별하지 못하면 test_picks_highest_version은 통과하면서 아무것도 지키지 않는다.
    실측으로 그런 상태였다(모듈 docstring 참조). 이 테스트가 깨졌다는 것은 위 테스트가
    무의미해졌다는 뜻이므로, 실패를 무시하지 말고 VERSIONS를 바꿔라.
    """
    home = make_home(tmp_path, VERSIONS)
    naive = picked_root(run_step0(skill, home, block=naive_head_block(skill)))
    assert naive is not None, "변종이 아무것도 고르지 못했다 — 픽스처가 깨졌다"
    assert not naive.endswith(HIGHEST), (
        "픽스처가 판별력을 잃었다 — head -1도 %s를 고른다. VERSIONS를 바꿔라." % HIGHEST
    )


@pytest.mark.parametrize("skill", SKILLS)
def test_ignores_non_semver_directory(tmp_path, skill):
    """'unknown'은 sort -V에서 릴리즈를 이긴다. 이 기기에 실재하는 디렉토리 이름이다."""
    home = make_home(tmp_path, ["3.0.0", "unknown", "latest"])
    assert picked_root(run_step0(skill, home)).endswith("/3.0.0")


@pytest.mark.parametrize("skill", SKILLS)
def test_ignores_prerelease_directory(tmp_path, skill):
    """semver에서 rc는 정식 릴리즈보다 낮은데 sort -V는 반대로 본다."""
    home = make_home(tmp_path, ["3.0.0", "3.1.0-rc1"])
    assert picked_root(run_step0(skill, home)).endswith("/3.0.0")


@pytest.mark.parametrize("skill", SKILLS)
def test_marketplace_name_does_not_decide(tmp_path, skill):
    """경로 전체로 정렬하면 이름이 뒤인 마켓플레이스의 낮은 버전이 이긴다."""
    home = make_home(tmp_path, [], marketplace="a-market",
                     extra=[("a-market", "3.0.0"), ("z-market", "2.0.0")])
    assert picked_root(run_step0(skill, home)).endswith("/3.0.0")


@pytest.mark.parametrize("skill", SKILLS)
def test_excludes_marketplace_clone(tmp_path, skill):
    """marketplaces/ 아래는 레포 클론이지 설치본이 아니다.

    픽스처의 클론에는 `99.0.0`이 있다. `plugins/cache` 한정이 없으면 그것이 이긴다.
    """
    home = make_home(tmp_path, ["3.0.0"], with_clone=True)
    root = picked_root(run_step0(skill, home))
    assert "/marketplaces/" not in root
    assert "99.0.0" not in root
    assert root.endswith("/cache/claude-sync/claude-sync/3.0.0")


@pytest.mark.parametrize("skill", SKILLS)
def test_fails_loudly_when_nothing_installed(tmp_path, skill):
    """판정 불가가 '문제 없음'과 같은 모양이면 안 된다 — 비-0으로 끝나야 한다."""
    home = tmp_path / "empty"
    (home / ".claude").mkdir(parents=True)
    proc = run_step0(skill, home)
    assert proc.returncode != 0
    assert "찾지 못했습니다" in proc.stderr
    assert "Plugin root:" not in proc.stdout


@pytest.mark.parametrize("skill", SKILLS)
def test_no_skill_uses_old_pattern(skill):
    """옛 패턴은 임의의 버전을 고른다. 남아 있으면 안 된다."""
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    assert "find ~/.claude -path" not in text
