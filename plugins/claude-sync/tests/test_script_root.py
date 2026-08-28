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

**이 파일은 관심사를 둘 담는다.** 위 문단은 첫째(0단계 루트 해석, 아래 절반의 앞쪽)만
설명한다. 둘째는 **세 SKILL.md의 계약**이고 분량으로는 그쪽이 더 크다 —
호환성 검사의 위치와 그것이 앞서야 할 실행줄, 다운그레이드 탐지 순서, 공유 스테이징을
비우는 횟수와 순서, base 게이트의 두 축, restore 명령의 스코프 정책, 스킬이 스크립트의
어느 키를 읽는지를 적은 산문 앵커, `## 동기화 대상` 절이 말하는 추출 필드, 선택 결과
JSON의 스키마, 그리고 그 표들이 스스로 줄어드는 것을 막는 완전성 메타가드. 그 계약을
재려면 프로덕션 어댑터의 상수가 필요해서 이 파일은 `plugin_config`를 import한다
(선택 JSON의 섹션 이름, 보류 종류, 추출 필드 이름의 진실 원천).

첫째는 SKILL.md의 bash를 **실행해서** 재고, 둘째는 SKILL.md를 **읽어서** 잰다.
둘을 파일로 가르는 것이 다음 정리다.

**사용자 문서(README·backup-readme)는 여기가 아니라 `test_user_docs.py`에 있다** —
스킬도 스크립트도 아니어서 이 파일의 두 관심사 어느 쪽에도 속하지 않는다.
"""
import json
import os
import re
import subprocess

import pytest

import plugin_config as pc   # conftest.py가 lib를 sys.path에 넣는다

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


def sync_target_section():
    """sync-backup SKILL.md의 `## 동기화 대상` 절. section()은 `### `만 자른다."""
    text = read_skill("sync-backup")
    i = text.index("## 동기화 대상")
    m = re.compile(r"\n## ").search(text, i + 1)
    return text[i:m.start() if m else len(text)]


def sync_target_lines(table):
    """`## 동기화 대상` 절에서 settings.json을 말하는 줄. 표 행과 산문 문단을 가른다.

    **절 전체를 보면 안 된다.** 바로 아래 MCP 문단이 `<REDACTED>`를 이미 갖고 있어서,
    플러그인 쪽 문장이 `<MASKED>`로 **거짓이 되어도 절 단위 검사는 통과한다**(실측).
    `test_user_docs.py`가 "key by key"에서 쓴 것과 같은 처방 — **같은 줄에서 지목한다.**
    """
    lines = [line for line in sync_target_section().splitlines()
             if "settings.json" in line and line.startswith("|") == table]
    assert len(lines) == 1, "settings.json 줄을 하나로 특정하지 못했다: %d개" % len(lines)
    return lines[0]


# 추출 필드 수의 한국어 수사. `len(pc.SECTIONS)`가 바뀌면 문서가 따라와야 한다.
KOREAN_COUNT = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯"}


def test_backup_skill_lists_all_three_fields_and_the_auto_source():
    """`## 동기화 대상` 절 — "두 필드만 추출"·"통째로 덮어쓰인다"는 이제 거짓이다 (13장).

    이 절은 5단계의 배선과 **같은 파일 안에서** 자기모순이 될 수 있는 자리다. 5단계는
    세 섹션을 키 단위로 병합하는데 이 절만 두 필드를 말하면, 사용자와 다음 구현자가
    읽는 것은 앞머리 쪽이다.

    **토큰을 손으로 적지 않고 어댑터에서 뽑는다.** 상수로 두면 아무 문자열로 바꾸는
    것만으로 존재 단정이 통째로 공허해진다 — 이 파일이 FOREIGN_MCP_CALL에서 닫은
    성질이고, `not in` 가드는 애초에 바늘이 틀리면 초록이다.
    """
    sec = sync_target_section()
    para = sync_target_lines(table=False)
    for field in pc.SECTIONS:                    # 추출하는 세 필드 = 세 섹션
        assert "`%s`" % field in para, field
    for alias in pc.MARKETPLACE_ALIASES:         # 별칭 키도 읽는다는 사실
        assert "`%s`" % alias in para, alias
    # auto 플래그의 출처. 경로도 어댑터에서 뽑는다 — expanduser를 되돌려 문서 표기와 맞춘다.
    auto_source = pc.DEFAULT_INSTALLED.replace(os.path.expanduser("~"), "~", 1)
    assert auto_source.startswith("~/"), auto_source
    assert "`%s`" % auto_source in para, auto_source
    assert "`auto`" in para
    # 마스킹 값도 **같은 문단에서** 요구한다. 절 단위로 물으면 MCP 문단이 대신 충족시킨다.
    assert pc.SENTINEL in para, pc.SENTINEL

    # "두 필드만"의 **positive 대응**. 부재만 걸면 조사 하나("두 필드를 추출")로 옛
    # 서술이 되살아나도 통과한다(실측). 수사를 어댑터의 섹션 수에서 뽑아 짝짓는다.
    assert sorted(KOREAN_COUNT) == [1, 2, 3, 4, 5], sorted(KOREAN_COUNT)
    # **값도 건다.** 키만 잠그면 `2: "둘"`로 바꾸는 것만으로 negative 루프가
    # "둘 필드"를 찾게 되어 "두 필드를 추출" 회귀 방어가 조용히 사라진다(실측).
    assert set(KOREAN_COUNT.values()) == {"한", "두", "세", "네", "다섯"}
    want = len(pc.SECTIONS)
    assert want in KOREAN_COUNT, want
    assert "%s 필드" % KOREAN_COUNT[want] in para, KOREAN_COUNT[want]
    for n, word in KOREAN_COUNT.items():
        if n != want:
            assert "%s 필드" % word not in para, word
    assert "두 필드만" not in sec

    # 표 행(:33)도 같은 사실을 말해야 한다. 산문만 고치고 표를 두면 요약이 거짓으로 남는다.
    row = sync_target_lines(table=True)
    assert "설정 값은 마스킹" in row, row
    assert "목록만" not in row, row

    assert "통째로 새로 생성되어 덮어쓰" not in sec
    # 정정 문안 쪽도 함께 건다 — 부재만 보는 검사는 문단이 통째로 지워져도 초록이다.
    assert "`plugins.json`도 **섹션별 키 단위 3-way 병합** 대상이다" in sec


def test_backup_documents_marker_fields():
    """세 필드 각각에 대한 설명 문장(백틱 표기)이 있는지 확인한다.

    필드 이름만 찾으면 같은 절 안의 JSON 예시(따옴표 표기)가 항상 걸려
    설명 문단이 통째로 지워져도 통과한다(불변식 7). 백틱으로 감싼 표기는
    JSON 예시가 아니라 산문 설명에만 나타난다.
    """
    sec = section("sync-backup", "7. sync-metadata.json 생성")
    for field in ("written_by_version", "min_reader_version", "schema"):
        assert "`%s`" % field in sec, field


def plugin_restore_section():
    """restore의 플러그인 절. **제목의 접두를 바꾸면 여기서 ValueError로 죽는다.**

    절 하나를 두 곳에서 자르면 한쪽만 갱신돼 서로 다른 범위를 보게 된다 — 이 파일의
    검사들이 전부 "절 안에 있는가"를 묻는 형태이므로 그 어긋남은 조용하다.
    """
    text = read_skill("sync-restore")
    return text[text.index("### 5. 플러그인 복원"):text.index("### 6. MCP 서버 복원")]


# bash 블록 추출은 **한 벌이다.** 본문만 필요한 곳과 위치까지 필요한 곳이 서로 다른
# 구현을 쓰면 경계 규칙이 미세하게 갈리고, 그 어긋남은 조용하다 — 이 저장소가 없애려던
# "파서 두 벌"의 테스트 층 판이다.
BASH_BLOCK = re.compile(r"```bash\n(.*?)```", re.S)


def bash_blocks(text):
    """```bash 블록의 본문만 모은다 — 산문의 언급과 실행줄을 가른다."""
    return [m.group(1) for m in BASH_BLOCK.finditer(text)]


def test_restore_surfaces_update_guidance_in_plugin_step():
    """버전이 낮아 막혔다면 필요한 것은 plugin update다. 여기가 탈출구다.

    **bash 블록 안에서 찾는다.** 절 전체에서 찾으면 같은 문구를 쓴 산문 한 줄이
    블록을 대신 충족시켜, spec 12장이 보존하라고 지정한 실행 블록을 **통째로 지워도**
    통과한다 — 실측으로 정확히 그 상태였다(불변식 7).
    """
    assert any("claude plugin update claude-sync" in block
               for block in bash_blocks(plugin_restore_section()))


def status_plugin_section(text=None):
    """status 2단계의 **플러그인 반쪽**만 잘라낸다.

    그 절은 플러그인과 MCP를 함께 담으므로 절 전체를 보면 플러그인 쪽 문장이 MCP
    문단으로 옮겨져도 통과한다(실측). backup·restore의 플러그인 절은 제목으로 정확히
    잘리는데 status만 그렇지 않아 여기서 경계를 맞춘다.
    """
    text = read_skill("sync-status") if text is None else text
    start = text.index("파일 분석 이후, 플러그인과 MCP 서버 비교를 각각 수행한다:")
    return text[start:text.index("MCP 서버 비교:", start)]


# 세 스킬이 호환성 검사를 부르는 유일한 형태. **셋이 같은 문자열을 쓰는 것 자체가 계약이다** —
# 스킬마다 제 나름의 호출을 만들면 경로·인자가 갈리고, 그것이 이 프로젝트가 없애려고 만든
# 드리프트다. 산문이 아니라 실행줄이라야 앵커가 된다(불변식 7).
COMPAT_CALL = 'python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"'

# 두 수집 단계의 실행줄. 세 곳이 함께 쓰므로 상수로 묶는다 — 스테이징 순서 가드가
# COMPAT_WIRING의 **인덱스**를 딛으면, 표에서 항목 하나를 빼는 것만으로 그 가드가
# 엉뚱한 줄을 보게 되고 아무도 그것을 알아채지 못한다.
COLLECT_PLUGINS_CALL = 'python3 "$SYNC_SCRIPTS/collect_plugins.py" "$SYNC_REPO" "$BASE_STAGING"'
COLLECT_MCP_CALL = 'python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$BASE_STAGING"'

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
            # extract_plugins.py를 지우면서 **앵커를 지우지 않는다** — 이 항목은
            # "호환성 검사가 이 실행줄보다 앞에 있어야 한다"를 거는 자리다. 지우면
            # 새 호출이 아무 앵커도 없이 남고 2.5단계가 뒤로 밀려도 아무도 못 잡는다.
            # 표의 **축소**는 test_before_calls_covers_every_gated_script_call이 잡는다.
            # 그 단정이 없으면 항목을 지워도 스위트 전체가 통과했다(실측) — "각 항목마다
            # 검사"하는 맨 목록은 자기 축소를 탐지할 수 없고, 이 저장소가 그것을 푸는
            # 방식이 완전성 단정을 짝지어 두는 것이다(test_every_skill_on_disk_...와 같은 꼴).
            COLLECT_PLUGINS_CALL,
            'python3 "$SYNC_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"',
            COLLECT_MCP_CALL,
            'python3 "$SYNC_SCRIPTS/generate_metadata.py" "$SYNC_REPO/sync-metadata.json"',
            'python3 "$SYNC_SCRIPTS/update_base.py" "$HOME/.claude" "${PUSHED_RELS[@]}"',
            'python3 "$SYNC_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"',
        ),
    },
    "sync-status": {
        "section": "1.5 호환성 검사",
        "after_section": "### 1. 설정 확인 및 레포 준비",
        "before_section": "### 2. 메타데이터 기반 상태 분석",
        "before_calls": (
            'python3 "$SYNC_BACKUP_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"',
            'python3 $SYNC_SCRIPTS/check_status.py "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/compare_plugins.py" "$SYNC_REPO/plugins.json"',
            'python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"',
        ),
    },
    "sync-restore": {
        "section": RESTORE_CHECK_SECTION,
        "after_section": "### 2. 레포에서 최신 상태 가져오기",
        "before_section": "### 3. 파일별 reconcile",
        "before_calls": (
            'python3 "$SYNC_BACKUP_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/reconcile_restore.py" "$SYNC_REPO" --apply',
            'python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/plan_plugins.py" apply-base',
            'python3 "$SYNC_SCRIPTS/plan_mcp.py" apply-base',
            'python3 "$SYNC_SCRIPTS/plan_plugins.py" plan "$SYNC_REPO/plugins.json"',
            'python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json"',
            'python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"',
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
    restore에서 이 한 줄을 지웠을 때 스위트 전체가 통과했다. backup만 실행줄 앵커가
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
# 통과한다 — 실측으로, 호출을 MCP 계획 바로 앞으로 옮겼을 때 스위트 전체가 통과했다.
DOWNGRADE_SECTION = {
    "sync-backup": "4.5 다운그레이드 사고 탐지",
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
#  - backup : 수집이 레포 파일을 v2로 덮어쓰면 "레포가 옛 형식"이라는 증거가 사라진다.
#             **가장 앞선 수집 단계**를 앵커로 쓴다 — plan ③이 탐지를 plugins.json으로
#             넓히면 그 순서가 곧 정확도가 된다.
#  - restore: 6-5의 local_stale 안내 문구가 이 판정에 기대므로 그 앞이어야 한다
# status는 읽기 전용이라 순서가 결과를 바꾸지 않으므로 표에 없다.
DOWNGRADE_BEFORE = {
    "sync-backup": COLLECT_PLUGINS_CALL,
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

    표 셋(`SKILLS`·`COMPAT_WIRING`·`PLUGIN_STEP`)을 함께 걸므로 어느 위치에 두어도
    한쪽은 앞서 참조하게 된다. `PLUGIN_STEP`은 플러그인 단계 가드들과 함께 아래에 있다.
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
    # 같은 이유로 플러그인 단계 표도 함께 건다. 이 표에서 스킬 하나를 빼면 그 스킬은
    # 섹션 단위 status 검사를 아무 소리 없이 빠져나간다(실측 — 빼도 스위트 전체가 통과했다).
    assert set(PLUGIN_STEP) == set(SKILLS), "PLUGIN_STEP이 SKILLS와 다르다: %s" % sorted(
        set(PLUGIN_STEP).symmetric_difference(SKILLS)
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


def test_backup_reports_staging_failure_to_the_user():
    """spec 7.4는 "보고한다"고 썼다. 반환만 하고 아무도 읽지 않으면 보고가 아니다."""
    sec = section("sync-backup", "6. mcp-servers.json 생성 (키 단위 3-way 병합)")
    assert "`base_staging`" in sec
    assert "`base_staging_reason`" in sec
    # 필드 이름만 보면 문단이 통째로 지워져도 통과한다(불변식 7). 이 문단의 값어치는
    # "레포는 갱신됐지만"과 "skipped로 오해하지 않는다"라는 정반대 사실의 구별이다.
    assert "레포는 갱신됐지만" in sec and "오해하지 않는다" in sec


def test_backup_base_gate_cites_the_rename_contract_not_the_old_reason():
    """게이트가 참인 근거는 rename 계약이다 — "status=ok일 때만 쓴다"가 아니다.

    옛 근거는 거짓이었다: 수집 스크립트가 스테이징을 레포보다 먼저 썼으므로
    레포 쓰기가 실패해도 파일이 남았다. 근거를 갱신하지 않으면 다음 사람이
    그 문장을 믿고 rename을 지운다.
    """
    text = read_skill("sync-backup")
    assert "status=ok일 때만 쓰므로" not in text
    assert "rename" in section("sync-backup", "10. 커밋 & 푸시")


def test_backup_base_gate_distinguishes_push_failure_from_staging_failure():
    """세 경우를 하나의 근거("스테이징 파일이 없다")로 뭉개면 거짓이 된다.

    푸시 실패는 6단계가 끝난 뒤 일어나므로 그 시점에 스테이징 최종 파일은 이미
    존재한다 — 막는 것은 `-f` 검사가 아니라 REPO_HAS_CONTENT=0이다. 이 구별이
    지워지면 다음 사람이 REPO_HAS_CONTENT 조건을 중복으로 보고 지울 수 있다.
    """
    sec = section("sync-backup", "11. base(.sync-state) 갱신 규칙")
    assert "REPO_HAS_CONTENT=0" in sec and "이미 존재한다" in sec


# 두 수집 단계(backup)와 두 apply-base(restore)가 **같은 디렉토리**를 쓴다. 각 단계가
# 제 앞에서 비우면 앞 단계의 산출물이 지워지고 그 파일의 base가 영영 전진하지 않는다.
STAGING_CLEAR = 'rm -rf "$BASE_STAGING"'


def test_backup_clears_the_shared_staging_once_before_both_collectors():
    """7.4 — 각 단계가 제 앞에서 rm -rf하면 앞 단계의 산출물이 지워진다.

    횟수와 순서를 **둘 다** 건다. 순서만 걸면 6단계에 rm -rf를 하나 더 넣어도 통과하고,
    그때 플러그인 스테이징이 지워져 `base/plugins.json`이 영영 만들어지지 않는다.
    """
    text = read_skill("sync-backup")
    count = text.count(STAGING_CLEAR)
    assert count == 1, "스테이징 비우기가 %d번이다. 정확히 한 번이어야 한다" % count
    clear = index_of(text, STAGING_CLEAR, "sync-backup")
    for call in (COLLECT_PLUGINS_CALL, COLLECT_MCP_CALL):
        assert clear < index_of(text, call, "sync-backup"), (
            "스테이징 비우기가 %r보다 뒤에 있다" % call
        )


def test_backup_base_gate_covers_both_relpaths():
    """게이트가 한 파일에만 걸리면 MCP가 skipped인 실행에서 플러그인 base가 전진하지 않는다.

    그러면 merge가 매번 base=None 합집합 degrade를 타 케이스 3·4가 영영 발생하지 않고,
    삭제 전파가 **조용히** 죽는다(7.4).

    `"$BASE_STAGING"`까지 함께 거는 것은 source_root를 `"$SYNC_REPO"`로 바꾸는 오사용을
    이 자리에서 잡기 위해서다 — 그러면 base ← 레포 파일 바이트가 되어 다음 백업이
    타 기기의 플러그인을 경고 없이 지운다.
    """
    block = section("sync-backup", "10. 커밋 & 푸시")
    assert "for rel in plugins.json mcp-servers.json" in block
    assert '"$BASE_STAGING" "${RELS[@]}"' in block
    # 게이트의 **두 축**을 다 건다. 이 축을 빼면 푸시 실패 실행에서도 base가 전진해
    # spec 7.4가 막으려던 상태가 된다 — 파일 존재만으로는 그것을 막지 못한다.
    assert '[ "$REPO_HAS_CONTENT" = "1" ]' in block
    assert '[ -f "$MCP_STAGING/mcp-servers.json" ]' not in read_skill("sync-backup")


def test_restore_clears_the_shared_staging_before_both_apply_base_calls():
    """apply-base 산출물이 같은 디렉토리를 쓴다 — rm -rf는 둘보다 앞에서 한 번이다."""
    text = read_skill("sync-restore")
    count = text.count(STAGING_CLEAR)
    assert count == 1, "스테이징 비우기가 %d번이다. 정확히 한 번이어야 한다" % count
    clear = index_of(text, STAGING_CLEAR, "sync-restore")
    for call in ('"$SYNC_SCRIPTS/plan_plugins.py" apply-base',
                 '"$SYNC_SCRIPTS/plan_mcp.py" apply-base'):
        assert clear < index_of(text, call, "sync-restore"), (
            "스테이징 비우기가 %r보다 뒤에 있다" % call
        )


def test_restore_never_executes_marketplace_remove():
    """14.1 — 연쇄 삭제 방어. 안내는 하되 실행하지 않는다 (9.3.5).

    산문에는 나타나야 한다 — 사용자가 손으로 실행할 명령을 알려 주는 자리다.
    """
    sec = plugin_restore_section()
    assert "marketplace remove" in sec
    assert not any("marketplace remove" in block for block in bash_blocks(sec))


# 5절의 자기 업데이트 안내. claude-sync **자신**을 올리는 명령이라 9.3.1이 스코프를
# 규정한 대상이 아니다(spec 12장이 이 두 줄의 보존을 지시한다). **제외 목록으로 적는다** —
# 허용 목록(설치·활성화 동사)으로 적으면 목록에서 동사 하나를 빼는 것만으로 그 명령이
# 검사를 조용히 빠져나가고, 나중에 추가되는 명령은 아예 검사되지 않는다.
# **동사가 아니라 명령 전문으로 적는다.** 동사(`update `)로 면제하면 5-2의 install을
# `claude plugin update <id>`로 바꾼 줄까지 함께 빠져나가 --scope user 가드도 -y 가드도
# 그 줄을 보지 않는다(실측 — 그렇게 바꿔도 스위트 전체가 통과했다).
RESTORE_SELF_UPDATE_COMMANDS = (
    "claude plugin marketplace update claude-sync",
    "claude plugin update claude-sync",
)


def restore_plugin_commands():
    """5절의 bash 블록에서 복원이 실제로 내는 `claude plugin` 명령을 모은다."""
    prefix = "claude plugin "
    out = []
    for block in bash_blocks(plugin_restore_section()):
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith(prefix) or line in RESTORE_SELF_UPDATE_COMMANDS:
                continue
            out.append(line)
    return out


def test_restore_plugin_commands_carry_scope_user_and_never_dash_y():
    """14.1 — --scope user가 없으면 복원된 플러그인이 settings.json에 나타나지 않아
    backup이 못 보고 status가 only_repo를 영구 보고한다(I6). -y는 D2 위반이다."""
    commands = restore_plugin_commands()
    assert commands, "5절에 복원 명령이 하나도 없다 — 배선이 사라졌다"
    for command in commands:
        assert "--scope user" in command, command
        assert " -y" not in command and "--yes" not in command, command


# 플러그인 단계가 있어야 할 절. 세 스크립트의 최상위 status가 **섹션 skip을 반영하지
# 않으므로**(collect_plugins·compare_plugins·build_plan·apply_base의 공통 계약),
# 소비자가 최상위만 읽으면 두 섹션이 접힌 실행을 "할 것이 없습니다"로 보고하고
# **조용히 아무것도 하지 않는다.** 세 스킬이 각자 그 자리에서 섹션 단위 status를
# 따로 읽는다고 적어야 한다.
PLUGIN_STEP = {
    "sync-backup": lambda: section("sync-backup", "5. plugins.json 생성 (키 단위 3-way 병합)"),
    # status의 2단계는 플러그인과 MCP를 **함께** 담으므로 절 전체를 보면 플러그인 쪽
    # 문장이 MCP 문단으로 옮겨져도 통과한다(실측). 반쪽만 자른다.
    "sync-status": status_plugin_section,
    "sync-restore": plugin_restore_section,
}
PER_SECTION_STATUS = 'sections[<섹션>]["status"]'
# 문단을 반대 지시로 뒤집으면 반드시 사라지는 어휘. 리터럴 하나만 걸면 "최상위만 읽으면
# 된다"로 뒤집어도 그 리터럴이 남아 통과한다(실측). 세 스킬 모두 지금 이 둘을 갖는다.
PER_SECTION_WORDING = ("반영하지 않는다", "반드시 따로 읽")


@pytest.mark.parametrize("skill", sorted(PLUGIN_STEP))
def test_plugin_step_reads_the_per_section_status_separately(skill):
    """최상위 status는 섹션 skip을 반영하지 않는다 — 그 사실이 절 안에 적혀야 한다.

    파일 어딘가면 되는 검사는 문장이 엉뚱한 단계로 옮겨져도 통과한다(불변식 7).

    **리터럴 하나로는 부족하다** — 그것만 남기고 문단을 반대 지시로 뒤집어도 통과한다.
    뒤집으면 반드시 사라지는 어휘를 함께 건다.
    """
    # 상수 자신이 넓어지는 것도 막는다 — 'sections'로 줄이면 어느 문장이든 만족시킨다.
    assert '["status"]' in PER_SECTION_STATUS
    # 어휘 목록이 줄면 그만큼 뒤집기가 통과한다(실측). 손으로 고른 목록이라 대조할
    # 외부 진실 원천이 없으므로 개수를 건다 — 늘리거나 줄이는 것은 의도된 행위여야 한다.
    assert len(PER_SECTION_WORDING) == 2
    sec = PLUGIN_STEP[skill]()
    assert PER_SECTION_STATUS in sec, skill
    for wording in PER_SECTION_WORDING:
        assert wording in sec, (skill, wording)


# skip이 **아닌** 갈래. 보류 파일을 읽지 못한 실행에서 pluginConfigs만 접히는데
# enabledPlugins는 H3의 해제 기록을 함께 잃는다 — 그 섹션은 status가 "ok"이므로 skip
# 분기로는 절대 렌더링되지 않고, 이 문단이 없으면 **왜 해제가 되돌아갔는지가 사용자에게
# 도달할 경로가 없다.** 스크립트가 필드를 싣고만 있으므로 여기가 그 유일한 경로다.
DEGRADED_KEY = "`degraded_reason`"
DEGRADED_WORDING = ("다시 보류", "함께 알린다")


@pytest.mark.parametrize("skill", sorted(PLUGIN_STEP))
def test_plugin_step_reports_the_degraded_reason_of_a_section_it_kept(skill):
    """`status`가 "ok"인 섹션에도 실릴 수 있는 사유를 세 스킬이 함께 알려야 한다.

    키 이름만 걸면 "이 필드는 무시해도 된다"로 뒤집어도 통과한다(PER_SECTION_WORDING과
    같은 형태의 실측). 뒤집으면 반드시 사라지는 어휘를 함께 건다.
    """
    assert len(DEGRADED_WORDING) == 2
    sec = PLUGIN_STEP[skill]()
    assert DEGRADED_KEY in sec, skill
    for wording in DEGRADED_WORDING:
        assert wording in sec, (skill, wording)


def syncignore_patterns(text):
    """`.syncignore` 예시 fence의 패턴 줄. 주석과 빈 줄은 뺀다.

    **손으로 적지 않는다.** 이 검사의 주제가 "문서가 드는 예시가 실제로 무언가를
    제외하는가"이므로, 바늘을 상수로 두면 문서를 고치지 않고 상수만 고쳐도 초록이 된다.
    """
    i = text.index("`.syncignore` 예시:")
    m = re.compile(r"```\n(.*?)```", re.S).search(text, i)
    assert m, ".syncignore 예시 블록을 찾지 못했다"
    return [line.strip() for line in m.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")]


def syncignore_block():
    """4단계에서 `.syncignore`를 적용하는 bash 블록. 산문이 아니라 실행줄이다."""
    blocks = [b for b in bash_blocks(read_skill("sync-backup"))
              if ".syncignore" in b and "find " in b]
    assert len(blocks) == 1, "적용 블록이 하나가 아니다: %d개" % len(blocks)
    return blocks[0]


def test_syncignore_examples_actually_exclude_something(tmp_path):
    """**문서가 드는 패턴을 그대로 실행해 본다.**

    이 기능에는 저장소 전체에 테스트가 하나도 없었고, 그동안 문서는 *"gitignore 형식"*
    이라 말하며 `skills/secret-tool/`(후행 슬래시)을 예시로 들었다. 구현은
    `find -path`이고 find는 디렉토리를 후행 슬래시 없이 출력하므로 **그 패턴은 매치 0건**
    이었다(실측). 문서를 그대로 따른 사용자는 제외했다고 믿은 디렉토리를 경고 한 줄 없이
    push한다 — 조용한 fail-open이다.

    **예시를 파일에서 뽑고, 트리를 그 예시에서 만든다.** 패턴이 다시 슬래시로 끝나면
    `rstrip("/")`으로 만든 대상이 매치되지 않아 그대로 남고 이 테스트가 죽는다.
    남겨 두는 대조 파일(`agents/public.md`)이 없으면 "전부 지운다"로도 단정이 참이 된다.
    """
    patterns = syncignore_patterns(read_skill("sync-backup"))
    assert len(patterns) >= 2, patterns

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    targets = []
    for pattern in patterns:
        rel = pattern.replace("*", "x").rstrip("/")
        target = repo / rel
        if "." in os.path.basename(rel):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("secret", encoding="utf-8")
        else:
            target.mkdir(parents=True, exist_ok=True)
            (target / "SKILL.md").write_text("secret", encoding="utf-8")
        targets.append((pattern, target))
    keep = repo / "agents" / "public.md"
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("keep", encoding="utf-8")

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".syncignore").write_text(
        "# 주석은 무시된다\n\n" + "\n".join(patterns) + "\n", encoding="utf-8")

    proc = subprocess.run(["bash", "-c", syncignore_block()],
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home), SYNC_REPO=str(repo)))
    assert proc.returncode == 0, proc.stderr
    for pattern, target in targets:
        assert not target.exists(), (
            "문서가 드는 패턴이 아무것도 제외하지 않는다: %r" % pattern)
    assert keep.exists(), "패턴에 없는 파일까지 지웠다"
    assert (repo / ".git").exists(), ".git이 prune되지 않았다"


def test_status_reports_plugin_sections_through_the_new_script():
    """결함 B — check_status.py의 키 집합 비교를 지우고 새 스크립트를 부른다."""
    sec = PLUGIN_STEP["sync-status"]()
    assert '"$SYNC_SCRIPTS/compare_plugins.py"' in sec
    assert "skipped" in sec
    with open(os.path.join(SKILLS_DIR, "sync-status", "scripts", "check_status.py"),
              encoding="utf-8") as f:
        source = f.read()
    # 막아야 하는 것은 "그 문자열이 다시 나타나는 것"이 아니라 **이 스크립트가 플러그인
    # 문서를 다시 파싱하는 것**이다(docstring이 약속하는 것도 그쪽이다). 다른 키로
    # 되살려도 걸리도록 JSON 읽기 자체를 건다 — 이 스크립트는 이제 JSON을 읽지 않는다.
    assert "enabledPlugins" not in source
    assert "plugins.json" not in source
    assert "import json" not in source
    # **"모두 동기화 상태"가 전칭으로 읽히면 안 된다.** 이 스크립트가 열거하는 것은
    # agents·skills·CLAUDE.md뿐인데, 범위를 적는 절이 사라지면 소비자가 그 한 줄을
    # "전부 동일"로 요약해 플러그인·MCP의 차이가 조용히 사라진다.
    assert "따로 보고합니다" in source


def test_extract_plugins_is_gone_everywhere():
    """12장 — 스킬이 새 스크립트를 부르게 된 뒤에 지운다. 그 전에 지우면 백업이 깨진다."""
    scripts = os.path.join(SKILLS_DIR, "sync-backup", "scripts")
    assert not os.path.exists(os.path.join(scripts, "extract_plugins.py"))
    for skill in SKILLS:
        assert "extract_plugins" not in read_skill(skill), skill


def choice_json_payload():
    """5-7의 선택 결과 heredoc 본문. 없으면 무엇이 사라졌는지 말하고 실패한다."""
    sec = plugin_restore_section()
    marker = "<< 'EOF'\n"
    assert marker in sec, "5-7에 선택 결과 heredoc이 없다"
    body = sec.split(marker, 1)[1]
    return body.split("\nEOF", 1)[0]


def test_restore_choice_json_uses_the_real_section_names():
    """9.3.7 — 섹션 이름이 틀리면 `choice_list`가 **그 섹션을 조용히 무시한다.**

    예외도 빈 결과도 나지 않는다. 선택을 하나도 적용하지 않은 복원이 성공한 것처럼
    보이고, 사용자가 고른 "로컬 유지"·"이 기기 값으로 통일"이 전부 사라진다.
    프로덕션에는 이 오타를 막는 가드가 없으므로(하네스의 `_apply_base`에만 있다)
    **템플릿 자체를 어댑터의 SECTIONS에 묶는다** — 손으로 옮겨 적은 목록과 비교하면
    섹션 이름이 바뀔 때 같이 틀린다.
    """
    data = json.loads(choice_json_payload())
    assert set(data) == set(pc.SECTIONS), sorted(set(data).symmetric_difference(pc.SECTIONS))
    # `configured`를 빠뜨리면 6.4의 탈출구가 무증상으로 죽는다 — 한 번 declined된 항목은
    # 사용자가 값을 채워도 보류 파일에 남아 지문이 계속 매치되어 다시 묻지 않는다.
    assert "configured" in data["pluginConfigs"]
    assert "release" in data["enabledPlugins"]


# 스테이징을 base로 옮기는 절. **어느 단계에도 속하지 않아야 한다** — 아래 도달성 단정.
RESTORE_BASE_SECTION = "6.5 base 갱신 (스테이징 → base)"
RELS_LOOP = "for rel in plugins.json mcp-servers.json"

# 통째로 건너뛸 수 있다고 스스로 적어 둔 단계. 이 목록은 아래에서 **파일에서 뽑은
# 집합과 대조**하므로 손으로 줄일 수 없다.
SKIPPABLE_RESTORE_STEPS = (
    ("5. 플러그인 복원", "플러그인 단계 전체를 건너뛴다"),
    ("6. MCP 서버 복원", "MCP 단계 전체를 건너뛴다"),
)


def restore_step_headings():
    """sync-restore의 '### ' 제목 전부(제목 문자열만)."""
    return [m.group(1) for m in re.finditer(r"\n### (.+)", read_skill("sync-restore"))]


def test_restore_base_gate_covers_both_relpaths():
    """9.3.7 — restore 경로의 base가 전진하지 않으면 탈출구가 통째로 죽는다.

    backup 쪽 동형은 test_backup_base_gate_covers_both_relpaths가 잡는데, restore 쪽은
    무가드였다(실측 — 루프를 mcp-servers.json 하나로 줄여도 스위트 전체가 통과했다).
    그렇게 되면 `keep_stale`·`keep_local`·`release` 선택이 base에 반영되지 않아
    **사용자가 고른 것이 조용히 무효가 된다.**
    """
    sec = section("sync-restore", RESTORE_BASE_SECTION)
    assert RELS_LOOP in sec
    assert '"$BASE_STAGING" "${RELS[@]}"' in sec


def test_restore_base_advance_is_reachable_when_either_step_is_skipped():
    """**모양이 아니라 도달성을 잰다.** 루프를 잠가도 그 루프에 도달하는지는 별개다.

    5절과 6절은 각각 통째로 건너뛸 수 있다고 스스로 적어 두었다. 스테이징 → base 이동이
    그 둘 중 하나 **안에** 있으면, 그 단계가 `skipped`인 실행에서 다른 파일이 이미
    계산해 스테이징에 써 둔 base가 영영 옮겨지지 않는다 — 두 파일 중 하나만 skip돼도
    나머지의 선택이 조용히 무효가 된다(9.3.7). 옮기는 경로가 하나뿐이므로 그 자리는
    **어느 단계에도 속하지 않아야** 한다.
    """
    text = read_skill("sync-restore")
    # 루프의 **내용**도 함께 건다 — RELS_LOOP를 "for rel in"으로 넓히면 개수·부재·모양
    # 단정이 전부 통과하면서 두 relpath 가드가 조용히 죽는다(실측).
    assert "plugins.json" in RELS_LOOP and "mcp-servers.json" in RELS_LOOP
    assert text.count(RELS_LOOP) == 1, "base 이동 루프가 하나여야 한다"
    # **표를 파일에서 뽑은 사실과 짝짓는다.** 손으로 쓴 목록이면 항목을 지우는 것만으로
    # 그 단계가 검사를 조용히 빠져나간다(실측) — 이 파일이 다른 자리에서 닫은 성질이다.
    skippable = {heading for heading, _ in SKIPPABLE_RESTORE_STEPS}
    found = {h for h in restore_step_headings() if "단계 전체를 건너뛴다" in section("sync-restore", h)}
    assert skippable == found, sorted(skippable.symmetric_difference(found))
    for step, skip in SKIPPABLE_RESTORE_STEPS:
        sec = section("sync-restore", step)
        assert skip in sec, "%s가 통째로 건너뛸 수 있다는 사실이 사라졌다" % step
        assert RELS_LOOP not in sec, (
            "%s 안에 base 이동이 있다 — 그 단계가 skipped면 다른 파일의 base도 죽는다" % step
        )
    assert "어느 쪽이 건너뛰어졌더라도" in section("sync-restore", RESTORE_BASE_SECTION)

    # **어느 단계에도 속하지 않는 것만으로는 부족하다 — 두 생산자보다 뒤여야 한다.**
    # 이동이 6-6의 MCP apply-base보다 앞이면 그 산출물이 만들어지기 전에 옮기기가
    # 끝나 mcp-servers.json의 base가 영영 전진하지 않는다(실측 — 절을 앞으로 옮겨도
    # 스위트 전체가 통과했다). 플러그인 쪽에서 이 절이 막은 것과 같은 상태다.
    # test_restore_clears_the_shared_staging_before_both_apply_base_calls의 짝이다.
    move = index_of(text, RELS_LOOP, "sync-restore")
    for producer in ('"$SYNC_SCRIPTS/plan_plugins.py" apply-base',
                     '"$SYNC_SCRIPTS/plan_mcp.py" apply-base'):
        assert index_of(text, producer, "sync-restore") < move, (
            "base 이동이 %r보다 앞이다 — 그 산출물이 옮겨지지 않는다" % producer
        )


# 게이트되는 스크립트 실행줄. `cp`는 자료 복사라 게이트 대상이 아니고, 인라인
# `python3 -c`·`python3 - <<'PY'`는 스크립트를 부르지 않으므로 둘 다 이 정규식에
# 걸리지 않는다 — 예외 목록을 따로 두지 않는 근거가 그것이다.
SCRIPT_CALL = re.compile(r'python3 "?\$SYNC_(?:SCRIPTS|BACKUP_SCRIPTS|LIB)/')


def script_calls_after_the_check(skill):
    """호환성 검사 호출줄 **뒤에** 오는 스크립트 실행줄 전부. 완전성 단정의 진실 원천이다.

    **면제는 검사 호출줄과 그 앞까지다 — 블록 단위가 아니다.** 블록째 면제하면 검사와
    같은 블록에 실행줄을 **덧붙이는** 것만으로 그 줄이 대조에서 통째로 빠진다(실측).
    검사 **앞**의 줄은 여기서 요구하지 않는다 — 요구하면
    test_compatibility_check_precedes_everything_it_gates와 논리적으로 충돌한다.
    대신 script_calls_before_the_check가 그런 줄을 **금지한다**: 검사가 막을 수 없는
    자리에 있다는 사실이 곧 거기 있으면 안 되는 이유다.
    """
    text = read_skill(skill)
    after = index_of(text, COMPAT_CALL, skill)
    out, cursor = [], 0
    for m in BASH_BLOCK.finditer(text):
        cursor = m.start(1)
        for raw in m.group(1).splitlines():
            here = text.index(raw, cursor) if raw else cursor
            cursor = here + len(raw)
            if here > after and SCRIPT_CALL.match(raw.strip()):
                out.append(raw.strip())
    return out


def script_calls_before_the_check(skill):
    """호환성 검사 호출줄 **앞에** 오는 스크립트 실행줄. 지금은 세 스킬 다 0건이다."""
    text = read_skill(skill)
    before = index_of(text, COMPAT_CALL, skill)
    out, cursor = [], 0
    for m in BASH_BLOCK.finditer(text):
        cursor = m.start(1)
        for raw in m.group(1).splitlines():
            here = text.index(raw, cursor) if raw else cursor
            cursor = here + len(raw)
            line = raw.strip()
            if here < before and SCRIPT_CALL.match(line) and line != COMPAT_CALL:
                out.append(line)
    return out


@pytest.mark.parametrize("skill", SKILLS)
def test_no_gated_script_call_precedes_the_check(skill):
    """검사보다 앞에서 스크립트를 부르면 **그 줄은 검사가 막을 수 없다.**

    표에 넣어 순서를 걸 수도 없다(검사가 그보다 앞이라는 단정과 충돌한다). 그러므로
    남는 처방은 금지 하나다. 지금 세 스킬 다 0건이라 이 단정은 공허하지 않다 —
    실측으로, 검사 호출 **앞**에 게이트 대상 한 줄을 넣어도 스위트 전체가 통과했다.
    """
    assert not script_calls_before_the_check(skill), script_calls_before_the_check(skill)


@pytest.mark.parametrize("skill", SKILLS)
def test_before_calls_covers_every_gated_script_call(skill):
    """`before_calls`가 게이트되는 실행줄을 **전부** 담는지 SKILL.md에서 뽑아 대조한다.

    이 단정이 없으면 표에서 앵커 한 줄을 지워도 아무도 못 잡는다(실측) — "각 항목마다
    검사"하는 맨 목록은 자기 축소를 탐지할 수 없기 때문이다. 진실 원천을 손으로 쓴
    목록이 아니라 **SKILL.md의 bash 블록 자체**로 잡아 그 성질을 없앤다
    (test_every_skill_on_disk_is_covered_by_the_contract와 같은 idiom).
    """
    covered = COMPAT_WIRING[skill]["before_calls"]
    for line in script_calls_after_the_check(skill):
        assert any(line.startswith(anchor) for anchor in covered), (
            "%s: 검사 뒤의 실행줄인데 before_calls에 없다 — %r" % (skill, line)
        )


REDIRECT = re.compile(r"\s*>\s*\S+$")


@pytest.mark.parametrize("skill", SKILLS)
def test_each_anchor_witnesses_exactly_one_call_site(skill):
    """앵커 하나는 **호출 지점 하나**를 증언해야 한다.

    좁은 앵커 둘을 넓은 하나로 교체하면 그 하나가 두 지점을 덮고, 그 순간 표는 두 지점이
    **존재한다는 사실**을 더 이상 증언하지 못한다 — 한 지점을 파일에서 지워도 남은
    지점이 앵커를 만족시켜 아무도 알아채지 못한다. 접두 관계만 보는 위 단정은 그 교체를
    통과시킨다(실측).

    끝의 `> /tmp/…` 리다이렉트는 지우고 센다 — 같은 호출의 표기 차이일 뿐이고,
    restore의 `--set-base-from`처럼 **같은 줄이 여러 번** 나오는 것은 지점 하나다.
    """
    calls = script_calls_after_the_check(skill)
    for anchor in COMPAT_WIRING[skill]["before_calls"]:
        sites = {REDIRECT.sub("", line) for line in calls if line.startswith(anchor)}
        assert len(sites) == 1, (
            "%s: 앵커가 호출 지점 %d개를 덮는다 — %r → %s" % (
                skill, len(sites), anchor, sorted(sites))
        )


@pytest.mark.parametrize("skill", SKILLS)
def test_no_anchor_swallows_another(skill):
    """앵커 하나가 다른 앵커의 접두이면 안 된다.

    **이 단정이 막는 것은 넓은 앵커를 「더하는」 형태 하나다.** 좁은 둘을 지우고 넓은
    하나로 **교체**하면 남은 앵커 중 어느 것도 다른 것의 접두가 아니라 여기를 통과한다 —
    실측으로 확인했다. 표를 "정리"하다 자연히 일어나는 편집은 추가가 아니라 그 교체이고,
    그쪽은 test_each_anchor_witnesses_exactly_one_call_site가 잡는다.
    """
    anchors = COMPAT_WIRING[skill]["before_calls"]
    for one in anchors:
        for other in anchors:
            assert one is other or not other.startswith(one), (one, other)


# SKILL.md가 스크립트의 계약을 **어느 키에서 읽는지**까지 적어야 하는 자리. 이 문장이
# 흐려지면 스킬이 다른 경로로 같은 값을 만들어 내고, 그 순간 결함 B(파서 두 벌)와
# 인계 계약 ⑶(계획이 지목하지 않은 id에 설정을 채운다 = 실제 흐름이 만들 수 없는 상태)이
# 되살아난다. 둘 다 예외도 빈 결과도 없이 조용하다.
SCRIPT_CONTRACT_PHRASES = [
    ("sync-status", '`changed_detail[<키>]["local"]`'),
    # spec 9.2가 "설치됨/미설치를 구별해 말한다"를 요구하고 그 구별을 실을 필드로
    # not_installed를 지목한다. 스크립트는 필드를 싣고만 있으므로 **이 문장이 그 구별이
    # 사용자에게 닿는 유일한 경로**다. 지워지면 남는 문장은 전부 참인데(absent_locally
    # 불릿이 "이 목록 자체는 미설치가 아니다"라고만 말한다) 구별을 말할 자리가 없어진다.
    ("sync-status", "`not_installed` — `absent_locally` 중"),
    # `unrestorable`은 `only_repo`에서 뽑히지 않는다 — restore가 새 항목으로 훑는
    # 집합에서 뽑으므로 값 보류(H3) + 레포 전용 키도 담는다. 이 문장이 없으면 소비자가
    # `only_repo` 밑에서만 "복원할 수 없습니다"를 붙이고, 그 키에는 `not_installed`의
    # "restore가 설치합니다"가 그대로 나간다(spec 9.2가 금지한 문구).
    ("sync-status", "**`only_repo`의 부분집합이 아니다**"),
    ("sync-restore", "**`config_keys`에 실린 키만**"),
    # 5-6이 **계획이 실제로 내는 버킷**을 가리켜야 한다. 앞 판은 `absent_locally`를
    # 가리켰는데 그것은 compare_plugins(status)만 내는 필드이고, restore 문맥에서는
    # 구조적으로 공집합이다(restore_plan이 값 보류 키를 value_held에 넣는 조건이
    # `name in local`이라 로컬에 값이 없는 키는 add/needs_secret으로 빠진다).
    ("sync-restore", "`add`/`needs_secret`"),
    # 계획 JSON은 두 층인데 5-5·5-6이 섹션별 버킷과 최상위 키를 구별 없이 불렀다.
    # 소비자가 최상위에서 `local_stale`을 찾아 없으면 **케이스 4·5·8·9가 하나도
    # 보고되지 않는다** — 넷 다 spec 9.3.4의 안정 상태라 사용자가 고를 기회 자체가
    # 사라진다. 층을 거는 가드가 없어 "네 버킷은 최상위에 있다"는 거짓을 넣어도
    # 스위트가 전부 통과했다(실측).
    ("sync-restore", "버킷은 `sections[<섹션>]` 안에 있다"),
]


@pytest.mark.parametrize("skill,phrase", SCRIPT_CONTRACT_PHRASES)
def test_plugin_step_names_the_key_it_reads(skill, phrase):
    assert phrase in PLUGIN_STEP[skill](), (skill, phrase)


def test_the_script_contract_table_did_not_shrink():
    """위 표는 **손으로 고른 목록**이라 대조할 외부 진실 원천이 없다.

    그래서 개수만 함께 건다 — 항목을 지우면 그 계약이 아무 소리 없이 검사에서
    빠지기 때문이다(실측 — 하나를 지워도 스위트 전체가 통과했다). 계약을 더하거나
    빼는 것은 의도된 행위여야 하고, 그때 이 숫자를 함께 고치는 것이 그 표시다.
    이 단정이 말하는 것은 그것뿐이다 — 표의 **내용**이 옳은지는 재지 않는다.
    """
    assert len(SCRIPT_CONTRACT_PHRASES) == 6


# SCRIPT_CALL의 대안 목록이 SKILL.md가 실제로 쓰는 루트 변수를 전부 덮는지 대조한다.
# 덮지 못하면 그 변수로 부르는 실행줄이 완전성 검사에서 통째로 빠지는데, 빠져도
# 아무 테스트가 실패하지 않는다(실측). `.py` 경로만 보므로 bootstrap.sh 복사와
# `$SYNC_ROOT/.claude-plugin/...` 읽기는 자연히 제외된다 — 예외 목록이 필요 없다.
SCRIPT_PATH_VAR = re.compile(r"\$(SYNC_[A-Z_]+)/[A-Za-z0-9_]+\.py")


def test_script_call_pattern_covers_every_root_variable():
    found = {name for skill in SKILLS for block in bash_blocks(read_skill(skill))
             for name in SCRIPT_PATH_VAR.findall(block)}
    # **진실 원천이 스스로 좁아지는 것**을 막는다. SCRIPT_PATH_VAR를 한 변수로 좁히면
    # found가 그만큼 줄고, SCRIPT_CALL이 그것을 덮으므로 전부 초록이 된다(실측).
    # 세 변수는 세 SKILL.md가 이미 전부 쓰고 있다.
    assert found >= {"SYNC_SCRIPTS", "SYNC_BACKUP_SCRIPTS", "SYNC_LIB"}, sorted(found)
    for name in sorted(found):
        assert SCRIPT_CALL.match('python3 "$%s/x.py"' % name), (
            "SCRIPT_CALL이 $%s를 덮지 않는다 — 그 변수로 부르는 줄이 완전성 검사에서 빠진다"
            % name
        )


def status_only_repo_guidance():
    """2단계 `only_repo` 불릿이 말하는 처방 문장.

    **손으로 적지 않고 파일에서 뽑는다.** `not in` 가드는 바늘이 틀려도 통과하므로
    (없어야 할 것을 찾는 검사라 부재가 곧 초록이다) 상수로 두면 값을 아무 문구로
    바꾸는 것만으로 통째로 공허해진다(실측). 여기서 뽑으면 2단계의 문구가 바뀔 때
    가드가 따라가고, 뽑지 못하면 그 자리에서 실패한다.
    """
    for line in PLUGIN_STEP["sync-status"]().splitlines():
        if line.startswith("- `only_repo`"):
            for part in line.split("—", 1)[1].split(". "):
                if "/sync-restore" in part:
                    return part.strip().rstrip(".")
    raise AssertionError("2단계에서 only_repo의 처방 문장을 뽑지 못했다 — 불릿이 낡았다")


def test_status_summary_does_not_keep_a_second_glossary():
    """용어집이 두 벌이면 **낡은 쪽이 이긴다** — 3단계가 사용자에게 갈 최종 요약을 만든다.

    실측으로, 3단계의 `only_repo` 정의를 2단계와 정면으로 모순되게 바꿔도 797개가 전부
    통과했다. 그 정의는 `unrestorable` 항목에 대해 거짓이고(spec 9.2가 금지한 문구),
    3단계에는 `held`·`absent_locally`·`not_installed`가 아예 없어 요약만 보고 보고하면
    보류 항목이 `only_local`·`changed`로 나간다 — 역시 9.2가 금지한 것이다.
    """
    sec = section("sync-status", "3. 결과 요약")
    # **형태가 아니라 문구를 건다.** 불릿 기호 한 글자(`-` → `*`)만 바꾸거나 표 한 행,
    # 산문 한 줄로 되살리면 아래 불릿 검사를 전부 우회한다(실측). spec 9.2가 금지한
    # 이 문장은 unrestorable 항목에 대해 거짓이므로 어느 형태로도 여기 있으면 안 된다.
    # 백틱을 양쪽에서 지우고 비교한다 — `- **only_repo**:`든 표 한 행이든 산문이든,
    # 표기만 바꾼 되살리기를 전부 같은 바늘로 잡는다.
    banned = status_only_repo_guidance().replace("`", "")
    assert banned, "금지 문구를 뽑지 못했다"
    assert banned not in sec.replace("`", ""), banned
    # 아래는 형태 쪽 그물이다 — 금지 문구를 바꿔 쓴 정의도 불릿 머리로는 걸린다.
    # 언급까지 막지는 않는다: 왜 두 벌이면 안 되는지를 적은 문장 자체가 버킷 이름을 부른다.
    for line in sec.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        head = line[2:].lstrip("*`")
        for bucket in ("only_local", "only_repo", "changed"):
            assert not head.startswith(bucket), (
                "3단계에 버킷 정의가 다시 생겼다(%s) — 문구는 2단계 한 곳에서만 정한다\n%s"
                % (bucket, line)
            )
    assert "2단계를 따른다" in sec


# skipped의 `reason`이 형식 문제일 때 안내할 명령. 네 자리(backup 5단계, status 2단계의
# 플러그인·MCP 두 문단, restore 5절)가 같은 말을 해야 한다 — 하나만 빠지면 그 경로의
# 사용자는 자기 플러그인이 낡았다는 사실을 어디에서도 듣지 못한다. **개수까지 건다**:
# 존재만 보면 네 자리 중 하나가 빠져도 나머지가 가려 준다(실측으로 그 상태였다).
UPDATE_GUIDANCE = ("claude plugin marketplace update claude-sync"
                   " && claude plugin update claude-sync")
UPDATE_GUIDANCE_SITES = [
    ("sync-backup", "5. plugins.json 생성 (키 단위 3-way 병합)", 1),
    ("sync-status", "2. 메타데이터 기반 상태 분석", 2),   # 플러그인 + MCP
    ("sync-restore", "5. 플러그인 복원", 1),
]


@pytest.mark.parametrize("skill,heading,count", UPDATE_GUIDANCE_SITES)
def test_skipped_branches_point_at_the_update_command(skill, heading, count):
    found = section(skill, heading).count(UPDATE_GUIDANCE)
    assert found == count, "%s '%s': 업데이트 안내가 %d번(기대 %d번)" % (
        skill, heading, found, count)


def test_every_skill_has_an_update_guidance_site():
    """표에서 스킬 하나를 빼면 그 스킬의 안내가 조용히 검사에서 사라진다(실측).

    세 스킬이 전부 skipped 갈래를 갖고 셋 다 같은 안내를 해야 하므로 SKILLS와 짝짓는다.
    """
    listed = {skill for skill, _, _ in UPDATE_GUIDANCE_SITES}
    assert listed == set(SKILLS), sorted(listed.symmetric_difference(SKILLS))


# 각 스킬의 플러그인 단계에 **있으면 안 되는** MCP 호출. PLUGIN_STEP의 접근자가 넓어지면
# 절 경계가 무의미해지는데(status를 2단계 전체로 되돌려도 스위트 전체가 통과했다),
# 그 넓어짐은 이 호출이 딸려 들어오는 것으로 드러난다.
FOREIGN_MCP_CALL = {
    "sync-backup": '"$SYNC_SCRIPTS/collect_mcp.py"',
    "sync-status": '"$SYNC_SCRIPTS/compare_mcp.py"',
    "sync-restore": '"$SYNC_SCRIPTS/plan_mcp.py"',
}


@pytest.mark.parametrize("skill", SKILLS)
def test_plugin_step_slice_excludes_the_mcp_half(skill):
    assert set(FOREIGN_MCP_CALL) == set(SKILLS)
    # **값도 잠근다.** 아무 데도 없는 문자열로 바꾸면 이 단정이 통째로 공허해진다(실측).
    assert FOREIGN_MCP_CALL[skill] in read_skill(skill), FOREIGN_MCP_CALL[skill]
    assert FOREIGN_MCP_CALL[skill] not in PLUGIN_STEP[skill](), (
        "%s: 플러그인 단계 접근자가 MCP 쪽까지 잘라 왔다 — 절 경계가 무의미해진다" % skill
    )


def test_backup_report_table_covers_every_held_kind():
    """보류 종류를 어댑터에서 뽑아 대조한다.

    표를 손으로 옮겨 적으면 종류가 늘 때 따라오지 못하고, 한 행이 지워져도 아무도
    알아채지 못한다(실측 — `held.extended_value` 행을 지워도 스위트 전체가 통과했다).
    보류는 백업하지 않는 항목이라, 행이 사라지면 사용자는 그 항목이 왜 레포에 안
    올라가는지 들을 곳이 없어진다.
    """
    sec = PLUGIN_STEP["sync-backup"]()
    kinds = {kind for names in pc.HELD_KINDS.values() for kind in names}
    assert kinds, "plugin_config에서 보류 종류를 못 뽑았다"
    for kind in sorted(kinds):
        assert "`held.%s`" % kind in sec, kind
