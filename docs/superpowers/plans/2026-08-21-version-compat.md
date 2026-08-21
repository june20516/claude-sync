# 버전 호환성 대처 Implementation Plan

> **agentic worker에게:** REQUIRED SUB-SKILL: 이 plan을 task 단위로 구현하려면 suberpower:subagent-driven-development(권장) 또는 suberpower:executing-plans를 사용하세요. Step은 추적을 위해 checkbox(`- [ ]`) 문법을 사용합니다.

**Goal:** 백업 레포가 자기를 쓴 버전과 읽는 데 필요한 최소 버전을 스스로 밝히게 하고, 낮은 버전 기기가 그것을 읽고 `/sync-backup`을 스스로 멈추게 한다.

**Architecture:** 판정은 신설 `lib/compat.py` 하나를 통한다(순수 함수 + 얇은 CLI). 표식은 `generate_metadata.py`가 `sync-metadata.json`에 쓴다. 항목별 보류는 metadata가 아니라 각 파일 자체의 `version` 필드로 하며 기존 `UnknownBackupSchema` 경로에 합류시킨다. 세 SKILL.md는 스크립트 경로를 플러그인 루트 기준으로 잡고, 레포를 가져온 직후 아무것도 쓰기 전에 `compat.py`를 부른다.

**Tech Stack:** Python 3 표준 라이브러리만. 테스트는 pytest(`uv run --with pytest`). 셸은 bash/zsh, macOS BSD `sort -V`.

**Spec:** `docs/superpowers/specs/2026-08-21-version-compat-design.md` — 이 plan은 그 문서를 구현한다. 판정표는 spec 6.4, 에러 처리는 spec 10을 따른다.

**작업 브랜치:** `feat/version-compat` (이미 생성됨). PR target은 `main`이 아니라 **`release/3.0.0`**이다.

**절대 하지 말 것:**
- `plugin.json`·`.claude-plugin/marketplace.json`의 버전을 올리는 것. 둘 다 `3.0.0`이고 이 작업도 같은 릴리즈다.
- 이 기기에서 `/sync-backup`을 실행하는 것. 플러그인 캐시가 아직 `2.0.0`이라 백업 레포가 파괴된다.
- 실제 `~/.claude.json`·`~/.claude/.sync-state`·`~/.claude/settings.json`을 건드리는 것. 테스트는 `tmp_path`와 `claude_json_path=`/`base_dir=`/`HOME=`로 격리한다.

**모든 명령은 레포 루트 `/Users/bran/personal/claude-sync`에서 실행한다.**

**커밋 규약:** 커밋은 반드시 경로를 명시한다(`git commit -m "..." -- <paths>`). 다만
`git commit -- <경로>`는 **추적되지 않는 새 파일에 실패한다**(`pathspec did not match`).
새 파일을 만든 task는 먼저 `git add -- <같은 경로들>`을 실행한 뒤 커밋한다.

```bash
git add -- <paths>
git commit -m "..." -- <paths>
```


전체 테스트: `uv run --with pytest pytest plugins/claude-sync/tests -q`
착수 전 기준선: **166 passed**

---

### Task 1: `parse_version` — semver 비교의 기초

문자열 비교를 쓰면 `"3.10.0" > "3.9.0"`이 거짓이 된다. 이 프로젝트가 명시적으로 경고하는 함정이므로 가장 먼저 못을 박는다.

**Files:**
- Create: `plugins/claude-sync/lib/compat.py`
- Test: `plugins/claude-sync/tests/test_compat.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_compat.py`를 새로 만든다.

```python
"""lib/compat.py의 버전 호환성 판정 테스트.

실제 ~/.claude는 건드리지 않는다 — 모든 경로를 tmp_path로 주입한다.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import compat  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("3.0.0", (3, 0, 0)),
    ("v3.0.0", (3, 0, 0)),
    ("3.0.0-rc1", (3, 0, 0)),
    ("  3.0.0", (3, 0, 0)),
    ("3.10.0", (3, 10, 0)),
    ("10.0.0", (10, 0, 0)),
])
def test_parse_version_accepts(text, expected):
    assert compat.parse_version(text) == expected


@pytest.mark.parametrize("text", ["unknown", "", "3.0", "a.b.c", "v", None, 3, ["3.0.0"],
                                  "3.0.0.5", "1.2.3.4"])
def test_parse_version_rejects(text):
    assert compat.parse_version(text) is None


def test_parse_version_orders_by_number_not_string():
    """문자열 비교였다면 '3.10.0' < '3.9.0'이 되어 거짓이 된다."""
    assert compat.parse_version("3.10.0") > compat.parse_version("3.9.0")
    assert compat.parse_version("3.0.0") < compat.parse_version("3.0.1")
    assert compat.parse_version("2.9.9") < compat.parse_version("10.0.0")


def test_parse_version_still_accepts_non_numeric_suffix():
    """lookahead가 접미사까지 막아버리면 안 된다 — 막는 것은 4번째 숫자 구성요소뿐이다."""
    assert compat.parse_version("3.0.0-rc1") == (3, 0, 0)
    assert compat.parse_version("3.0.0+build.7") == (3, 0, 0)
    assert compat.parse_version("3.0.0 or later") == (3, 0, 0)
```

> **정정 (2026-08-21, code review 후):** 최초 계획의 정규식에는 `(?![\d.])`가 없어
> `'3.0.0.5'`가 `(3,0,0)`으로 읽히는 fail-open이 있었다. 위 코드는 그것을 봉쇄한 최종본이며,
> 실제 구현에서는 Task 1 커밋(`3fe72f8`) 뒤 별건 커밋(`7cb54c3`)으로 적용되었다.

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: `ModuleNotFoundError: No module named 'compat'`로 collection error

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/compat.py`를 새로 만든다.

```python
#!/usr/bin/env python3
"""claude-sync 버전 호환성 판정.

레포의 sync-metadata.json이 요구하는 최소 리더 버전과 이 기기의 플러그인 버전을 비교한다.
**판정은 이 모듈 하나를 통한다** — 세 SKILL.md가 각자 버전을 비교하면 이 프로젝트가
없애려고 만든 파서 드리프트가 그대로 재현된다.

순수 판정 함수 + 얇은 main()으로 나눈다(mcp_config.py와 같은 구조). git도 네트워크도
부르지 않는다 — 다운그레이드 탐지의 git 부분은 detect_downgrade.py의 몫이다.
"""
import json
import os
import re
import sys

# 우리가 쓰는 백업을 읽으려면 필요한 최소 버전. 현재 플러그인 버전이 아니다 —
# 그러면 3.0.1을 내는 순간 3.0.0 기기가 전부 막힌다.
# 불변식: 이 값의 major는 plugin.json의 major와 같아야 한다(test_min_reader_major_matches_plugin_json).
# 결정 1에 따라 같은 major 안에서는 스키마가 깨지지 않으므로 값은 항상 {major}.0.0이다.
# 한 번 올려 푸시하면 되돌릴 수 없다. 그 미만 기기는 전부 막힌다.
MIN_READER_VERSION = "3.0.0"

METADATA_RELPATH = "sync-metadata.json"

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?![\d.])")


def parse_version(text):
    """'3.10.0' -> (3, 10, 0). 파싱 못 하면 None.

    문자열 비교를 쓰면 "3.10.0" > "3.9.0"이 거짓이 된다. 반드시 정수 튜플로 비교한다.
    선행 v('v3.0.0')와 접미사('3.0.0-rc1')는 허용하고 코어 3자리만 읽는다.
    접미사를 무시하므로 pre-release는 정식 릴리즈와 동등하게 다뤄진다 — semver의
    "pre-release가 더 낮다"와 다르지만, 이 프로젝트는 pre-release를 배포한 적이 없다.
    네 번째 숫자 구성요소('3.0.0.5')는 거부한다 — 코어만 읽어 통과시키면 fail-open이 된다.
    'unknown'은 None이다 — claude plugin list가 실제로 내는 값이다.
    """
    if not isinstance(text, str):
        return None
    m = _VERSION_RE.match(text)
    if m is None:
        return None
    return tuple(int(g) for g in m.groups())
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(compat): semver 파싱 신설 — 문자열 비교 함정을 막는다

'3.10.0' > '3.9.0'이 문자열 비교로는 거짓이 된다. 정수 튜플로만 비교한다.
plugin list가 실제로 내는 'unknown'은 파싱 실패(None)로 다룬다." \
  -- plugins/claude-sync/lib/compat.py plugins/claude-sync/tests/test_compat.py
```

---

### Task 2: `read_plugin_version` / `load_metadata` — 읽기

둘 다 **예외를 던지지 않는다.** "자기 버전을 모른다"와 "표식이 없다"는 정상적으로 표현 가능한 상태여야 한다. 예외로 만들면 호출부마다 try가 생기고 그 처리가 갈린다.

**Files:**
- Modify: `plugins/claude-sync/lib/compat.py`
- Test: `plugins/claude-sync/tests/test_compat.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_compat.py` 끝에 추가한다.

```python
def write_plugin_json(tmp_path, obj=None, *, broken=False):
    """plugin.json 역할의 임시 파일 경로를 반환한다.

    broken=True면 깨진 JSON을 쓴다. obj는 그대로 직렬화한다.
    """
    path = tmp_path / "plugin.json"
    path.write_text("{ not json" if broken else json.dumps(obj), encoding="utf-8")
    return str(path)


def test_read_plugin_version_reads_version(tmp_path):
    path = write_plugin_json(tmp_path, {"name": "claude-sync", "version": "3.0.0"})
    assert compat.read_plugin_version(path) == "3.0.0"


def test_read_plugin_version_missing_file(tmp_path):
    assert compat.read_plugin_version(str(tmp_path / "nope.json")) is None


def test_read_plugin_version_broken_json(tmp_path):
    assert compat.read_plugin_version(write_plugin_json(tmp_path, broken=True)) is None


@pytest.mark.parametrize("obj", [{}, {"version": 3}, {"version": None}, [], "x"])
def test_read_plugin_version_unusable(tmp_path, obj):
    assert compat.read_plugin_version(write_plugin_json(tmp_path, obj)) is None


def write_metadata(tmp_path, obj=None, *, broken=False, missing=False):
    """sync-metadata.json **파일 경로**를 반환한다 (레포 디렉토리가 아니다).

    missing=True면 파일을 만들지 않는다. broken=True면 깨진 JSON을 쓴다.
    같은 이름의 인자가 헬퍼마다 정반대를 뜻하지 않도록 의미를 키워드로 드러낸다.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    path = repo / compat.METADATA_RELPATH
    if broken:
        path.write_text("{ not json", encoding="utf-8")
    elif not missing:
        path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def test_load_metadata_reads_dict(tmp_path):
    path = write_metadata(tmp_path, {"min_reader_version": "3.0.0"})
    assert compat.load_metadata(path) == {"min_reader_version": "3.0.0"}


def test_load_metadata_missing_is_none(tmp_path):
    assert compat.load_metadata(write_metadata(tmp_path, missing=True)) is None


def test_load_metadata_broken_is_none(tmp_path):
    """깨진 metadata를 차단 근거로 삼으면 데드락이다 — 그 파일을 고치는 것이 다음 백업이다."""
    assert compat.load_metadata(write_metadata(tmp_path, broken=True)) is None


@pytest.mark.parametrize("obj", [[], "x", 3, None])
def test_load_metadata_non_dict_is_none(tmp_path, obj):
    path = tmp_path / "m.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    assert compat.load_metadata(str(path)) is None


def test_default_plugin_json_path_points_at_real_plugin_json():
    """lib/../.claude-plugin/plugin.json 이 실제로 존재해야 한다."""
    assert os.path.isfile(compat.default_plugin_json_path())
    assert compat.read_plugin_version(compat.default_plugin_json_path()) is not None
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: `AttributeError: module 'compat' has no attribute 'read_plugin_version'`로 다수 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/compat.py`의 `parse_version` 아래에 추가한다.

```python
def default_plugin_json_path():
    """이 모듈 위치에서 유도한 plugin.json 경로 (lib/../.claude-plugin/plugin.json)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", ".claude-plugin", "plugin.json")


UNREADABLE = object()   # 파일은 있는데 읽지 못했다 — "없다"와 반드시 구별한다


def _load_json(path):
    """JSON 파일을 세 상태로 읽는다. 예외를 던지지 않는다.

    - 없음 / JSON 깨짐 -> None
    - 열지 못함(PermissionError, EIO, IsADirectoryError 등) -> UNREADABLE
    - 그 외 -> 디코드된 객체

    **"못 읽음"과 "없음"을 같은 값으로 접으면 안 된다.** 접는 판단을 저수준 로더에
    박아두면 호출부가 되돌릴 수 없고, load_metadata 쪽에서 fail-open이 된다.
    셋을 그대로 돌려주고 해석은 각 함수가 한다.
    깨진 JSON만 None으로 degrade한다 — 내용의 문제이고 다음 백업이 되돌린다.
    (mcp_config._BROKEN이 쓰는 out-of-band 센티널과 같은 이유다.)
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    except OSError:
        return UNREADABLE
    try:
        return json.loads(raw)
    except ValueError:
        return None


def read_plugin_version(plugin_json_path=None):
    """plugin.json의 version 문자열. 읽지 못하면 None(예외 아님).

    '자기 버전을 모른다'는 정상적으로 표현 가능한 상태여야 한다. 예외로 만들면
    호출부마다 try가 생기고 그 처리가 갈린다.
    기본 경로 결정을 함수 안에 둔다 — mcp_config.read_local_servers와 같은 형태다.
    호출부마다 `or default_...()`를 복붙하면 한 곳이 빠졌을 때 조용히 깨진다.

    UNREADABLE도 dict가 아니므로 None이 된다. 자기 버전을 못 읽으면 상위 판정이
    차단으로 접으므로 이쪽은 이미 fail-safe다.
    """
    path = default_plugin_json_path() if plugin_json_path is None else plugin_json_path
    obj = _load_json(path)
    if not isinstance(obj, dict):
        return None
    version = obj.get("version")
    return version if isinstance(version, str) else None


def load_metadata(path):
    """sync-metadata.json을 읽는다. 없거나 깨졌거나 dict가 아니면 None,
    열지 못했으면 UNREADABLE.

    깨진 metadata를 차단 근거로 삼으면 데드락이 된다 — 그 파일을 정상으로 되돌리는 것이
    다음 백업인데 그 백업이 막힌다. load_backup이 깨진 파일을 {}로 degrade하는 것과 같은
    이유다("레포 파일 하나가 깨졌다고 전체를 막지 않는다").

    **못 읽음은 다르다.** 표식 없음은 "2.x가 썼다"는 의미 있는 결론이라 통과로 이어지는데,
    못 읽은 파일이 그 결론을 참칭하면 상위 버전이 쓴 레포를 통과시킨다. 환경의 문제라
    다음 백업이 고쳐주지도 않으므로 데드락 논거가 닿지 않는다. 그대로 올려보낸다.
    """
    obj = _load_json(path)
    if obj is UNREADABLE:
        return UNREADABLE
    return obj if isinstance(obj, dict) else None
```

`json.JSONDecodeError`는 `ValueError`의 하위 클래스이고 `UnicodeDecodeError`도 `ValueError`의 하위 클래스이므로 `(OSError, ValueError)` 하나로 둘 다 잡힌다.

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(compat): plugin.json·sync-metadata.json 읽기 — 실패는 예외가 아니라 None

'자기 버전을 모른다'와 '표식이 없다'는 정상 상태다. 깨진 metadata를 차단 근거로
삼으면 그 파일을 고치는 다음 백업까지 막혀 데드락이 되므로 None으로 degrade한다." \
  -- plugins/claude-sync/lib/compat.py plugins/claude-sync/tests/test_compat.py
```

---

### Task 3: `evaluate` — 판정표 6행과 안내 문구

spec 6.4의 표 전수를 구현한다. 안내 문구는 **여기서만** 만든다 — 세 SKILL.md가 각자 쓰면 드리프트한다.

문구는 **사실만 말하고 행동은 말하지 않는다.** backup은 중단하고 status는 계속하고 restore는 묻기 때문이다. 행동 문장은 각 SKILL.md가 붙인다.

**Files:**
- Modify: `plugins/claude-sync/lib/compat.py`
- Test: `plugins/claude-sync/tests/test_compat.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_compat.py` 끝에 추가한다.

```python
# --- spec 6.4 판정표 전수 ---

def test_evaluate_0_unreadable_metadata_blocks():
    """못 읽음은 없음이 아니다 — 상위 버전이 쓴 레포를 통과시키면 안 된다."""
    v = compat.evaluate(compat.UNREADABLE, "3.0.0")
    assert v["blocked"] is True
    assert v["reason"] == "metadata_unreadable"


def test_message_for_unreadable_metadata_omits_upgrade_commands():
    """플러그인을 올려도 해결되지 않는다. 잘못된 해법을 내밀면 안 된다."""
    msg = compat.evaluate(compat.UNREADABLE, "3.0.0")["message"]
    assert "claude plugin update" not in msg
    assert "권한" in msg
    assert compat.METADATA_RELPATH in msg


def test_evaluate_1_no_metadata_passes():
    """표식 없음 = 2.x가 쓴 것 = 우리보다 앞설 수 없다 (결정 4)."""
    v = compat.evaluate(None, "3.0.0")
    assert v["blocked"] is False
    assert v["reason"] is None
    assert v["message"] == ""


def test_evaluate_2_no_min_reader_field_passes():
    v = compat.evaluate({"written_by_version": "3.0.0"}, "3.0.0")
    assert v["blocked"] is False
    assert v["repo_written_by"] == "3.0.0"


@pytest.mark.parametrize("bad", ["", "unknown", "3.0", 3, ["3.0.0"]])
def test_evaluate_3_unparsable_min_reader_blocks(bad):
    """필드가 있는데 못 읽는다 = 상위 버전이 모르는 형식으로 썼을 수 있다. 모르면 안 쓴다."""
    v = compat.evaluate({"min_reader_version": bad}, "3.0.0")
    assert v["blocked"] is True
    assert v["reason"] == "min_reader_unparsable"


def test_evaluate_explicit_null_is_treated_as_absent():
    """JSON의 null은 필드 없음과 구별되지 않는다 — dict.get이 둘 다 None을 준다.

    구별하려면 센티널이 필요한데, 여기서는 구별할 실익이 없다. null은 '요구 없음'이다.
    """
    v = compat.evaluate({"min_reader_version": None}, "3.0.0")
    assert v["blocked"] is False
    assert v["reason"] is None


def test_evaluate_4_unknown_my_version_with_requirement_blocks():
    """레포가 최소치를 요구하는데 충족을 증명할 수 없다."""
    v = compat.evaluate({"min_reader_version": "3.0.0"}, None)
    assert v["blocked"] is True
    assert v["reason"] == "my_version_unknown"


def test_evaluate_4b_unknown_my_version_without_requirement_passes():
    """요구가 없으면 증명할 것도 없다."""
    v = compat.evaluate(None, None)
    assert v["blocked"] is False


def test_evaluate_5_older_than_min_reader_blocks():
    v = compat.evaluate({"min_reader_version": "4.0.0"}, "3.0.0")
    assert v["blocked"] is True
    assert v["reason"] == "older_than_min_reader"
    assert v["repo_min_reader"] == "4.0.0"
    assert v["my_version"] == "3.0.0"


def test_evaluate_6_equal_or_newer_passes():
    assert compat.evaluate({"min_reader_version": "3.0.0"}, "3.0.0")["blocked"] is False
    assert compat.evaluate({"min_reader_version": "3.0.0"}, "3.10.0")["blocked"] is False


def test_evaluate_uses_numeric_comparison():
    """3.9.0 기기가 3.10.0을 요구하는 레포를 만나면 막혀야 한다.

    문자열 비교였다면 '3.9.0' > '3.10.0'이 참이 되어 통과해 버린다.
    """
    v = compat.evaluate({"min_reader_version": "3.10.0"}, "3.9.0")
    assert v["blocked"] is True


# --- 안내 문구 ---

def test_message_contains_both_commands_and_restart_notice():
    v = compat.evaluate({"min_reader_version": "4.0.0"}, "3.0.0")
    msg = v["message"]
    assert "claude plugin marketplace update claude-sync" in msg
    assert "claude plugin update claude-sync" in msg
    assert "/reload-plugins" in msg
    assert "재시작" in msg
    assert "4.0.0" in msg and "3.0.0" in msg


@pytest.mark.parametrize("meta,mine", [
    (compat.UNREADABLE, "3.0.0"),                  # metadata_unreadable
    ({"min_reader_version": "?"}, "3.0.0"),        # min_reader_unparsable
    ({"min_reader_version": "4.0.0"}, None),       # my_version_unknown
    ({"min_reader_version": "4.0.0"}, "3.0.0"),    # older_than_min_reader
])
def test_message_says_nothing_about_stopping_or_continuing(meta, mine):
    """행동은 각 SKILL.md가 정한다 — backup은 중단, status는 계속, restore는 질문.

    네 갈래를 전부 본다. 한 갈래만 보면 나머지에 행동 단어가 새어 들어가도 못 잡는다.
    """
    msg = compat.evaluate(meta, mine)["message"]
    assert msg != ""
    assert "중단" not in msg
    assert "계속" not in msg
    assert "멈춥니다" not in msg


def test_message_for_unknown_my_version_suggests_checking_install():
    """자기 버전을 못 읽었다면 설치가 깨졌을 수 있다 — update만으로 안 풀린다."""
    msg = compat.evaluate({"min_reader_version": "4.0.0"}, None)["message"]
    assert "claude plugin list" in msg


def test_message_for_unknown_my_version():
    msg = compat.evaluate({"min_reader_version": "4.0.0"}, None)["message"]
    assert "버전 미상" in msg
    assert "claude plugin update claude-sync" in msg


def test_message_for_unparsable_min_reader():
    msg = compat.evaluate({"min_reader_version": "?"}, "3.0.0")["message"]
    assert "알아볼 수 없" in msg
    assert "claude plugin update claude-sync" in msg
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: `AttributeError: module 'compat' has no attribute 'evaluate'`로 다수 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/compat.py`의 `load_metadata` 아래에 추가한다.

```python
# 안내 문구의 명령은 항상 두 줄이다. 마켓플레이스 갱신 없이 plugin update만 하면
# 새 버전을 못 본다.
_UPGRADE_COMMANDS = (
    "  claude plugin marketplace update claude-sync\n"
    "  claude plugin update claude-sync"
)

# 재시작 안내는 반드시 넣는다. plugin update가 "restart required to apply"라고 명시하고,
# 자동 갱신 경로에서도 "Run /reload-plugins to apply"가 뜬다.
_RESTART_NOTICE = (
    "그다음 Claude Code를 재시작하거나 /reload-plugins 를 실행하세요.\n"
    "업데이트는 재시작 전까지 적용되지 않습니다."
)


def _upgrade_message(reason, repo_min_reader, my_version):
    """차단 사유를 사용자 문구로 바꾼다. **문구는 여기서만 만든다.**

    사실만 말하고 행동은 말하지 않는다 — backup은 중단하고 status는 계속하고
    restore는 묻기 때문이다. 행동 문장은 각 SKILL.md가 붙인다.
    """
    mine = my_version if my_version else "버전 미상"
    if reason == "metadata_unreadable":
        # 플러그인을 올려도 해결되지 않는다. 업그레이드 명령을 내밀지 않는다.
        # "멈춥니다"라고 쓰지 않는다 — backup만 멈추고 status는 계속하며 restore는 묻는다.
        return (
            "백업 레포의 %s을 읽지 못했습니다 (권한 또는 입출력 문제).\n"
            "표식을 확인할 수 없어, 이 레포가 더 높은 버전을 요구하는지 알 수 없습니다.\n\n"
            "  ls -l <레포>/%s 으로 권한을 확인하거나, 레포를 다시 클론하세요."
            % (METADATA_RELPATH, METADATA_RELPATH)
        )
    if reason == "repo_not_found":
        # 업그레이드 문제가 아니다. 명령을 내밀지 않는다.
        return (
            "백업 레포 디렉토리를 찾을 수 없습니다.\n"
            "호환성을 확인할 수 없어, 이 레포가 더 높은 버전을 요구하는지 알 수 없습니다.\n\n"
            "  레포 경로가 올바른지 확인하거나, 레포를 다시 클론하세요."
        )
    if reason == "min_reader_unparsable":
        head = (
            "이 백업이 요구하는 최소 버전을 알아볼 수 없습니다 "
            "— 상위 버전이 쓴 백업일 수 있습니다 (이 기기: %s)." % mine
        )
    else:
        head = (
            "이 백업은 claude-sync %s 이상이 필요합니다 (이 기기: %s)."
            % (repo_min_reader or "알 수 없음", mine)
        )
    body = "%s\n이 버전이 백업을 쓰면 레포가 손상될 수 있습니다.\n\n%s\n\n%s" % (
        head,
        _UPGRADE_COMMANDS,
        _RESTART_NOTICE,
    )
    if reason == "my_version_unknown":
        # 자기 버전을 못 읽었다면 설치 자체가 깨졌을 수 있다. update만으로 안 풀린다.
        body += (
            "\n\n이 기기의 플러그인 버전을 읽지 못했습니다. 설치 상태도 확인하세요:\n"
            "  claude plugin list"
        )
    return body


def evaluate(meta, my_version):
    """호환성 판정. spec 6.4의 표 전수이며 이 표 밖의 경우는 없다.

    meta는 load_metadata의 반환(dict, None, 또는 UNREADABLE), my_version은
    read_plugin_version의 반환.

    **UNREADABLE을 반드시 먼저 걸러야 한다.** 그것은 dict가 아니므로
    isinstance(meta, dict) 검사만 하면 조용히 "표식 없음"으로 접혀 통과하고,
    상위 버전이 쓴 레포를 파괴한다. 이 판정을 단순화하려는 시도를 경계할 것.
    """
    raw_min = meta.get("min_reader_version") if isinstance(meta, dict) else None
    raw_written = meta.get("written_by_version") if isinstance(meta, dict) else None
    verdict = {
        "blocked": False,
        "reason": _block_reason(meta, raw_min, my_version),
        "my_version": my_version,
        "repo_min_reader": raw_min if isinstance(raw_min, str) else None,
        "repo_written_by": raw_written if isinstance(raw_written, str) else None,
        "message": "",
    }
    if verdict["reason"] is not None:
        verdict["blocked"] = True
        verdict["message"] = _upgrade_message(
            verdict["reason"], verdict["repo_min_reader"], my_version
        )
    return verdict


def _block_reason(meta, raw_min, my_version):
    """차단 사유. 통과면 None. **spec 6.4의 표를 위에서 아래로 그대로 읽는다.**

    판정을 한 함수에 모으고 verdict 조립은 evaluate가 한다 — 두 함수가 같은 dict를
    번갈아 수정하면 "어디서 message가 채워지는가"가 갈리고, 행을 추가할 때 한쪽만
    고쳐 드리프트한다.
    """
    if meta is UNREADABLE:
        return "metadata_unreadable"        # 0 못 읽음 — 없음이 아니다
    if raw_min is None:
        return None                          # 1·2 표식 없음 → 통과
    required = parse_version(raw_min)
    if required is None:
        return "min_reader_unparsable"       # 3 있는데 못 읽음 — 모르면 안 쓴다
    mine = parse_version(my_version)
    if mine is None:
        return "my_version_unknown"          # 4 충족을 증명할 수 없다
    if mine < required:
        return "older_than_min_reader"       # 5
    return None                              # 6 통과
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(compat): 판정표 6행과 안내 문구 — 문구는 한 곳에서만 만든다

표식이 없으면 통과한다(2.x가 쓴 것이라 앞설 수 없다). 필드가 있는데 못 읽으면
차단한다(모르면 안 쓴다). 내 버전을 몰라도 요구가 없으면 통과한다.

문구는 사실만 말하고 행동은 말하지 않는다 — backup은 중단하고 status는 계속하고
restore는 묻기 때문이다." \
  -- plugins/claude-sync/lib/compat.py plugins/claude-sync/tests/test_compat.py
```

---

### Task 4: `check` + CLI — 세 스킬이 부르는 얼굴

`lib/`는 import 전용이지만 이것 하나는 스킬이 직접 부른다. **판정을 한 파일에 두라는 제약**을 지키려면 별도 스크립트로 빼지 않는 편이 낫다.

**Files:**
- Modify: `plugins/claude-sync/lib/compat.py`
- Test: `plugins/claude-sync/tests/test_compat.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_compat.py` 끝에 추가한다. 파일 상단 import에 `subprocess`를 추가한다.

```python
LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib")
COMPAT_CLI = os.path.join(LIB_DIR, "compat.py")


def dir_snapshot(path):
    """디렉토리 안 모든 파일의 (상대경로, 내용) 집합. 쓰기 여부 검증용."""
    out = {}
    for root, _, files in os.walk(path):
        for f in files:
            full = os.path.join(root, f)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, path)] = fh.read()
    return out


def repo_with_metadata(tmp_path, obj=None, **kw):
    """레포 디렉토리 경로를 반환한다.

    write_metadata는 파일 경로를 주는데 check()는 레포 디렉토리를 받는다.
    """
    return os.path.dirname(write_metadata(tmp_path, obj, **kw))


def test_check_passes_on_repo_without_metadata(tmp_path):
    repo = repo_with_metadata(tmp_path, missing=True)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(repo, plugin_json_path=plugin_json)
    assert v["status"] == "ok"
    assert v["blocked"] is False


def test_check_blocks_on_higher_min_reader(tmp_path):
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "4.0.0",
                                         "written_by_version": "4.0.0"})
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    v = compat.check(repo, plugin_json_path=plugin_json)
    assert v["blocked"] is True
    assert v["repo_written_by"] == "4.0.0"


def test_check_writes_nothing(tmp_path):
    """읽기 전용이다. 차단 판정이 나도 레포를 건드리지 않는다."""
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "4.0.0"})
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    before = dir_snapshot(repo)
    compat.check(repo, plugin_json_path=plugin_json)
    assert dir_snapshot(repo) == before


def test_cli_prints_json_and_exits_zero(tmp_path):
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "3.0.0"})
    proc = subprocess.run([sys.executable, COMPAT_CLI, repo],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["blocked"] is False
    assert out["repo_min_reader"] == "3.0.0"


def test_cli_exits_zero_even_when_blocking(tmp_path):
    """비-0으로 끝내면 SKILL.md의 셸이 set -e로 죽어 안내를 못 보여준다."""
    repo = repo_with_metadata(tmp_path, {"min_reader_version": "99.0.0"})
    proc = subprocess.run([sys.executable, COMPAT_CLI, repo],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["blocked"] is True
    assert "claude plugin update claude-sync" in out["message"]


def test_cli_without_argument_fails():
    proc = subprocess.run([sys.executable, COMPAT_CLI], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "사용:" in proc.stderr
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: `AttributeError: module 'compat' has no attribute 'check'`로 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/compat.py` 끝에 추가한다.

```python
def check(repo_dir, plugin_json_path=None):
    """레포 디렉토리를 읽어 판정한다. **어떤 파일도 쓰지 않는다.**

    레포 디렉토리가 없으면 차단한다. "표식 없음"으로 접으면 안 된다 — 표식 없음은
    "2.x가 썼다"는 *결론*이지만 레포가 없는 것은 결론이 아니라 호출자의 입력 오류다.
    특히 빈 문자열은 os.path.join("", ...)이 상대 경로가 되어 **현재 디렉토리의 파일을
    읽고 통과 판정을 낸다.**
    """
    # or를 쓰지 않는다 — read_plugin_version이 None을 받아 기본 경로를 정한다.
    # or는 빈 문자열도 falsy로 보아 "기본값 써라"로 오독한다.
    my_version = read_plugin_version(plugin_json_path)
    if not (isinstance(repo_dir, str) and os.path.isdir(repo_dir)):
        return {
            "status": "ok",
            "blocked": True,
            "reason": "repo_not_found",
            "my_version": my_version,
            "repo_min_reader": None,
            "repo_written_by": None,
            "message": _upgrade_message("repo_not_found", None, my_version),
        }
    meta = load_metadata(os.path.join(repo_dir, METADATA_RELPATH))
    verdict = {"status": "ok"}
    verdict.update(evaluate(meta, my_version))
    return verdict


def main():
    if len(sys.argv) != 2:
        print("사용: compat.py <레포 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = check(sys.argv[1])
    except Exception as e:  # noqa: BLE001 — 마지막 방어선
        # 형제 스크립트의 status="skipped"를 베끼지 않는다. 거기서 skipped는
        # "이 단계만 건너뛰고 진행"이지만, 호환성 검사에서 그것은
        # "가드 없이 백업 진행"이다. compat은 fail-closed다.
        out = {
            "status": "error",
            "blocked": True,
            "reason": "check_failed",
            "my_version": None,
            "repo_min_reader": None,
            "repo_written_by": None,
            "message": "호환성 검사가 실패했습니다 (%s: %s).\n"
                       "이 레포를 안전하게 다룰 수 있는지 판단할 수 없습니다."
                       % (type(e).__name__, e),
        }
        print("호환성 검사 실패: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

**차단이어도 종료 코드는 0이다.** 비-0으로 끝내면 SKILL.md의 셸이 죽어 안내 문구를 보여주지 못한다. 기존 스크립트들이 `{"status": "skipped"}`로 보고하는 것과 같은 관례다.

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(compat): check()와 CLI 진입점 — 세 스킬이 부르는 유일한 얼굴

차단이어도 종료 코드는 0이다. 비-0이면 SKILL.md의 셸이 죽어 안내를 못 보여준다.
판정을 한 파일에 두라는 제약 때문에 별도 스크립트로 빼지 않는다." \
  -- plugins/claude-sync/lib/compat.py plugins/claude-sync/tests/test_compat.py
```

---

### Task 5: `mcp_config`의 `version` 게이트 — 지금 뚫려 있는 구멍

`_recognized_servers`는 **형태만** 보고 `version` 필드를 보지 않는다. 미래의 v3 문서가 `{"version": 3, "servers": {...}}` 형태를 유지하면 알아보는 것으로 판정되어 그대로 병합된다. `UnknownBackupSchema`가 발동하지 않는다.

**한 곳에만 넣는다.** `parse_base`·`parse_backup`·`load_backup`이 모두 이 함수를 통하므로 세 곳이 자동으로 같은 기준을 갖는다. 한 곳에만 넣으면 "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고, 그 비대칭이 상위 버전 백업을 파괴한다.

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py:136-148` (`_recognized_servers`)
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_config.py` 끝에 추가한다.

```python
# --- 상위 스키마 게이트 (spec 7장) ---

def _v3_doc():
    """형태는 v2와 같지만 version이 3인 문서. 형태만 보면 알아보게 된다."""
    return json.dumps({"version": 3, "scope": "user", "servers": {"a": {"command": "a"}}})


def test_load_backup_rejects_higher_schema_version(tmp_path):
    path = tmp_path / "mcp-servers.json"
    path.write_text(_v3_doc(), encoding="utf-8")
    with pytest.raises(mc.UnknownBackupSchema):
        mc.load_backup(str(path))


def test_parse_base_rejects_higher_schema_version():
    """레포와 base가 같은 기준을 써야 한다 — 비대칭이 상위 버전 백업을 파괴한다."""
    assert mc.parse_base(_v3_doc().encode("utf-8")) is None


def test_parse_backup_degrades_higher_schema_version():
    assert mc.parse_backup(_v3_doc()) == {}


def test_current_schema_version_still_accepted(tmp_path):
    path = tmp_path / "mcp-servers.json"
    mc.dump_backup({"a": {"command": "a"}}, str(path))
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


def test_v1_array_still_accepted(tmp_path):
    """v1 배열에는 version 개념이 없다. 게이트가 이것을 막으면 안 된다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps([{"name": "a", "command": "a"}]), encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


def test_object_without_version_still_accepted(tmp_path):
    """손으로 만든 문서를 막을 이유는 없다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"servers": {"a": {"command": "a"}}}), encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}
```

`test_mcp_config.py` 상단에 `import json`과 `import pytest`가 없으면 추가한다.

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q -k "schema_version or v1_array or without_version"
```
기대: `test_load_backup_rejects_higher_schema_version`이 `DID NOT RAISE`로 FAIL, `test_parse_base_rejects_higher_schema_version`이 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/mcp_config.py`의 `_recognized_servers`를 다음으로 교체한다.

```python
def _recognized_servers(obj):
    """알아볼 수 있는 백업 문서면 servers 매핑, 아니면 None.

    v1 배열과 servers가 dict인 v2 객체만 인정한다. 이 판정이 parse_base·parse_backup·
    load_backup의 공통 기준이다 — 세 곳이 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이
    생기고, 그 비대칭이 상위 버전 백업을 파괴한다.

    version이 SCHEMA_VERSION보다 크면 알아보지 못한 것으로 취급한다. 형태만 보면
    미래의 v3 문서({"version": 3, "servers": {...}})가 통과해 그대로 병합되는데,
    v3가 servers 값의 의미를 바꿨다면 조용히 파괴된다.
    version이 없거나 int가 아니면 통과시킨다 — 손으로 만든 문서를 막을 이유는 없다.
    """
    if isinstance(obj, list):
        return _servers_from_obj(obj)          # v1 배열에는 version 개념이 없다
    if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
        if _claims_newer_schema(obj.get("version")):
            return None
        return _servers_from_obj(obj)
    return None


def _claims_newer_schema(version):
    """version이 SCHEMA_VERSION보다 높다고 주장하는가.

    float까지 본다. {"version": 3.0}은 파이썬이 아닌 도구(jq, YAML 변환기, 다른 언어의
    v3 writer)가 실제로 만드는 형태다. int만 막고 float를 통과시키면 게이트의 존재
    이유 자체가 무력화된다.
    bool은 제외한다 — True는 int의 인스턴스지만 버전 주장이 아니다.
    문자열("3")은 통과시킨다. 손으로 고친 문서를 막지 않기 위해서다.
    """
    if isinstance(version, bool):
        return False
    return isinstance(version, (int, float)) and version > SCHEMA_VERSION
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS. **기존 166개가 하나도 깨지지 않아야 한다** — 깨졌다면 게이트가 과하게 잡은 것이다

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(mcp): 상위 스키마 문서를 알아보지 못한 것으로 취급한다

_recognized_servers가 형태만 보고 version을 안 봐서, 미래의 v3 문서가
{\"version\": 3, \"servers\": {...}} 형태를 유지하면 그대로 병합됐다.
UnknownBackupSchema는 이 경우 발동하지 않는다.

게이트를 이 함수 한 곳에 넣어 parse_base·parse_backup·load_backup이 자동으로
같은 기준을 갖게 한다. 한 곳에만 넣으면 이력은 못 믿는데 레포는 믿는 비대칭이 생긴다." \
  -- plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
```

---

### Task 6: 표식 쓰기 + semver 불변식 테스트

`generate_metadata.py`가 세 필드를 쓴다. **이 task의 핵심은 `test_min_reader_major_matches_plugin_json`이다** — 이 테스트 하나가 이 프로젝트에서 semver를 의미 있게 만드는 유일한 장치다. major를 올리면서 상수를 안 건드리면 여기서 깨진다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/generate_metadata.py`
- Test: `plugins/claude-sync/tests/test_metadata.py` (신설)

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_metadata.py`를 새로 만든다.

```python
"""sync-metadata.json 표식 생성과 semver 불변식.

실제 ~/.claude는 건드리지 않는다 — claude_dir을 tmp_path로 주입한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import generate_metadata as gm  # noqa: E402


def fake_claude_dir(tmp_path):
    """agents/skills/CLAUDE.md를 가진 ~/.claude 역할 디렉토리."""
    d = tmp_path / "claude"
    (d / "agents").mkdir(parents=True)
    (d / "skills" / "demo").mkdir(parents=True)
    (d / "agents" / "a.md").write_text("a", encoding="utf-8")
    (d / "skills" / "demo" / "SKILL.md").write_text("s", encoding="utf-8")
    (d / "CLAUDE.md").write_text("c", encoding="utf-8")
    return str(d)


def write_plugin_json(tmp_path, obj=None, *, missing=False):
    """plugin.json 역할의 임시 파일 경로. missing=True면 파일을 만들지 않는다.

    test_compat.py의 같은 이름 헬퍼와 키워드 의미를 맞춘다 — 같은 이름이 파일마다
    다른 뜻을 가지면 호출부를 읽을 때마다 어느 쪽인지 확인해야 한다.
    """
    path = tmp_path / "plugin.json"
    if not missing:
        path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def test_metadata_has_all_three_markers(tmp_path):
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert meta["written_by_version"] == "3.0.0"
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION
    assert meta["schema"] == {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION}
    assert len(meta["files"]) == 3


def test_min_reader_is_constant_not_plugin_version(tmp_path):
    """같은 major 안의 상승이 옛 기기를 막아서는 안 된다.

    plugin.json이 3.9.9여도 min_reader_version은 3.0.0이다. 현재 버전을 그대로 쓰면
    3.0.1을 내는 순간 3.0.0 기기가 전부 막힌다.
    """
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.9.9"})
    )
    assert meta["written_by_version"] == "3.9.9"
    assert meta["min_reader_version"] == "3.0.0"


def test_min_reader_major_matches_plugin_json():
    """MIN_READER_VERSION의 major == 레포 plugin.json의 major.

    이 테스트가 이 프로젝트에서 semver를 의미 있게 만드는 유일한 장치다.
    major를 올리면서 상수를 안 건드리면 여기서 깨진다 — 조용한 실패를 시끄러운
    실패로 바꾸는 것이 존재 이유다.
    """
    plugin_version = compat.read_plugin_version(compat.default_plugin_json_path())
    assert plugin_version is not None
    assert compat.parse_version(compat.MIN_READER_VERSION)[0] == \
        compat.parse_version(plugin_version)[0]


def test_min_reader_minor_and_patch_are_zero():
    """결정 1에 따라 호환 경계는 항상 {major}.0.0이다."""
    assert compat.parse_version(compat.MIN_READER_VERSION)[1:] == (0, 0)


def test_written_by_omitted_when_plugin_json_unreadable(tmp_path):
    """자기 버전을 몰라도 min_reader는 정상 기록된다 — 상수를 쓰는 두 번째 이유."""
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, missing=True)
    )
    assert "written_by_version" not in meta
    assert meta["min_reader_version"] == compat.MIN_READER_VERSION


def test_schema_map_omits_plugins_json(tmp_path):
    """plugins.json에는 자체 version 필드가 없다. 없는 사실을 쓰지 않는다."""
    meta = gm.build_metadata(
        fake_claude_dir(tmp_path), write_plugin_json(tmp_path, {"version": "3.0.0"})
    )
    assert "plugins.json" not in meta["schema"]


def test_default_output_name_matches_compat_constant():
    """쓰는 쪽과 읽는 쪽이 같은 파일을 봐야 한다. 리터럴이 갈리면 무증상 고장이다."""
    src = open(gm.__file__, encoding="utf-8").read()
    assert "compat.METADATA_RELPATH" in src
    assert '"sync-metadata.json"' not in src


def test_metadata_is_byte_stable_across_runs(tmp_path):
    """표식 파일이 소음이 되면 안 된다 — 같은 입력이면 같은 바이트여야 한다."""
    claude_dir = fake_claude_dir(tmp_path)
    plugin_json = write_plugin_json(tmp_path, {"version": "3.0.0"})
    out1, out2 = str(tmp_path / "m1.json"), str(tmp_path / "m2.json")
    gm.write_metadata(out1, gm.build_metadata(claude_dir, plugin_json))
    gm.write_metadata(out2, gm.build_metadata(claude_dir, plugin_json))
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read()
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_metadata.py -q
```
기대: `AttributeError: module 'generate_metadata' has no attribute 'build_metadata'`로 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/skills/sync-backup/scripts/generate_metadata.py`를 다음으로 교체한다.

```python
#!/usr/bin/env python3
"""백업 시점의 파일별 내용 해시(sha256)와 버전 표식을 기록한다. mtime 미사용.

표식 세 필드의 성격이 다르다:
- written_by_version: 정보. 판정에 쓰지 않는다.
- min_reader_version: **판정 근거.** 이것 하나가 backup 게이트다.
- schema: 사람이 읽는 요약. 판정 근거가 아니다 — 항목별 보류는 각 파일 자체의
  version 필드로 한다(spec 결정 2).
"""
import hashlib
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import compat  # noqa: E402
import mcp_config as mc  # noqa: E402


def file_sha256(path):
    """파일의 sha256 hex. 파일이 없으면(끊어진 심볼릭 링크 포함) None.

    (PermissionError 등 그 외 OSError는 전파한다 — sync_state.file_hash와 같은 관례.)
    표식 생성 전체가 죽는 것보다 파일 하나가 빠지는 것이 싸다. 죽으면 표식 없는
    백업이 푸시된다.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read())
    except FileNotFoundError:
        return None
    return h.hexdigest()


def collect(base, prefix):
    result = {}
    if os.path.isfile(base):
        digest = file_sha256(base)
        if digest is not None:
            result[prefix] = digest
        return result
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                digest = file_sha256(full)
                if digest is None:
                    print("건너뜀(읽을 수 없음): %s" % full, file=sys.stderr)
                    continue
                rel = os.path.relpath(full, base)
                result[prefix + "/" + rel] = digest
    return result


def build_metadata(claude_dir, plugin_json_path):
    """표식이 붙은 메타데이터 dict.

    plugin.json을 못 읽으면 written_by_version을 생략한다 — 자기 버전을 모르는 것이
    파일 해시를 못 쓸 이유는 아니다. min_reader_version은 상수이므로 이 경우에도
    정상 기록된다.
    """
    metadata = {"files": {}}
    metadata["files"].update(collect(os.path.join(claude_dir, "agents"), "agents"))
    metadata["files"].update(collect(os.path.join(claude_dir, "skills"), "skills"))
    metadata["files"].update(collect(os.path.join(claude_dir, "CLAUDE.md"), "CLAUDE.md"))
    written_by = compat.read_plugin_version(plugin_json_path)
    if written_by is not None:
        metadata["written_by_version"] = written_by
    metadata["min_reader_version"] = compat.MIN_READER_VERSION
    metadata["schema"] = {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION}
    return metadata


def write_metadata(output_path, metadata):
    """sort_keys로 바이트를 안정화한다 — os.walk 순서 때문에 매 백업마다 diff가 생기면
    표식 파일 자체가 소음이 된다."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def main():
    # 파일명을 리터럴로 다시 쓰지 않는다 — 쓰는 쪽과 읽는 쪽이 다른 파일을 보면
    # 표식이 있는데도 없는 것으로 판정되는 무증상 고장이 된다.
    output_path = sys.argv[1] if len(sys.argv) > 1 else compat.METADATA_RELPATH
    metadata = build_metadata(
        os.path.expanduser("~/.claude"), compat.default_plugin_json_path()
    )
    if "written_by_version" not in metadata:
        print(
            "경고: plugin.json에서 버전을 읽지 못해 written_by_version을 생략했습니다.",
            file=sys.stderr,
        )
    write_metadata(output_path, metadata)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(metadata): 버전 표식 세 필드 — min_reader는 major에 묶인 상수다

written_by_version은 plugin.json에서, min_reader_version은 compat의 상수에서,
schema는 mcp_config.SCHEMA_VERSION에서 온다. plugins.json은 자체 version 필드가
없으므로 schema에 넣지 않는다 — 없는 사실을 쓰지 않는다.

test_min_reader_major_matches_plugin_json이 상수와 plugin.json의 major를 묶는다.
major를 올리면서 상수를 안 건드리면 여기서 깨진다. 이것이 이 프로젝트에서 semver를
의미 있게 만드는 유일한 장치다.

sort_keys를 넣어 os.walk 순서로 생기던 diff 소음을 없앤다." \
  -- plugins/claude-sync/skills/sync-backup/scripts/generate_metadata.py \
     plugins/claude-sync/tests/test_metadata.py
```

---

### Task 7: `shape_of` / `downgrade_suspected` — 순수 판정

`mcp_config`는 파싱해서 매핑만 주므로 **원본 형태가 사라진다.** 다운그레이드 판정에는 "v1 배열이었나 v2 객체였나"가 필요하다.

**Files:**
- Modify: `plugins/claude-sync/lib/compat.py`
- Test: `plugins/claude-sync/tests/test_compat.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_compat.py` 끝에 추가한다.

```python
# --- 다운그레이드 판정 (spec 9.1) ---

@pytest.mark.parametrize("data,expected", [
    (None, "absent"),
    (b"{ not json", "broken"),
    (b"[]", "v1_array"),
    (b'[{"name":"a","command":"a"}]', "v1_array"),
    (b'{"version":2,"servers":{}}', "v2_object"),
    (b'{"servers":{"a":{}}}', "v2_object"),
    (b'{"version":3,"servers":{}}', "v2_object"),
    (b"null", "unknown"),
    (b'"x"', "unknown"),
    (b'{"servers":[]}', "unknown"),
    (b"3", "unknown"),
])
def test_shape_of(data, expected):
    assert compat.shape_of(data) == expected


def test_shape_of_accepts_str():
    assert compat.shape_of('{"version":2,"servers":{}}') == "v2_object"


def test_downgrade_suspected_when_repo_v1_and_base_v2():
    """레포는 v1인데 내 base는 v2였다 = 옛 기기가 덮어썼다."""
    assert compat.downgrade_suspected("v1_array", "v2_object") is True


@pytest.mark.parametrize("repo,base", [
    ("v1_array", "v1_array"),    # 정말 오래된 레포
    ("v1_array", "absent"),      # 이력 없음 — 근거가 될 수 없다
    ("v1_array", "broken"),      # 신뢰할 수 없는 이력 (불변식 2)
    ("v1_array", "unknown"),
    ("v2_object", "v2_object"),  # 정상
    ("v2_object", "v1_array"),   # 오히려 전진
    ("absent", "v2_object"),     # 파일이 사라진 것은 다른 문제다
    ("broken", "v2_object"),
])
def test_downgrade_not_suspected(repo, base):
    assert compat.downgrade_suspected(repo, base) is False
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat.py -q -k "shape_of or downgrade"
```
기대: `AttributeError: module 'compat' has no attribute 'shape_of'`로 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/compat.py`의 `check` 위에 추가한다.

```python
# 백업 문서의 형태. 문자열 리터럴을 흩뿌리지 않는다 — 호출부 오타가 AttributeError로
# 즉시 드러난다(불변식 6).
SHAPE_ABSENT = "absent"
SHAPE_BROKEN = "broken"
SHAPE_UNREADABLE = "unreadable"   # 파일/blob을 읽지 못했다 — absent가 아니다
SHAPE_V1_ARRAY = "v1_array"
SHAPE_V2_OBJECT = "v2_object"
SHAPE_UNKNOWN = "unknown"
_SHAPES = frozenset({
    SHAPE_ABSENT, SHAPE_BROKEN, SHAPE_UNREADABLE,
    SHAPE_V1_ARRAY, SHAPE_V2_OBJECT, SHAPE_UNKNOWN,
})


def shape_of(data):
    """백업 문서의 형태. absent | broken | v1_array | v2_object | unknown

    다운그레이드 판정에 필요하다. mcp_config는 파싱해서 매핑만 주므로 원본 형태가 사라진다.
    version 값은 보지 않는다 — 여기서 답하는 질문은 "v1이냐 v2냐"이지
    "읽어도 되느냐"가 아니다. 후자는 mcp_config의 게이트가 답한다.

    **SHAPE_UNREADABLE은 여기서 나오지 않는다.** 이 함수는 경로가 아니라 원본 바이트를
    받으므로 읽기 실패를 알 수 없다. 읽는 쪽(detect_downgrade.py)이 그 상태를 만든다.

    파싱된 객체를 넘기는 것은 "깨진 문서"가 아니라 호출자 오류이므로 TypeError로 드러낸다.
    fail-open 방향의 반환값으로 삼키면 그 실수가 "사고 없음"이라는 결론이 된다(불변식 6).
    """
    if data is None:
        return SHAPE_ABSENT
    if not isinstance(data, (str, bytes, bytearray)):
        raise TypeError(
            "shape_of는 원본 문서(str/bytes)를 받는다: %r" % type(data).__name__
        )
    try:
        obj = json.loads(data)
    except ValueError:
        return SHAPE_BROKEN
    if isinstance(obj, list):
        return SHAPE_V1_ARRAY
    if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
        return SHAPE_V2_OBJECT
    return SHAPE_UNKNOWN


def downgrade_suspected(repo_shape, base_shape):
    """레포는 v1 배열인데 내 base는 v2 객체였다 -> 옛 버전 기기가 덮어썼다.

    레포가 v1인 것만으로는 부족하다 — 정말 오래된 레포일 수 있다. base가 v2였다는 것은
    이 기기가 v2를 본 적이 있다는 뜻이고, 그 뒤 v1이 되었다면 누군가 되돌린 것이다.
    base를 못 읽으면 판정하지 않는다 — 신뢰할 수 없는 이력은 근거가 될 수 없다(불변식 2).

    모르는 shape는 조용히 False로 만들지 않는다. 같은 파일의 _upgrade_message가 모르는
    reason에 예외를 던지는데 여기만 조용하면 관례가 갈리고, 조용한 쪽이 fail-open이다(불변식 6).
    """
    for name, value in (("repo_shape", repo_shape), ("base_shape", base_shape)):
        if value not in _SHAPES:
            raise ValueError("알 수 없는 %s: %r" % (name, value))
    return repo_shape == SHAPE_V1_ARRAY and base_shape == SHAPE_V2_OBJECT
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(compat): 백업 문서의 형태 판정과 다운그레이드 탐지 조건

mcp_config는 파싱해서 매핑만 주므로 v1 배열이었는지 v2 객체였는지가 사라진다.
shape_of가 그것을 답한다.

레포가 v1인 것만으로는 부족하다 — 정말 오래된 레포일 수 있다. base가 v2였을 때만
사고로 판정한다. base를 못 읽으면 판정하지 않는다(불변식 2)." \
  -- plugins/claude-sync/lib/compat.py plugins/claude-sync/tests/test_compat.py
```

---

### Task 8: `detect_downgrade.py` — git 히스토리에서 마지막 정상 백업 찾기

git을 부르는 것은 스크립트의 일이다. `compat.py`는 순수하게 유지한다.

**자동 복구하지 않는다.** 옛 기기가 *의도적으로* 지운 서버까지 되살리기 때문이다(결정 5).

**Files:**
- Create: `plugins/claude-sync/skills/sync-backup/scripts/detect_downgrade.py`
- Test: `plugins/claude-sync/tests/test_downgrade.py` (신설, 실제 git 레포 픽스처)

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_downgrade.py`를 새로 만든다.

```python
"""다운그레이드 탐지 — 실제 git 레포 픽스처를 쓴다.

실제 ~/.claude/.sync-state는 건드리지 않는다 — base_dir을 tmp_path로 주입한다.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import detect_downgrade as dd  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "skills", "sync-backup", "scripts", "detect_downgrade.py",
)


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo)] + list(args), check=True, capture_output=True
    )


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    # 전역 commit.gpgsign이 켜져 있으면 서명 키가 없는 픽스처 커밋이 exit 128로 죽는다.
    # 레포 로컬 설정만 끈다 — 전역 ~/.gitconfig는 건드리지 않는다.
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def commit_mcp(repo, payload, message):
    """payload를 mcp-servers.json으로 쓰고 커밋한다. payload는 이미 직렬화된 문자열."""
    (repo / mc.BACKUP_RELPATH).write_text(payload, encoding="utf-8")
    git(repo, "add", mc.BACKUP_RELPATH)
    git(repo, "commit", "-q", "-m", message)


def v2(servers):
    return json.dumps({"version": 2, "scope": "user", "servers": servers}, indent=2)


def v1(names):
    return json.dumps([{"name": n, "command": n} for n in names], indent=2)


def base_dir_with(tmp_path, payload):
    """base 블롭 디렉토리. payload가 None이면 이력 없음."""
    d = tmp_path / "base"
    d.mkdir(exist_ok=True)
    if payload is not None:
        (d / mc.BACKUP_RELPATH).write_text(payload, encoding="utf-8")
    return str(d)


def test_detects_downgrade_and_finds_last_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}, "b": {"command": "b"}}), "backup: v2")
    commit_mcp(repo, v1(["a"]), "backup: 옛 기기가 덮어씀")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["status"] == "ok"
    assert out["downgrade_suspected"] is True
    assert out["candidate"]["subject"] == "backup: v2"
    assert out["candidate"]["server_count"] == 2
    assert out["candidate"]["server_names"] == ["a", "b"]
    assert len(out["candidate"]["sha"]) == 40


def test_no_detection_when_base_is_v1(tmp_path):
    """정말 오래된 레포다. 사고가 아니다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v1(["a"])))
    assert out["downgrade_suspected"] is False
    assert out["candidate"] is None


def test_no_detection_when_base_absent(tmp_path):
    """신뢰할 수 없는 이력은 근거가 될 수 없다 (불변식 2)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, None))
    assert out["downgrade_suspected"] is False


def test_no_detection_when_repo_is_v2(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["downgrade_suspected"] is False


def test_candidate_null_when_history_has_no_v2(tmp_path):
    """사고는 알리되 복구는 제안하지 않는다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup 1")
    commit_mcp(repo, v1(["a", "b"]), "backup 2")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["downgrade_suspected"] is True
    assert out["candidate"] is None


def test_skips_commits_where_file_absent(tmp_path):
    """파일이 없던 커밋에서 git show가 실패해도 탐색이 멈추면 안 된다."""
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("x", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "initial")
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup: v2")
    git(repo, "rm", "-q", mc.BACKUP_RELPATH)
    git(repo, "commit", "-q", "-m", "삭제")
    commit_mcp(repo, v1(["a"]), "backup: 되돌림")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["candidate"]["subject"] == "backup: v2"


def test_unreadable_repo_file_is_not_absent(tmp_path):
    """못 읽음을 absent로 접으면 탐지가 조용히 꺼진다(불변식 6)."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    (repo / mc.BACKUP_RELPATH).chmod(0)
    try:
        out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    finally:
        (repo / mc.BACKUP_RELPATH).chmod(0o644)
    assert out["repo_shape"] == compat.SHAPE_UNREADABLE
    assert out["downgrade_suspected"] is False


def test_shapes_are_always_reported(tmp_path):
    """탐지하지 못한 이유가 호출부에 드러나야 한다."""
    repo = make_repo(tmp_path)
    commit_mcp(repo, v1(["a"]), "backup")
    out = dd.detect(str(repo), base_dir=base_dir_with(tmp_path, None))
    assert out["repo_shape"] == compat.SHAPE_V1_ARRAY
    assert out["base_shape"] == compat.SHAPE_ABSENT
    assert out["downgrade_suspected"] is False


def test_not_a_git_repo_is_skipped(tmp_path):
    """탐지 실패가 백업을 막지 않는다."""
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / mc.BACKUP_RELPATH).write_text(v1(["a"]), encoding="utf-8")
    out = dd.detect(str(plain), base_dir=base_dir_with(tmp_path, v2({"a": {"command": "a"}})))
    assert out["status"] == "skipped"
    assert "reason" in out


def test_cli_prints_json(tmp_path):
    repo = make_repo(tmp_path)
    commit_mcp(repo, v2({"a": {"command": "a"}}), "backup")
    proc = subprocess.run(
        [sys.executable, SCRIPT, str(repo)],
        capture_output=True, text=True,
        env=dict(os.environ, HOME=str(tmp_path / "fakehome")),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["downgrade_suspected"] is False
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_downgrade.py -q
```
기대: `ModuleNotFoundError: No module named 'detect_downgrade'`로 collection error

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/skills/sync-backup/scripts/detect_downgrade.py`를 새로 만든다.

```python
#!/usr/bin/env python3
"""다운그레이드 사고를 탐지하고 마지막 정상(v2) 백업 커밋을 찾는다 (읽기 전용).

사용: detect_downgrade.py <레포 경로>

레포의 mcp-servers.json이 v1 배열인데 이 기기의 base는 v2 객체였다면, 옛 버전 기기가
덮어쓴 것이다. git 히스토리를 훑어 마지막 v2 커밋을 후보로 제시한다.

**자동으로 복구하지 않는다** — 옛 기기가 의도적으로 지운 서버까지 되살리기 때문이다.
탐지 실패가 백업을 막아서도 안 된다. 부가 기능이므로 status=skipped로 물러난다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402


def _git(repo_path, args):
    """git 표준 출력(bytes). 실패하면 RuntimeError."""
    proc = subprocess.run(["git", "-C", repo_path] + args, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "git 실패")
    return proc.stdout


def find_last_v2_commit(repo_path):
    """mcp-servers.json이 v2 객체였던 마지막 커밋. 없으면 None."""
    out = _git(
        repo_path,
        ["log", "--format=%H%x09%ad%x09%s", "--date=short", "--", mc.BACKUP_RELPATH],
    )
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        try:
            blob = _git(repo_path, ["show", "%s:%s" % (sha, mc.BACKUP_RELPATH)])
        except RuntimeError:
            continue          # 그 커밋에는 파일이 없었다. 탐색은 계속한다
        if compat.shape_of(blob) != "v2_object":
            continue
        servers = mc.parse_backup(blob)
        return {
            "sha": sha,
            "date": date,
            "subject": subject,
            "server_count": len(servers),
            "server_names": sorted(servers),
        }
    return None


def _shape_of_file(path):
    """파일을 읽어 형태를 판정한다.

    **못 읽음을 absent로 접지 않는다(불변식 6).** absent는 "파일이 없다"는 결론이지만
    권한·IO 실패는 아무 결론도 아니다. 접으면 다운그레이드 탐지가 조용히 꺼진다.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return compat.SHAPE_ABSENT
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw)


def _base_shape(base_dir):
    """base 블롭의 형태. read_base는 없으면 None, 그 외 OSError는 전파한다."""
    try:
        raw = ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir)
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw)


def detect(repo_path, base_dir=ss.BASE_DIR):
    """{"status", "downgrade_suspected", "repo_shape", "base_shape", "candidate"}

    repo_shape·base_shape를 항상 출력에 싣는다 — 탐지하지 못한 경우에도 왜 못 했는지가
    호출부에 드러나야 한다(불변식 6). SKILL.md가 "탐지할 수 없었다"와 "사고가 없다"를
    구별해 보고할 수 있는 근거가 이것이다.
    """
    repo_shape = _shape_of_file(os.path.join(repo_path, mc.BACKUP_RELPATH))
    base_shape = _base_shape(base_dir)
    suspected = compat.downgrade_suspected(repo_shape, base_shape)
    out = {
        "status": "ok",
        "downgrade_suspected": suspected,
        "repo_shape": repo_shape,
        "base_shape": base_shape,
        "candidate": None,
    }
    if suspected:
        try:
            out["candidate"] = find_last_v2_commit(repo_path)
        except (RuntimeError, OSError) as e:
            return {"status": "skipped", "reason": str(e),
                    "downgrade_suspected": suspected,
                    "repo_shape": repo_shape, "base_shape": base_shape,
                    "candidate": None}
    return out


def main():
    if len(sys.argv) != 2:
        print("사용: detect_downgrade.py <레포 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = detect(sys.argv[1])
    except OSError as e:
        out = {"status": "skipped", "reason": str(e)}
        print("다운그레이드 탐지 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(backup): 다운그레이드 탐지와 마지막 정상 백업 후보 탐색

레포가 v1 배열인데 base가 v2였으면 옛 기기가 덮어쓴 것이다. git 히스토리에서
마지막 v2 커밋을 찾아 날짜·서버 수·서버 이름과 함께 후보로 제시한다.

자동 복구하지 않는다 — 옛 기기가 의도적으로 지운 서버까지 되살린다.
git 실패는 skipped로 물러난다. 탐지 실패가 백업을 막으면 안 된다." \
  -- plugins/claude-sync/skills/sync-backup/scripts/detect_downgrade.py \
     plugins/claude-sync/tests/test_downgrade.py
```

---

### Task 9: 스크립트 경로 해석 — 세 SKILL.md의 0단계

지금 이 기기에서 이미 두 개가 매칭되고 `head -1`이 고르는 것은 `2.0.0`이다. 3.0.0 세션이 2.0.0의 `generate_metadata.py`를 실행하면 **표식이 조용히 안 써져** (a)와 (b)가 무력화된다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md:64-73`
- Modify: `plugins/claude-sync/skills/sync-status/SKILL.md:19-28`
- Modify: `plugins/claude-sync/skills/sync-restore/SKILL.md:38-51`
- Test: `plugins/claude-sync/tests/test_script_root.py` (신설)

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_script_root.py`를 새로 만든다.

```python
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
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_script_root.py -q
```
기대: 파이프라인 테스트 4개는 PASS, `test_all_skills_use_new_pipeline`·`test_no_skill_uses_old_pattern` 6개는 FAIL

- [ ] **Step 3: 세 SKILL.md의 0단계를 교체**

`plugins/claude-sync/skills/sync-backup/SKILL.md`의 `### 0. 스크립트 경로 확인` 절 전체(코드 블록과 그 아래 한 문장 포함)를 다음으로 교체한다.

````markdown
### 0. 플러그인 루트 확인

**실행 중인 플러그인과 같은 버전의 스크립트를 써야 한다.** 옛 버전 디렉토리가 지워지지 않고 남으므로, 아무거나 고르면 3.0.0 세션이 2.0.0의 스크립트를 실행해 표식이 조용히 안 써진다.

```bash
# plugins/cache 아래만 본다 — plugins/marketplaces는 레포 클론이지 설치본이 아니다.
# 여러 버전이 남아 있으므로 sort -V로 가장 높은 것을 고른다. head -1은 임의 선택이다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' | sort -V | tail -1)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

# 어느 버전을 쓰는지 눈에 보이게 한다. 불일치는 조용하면 안 된다.
echo "Plugin root: $SYNC_ROOT"
python3 -c 'import json,sys; print("Version:", json.load(open(sys.argv[1])).get("version","unknown"))' \
  "$SYNC_ROOT/.claude-plugin/plugin.json"
```

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 **즉시 중단하고** 사용자에게 안내한다. 어떤 버전을 실행할지 모르는 채로 진행해서는 안 된다.
````

`plugins/claude-sync/skills/sync-status/SKILL.md`의 같은 절을 다음으로 교체한다. `SYNC_SCRIPTS`의 스킬 이름과 `SYNC_BACKUP_SCRIPTS` 한 줄만 다르다.

````markdown
### 0. 플러그인 루트 확인

**실행 중인 플러그인과 같은 버전의 스크립트를 써야 한다.** 옛 버전 디렉토리가 지워지지 않고 남으므로, 아무거나 고르면 이 세션이 다른 버전의 스크립트를 실행하게 된다.

```bash
# plugins/cache 아래만 본다 — plugins/marketplaces는 레포 클론이지 설치본이 아니다.
# 여러 버전이 남아 있으므로 sort -V로 가장 높은 것을 고른다. head -1은 임의 선택이다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' | sort -V | tail -1)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-status/scripts"
SYNC_BACKUP_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

echo "Plugin root: $SYNC_ROOT"
python3 -c 'import json,sys; print("Version:", json.load(open(sys.argv[1])).get("version","unknown"))' \
  "$SYNC_ROOT/.claude-plugin/plugin.json"
```

`SYNC_BACKUP_SCRIPTS`는 다운그레이드 탐지(`detect_downgrade.py`)를 부르기 위해 필요하다. 읽기 전용 스크립트이므로 status가 불러도 안전하며, 복사본을 만들지 않는다.

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 즉시 중단하고 사용자에게 안내한다.
````

`plugins/claude-sync/skills/sync-restore/SKILL.md`의 같은 절을 다음으로 교체한다.

````markdown
### 0. 플러그인 루트 확인

**실행 중인 플러그인과 같은 버전의 스크립트를 써야 한다.** 옛 버전 디렉토리가 지워지지 않고 남으므로, 아무거나 고르면 이 세션이 다른 버전의 스크립트를 실행하게 된다.

```bash
# plugins/cache 아래만 본다 — plugins/marketplaces는 레포 클론이지 설치본이 아니다.
# 여러 버전이 남아 있으므로 sort -V로 가장 높은 것을 고른다. head -1은 임의 선택이다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' | sort -V | tail -1)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-restore/scripts"
SYNC_BACKUP_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

echo "Plugin root: $SYNC_ROOT"
python3 -c 'import json,sys; print("Version:", json.load(open(sys.argv[1])).get("version","unknown"))' \
  "$SYNC_ROOT/.claude-plugin/plugin.json"
```

`SYNC_BACKUP_SCRIPTS`가 필요한 이유는 base 블롭을 기록하는 주체가 `sync-backup/scripts/update_base.py` **하나뿐**이기 때문이다(파일 쪽과 같은 규칙을 공유한다). 이제 두 경로 모두 같은 `SYNC_ROOT`에서 나오므로 서로 다른 버전이 섞일 수 없다.

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 즉시 중단하고 사용자에게 안내한다.
````

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "fix(skills): 플러그인 루트를 정확히 고른다 — 버전 드리프트 차단

세 SKILL.md의 0단계가 find ~/.claude | head -1로 스크립트를 골랐다. 이 기기에서
이미 두 개가 매칭되고 head -1이 고르는 것은 2.0.0이다. 다른 하나는 marketplaces의
레포 클론이라 설치본도 아니다. 3.0.0이 설치되면 셋이 되고 순서는 파일시스템 순서다.

3.0.0 세션이 2.0.0의 generate_metadata.py를 실행하면 표식이 조용히 안 써지고
(a)와 (b)가 무력화된다.

plugins/cache 한정 + sort -V + tail -1로 교체하고, 고른 루트의 버전을 출력해
불일치가 눈에 보이게 한다. restore의 SYNC_BACKUP_SCRIPTS도 같은 루트에서 유도한다." \
  -- plugins/claude-sync/skills/sync-backup/SKILL.md \
     plugins/claude-sync/skills/sync-status/SKILL.md \
     plugins/claude-sync/skills/sync-restore/SKILL.md \
     plugins/claude-sync/tests/test_script_root.py
```

---

### Task 10: `/sync-backup` — 유일하게 차단하는 명령

호환성 검사는 **레포를 가져온 직후, 아무것도 쓰기 전에** 한다. 늦게 검사하면 이미 레포를 건드린 뒤가 된다.

다운그레이드 탐지는 **MCP 수집 앞(5.5)**이다. 수집이 `mcp-servers.json`을 v2로 덮어쓰면 "레포가 v1 배열"이라는 증거가 사라져 탐지 자체가 불가능해진다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md` (2단계 뒤, 6단계 앞, 7단계, 12단계)
- Test: `plugins/claude-sync/tests/test_script_root.py` (SKILL.md 계약 단언 추가)

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_script_root.py` 끝에 추가한다.

```python
def read_skill(name):
    with open(os.path.join(SKILLS_DIR, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def test_backup_checks_compat_before_writing_anything():
    text = read_skill("sync-backup")
    assert "compat.py" in text
    assert "2.5" in text
    # 호환성 검사가 파일 reconcile(4단계)보다 앞에 있어야 한다
    assert text.index("compat.py") < text.index("### 4. 파일별 reconcile")


def test_backup_detects_downgrade_before_mcp_collection():
    """수집이 레포 파일을 덮어쓰면 v1 배열이라는 증거가 사라진다."""
    text = read_skill("sync-backup")
    assert "detect_downgrade.py" in text
    assert text.index("detect_downgrade.py") < text.index("collect_mcp.py")


def test_backup_documents_marker_fields():
    text = read_skill("sync-backup")
    for field in ("written_by_version", "min_reader_version", "schema"):
        assert field in text
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_script_root.py -q -k backup
```
기대: `assert 'compat.py' in text`로 FAIL

- [ ] **Step 3: SKILL.md 수정**

`plugins/claude-sync/skills/sync-backup/SKILL.md`의 `### 3. Git User 설정` **바로 위**에 다음 절을 삽입한다.

````markdown
### 2.5 호환성 검사 (차단 지점)

**레포를 가져온 직후, 아무것도 쓰기 전에 검사한다.** 늦게 하면 이미 레포를 건드린 뒤가 된다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"
```

출력 JSON의 `blocked`가 `true`면 **여기서 중단한다.** 파일 복사(4단계)도 `plugins.json`(5단계)도 MCP 수집(6단계)도 하지 않는다.

**`message` 필드를 그대로 보여준다. 명령을 직접 타자하지 않는다** — 안내 문구는 `compat.py`가 만드는 것이 계약이고, SKILL.md가 따로 쓰면 드리프트한다.

덧붙이는 한 문장은 **`blocked`가 아니라 `reason`으로 분기한다.** `blocked`는 "차단"이라는 뜻일 뿐 "업그레이드하면 풀린다"는 뜻이 아니다.

| `reason` | 덧붙일 문장 |
|---|---|
| `older_than_min_reader` / `my_version_unknown` / `min_reader_unparsable` | "백업을 중단했습니다. 위 명령으로 업데이트한 뒤 다시 실행하세요." |
| `metadata_unreadable` | "백업을 중단했습니다. 표식을 읽을 수 없어 이 레포를 안전하게 다룰 수 있는지 판단할 수 없기 때문입니다." |

`metadata_unreadable`에 "업데이트하세요"를 붙이면 **틀린 해법**이다. 그 갈래의 `message`에는 업그레이드 명령이 의도적으로 빠져 있으므로 "위 명령"이 가리킬 것도 없다.

`pull_only` 가드가 1단계에서 하는 것과 같은 형태다. **차단은 이 명령에만 건다** — status를 막으면 진단 수단이 사라지고 restore를 막으면 업데이트 안내를 받을 경로가 사라진다.

`blocked`가 `false`면 조용히 다음 단계로 간다.
````

`### 6. mcp-servers.json 생성` **바로 위**에 다음 절을 삽입한다.

````markdown
### 5.5 다운그레이드 사고 탐지

**MCP 수집보다 먼저 한다.** 6단계가 `mcp-servers.json`을 v2로 덮어쓰면 "레포가 v1 배열"이라는 증거가 사라져 탐지 자체가 불가능해진다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_BACKUP_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"
```

`SYNC_BACKUP_SCRIPTS`는 0단계의 `SYNC_SCRIPTS`와 같다.

`status`가 `"skipped"`면 탐지만 건너뛰고 백업은 계속한다. 탐지는 부가 기능이다.

`downgrade_suspected`가 `true`면 레포의 `mcp-servers.json`이 v1 배열인데 이 기기의 base는 v2였다는 뜻이다 — **옛 버전 기기가 덮어썼다.** 사용자에게 다음을 보여주고 고르게 한다.

1. 사고 사실과 근거: "백업 레포의 MCP 파일이 옛 형식으로 되돌아가 있습니다. 이 기기가 마지막으로 본 것은 새 형식이었습니다."
2. `candidate`가 있으면 그 커밋의 `date`·`subject`·`server_count`·`server_names`
3. 선택지 셋:
   - **복구한다** — 후보 커밋의 파일을 레포 작업본에 되돌려 놓고 백업을 계속한다. 이어지는 6단계의 3-way 병합이 로컬과 정상적으로 합친다.
     ```bash
     git -C "$SYNC_REPO" show "<sha>:mcp-servers.json" > "$SYNC_REPO/mcp-servers.json"
     ```
   - **복구하지 않고 계속한다** — 현재 레포 상태 그대로 백업한다.
   - **중단한다** — 다른 기기의 상태를 확인한 뒤 다시 온다.

`candidate`가 `null`이면 히스토리에 v2 커밋이 없다는 뜻이다. 사고는 알리되 복구는 제안하지 않는다.

**자동으로 복구하지 않는다.** 옛 기기가 *의도적으로* 지운 서버까지 되살리기 때문이다.
````

`### 7. sync-metadata.json 생성`의 본문과 예시 JSON을 다음으로 교체한다.

````markdown
### 7. sync-metadata.json 생성

백업 시점의 파일 해시와 **버전 표식**을 기록한다.

```bash
python3 $SYNC_SCRIPTS/generate_metadata.py sync-metadata.json
```

생성되는 파일 예시:

```json
{
  "files": {
    "CLAUDE.md": "1c2d3e4f5a6b...(sha256 64자)",
    "agents/code-reviewer.md": "a3f2c1d4e5b6...(sha256 64자)",
    "skills/investigate/SKILL.md": "9d8e7f6a5b4c...(sha256 64자)"
  },
  "min_reader_version": "3.0.0",
  "schema": { "mcp-servers.json": 2 },
  "written_by_version": "3.0.0"
}
```

- `written_by_version` — 이 백업을 쓴 플러그인 버전. 정보일 뿐 판정에 쓰지 않는다.
- `min_reader_version` — **이 백업을 읽는 데 필요한 최소 버전.** 2.5단계의 차단 근거가 이것 하나다.
- `schema` — 사람이 읽는 요약. 항목별 보류는 각 파일 자체의 `version` 필드로 판정하므로 이 맵은 판정에 쓰지 않는다.

이 파일은 매 백업마다 재생성되는 파생 산출물이며 **reconcile 대상이 아니다.** 시각·기기명은 넣지 않는다 — 매번 diff가 생겨 소음이 된다. 언제·누가는 git commit이 이미 기록한다.
````

`### 12. 결과 보고`의 본문에 다음 문단을 덧붙인다.

````markdown
레포에 `sync-metadata.json`을 처음 쓴 경우(직전 커밋에 그 파일의 `min_reader_version`이 없었던 경우) 한 번만 알린다:

> "이 백업은 claude-sync 3.0.0 이상을 요구하도록 기록되었습니다. 더 낮은 버전의 기기에서 `/sync-backup`을 실행하면 차단됩니다. 다른 기기들도 `claude plugin update claude-sync` 후 재시작해 주세요."
````

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(backup): 2.5 호환성 차단과 5.5 다운그레이드 탐지

호환성 검사는 레포를 가져온 직후, 아무것도 쓰기 전에 한다. blocked면
파일 복사도 plugins.json도 MCP 수집도 하지 않고 중단한다. pull_only 가드와 같은
형태다. 차단은 이 명령에만 건다.

다운그레이드 탐지는 MCP 수집 앞이다. 수집이 레포 파일을 v2로 덮어쓰면
'레포가 v1 배열'이라는 증거가 사라져 탐지가 불가능해진다. 브리프는 수집 뒤(6.5)로
적었는데 그것은 동작하지 않는다.

7단계에 표식 세 필드의 성격을, 12단계에 첫 기록 안내를 적었다." \
  -- plugins/claude-sync/skills/sync-backup/SKILL.md \
     plugins/claude-sync/tests/test_script_root.py
```

---

### Task 11: `/sync-status` — 경고만, 아무것도 막지 않는다

버전이 안 맞을 때 사용자가 가장 먼저 실행할 명령이 status다. 그것마저 막으면 진단 수단이 사라진다. 읽기 전용이라 위험도 없다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-status/SKILL.md` (1단계 뒤, 3단계)
- Test: `plugins/claude-sync/tests/test_script_root.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_script_root.py` 끝에 추가한다.

```python
def test_status_warns_but_never_blocks():
    text = read_skill("sync-status")
    assert "compat.py" in text
    assert "detect_downgrade.py" in text
    assert "막지 않는다" in text
    # 분석을 중단시키는 지시가 없어야 한다
    assert "즉시 중단하고 분석" not in text


def test_status_puts_version_mismatch_first():
    text = read_skill("sync-status")
    assert "첫 줄" in text
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_script_root.py -q -k status
```
기대: `assert 'compat.py' in text`로 FAIL

- [ ] **Step 3: SKILL.md 수정**

`plugins/claude-sync/skills/sync-status/SKILL.md`의 `### 2. 메타데이터 기반 상태 분석` **바로 위**에 다음 절을 삽입한다.

````markdown
### 1.5 호환성 검사 (경고만)

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"
python3 "$SYNC_BACKUP_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"
```

`blocked`가 `true`면 **분석 결과 맨 위에 크게 경고한다.** `message`를 그대로 보여주고 다음을 덧붙인다:

> "이 상태에서는 `/sync-backup`이 차단됩니다. 아래 분석은 계속 진행합니다."

**이 명령은 아무것도 막지 않는다.** 버전이 안 맞을 때 사용자가 가장 먼저 실행할 명령이 status이고, 그것마저 막으면 진단 수단이 사라진다. 읽기 전용이라 위험도 없다.

`downgrade_suspected`가 `true`면 함께 알린다:

> "백업 레포의 MCP 파일이 옛 형식으로 되돌아가 있습니다 — 낮은 버전 기기가 덮어쓴 것으로 보입니다. `/sync-backup`을 실행하면 복구 후보를 제시합니다."

`candidate`가 있으면 그 커밋의 날짜와 서버 수도 함께 보여준다. status는 복구하지 않는다.
````

`### 3. 결과 요약`의 첫 줄 앞에 다음을 삽입한다.

````markdown
**버전 불일치가 있으면 요약의 첫 줄에 넣는다.** 예: "이 기기 3.0.0 / 백업 3.1.0 — `/sync-backup`이 차단됩니다."
````

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(status): 호환성·다운그레이드 경고 — 아무것도 막지 않는다

버전이 안 맞을 때 사용자가 가장 먼저 실행할 명령이 status다. 그것마저 막으면
진단 수단이 사라진다. 읽기 전용이라 위험도 없다.

불일치는 요약의 첫 줄에 넣고, 다운그레이드가 의심되면 복구는 backup에서
한다고 안내한다." \
  -- plugins/claude-sync/skills/sync-status/SKILL.md \
     plugins/claude-sync/tests/test_script_root.py
```

---

### Task 12: `/sync-restore` — 경고 후 진행 여부를 묻는다

restore는 pull-only라 레포를 훼손하지 않는다. 다만 **모르는 스키마의 항목을 건너뛴 부분 복원**이 된다는 점을 명시해야 한다. 그리고 여기가 **탈출구다** — 버전이 낮아 막혔다면 사용자에게 필요한 것은 `plugin update`이고, 그 안내가 복원 절차 안에 있어야 한다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-restore/SKILL.md` (2단계 뒤, 5단계, 7단계)
- Test: `plugins/claude-sync/tests/test_script_root.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_script_root.py` 끝에 추가한다.

```python
def test_restore_asks_before_continuing():
    text = read_skill("sync-restore")
    assert "compat.py" in text
    assert "부분 복원" in text
    assert "계속할지" in text


def test_restore_surfaces_update_guidance_in_plugin_step():
    """버전이 낮아 막혔다면 필요한 것은 plugin update다. 여기가 탈출구다."""
    text = read_skill("sync-restore")
    plugin_step = text[text.index("### 5. 플러그인 복원"):text.index("### 6. MCP 서버 복원")]
    assert "claude plugin update claude-sync" in plugin_step


def test_restore_reports_version_skips_as_pending_not_failure():
    text = read_skill("sync-restore")
    assert "보류" in text
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_script_root.py -q -k restore
```
기대: `assert 'compat.py' in text`로 FAIL

- [ ] **Step 3: SKILL.md 수정**

`plugins/claude-sync/skills/sync-restore/SKILL.md`의 `### 3. 파일별 reconcile` **바로 위**에 다음 절을 삽입한다.

````markdown
### 2.5 호환성 검사 (경고 후 질문)

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"
```

`blocked`가 `true`면 `message`를 보여주고 다음을 덧붙인 뒤 **계속할지 묻는다.**

> "restore는 레포를 훼손하지 않지만, 이 버전이 알아보지 못하는 항목은 건너뛴 **부분 복원**이 됩니다. 파일 동기화는 스키마와 무관하므로 정상 동작합니다. 계속할까요?"

선택지는 둘이다.

- **계속한다** — 파일은 정상 복원되고, 알아보지 못하는 MCP 항목만 보류된다.
- **중단하고 업데이트한다** — 5단계의 안내대로 플러그인을 올린 뒤 다시 실행한다.

**restore를 막지 않는 이유**: 버전이 낮아 backup이 막힌 사용자가 업데이트 안내를 받을 수 있는 경로가 restore다. 여기까지 막으면 탈출구가 사라진다.
````

`### 5. 플러그인 복원 (additive)`의 첫 문단 **앞**에 다음을 삽입한다.

````markdown
**2.5단계에서 버전 경고가 있었다면 이 안내를 가장 먼저 보여준다.** 사용자에게 지금 필요한 것은 다른 플러그인 설치가 아니라 claude-sync 자신의 업데이트다.

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync
```

그다음 Claude Code를 재시작하거나 `/reload-plugins`를 실행해야 적용된다. 업데이트 후 `/sync-restore`를 다시 실행하면 보류됐던 항목이 복원된다.
````

`### 7. 결과 보고`의 목록에서 `- **건너뛴 MCP 서버**:` 항목 아래에 다음을 추가한다.

````markdown
- **버전 때문에 보류한 항목**: 이 기기의 플러그인이 낮아 알아보지 못한 것. **"실패"가 아니라 "보류"로 보고한다** — 데이터는 레포에 그대로 있고 업데이트 후 다시 실행하면 복원된다
````

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(restore): 호환성 경고 후 질문 — 막지 않는 것이 탈출구다

버전이 낮아 backup이 막힌 사용자가 업데이트 안내를 받을 경로가 restore다.
여기까지 막으면 탈출구가 사라진다. 대신 부분 복원이 된다는 점을 명시하고
계속할지 묻는다.

5단계에서 claude-sync 자신의 업데이트 안내를 가장 먼저 노출하고,
7단계는 버전 때문에 못 읽은 항목을 실패가 아니라 보류로 보고한다." \
  -- plugins/claude-sync/skills/sync-restore/SKILL.md \
     plugins/claude-sync/tests/test_script_root.py
```

---

### Task 13: 반복 적용·교대 적용

> 단발 호출 테스트가 전부 통과하는데도 시스템이 데이터를 잃은 전례가 이 프로젝트에 있다.

**Files:**
- Test: `plugins/claude-sync/tests/test_compat_cycle.py` (신설)

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_compat_cycle.py`를 새로 만든다.

```python
"""반복 적용·교대 적용 — 상태 기계가 발산하거나 흔적을 남기지 않는지 본다.

실제 ~/.claude는 건드리지 않는다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import collect_mcp  # noqa: E402
import generate_metadata as gm  # noqa: E402

COMPAT_CLI = os.path.join(os.path.dirname(__file__), "..", "lib", "compat.py")


def fake_claude_dir(tmp_path):
    d = tmp_path / "claude"
    (d / "agents").mkdir(parents=True)
    (d / "agents" / "a.md").write_text("a", encoding="utf-8")
    (d / "CLAUDE.md").write_text("c", encoding="utf-8")
    return str(d)


def plugin_json(tmp_path, version="3.0.0"):
    path = tmp_path / "plugin.json"
    path.write_text(json.dumps({"version": version}), encoding="utf-8")
    return str(path)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def dir_snapshot(path):
    out = {}
    for root, _, files in os.walk(path):
        for f in files:
            full = os.path.join(root, f)
            out[os.path.relpath(full, path)] = read_bytes(full)
    return out


def test_metadata_stable_across_three_runs(tmp_path):
    """세 번 돌려도 바이트가 같아야 한다. 매번 diff가 나면 표식이 소음이 된다."""
    claude_dir, pj = fake_claude_dir(tmp_path), plugin_json(tmp_path)
    outs = []
    for i in range(3):
        p = str(tmp_path / ("m%d.json" % i))
        gm.write_metadata(p, gm.build_metadata(claude_dir, pj))
        outs.append(read_bytes(p))
    assert outs[0] == outs[1] == outs[2]


def test_repeated_backup_does_not_diverge(tmp_path):
    """같은 로컬로 collect를 두 번 돌리면 레포 파일과 base가 그대로여야 한다."""
    local = tmp_path / "claude.json"
    local.write_text(json.dumps({"mcpServers": {"a": {"command": "a"}}}), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    staging = str(tmp_path / "staging")
    base_dir = str(tmp_path / "base")

    collect_mcp.collect(str(repo), staging, claude_json_path=str(local), base_dir=base_dir)
    # 1회차 결과를 base로 올린다 (SKILL.md 11단계가 하는 일)
    os.makedirs(base_dir, exist_ok=True)
    with open(os.path.join(base_dir, mc.BACKUP_RELPATH), "wb") as f:
        f.write(read_bytes(os.path.join(staging, mc.BACKUP_RELPATH)))
    first = read_bytes(os.path.join(str(repo), mc.BACKUP_RELPATH))

    collect_mcp.collect(str(repo), staging, claude_json_path=str(local), base_dir=base_dir)
    second = read_bytes(os.path.join(str(repo), mc.BACKUP_RELPATH))
    assert first == second


def test_block_then_unblock_leaves_no_state(tmp_path):
    """교대 적용: 차단됐다가 해제되면 흔적 없이 통과한다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    meta_path = repo / compat.METADATA_RELPATH
    pj = plugin_json(tmp_path, "3.0.0")

    meta_path.write_text(json.dumps({"min_reader_version": "4.0.0"}), encoding="utf-8")
    blocked_before = dir_snapshot(str(repo))
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is True
    assert dir_snapshot(str(repo)) == blocked_before   # 차단이 레포를 건드리지 않았다

    meta_path.write_text(json.dumps({"min_reader_version": "3.0.0"}), encoding="utf-8")
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is False

    meta_path.write_text(json.dumps({"min_reader_version": "4.0.0"}), encoding="utf-8")
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is True


def test_cli_usage_error_is_clean(tmp_path):
    """가짜 안전망 방지 — sys.exit(1)이 없어도 IndexError가 exit 1을 대신 만든다.

    종료 코드만 보면 변이를 못 잡는다. 트레이스백이 없고 stdout이 비어 있어야
    "의도된 사용법 오류"이며, 인자를 두 개 준 경우도 함께 본다(그 경로는 변이 시 exit 0이 된다).
    """
    for argv in ([], [str(tmp_path), "extra"]):
        proc = subprocess.run([sys.executable, COMPAT_CLI] + argv,
                              capture_output=True, text=True)
        assert proc.returncode == 1, argv
        assert "사용:" in proc.stderr
        assert "Traceback" not in proc.stderr, argv
        assert proc.stdout == "", argv


def test_gate_keeps_boolean_version_readable(tmp_path):
    """{"version": true}가 통과함을 고정한다 — bool 제외가 의도임을 문서화한다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"version": True, "servers": {"a": {"command": "a"}}}),
                    encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


def test_check_is_idempotent(tmp_path):
    """같은 입력이면 몇 번을 불러도 같은 판정이다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / compat.METADATA_RELPATH).write_text(
        json.dumps({"min_reader_version": "4.0.0", "written_by_version": "4.0.0"}),
        encoding="utf-8",
    )
    pj = plugin_json(tmp_path)
    results = [compat.check(str(repo), plugin_json_path=pj) for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_upgrade_then_write_marker_unblocks_older_repo(tmp_path):
    """3.0.0이 쓴 레포는 3.0.0이 다시 읽을 수 있다 — 자기가 자기를 막지 않는다."""
    claude_dir, pj = fake_claude_dir(tmp_path), plugin_json(tmp_path, "3.0.0")
    repo = tmp_path / "repo"
    repo.mkdir()
    gm.write_metadata(
        str(repo / compat.METADATA_RELPATH), gm.build_metadata(claude_dir, pj)
    )
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is False
```

- [ ] **Step 2: test를 실행하여 실패 또는 통과를 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_compat_cycle.py -q
```
기대: 전부 PASS. 하나라도 FAIL이면 앞선 task의 구현에 결함이 있는 것이므로 **테스트를 고치지 말고 구현을 고친다.**

- [ ] **Step 3: 전체 테스트 실행**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기대: 전부 PASS (실패 0)

- [ ] **Step 4: Commit**

```bash
git commit -m "test: 반복 적용·교대 적용 — 단발 테스트가 못 잡는 것

표식은 세 번 돌려도 바이트가 같아야 하고, 같은 로컬로 두 번 백업해도 레포가
발산하면 안 된다. 차단은 레포에 어떤 흔적도 남기지 않아야 하고, 해제되면 다시
통과해야 한다. 3.0.0이 쓴 레포를 3.0.0이 다시 읽을 수 있어야 한다.

단발 호출 테스트가 전부 통과하는데도 데이터를 잃은 전례가 이 프로젝트에 있다." \
  -- plugins/claude-sync/tests/test_compat_cycle.py
```

---

### Task 14: 문서 갱신과 최종 검증

**Files:**
- Modify: `docs/superpowers/2026-08-21-release-3.0.0-PLAN.md`
- Modify: `docs/superpowers/2026-08-21-version-compat-BRIEF.md`

- [ ] **Step 1: 전체 테스트와 버전 불변 확인**

실행:
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
grep -n '"version"' .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
```
기대: 전부 PASS, 그리고 두 파일 모두 `"version": "3.0.0"` (**올리지 않았어야 한다**)

- [ ] **Step 2: 릴리즈 계획의 작업 상태 갱신**

`docs/superpowers/2026-08-21-release-3.0.0-PLAN.md`의 작업 표에서 2번 행을 다음으로 교체한다.

```markdown
| 2 | **버전 호환성 대처** — 표식·차단·복구 | ✅ 완료 | `feat/version-compat` |
```

같은 파일의 `- 상태: 두 작업 중 **1/2 완료**`를 다음으로 교체한다.

```markdown
- 상태: 두 작업 중 **2/2 완료** — 배포 절차(4장)로 진행 가능
```

`## 3. 다음 세션이 할 일` 절 제목 아래 첫 줄에 다음을 삽입한다.

```markdown
> **작업 2는 완료되었다.** 남은 것은 4장의 배포 절차뿐이다. 설계는
> `specs/2026-08-21-version-compat-design.md`, 구현 계획은
> `plans/2026-08-21-version-compat.md`에 있다.
```

- [ ] **Step 3: 브리프의 상태 갱신**

`docs/superpowers/2026-08-21-version-compat-BRIEF.md`의 `- 상태: **착수 전.** 조사·결정이 선행되어야 한다.`를 다음으로 교체한다.

```markdown
- 상태: **완료.** 조사(2장)와 결정(3장)이 끝났고 설계는
  `specs/2026-08-21-version-compat-design.md`, 구현은 `plans/2026-08-21-version-compat.md`로 이어졌다.
  **이 문서는 조사 기록으로 남긴다.** 5장의 다운그레이드 탐지 위치(6.5단계)는
  설계 8.1에서 5.5단계로 정정되었다 — MCP 수집이 레포 파일을 덮어쓰면 증거가 사라진다.
```

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: 3.0.0 작업 2 완료 반영 — 릴리즈 계획과 브리프 상태 갱신

브리프는 조사 기록으로 남기고, 다운그레이드 탐지 위치가 6.5에서 5.5로 정정된
사실을 명시한다." \
  -- docs/superpowers/2026-08-21-release-3.0.0-PLAN.md \
     docs/superpowers/2026-08-21-version-compat-BRIEF.md
```

- [ ] **Step 5: PR 생성 (사용자 승인 후)**

푸시는 외부 동작이므로 **사용자에게 확인을 받고** 실행한다. target이 `main`이 아니라 `release/3.0.0`인지 반드시 확인한다.

```bash
git push -u origin feat/version-compat
gh pr create --base release/3.0.0 --head feat/version-compat \
  --title "feat: 버전 호환성 대처 — 표식·가드·다운그레이드 탐지"
```

---

## 완료 정의

- [ ] **업그레이드 명령이 SKILL.md에 하드코딩되어 남아 있지 않다.** 착수 시점의 실측 분포는
  `lib/compat.py`의 `_UPGRADE_COMMANDS` 1곳 + `sync-backup/SKILL.md:205` + `sync-restore/SKILL.md:150`
  + `sync-status/SKILL.md:65` + `README.md`·`README.ko.md` 각 1곳이다.
  - compat 갈래(Task 10·11·12): 세 SKILL.md가 명령을 타자하지 않고 `compat.py`의 `message`를 그대로 옮긴다
  - MCP 갈래: `compare_mcp.py`·`collect_mcp.py`가 `UnknownBackupSchema`를 잡을 때 payload에 안내 문구를
    함께 실어 SKILL.md가 옮기기만 하게 한다. 이때 `_UPGRADE_COMMANDS`를 public으로 여는 것이 정당해진다
  - **`sync-status/SKILL.md:65`는 지금 `claude plugin update claude-sync` 한 줄뿐이라 브리프가 못박은
    "명령은 항상 두 줄"을 이미 어기고 있다.** 위 둘 중 하나를 하면 자동으로 해결된다
- [ ] `uv run --with pytest pytest plugins/claude-sync/tests -q`가 전부 통과하고, **기준선 166개가 하나도 깨지지 않았다** (신규 100개 이상 추가)
- [ ] `plugin.json`·`marketplace.json`이 여전히 `3.0.0`
- [ ] `test_min_reader_major_matches_plugin_json`이 통과한다 (semver 불변식)
- [ ] 세 SKILL.md 어디에도 `find ~/.claude -path`가 없다
- [ ] 반복 적용·교대 적용 테스트가 통과한다
- [ ] PR target이 `release/3.0.0`이다
- [ ] 이 기기에서 `/sync-backup`을 **실행하지 않았다** (캐시가 아직 2.0.0)
