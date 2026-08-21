"""SKILL.md 0단계의 플러그인 루트 해석.

**사본을 검사하지 않는다. SKILL.md에서 블록을 꺼내 실제로 실행한다.**
사본 기반 검사는 가짜 안전망이었다 — 실측으로, sort -V | tail -1을 head -1로 바꾼
트리에서도 검사 13개가 전부 통과했다. head -1은 가장 낮은 버전을 고르는,
이 작업이 없애려던 바로 그 동작이다.

실제 ~/.claude는 건드리지 않는다. HOME을 픽스처 트리로 바꿔 실행한다.
"""
import os
import re
import subprocess

import pytest

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
SKILLS = ["sync-backup", "sync-status", "sync-restore"]


def step0_block(skill):
    """SKILL.md의 0단계 bash 블록을 파일에서 그대로 꺼낸다."""
    with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    i = text.index("### 0. 플러그인 루트 확인")
    m = re.search(r"```bash\n(.*?)```", text[i:], re.S)
    assert m, "0단계에 bash 블록이 없다: %s" % skill
    return m.group(1)


def run_step0(skill, home):
    return subprocess.run(
        ["bash", "-c", step0_block(skill)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )


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
        (home / ".claude" / "plugins" / "marketplaces" / "claude-sync" / "plugins"
         / "claude-sync" / ".claude-plugin").mkdir(parents=True)
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return home


@pytest.mark.parametrize("skill", SKILLS)
def test_picks_highest_version(tmp_path, skill):
    """head -1이었다면 가장 낮은 버전을 고른다."""
    home = make_home(tmp_path, ["2.0.0", "3.0.0", "3.9.0", "3.10.0"])
    assert picked_root(run_step0(skill, home)).endswith("/3.10.0")


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
    """marketplaces/ 아래는 레포 클론이지 설치본이 아니다."""
    home = make_home(tmp_path, ["3.0.0"], with_clone=True)
    root = picked_root(run_step0(skill, home))
    assert "/marketplaces/" not in root
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


def read_skill(name):
    with open(os.path.join(SKILLS_DIR, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def test_backup_detects_downgrade_before_mcp_collection():
    """수집이 레포 파일을 덮어쓰면 v1 배열이라는 증거가 사라진다.

    실행 줄 전체를 앵커로 쓴다 — 파일명만 쓰면 다른 절의 산문에 등장하는
    같은 파일명이 순서를 우연히 맞춰 통과시킬 수 있다(불변식 7).
    """
    text = read_skill("sync-backup")
    assert text.index('detect_downgrade.py" "$SYNC_REPO"') < text.index(
        'collect_mcp.py" "$SYNC_REPO" "$MCP_STAGING"'
    )


def test_backup_documents_marker_fields():
    """세 필드 각각에 대한 설명 문장(백틱 표기)이 있는지 확인한다.

    필드 이름만 찾으면 같은 절 안의 JSON 예시(따옴표 표기)가 항상 걸려
    설명 문단이 통째로 지워져도 통과한다(불변식 7). 백틱으로 감싼 표기는
    JSON 예시가 아니라 산문 설명에만 나타난다.
    """
    sec = section("sync-backup", "7. sync-metadata.json 생성")
    for field in ("written_by_version", "min_reader_version", "schema"):
        assert "`%s`" % field in sec, field


def test_restore_surfaces_update_guidance_in_plugin_step():
    """버전이 낮아 막혔다면 필요한 것은 plugin update다. 여기가 탈출구다."""
    text = read_skill("sync-restore")
    plugin_step = text[text.index("### 5. 플러그인 복원"):text.index("### 6. MCP 서버 복원")]
    assert "claude plugin update claude-sync" in plugin_step


LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")


def section(skill, heading):
    """'### <heading>'부터 다음 '### '까지 잘라낸다.

    파일 전체에 대한 존재 검사는 절이 통째로 사라지거나 엉뚱한 곳으로 옮겨져도
    다른 곳의 한 마디에 가려 통과한다(불변식 7).
    """
    text = read_skill(skill)
    i = text.index("### " + heading)
    m = re.compile(r"\n### ").search(text, i + 1)
    return text[i:m.start() if m else len(text)]


def test_backup_compat_section_sits_right_after_repo_fetch():
    """레포를 가져온 직후, 아무것도 쓰기 전이어야 한다. 앞뒤를 둘 다 건다."""
    text = read_skill("sync-backup")
    assert (text.index("### 2. 레포 준비")
            < text.index("### 2.5 호환성 검사")
            < text.index("### 3. Git User 설정"))


def test_backup_runs_compat_before_any_repo_write():
    """앵커를 산문이 아니라 실행 줄로 잡는다 — 0단계 산문의 'compat.py'가 아니다."""
    text = read_skill("sync-backup")
    call = text.index('compat.py" "$SYNC_REPO"')
    for later in ("### 4. 파일별 reconcile", "extract_plugins.py",
                  "collect_mcp.py", "generate_metadata.py"):
        assert call < text.index(later), later


def test_backup_blocked_stops_the_run():
    sec = section("sync-backup", "2.5 호환성 검사")
    assert "여기서 중단한다" in sec
    assert "MCP 수집(6단계)도 하지 않는다" in sec


def test_status_never_stops_the_analysis():
    """status는 어떤 갈래에서도 멈추지 않는다 — 진단 수단이 사라지면 안 된다."""
    sec = section("sync-status", "1.5 호환성 검사")
    assert "분석은 계속한다" in sec
    assert "아래 분석은 계속 진행합니다" in sec
    assert "중단" not in sec


def test_status_reports_undetectable_downgrade():
    """'확인하지 못했다'와 '사고가 없다'는 다른 말이다(불변식 6)."""
    sec = section("sync-status", "1.5 호환성 검사")
    assert "확인하지 못했다" in sec
    assert "newer_schema_seen" in sec


def test_status_puts_version_mismatch_first():
    sec = section("sync-status", "3. 결과 요약")
    assert "첫 줄" in sec


def test_restore_asks_instead_of_deciding():
    sec = section("sync-restore", "2.5 호환성 검사")
    assert "계속할지 묻는다" in sec
    assert "부분 복원" in sec


def test_restore_branches_on_reason_for_upgrade_advice():
    """업그레이드로 풀리지 않는 갈래에 '업데이트하세요'를 붙이면 틀린 해법이다."""
    sec = section("sync-restore", "2.5 호환성 검사")
    assert "업데이트를 권하지 않는다" in sec


def test_restore_reports_version_skips_as_pending():
    sec = section("sync-restore", "7. 결과 보고")
    assert "보류" in sec


REASON_LITERAL = re.compile(r'(?:return|"reason":)\s*"([a-z_]+)"')


def test_backup_reason_table_covers_every_compat_reason():
    """문서의 분기표가 코드의 reason을 전부 덮는지 원본에서 뽑아 대조한다.

    손으로 옮겨 적어 비교하면 값이 늘어날 때 따라오지 못한다(불변식 7).
    """
    with open(os.path.join(LIB_DIR, "compat.py"), encoding="utf-8") as f:
        reasons = set(REASON_LITERAL.findall(f.read()))
    assert reasons, "compat.py에서 reason을 못 뽑았다 — 정규식이 낡았다"
    table = section("sync-backup", "2.5 호환성 검사")
    missing = sorted(r for r in reasons if r not in table)
    assert not missing, "2.5 분기표에 없는 reason: %s" % missing


def test_restore_reason_table_covers_every_compat_reason():
    """손으로 옮겨 적어 비교하면 값이 늘어날 때 따라오지 못한다(불변식 7).

    빠진 reason은 restore의 폴백으로 떨어져 '조용히 멈추는 갈래'가 된다.
    restore가 멈추면 안 된다는 것이 이 설계의 원칙이므로 놓치는 방향이 위험하다.
    """
    with open(os.path.join(LIB_DIR, "compat.py"), encoding="utf-8") as f:
        reasons = set(REASON_LITERAL.findall(f.read()))
    assert reasons, "compat.py에서 reason을 못 뽑았다 — 정규식이 낡았다"
    sec = section("sync-restore", "2.5 호환성 검사")
    missing = sorted(r for r in reasons if r not in sec)
    assert not missing, "restore 2.5에 없는 reason: %s" % missing


PAIRED = re.compile(
    r"claude plugin marketplace update claude-sync[ \n]*(?:&&\s*)?claude plugin update claude-sync")
LONE = re.compile(r"(?<!marketplace )claude plugin update claude-sync")


@pytest.mark.parametrize("skill", SKILLS)
def test_marketplace_update_always_precedes_plugin_update(skill):
    """마켓플레이스 갱신이 먼저여야 한다 — 갱신 없이 update만 하면 새 버전을 못 본다.

    등장 횟수만 세면 순서가 뒤바뀌어도 통과한다(불변식 7).
    """
    text = read_skill(skill)
    paired, lone = len(PAIRED.findall(text)), len(LONE.findall(text))
    assert paired == lone, (
        "%s: 짝지어진 %d회 vs plugin update %d회 — 순서가 뒤바뀌었거나 떨어져 있다"
        % (skill, paired, lone)
    )
