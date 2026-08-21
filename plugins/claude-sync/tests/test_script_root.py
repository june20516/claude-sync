"""SKILL.md 0단계의 플러그인 루트 해석 — 셸 파이프라인을 직접 실행해 검증한다.

실제 ~/.claude는 건드리지 않는다. HOME을 픽스처 트리로 바꿔 실행한다.
"""
import os
import subprocess

import pytest

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")

# SKILL.md 세 곳에 그대로 들어가는 파이프라인. 여기와 SKILL.md가 갈리면
# test_all_skills_use_new_pipeline이 잡는다.
PIPELINE = (
    'find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null '
    "| sed 's|/\\.claude-plugin$||' | sort -V | tail -1"
)


def make_home(tmp_path, cache_versions, with_marketplace=False):
    home = tmp_path / "home"
    for v in cache_versions:
        (home / ".claude" / "plugins" / "cache" / "claude-sync" / "claude-sync" / v
         / ".claude-plugin").mkdir(parents=True)
    if with_marketplace:
        (home / ".claude" / "plugins" / "marketplaces" / "claude-sync" / "plugins"
         / "claude-sync" / ".claude-plugin").mkdir(parents=True)
    return home


def run_pipeline(home):
    proc = subprocess.run(
        ["bash", "-c", PIPELINE],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_picks_highest_version_not_first_found(tmp_path):
    """head -1이었다면 파일시스템 순서라 임의 선택이 된다."""
    home = make_home(tmp_path, ["2.0.0", "3.0.0", "3.10.0"])
    assert run_pipeline(home).endswith("/claude-sync/claude-sync/3.10.0")


def test_sorts_numerically_not_lexically(tmp_path):
    """문자열 정렬이었다면 3.9.0이 3.10.0보다 뒤에 온다."""
    home = make_home(tmp_path, ["3.9.0", "3.10.0"])
    assert run_pipeline(home).endswith("/3.10.0")


def test_excludes_marketplace_clone(tmp_path):
    """marketplaces/ 아래는 레포 클론이지 설치본이 아니다."""
    home = make_home(tmp_path, ["3.0.0"], with_marketplace=True)
    result = run_pipeline(home)
    assert "/marketplaces/" not in result
    assert result.endswith("/cache/claude-sync/claude-sync/3.0.0")


def test_empty_when_nothing_installed(tmp_path):
    """SKILL.md가 중단할 수 있도록 빈 문자열을 낸다."""
    home = tmp_path / "empty"
    (home / ".claude").mkdir(parents=True)
    assert run_pipeline(home) == ""


@pytest.mark.parametrize("skill", ["sync-backup", "sync-status", "sync-restore"])
def test_all_skills_use_new_pipeline(skill):
    """세 SKILL.md가 같은 파이프라인을 쓴다. 한 곳만 고치고 잊는 것을 막는다."""
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    assert "plugins/cache" in text
    assert "sort -V" in text
    assert "SYNC_ROOT" in text


@pytest.mark.parametrize("skill", ["sync-backup", "sync-status", "sync-restore"])
def test_no_skill_uses_old_pattern(skill):
    """옛 패턴은 임의의 버전을 고른다. 남아 있으면 안 된다."""
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    assert 'find ~/.claude -path' not in text


@pytest.mark.parametrize("skill", ["sync-backup", "sync-status", "sync-restore"])
def test_all_skills_check_empty_root_before_using_it(skill):
    """빈 SYNC_ROOT로 python3를 부르면 '/.claude-plugin/plugin.json'을 열려다 죽는다.

    진짜 원인('플러그인을 못 찾았다')이 트레이스백에 가려진다.
    """
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    assert '[ -z "$SYNC_ROOT" ]' in text
    assert text.index('[ -z "$SYNC_ROOT" ]') < text.index("Plugin root:")
