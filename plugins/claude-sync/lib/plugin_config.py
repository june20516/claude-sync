#!/usr/bin/env python3
"""claude-sync의 플러그인 동기화 어댑터.

데이터 소스는 두 파일이고 역할이 다르다(spec 3장) —
  ~/.claude/settings.json                    세 섹션 값의 **유일한** 원천
  ~/.claude/plugins/installed_plugins.json   각 항목의 auto 플래그 **하나만**
installed_plugins.json을 값의 원천으로 삼지 않는 이유는 그것이 settings.json에서
파생되기 때문이다. `claude plugin list --json`을 쓰지 않는 이유는 "키 부재"와 false를
구별하지 못하기 때문이다.

키 단위 3-way 판정·인식은 값 무관 코어(keyed_sync)에 있다. 이 모듈은 플러그인의 도메인
지식만 얹는다 — 인식(4.4)·정규화(7.2)·보류(7.3)·복원 가능성(8장)·비밀 키(6.1)·
정합성(7.6).

**한 문서 안에 세 섹션이 있다.** load_backup·parse_base·parse_backup이 돌려주는 것은
매핑 하나가 아니라 {섹션 이름: 매핑}이고, 코어 함수는 **섹션 하나씩** 부른다.

예외별 skip 범위 (호출부가 각각 **다른** except 절로 잡아야 한다) —
  LocalConfigUnavailable   전체 skip (settings.json = 세 섹션 값의 유일한 원천)
  UnknownBackupSchema      전체 skip (레포 문서를 알아볼 수 없다)
  AutoFlagsUnavailable     enabledPlugins·pluginConfigs만 skip, marketplaces는 진행
  HeldStateUnavailable     pluginConfigs만 skip

**이 네 예외를 공통 기반 클래스로 묶지 말 것.** `except PluginReadUnavailable` 한 줄로
전부 잡히면 위의 부분 skip 규정이 조용히 전체 skip으로 바뀐다 — auto를 못 읽었을 뿐인데
마켓플레이스까지 날아가고, 그 축소는 예외 종류가 같아 보이므로 로그에 흔적을 남기지 않는다.
skip 범위가 다른 것이 곧 클래스가 다른 이유다.

PermissionError 등 그 외 OSError는 네 읽기 함수 모두에서 **전파한다**(감싸지 않는다) —
감싸면 "읽을 수 없음"이 "0개"나 "보류 없음"으로 접힌다.
"""
import copy
import hashlib
import json
import os

import keyed_sync as ks

SCHEMA_VERSION = 2
BACKUP_RELPATH = "plugins.json"
SECTIONS = ("enabledPlugins", "extraKnownMarketplaces", "pluginConfigs")

# pluginConfigs 정규화가 options 값을 이것으로 덮는다(7.2). 키 이름은 보존한다 —
# 레포 파일만 보고 "복원할 때 어떤 값을 되물어야 하는지"를 알아야 하기 때문이다(6.1).
SENTINEL = "<REDACTED>"

# 별칭은 같은 뜻이다. 둘 다 있으면 앞의 것을 채택한다 — CLI와 같은 규칙이고,
# 순서가 곧 우선순위다. 이 튜플의 순서를 바꾸면 규칙이 뒤집힌다.
MARKETPLACE_ALIASES = ("extraKnownMarketplaces", "additionalMarketplaces")

DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")
DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
DEFAULT_HELD = os.path.expanduser("~/.claude/.sync-state/plugins-held.json")

HELD_SCHEMA_VERSION = 1
EMPTY_HELD = {"pluginConfigs": {}, "release": {"enabledPlugins": []}}

# installed_plugins.json 자체가 달고 다니는 스키마 버전. 다른 두 게이트(SCHEMA_VERSION·
# HELD_SCHEMA_VERSION)와 달리 **이 파일의 소유자는 이 프로젝트가 아니라 claude CLI다.**
# CLI가 이 파일을 v3으로 올리면 여기도 올려야 한다 — 그때까지 **모든 기기에서 동시에**
# enabledPlugins·pluginConfigs 백업이 멈춘다. 가시적이고 되돌릴 수 있는 정지이므로
# fail-closed 자체는 옳다(반대편은 N6, 되돌릴 수 없다). 갱신 의무만 잊지 말 것.
INSTALLED_SCHEMA_VERSION = 2

# 사용자에게 reason으로 그대로 나가는 문구의 꼬리. 같은 함수 안에서 갈래마다 다르면
# "그래서 무엇이 빠졌는가"를 사용자가 갈래마다 다시 추측해야 한다. 함수당 하나로 고정한다.
SKIP_ALL = "플러그인 단계 전체를 건너뛴다"
SKIP_AUTO_SECTIONS = "enabledPlugins·pluginConfigs를 건너뛴다"
SKIP_PLUGIN_CONFIGS = "pluginConfigs를 건너뛴다"

# 코어의 예외를 그대로 re-export한다. 클래스가 두 벌이 되면 스크립트의 except 튜플이
# 갈라지고, 갱신을 잊으면 traceback으로 죽어 결함 C가 되살아난다.
LocalConfigUnavailable = ks.LocalConfigUnavailable
UnknownBackupSchema = ks.UnknownBackupSchema


class AutoFlagsUnavailable(Exception):
    """installed_plugins.json에서 auto 판정을 할 수 없다 (spec 3.4).

    **전체 skip이 아니라 두 섹션(enabledPlugins·pluginConfigs)만 skip하는 근거다.**
    extraKnownMarketplaces는 auto와 무관하므로 계속 진행한다.
    "전량 포함 + 경고"로 접으면 auto 항목이 레포에 실리고 base가 전진해, 타 기기의
    restore가 그것을 설치하며 **되돌릴 수 없는 수동 승격**을 일으킨다(N6).
    """


class HeldStateUnavailable(Exception):
    """plugins-held.json을 알아볼 수 없다 (spec 6.4).

    **파일 부재는 이 예외가 아니다** — 보류 없음이 첫 실행의 정상 상태다.
    이 예외는 pluginConfigs 한 섹션만 skip하는 근거다.
    """


# ---------------------------------------------------------------- 로컬 읽기 (3.2)

def _section_of(data, key, path):
    """settings.json의 한 섹션. 키가 없으면 {}, 있는데 객체가 아니면 읽기 실패다.

    이 구별이 없으면 {"enabledPlugins": null}인 기기에서 "0개"로 읽혀 base에 있던
    항목 전부가 케이스 3(삭제)으로 판정되고 레포에서 전멸한다.

    path를 인자로 받는 이유는 메시지 때문이다 — 이 문구가 그대로 사용자에게
    reason으로 나가는데, settings.json과 plugins-held.json이 **둘 다 pluginConfigs라는
    섹션 이름을 갖는다.** 경로가 없으면 어느 파일을 고쳐야 하는지 알 수 없다.
    """
    if key not in data:
        return {}
    value = data[key]
    if not isinstance(value, dict):
        raise LocalConfigUnavailable(
            "%s의 %s가 객체가 아님(%s) — %s"
            % (path, key, type(value).__name__, SKIP_ALL))
    return dict(value)


def _marketplaces_of(data, path):
    """별칭 둘 중 **먼저 존재하는 쪽**만 읽고 검증한다 (3.3).

    둘 다 있으면 additionalMarketplaces를 무시한다 — CLI와 같은 규칙이다.
    채택하지 않은 쪽의 형태는 보지 않는다. 쓰지 않는 값이기 때문이다.
    """
    for key in MARKETPLACE_ALIASES:
        if key in data:
            return _section_of(data, key, path)
    return {}


def read_local_sections(settings_path=None):
    """settings.json에서 세 섹션을 읽는다. backup·status·restore가 **같은 정의**를 쓴다.

    스킬마다 다른 필터를 적용하면 같은 기기에서 backup↔restore를 교대할 때 base가 두
    정의 사이를 오간다(spec 3.1). auto 항목도 여기서는 빼지 않는다 — local에 그대로 두고
    hold 집합에 넣는다. 그래야 restore가 "이미 있다"로 보고 재설치하지 않는다(N6).
    PermissionError 등 그 외 OSError는 전파한다(감싸지 않는다).
    """
    path = DEFAULT_SETTINGS if settings_path is None else settings_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise LocalConfigUnavailable("%s 없음 — %s" % (path, SKIP_ALL)) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LocalConfigUnavailable(
            "%s 파싱 실패: %s — %s" % (path, e, SKIP_ALL)) from e
    if not isinstance(data, dict):
        raise LocalConfigUnavailable(
            "%s 최상위가 객체가 아님 — %s" % (path, SKIP_ALL))
    return {
        "enabledPlugins": _section_of(data, "enabledPlugins", path),
        "extraKnownMarketplaces": _marketplaces_of(data, path),
        "pluginConfigs": _section_of(data, "pluginConfigs", path),
    }


def read_auto_ids(installed_path=None):
    """의존성으로 자동 설치된 플러그인 id 집합 (3.4).

    plugins[<id>]는 **배열**이다 — 같은 플러그인이 스코프별로 여러 벌 설치될 수 있다.
    user 스코프 항목 중 auto가 True인 것이 하나라도 있으면 그 id는 auto다.

    이 집합은 hold 계산의 입력이다. **로컬에서 키를 지우는 데 쓰지 않는다.**

    **"알아볼 수 없다"의 전수 목록 — 아래는 전부 AutoFlagsUnavailable이다:**
      1. 파일 부재
      2. JSON 구문 오류 / 인코딩 오류
      3. 최상위가 객체가 아님
      4. version이 INSTALLED_SCHEMA_VERSION보다 높다고 주장함 (version 키 부재는 정상)
      5. plugins 키 부재
      6. plugins가 객체가 아님
      7. plugins[<id>]가 배열이 아님
      8. plugins[<id>]의 원소가 객체가 아님
      9. 원소에 auto가 있는데 bool이 아님
     10. 원소에 scope가 있는데 문자열이 아님

    9·10에서 **키 부재는 이상이 아니다.** 실기기의 항목에는 auto 키가 아예 없고
    "키 부재 = auto 아님"이 정상 판정이다. 값이 있는데 타입이 다른 경우만 막는다.
    값 비교가 `is True`·`== "user"`라 auto=1·auto="true"·scope=["user"]가 전부 조용히
    "auto 아님"으로 접히는데, 원소가 dict가 아닌 것은 막으면서 dict 안의 타입 이상은
    통과시키는 것은 같은 함수 안의 비일관이다.

    5·8·9·10을 빈 집합으로 접지 않는 이유가 이 함수의 존재 이유다. auto 판정이 거짓으로
    비면 auto 항목이 hold에 들어가지 못하고 그대로 레포에 실려 승격되며, 타 기기의
    restore가 그것을 설치한다 — **되돌릴 수 없다**(N6). 반대로 과하게 raise하면 두
    섹션이 skip될 뿐이고 레포는 그대로다. 비대칭이 명확하므로 전부 raise 쪽으로 조인다.

    PermissionError 등 그 외 OSError는 전파한다(감싸지 않는다).
    """
    path = DEFAULT_INSTALLED if installed_path is None else installed_path

    def unreadable(detail):
        return AutoFlagsUnavailable("%s: %s — auto 판정 불가로 %s"
                                    % (path, detail, SKIP_AUTO_SECTIONS))

    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise unreadable("파일 없음") from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise unreadable("파싱 실패(%s)" % e) from e
    if not isinstance(data, dict):
        raise unreadable("최상위가 객체가 아님(%s)" % type(data).__name__)
    if ks.claims_newer_schema(data.get("version"), INSTALLED_SCHEMA_VERSION):
        raise unreadable("상위 버전 주장(version=%r)" % data.get("version"))
    if "plugins" not in data:
        raise unreadable("plugins 키가 없음")
    plugins = data["plugins"]
    if not isinstance(plugins, dict):
        raise unreadable("plugins가 객체가 아님(%s)" % type(plugins).__name__)
    out = set()
    for plugin_id, entries in plugins.items():
        if not isinstance(entries, list):
            raise unreadable("plugins[%s]가 배열이 아님(%s)"
                             % (plugin_id, type(entries).__name__))
        for entry in entries:
            if not isinstance(entry, dict):
                raise unreadable("plugins[%s]의 원소가 객체가 아님(%s)"
                                 % (plugin_id, type(entry).__name__))
            # 키 부재는 통과시킨다("auto 아님"이 정상 판정). 값이 있는데 타입이 다르면
            # `is True`·`== "user"`가 조용히 거짓이 되어 판정에서 빠진다 — N6의 입구다.
            if "auto" in entry and not isinstance(entry["auto"], bool):
                raise unreadable("plugins[%s]의 auto가 bool이 아님(%r)"
                                 % (plugin_id, entry["auto"]))
            if "scope" in entry and not isinstance(entry["scope"], str):
                raise unreadable("plugins[%s]의 scope가 문자열이 아님(%r)"
                                 % (plugin_id, entry["scope"]))
        if any(e.get("scope") == "user" and e.get("auto") is True for e in entries):
            out.add(plugin_id)
    return frozenset(out)


def read_held_state(held_path=None):
    """이 기기의 보류 선택 (6.4·7.3). 파일이 없으면 보류 없음.

    {"pluginConfigs": {id: 지문}, "release": {"enabledPlugins": [id]}}

    **없음과 깨짐을 구별한다.** 부재는 첫 실행의 정상 상태이고, 깨짐은 pluginConfigs
    섹션을 skip할 사유다. 형태를 알아볼 수 없는데 빈 상태로 접으면 사용자의 보류 선택이
    조용히 사라지고 restore가 매번 다시 묻는다.

    **부재 갈래는 파일 부재만 담는다** — PermissionError까지 여기로 접으면 읽을 수 없는
    보류 파일이 "보류 없음"이 되어, 사용자가 보류해 둔 pluginConfigs가 그대로 레포로 올라간다.

    반환값은 EMPTY_HELD와 어떤 객체도 공유하지 않는다(deepcopy) — 호출부가 결과를
    변형하면 모듈 상수가 오염되어 그 프로세스의 이후 모든 읽기가 거짓 보류를 돌려준다.

    이 파일의 **소유자는 plan_plugins.py apply-base 하나뿐이다.** 다른 스크립트는 읽기만 한다.
    """
    path = DEFAULT_HELD if held_path is None else held_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError:
        return copy.deepcopy(EMPTY_HELD)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HeldStateUnavailable(
            "%s: 파싱 실패(%s) — %s" % (path, e, SKIP_PLUGIN_CONFIGS)) from e
    if not isinstance(data, dict):
        raise HeldStateUnavailable("%s: 최상위가 객체가 아님(%s) — %s"
                                   % (path, type(data).__name__, SKIP_PLUGIN_CONFIGS))
    if ks.claims_newer_schema(data.get("version"), HELD_SCHEMA_VERSION):
        raise HeldStateUnavailable("%s: 상위 버전 주장(version=%r) — %s"
                                   % (path, data.get("version"), SKIP_PLUGIN_CONFIGS))
    configs = data.get("pluginConfigs", {})
    if not isinstance(configs, dict) or not all(
            isinstance(v, str) for v in configs.values()):
        raise HeldStateUnavailable("%s: pluginConfigs가 {id: 지문} 형태가 아님 — %s"
                                   % (path, SKIP_PLUGIN_CONFIGS))
    release = data.get("release", {})
    if not isinstance(release, dict):
        raise HeldStateUnavailable("%s: release가 객체가 아님(%s) — %s"
                                   % (path, type(release).__name__, SKIP_PLUGIN_CONFIGS))
    released = release.get("enabledPlugins", [])
    if not isinstance(released, list) or not all(isinstance(v, str) for v in released):
        raise HeldStateUnavailable("%s: release.enabledPlugins가 문자열 배열이 아님 — %s"
                                   % (path, SKIP_PLUGIN_CONFIGS))
    return {"pluginConfigs": dict(configs),
            "release": {"enabledPlugins": list(released)}}


def read_hold_inputs(installed_path=None, held_path=None):
    """auto 집합과 보류 상태를 읽고, 실패에 대응하는 **섹션 skip 사유**를 함께 돌려준다.

    반환: (auto_ids, held_state, {섹션: 사유})

    두 실패는 범위가 다르다(spec 9.1.2·9.3.6):
      installed_plugins.json 판정 불가 → enabledPlugins·pluginConfigs 두 섹션
      plugins-held.json 깨짐          → pluginConfigs 한 섹션
    어느 쪽도 전체 skip이 아니다 — extraKnownMarketplaces는 auto와도 보류 파일과도
    무관하므로 계속 진행한다.

    **이 함수를 스크립트마다 다시 짜지 않는다.** 범위가 갈리면 backup은 두 섹션을 접는데
    restore는 안 접는 상태가 생기고, 그 비대칭은 예외 종류가 같아 보여 흔적을 남기지 않는다.

    실패한 쪽의 값은 "보류 없음"으로 채우지만 **그 섹션은 어차피 skip되므로 쓰이지
    않는다.** 채우는 이유는 나머지 섹션의 훅을 만들 수 있게 하기 위해서다.

    PermissionError 등 그 외 OSError는 두 읽기 함수와 마찬가지로 전파한다 — 여기서
    삼키면 "읽을 수 없음"이 "auto 없음·보류 없음"으로 접혀 N6의 입구가 열린다.
    """
    skipped = {}
    try:
        auto_ids = read_auto_ids(installed_path)
    except AutoFlagsUnavailable as e:
        auto_ids = frozenset()
        skipped["enabledPlugins"] = str(e)
        skipped["pluginConfigs"] = str(e)
    try:
        held_state = read_held_state(held_path)
    except HeldStateUnavailable as e:
        held_state = copy.deepcopy(EMPTY_HELD)
        # setdefault다 — auto 실패 사유가 이미 있으면 그것이 더 넓은 원인이다.
        # 덮으면 사용자가 보는 reason이 "보류 파일이 깨졌다"뿐이라, 정작 enabledPlugins도
        # 함께 접힌 이유(auto 판정 불가)를 어디에서도 읽을 수 없게 된다.
        skipped.setdefault("pluginConfigs", str(e))
    return auto_ids, held_state, skipped


def skipped_section(reason):
    """섹션 skip 갈래의 **보고 모양**. 섹션 skip을 보고하는 모든 스크립트가 이것을 쓴다.

    SKILL.md는 그 스크립트들의 sections를 같은 코드로 읽는다. 각자 리터럴로 두면 한쪽이
    "message"로 써도 갈린 것을 알 자리가 없고, 그러면 그 스크립트의 skip이 조용히 읽히지
    않는다 — 섹션이 빠졌다는 사실 자체가 사용자에게 도달하지 않는다.

    **이 함수가 리터럴을 막지는 못한다** — 같은 모양을 손으로 쓰는 것을 금지하는 장치는
    없다. 실제로 스크립트들의 main()은 **최상위** skip을 리터럴로 쓴다. 그것을 여기로
    끌어오지 않는 것은 층위가 다르기 때문이다: 최상위 skip은 sections 자체가 없는 **문서
    전체**의 갈래다. 같은 두 키 리터럴이 mcp 계열 셋(compare_mcp·collect_mcp·plan_mcp)에도
    그대로 있는데 **셋 다 plugin_config를 import하지 않는다**(detect_downgrade는 같은
    status·reason 짝을 더 넓은 dict 안에 쓴다). 이 어댑터의 헬퍼 뒤에 숨기면 그 스크립트들이
    공유하는 모양이 오히려 두 곳에서 정의된다. 여기가 정하는 것은 **섹션 층위 하나**다.
    """
    return {"status": "skipped", "reason": reason}


# ---------------------------------------------------------------- 인식 계층 (4.4)

def _all_sections(mapping):
    """어떤 매핑이든 세 섹션 키를 **전부** 갖게 편다. 호출부의 KeyError를 없앤다.

    parse_backup과 load_backup은 둘 다 "알아볼 수 없음"이나 "파일 부재"를 빈 {}로
    degrade하는데, 그 {}를 그대로 돌려주면 호출부의 repo["enabledPlugins"]가 KeyError로
    죽는다 — 읽기 실패를 안전하게 접겠다는 설계가 정반대로 traceback이 된다.
    셋 중 parse_base만 이 평탄화를 쓰지 않는다. 거기서는 {}(이력이 비었다)와
    None(이력을 못 믿는다)의 구별 자체가 반환값의 의미이기 때문이다.
    """
    return {name: mapping.get(name, {}) for name in SECTIONS}


def _recognized_sections(obj):
    """알아볼 수 있는 백업 문서면 {섹션: 매핑}, 아니면 None.

    네 조건이 **전부** 참일 때만 인식한다(spec 4.4):
      1. 최상위가 객체다
      2. version이 없거나 SCHEMA_VERSION 이하다 (float 우회 포함, bool·문자열은 제외)
      3. 아는 섹션 중 **적어도 하나**가 존재한다
      4. 존재하는 **모든** 아는 섹션이 객체다

    조건 4가 없으면 {"enabledPlugins": {...}, "extraKnownMarketplaces": "손상"}이
    인식되어 손상된 섹션이 "0개"로 읽히고 로컬 값으로 덮인다 — 조건 3이 {"foo": 1}에
    대해 막는 것과 같은 사고가 섹션 단위로 열린다.

    **부재 섹션은 {}로 채운다**("이력이 비어 있었다"). 문서 자체를 인식하지 못하면
    None이고, 그때는 세 섹션 모두 신뢰할 수 없는 이력이다. 이 구별이 불변식 2의
    섹션 단위 판이다.

    이 판정이 parse_base·parse_backup·load_backup의 공통 기준이다 — 세 곳이 갈리면
    "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고, 그 비대칭이 상위 버전 백업을 파괴한다.
    """
    if not isinstance(obj, dict):
        return None
    if ks.claims_newer_schema(obj.get("version"), SCHEMA_VERSION):
        return None
    present = [name for name in SECTIONS if name in obj]
    if not present:
        return None
    if any(not isinstance(obj[name], dict) for name in present):
        return None
    return {name: dict(obj[name]) if name in obj else {} for name in SECTIONS}


def parse_backup(data):
    """JSON 바이트/문자열에서 섹션 dict를 읽는다(관대한 해석). 실패는 전부 빈 세 섹션.

    **레포 파일을 읽을 때는 이 함수가 아니라 load_backup을 쓴다** — 알아볼 수 없는
    문서를 "0개"로 읽으면 그 파일을 덮어써 파괴하기 때문이다.
    """
    return _all_sections(ks.parse_backup(data, _recognized_sections))


def parse_base(data):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None (합집합 degrade).

    **여기만 평탄화하지 않는다** — None이 반환값의 의미 그 자체이기 때문이다.
    """
    return ks.parse_base(data, _recognized_sections)


def load_backup(path):
    """레포의 plugins.json을 안전하게 읽는다. 파일이 없으면 세 섹션 모두 {}.

    구문이 깨진 파일은 **세 섹션이 모두 {}인 dict**로 degrade하고(parse_backup과 같다),
    구문은 유효한데 형식을 알아볼 수 없으면 UnknownBackupSchema를 던진다.
    (PermissionError 등 그 외 OSError는 전파한다.)
    """
    return _all_sections(ks.load_backup(path, _recognized_sections))


def dump_backup(sections, path):
    """v2 형식으로 저장한다. **세 섹션 키를 항상 기록한다**(4.3).

    빈 섹션을 생략하면 플러그인 0개인 기기의 백업 결과가 {"version":2,"scope":"user"}가
    되고, 다음 백업의 인식 규칙(조건 3)에 걸려 **영구 skip**된다. 파일을 지워도 같은
    모양이 다시 만들어져 탈출구가 통하지 않는다.

    "항상 기록한다"는 **"판정한 섹션이 비면 {}로 쓴다"**는 뜻이지 **"skipped 섹션을 {}로
    덮는다"**는 뜻이 아니다 — 후자는 타 기기 항목의 전량 소실이다(7.5). 호출부가 skipped
    섹션에 레포 원래 값을 넣어 이 함수에 넘긴다.

    섹션 값이 dict가 아니면 **쓰기 전에** ValueError를 던진다. 그대로 쓰면 자기가 쓴
    파일을 자기 load_backup이 조건 4에서 인식하지 못해 그 백업이 영구히
    UnknownBackupSchema가 된다.

    ValueError를 고른 근거는 둘이다 — (a) **쓰기 전에** 던지므로 손상된 파일이 애초에
    레포에 들어가지 않는다, (b) 이것은 사용자 데이터 문제가 아니라 호출부의 계약 위반이고,
    코어의 _normalized가 키 집합 위반에 쓰는 것과 같은 신호 종류다.

    **이 예외는 호출부에서 skip으로 접힌다.** 세 스크립트의 except 튜플에 ValueError가
    이미 들어 있어서(코어의 normalize 계약 위반을 잡으려고 넣은 것이다) 여기서 던진
    ValueError도 {"status":"skipped"}가 된다 — 즉 이 버그는 traceback이 아니라 skip으로
    보고된다. 그것을 알고 받아들인 트레이드오프다: 전용 예외를 만들어 튜플에서 빼면
    어댑터 훅의 결함 하나가 백업 흐름 전체를 traceback으로 세우는데, 그것이 이 프로젝트가
    이미 고친 결함 C다. 손상 파일이 레포에 들어가지 않는 것이 우선이다.
    """
    payload = {"version": SCHEMA_VERSION, "scope": "user"}
    for name in SECTIONS:
        value = sections.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(
                "%s에 쓸 %s 섹션이 객체가 아니다(%s) — 이대로 쓰면 다음 load_backup이"
                " 이 파일을 알아보지 못한다" % (path, name, type(value).__name__))
        payload[name] = value
    ks.dump_json(payload, path)


# ------------------------------------------------------- 정규화·비밀 키 (6.1, 7.2)

def _identity(mapping):
    """enabledPlugins의 정규화 — 값을 좁히지 않는다.

    값 스키마는 union([array, boolean, object])이고 버전 제약 표현이 실재한다.
    bool로 좁히면 데이터를 파괴한다(G5). deepcopy로 돌려주는 것은 호출부가 결과를
    다듬어도 원본 설정이 오염되지 않게 하기 위해서다.
    """
    return copy.deepcopy(dict(mapping))


def _drop_auto_update(marketplaces):
    """extraKnownMarketplaces의 정규화 — autoUpdate 필드를 제거한다 (7.2).

    값에는 실재하지만 `marketplace add`에 이를 설정하는 옵션이 없다(실측). 비교에 넣으면
    한 기기가 켜고 다른 기기가 껐을 때 **수렴시킬 CLI 수단이 없어** 영구 보고된다.
    **필드 제거이지 키 제거가 아니므로** 값 층위에서 안전하다 — 코어의 _normalized 가드를
    통과한다.
    """
    out = {}
    for name, value in marketplaces.items():
        if not isinstance(value, dict):
            out[name] = copy.deepcopy(value)
            continue
        new = copy.deepcopy(value)
        new.pop("autoUpdate", None)
        out[name] = new
    return out


def _redact_configs(configs):
    """pluginConfigs의 정규화 — options의 **값만** 마스킹하고 키 이름은 보존한다 (6.1).

    키 이름을 보존해야 복원 시 레포 파일만 보고 "어떤 값을 물어야 하는지"를 알 수 있다.
    options가 객체가 아니면 필드 전체를 문자열 SENTINEL로 바꾼다 — 타입이 dict에서
    str로 바뀌므로 secret_keys는 그 항목에 대해 키를 하나도 묻지 않는다.
    이미 마스킹된 입력에 다시 적용해도 결과가 같다(멱등) — 로컬(평문)과 레포(마스킹됨)를
    수렴시키는 전제다.
    """
    out = {}
    for plugin_id, cfg in configs.items():
        if not isinstance(cfg, dict):
            out[plugin_id] = copy.deepcopy(cfg)
            continue
        new = copy.deepcopy(cfg)
        if "options" in new:
            options = new["options"]
            new["options"] = ({k: SENTINEL for k in options}
                              if isinstance(options, dict) else SENTINEL)
        out[plugin_id] = new
    return out


SECTION_NORMALIZE = {
    "enabledPlugins": _identity,
    "extraKnownMarketplaces": _drop_auto_update,
    "pluginConfigs": _redact_configs,
}


def _config_secret_keys(cfg):
    """복원 시 사용자에게 값을 물어야 하는 option 키 이름 목록 (6.1·6.2).

    비어 있으면 물어볼 것이 없다 — add 버킷으로 간다.
    """
    if not isinstance(cfg, dict):
        return []
    options = cfg.get("options")
    return sorted(options) if isinstance(options, dict) else []


def _no_secrets(value):
    """enabledPlugins·extraKnownMarketplaces에는 되물을 비밀이 없다.

    여기서 비어 있지 않은 목록을 돌려주면 정상 항목이 needs_secret 버킷으로 새어 나가
    설치되지 않는다.
    """
    return []


SECTION_SECRET_KEYS = {
    "enabledPlugins": _no_secrets,
    "extraKnownMarketplaces": _no_secrets,
    "pluginConfigs": _config_secret_keys,
}


# ------------------------------------------------------------------ 보류 (7.3)

def value_fingerprint(value):
    """정규화된 레포 값의 sha256 지문. plugins-held.json에 저장되는 형태다 (6.4).

    코어와 **같은 정규 직렬화**(ks.fingerprint)를 쓴다 — 여기서 옵션을 다시 적으면
    디스크 표현과 지문이 어긋난다.
    """
    return hashlib.sha256(ks.fingerprint(value).encode("utf-8")).hexdigest()


def marketplace_of(plugin_id):
    """'<plugin>@<marketplace>'의 마켓플레이스 부분. 그 형태가 아니면 None."""
    if not isinstance(plugin_id, str) or plugin_id.count("@") != 1:
        return None
    name, _, marketplace = plugin_id.partition("@")
    return marketplace if name and marketplace else None


def _source_kind(value):
    """마켓플레이스 값의 source.source. 알아볼 수 없으면 None."""
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    if not isinstance(source, dict):
        return None
    kind = source.get("source")
    return kind if isinstance(kind, str) else None


def directory_marketplaces(local_marketplaces, repo_marketplaces):
    """로컬 디렉토리에서 등록한 마켓플레이스 이름 집합 (H2).

    **양쪽을 다 본다.** 로컬 쪽은 생산 측 방어(기기 A가 애초에 올리지 않는다)이고,
    레포 쪽은 이미 실린 옛 항목의 소비 측 방어다(기기 B에는 등록할 소스가 없다).
    """
    names = set()
    for mapping in (local_marketplaces, repo_marketplaces):
        for name, value in mapping.items():
            if _source_kind(value) == "directory":
                names.add(name)
    return frozenset(names)


def _make_hold(section, *, auto_ids, directory_names, held_configs, released):
    """섹션 하나의 hold 훅을 만든다. 코어가 (local, repo)로 부른다.

    **좌우 비대칭이다** — H3·H4는 레포 값을 보고, H1·H2는 로컬 쪽 사실(auto 플래그,
    마켓플레이스 출처)을 본다. 인자 순서가 뒤집히면 예외도 빈 결과도 나지 않고
    판정이 조용히 반대로 선다.

    **입력은 이미 정규화돼 있다** — H4의 지문이 마스킹된 레포 값으로 계산되는 근거다.
    """
    def hold(local, repo):
        value, action = set(), set()
        for key in set(local) | set(repo):
            if section != "extraKnownMarketplaces" and key in auto_ids:      # H1
                value.add(key)
                action.add(key)
            owner = key if section == "extraKnownMarketplaces" else marketplace_of(key)
            if owner is not None and owner in directory_names:               # H2
                value.add(key)
                action.add(key)
            if (section == "enabledPlugins" and key in repo                  # H3
                    and not isinstance(repo[key], bool) and key not in released):
                value.add(key)                    # 행동 보류가 아니다 — 설치한다
            if (section == "pluginConfigs" and key in repo                   # H4
                    and held_configs.get(key) == value_fingerprint(repo[key])):
                value.add(key)
                action.add(key)
        return {"value": value, "action": action}
    return hold


HELD_KINDS = {
    "enabledPlugins": ("auto", "local_marketplace", "extended_value"),
    "extraKnownMarketplaces": ("local_marketplace",),
    "pluginConfigs": ("auto", "local_marketplace", "declined"),
}


def held_kinds(section, keys, *, auto_ids, directory_names, held_configs, repo_norm):
    """보류 키를 종류별로 가른다. status·backup이 종류별 문구로 보고하기 위해서다.

    한 키가 여러 종류에 걸칠 수 있으므로 첫 종류에서 멈추지 않는다.
    **어느 종류에도 걸리지 않는 키가 있으면 ValueError다** — 조용히 빠뜨리면 그 키가
    사용자 보고에서 통째로 사라진다(불변식 6). 스크립트가 그 섹션을 skipped로 접는다.
    """
    kinds = {name: [] for name in HELD_KINDS[section]}
    for key in sorted(keys):
        owner = key if section == "extraKnownMarketplaces" else marketplace_of(key)
        if "auto" in kinds and key in auto_ids:
            kinds["auto"].append(key)
        if owner is not None and owner in directory_names:
            kinds["local_marketplace"].append(key)
        if ("extended_value" in kinds and key in repo_norm
                and not isinstance(repo_norm[key], bool)):
            kinds["extended_value"].append(key)
        if ("declined" in kinds and key in repo_norm
                and held_configs.get(key) == value_fingerprint(repo_norm[key])):
            kinds["declined"].append(key)
    covered = {key for names in kinds.values() for key in names}
    missing = sorted(set(keys) - covered)
    if missing:
        raise ValueError("%s의 보류 사유를 분류할 수 없다: %s" % (section, missing))
    return kinds


def held_context(local, repo, *, auto_ids, held_state):
    """hold 훅과 held_kinds가 **같은 입력에서 같은 값**을 보게 하는 컨텍스트.

    두 곳이 각자 계산하면 "보류로 판정했는데 보고에서는 종류를 못 찾는" 상태가 생기고,
    held_kinds가 그것을 ValueError로 막으므로 섹션이 통째로 skipped가 된다.
    호출부(스크립트)는 이 함수를 한 번 불러 hold와 held_kinds 양쪽에 같은 값을 넘긴다.

    키 이름은 _make_hold와 held_kinds의 **키워드 인자 이름과 같다** — 양쪽 다
    `**context`로 받으므로 이름이 어긋나면 조용한 오판정이 아니라 TypeError로 즉시 드러난다.
    released를 여기 담지 않는 것은 그것이 H3 한 종류의 탈출구이고 held_kinds가 받지
    않기 때문이다 — 두 곳이 공유하지 않는 값을 공유 컨텍스트에 넣으면 위 대응이 깨진다.
    """
    return {
        "auto_ids": auto_ids,
        "directory_names": directory_marketplaces(
            local.get("extraKnownMarketplaces", {}),
            repo.get("extraKnownMarketplaces", {})),
        "held_configs": dict(held_state.get("pluginConfigs", {})),
    }


# ------------------------------------------------- 복원 가능성 (8장)·정합성 (7.6)

# extraKnownMarketplaces에 없어도 "아는 이름"으로 치는 다섯. **이 파일이 정하는 것은
# 목록과 그 두 쓰임뿐이다** — _plugin_restorable(레포에 소스가 없어도 복원 가능)과
# orphaned(고아가 아니다). 이 다섯을 **등록 명령에서 빼는 처리는 여기 없다**; 그것은
# restore 스크립트의 몫이고 아직 존재하지 않는다.
# claude-plugins-official은 이미 자동 설치되어 등록이 무의미하고, 나머지 넷은
# 마켓플레이스가 아닌 **의사 출처**라 등록이 실패한다.
ALWAYS_KNOWN = frozenset({
    "inline", "skills-dir", "synced", "builtin", "claude-plugins-official"})

# 그 넷. 소속 플러그인은 복원할 수 없다 — claude-plugins-official만 설치가 가능하다.
PSEUDO_SOURCES = ALWAYS_KNOWN - {"claude-plugins-official"}

# 제3자가 쓸 수 없는 예약 이름. **이 파일은 목록만 정하고 어디서도 쓰지 않는다** —
# restorable도 orphaned도 이 집합을 보지 않는다. 미리 거르지 않는 것이 8.3이고(정당한
# 소유자일 수 있다), 등록을 시도해 실패했을 때 "예약된 이름이라 거부되었다"로 갈래를
# 구별해 보고하는 것은 **restore 스크립트가 할 일이다**(10.2). 그 소비자가 생기기
# 전까지 이 상수의 사용처는 열거형 대조 테스트뿐이다.
# always-known 판정이 우선한다 — claude-plugins-official은 ALWAYS_KNOWN에서 먼저
# 걸러지므로 이 갈래에 도달하지 않는다.
RESERVED_MARKETPLACE_NAMES = frozenset({
    "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
    "anthropic-marketplace", "anthropic-plugins", "agent-skills",
    "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins",
    "claude-for-legal", "claude-for-financial-services",
    "financial-services-plugins", "first-party-plugins",
    "claude-community", "claude-plugins-community", "healthcare",
})

# 출처 종류별로 `marketplace add`에 넘길 문자열을 어느 필드에서 뽑는가 (8.6).
# github은 실측된 형태다. url·git의 필드 이름은 측정되지 않았으므로 후보를 순서대로
# 훑고, 문자열을 하나도 찾지 못하면 **인자를 만들 수 없음 = unrestorable**로 접는다 —
# 짐작해서 잘못된 인자를 넘기면 CLI가 모호한 문구로 실패해 사용자가 원인을 못 찾는다.
# git의 후보가 **둘인 것 자체가 장치다**(어느 쪽이 옳은 필드인지 모르므로 둘 다 시도한다).
# 하나로 줄이면 나머지 필드만 가진 값이 조용히 unrestorable이 된다.
_SOURCE_ARG_FIELDS = {"github": ("repo",), "url": ("url",), "git": ("url", "repo")}


def marketplace_arg(value):
    """`claude plugin marketplace add`에 넘길 문자열. 만들 수 없으면 None (8.6).

    directory 출처는 여기 오지 않는다 — H2로 보류되기 때문이다. 와도 None이 된다.

    **비어 있지 않은 문자열만 인자로 인정한다.** ""나 문자열이 아닌 값을 돌려주면 그것이
    그대로 argv에 실려, 사용자는 자기 설정의 어느 필드가 비었는지 대신 CLI의 모호한
    문구를 보게 된다. 여기서 None으로 접으면 10.2의 갈래별 사유가 그 자리를 대신한다.
    """
    kind = _source_kind(value)
    # kind가 None이 아니면 _source_kind가 value·value["source"] 둘 다 dict임을 이미 보장한다.
    # kind가 None이면 아래 루프가 한 번도 돌지 않으므로 source가 None인 채로 쓰이지 않는다.
    source = value.get("source") if isinstance(value, dict) else None
    for field in _SOURCE_ARG_FIELDS.get(kind, ()):
        candidate = source.get(field)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _plugin_restorable(key, repo_marketplaces):
    """플러그인 id를 이 도구가 재현할 수 있는가 (8.1).

    **시도하면 반드시 실패하는 것만 거른다**(10장). 과하게 좁히면 정당한 항목이
    unrestorable로 빠지는데, 사용자에게는 그것을 되돌릴 수단이 없다.
    """
    marketplace = marketplace_of(key)
    if marketplace is None or marketplace in PSEUDO_SOURCES:
        return False
    return marketplace in ALWAYS_KNOWN or marketplace in repo_marketplaces


def unrestorable_reason(section, key, value, repo):
    """복원 불가의 **갈래**를 문장으로 (10.2). 복원 가능하면 None.

    "복원 불가"만 말하면 사용자가 무엇을 해야 하는지 알 수 없다 — 종류별 사유가
    "의사 출처라 원래 불가능하다"와 "레포에 소스가 없으니 백업한 기기에서 올려라"를 가른다.

    갈래의 순서와 조건은 _plugin_restorable·marketplace_arg와 **같아야 한다.** 갈리면
    양쪽 다 무증상이다 — 복원 가능한데 사유가 붙거나, 복원 불가인데 사유가 None이 되어
    그 항목이 보고에서 이유 없이 사라진다.
    """
    if section == "extraKnownMarketplaces":
        if marketplace_arg(value) is not None:
            return None
        # "인자를 만들 수 없다"의 세 갈래는 **사용자가 할 일이 서로 다르다.** 종류만
        # 지목하면 (a)에서 멀쩡한 종류를 범인으로 지목하고, 종류를 그대로 끼워 넣으면
        # (c)에서 파이썬 값(None)이 사용자 눈앞에 나간다.
        kind = _source_kind(value)
        if kind is None:                                                    # (c)
            return "마켓플레이스 값에서 출처 종류(source.source)를 읽을 수 없어 등록 인자를 만들 수 없다"
        fields = _SOURCE_ARG_FIELDS.get(kind)
        if not fields:                                                      # (b)
            return "'%s' 출처로는 등록 인자를 만들 수 없다" % kind
        return ("'%s' 출처인데 등록 인자로 쓸 필드가 비어 있다: %s"        # (a)
                % (kind, "·".join(fields)))
    marketplace = marketplace_of(key)
    if marketplace is None:
        return "플러그인 id 형태(<plugin>@<marketplace>)가 아니다"
    if marketplace in PSEUDO_SOURCES:
        return "'%s' 출처는 마켓플레이스가 아닌 의사 출처다" % marketplace
    if marketplace not in ALWAYS_KNOWN and marketplace not in repo.get(
            "extraKnownMarketplaces", {}):
        return "레포에 '%s' 마켓플레이스의 소스가 없다" % marketplace
    return None


def orphaned(merged_plugins, merged_marketplaces):
    """마켓플레이스가 결과 문서에 없는 플러그인 id (7.6). **차단하지 않는다.**

    런타임은 조용히 건너뛰고("Skipping orphaned enabledPlugins entry"), 새 기기의
    restore는 "플러그인이 없다"와 **똑같은 문구**로 실패해 원인을 알 수 없다.
    섹션 간에 게이트를 두지 않는 대신 이 검사로 보고만 한다.

    **None을 ""로 접지 않는다.** marketplace_of는 형태 위반에 None을 돌려줄 뿐 ""를
    돌려주는 일이 없으므로(`if name and marketplace`) 그 접기는 죽은 정규화이면서,
    이름이 빈 문자열인 마켓플레이스 항목 하나가 known에 들어가는 순간 **모든 형태 위반
    id가 "알려진 마켓플레이스 소속"으로 판정돼 보고에서 통째로 사라진다.**
    _recognized_sections는 섹션 키의 형태를 검사하지 않으므로 그런 문서는 정상 인식된다.
    """
    known = set(merged_marketplaces) | ALWAYS_KNOWN
    return sorted(plugin_id for plugin_id in merged_plugins
                  if marketplace_of(plugin_id) not in known)


def value_command(local_value, repo_value):
    """레포 값에 맞추려면 실행해야 할 CLI 명령. 필요 없으면 None (9.3.1의 3단계).

    enable/disable은 **멱등이 아니다** — 이미 그 상태면 exit 1이다(실측). 현재 상태와
    같은데 부르면 거짓 실패를 양산한다.

    레포 값이 불리언이 아니면 None이다 — 배열·객체를 쓸 CLI가 없다(H3의 값은 밀지
    않는다). **로컬의 부재는 false가 아니다** — 매니페스트 기본값(defaultEnabled)에
    위임하는 상태이므로 의미가 반대다. 따라서 부재는 "명령이 필요하다"로 다룬다.
    """
    if not isinstance(repo_value, bool):
        return None
    if isinstance(local_value, bool) and local_value == repo_value:
        return None
    return "enable" if repo_value else "disable"


def build_hooks(local, repo, *, auto_ids, held_state, _context=None):
    """섹션별 훅 묶음 {섹션: {"normalize", "hold", "restorable", "secret_keys"}}.

    **레포를 읽은 뒤에 불러야 한다**(spec 9.1.1의 4단계 > 2단계). 여기서 레포에 의존하는
    것은 **훅을 만드는 시점의 레포를 클로저로 닫는 셋**이다 —
      H2의 레포 쪽 방어  held_context의 directory_marketplaces가 레포에 이미 실린
                         directory 출처를 본다. 비면 기기 B에 등록할 소스가 없는 항목이
                         보류되지 않고 케이스 3(삭제)으로 레포에서 지워진다.
      restorable         "레포에 그 마켓플레이스의 소스가 있는가"(8.1)를 repo_marketplaces로
                         판정한다. 비면 그 조건이 항상 거짓이 되어 판정이 무너진다.
      reason             unrestorable_reason에 넘길 같은 repo를 닫는다. 비면 "레포에 소스가
                         없다"를 볼 수 없어 **전부 복원 가능으로 판정**된다.

    **H1·H3·H4는 이 셋에 들지 않는다.** 코어가 hold(local, repo)를 부를 때 레포를 넘기므로
    순서를 뒤집어도 그대로 계산된다. 그래서 이 뒤집기가 조용하다 — 보류 네 종류 중 셋이
    멀쩡히 동작하고 H2 하나만 무증상으로 죽으므로, 순서를 지키는 것 말고는 드러날 자리가
    없다. (이 문단의 앞 판은 근거를 H3·H4로 적었는데 사실이 아니었다. 그 문장을 믿고
    순서를 바꾸면 정확히 위의 셋이 죽는다.)

    코어가 보는 계약은 normalize(mapping)·hold(local, repo)·restorable(key, value)·
    secret_keys(value) 넷뿐이고, 그 서명 밖의 입력(auto 집합, **다른 섹션**인
    extraKnownMarketplaces의 출처와 그 등록 가능 여부, 보류 파일)은 전부 여기서 닫는다.

    **넷이 다 섹션마다 다른 함수인 것은 아니다.** normalize·hold만 섹션별 함수다.
    restorable은 갈래가 둘뿐이고(마켓플레이스 / 플러그인) enabledPlugins와
    pluginConfigs가 **같은 규칙**을 쓴다 — 설정을 채우는 명령이 install --config라서다.
    secret_keys는 _no_secrets 하나를 두 섹션이 **같은 객체로 공유**한다. reason은
    섹션을 인자로 받는 함수 하나다.

    보류 판정의 입력은 held_context가 만든다 — 호출부가 그 함수를 한 번 더 불러
    held_kinds에 같은 값을 넘기면 훅과 보고가 갈릴 수 없다.

    **이 hold의 value 축은 ks.next_base(value_held=)에 반드시 넘겨야 한다** — 안 넘기면
    보류 키가 base에 얼어붙어 보류가 풀리는 순간 케이스 3(삭제)이 난다. 그 조립은
    value_held_for가 한다; 손으로 다시 짜지 말 것(정규화·인자 순서 함정이 둘 다 조용하다).

    **다섯 번째 키 reason은 코어가 보지 않는다** — 계약은 위의 넷뿐이고, reason은 보고
    층이 쓴다. 그런데도 여기 얹는 이유는 restorable과 **같은 repo를 닫기 위해서다.**
    unrestorable_reason은 문서 전체를 받는데 restorable(key, value)는 섹션 층위라, 한
    스크립트 안에서 층위가 섞여 섹션 매핑을 문서 자리에 넘기기 쉽다 — 그러면 복원
    가능한 항목에 "레포에 소스가 없다"가 붙는다(실측). held_context가 hold와 held_kinds에
    쓴 처방과 같다: 한 번 닫아 양쪽이 같은 값을 보게 한다.

    restorable도 자기 섹션 밖을 본다 — 8.1의 판정이 **레포의** extraKnownMarketplaces를
    필요로 한다. 로컬 쪽을 보면 안 되는 이유는 방향이다: 복원은 레포 문서를 이 기기에
    재현하는 일이고, 등록할 소스가 실려 있는 곳은 레포다. 로컬을 보면 아직 이 기기에
    없는 마켓플레이스의 플러그인이 전부 unrestorable로 접혀 **첫 복원이 통째로 빈다.**
    """
    # _context는 hooks_and_context 전용 내부 통로다 — 외부 호출부가 임의의 컨텍스트를
    # 끼워 넣으라는 자리가 아니라, 훅이 닫는 세 값과 보고에 넘길 컨텍스트의 값을 **같은
    # 객체**로 만들기 위한 것이다. 그래서 밑줄로 사적 표시를 하고 기본값을 둔다
    # (기존 호출부는 안 넘기므로 서명 변경이 호환된다).
    #
    # **_context를 넘기면 local·auto_ids는 이 함수에서 한 번도 쓰이지 않는다** — 둘의
    # 유일한 사용처가 바로 아래 fallback의 held_context 호출이다. 반면 held_state는
    # 계속 산다: 다음 줄의 released가 그것을 읽는다. 그래서 _context와 auto_ids가 서로
    # 다른 입력에서 왔으면 훅의 보류 판정(_context 안의 auto_ids)과 release 탈출구
    # (held_state)가 다른 세계를 보게 되는데, 여기에 그것을 잡는 장치는 없다.
    # 그러므로 _context는 **반드시 같은 입력에서 만든 것**이어야 하고, 그 일관성을
    # 보장하는 유일한 자리가 hooks_and_context다 — 밑줄 접두사가 뜻하는 바가 이것이다.
    context = _context if _context is not None else held_context(
        local, repo, auto_ids=auto_ids, held_state=held_state)
    released = frozenset(held_state.get("release", {}).get("enabledPlugins", []))
    repo_marketplaces = frozenset(repo.get("extraKnownMarketplaces", {}))

    def restorable_for(section):
        if section == "extraKnownMarketplaces":
            return lambda key, value: marketplace_arg(value) is not None
        return lambda key, value: _plugin_restorable(key, repo_marketplaces)

    return {
        section: {
            "normalize": SECTION_NORMALIZE[section],
            "hold": _make_hold(section, released=released, **context),
            "restorable": restorable_for(section),
            "secret_keys": SECTION_SECRET_KEYS[section],
            "reason": (lambda key, value, s=section:
                       unrestorable_reason(s, key, value, repo)),
        }
        for section in SECTIONS
    }


def hooks_and_context(local, repo, *, auto_ids, held_state):
    """훅 묶음과 held_kinds용 컨텍스트를 **한 번의 입력으로** 함께 만든다.

    스크립트가 build_hooks와 held_context를 따로 부르면 두 입력이 같다는 보장이
    호출부의 규율뿐이다. 어긋나면 hold가 보류한 키를 held_kinds가 분류하지 못해
    ValueError가 나고 그 섹션이 통째로 skipped가 된다 — 무엇도 잘못되지 않았는데
    타 기기 항목이 pass-through로만 남는다. 세 스크립트가 같은 두 줄을 각자 쓰는
    대신 이것을 부르면 (local, repo)를 한 번만 받으므로 갈릴 자리가 없다.

    컨텍스트는 **한 번만** 만들어 build_hooks에 _context로 건네고 그대로 돌려준다 —
    훅이 닫는 세 값(auto_ids·directory_names·held_configs)이 여기서 돌려주는 dict의
    값과 **같은 객체**다. 동일성이 객체 identity로 성립하므로, held_context가 언젠가
    순수하지 않게 되어도(경로를 읽거나 시각을 보거나 캐시를 타도) 두 값이 갈릴 자리가
    없다. 두 번 불러 "입력이 같으니 결과도 같다"에 기대면 그 등식을 지탱하는 것이
    구조가 아니라 함수의 성질뿐이다.

    **닫히는 것은 세 값이지 dict가 아니다.** build_hooks가
    `_make_hold(section, released=released, **context)`로 **풀어서** 넘기므로 훅의
    자유변수는 ('auto_ids', 'directory_names', 'held_configs', 'released', 'section')
    이고 context dict는 어디에도 닫히지 않는다. 그래서 돌려받은 dict를 손대면 비대칭이
    나온다 — `context["auto_ids"] = ...` 같은 **재바인딩은 훅에 반영되지 않고**,
    `context["held_configs"]`의 **제자리 변형은 반영된다**(값이 같은 객체라서).
    """
    context = held_context(local, repo, auto_ids=auto_ids, held_state=held_state)
    return (build_hooks(local, repo, auto_ids=auto_ids, held_state=held_state,
                        _context=context),
            context)


def value_held_for(section, hooks, local, repo):
    """next_base에 넘길 **값 보류** 집합. 조립의 계약을 여기서 한 번만 지킨다.

    `ks.next_base(..., value_held=frozenset())`는 기본값이 빈 집합이라 안 넘기면 예외도
    경고도 없이 "보류 없음"으로 계산된다. 그러면 보류 키가 base에 얼어붙고, **보류가
    풀리는 나중 시점에 케이스 3(삭제)** 으로 증상이 나온다 — 원인에서 멀리 떨어진 곳에서.
    plugin_config는 보류가 있는 첫 어댑터이므로(mcp_config.next_base의 경고가 지목하는
    그 어댑터다) restore 경로가 반드시 이 값을 넘겨야 한다.

    조립에 함정이 둘 더 있고 **둘 다 조용하다** —
      1. hold는 **정규화된** 입력을 받는 것이 계약이다. H4의 지문은 마스킹된 레포 값으로
         계산되므로, 평문을 그대로 넘기면 지문이 어긋나 보류가 통째로 비어 버린다.
      2. (local, repo) 순서가 뒤집히면 예외도 빈 결과도 나지 않고 판정이 반대로 선다.
    앞으로 네 스크립트가 각자 조립하게 되므로 한 곳만 틀려도 무증상이다. 한 번으로 만든다.

    **행동 보류(action)가 아니라 값 보류(value)를 쓴다.** base는 "이 기기가 마지막으로
    동의한 값"이고, 행동 보류는 "설치를 안 한다"일 뿐 값에 동의하지 않는다는 뜻이 아니다.
    """
    normalize = hooks[section]["normalize"]
    held = hooks[section]["hold"](normalize(local), normalize(repo))
    return frozenset(held["value"])
