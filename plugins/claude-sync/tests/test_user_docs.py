"""사용자 문서가 `plugins.json`에 대해 말하는 것 (spec 13장 첫 표, "새로 적어야 할 한계").

**왜 스킬 계약 파일들이 아니라 여기인가.** `test_script_root.py`는 SKILL.md의 0단계
bash를 **실행해서** 재고, `test_skill_wiring.py`는 세 SKILL.md의 **배선 계약**을 읽어서
잰다. `README.md`·`README.ko.md`는 스킬도 스크립트도 아니고 `backup-readme*.md`는 백업
레포에 그대로 복사되는 자료 파일이라, 그쪽에 얹으면 간판이 내용을 설명하지 못하는 파일이
하나 더 생긴다. SKILL.md의 서술 정정은 배선 계약 쪽 관심사이므로
`test_skill_wiring.py`에 남겼다. **예외는 파일 끝의 배포 순서 경고 하나다** —
그것은 배선이 아니라 같은 한 경고가 사용자 문서 넷과 `sync-backup/SKILL.md`에 흩어진
것이라, 표를 두 파일로 가르면 한쪽만 낡는다. 그 자리의 주석이 이유를 적었다.

**`not in` 가드는 바늘이 틀려도 초록이다** — 없어야 할 것을 찾는 검사라 부재가 곧 통과다.
그래서 옛 문구를 혼자 걸지 않고 **정정 문안과 짝지어** 건다(CORRECTIONS). 문서를 옛
문장으로 되돌리면 두 절반이 함께 죽고, 바늘만 무의미한 값으로 바뀌면 정정 문안 쪽 절반이
남는다(실측 — 정정 문안 쪽을 무의미한 값으로 바꾸면 CAUGHT다).

**바늘의 값은 저장소 안의 원천에 묶는다.** *"정정 후에는 옛 문구를 담은 원천이 남지
않는다"* 는 서술을 두 번 적었고 두 번 다 **거짓이었다.** 바늘 전부가
`plans/2026-08-20-mcp-integration.md`(커밋 하나뿐인 완결 문서) · spec 13장 ·
이 plan 본문의 Task 15 기록 중 어딘가에 축자로 남아 있다.
`test_every_stale_needle_is_quoted_by_a_source_document`가 그 대응을 건다 —
**면제 목록이 없다.** 예외를 인정하기 전에 원천을 전수로 훑는다.

목록이 스스로 줄어드는 것은 넷으로 막는다.
- USER_DOCS는 디스크의 README 계열 파일 목록과 대조한다(손으로 고른 목록이 아니다)
- CORRECTIONS의 **개수**는 spec 13장 첫 표에서, SYNCIGNORE_MEANING의 **개수**는
  `lib/syncignore.py`의 정본 번호 목록에서 뽑는다 — 둘 다 손으로 적지 않는다(plan ③ Task 10)
- CORRECTIONS는 개수를 함께 걸고, 바늘의 값은 원천 문서에 묶는다
- 새 한계의 **항목 수**는 spec 13장의 불릿 수에서 뽑는다
- 새 한계의 **내용**은 같은 언어의 두 문서끼리, 백틱 토큰은 한↔영끼리 대조한다
"""
import inspect
import os
import re

import pytest

import compat               # conftest.py가 lib를 sys.path에 넣는다
import mcp_config as mc
import plugin_config as pc
from two_x_facts import TWO_X_CARRIES   # 측정은 한 벌이다 — 그 파일의 docstring 참조

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
BACKUP_SCRIPTS = os.path.join(
    ROOT, "plugins", "claude-sync", "skills", "sync-backup", "scripts")
SPEC = os.path.join(ROOT, "docs", "superpowers", "specs",
                    "2026-08-24-plugins-sync-design.md")
# `.syncignore`의 진실 원천은 **실행되는 쪽**이다 — test_skill_wiring.py가 이 SKILL.md의
# bash 블록을 예시 패턴과 함께 실제로 돌린다. 여기서는 README 두 벌이 그 검사를 받은
# 예시와 같은 것을 드는지만 잰다(세 벌이 갈리면 한 곳만 고친 정정이 나머지를 남긴다).
SYNCIGNORE_SOURCE = os.path.join(
    ROOT, "plugins", "claude-sync", "skills", "sync-backup", "SKILL.md")

USER_DOCS = {
    "README.md": os.path.join(ROOT, "README.md"),
    "README.ko.md": os.path.join(ROOT, "README.ko.md"),
    "backup-readme.md": os.path.join(BACKUP_SCRIPTS, "backup-readme.md"),
    "backup-readme.ko.md": os.path.join(BACKUP_SCRIPTS, "backup-readme.ko.md"),
}

# 새 한계 목록의 머리말. 영어판·한국어판이 다르므로 문서마다 적는다.
LIMITS_ANCHOR = {
    "README.md": "Not synced:",
    "README.ko.md": "동기화되지 않는 것:",
    "backup-readme.md": "Not synced:",
    "backup-readme.ko.md": "동기화되지 않는 것:",
}


def read_doc(name):
    with open(USER_DOCS[name], encoding="utf-8") as f:
        return f.read()


# (옛 문구, 정정 문안). 정정 문안이 None인 항목은 **삭제만 있고 대체가 없는** 자리다.
# 지금은 하나도 없다 — README.ko.md의 예외 문구 삭제조차 "문장이 거기서 끝난다"는
# 정정 문안으로 표현할 수 있었다.
CORRECTIONS = {
    "README.md": (
        # spec 13장 3행 — "sensitive data excluded"는 pluginConfigs를 마스킹해서
        # 싣게 된 뒤로 거짓이다.
        ("Plugin/marketplace list (sensitive data excluded)",
         "plugin config **key names** (config values are masked)"),
        # 1행
        ("`plugins.json` is still overwritten wholesale",
         "**`plugins.json` merges key by key.**"),
        # 4행
        ("only the plugin list is extracted",
         "three fields are extracted and `pluginConfigs` values are masked"),
    ),
    "README.ko.md": (
        ("(민감 정보 제외)",
         "플러그인 설정 **키 이름** (설정 값은 마스킹)"),
        ("여전히 매 백업마다 통째로 덮어쓰입니다",
         "**`plugins.json`은 키 단위로 병합됩니다.**"),
        # 2행 — 영어판에는 이 문장이 **없다**. 한국어판만 보고 지시하면 영어 README는
        # 아무것도 고쳐지지 않으므로 두 파일의 표를 따로 둔다.
        ("**예외: `plugins.json`",
         "로컬 파일은 절대 자동으로 덮어쓰지 않습니다.\n"),
        ("플러그인 목록만 추출하며",
         "세 필드만 추출하며, `pluginConfigs`의 값은 `<REDACTED>`로 마스킹합니다"),
    ),
    "backup-readme.md": (
        # 13장 표에 **없는** 자리. generate_metadata.py:1이 "mtime 미사용"이라 적고
        # README.md:87도 같은 말을 하는데 백업 레포에 복사되는 이 파일만 반대를
        # 말하고 있었다 — 사용자가 클론했을 때 처음 읽는 문서다(quality review I3).
        # **정정 문안의 뒤 절반이 다시 거짓이었다.** "3-way 충돌 감지용"은 실측으로
        # 틀렸다 — `files` 맵을 읽는 프로덕션 코드가 하나도 없고(쓰는 쪽
        # generate_metadata.py뿐), 3-way의 실제 입력은 기기별 base다. 이 저장소의
        # 리뷰 체계가 스스로 만든 거짓을 이 표가 정답으로 잠그고 있었다.
        # 바늘을 **두 절반에 걸치도록** 잡아 어느 쪽을 되돌려도 죽게 한다.
        # 무엇이 참인지는 test_no_production_code_reads_the_metadata_files_map이 잰다.
        ("Per-file modification timestamps",
         "a per-file content hash of what this backup contained. Those hashes are "
         "a record, not an input"),
        # 5행
        ("(no sensitive data)",
         "plugin config key names (extracted from settings.json; config values masked)"),
        # 6행
        ("`plugins.json`, in contrast, is regenerated and overwritten on every backup.",
         "`plugins.json` is merged the same way, key by key, across its three sections"),
    ),
    "backup-readme.ko.md": (
        ("파일별 수정 시각",
         "이 백업에 담긴 파일별 내용 해시. 그 해시는 기록일 뿐 판정 입력이 아닙니다"),
        ("민감 정보 미포함",
         "설정 키 이름 (settings.json에서 추출, 설정 값은 마스킹)"),
        ("반면 `plugins.json`은 매 백업마다 새로 생성되어 덮어쓰입니다.",
         "`plugins.json`도 세 섹션 각각에 대해 같은 방식으로 키 단위 병합됩니다"),
    ),
}

PAIRS = [(name, stale, fixed)
         for name, pairs in CORRECTIONS.items() for stale, fixed in pairs]


def test_user_doc_list_covers_every_doc_on_disk():
    """USER_DOCS를 **디스크에서 뽑은 목록**과 대조한다.

    손으로 고른 목록이면 항목 하나(예: 영어 README)를 지우는 것만으로 그 파일이 아래
    가드 전부에서 조용히 빠진다 — 이 저장소가 반복해서 만난 다섯째 축이다.
    """
    # **루트의 모든 .md를 징집하면 안 된다.** CHANGELOG·CONTRIBUTING이 생기는 순간
    # "새 한계 일곱을 적어야 하는 사용자 문서"로 규정돼, 다음 사람이 그것을 풀려고
    # USER_DOCS에 아무거나 넣는다 — 이 가드가 막으려던 바로 그 결함이다.
    found = {n for n in os.listdir(ROOT)
             if n.startswith("README") and n.endswith(".md")}
    found |= {n for n in os.listdir(BACKUP_SCRIPTS) if n.startswith("backup-readme")}
    assert found == set(USER_DOCS), (
        "사용자 문서 목록이 디스크와 어긋난다: %s\n"
        "문서를 더했다면 USER_DOCS·LIMITS_ANCHOR·CORRECTIONS 셋과 파일 끝의 배포 순서 표 "
        "여섯(DEPLOY_ORDER_ANCHOR·_NO_MCP·_OTHERS·_SCOPE·_MARKER·MERGE_PROMISE)에 모두 "
        "더한다. CORRECTIONS의 개수는 손으로 적지 않는다 — spec 13장 첫 표에서 뽑으므로 "
        "그 표에도 행을 더해야 한다."
        % sorted(found.symmetric_difference(USER_DOCS)))
    assert set(CORRECTIONS) == set(USER_DOCS), sorted(
        set(CORRECTIONS).symmetric_difference(USER_DOCS))
    assert set(LIMITS_ANCHOR) == set(USER_DOCS), sorted(
        set(LIMITS_ANCHOR).symmetric_difference(USER_DOCS))


SPEC_PATH = os.path.join(ROOT, "docs", "superpowers", "specs",
                         "2026-08-24-plugins-sync-design.md")
DOC_ANCHOR = re.compile(r"`([A-Za-z0-9._-]+\.md):\d+`")


def spec_correction_counts():
    """spec 13장 **첫 표**가 사용자 문서를 지목하는 횟수 {문서: 개수}.

    **원천을 여기로 정했다**(plan ③ Task 10). 앞 판은 개수를 손으로 적어 두고 주석에
    *"대조할 외부 진실 원천이 없다"* 고 적었는데, 그러면 한 쌍을 지우면서 그 숫자도 함께
    줄이는 편집이 조용히 통과한다 — 이 저장소가 반복해 만난 다섯째 축이다.

    **첫 표만 본다.** 같은 장의 두 번째 표(2.x 배포 순서 경고)는 CORRECTIONS가 아니라
    별도 가드들이 담당하므로, `### `로 잘라 범위를 못박는다. 넓히면 그쪽 행이 개수를
    부풀려 이 단정이 영영 빨간 채로 남는다.
    """
    with open(SPEC_PATH, encoding="utf-8") as f:
        text = f.read()
    start = text.index("## 13. 문서 정정")
    end = text.index("### ", start)
    counts = {}
    for line in text[start:end].splitlines():
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1]
        for name in DOC_ANCHOR.findall(cell):
            if name in USER_DOCS:
                counts[name] = counts.get(name, 0) + 1
    return counts


def test_the_corrections_table_matches_the_spec_chapter_that_owns_it():
    """CORRECTIONS의 **개수를 spec 13장에서 뽑는다.** 한 쌍이 조용히 빠지지 않는다.

    양쪽을 함께 지워야 통과하는데, 그러면 그것은 **의도된 결정**이고 spec이 그 결정의
    자리다. 이 단정이 말하는 것은 개수뿐이다 — 표의 **내용**이 옳은지는 위 파라미터화된
    테스트가 문서마다 잰다.

    **한국어 두 문서가 함께 묶인다.** spec의 한 행이 `backup-readme.md`와
    `backup-readme.ko.md`를 함께 지목하므로, 한국어 쪽만 지우면 그 문서의 개수가 줄어
    여기서 죽는다 — KICKOFF 5장이 *"같은 언어의 두 문서를 똑같이 고치는 산문 편집이
    잡히지 않는다"* 고 적은 자리의 한국어 절반이다.
    """
    counts = spec_correction_counts()
    # **선택자가 비면 스스로 실패한다.** 슬라이스나 정규식이 낡아 아무것도 못 뽑으면
    # 아래 비교가 `{} == {...}`로 죽는다 — 조용히 0회 순회하고 초록이 되지 않는다.
    assert set(counts) == set(USER_DOCS), (
        "spec 13장 첫 표가 사용자 문서 넷을 다 지목하지 않는다: %s" % sorted(counts))
    assert {name: len(pairs) for name, pairs in CORRECTIONS.items()} == counts, (
        sorted(CORRECTIONS.items()), sorted(counts.items()))


@pytest.mark.parametrize("name,stale,fixed", PAIRS,
                         ids=["%s:%d" % (n, i) for n in CORRECTIONS
                              for i in range(len(CORRECTIONS[n]))])
def test_user_doc_says_the_new_thing_and_not_the_old(name, stale, fixed):
    """13장 — 한 곳만 고치면 나머지가 옛 서술을 계속 말한다.

    "통째로 덮어쓴다"는 이제 거짓이고, "민감 정보 제외"도 거짓이다 — pluginConfigs를
    **마스킹해서** 싣기 때문이다.
    """
    text = read_doc(name)
    if fixed is not None:
        assert fixed in text, "%s: 정정 문안이 없다 — %r" % (name, fixed)
    assert stale not in text, "%s: 옛 서술이 남아 있다 — %r" % (name, stale)


@pytest.mark.parametrize("name", sorted(USER_DOCS))
def test_user_doc_says_plugins_json_merges_key_by_key(name):
    """`plugins.json`을 **이름으로 지목해서** 말해야 한다.

    "키 단위"·"key by key"만 찾으면 같은 문서의 `mcp-servers.json` 문단이 항상 걸려,
    플러그인 쪽 문장이 통째로 사라져도 통과한다.
    """
    text = read_doc(name)
    korean = name.endswith(".ko.md")
    phrase = "키 단위" if korean else "key by key"
    hits = [line for line in text.splitlines()
            if "plugins.json" in line and phrase in line]
    assert hits, "%s: `plugins.json`이 %s로 병합된다는 문장이 없다" % (name, phrase)


# 정정 **전** 문서를 축자로 인용하는 저장소 내 문서 셋. 바늘의 값을 여기에 묶는다.
# **셋 다 실어야 한다** — 어느 하나만 빼도 묶이지 않는 바늘이 생긴다(실측).
# `2026-08-20-mcp-integration.md`는 커밋 하나뿐인 완결 문서이고, spec은 plan ③이 13장을
# 고친다. 이 plan 본문은 여전히 편집되지만 인용을 담은 Task 15의 Step 1 초안과 규정 결함
# 기록은 이력이라 바뀌지 않는다.
NEEDLE_SOURCES = (
    os.path.join(ROOT, "docs", "superpowers", "plans", "2026-08-20-mcp-integration.md"),
    os.path.join(ROOT, "docs", "superpowers", "plans", "2026-08-25-plugins-sync-body.md"),
    SPEC,
)


def test_every_stale_needle_is_quoted_by_a_source_document():
    """바늘의 **값**을 잠근다 — `not in` 가드는 바늘이 틀리면 초록이기 때문이다.

    바늘 하나를 무의미한 값으로 바꾸면 원천이 그것을 인용하지 않아 여기서 죽는다.
    `NEEDLE_SOURCES`에서 문서 하나를 빼는 것도 같은 대조에서 죽는다(다섯째 축).

    **면제 목록이 없다.** 초판은 `민감 정보 미포함` 하나를 예외로 뒀는데, 그 문구는
    이 plan 본문의 Step 1 초안에 축자로 있었다 — 원천을 전수로 훑지 않고 예외를
    인정했던 것이다.
    """
    text = ""
    for path in NEEDLE_SOURCES:
        assert os.path.isfile(path), "원천 문서가 없다 — 옮겼거나 이름이 바뀌었다: %s" % path
        with open(path, encoding="utf-8") as f:
            text += f.read() + "\n"
    unsourced = sorted(stale for _, stale, _ in PAIRS if stale not in text)
    assert unsourced == [], (
        "원천이 인용하지 않는 바늘이 있다: %s\n"
        "사용자 문서가 아니라 **원천 문서**가 바뀌었을 수 있다 — 그때는 CORRECTIONS의 "
        "바늘이 아니라 NEEDLE_SOURCES 쪽을 확인한다." % unsourced)


def spec_limit_bullets():
    """spec 13장 "새로 적어야 할 한계" 절의 불릿. 새 한계 목록의 진실 원천이다."""
    with open(SPEC, encoding="utf-8") as f:
        text = f.read()
    head = "### 새로 적어야 할 한계"
    assert head in text, "spec에서 %r 절을 찾지 못했다 — 제목이 바뀌었다" % head
    i = text.index(head)
    m = re.compile(r"\n(?:#{2,3}) |\n---\n").search(text, i + 1)
    sec = text[i:m.start() if m else len(text)]
    return [line for line in sec.splitlines() if line.startswith("- ")]


def doc_limit_bullets(name):
    """문서의 새 한계 목록. 머리말 뒤부터 불릿이 아닌 산문·헤딩을 만날 때까지.

    **빈 줄로 끊지 않는다.** 불릿 사이에 빈 줄이 들어간 loose list는 렌더링 결과가
    같은데, 빈 줄에서 멈추면 내용이 하나도 안 바뀐 편집이 개수 단정을 깨뜨린다(실측).
    """
    text = read_doc(name)
    anchor = LIMITS_ANCHOR[name]
    assert anchor in text, "%s: 새 한계 목록의 머리말(%r)이 없다" % (name, anchor)
    out = []
    for line in text[text.index(anchor) + len(anchor):].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            break
        out.append(stripped)
    return out


def test_spec_still_lists_seven_new_limits():
    """진실 원천이 스스로 좁아지는 것을 막는다 — 추출이 빈 목록을 내면 아래가 공허해진다."""
    assert len(spec_limit_bullets()) == 7, spec_limit_bullets()


@pytest.mark.parametrize("name", sorted(USER_DOCS))
def test_user_doc_lists_every_new_limit(name):
    """한계를 적지 않으면 사용자가 "동기화되겠지"라고 믿는다.

    개수를 **spec에서 뽑아** 맞춘다 — 문서마다 손으로 센 숫자를 두면 한 항목이 빠져도
    아무도 알아채지 못한다. 네 문서 중 하나만 빠뜨리는 것도 여기서 드러난다.
    """
    assert len(doc_limit_bullets(name)) == len(spec_limit_bullets()), doc_limit_bullets(name)


# 새 한계 중 **코드가 이름을 소유한** 둘. 문서가 그 이름을 부르지 않으면 사용자는 무엇을
# 찾아야 하는지 모른다. 어댑터에서 **뽑고 값을 핀한다** — 코드가 그 필드를 더 이상
# pop하지 않으면 추출이 죽고, 이름이 바뀌면 핀이 죽어 문서와 함께 고치도록 강제한다.
# ("가드가 따라간다"가 아니다 — 따라가면 문서가 낡은 채로 초록이 된다.)
_AUTO_UPDATE_MATCH = re.search(
    r'\.pop\("([A-Za-z]+)", None\)', inspect.getsource(pc._drop_auto_update))
assert _AUTO_UPDATE_MATCH, "_drop_auto_update에서 pop하는 필드 이름을 뽑지 못했다"
AUTO_UPDATE_FIELD = _AUTO_UPDATE_MATCH.group(1)
HELD_FILE = os.path.basename(pc.DEFAULT_HELD)


def limit_tokens(name):
    """새 한계 목록의 백틱 토큰. 언어를 가로질러 비교할 수 있는 유일한 서명이다."""
    return [tok for bullet in doc_limit_bullets(name)
            for tok in re.findall(r"`([^`]+)`", bullet)]


def test_the_two_language_pairs_carry_the_same_limits():
    """같은 언어의 두 문서는 **같은 일곱 항목**을 적어야 한다.

    개수만 잠그면 항목의 **내용**이 어떤 값으로도 바뀔 수 있다 — 실측으로, 한 불릿을
    다른 불릿의 복제로 바꾸거나 *"평문으로 동기화되므로 복원 시 다시 입력할 필요가
    없다"* 는 **정반대의 보안 서술**로 바꿔도 스위트 전체가 통과했다. 이 task의 명제가
    "한 곳만 고치면 나머지가 옛 서술을 계속 말한다"이므로, 정정 여덟 곳에 세운 것과 같은
    잠금을 새로 쓴 일곱 곳에도 세운다.
    """
    assert doc_limit_bullets("README.md") == doc_limit_bullets("backup-readme.md")
    assert doc_limit_bullets("README.ko.md") == doc_limit_bullets("backup-readme.ko.md")


def test_the_limits_carry_the_same_tokens_across_languages():
    """한↔영을 가로지르는 서명. 위 짝 비교는 **한 언어의 두 문서를 함께** 고치면 죽는다.

    산문은 언어가 달라 비교할 수 없지만 백틱 토큰은 같아야 한다 — 항목을 더하거나
    빼거나 복제하면 여기서 드러난다.

    **서명이 비어 있으면 이 단정은 공허하다.** 코드가 이름을 소유한 둘을 함께 요구해
    `limit_tokens`가 아무것도 뽑지 못하는 상태를 막는다.
    """
    tokens = limit_tokens("README.md")
    assert AUTO_UPDATE_FIELD in tokens, tokens
    assert any(HELD_FILE in tok for tok in tokens), tokens
    assert tokens == limit_tokens("README.ko.md")


@pytest.mark.parametrize("name", sorted(USER_DOCS))
def test_limits_name_the_tokens_the_code_owns(name):
    assert AUTO_UPDATE_FIELD == "autoUpdate", AUTO_UPDATE_FIELD
    assert HELD_FILE == "plugins-held.json", HELD_FILE
    bullets = "\n".join(doc_limit_bullets(name))
    for token in (AUTO_UPDATE_FIELD, HELD_FILE):
        assert token in bullets, "%s: 새 한계가 `%s`를 부르지 않는다" % (name, token)


# --- `.syncignore`: 문서가 드는 예시가 실제로 무언가를 제외하는가 ---

def syncignore_patterns(text):
    """`.syncignore` 예시 fence의 패턴 줄. 주석과 빈 줄은 뺀다."""
    i = text.index(".syncignore")
    m = re.compile(r"```\n(.*?)```", re.S).search(text, i)
    assert m, ".syncignore 예시 블록을 찾지 못했다"
    return [line.strip() for line in m.group(1).splitlines()
            if line.strip() and not line.strip().startswith("#")]


def test_the_syncignore_example_is_the_same_in_every_document():
    """세 문서가 **같은** 예시를 싣는다.

    갈리면 한 곳만 고친 정정이 나머지 두 곳에 동작하지 않는 예시를 남긴다. 실행해서
    재는 것은 test_skill_wiring.py의 test_syncignore_examples_actually_exclude_something
    하나이므로, 그 검사를 받지 않는 사본이 생기는 것이 정확히 이 결함의 형태다.
    """
    with open(SYNCIGNORE_SOURCE, encoding="utf-8") as f:
        expected = syncignore_patterns(f.read())
    assert expected, "SKILL.md의 예시가 비었다"
    for name in ("README.md", "README.ko.md"):
        assert syncignore_patterns(read_doc(name)) == expected, name


# `.syncignore`의 **뜻**을 사용자 문서가 말하는가.
#
# 규정의 정본은 `lib/syncignore.py` 모듈 docstring이다 — "올리지 않는다", backup 방향
# 전용. 세 스킬의 행동이 거기서 유도된다. 사용자에게 도달하는 절반이 README 두 벌이라
# 여기서 잰다. **바늘을 문구에만 두지 않는다** — 산문만 보는 검사는 코드가 반대로
# 바뀌어도 초록이므로, "restore가 무시한다"는 절반은 reconcile_restore.py가
# `.syncignore`를 부르지 않는다는 **코드 사실**에 묶는다.
RESTORE_RECONCILE = os.path.join(
    ROOT, "plugins", "claude-sync", "skills", "sync-restore", "scripts",
    "reconcile_restore.py")
SYNCIGNORE_LIB = os.path.join(
    ROOT, "plugins", "claude-sync", "lib", "syncignore.py")

SYNCIGNORE_MEANING = {
    "README.md": (
        '**`.syncignore` means one thing — "do not upload" — and it applies to the '
        'backup direction only.**',
        "**Restore ignores `.syncignore`.**",
        "**Excluding a path does not protect the local file from being overwritten**",
    ),
    "README.ko.md": (
        '**`.syncignore`의 뜻은 "올리지 않는다" 하나이고, backup 방향에만 적용됩니다.**',
        "**복원은 `.syncignore`를 무시합니다.**",
        "**경로를 제외해도 로컬 파일이 덮어쓰이지 않게 보호되지는 않습니다**",
    ),
}


def test_restore_really_does_ignore_syncignore():
    """문서가 말하는 "restore는 무시한다"를 **코드에서** 잰다.

    reconcile_restore.py가 `.syncignore`를 보기 시작하면 여기가 빨개진다 — 그때
    고칠 것은 이 단정이 아니라 `lib/syncignore.py`의 정본과 아래 두 README다.
    이 저장소가 반복해서 만난 형태가 "문장이 코드와 어긋난다"이므로, 결정을 산문에만
    두지 않는다.
    """
    with open(RESTORE_RECONCILE, encoding="utf-8") as f:
        src = f.read()
    # 산문의 언급이 아니라 **쓰는 것**을 본다 — docstring에 이름이 나왔다고 죽으면
    # 다음 사람이 이 단정을 못 믿게 되고, 그러면 가드가 아니라 소음이 된다.
    assert "import syncignore" not in src and "syncignore." not in src, (
        "reconcile_restore.py가 `.syncignore`를 쓴다 — 결정이 바뀌었다면 "
        "lib/syncignore.py의 정본과 README 두 벌을 함께 고친다")
    # **정본이 코드와 같은 말을 하는가.** 정본이 뒤집히면 그것을 읽고 유도하는 다음
    # 사람이 restore·status를 반대로 고친다 — 이 라운드의 출발점이 바로 그 형태였다.
    with open(SYNCIGNORE_LIB, encoding="utf-8") as f:
        canon = f.read()
    assert "**restore — 무시한다(결정).**" in canon, (
        "lib/syncignore.py의 정본이 restore의 결정을 적지 않는다 — 코드는 무시한다")


CANON_POINT = re.compile(r"^(\d+)\. ", re.M)


def syncignore_canonical_points():
    """정본(`lib/syncignore.py`)이 **README가 말해야 한다고 정한** 항목들.

    앞 판은 개수를 `== 3`으로 적어 두었고, 그러면 한 문장을 지우면서 그 숫자도 함께
    줄이는 편집이 통과한다. 정본에 번호 목록을 두고 여기서 뽑는다 — 항목이 늘면 두
    README와 위 표를 함께 고쳐야 이 단정이 초록이 된다.
    """
    with open(SYNCIGNORE_LIB, encoding="utf-8") as f:
        text = f.read()
    start = text.index("**README 두 벌이 말해야 하는 것**")
    end = text.index("**왜 여기 있는가.**", start)
    points = CANON_POINT.findall(text[start:end])
    assert points, "정본에서 번호 목록을 뽑지 못했다 — 앵커가 낡았다"
    return points


@pytest.mark.parametrize("name", sorted(SYNCIGNORE_MEANING))
def test_readme_states_what_syncignore_means(name):
    """세 문장이 함께 있어야 뜻이 온전하다.

    "올리지 않는다"만 적으면 사용자는 복원도 막힌다고 읽고, 제외한 경로의 로컬 파일이
    레포 내용으로 덮어쓰일 수 있다는 것을 모른 채 `/sync-restore`를 돌린다. 개수를
    함께 걸어 한 문장이 조용히 빠지는 것을 막는다.
    """
    assert len(SYNCIGNORE_MEANING[name]) == len(syncignore_canonical_points())
    text = read_doc(name)
    for phrase in SYNCIGNORE_MEANING[name]:
        assert phrase in text, "%s: %r" % (name, phrase)


# (문서, 옛 문구, 정정 문안). CORRECTIONS와 같은 짝 형태이지만 그 표에 넣지 않는다 —
# 그쪽 바늘은 저장소 안의 **원천 문서가 인용한 것**이어야 하고, 이 두 문구는 정정 전
# README에만 있었을 뿐 어느 원천도 인용하지 않는다. 개수는 아래에서 함께 건다.
SYNCIGNORE_WORDING = [
    ("README.md", "(gitignore format)", "**glob patterns, one per line**"),
    ("README.ko.md", "(gitignore 형식)", "**한 줄에 하나씩 glob 패턴**"),
]


@pytest.mark.parametrize("name,stale,fixed", SYNCIGNORE_WORDING,
                         ids=[n for n, _, _ in SYNCIGNORE_WORDING])
def test_readme_does_not_call_syncignore_a_gitignore(name, stale, fixed):
    """*"gitignore 형식"* 은 코드와 어긋난다 — 부정(`!`)도, 디렉토리 의미도 없다.

    `not in` 가드는 바늘이 틀려도 초록이므로 정정 문안과 **짝지어** 건다(CORRECTIONS와
    같은 처방). 사용자가 이 말을 믿고 gitignore 습관대로 후행 슬래시를 붙이면 그 줄은
    아무것도 제외하지 않고, `.syncignore`로 민감 파일을 걸렀다고 믿은 채 push한다.
    """
    assert len(SYNCIGNORE_WORDING) == 2
    text = read_doc(name)
    assert fixed in text, "%s: 정정 문안이 없다 — %r" % (name, fixed)
    assert stale not in text, "%s: 옛 서술이 남아 있다 — %r" % (name, stale)


# --- 스킬 표의 `/sync-restore` 행 ---

# 표는 README의 **첫 화면**이다. 여기서 "충돌 시 중단"이라고 말하면 사용자는 "충돌이
# 있으면 아무것도 안 일어난다"로 읽고 restore를 돌린다. 실제로는 reconcile_restore.py
# --apply가 add/overwrite/keep/auto_merge를 **전부 적용하고** 겹친 것만 남기며, 같은
# 파일의 충돌 문단이 이미 그렇게 적고 있다 — 한 문서가 같은 사실을 반대로 말했다.
RESTORE_ROW_HEAD = "| `/sync-restore` |"
RESTORE_ROW_WORDING = {"README.md": "left untouched", "README.ko.md": "그대로 보존"}
RESTORE_ROW_BANNED = {"README.md": "aborts safely on conflicts",
                      "README.ko.md": "충돌 시 안전 중단"}


def test_the_skill_table_documents_are_derived_from_disk():
    """표를 가진 문서 목록이 손으로 고른 것이면 한 줄을 지워 검사에서 빼낼 수 있다."""
    found = {name for name in USER_DOCS if RESTORE_ROW_HEAD in read_doc(name)}
    assert found == set(RESTORE_ROW_WORDING) == set(RESTORE_ROW_BANNED), sorted(found)


@pytest.mark.parametrize("name", sorted(RESTORE_ROW_WORDING))
def test_skill_table_matches_the_conflict_behavior_the_same_file_describes(name):
    """표의 restore 설명이 **같은 파일의 충돌 문단**과 같은 말을 해야 한다.

    바늘의 값을 같은 문서에 묶는 것이 요점이다 — 표 한 줄만 보는 검사는 어떤 문구로
    바꿔도 통과시킬 수 있다(실측: 이 줄을 다른 거짓으로 바꾸는 변조가 SURVIVED였다).
    """
    text = read_doc(name)
    rows = [line for line in text.splitlines() if line.startswith(RESTORE_ROW_HEAD)]
    assert len(rows) == 1, rows
    assert RESTORE_ROW_BANNED[name] not in rows[0], rows[0]
    phrase = RESTORE_ROW_WORDING[name]
    assert phrase in rows[0], (name, phrase)
    bullets = [line for line in text.splitlines()
               if line.startswith("- ") and phrase in line]
    assert bullets, "%s: 충돌 문단이 %r를 말하지 않는다 — 바늘이 낡았다" % (name, phrase)


# --- `sync-metadata.json`이 실제로 무엇에 쓰이는가 (진실 쪽 단정) ---

LIB_DIR = os.path.join(ROOT, "plugins", "claude-sync", "lib")
SKILLS_DIR = os.path.join(ROOT, "plugins", "claude-sync", "skills")


def production_sources():
    """lib/과 세 스킬의 scripts/에 있는 프로덕션 .py 전체. (경로, 소스)."""
    dirs = [LIB_DIR] + [os.path.join(SKILLS_DIR, n, "scripts")
                        for n in sorted(os.listdir(SKILLS_DIR))
                        if os.path.isdir(os.path.join(SKILLS_DIR, n, "scripts"))]
    out = []
    for d in dirs:
        for name in sorted(os.listdir(d)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(d, name), encoding="utf-8") as f:
                out.append((os.path.join(d, name), f.read()))
    assert len(out) >= 10, "프로덕션 소스를 못 찾았다 — 디렉토리 구조가 바뀌었다"
    return out


# 프로덕션에서 `"files"`라는 키 이름을 쓰는 파일과, 그것이 metadata의 맵인지.
# **이름만 더해서는 통과하지 못한다** — 아래 단정이 "metadata를 열지 않는다"를 코드에서
# 다시 잰다. 목록이 스스로 줄어드는 것은 위 production_sources의 개수 단정이 막는다.
FILES_KEY_OWNERS = {
    "generate_metadata.py": "sync-metadata.json의 files 맵을 **쓰는** 쪽이다",
    "detect_downgrade.py": "자기 출력의 relpath 맵 이름이다. metadata와 무관하다",
}


def test_no_production_code_reads_the_metadata_files_map():
    """`sync-metadata.json`의 `files` 맵은 **쓰기만 하고 아무도 읽지 않는다.**

    이 단정이 있는 이유는 문서가 아니라 **가드의 실패 이력**이다. plan ②의 최종
    리뷰가 옛 거짓("파일별 수정 시각")을 고치면서 *"3-way 충돌 감지용"* 이라는 새
    거짓을 넣었고, 위 CORRECTIONS가 그것을 **정정 문안으로 등록**해 거짓이 정답으로
    잠겼다. 문안만 바꾸면 같은 일이 반복되므로, 문서가 말하는 것을 **코드에서** 잰다.

    `backup-readme*.md`는 사용자의 백업 레포로 복사되는 파일이다 — 레포를 클론한
    사람이 처음 읽는 문서가 동작 모델을 틀리게 말하면 안 된다.

    여기가 빨개졌다면 `files` 맵에 소비자가 생긴 것이니, 위 두 파일의
    `sync-metadata.json` 줄("기록일 뿐 판정 입력이 아니다")을 **함께** 고친다.

    **`"files"`라는 이름을 쓴다고 곧 metadata의 소비자는 아니다.** 이름만으로 걸면
    자기 출력에 같은 이름을 쓰는 스크립트가 생길 때 이 가드를 지우고 싶어진다.
    그래서 목록에 이름을 더하는 것만으로는 통과하지 못하게, 쓰는 쪽
    (`generate_metadata.py`) 말고는 **소스에 표식 파일 이름의 리터럴도 `load_metadata(`
    호출도 없다**를 함께 건다.

    **이것은 텍스트 검사다.** 경로를 상수 심볼로만 조립하는 미래 소비자는 이 두 바늘을
    피할 수 있다. 그래도 조용한 fail-open은 아니다 — 그런 파일도 `"files"`를 쓰는 한
    위 목록에 이름을 **명시적으로** 더해야 통과하고, 그 순간 사람이 판단을 하게 된다.
    """
    mentions = [(path, src) for path, src in production_sources() if '"files"' in src]
    names = sorted(os.path.basename(p) for p, _ in mentions)
    assert names == sorted(FILES_KEY_OWNERS), names
    writer = os.path.join(BACKUP_SCRIPTS, "generate_metadata.py")
    src = open(writer, encoding="utf-8").read()
    assert 'metadata = {"files"' in src, "generate_metadata.py가 더 이상 쓰는 쪽이 아니다"
    for path, other in mentions:
        if os.path.basename(path) == "generate_metadata.py":
            continue
        # 바늘을 compat에서 뽑는다 — 리터럴을 적으면 파일 이름이 바뀌어도 초록이다.
        assert compat.METADATA_RELPATH not in other, path
        assert "load_metadata(" not in other, path


def test_the_only_metadata_reader_reads_the_version_markers():
    """표식 파일을 **여는** 프로덕션 코드는 compat 하나이고, 거기서 읽는 것은 버전 표식뿐.

    `min_reader_version`이 게이트이고 `written_by_version`은 메시지용이다. 파일
    해시는 어느 쪽도 아니다 — 그것이 backup-readme가 말해야 하는 사실이다.
    """
    readers = [os.path.basename(path) for path, src in production_sources()
               if "load_metadata(" in src]
    assert sorted(readers) == ["compat.py"], readers
    with open(os.path.join(LIB_DIR, "compat.py"), encoding="utf-8") as f:
        fields = set(re.findall(r'meta\.get\("([a-z_]+)"', f.read()))
    assert fields == {"min_reader_version", "written_by_version"}, fields


THREE_WAY_CONSUMERS = {
    "sync-status": "check_status.py",
    "sync-restore": "reconcile_restore.py",
    "sync-backup": "reconcile_backup.py",
}


def test_the_three_way_consumer_table_covers_every_skill():
    """표에서 스킬 하나를 빼면 그 스크립트가 조용히 검사에서 사라진다(실측 — 항목을
    지워도 스위트 전체가 통과했다).

    세 스킬이 전부 3-way 판정을 하므로 디스크의 스킬 목록과 짝짓는다. 새 스킬이
    생기면 여기가 빨개져 "그 스킬은 무엇을 기준선으로 쓰는가"를 묻게 한다.
    """
    skills = {n for n in os.listdir(SKILLS_DIR)
              if os.path.isfile(os.path.join(SKILLS_DIR, n, "SKILL.md"))}
    assert set(THREE_WAY_CONSUMERS) == skills, sorted(
        set(THREE_WAY_CONSUMERS).symmetric_difference(skills))


@pytest.mark.parametrize("skill", sorted(THREE_WAY_CONSUMERS))
def test_three_way_input_is_the_per_device_base(skill):
    """3-way 판정의 실제 입력은 기기별 base 블롭이다 — 세 스크립트가 전부 base_hash를 쓴다.

    위 두 단정은 "표식이 아니다"를 말할 뿐이라, 그것만으로는 문서가 대신 무엇을
    적어야 하는지가 비어 있다. 여기가 그 자리를 채운다.
    """
    path = os.path.join(SKILLS_DIR, skill, "scripts", THREE_WAY_CONSUMERS[skill])
    with open(path, encoding="utf-8") as f:
        src = f.read()
    assert "base_hash(" in src, path
    assert "sync-metadata" not in src, "%s가 표식 파일을 읽는다" % path


@pytest.mark.parametrize("name", ["backup-readme.md", "backup-readme.ko.md"])
def test_backup_readme_points_at_the_sync_state_base(name):
    """백업 레포 README가 3-way의 입력을 **이름으로** 지목해야 한다.

    "이 파일이 아니다"만 적으면 클론한 사람은 그럼 무엇인지 알 수 없고, 위
    CORRECTIONS의 바늘은 그 절반을 재지 않는다.

    **한 줄 안에서 찾는다.** 초판은 파일 전체에서 `.sync-state/`를 찾았는데, 새 한계
    목록의 `plugins-held.json` 줄이 항상 걸려 이 문장에서 지목을 빼도 통과했다
    (변조 실측 — 공허한 단정이었다).
    """
    hits = [line for line in read_doc(name).splitlines()
            if "sync-metadata.json" in line and ".sync-state/" in line]
    assert len(hits) == 1, (
        "%s: `sync-metadata.json` 줄이 3-way의 기준선을 지목하지 않는다: %s"
        % (name, hits))


# --- 2.x 배포 순서 경고 (spec 11.2 · 13장) ------------------------------------
#
# 11.2가 *"배포 순서가 **유일한** 방어"*라고 선언한다 — 2.x에는 `min_reader_version`
# 가드 코드 자체가 없어 표식을 **읽지 못한다.** 나머지 층(형태 판정·다운그레이드 대화)은
# 전부 사고 **뒤**의 탐지이고, 사고가 일어나지 않게 하는 것은 이 경고 산문 하나다.
#
# 그런데 정정 전에는 그 경고가 **전부 `mcp-servers.json` 이야기만** 했다. MCP를 쓰지 않는
# 사용자는 "나에겐 해당 없음"으로 읽고 2.x 기기에서 백업을 돌린다.
#
# **`sync-backup/SKILL.md`가 왜 이 파일에 섞이는가.** 이 파일 머리말이 세운 경계 —
# SKILL.md의 서술은 `test_skill_wiring.py` — 는 여전히 유효하다. 그쪽이 재는 것은
# **배선 계약**(무엇을 어떤 순서로 부르는가)이다. 배포 순서 경고는 배선이 아니라
# **사용자가 읽는 같은 한 경고가 다섯 파일에 흩어진 것**이라, 표를 두 파일로 가르면
# 한쪽만 낡는다. 하나의 불변식은 하나의 표로 건다.
#
# **아래 표들의 규칙은 하나다.** `DEPLOY_ORDER_ANCHOR`만 parametrize의 원천이므로
# **완전성 단정이 필요하다**(표가 줄면 케이스가 조용히 사라진다). 나머지 바늘 표는 전부
# `needle()`로만 읽으며, 행이 없으면 그 자리에서 죽으므로 완전성 단정을 따로 두지 않는다
# — 가드를 지키는 별도의 가드를 만들지 않는다(기준 ⑵).
DEPLOY_ORDER_SKILL = "sync-backup/SKILL.md"

# 경고가 사는 절의 제목. 제목은 **재는 대상이 아니라 위치 지목**이고, 사라지면 아래
# 추출기가 스스로 죽는다.
#
# **접두사가 아니라 제목 전체를 적는다.** 접두사만 핀하면 뒷부분을 개명해도 추출이
# 계속 성공하고, 그 제목을 인용하는 상호참조(backup-readme 둘)가 조용히 낡는다
# — Task 5의 I6과 같은 형태다.
DEPLOY_ORDER_ANCHOR = {
    "README.md": "## Upgrading to v3.0.0 (read this first)",
    "README.ko.md": "## v3.0.0으로 올릴 때 (먼저 읽으세요)",
    "backup-readme.md": "### Before backing up: every machine must be on v3.0.0",
    "backup-readme.ko.md": "### 백업하기 전에: 모든 기기가 v3.0.0이어야 합니다",
    DEPLOY_ORDER_SKILL: "### 12. 결과 보고",
}

# 「나에겐 해당 없음」 오독을 닫는 문구. **이 task의 존재 이유가 정확히 이것이다** —
# 문제는 "손실 목록에 `plugins.json`이 없다"가 아니라 "MCP를 쓰지 않는 사용자가 이
# 경고를 자기 얘기로 읽지 않는다"였다. 훑는 독자는 절 제목과 머리 문장만 본다.
#
# 다섯 문서가 각각 다른 문장으로 쓴다 — 독자와 맥락이 다르므로 **의도된 것이다.**
# 그래서 문구는 문서별로 적되 **자리는 기계로 건다**(deploy_order_prose) — 불릿이 아니라
# 경고의 **산문** 안에 있어야 한다. 한 문서의 불릿 속으로 밀려나면 그 문서를 이미 자기
# 얘기로 읽은 사람만 만나게 되어 아무것도 예방하지 못한다.
DEPLOY_ORDER_NO_MCP = {
    "README.md": "even if you use no MCP servers",
    "README.ko.md": "MCP 서버를 하나도 쓰지 않더라도",
    "backup-readme.md": "even if that machine uses no MCP servers",
    "backup-readme.ko.md": "MCP 서버를 하나도 쓰지 않더라도",
    DEPLOY_ORDER_SKILL: "MCP 서버를 쓰지 않는 기기라도 해당됩니다",
}

# 손실의 두 절반. **불릿마다 둘 다** 있어야 한다.
#
# ① 타 기기 것이 사라진다 — 2.x는 두 문서를 **그 기기 것만으로 통째로** 다시 만든다
#    (plugins는 `settings.json`에서, mcp는 `claude mcp list` 출력에서 — 실측).
#    정정 전 mcp 불릿은 이 절반을 빼놓았고, 그 빈틈을 몇 줄 아래 "서버 이름 키 단위로
#    병합되므로 타 기기 서버가 사라지지 않는다"가 **조건 없이** 반대로 메우고 있었다.
# ② 그 기기 것까지 사라진다 — 2.x가 아예 모르는 키(plugins)와 파싱하지 못하는 서버(mcp).
#
# **동사를 바늘에 포함시킨다.** 범위만 재면 "사라진다"를 "보존된다"로 한 단어 뒤집어도
# 초록이다(리뷰어 변조 R3).
DEPLOY_ORDER_OTHERS = {
    "README.md": "**only on another machine** are erased from the repo",
    "README.ko.md": "**다른 기기에만** 있는 것이 레포에서 사라지고",
    "backup-readme.md": "**only on another machine** are erased from the repo",
    "backup-readme.ko.md": "**다른 기기에만** 있는 것이 레포에서 사라지고",
    DEPLOY_ORDER_SKILL: "**다른 기기에만** 있는 것이 레포에서 사라지고",
}
DEPLOY_ORDER_SCOPE = {
    "README.md": "are erased **including that machine's own**",
    "README.ko.md": "**그 기기 것까지** 사라집니다",
    "backup-readme.md": "are erased **including that machine's own**",
    "backup-readme.ko.md": "**그 기기 것까지** 사라집니다",
    DEPLOY_ORDER_SKILL: "**그 기기 것까지** 사라집니다",
}

# 표식이 **오늘 아무도 막지 못한다**는 사실. `compat._block_reason`은 `mine < required`
# 일 때만 막고 표식 값은 `MIN_READER_VERSION`이므로 그 버전 기기는 통과한다 — 즉
# 막아야 할 2.x는 읽지 못하고, 읽는 v3은 충족한다. "v3 기기가 표식을 읽고 멈춘다"는
# 서술은 그래서 거짓이고, 하필 사용자가 *배포 순서를 지킬 것인가*를 정하는 문단에 있었다.
DEPLOY_ORDER_MARKER = {
    "README.md": "no code that reads the marker",
    "README.ko.md": "그 표식을 읽는 코드가 없습니다",
    "backup-readme.md": "no code that reads the marker",
    "backup-readme.ko.md": "그 표식을 읽는 코드가 없습니다",
    DEPLOY_ORDER_SKILL: "그 표식을 읽는 코드가 없습니다",
}

# 「타 기기 항목은 사라지지 않는다」는 무조건 약속. **v3.0.0 이상끼리일 때만 참이다.**
# 조건 없이 두면, 경고를 읽은 독자가 몇 줄 아래에서 반대 문장을 만나 "그럼 2.x 백업이라도
# 타 기기 것은 남겠네"로 되돌아간다 — 이 task가 없애려던 오독의 재발이다.
MERGE_PROMISE = {
    "README.md": "only exist on another",
    "README.ko.md": "다른 기기에만 있는",
    "backup-readme.md": "only exist on another",
    "backup-readme.ko.md": "다른 기기에만 있는",
}

# **바늘을 손으로 적지 않는다.** 어댑터가 relpath를 개명하면 문서는 낡았는데 손으로 적은
# 바늘은 옛 이름을 계속 만족시킨다 — 그때 이 가드가 조용히 무의미해진다.
DEPLOY_ORDER_RELPATHS = (mc.BACKUP_RELPATH, pc.BACKUP_RELPATH)
assert len(set(DEPLOY_ORDER_RELPATHS)) == 2, DEPLOY_ORDER_RELPATHS

# 2.x가 `plugins.json`에서 **옮기는** 키와 **모르는** 키. 합집합 하나로 재면 두 축이
# 접혀서, 둘을 맞바꾼 문장("v2가 옮기는 것은 pluginConfigs뿐 …")도 초록이 된다.
# 맞바꾼 문장은 사용자에게 "당신의 `pluginConfigs`는 안전하다"고 말한다 — 정확히 거짓이다.
TWO_X_ERASES_EVERYWHERE = tuple(sorted(
    (set(pc.SECTIONS) | set(pc.MARKETPLACE_ALIASES)) - set(TWO_X_CARRIES)))
assert set(TWO_X_CARRIES) <= set(pc.SECTIONS) | set(pc.MARKETPLACE_ALIASES), (
    "2.x가 옮기는 키 이름이 어댑터에 없다 — 핀이 낡았다: %s" % sorted(TWO_X_CARRIES))
assert TWO_X_ERASES_EVERYWHERE, "떨어지는 키가 없다 — 추출이 죽었다"

# 표식 필드 이름을 `compat.py`가 **실제로 읽는 것**에서 뽑는다.
with open(os.path.join(LIB_DIR, "compat.py"), encoding="utf-8") as _f:
    MIN_READER_FIELD = "min_reader_version"
    assert MIN_READER_FIELD in set(re.findall(r'meta\.get\("([a-z_]+)"', _f.read())), (
        "compat.py가 %s를 읽지 않는다 — 필드 이름이 바뀌었다" % MIN_READER_FIELD)

_HEADING = re.compile(r"^#{1,6} ", re.M)
# 불릿 마커에 의존하지 않는다 — `- `만 보면 `* `나 `1. `로 바꾼 편집이 통과한다(변조 R4).
_BULLET = re.compile(r"(?:[-*+]|\d+\.)\s")
# 문장 경계. `settings.json,`·`v2.x`처럼 **뒤에 공백이 없는** 마침표는 자르지 않는다.
_SENTENCE = re.compile(r"(?<=\.)\s+")


def needle(table, name, what):
    """바늘 표의 한 행. 행이 없으면 **그 자리에서** 죽는다(기준 ⑵)."""
    value = table.get(name)
    assert value, "%s: %s 바늘이 표에 없다 — 표가 줄었거나 문서가 새로 들어왔다" % (name, what)
    return value


def deploy_order_path(name):
    if name == DEPLOY_ORDER_SKILL:
        return os.path.join(SKILLS_DIR, *DEPLOY_ORDER_SKILL.split("/"))
    return USER_DOCS[name]


def deploy_order_warning(name):
    """배포 순서 경고 블록 — 지목한 **절 안의 첫 인용 블록**만 자른다.

    파일 전체에서 relpath를 찾으면 안 된다. 다섯 문서 전부가 다른 문단에서 두 이름을
    이미 말하고 있어서, 경고가 통째로 mcp 전용으로 되돌아가도 파일 단위 검사는
    통과한다(불변식 7 — 이 저장소에서 두 번 발동한 결함이다).

    절로 자르는 것도 부족하다. 절 안에서 인용 블록만 남기지 않으면 README의 뒤따르는
    산문과 bash 블록이 같은 절에 있어 다시 가려진다.
    """
    anchor = DEPLOY_ORDER_ANCHOR[name]
    with open(deploy_order_path(name), encoding="utf-8") as f:
        text = f.read()
    assert anchor in text, (
        "%s: 배포 순서 경고의 머리말(%r)이 없다 — 절이 사라졌거나 제목이 바뀌었다"
        % (name, anchor))
    i = text.index(anchor)
    m = _HEADING.search(text, i + len(anchor))
    section = text[i:m.start() if m else len(text)]
    block = []
    for line in section.splitlines():
        if line.startswith(">"):
            block.append(line)
        elif block:
            break
    assert block, "%s: %r 절에 인용 블록이 없다 — 경고가 사라졌다" % (name, anchor)
    return "\n".join(block)


def deploy_order_prose(name):
    """경고 블록에서 **불릿을 뺀** 산문.

    문서별 손실 불릿은 "그 문서를 쓰는 사람"에게만 말한다. 「나에겐 해당 없음」 오독을
    닫는 문장과 표식 사실은 **누구에게나 말하는 자리**에 있어야 한다 — 앞뒤 순서는
    문서마다 다를 수 있으므로(SKILL.md는 지시문 직전에 둔다) 재지 않는다.
    """
    lines = [line for line in deploy_order_warning(name).splitlines()
             if not _BULLET.match(line.lstrip("> "))]
    prose = "\n".join(lines)
    assert prose.strip("> \n"), "%s: 경고에 산문이 없다 — 불릿만 남았다" % name
    return prose


def deploy_order_bullet(name, relpath):
    """경고 블록에서 그 문서를 말하는 불릿 한 줄.

    **relpath로 찾는다** — 손으로 고른 목록이 아니라 두 어댑터 상수 위를 도는 루프다.
    """
    hits = [line for line in deploy_order_warning(name).splitlines()
            if _BULLET.match(line.lstrip("> ")) and relpath in line]
    assert len(hits) == 1, (
        "%s: %s를 말하는 불릿을 하나로 특정하지 못했다(%d개)" % (name, relpath, len(hits)))
    return hits[0]


def sentences_of(text):
    parts = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    assert parts, "문장을 하나도 뽑지 못했다: %r" % text[:60]
    return parts


def section_titled(name, relpath):
    """제목에 그 relpath가 든 절. **언어별 제목을 손으로 적지 않는다.**"""
    text = read_doc(name)
    heads = [line for line in text.splitlines()
             if line.startswith("### ") and relpath in line]
    assert len(heads) == 1, (
        "%s: %s 절 제목을 하나로 특정하지 못했다: %s" % (name, relpath, heads))
    i = text.index(heads[0])
    m = _HEADING.search(text, i + len(heads[0]))
    return text[i:m.start() if m else len(text)]


def test_the_deploy_order_table_covers_every_document_that_carries_the_warning():
    """표에서 문서 하나를 빼면 그 파일이 아래 가드 전부에서 조용히 사라진다(다섯째 축).

    사용자 문서 넷은 **디스크에서 뽑은** USER_DOCS와 짝짓는다 —
    `test_user_doc_list_covers_every_doc_on_disk`가 그 목록을 디스크에 묶고 있으므로
    **영어판만 빼는 변조**가 여기서 죽는다. SKILL.md는 "경고를 지닌 스킬"을 디스크에서
    유도할 방법이 없어 이름을 핀하고, 그 파일이 실재하는지만 함께 묻는다.

    **다른 바늘 표에는 완전성 단정을 두지 않는다.** 전부 `needle()`로만 읽혀 행이 없으면
    자기 자리에서 죽기 때문이다 — 가드를 지키는 가드를 만들지 않는다(기준 ⑵).
    """
    expected = set(USER_DOCS) | {DEPLOY_ORDER_SKILL}
    assert set(DEPLOY_ORDER_ANCHOR) == expected, sorted(
        set(DEPLOY_ORDER_ANCHOR).symmetric_difference(expected))
    path = deploy_order_path(DEPLOY_ORDER_SKILL)
    assert os.path.isfile(path), "핀한 SKILL.md가 없다 — 옮겼거나 이름이 바뀌었다: %s" % path


@pytest.mark.parametrize("name", sorted(DEPLOY_ORDER_ANCHOR))
def test_deploy_order_warning_names_both_backed_up_documents(name):
    """경고 하나가 한 문서 이야기만 하면 나머지 문서를 쓰는 사용자는 그냥 지나친다.

    이것이 이 저장소의 **유일한 예방**이다 — 2.x는 표식을 읽지 못하므로 사고를 막을
    코드가 어디에도 없다.
    """
    for relpath in DEPLOY_ORDER_RELPATHS:
        deploy_order_bullet(name, relpath)


@pytest.mark.parametrize("name", sorted(DEPLOY_ORDER_ANCHOR))
def test_every_bullet_says_both_halves_of_the_loss(name):
    """**두 문서가 같은 이유로 같은 손실을 입는다** — 불릿마다 두 절반을 다 적어야 한다.

    정정 전 mcp 불릿은 「옛 배열 형식 + 공백 든 서버」 둘만 적었다. 실측은 더 넓다:
    2.x의 `parse_mcp.py`가 그 기기의 `claude mcp list` 출력만으로 배열을 통째로 만들고
    2.x의 백업 절이 그것을 커밋하므로 **다른 기기에만 등록된 서버도 사라진다.**
    plugins 불릿은 그 손실을 적는데 mcp 불릿만 빼놓으면 사실이 반쪽만 전달되고,
    몇 줄 아래 무조건 약속이 그 빈틈을 반대로 메운다.
    """
    for relpath in DEPLOY_ORDER_RELPATHS:
        bullet = deploy_order_bullet(name, relpath)
        for what, table in (("타 기기 손실", DEPLOY_ORDER_OTHERS),
                            ("그 기기 손실", DEPLOY_ORDER_SCOPE)):
            phrase = needle(table, name, what)
            assert phrase in bullet, (
                "%s: %s 불릿이 %s를 말하지 않는다 — %r" % (name, relpath, what, phrase))


@pytest.mark.parametrize("name", sorted(DEPLOY_ORDER_ANCHOR))
def test_the_plugins_bullet_keeps_the_two_key_sets_apart(name):
    """「2.x가 옮기는 키」와 「2.x가 모르는 키」를 **맞바꿔도** 초록이면 안 된다(축 분리).

    합집합 하나로 `in`만 재면 두 축이 접힌다. 맞바꾼 문장은 사용자에게
    *"당신의 `pluginConfigs`는 안전하다"* 고 말하는데 그것이 정확히 거짓이다.
    두 집합 다 어댑터에서 유도하므로 섹션이 늘면 다섯 문서가 함께 빨개진다.
    """
    bullet = deploy_order_bullet(name, pc.BACKUP_RELPATH)
    scope = needle(DEPLOY_ORDER_SCOPE, name, "그 기기 손실")
    parts = sentences_of(bullet)
    erased = [s for s in parts if scope in s]
    assert len(erased) == 1, (
        "%s: 「그 기기 것까지」를 말하는 문장을 하나로 특정하지 못했다(%d개)"
        % (name, len(erased)))
    erased = erased[0]
    carried = " ".join(s for s in parts if s != erased)
    assert carried, "%s: 2.x가 옮기는 키를 말하는 문장이 없다" % name
    for key in TWO_X_ERASES_EVERYWHERE:
        assert key in erased, "%s: 사라지는 쪽 문장이 %s를 말하지 않는다" % (name, key)
        assert key not in carried, "%s: %s를 「2.x가 옮긴다」 쪽에 적었다" % (name, key)
    for key in TWO_X_CARRIES:
        assert key in carried, "%s: 2.x가 옮기는 키(%s)를 말하지 않는다" % (name, key)
        assert key not in erased, "%s: %s를 「사라진다」 쪽에 적었다" % (name, key)


@pytest.mark.parametrize("name", sorted(DEPLOY_ORDER_ANCHOR))
def test_deploy_order_warning_closes_the_not_applicable_to_me_misreading(name):
    """경고가 **MCP 미사용자를 명시적으로 포함**해야 한다.

    이 저장소의 유일한 예방이 이 한 마디에 달려 있다. 정정 전 넷이 전부
    `mcp-servers.json` 이야기만 했고, 문제는 목록이 짧다는 것이 아니라 **독자가
    자기 얘기로 읽지 않는다**는 것이었다.
    """
    phrase = needle(DEPLOY_ORDER_NO_MCP, name, "MCP 미사용자 포함")
    assert phrase in deploy_order_prose(name), (
        "%s: 경고의 산문이 MCP 미사용자를 포함시키지 않는다(%r). `plugins.json`을 "
        "손실 목록에 더하는 것만으로는 「나에겐 해당 없음」 오독이 닫히지 않는다"
        % (name, phrase))


@pytest.mark.parametrize("name", sorted(DEPLOY_ORDER_ANCHOR))
def test_the_marker_sentence_matches_what_compat_actually_blocks(name):
    """표식 서술을 `compat`의 판정에 묶는다.

    **표식은 오늘 아무 기기도 막지 못한다.** `_block_reason`은 `mine < required`일 때만
    막는데 표식 값이 `MIN_READER_VERSION`이므로 그 버전 기기는 통과하고, 막아야 할
    2.x에는 표식을 읽는 코드가 아예 없다. 그래서 *"v3 기기가 읽고 멈춘다"* 는 서술은
    거짓이고, 하필 사용자가 **배포 순서를 지킬 것인가**를 정하는 문단에 있었다.

    아래 첫 단정이 그 사실을 코드에서 직접 확인한다 — 판정이 바뀌면 이 문단의 서술이
    함께 바뀌어야 하고, 그때 여기가 빨개진다.
    """
    assert compat._block_reason({}, compat.MIN_READER_VERSION,
                                compat.MIN_READER_VERSION) is None, (
        "표식이 같은 버전 기기를 막는다 — 다섯 문서의 표식 문단을 다시 써야 한다")
    prose = deploy_order_prose(name)
    assert MIN_READER_FIELD in prose, (
        "%s: 경고가 표식(%s)을 이름으로 지목하지 않는다" % (name, MIN_READER_FIELD))
    phrase = needle(DEPLOY_ORDER_MARKER, name, "표식을 읽지 못한다")
    assert phrase in prose, (
        "%s: 경고가 「2.x에는 표식을 읽는 코드가 없다」를 말하지 않는다 — 그것이 "
        "*배포 순서가 유일한 방어*의 근거다: %r" % (name, phrase))


@pytest.mark.parametrize("name", sorted(USER_DOCS))
def test_the_merge_promise_names_the_version_it_depends_on(name):
    """「타 기기 항목은 사라지지 않는다」에 **버전 조건**이 붙어야 한다.

    경고를 읽은 독자가 몇 줄 아래에서 무조건 약속을 만나면 "그럼 2.x 백업이라도 타 기기
    것은 남겠네"로 되돌아간다 — 이 task가 없애려던 오독의 재발이고, MCP는 쓰지만 공백
    명령이 없는 사용자에게 특히 그렇다.

    줄 수를 **relpath 개수에서** 뽑는다 — 문서마다 두 문서에 하나씩이므로, 한쪽 약속이
    사라지거나 새 문서가 늘면 여기가 먼저 빨개진다.
    """
    phrase = needle(MERGE_PROMISE, name, "무조건 약속")
    version = "v" + compat.MIN_READER_VERSION
    hits = [line for line in read_doc(name).splitlines() if phrase in line]
    assert len(hits) == len(DEPLOY_ORDER_RELPATHS), (
        "%s: 무조건 약속 줄이 %d개다 — 백업 문서마다 하나여야 한다: %s"
        % (name, len(hits), hits))
    missing = [line for line in hits if version not in line]
    assert not missing, (
        "%s: 무조건 약속에 버전 조건(%s)이 없다: %s" % (name, version, missing))


@pytest.mark.parametrize(
    "name,relpath",
    [(n, r) for n in sorted(USER_DOCS) if n.startswith("backup-readme")
     for r in DEPLOY_ORDER_RELPATHS],
    ids=lambda v: v)
def test_each_document_section_cites_the_deploy_order_section_by_its_full_title(name, relpath):
    """문서별 절 **둘 다** 배포 순서 절을 제목 전체로 가리켜야 한다.

    이 task가 겨냥한 독자는 *MCP를 안 쓰고 플러그인만 쓰는 사용자*다. 그 사람이 찾아
    들어가는 절이 `plugins.json` 절인데 거기서 무조건적인 안전 보장만 만나면, 경고를
    한 번도 보지 못한 채 백업을 돌린다. 상호참조를 mcp 절에만 단 것은 역사적 이유
    (옛 경고가 거기 있었다)이지 독자 때문이 아니었다.

    인용문을 **절 제목 상수에서 유도한다** — 손으로 적으면 제목의 뒷부분을 개명했을 때
    독자가 없는 절을 찾는다(Task 5 I6과 같은 형태). 절도 relpath로 찾아 언어별 제목을
    손으로 적지 않는다.
    """
    title = DEPLOY_ORDER_ANCHOR[name].lstrip("# ").strip()
    assert title, "%s: 절 제목 상수에서 인용할 문자열을 뽑지 못했다" % name
    assert title in section_titled(name, relpath), (
        "%s: %s 절이 배포 순서 절을 제목 전체로 가리키지 않는다 — %r"
        % (name, relpath, title))
