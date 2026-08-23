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
"""
import os
import re
import subprocess

import pytest

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
SKILLS = ["sync-backup", "sync-status", "sync-restore"]

# 모듈 docstring의 세 조건을 만족하는 조합이다. 손대기 전에 그 설명을 읽을 것.
VERSIONS = ["2.0.0", "3.0.0", "3.9.0", "3.10.0", "12.0.0"]
HIGHEST = "/12.0.0"
SORT_PIPE = "| sort -V | tail -1 |"

# restore의 검사 절은 두 방향(상위 버전 / 다운그레이드)을 다 다루므로 제목이 다르다.
RESTORE_CHECK_SECTION = "2.5 호환성·다운그레이드 검사"


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


def read_skill(name):
    with open(os.path.join(SKILLS_DIR, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


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


def subsection(skill, heading):
    """'#### <heading>'부터 다음 '#### ' 또는 '### '까지 잘라낸다."""
    text = read_skill(skill)
    i = text.index("#### " + heading)
    m = re.compile(r"\n#{3,4} ").search(text, i + 1)
    return text[i:m.start() if m else len(text)]


# 세 스킬이 호환성 검사를 부르는 유일한 형태. **셋이 같은 문자열을 쓰는 것 자체가 계약이다** —
# 스킬마다 제 나름의 호출을 만들면 경로·인자가 갈리고, 그것이 이 프로젝트가 없애려고 만든
# 드리프트다. 산문이 아니라 실행줄이라야 앵커가 된다(불변식 7).
COMPAT_CALL = 'python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"'

# 스킬별 배선. 세 스킬의 계약이 서로 다르므로(막는 대상도, 앞뒤 경계도) 표로 몬다.
# 한 스킬씩 손으로 쓰면 새 스킬이나 새 단계가 생겼을 때 한 곳만 고치고 만다.
#
# after_section  : 검사 절이 이 절보다 뒤에 있어야 한다 — 레포를 가져오기 전에는 판정할 것이 없다
# before_section : 검사 절이 이 절보다 앞에 있어야 한다 — 절이 뒤로 밀리는 것을 막는다
# before_calls   : 검사 호출이 이 실행줄들보다 앞에 있어야 한다. 검사가 막아야 할 것들이다
COMPAT_WIRING = {
    "sync-backup": {
        "section": "2.5 호환성 검사",
        "after_section": "### 2. 레포 준비",
        "before_section": "### 3. Git User 설정",
        "before_calls": (
            'python3 $SYNC_SCRIPTS/reconcile_backup.py "$SYNC_REPO"',
            "python3 $SYNC_SCRIPTS/extract_plugins.py plugins.json",
            'python3 "$SYNC_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$MCP_STAGING"',
            'python3 "$SYNC_SCRIPTS/generate_metadata.py" "$SYNC_REPO/sync-metadata.json"',
        ),
    },
    "sync-status": {
        "section": "1.5 호환성 검사",
        "after_section": "### 1. 설정 확인 및 레포 준비",
        "before_section": "### 2. 메타데이터 기반 상태 분석",
        "before_calls": (
            'python3 $SYNC_SCRIPTS/check_status.py "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"',
        ),
    },
    "sync-restore": {
        "section": RESTORE_CHECK_SECTION,
        "after_section": "### 2. 레포에서 최신 상태 가져오기",
        "before_section": "### 3. 파일별 reconcile",
        "before_calls": (
            'python3 "$SYNC_SCRIPTS/reconcile_restore.py" "$SYNC_REPO" --apply',
            'python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json"',
            'python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$MCP_STAGING" mcp-servers.json',
        ),
    },
}


def index_of(text, needle, skill):
    """needle의 위치. 없으면 무엇을 못 찾았는지 말하고 실패한다.

    text.index를 그대로 쓰면 ValueError가 나서 "어느 앵커가 낡았는지"가 안 보인다.
    """
    assert needle in text, "%s: 실행줄을 찾지 못했다 — 앵커가 낡았다: %r" % (skill, needle)
    return text.index(needle)


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_actually_runs_the_compatibility_check(skill):
    """세 스킬 모두 compat.py를 **실제로 실행**한다.

    절의 산문만 검사하면 절이 남은 채 호출줄만 사라져도 통과한다 — 실측으로, status와
    restore에서 이 한 줄을 지웠을 때 367개가 전부 통과했다. backup만 실행줄 앵커가
    있었고 나머지 둘은 "분석은 계속한다" 같은 문장만 보고 있었다(불변식 7).

    호출이 지정된 절 **안에** 있어야 한다. 파일 어딘가에 있기만 하면 되는 검사는
    호출이 엉뚱한 단계로 옮겨져도 통과한다.
    """
    text = read_skill(skill)
    count = text.count(COMPAT_CALL)
    assert count == 1, (
        "%s: 호환성 검사 호출이 %d번이다. 정확히 한 번이어야 한다 — %r"
        % (skill, count, COMPAT_CALL)
    )
    heading = COMPAT_WIRING[skill]["section"]
    assert COMPAT_CALL in section(skill, heading), (
        "%s: 호출이 '%s' 절 밖에 있다" % (skill, heading)
    )


@pytest.mark.parametrize("skill", SKILLS)
def test_compatibility_check_sits_between_its_boundaries(skill):
    """검사 절이 레포 준비 뒤, 그 결과를 쓰는 첫 단계 앞이어야 한다.

    앞뒤를 **둘 다** 건다. 한쪽만 걸면 절이 엉뚱한 위치에 있어도 통과한다.
    """
    text = read_skill(skill)
    w = COMPAT_WIRING[skill]
    here = index_of(text, "### " + w["section"], skill)
    assert index_of(text, w["after_section"], skill) < here, (
        "%s: 검사 절이 '%s'보다 앞이다 — 레포를 가져오기 전에는 판정할 것이 없다"
        % (skill, w["after_section"])
    )
    assert here < index_of(text, w["before_section"], skill), (
        "%s: 검사 절이 '%s'보다 뒤로 밀렸다" % (skill, w["before_section"])
    )


@pytest.mark.parametrize("skill", SKILLS)
def test_compatibility_check_precedes_everything_it_gates(skill):
    """검사 호출이, 검사가 막아야 할 모든 실행줄보다 앞이어야 한다.

    늦게 하면 이미 레포를 건드린 뒤다. backup은 레포를 되쓰고, restore는 모르는
    스키마의 항목을 건너뛴 부분 복원을 이미 진행한 뒤가 된다.
    """
    text = read_skill(skill)
    call = index_of(text, COMPAT_CALL, skill)
    for later in COMPAT_WIRING[skill]["before_calls"]:
        assert call < index_of(text, later, skill), (
            "%s: 호환성 검사가 %r보다 뒤에 있다" % (skill, later)
        )


# 다운그레이드 탐지는 **세 스킬 모두** 부른다.
# 부르는 경로가 스킬마다 다르므로($SYNC_SCRIPTS vs $SYNC_BACKUP_SCRIPTS) 공통 조각만 앵커로 쓴다.
#
# restore가 뒤늦게 합류했다. 브리프·스펙·계획이 모두 (c)를 backup·status 이야기로만 썼고
# 여섯 단계가 그대로 통과시켰는데, restore야말로 사고가 **마지막 피해**를 내는 자리다 —
# 되돌아간 레포에는 서버가 없고 base에는 있으므로 restore_plan이 그것을 local_stale로 넣고,
# 6-5가 "다른 기기가 삭제했습니다"라며 제거를 권한다. 그 서버의 마지막 사본이 로컬에 있는데도.
DOWNGRADE_CALL = 'detect_downgrade.py" "$SYNC_REPO"'
DOWNGRADE_CALLERS = SKILLS

# 탐지 호출이 있어야 할 절. 파일 어딘가면 되는 검사는 호출이 엉뚱한 단계로 옮겨져도
# 통과한다 — 실측으로, 호출을 MCP 계획 바로 앞으로 옮겼을 때 383개가 전부 통과했다.
DOWNGRADE_SECTION = {
    "sync-backup": "5.5 다운그레이드 사고 탐지",
    "sync-status": "1.5 호환성 검사",
    "sync-restore": RESTORE_CHECK_SECTION,
}


@pytest.mark.parametrize("skill", DOWNGRADE_CALLERS)
def test_downgrade_detection_is_actually_called(skill):
    """탐지 호출도 실행줄로 걸고, 지정된 절 안에 있는지까지 본다.

    실측으로, status에서 이 줄과 $SYNC_BACKUP_SCRIPTS 정의를 지웠을 때 367개가 전부
    통과했다. 절의 산문("확인하지 못했다", newer_schema_seen)은 그대로 남기 때문이다.
    """
    count = read_skill(skill).count(DOWNGRADE_CALL)
    assert count == 1, (
        "%s: 다운그레이드 탐지 호출이 %d번이다 — %r" % (skill, count, DOWNGRADE_CALL)
    )
    heading = DOWNGRADE_SECTION[skill]
    assert DOWNGRADE_CALL in section(skill, heading), (
        "%s: 탐지 호출이 '%s' 절 밖에 있다" % (skill, heading)
    )


# 탐지 호출이 반드시 앞서야 하는 실행줄.
#  - backup : 수집이 레포 파일을 v2로 덮어쓰면 "레포가 v1"이라는 증거가 사라진다
#  - restore: 6-5의 local_stale 안내 문구가 이 판정에 기대므로 그 앞이어야 한다
# status는 읽기 전용이라 순서가 결과를 바꾸지 않으므로 표에 없다.
DOWNGRADE_BEFORE = {
    "sync-backup": 'python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$MCP_STAGING"',
    "sync-restore": 'python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json"',
}


@pytest.mark.parametrize("skill", sorted(DOWNGRADE_BEFORE))
def test_downgrade_detection_precedes_what_it_informs(skill):
    """탐지가 그 결과를 쓰는 단계보다 앞이어야 한다.

    실행줄 전체를 앵커로 쓴다 — 파일명만 쓰면 다른 절의 산문에 등장하는
    같은 파일명이 순서를 우연히 맞춰 통과시킬 수 있다(불변식 7).
    """
    text = read_skill(skill)
    call = index_of(text, DOWNGRADE_CALL, skill)
    assert call < index_of(text, DOWNGRADE_BEFORE[skill], skill), (
        "%s: 다운그레이드 탐지가 %r보다 뒤에 있다" % (skill, DOWNGRADE_BEFORE[skill])
    )


@pytest.mark.parametrize("skill", ["sync-status", "sync-restore"])
def test_cross_skill_scripts_come_from_the_same_root(skill):
    """다른 스킬의 스크립트를 부를 때도 0단계의 SYNC_ROOT에서 유도해야 한다.

    별도 find로 찾으면 한 세션 안에서 서로 다른 버전의 스크립트가 섞인다 — 이 작업이
    없애려던 바로 그 결함이다(spec 1.2). status는 detect_downgrade.py를, restore는
    update_base.py를 sync-backup에서 가져온다.
    """
    sec = section(skill, "0. 플러그인 루트 확인")
    assert 'SYNC_BACKUP_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"' in sec


def test_every_skill_on_disk_is_covered_by_the_contract():
    """디스크에 있는 스킬이 계약을 조용히 빠져나가지 못하게 한다.

    SKILLS와 COMPAT_WIRING이 둘 다 손으로 쓴 목록이다. 넷째 스킬이 생겼는데 여기에
    안 적으면 위 검사들이 그 스킬을 아예 보지 않는다 — 통과하지만 아무것도 안 지킨다.
    새 스킬을 더할 때는 계약을 어떻게 할지 정하고 두 곳에 적어라.
    """
    on_disk = {
        d for d in os.listdir(SKILLS_DIR)
        if os.path.isfile(os.path.join(SKILLS_DIR, d, "SKILL.md"))
    }
    assert on_disk == set(SKILLS), "SKILLS가 디스크와 다르다: %s" % sorted(
        on_disk.symmetric_difference(SKILLS)
    )
    assert set(COMPAT_WIRING) == set(SKILLS), "COMPAT_WIRING이 SKILLS와 다르다: %s" % sorted(
        set(COMPAT_WIRING).symmetric_difference(SKILLS)
    )


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
    sec = section("sync-restore", RESTORE_CHECK_SECTION)
    assert "계속할지 묻는다" in sec
    assert "부분 복원" in sec


def test_restore_branches_on_reason_for_upgrade_advice():
    """업그레이드로 풀리지 않는 갈래에 '업데이트하세요'를 붙이면 틀린 해법이다."""
    sec = section("sync-restore", RESTORE_CHECK_SECTION)
    assert "업데이트를 권하지 않는다" in sec


def test_restore_reports_version_skips_as_pending():
    sec = section("sync-restore", "7. 결과 보고")
    assert "보류" in sec


def test_restore_reports_downgrade_and_points_at_the_writable_path():
    """restore는 push하지 않으므로 레포를 고칠 수 없다. 고칠 수 있는 경로로 보내야 한다.

    여기서 "복구했다"고 말하거나 복구를 실행하는 시늉을 하면, 사용자는 레포가
    나은 줄 알고 떠난다.
    """
    sub = subsection("sync-restore", "다운그레이드 탐지 결과")
    assert "downgrade_suspected" in sub
    assert "push하지 않으므로" in sub
    assert "/sync-backup" in sub
    # "확인하지 못했다"와 "사고가 없다"를 구별해 보고해야 한다(불변식 6).
    assert "reason" in sub


def test_restore_local_stale_does_not_claim_deletion_when_downgraded():
    """다운그레이드 의심 시 "다른 기기가 삭제했습니다"는 거짓이고, 제거로 이끈다.

    아무도 지우지 않았다. 낮은 버전 기기가 레포를 되돌리며 흘린 것이고, 그렇다면
    **로컬에 남은 값이 마지막 사본**이다. 여기서 제거를 권하면 이 릴리즈가 막으려는
    사고가 완성된다 — restore가 그 마지막 피해를 내는 자리다.

    기본 문구가 `downgrade_suspected` 분기 **뒤에** 와야 한다. 순서를 걸지 않으면
    분기를 지워도 문장이 남아 통과한다(불변식 7).
    """
    sub = subsection("sync-restore", "6-5. ")
    assert "downgrade_suspected" in sub, "6-5가 탐지 결과로 분기하지 않는다"
    guard = sub.index("`downgrade_suspected`가 거짓일 때")
    assert guard < sub.index("다른 기기가 이 서버를 삭제했습니다"), (
        "기본 문구가 분기보다 앞에 있다 — 분기를 지워도 통과한다"
    )
    # 절 전체에 대한 존재 검사는 안 된다 — 같은 표현이 표에도, 작성자용 설명문에도 있어
    # 정작 사용자에게 보일 문장이 지워져도 가려 준다. 실측으로 그렇게 세 갈래를
    # 놓쳤다(불변식 7). 갈래를 자르고, 그 안에서 다시 인용문만 자른다.
    true_branch = sub[sub.index("**`downgrade_suspected`가 참일 때**"):sub.index("| 선택 |")]

    # 사용자에게 실제로 보일 문구. 설명문이 아니라 이것이 행동을 바꾼다.
    quote = "\n".join(ln for ln in true_branch.splitlines() if ln.startswith("> "))
    assert quote, "다운그레이드 갈래에 사용자에게 보일 문구가 없다"
    assert "유실된 것으로 보입니다" in quote, "삭제가 아니라 유실이라고 말해야 한다"
    assert "마지막 사본" in quote, "로컬이 마지막 사본일 수 있다는 경고가 없다"

    assert "권하지 않는다" in true_branch, "제거를 권하지 않는다고 말해야 한다"

    # 표의 '제거' 행도 같은 말을 해야 한다. 산문과 표가 갈리면 표가 이긴다.
    table = sub[sub.index("| 선택 |"):]
    remove_row = next(ln for ln in table.splitlines() if ln.startswith("| **제거**"))
    assert "권하지 않는다" in remove_row, remove_row


def test_backup_notice_does_not_claim_older_devices_stop_themselves():
    """"낮은 버전 기기가 차단된다"고 쓰면 안 된다 — 오늘 존재하는 모든 낮은 버전에 거짓이다.

    차단 코드는 3.0.0에 처음 들어갔고 2.x에는 없다. min_reader_version이 항상
    {major}.0.0이므로 3.x끼리도 서로를 막지 않는다 — 그 문장이 참이 되는 기기 집합은
    4.0.0이 나오기 전까지 공집합이다(spec 8.4).

    문제는 부정확이 아니라 **행동을 바꾸는 거짓 안심**이다. 사용자가 이 문장을 읽는
    시점이 정확히 "다른 노트북을 지금 올릴 것인가"를 정하는 순간이다.
    """
    sec = section("sync-backup", "12. 결과 보고")
    assert "2.x 기기는 멈추지 않습니다" in sec
    assert "차단됩니다" not in sec
    assert "차단된다" not in sec


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
    sec = section("sync-restore", RESTORE_CHECK_SECTION)
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
