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

**남은 구멍은 하나다.** 옛 문구 쪽 바늘을 아무 데도 없는 값으로 바꾸면 아무도 잡지
못한다(실측 — 스위트 전체가 통과했다). 그러면 "정정 문안과 옛 문장을 **함께** 적는"
편집만 검출을 빠져나간다. 옛 문구를 담은 저장소 내 원천이 없어(정정하고 나면 어디에도
남지 않는다) 그 값을 잠글 방법을 찾지 못했다 — spec 13장 표의 인용문은 축약(`…`)이
섞여 있고 2행은 **남는** 문장을 인용하므로 진실 원천으로 쓸 수 없다.

목록이 스스로 줄어드는 것은 셋으로 막는다.
- USER_DOCS는 디스크에서 뽑은 파일 목록과 대조한다(손으로 고른 목록이 아니다)
- CORRECTIONS는 개수를 함께 건다(외부 진실 원천이 없는 표의 관행)
- 새 한계의 항목 수는 **spec 13장의 불릿 수**에서 뽑는다
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
        ("플러그인/마켓플레이스 목록 (민감 정보 제외)",
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
        # 5행
        ("Plugin/marketplace list (extracted from settings.json, no sensitive data)",
         "plugin config key names (extracted from settings.json; config values masked)"),
        # 6행
        ("`plugins.json`, in contrast, is regenerated and overwritten on every backup.",
         "`plugins.json` is merged the same way, key by key, across its three sections."),
    ),
    "backup-readme.ko.md": (
        ("플러그인/마켓플레이스 목록 (settings.json에서 추출, 민감 정보 미포함)",
         "설정 키 이름 (settings.json에서 추출, 설정 값은 마스킹)"),
        ("반면 `plugins.json`은 매 백업마다 새로 생성되어 덮어쓰입니다.",
         "`plugins.json`도 세 섹션 각각에 대해 같은 방식으로 키 단위 병합됩니다."),
    ),
}

PAIRS = [(name, stale, fixed)
         for name, pairs in CORRECTIONS.items() for stale, fixed in pairs]


def test_user_doc_list_covers_every_doc_on_disk():
    """USER_DOCS를 **디스크에서 뽑은 목록**과 대조한다.

    손으로 고른 목록이면 항목 하나(예: 영어 README)를 지우는 것만으로 그 파일이 아래
    가드 전부에서 조용히 빠진다 — 이 저장소가 반복해서 만난 다섯째 축이다.
    """
    found = {n for n in os.listdir(ROOT) if n.endswith(".md")}
    found |= {n for n in os.listdir(BACKUP_SCRIPTS) if n.startswith("backup-readme")}
    assert found == set(USER_DOCS), sorted(found.symmetric_difference(USER_DOCS))
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
        "backup-readme.md": 2,
        "backup-readme.ko.md": 2,
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


def spec_limit_bullets():
    """spec 13장 "새로 적어야 할 한계" 절의 불릿. 새 한계 목록의 진실 원천이다."""
    with open(SPEC, encoding="utf-8") as f:
        text = f.read()
    i = text.index("### 새로 적어야 할 한계")
    m = re.compile(r"\n(?:#{2,3}) |\n---\n").search(text, i + 1)
    sec = text[i:m.start() if m else len(text)]
    return [line for line in sec.splitlines() if line.startswith("- ")]


def doc_limit_bullets(name):
    """문서의 새 한계 목록. 머리말 바로 뒤에 붙은 연속된 불릿만 센다."""
    text = read_doc(name)
    anchor = LIMITS_ANCHOR[name]
    assert anchor in text, "%s: 새 한계 목록의 머리말(%r)이 없다" % (name, anchor)
    out = []
    for line in text[text.index(anchor) + len(anchor):].splitlines():
        stripped = line.strip()
        if not stripped:
            if out:
                break
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
# 찾아야 하는지 모른다. 바늘을 손으로 적지 않고 어댑터에서 뽑는다 — 이름이 코드에서
# 바뀌면 가드가 따라가고, 뽑지 못하면 그 자리에서 실패한다.
AUTO_UPDATE_FIELD = re.search(
    r'\.pop\("([A-Za-z]+)", None\)', inspect.getsource(pc._drop_auto_update)).group(1)
HELD_FILE = os.path.basename(pc.DEFAULT_HELD)


@pytest.mark.parametrize("name", sorted(USER_DOCS))
def test_limits_name_the_tokens_the_code_owns(name):
    assert AUTO_UPDATE_FIELD == "autoUpdate", AUTO_UPDATE_FIELD
    assert HELD_FILE == "plugins-held.json", HELD_FILE
    bullets = "\n".join(doc_limit_bullets(name))
    for token in (AUTO_UPDATE_FIELD, HELD_FILE):
        assert token in bullets, "%s: 새 한계가 `%s`를 부르지 않는다" % (name, token)
