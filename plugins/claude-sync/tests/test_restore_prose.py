"""`sync-restore/SKILL.md`의 **실행 산문**과 복원 스크립트의 결속.

**왜 이 파일이 필요한가.** 이 제품의 복원을 실제로 실행하는 오케스트레이터는 Python이
아니라 5-1~5-4의 산문이다 — 모델이 그것을 읽고 `claude plugin`을 부른다. 그런데 교대
시나리오(`test_plugin_cycle.py`)가 검증하는 것은 SKILL.md가 아니라 그 **Python
재구현**(`Device`)이라, 산문에서 버킷 이름을 바꿔치기해도 스위트가 전부 초록이었다
(2026-08-28 층 일관성 감사 실측 — 산문 변조 **6종 중 5종 SURVIVED**, 872 passed 기준.
살아남은 다섯이 전부 5-1~5-4이고, 잡힌 하나는 `sync-backup`의 실행줄 변조였다).
**같은 이름 바꿔치기라도 층에 따라 결과가 정반대다**(실측 — `build_plan`의 `install` 키를
개명하면 40개가 죽는데, 5-2 산문에서 같은 이름을 바꾸면 이 파일이 생기기 전에는 0개였다).

**왜 스킬 계약 파일들이 아니라 여기인가.** `test_script_root.py`는 0단계 bash를
**실행해서** 재고, `test_skill_wiring.py`는 세 SKILL.md의 **배선 계약**을 읽어서 잰다.
이 파일이 재는 것은 셋째다: 배선이 아니라 **실행 산문의 의미** — 어떤 버킷이 어떤 CLI
명령에 실리는가. `test_user_docs.py`가 사용자 문서를 같은 이유로 갈라 나간 선례다.

**진실 원천은 전부 코드와 파일에서 뽑는다. 손으로 적은 상수는 값만 바꾸면 공허해진다.**

| 무엇 | 어디서 |
|---|---|
| 계획의 버킷 이름 | `plan_plugins.build_plan`을 **실제로 돌려** 얻은 최상위 키 |
| 값 맞추기 명령 | `plan_plugins.recheck_values` 출력 + `pc.value_command`가 낼 수 있는 값 |
| 실행 절 목록 | SKILL.md의 `#### 5-N` 제목과 그 절 bash 블록의 `claude plugin` 줄 |
| 코어 버킷 | `keyed_sync.BUCKETS` |
| 보류 축 | `keyed_sync.no_hold`가 돌려주는 축 이름 |

**바늘은 버킷 이름을 담지 않는다.** 담으면 바늘이 곧 단정이 되어, 이름을 바꿔치기해도
"절이 낡았다"로만 죽고 **무엇으로 바뀌었는지**를 재지 못한다. 바늘은 **행위**를 가리키고
(`목록을 설치한다`), 단정은 "그 행위 문장이 부르는 계획 키가 무엇인가"다.

**표가 스스로 줄어드는 것은 파생 집합과의 등식으로 막는다.**
- 결속 표의 절 집합 == bash에서 `claude plugin`을 내는 절의 파생 집합
- 결속 표의 제외 버킷 집합 == 계획이 실제로 내는 `skipped_*` 키 집합
- 결속 표의 모든 버킷 ∈ 계획이 실제로 내는 키
- 픽스처가 그 버킷들을 **실제로 채우는가**(입력 축 — 픽스처가 비어도 키는 늘 있다)

**덮지 못한 것**(다음 라운드가 읽을 자리다).
- `sync-backup`·`sync-status`의 실행 산문. 두 스킬은 `claude plugin` 명령을 내지 않아
  위험이 낮다고 **추론**했을 뿐, 재 보지 않았다.
- restore 6절 6-1~6-6의 「버킷 → 명령」 결속. 6절은 **버킷 표의 완전성**만 걸었다.
- 5-6·5-7(`value_held`·`action_held`·선택 JSON)의 결속. 일부는 `test_skill_wiring.py`의
  `SCRIPT_CONTRACT_PHRASES`와 `test_restore_choice_json_uses_the_real_section_names`가 건다.
- **더해지는** 확장 지시. 5-3에만 형태 그물이 있고 다른 절에는 없다 —
  `test_the_config_clause_never_widens_beyond_the_keys_the_plan_named`의 docstring 참조.
- (닫힘) *"5절이 `local_ahead`·`local_only`·`in_sync`의 처방을 말하지 않는다"* 는 spec
  9.3.8(6차 개정 ②)이 판단했고, 5절 머리의 버킷 표가 그것을 싣는다. 아래
  `test_the_plugin_bucket_table_*` 셋과 베낌 가드가 그 표를 건다.
"""
import functools
import inspect
import json
import os
import re
import sys
import tempfile

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(TESTS_DIR, "..")
sys.path.insert(0, os.path.join(PLUGIN_DIR, "skills", "sync-restore", "scripts"))

import keyed_sync as ks       # noqa: E402  conftest.py가 lib를 sys.path에 넣는다
import mcp_config as mc       # noqa: E402
import plugin_config as pc    # noqa: E402
import plan_plugins           # noqa: E402
from skill_paths import SKILLS  # noqa: E402

SKILL_PATH = os.path.join(PLUGIN_DIR, "skills", "sync-restore", "SKILL.md")

PLUGIN_HEADING = "### 5. 플러그인 복원"
MCP_HEADING = "### 6. MCP 서버 복원"
MCP_END_HEADING = "### 6.5 base 갱신"
REPORT_HEADING = "### 7. 결과 보고"


def read_skill():
    with open(SKILL_PATH, encoding="utf-8") as f:
        return f.read()


def plugin_section():
    """5절 전체. **제목을 바꾸면 여기서 ValueError로 죽는다** — 조용히 빈 절을 보지 않는다."""
    text = read_skill()
    return text[text.index(PLUGIN_HEADING):text.index(MCP_HEADING)]


def mcp_bucket_table():
    """6절의 버킷 표가 있는 머리 부분 (`#### 6-1` 앞까지).

    **범위를 좁게 못박는다.** 6-1 이후까지 넓혀도 오늘은 결과가 같아 아무 단정도 실패하지
    않는다(실측 — 그 변조가 SURVIVED였다). 소절이 표를 하나 더 들이는 날 조용히 갈린다.
    """
    text = read_skill()
    sec = text[text.index(MCP_HEADING):text.index(MCP_END_HEADING)]
    out = sec[:sec.index("#### 6-1")]
    assert "#### " not in out, "버킷 표 슬라이스가 소절을 삼켰다"
    return out


def plugin_bucket_table():
    """5절 머리의 버킷 처방 표 (`#### 5-1` 앞까지).

    **범위를 좁게 못박는다** — mcp_bucket_table과 같은 이유다. 소절까지 넓히면 5-5의
    선택지 표가 섞여 들어 아래 완전성 등식이 조용히 다른 것을 잰다.
    """
    sec = plugin_section()
    out = sec[:sec.index("#### 5-1")]
    assert "#### " not in out, "버킷 표 슬라이스가 소절을 삼켰다"
    return out


def report_section():
    """7절. **5절을 삼키면 안 된다** — 삼켜도 오늘은 결과가 같아 조용하다(실측)."""
    text = read_skill()
    out = text[text.index(REPORT_HEADING):]
    assert PLUGIN_HEADING not in out, "7절 슬라이스가 5절을 삼켰다"
    return out


CLAUSE_HEAD = re.compile(r"^#### (\d+-\d+)\.", re.M)
BASH_BLOCK = re.compile(r"```bash\n(.*?)```", re.S)
# `claude plugin <하위명령>` — 두 단어짜리(`marketplace add`)까지 받는다. 인자는 `<`로
# 시작하거나 대문자를 담아 [a-z ]에 걸리지 않으므로 자연히 잘린다.
CLI_LINE = re.compile(r"^\s*claude plugin ([a-z]+(?: [a-z]+)?)\b", re.M)
# 표 행의 머리에 붙은 버킷 이름. `| \`add\` | ...`와 `| \`local_stale\`(케이스 4) | ...`을
# 함께 받는다.
BUCKET_ROW = re.compile(r"^\| `([a-z_]+)`", re.M)
# 마침표 뒤 공백, 강조가 마침표를 감싼 `...다.**` 뒤 공백, 그리고 줄바꿈이 문장 경계다.
SENTENCE = re.compile(r"(?<=\.)\s+|(?<=\.\*\*)\s+|\n")


def sentences(text):
    """산문을 문장으로 가른다.

    **문장 단위로 잘라야 결속이 의미를 갖는다.** 절 전체에서 "이 이름이 있는가"를 물으면
    다른 문장이 부르는 같은 이름이 대신 충족시킨다 — 감사가 실측한 변조 두 개가 정확히
    그 형태다(한 문장 안에서 버킷 이름만 바꿔치기).
    """
    return [s for s in SENTENCE.split(text) if s.strip()]


@functools.lru_cache(maxsize=None)
def clauses():
    """5절의 `#### 5-N` 소절 본문 {절 번호: 본문}. **손으로 나열하지 않는다.**"""
    sec = plugin_section()
    marks = list(CLAUSE_HEAD.finditer(sec))
    assert marks, "5절에서 `#### 5-N` 소절을 하나도 찾지 못했다 — 제목 형식이 바뀌었다"
    out = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(sec)
        out[m.group(1)] = sec[m.start():end]
    # **범위를 5절에 못박는다.** 자르는 원본을 파일 전체로 넓히면 6-1~6-6이 섞여 드는데,
    # 6절은 `claude plugin`을 내지 않아 아래 파생 집합이 그대로라 **아무 단정도 실패하지
    # 않는다**(실측 — 그 변조가 SURVIVED였다). 조용히 다른 절을 재는 상태가 된다.
    assert all(name.startswith("5-") for name in out), sorted(out)
    return out


@functools.lru_cache(maxsize=None)
def clause_commands():
    """절 → 그 절의 bash 블록이 내는 `claude plugin` 하위명령 집합.

    **산문의 언급이 아니라 실행 블록에서 뽑는다** — 5-5는 `marketplace remove`를 산문으로
    언급하지만 실행하지 않고, 그 구별이 이 파일의 "실행 절"의 정의다.
    """
    out = {}
    for name, text in clauses().items():
        verbs = {v for block in BASH_BLOCK.findall(text) for v in CLI_LINE.findall(block)}
        if verbs:
            out[name] = frozenset(verbs)
    assert out, "5절의 어느 소절에서도 `claude plugin` 실행줄을 찾지 못했다"
    return out


@functools.lru_cache(maxsize=None)
def value_commands():
    """`pc.value_command`가 낼 수 있는 CLI 하위명령. **손으로 적지 않는다.**

    5-4가 내는 명령의 진실 원천이다 — 스크립트가 `enable`을 더하거나 빼면 산문도 따라야
    한다. `None`(확장 포맷 값 = 어느 쪽도 내지 않음)은 명령이 아니므로 뺀다.
    """
    out = {pc.value_command(local, repo)
           for local in (True, False) for repo in (True, False)}
    out.discard(None)
    assert out, "value_command가 어떤 입력에도 명령을 내지 않는다"
    return frozenset(out)


# ---------------------------------------------------------------- 계획 픽스처

GH = {"source": {"source": "github", "repo": "acme/one"}}
GH2 = {"source": {"source": "github", "repo": "acme/two"}}


@functools.lru_cache(maxsize=None)
def fixture():
    """계획·재계산을 **실제로 돌려** 얻은 출력 한 쌍.

    키 목록을 손으로 적지 않는다 — 스크립트가 버킷을 더하거나 이름을 바꾸면 아래 결속이
    따라가거나 그 자리에서 실패해야 한다. 실제 `~/.claude`와 base 디렉토리는 건드리지
    않는다(전부 임시 경로 인자다).

    픽스처는 아래 결속이 거는 버킷을 **하나도 빠짐없이 채우도록** 골랐다 —
    `test_the_fixture_fills_every_bound_bucket`이 그것을 매번 확인한다.
    """
    tmp = tempfile.mkdtemp(prefix="claude-sync-restore-prose-")
    settings = os.path.join(tmp, "settings.json")
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"enabledPlugins": {"inst@m": True, "was@m": True},
                   "extraKnownMarketplaces": {"m": GH},
                   "pluginConfigs": {}}, f)
    repo_dir = os.path.join(tmp, "repo")
    os.makedirs(repo_dir)
    repo_path = os.path.join(repo_dir, pc.BACKUP_RELPATH)
    pc.dump_backup({
        "enabledPlugins": {"inst@m": True, "was@m": False, "have@m2": True,
                           "dormant@m2": False, "off@m2": False, "new@m2": True,
                           "orph@gone": True},
        "extraKnownMarketplaces": {"m": GH, "m2": GH2, "builtin": GH},
        "pluginConfigs": {"cfg@m2": {"options": {"apiKey": pc.SENTINEL}}},
    }, repo_path)
    installed = os.path.join(tmp, "installed_plugins.json")
    with open(installed, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "plugins": {"inst@m": [{"scope": "user"}],
                                             "was@m": [{"scope": "user"}],
                                             "dormant@m2": [{"scope": "user"}],
                                             "have@m2": [{"scope": "user"}]}}, f)
    base_dir = os.path.join(tmp, "base")
    os.makedirs(base_dir)
    # base가 `was@m: True`를 담아 **케이스 8(repo_ahead)**이 선다 — 5-5의 표가 부르는
    # 세 버킷 중 하나다. base를 빼도 `repo_values`·`local_values`는 채워지므로(그 키는
    # 케이스 9로 뭉친 뒤에도 `decided`에 남는다 — 실측) 그 둘만으로는 base 있는 판정을
    # 재지 못한다. 그래서 아래 픽스처 검사가 `repo_ahead` 자체를 못박는다.
    pc.dump_backup({"enabledPlugins": {"inst@m": True, "was@m": True},
                    "extraKnownMarketplaces": {"m": GH},
                    "pluginConfigs": {}},
                   os.path.join(base_dir, pc.BACKUP_RELPATH))
    plan = plan_plugins.build_plan(
        repo_path, settings_path=settings, installed_path=installed,
        held_path=os.path.join(tmp, "absent-held.json"), base_dir=base_dir)
    # 2단계·4단계가 돈 **뒤의** 로컬을 흉내 낸다 — 재계산의 존재 이유가 그 시점의
    # 로컬이 계획 시점과 다르다는 것이므로, 계획과 같은 파일을 다시 읽으면 이 출력이
    # 재계산을 재지 못한다. `new@m2`는 매니페스트 `defaultEnabled: false`로 꺼진 채
    # 깔린 갈래이고, 레포가 `true`이므로 `enable`이 나가야 한다.
    # `dormant@m2`는 이미 설치돼 있어 2단계의 대상이 아니고 로컬 키도 없다 — 실행
    # 직전에도 값을 읽을 수 없어 `assumed`가 참으로 남는 유일한 갈래다(9.3.1).
    after = os.path.join(tmp, "settings-after-install.json")
    with open(after, "w", encoding="utf-8") as f:
        json.dump({"enabledPlugins": {"inst@m": True, "was@m": True, "have@m2": True,
                                      "off@m2": True, "new@m2": False, "cfg@m2": True},
                   "extraKnownMarketplaces": {"m": GH, "m2": GH2},
                   "pluginConfigs": {"cfg@m2": {"options": {"apiKey": "typed"}}}}, f)
    recheck = plan_plugins.recheck_values(repo_path, plan, settings_path=after)
    return plan, recheck


def plan_output():
    return fixture()[0]


def recheck_output():
    return fixture()[1]


@functools.lru_cache(maxsize=None)
def plan_keys():
    """계획 JSON의 **버킷 키**. `status`·`sections`는 버킷이 아니라 층 구조다."""
    keys = set(plan_output()) - {"status", "sections"}
    assert keys, "계획이 버킷 키를 하나도 내지 않는다"
    return frozenset(keys)


def named_plan_keys(text):
    """그 문장이 백틱으로 부르는 계획 키.

    백틱을 요구하는 것이 핵심이다 — 5-2의 `` `install <id@marketplace> --config k=v` ``는
    명령의 **형태**를 보이는 자리이지 버킷을 부르는 자리가 아니다.
    """
    return {key for key in plan_keys() if "`%s`" % key in text}


# ------------------------------------------------------- 실행 절 ↔ 버킷 결속

# (절, 바늘, 계획 키, 갈래)
#
#   target      그 절이 명령의 대상으로 삼는 목록
#   excluded    그 절이 **부르지 않는** 목록
#   recomputed  그 절이 그대로 실행하지 **않고** 실행 직전에 다시 계산하는 목록
#
# 감사가 실측한 SURVIVE 넷이 이 표의 네 행에 정확히 대응한다(2026-08-28 층 일관성 감사):
#   "`install` 목록을 설치한다" → "`skipped_already_installed` 목록을 설치한다"
#   "`disable_after_install`의 항목만 끈다" → "`install`의 항목만 끈다"
#   "`skipped_always_known`은 등록하지 않는다" → "함께 등록한다"
#   그리고 같은 형태의 마켓플레이스 쪽 바꿔치기.
EXECUTION_BINDING = (
    ("5-1", "의 각 항목을 등록한다", "marketplace_add", "target"),
    ("5-1", "등록하지 않는다", "skipped_always_known", "excluded"),
    ("5-2", "목록을 설치한다", "install", "target"),
    ("5-2", "부르지 않는다", "skipped_already_installed", "excluded"),
    ("5-3", "사용자에게 묻는다", "config_keys", "target"),
    ("5-4", "그대로 실행하지 않는다", "disable_after_install", "recomputed"),
)


@pytest.mark.parametrize("clause,needle,bucket,kind", EXECUTION_BINDING)
def test_execution_clause_binds_the_bucket_it_names(clause, needle, bucket, kind):
    """행위 문장이 부르는 계획 키가 **정확히 그 버킷 하나**여야 한다.

    바늘이 사라지면(문장을 지우거나 뒤집으면) 개수 단정이 죽고, 이름이 바뀌면 집합
    단정이 죽는다. 둘 중 어느 쪽도 조용히 통과하지 않는다.
    """
    hits = [s for s in sentences(clauses()[clause]) if needle in s]
    assert len(hits) == 1, (
        "%s에서 '%s'를 담은 문장이 %d개다 — 절이 낡았거나 지시가 사라졌다"
        % (clause, needle, len(hits)))
    named = named_plan_keys(hits[0])
    assert named == {bucket}, (clause, needle, kind, sorted(named), hits[0])


def test_the_binding_covers_every_clause_that_issues_a_cli_command():
    """**표가 스스로 줄어드는 것을 막는다.**

    실행 절의 목록은 손으로 고른 것이 아니라 bash 블록에서 파생된다. 절이 늘면 결속을
    적기 전까지 여기서 실패하고, 표에서 절을 지우면 등식이 깨진다.
    """
    derived = set(clause_commands())
    bound = {clause for clause, _, _, _ in EXECUTION_BINDING}
    assert derived == bound, (sorted(derived), sorted(bound))
    for clause in derived:
        acting = [row for row in EXECUTION_BINDING
                  if row[0] == clause and row[3] != "excluded"]
        assert len(acting) == 1, (clause, acting)


def test_every_excluded_bucket_the_plan_emits_is_bound_to_a_do_not_call_sentence():
    """계획이 내는 `skipped_*`는 **부르지 말라**는 문장에 묶여 있어야 한다.

    그 둘은 계획이 "손대지 않기로 한 것"을 보고하는 유일한 자리다. 산문이 그것을 대상
    목록으로 착각하면(감사 변조 1·4가 그 형태다) 멱등이 아닌 명령이 이미 그 상태인 id에
    나가 거짓 실패를 양산하거나, 반드시 실패하는 의사 출처에 등록을 시도한다.
    """
    derived = {key for key in plan_keys() if key.startswith("skipped_")}
    assert derived, "계획이 `skipped_*` 키를 하나도 내지 않는다"
    bound = {bucket for _, _, bucket, kind in EXECUTION_BINDING if kind == "excluded"}
    assert derived == bound, (sorted(derived), sorted(bound))


def test_every_bound_bucket_is_a_key_the_plan_actually_emits():
    """바늘의 값을 아무 문구로 바꿔 무력화하는 길을 막는다 — 버킷 이름이 **실재**해야 한다."""
    for clause, needle, bucket, _ in EXECUTION_BINDING:
        assert bucket in plan_keys(), (clause, needle, bucket, sorted(plan_keys()))


def test_the_fixture_fills_every_bound_bucket():
    """**입력 축.** 픽스처가 비어도 위 결속은 전부 초록이다 — 키는 `build_plan`의 반환
    리터럴에 언제나 있기 때문이다. 그러면 "계획이 실제로 내는 이름"이라는 근거가 거짓이
    되고, 이 파일은 빈 dict의 키 이름만 검사하는 셈이 된다.
    """
    out = plan_output()
    for _, _, bucket, _ in EXECUTION_BINDING:
        assert out[bucket], (
            "픽스처가 %s를 채우지 않는다 — 결속의 근거가 빈 출력이 된다" % bucket)
    # 5-5가 부르는 두 최상위 키도 실제로 채워져야 한다. 그 둘은 결속 표가 아니라
    # 층 검사(`test_the_choice_clause_keeps_the_top_level_keys_in_the_top_layer`)가
    # 거는 자리다.
    assert out["repo_values"] and out["local_values"]
    # **base가 있어야 케이스 8이 선다.** base를 빼면 같은 키가 케이스 9로 뭉치는데,
    # 두 최상위 키는 그래도 채워져 위 단정이 통과한다(실측) — 그러면 이 픽스처가
    # "base 있는 판정"을 재지 않으면서 잰다고 주장하게 된다.
    assert out["sections"]["enabledPlugins"]["repo_ahead"] == ["was@m"]


def test_every_plan_key_is_named_somewhere_in_the_restore_prose():
    """계획이 내는 키는 **전부** 5절이나 7절이 이름으로 부른다.

    스크립트가 버킷을 더했는데 산문이 모르면 그 항목은 사용자에게 도달하지 않는다 —
    복원도, 보고도 되지 않고 아무 테스트도 실패하지 않는다.
    """
    prose = plugin_section() + report_section()
    missing = sorted(key for key in plan_keys() if "`%s`" % key not in prose)
    assert not missing, missing


# ------------------------------------------------- 등록 실패 게이트의 파급 범위

def install_dependent_clauses():
    """`claude plugin`을 내되 마켓플레이스를 **등록하는** 절이 아닌 절.

    그 절들의 명령은 전부 `<id@marketplace>`를 받으므로 1단계 등록에 똑같이 의존한다 —
    `plan_plugins._install_dependencies`의 docstring이 그 근거를 "명령의 **형태**"로 적는다.
    """
    out = {clause for clause, verbs in clause_commands().items()
           if any(not verb.startswith("marketplace") for verb in verbs)}
    assert len(out) >= 2, (
        "등록에 의존하는 절이 %d개다 — 파급 단정이 공허해진다" % len(out))
    return out


# 5-2가 뒤 절까지 미치는 필터 둘. 앞은 1단계 등록 실패(`depends_on`/`blocked`),
# 뒤는 2단계 설치 실패다. **둘 다 파급 범위를 산문으로만 정한다.**
REACH_NEEDLES = ("적용된다", "대상에서 뺀다")


@pytest.mark.parametrize("needle", REACH_NEEDLES)
def test_the_gate_in_the_install_clause_reaches_every_later_command_clause(needle):
    """감사 변조 3 — *"같은 규칙이 5-3·5-4에도 적용된다"* → *"5-2에만 적용된다"*.

    범위를 손으로 적지 않는다. 뒤 절의 목록은 bash에서 파생되므로, 절이 늘면 이 문장이
    그것을 이름하기 전까지 실패한다.
    """
    owner = "5-2"
    others = sorted(install_dependent_clauses() - {owner})
    assert others, "5-2 말고 등록에 의존하는 절이 없다 — 파생이 무너졌다"
    hits = [s for s in sentences(clauses()[owner]) if needle in s]
    assert len(hits) == 1, (needle, len(hits))
    for other in others:
        assert other in hits[0], (needle, other, hits[0])


def test_the_reach_table_did_not_shrink():
    """위 둘은 손으로 고른 목록이라 대조할 파생 원천이 없다 — 개수를 함께 건다.

    이 단정이 말하는 것은 그것뿐이다: 파급 문장을 **더 걸었다면** 이 숫자를 함께 고친다.
    """
    assert len(REACH_NEEDLES) == 2


# ------------------------------------------------------ 값 맞추기 절의 진실 원천

def test_the_value_clause_issues_exactly_what_value_command_can_emit():
    """5-4의 bash가 내는 명령 == `pc.value_command`가 낼 수 있는 명령.

    한쪽으로 좁으면 그 갈래가 실행되지 않고(레포의 `true`가 복원되지 않는다), 넓으면
    스크립트가 내지 않는 명령을 산문이 지시한다.
    """
    value_clause = [clause for clause, verbs in clause_commands().items()
                    if verbs == value_commands()]
    assert len(value_clause) == 1, (sorted(clause_commands().items()),
                                    sorted(value_commands()))
    assert value_clause[0] == "5-4", value_clause


def test_the_value_clause_takes_its_commands_from_the_recheck_output():
    """5-4가 실행하는 목록은 **재계산**이 낸 것이지 계획의 것이 아니다.

    필드 이름을 손으로 적지 않는다 — 재계산 출력에서 뽑는다. 재계산이 필드를 개명하면
    산문도 따라야 한다.
    """
    out = recheck_output()
    assert out["commands"], "픽스처가 재계산 명령을 하나도 내지 않는다 — 입력 축"
    item_keys = set(out["commands"][0])
    hits = [s for s in sentences(clauses()["5-4"]) if "의 각 항목에 대해" in s]
    assert len(hits) == 1, len(hits)
    for key in ("commands",):
        assert "`%s`" % key in hits[0], (key, hits[0])
    assert "command" in item_keys, sorted(item_keys)
    assert "`command`" in hits[0], hits[0]
    # 재계산이 실제로 내는 명령 값이 그 문장 안에 그대로 있어야 한다.
    for verb in sorted({c["command"] for c in out["commands"]}):
        assert "`%s`" % verb in hits[0], (verb, hits[0])


def test_the_value_clause_explains_both_branches_of_the_recheck_flag():
    """`assumed`는 불리언이므로 갈래가 **둘**이고, 산문은 둘 다 말해야 한다.

    참인 항목의 exit 1은 실패가 아니라 "이미 그 상태"이고, 거짓인 항목의 exit 1은 진짜
    실패다. 한쪽만 말하면 복원 성공이 실패로(또는 실패가 성공으로) 보고된다. 그 갈래를
    말하는 자리는 5-4뿐이다.

    **한 갈래를 지워도 다른 갈래의 언급이 대신 충족시킨다** — 이름만 절 전체에서 찾으면
    그렇다(실측 — 참 갈래 문단을 지운 변조가 SURVIVED였다). 그래서 갈래마다 문장을
    따로 요구한다. 필드 이름과 갈래의 개수는 재계산 출력에서 뽑는다.
    """
    out = recheck_output()
    assert any(item.get("assumed") for item in out["commands"]), (
        "픽스처가 assumed=true 항목을 내지 않는다 — 입력 축")
    flags = {item["assumed"] for item in out["commands"]}
    assert flags and all(isinstance(flag, bool) for flag in flags), sorted(flags)
    text = clauses()["5-4"]
    literals = sorted(json.dumps(value) for value in (True, False))
    # **갈래의 개수를 함께 건다.** 순회를 한쪽으로 줄이면 나머지 갈래를 재지 않는데,
    # 줄여도 남은 단정은 그대로 참이다(실측 — (True,)로 줄인 변조가 SURVIVED였다).
    assert len(literals) == 2, literals
    for literal in literals:
        # 문장 단위로 세지 않는다 — 참 갈래를 말하는 문장이 `false`를 **다른 뜻으로**
        # 함께 부른다(매니페스트 `defaultEnabled`가 그것이다). 갈래의 머리를 건다.
        needle = "`assumed`가 `%s`" % literal
        assert text.count(needle) == 1, (
            "5-4에서 '%s' 갈래를 여는 자리가 %d곳이다" % (needle, text.count(needle)))


def test_the_recheck_fixture_exercises_both_directions():
    """**입력 축.** 한 방향만 나오는 픽스처는 위 단정을 절반만 재고도 초록이다."""
    verbs = {item["command"] for item in recheck_output()["commands"]}
    assert verbs == set(value_commands()), sorted(verbs)


# ------------------------------------------------ 설정 채우기 절의 대상 한정

FILL_DIRECTIVE = re.compile(r"채운다|묻는다")


def test_the_config_clause_never_widens_beyond_the_keys_the_plan_named():
    """감사 변조 5 — 설정 채우기 절에 *"필요하면 다른 id의 설정도 함께 채운다"* 추가.

    **더해진 문장은 `in` 가드로 잡히지 않는다** — 원래 문장이 그대로 남기 때문이다.
    그래서 형태를 뒤집어 잰다: 이 절에서 "채운다/묻는다"로 지시하는 문장은 **전부**
    대상을 한정해야 한다 — 계획 키를 이름하든(`config_keys`), 한정 조사 `만`을 쓰든.
    한정 없는 지시가 하나라도 있으면 그것이 곧 확장이다.

    한정을 넘어선 설정 입력은 실제 흐름이 만들 수 없는 상태를 만들고, 이어지는 백업이
    그 값을 레포로 민다 — 레포에는 마스킹된 값만 있으므로 다른 기기에는 동작하지 않는
    항목이 설치된다.

    **이 검사가 재지 못하는 것**: 설정을 넓히되 "채운다/묻는다"를 쓰지 않는 문장.
    지시문을 형태로 고르는 이상 남는 구멍이고, 아래 개수 단정이 그 그물의 크기를 고정한다.
    """
    hits = [s for s in sentences(clauses()["5-3"]) if FILL_DIRECTIVE.search(s)]
    assert len(hits) >= 2, (
        "설정 채우기 절에서 지시 문장을 %d개만 찾았다 — 바늘이 낡았다" % len(hits))
    for sentence in hits:
        assert "`config_keys`" in sentence or "만" in sentence, sentence


# --------------------------------------------------- 결과 보고 ↔ 실행 절 결속

def only_clause(predicate, label):
    """조건을 만족하는 실행줄을 가진 절 **하나**. 둘이면 파생이 무의미하므로 죽는다."""
    hits = [clause for clause, text in clauses().items()
            if any(predicate(line)
                   for block in BASH_BLOCK.findall(text)
                   for line in block.splitlines()
                   if line.strip().startswith("claude plugin"))]
    assert len(hits) == 1, (label, hits)
    return hits[0]


def bare_install_clause():
    return only_clause(lambda l: " install " in l and "--config" not in l, "bare install")


def config_install_clause():
    return only_clause(lambda l: "--config" in l, "config install")


def value_clause():
    hits = [clause for clause, verbs in clause_commands().items()
            if verbs == value_commands()]
    assert len(hits) == 1, hits
    return hits[0]


# (보고 항목의 제목, 그 항목이 이름해야 할 절을 파생하는 함수)
REPORT_BINDING = (
    ("설치한 플러그인", lambda: {bare_install_clause(), value_clause()}),
    ("건너뛴 플러그인 설정", lambda: {config_install_clause()}),
)


@pytest.mark.parametrize("title,derive", REPORT_BINDING)
def test_the_report_item_points_at_the_clause_that_produced_it(title, derive):
    """7절이 가리키는 절 번호가 **그 일을 실제로 하는 절**이어야 한다.

    이 저장소는 실행 순서가 `1 → 2 → 4 → 3`이라 절 번호와 단계 번호가 어긋난다 —
    번호를 손으로 옮겨 적는 자리는 전부 조용히 틀릴 수 있는 자리다. 절 번호를 bash가
    내는 명령의 **형태**에서 파생해 대조한다.
    """
    lines = [line for line in report_section().splitlines() if title in line]
    assert len(lines) == 1, (title, len(lines))
    for clause in sorted(derive()):
        assert clause in lines[0], (title, clause, lines[0])


def test_the_report_binding_did_not_shrink():
    """손으로 고른 목록이라 개수를 함께 건다 — 항목을 지우면 조용히 덜 검사한다."""
    assert len(REPORT_BINDING) == 2


STEP_ENUM = re.compile(r'"step": "([a-z_|]+)"')


def step_enum_and_samples():
    """7절의 `step` 값. 열거(`a|b|c`) 하나와, 예시 JSON이 드는 단일 값들.

    **둘을 합치면 안 된다** — 예시가 드는 `"step": "install"` 하나가 열거에서 지워진
    `install`을 대신 채워 넣어 아래 단정을 통째로 공허하게 만든다(실측 — 합집합으로
    두었을 때 열거에서 `install`을 지운 변조가 SURVIVED).
    """
    enums, samples = [], set()
    for m in STEP_ENUM.finditer(report_section()):
        value = m.group(1)
        if "|" in value:
            enums.append(set(value.split("|")))
        else:
            samples.add(value)
    assert len(enums) == 1, "7절의 `step` 열거가 %d개다" % len(enums)
    return enums[0], samples


def test_the_failure_report_enumerates_every_command_the_clauses_issue():
    """실패 보고의 `step` 열거가 실행 절이 내는 명령을 남김없이 덮어야 한다.

    덮지 못한 명령의 실패는 **적을 칸이 없다** — 사용자가 무엇이 실패했는지 못 받는다.
    열거를 손으로 세지 않고 bash에서 파생한다.
    """
    enum, samples = step_enum_and_samples()
    issued = {verb.replace(" ", "_")
              for verbs in clause_commands().values() for verb in verbs}
    assert issued, "실행 절이 내는 명령이 없다 — 파생이 무너졌다"
    assert issued <= enum, sorted(issued - enum)
    # 예시 JSON이 드는 값도 그 열거의 원소여야 한다 — 아니면 소비자가 만들 수 없는
    # 보고 형태를 예시가 가르친다.
    assert samples <= enum, sorted(samples - enum)


# ------------------------------------------------------------ 절 참조 무결성

def test_every_clause_cross_reference_points_at_a_clause_that_exists():
    """`5-3`·`6-4` 같은 절 참조가 **실재하는 절**을 가리켜야 한다.

    절을 재배치하면(이 파일이 이미 한 번 겪었다 — 실행 순서 때문에 5-3과 5-4가 자리를
    바꿨다) 남은 참조가 조용히 다른 절을 가리키거나 없는 절을 가리킨다.
    """
    text = read_skill()
    heads = set(CLAUSE_HEAD.findall(text))
    assert heads, "SKILL.md에서 `#### N-M` 제목을 하나도 찾지 못했다"
    leads = "".join(sorted({h.split("-")[0] for h in heads}))
    refs = set("%s-%s" % m for m in
               re.findall(r"(?<![0-9])([%s])-(\d)(?![0-9])" % leads, text))
    assert refs >= heads, sorted(heads - refs)
    assert not refs - heads, sorted(refs - heads)


# ------------------------------------------- 6절 버킷 표의 완전성 (넓힌 자리)

def test_the_mcp_bucket_table_covers_every_core_bucket():
    """6절의 버킷 표는 코어가 내는 버킷을 남김없이 덮어야 한다.

    빠진 버킷은 **처방이 없는 채로** 사용자에게 도달한다 — 모델이 그 항목을 어떻게 다룰지
    산문에서 읽을 수 없다. 표를 손으로 세지 않고 `ks.BUCKETS`와 대조하고, 빠져도 되는
    둘(보류 축)은 **어댑터가 `no_hold`를 쓴다는 사실에서 파생**한다. MCP에 보류를 도입하는
    날 이 단정이 먼저 실패하고, 그것이 이 검사의 목적이다.
    """
    rows = set(BUCKET_ROW.findall(mcp_bucket_table()))
    assert rows, "6절에서 버킷 표를 뽑지 못했다"
    source = inspect.getsource(mc.restore_plan)
    assert "hold=ks.no_hold" in source, (
        "mcp_config.restore_plan이 no_hold를 쓰지 않는다 — 아래 면제의 근거가 사라졌다")
    hold_buckets = {"%s_held" % axis for axis in ks.no_hold({}, {})}
    assert hold_buckets <= set(ks.BUCKETS), sorted(hold_buckets)
    assert rows == set(ks.BUCKETS) - hold_buckets, (
        sorted(rows), sorted(set(ks.BUCKETS) - hold_buckets - rows))


# --------------------------------- 5절 버킷 표의 완전성 (6차 개정 ②)

# 표 행이 처리 절을 가리키는 형태. `(5-2)`처럼 괄호로 감싼 절 번호만 위임으로 센다 —
# 본문에 절 번호가 스치듯 나오는 것과 구별해야 한다.
CLAUSE_REF = re.compile(r"\((\d-\d)\)")

BACKUP_SKILL = "sync-backup"
BACKUP_COMMAND = "/" + BACKUP_SKILL

# 표가 **직접** 처방을 주는 버킷 → 그 행에 반드시 있어야 할 바늘.
# 손으로 고른 것은 바늘뿐이고, **어느 버킷이 여기 와야 하는지는 표에서 파생한다**
# (아래 test_..._splits_...). 바늘은 처방의 **행위**를 가리킨다 — 버킷 이름을 담으면
# 바늘이 곧 단정이 되어 처방을 비워도 초록이다.
TABLE_PRESCRIPTION = {
    "in_sync": ("아무것도 하지 않는다",),
    "local_only": (BACKUP_COMMAND,),
    "local_ahead": (BACKUP_COMMAND, "선택지를 주지 않는다"),
    "unrestorable": ("시도하지 않는다",),
}


def plugin_bucket_rows():
    """5절 표의 {버킷: 행 전문}. **손으로 나열하지 않는다.**"""
    out = {}
    for line in plugin_bucket_table().splitlines():
        m = BUCKET_ROW.match(line)
        if m:
            out[m.group(1)] = line
    assert out, "5절 머리에서 버킷 표를 뽑지 못했다"
    return out


def test_the_plugin_bucket_table_covers_every_core_bucket():
    """5절의 표는 코어가 내는 버킷을 **열한 개 전부** 덮어야 한다.

    빠진 버킷은 처방이 없는 채로 사용자에게 도달한다 — 그것이 6차 개정 ②가 고친
    결함이고(`local_ahead`·`local_only`·`in_sync`), 표가 줄어들면 그대로 되돌아온다.

    **6절과 달리 면제가 없다.** MCP는 `no_hold`라 보류 버킷 둘을 빼지만 플러그인
    어댑터는 네 종류의 보류를 낸다 — 그 사실을 리터럴로 적지 않고 **훅을 돌려서**
    확인한다. 어댑터가 보류를 그만두는 날 이 단정이 먼저 실패한다.
    """
    repo = {"x@m": {"version": "1.0"}}          # H3 — 레포 값이 확장 포맷이다
    hooks = pc.build_hooks(
        {section: {} for section in pc.SECTIONS},
        {"enabledPlugins": repo, "extraKnownMarketplaces": {}, "pluginConfigs": {}},
        auto_ids=frozenset(), held_state={})
    assert hooks["enabledPlugins"]["hold"]({}, repo)["value"], (
        "플러그인 어댑터가 보류를 하나도 내지 않는다 — 면제 없음의 근거가 사라졌다")
    rows = set(plugin_bucket_rows())
    assert rows == set(ks.BUCKETS), (sorted(set(ks.BUCKETS) - rows), sorted(rows))


def test_the_plugin_bucket_table_splits_into_delegating_and_prescribing_rows():
    """모든 행은 둘 중 하나다 — 처리 절을 가리키거나, 처방을 표에서 주거나.

    **어느 버킷이 처방 쪽인지는 표에서 파생한다.** 처방 없는 행에 `(5-5)`를 붙여
    "처리하는 절이 있다"고 위장하면 여기서 갈린다. 반대로 처방 행의 절 참조를 지우면
    바늘 검사가 없는 버킷이 늘어 이 등식이 깨진다.
    """
    rows = plugin_bucket_rows()
    delegating = {b for b, line in rows.items() if CLAUSE_REF.search(line)}
    prescribing = set(rows) - delegating
    assert delegating, "표의 어느 행도 처리 절을 가리키지 않는다 — 파생이 무너졌다"
    assert prescribing == set(TABLE_PRESCRIPTION), (
        sorted(prescribing), sorted(TABLE_PRESCRIPTION))
    # 위임 행이 가리키는 절은 실재해야 한다(전역 참조 무결성 검사가 파일 전체를 걸지만,
    # 이 표에 대해서도 직접 건다 — 표만 남기고 절을 지우는 변조를 여기서 잡는다).
    for bucket in sorted(delegating):
        for ref in CLAUSE_REF.findall(rows[bucket]):
            assert ref in clauses(), (bucket, ref, sorted(clauses()))


@pytest.mark.parametrize("bucket", sorted(TABLE_PRESCRIPTION))
def test_the_prescribing_row_actually_prescribes(bucket):
    """처방 행이 **행위**를 말해야 한다. 이름만 남기고 처방을 비우면 여기서 죽는다.

    `local_only`·`local_ahead`가 가리키는 명령은 손으로 적지 않는다 — 이 저장소의
    스킬 목록에서 파생한다(`skill_paths.SKILLS`). 백업 스킬의 이름이 바뀌면 이 산문도
    따라야 하고, 따르지 않으면 사용자는 존재하지 않는 명령을 안내받는다.
    """
    assert BACKUP_SKILL in SKILLS, (BACKUP_SKILL, SKILLS)
    rows = plugin_bucket_rows()
    line = rows[bucket]
    for needle in TABLE_PRESCRIPTION[bucket]:
        assert needle in line, (bucket, needle, line)
        # **바늘이 판별력을 가져야 한다.** 빈 문자열이나 모든 행에 있는 조각은 처방을
        # 통째로 비워도 초록이다 — 그 자리를 여기서 막는다.
        hits = sum(needle in other for other in rows.values())
        assert hits <= 2, (bucket, needle, hits)
    # `in_sync`에는 사용자 행동이 없다 — 다른 둘과 같은 문구를 주면 뜻이 반대가 된다.
    if bucket == "in_sync":
        assert BACKUP_COMMAND not in line, line


def test_the_two_bucket_tables_are_not_copies_of_each_other():
    """5절과 6절의 표는 같은 이름을 **다른 층·다른 처방**으로 다룬다 — 베낀 행이 없어야 한다.

    글자 그대로 같은 행이 있으면 한쪽을 고칠 때 다른 쪽이 조용히 낡는다. 그리고 실제
    사고가 있었다: 이 표의 초판에서 `in_sync`·`local_only`·`local_ahead` 세 행이 6절과
    **동일해** 변조 하네스가 두 표를 구별하지 못했다(실측 — 그 세 변조가 APPLY_FAIL).
    """
    rows5 = plugin_bucket_rows()
    rows6 = {}
    for line in mcp_bucket_table().splitlines():
        m = BUCKET_ROW.match(line)
        if m:
            rows6[m.group(1)] = line
    assert rows6, "6절에서 버킷 행을 뽑지 못했다"
    shared = set(rows5) & set(rows6)
    assert shared, "두 표가 공유하는 버킷이 없다 — 파생이 무너졌다"
    copied = sorted(b for b in shared if rows5[b] == rows6[b])
    assert not copied, copied


def named_section_buckets(text):
    """그 글이 백틱으로 부르는 **코어 버킷**(섹션 안의 이름)."""
    return {bucket for bucket in ks.BUCKETS if "`%s`" % bucket in text}


def test_the_choice_clause_keeps_the_top_level_keys_in_the_top_layer():
    """5-5는 층이 다른 두 이름을 한 표에서 부른다 — 버킷은 섹션 안, 값 목록은 최상위다.

    층을 뒤집으면 소비자가 없는 자리를 뒤져 **케이스 4·5·8·9가 하나도 보고되지 않는다.**
    버킷 쪽 층은 `test_skill_wiring.py`의 계약 문구가 이미 걸지만, `repo_values`·
    `local_values` 쪽은 걸리지 않아 층을 반대로 적어도 스위트가 전부 초록이었다(실측).

    **줄 단위로 본다.** 그 선언은 앞 문장을 "그 둘"로 받으므로 문장 하나에는 이름이 없다.
    """
    lines = [line for line in clauses()["5-5"].splitlines() if "최상위 키다" in line]
    assert len(lines) == 1, (
        "5-5에서 최상위 층을 선언하는 줄이 %d개다" % len(lines))
    named = named_plan_keys(lines[0])
    assert named, "그 줄이 계획의 최상위 키를 하나도 부르지 않는다"
    intruder = named_section_buckets(lines[0])
    assert not intruder, sorted(intruder)


def test_the_three_choice_table_covers_every_case_its_heading_declares():
    """5-5의 표가 제목이 약속한 케이스를 남김없이 담아야 한다.

    행 하나를 지우면 그 케이스는 **선택지 자체가 사라진다** — 넷 다 안정 상태라 사용자가
    고르지 않으면 영원히 유지된다. 제목과 표를 서로의 대조군으로 쓴다.
    """
    text = clauses()["5-5"]
    head = text.splitlines()[0]
    declared = set(re.findall(r"\d", re.search(r"케이스 ([\d·]+)", head).group(1)))
    assert declared, head
    rows = set()
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        m = re.search(r"케이스 ([\d·]+)", line)
        if m:
            rows |= set(re.findall(r"\d", m.group(1)))
    assert rows == declared, (sorted(rows), sorted(declared))
    named = set(BUCKET_ROW.findall(text))
    assert named, "5-5에서 버킷 행을 뽑지 못했다"
    assert named <= set(ks.BUCKETS), sorted(named - set(ks.BUCKETS))
    # `named_section_buckets`를 **양성으로도 쓴다.** 그 선택자는 위 층 검사에서
    # "비어 있어야 한다"로만 쓰이므로, 늘 빈 집합을 내도 그 검사가 초록이다
    # (실측 — set()을 돌려주는 변조가 SURVIVED였다). 여기서 실물을 요구해 묶어 둔다.
    assert named <= named_section_buckets(text), sorted(named)
