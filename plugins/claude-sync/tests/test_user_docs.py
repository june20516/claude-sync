"""사용자 문서가 `plugins.json`에 대해 말하는 것 (spec 13장 첫 표, "새로 적어야 할 한계").

**왜 test_script_root.py가 아니라 여기인가.** 그 파일은 관심사를 둘 담는다 — SKILL.md의
0단계 bash를 **실행해서** 재는 것과, 세 SKILL.md의 **배선 계약**을 읽어서 재는 것이다.
`README.md`·`README.ko.md`는 스킬도 스크립트도 아니고 `backup-readme*.md`는 백업 레포에
그대로 복사되는 자료 파일이라, 그쪽에 얹으면 간판이 내용을 설명하지 못하는 파일이 하나 더
생긴다. SKILL.md의 서술 정정은 그 파일의 둘째 관심사에 속하므로 그쪽에 남겼다.

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
- CORRECTIONS는 개수를 함께 걸고, 바늘의 값은 원천 문서에 묶는다
- 새 한계의 **항목 수**는 spec 13장의 불릿 수에서 뽑는다
- 새 한계의 **내용**은 같은 언어의 두 문서끼리, 백틱 토큰은 한↔영끼리 대조한다
"""
import inspect
import os
import re

import pytest

import plugin_config as pc   # conftest.py가 lib를 sys.path에 넣는다

ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
BACKUP_SCRIPTS = os.path.join(
    ROOT, "plugins", "claude-sync", "skills", "sync-backup", "scripts")
SPEC = os.path.join(ROOT, "docs", "superpowers", "specs",
                    "2026-08-24-plugins-sync-design.md")
# `.syncignore`의 진실 원천은 **실행되는 쪽**이다 — test_script_root.py가 이 SKILL.md의
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
        "문서를 더했다면 USER_DOCS·LIMITS_ANCHOR·CORRECTIONS 셋에 모두 더하고 "
        "test_the_corrections_table_did_not_shrink의 개수도 함께 고친다."
        % sorted(found.symmetric_difference(USER_DOCS)))
    assert set(CORRECTIONS) == set(USER_DOCS), sorted(
        set(CORRECTIONS).symmetric_difference(USER_DOCS))
    assert set(LIMITS_ANCHOR) == set(USER_DOCS), sorted(
        set(LIMITS_ANCHOR).symmetric_difference(USER_DOCS))


def test_the_corrections_table_did_not_shrink():
    """CORRECTIONS는 **손으로 고른 목록**이라 대조할 외부 진실 원천이 없다.

    그래서 개수만 함께 건다 — 한 쌍을 지우면 그 자리가 아무 소리 없이 검사에서 빠진다.
    영어 3 + 한국어 4(영어판에 없는 예외 문구 삭제가 하나 더 있다) + 백업 README 2 + 2.
    이 단정이 말하는 것은 그것뿐이다 — 표의 **내용**이 옳은지는 재지 않는다.
    """
    assert {name: len(pairs) for name, pairs in CORRECTIONS.items()} == {
        "README.md": 3,
        "README.ko.md": 4,
        "backup-readme.md": 3,
        "backup-readme.ko.md": 3,
    }


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
    재는 것은 test_script_root.py의 test_syncignore_examples_actually_exclude_something
    하나이므로, 그 검사를 받지 않는 사본이 생기는 것이 정확히 이 결함의 형태다.
    """
    with open(SYNCIGNORE_SOURCE, encoding="utf-8") as f:
        expected = syncignore_patterns(f.read())
    assert expected, "SKILL.md의 예시가 비었다"
    for name in ("README.md", "README.ko.md"):
        assert syncignore_patterns(read_doc(name)) == expected, name


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
    """
    writers = [path for path, src in production_sources() if '"files"' in src]
    assert [os.path.basename(p) for p in writers] == ["generate_metadata.py"], writers
    src = open(writers[0], encoding="utf-8").read()
    assert 'metadata = {"files"' in src, "generate_metadata.py가 더 이상 쓰는 쪽이 아니다"


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
    """
    assert ".sync-state/" in read_doc(name), name
