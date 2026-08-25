#!/usr/bin/env python3
"""claude-sync의 플러그인 동기화 어댑터.

데이터 소스는 두 파일이고 역할이 다르다(spec 3장) —
  ~/.claude/settings.json                    세 섹션 값의 **유일한** 원천
  ~/.claude/plugins/installed_plugins.json   각 항목의 auto 플래그 **하나만**
installed_plugins.json을 값의 원천으로 삼지 않는 이유는 그것이 settings.json에서
파생되기 때문이다. `claude plugin list --json`을 쓰지 않는 이유는 "키 부재"와 false를
구별하지 못하기 때문이다.

키 단위 3-way 판정·인식은 값 무관 코어(keyed_sync)에 있다. 이 모듈은 플러그인의 도메인
지식만 얹는다 — 인식(4.4)·정규화(7.2)·보류(7.3)·복원 가능성(8장)·비밀 키(6.1).

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
import json
import os

import keyed_sync as ks

SCHEMA_VERSION = 2
BACKUP_RELPATH = "plugins.json"
SECTIONS = ("enabledPlugins", "extraKnownMarketplaces", "pluginConfigs")

# 7.2 정규화(pluginConfigs 비밀 마스킹)가 쓴다 — Task 5에서 사용된다. 지금은 값만 선언한다.
SENTINEL = "<REDACTED>"

# 별칭은 같은 뜻이다. 둘 다 있으면 앞의 것을 채택한다 — CLI와 같은 규칙이고,
# 순서가 곧 우선순위다. 이 튜플의 순서를 바꾸면 규칙이 뒤집힌다.
MARKETPLACE_ALIASES = ("extraKnownMarketplaces", "additionalMarketplaces")

DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")
DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
DEFAULT_HELD = os.path.expanduser("~/.claude/.sync-state/plugins-held.json")

HELD_SCHEMA_VERSION = 1
INSTALLED_SCHEMA_VERSION = 2      # installed_plugins.json 자체가 달고 다니는 스키마 버전
EMPTY_HELD = {"pluginConfigs": {}, "release": {"enabledPlugins": []}}

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
            "%s의 %s가 객체가 아님(%s) — 플러그인 백업을 통째로 건너뛴다"
            % (path, key, type(value).__name__))
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
        raise LocalConfigUnavailable(
            "%s 없음 — 플러그인 백업을 통째로 건너뛴다" % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LocalConfigUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise LocalConfigUnavailable("%s 최상위가 객체가 아님" % path)
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
      4. version이 INSTALLED_SCHEMA_VERSION보다 높다고 주장함
      5. plugins 키 부재
      6. plugins가 객체가 아님
      7. plugins[<id>]가 배열이 아님
      8. plugins[<id>]의 원소가 객체가 아님

    5·8을 빈 집합으로 접지 않는 이유가 이 함수의 존재 이유다. auto 판정이 거짓으로
    비면 auto 항목이 hold에 들어가지 못하고 그대로 레포에 실려 승격되며, 타 기기의
    restore가 그것을 설치한다 — **되돌릴 수 없다**(N6). 반대로 과하게 raise하면 두
    섹션이 skip될 뿐이고 레포는 그대로다. 비대칭이 명확하므로 전부 raise 쪽으로 조인다.

    PermissionError 등 그 외 OSError는 전파한다(감싸지 않는다).
    """
    path = DEFAULT_INSTALLED if installed_path is None else installed_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise AutoFlagsUnavailable(
            "%s 없음 — auto 판정 불가로 enabledPlugins·pluginConfigs를 건너뛴다"
            % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AutoFlagsUnavailable(
            "%s 파싱 실패: %s — auto 판정 불가로 enabledPlugins·pluginConfigs를 건너뛴다"
            % (path, e)) from e
    if not isinstance(data, dict):
        raise AutoFlagsUnavailable("%s 최상위가 객체가 아님" % path)
    if ks.claims_newer_schema(data.get("version"), INSTALLED_SCHEMA_VERSION):
        raise AutoFlagsUnavailable(
            "%s가 상위 버전을 주장한다(version=%r) — auto 판정을 할 수 없다"
            % (path, data.get("version")))
    if "plugins" not in data:
        raise AutoFlagsUnavailable(
            "%s에 plugins 키가 없다 — auto 판정을 할 수 없다" % path)
    plugins = data["plugins"]
    if not isinstance(plugins, dict):
        raise AutoFlagsUnavailable(
            "%s의 plugins가 객체가 아님(%s)" % (path, type(plugins).__name__))
    out = set()
    for plugin_id, entries in plugins.items():
        if not isinstance(entries, list):
            raise AutoFlagsUnavailable(
                "%s의 plugins[%s]가 배열이 아님" % (path, plugin_id))
        for entry in entries:
            if not isinstance(entry, dict):
                raise AutoFlagsUnavailable(
                    "%s의 plugins[%s] 원소가 객체가 아님 — 그 항목의 auto를 읽을 수 없다"
                    % (path, plugin_id))
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
            "%s 파싱 실패: %s — pluginConfigs를 건너뛴다" % (path, e)) from e
    if not isinstance(data, dict):
        raise HeldStateUnavailable("%s 최상위가 객체가 아님" % path)
    if ks.claims_newer_schema(data.get("version"), HELD_SCHEMA_VERSION):
        raise HeldStateUnavailable("%s가 상위 버전을 주장한다" % path)
    configs = data.get("pluginConfigs", {})
    if not isinstance(configs, dict) or not all(
            isinstance(v, str) for v in configs.values()):
        raise HeldStateUnavailable(
            "%s의 pluginConfigs가 {id: 지문} 형태가 아님 — pluginConfigs를 건너뛴다" % path)
    release = data.get("release", {})
    if not isinstance(release, dict):
        raise HeldStateUnavailable("%s의 release가 객체가 아님" % path)
    released = release.get("enabledPlugins", [])
    if not isinstance(released, list) or not all(isinstance(v, str) for v in released):
        raise HeldStateUnavailable("%s의 release.enabledPlugins가 문자열 배열이 아님" % path)
    return {"pluginConfigs": dict(configs),
            "release": {"enabledPlugins": list(released)}}


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

    구문이 깨진 파일은 {}로 degrade하고, 구문은 유효한데 형식을 알아볼 수 없으면
    UnknownBackupSchema를 던진다. (PermissionError 등 그 외 OSError는 전파한다.)
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
    UnknownBackupSchema가 된다. 이것은 사용자 데이터 문제가 아니라 호출부의 계약 위반이므로
    읽기 실패 예외(LocalConfigUnavailable 등)로 던지지 않는다 — 그렇게 던지면 호출부의
    except 튜플에 잡혀 버그가 "정상적인 skip"으로 위장된다. 코어의 _normalized가 키 집합
    위반에 ValueError를 쓰는 것과 같은 이유다.
    """
    payload = {"version": SCHEMA_VERSION, "scope": "user"}
    for name in SECTIONS:
        value = sections.get(name, {})
        if not isinstance(value, dict):
            raise ValueError(
                "%s 섹션이 객체가 아니다(%s) — 이대로 쓰면 다음 load_backup이 이 파일을"
                " 알아보지 못한다" % (name, type(value).__name__))
        payload[name] = value
    ks.dump_json(payload, path)
