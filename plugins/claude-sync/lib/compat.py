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
        "needs_upgrade": False,
        "reason": _block_reason(meta, raw_min, my_version),
        "my_version": my_version,
        "repo_min_reader": raw_min if isinstance(raw_min, str) else None,
        "repo_written_by": raw_written if isinstance(raw_written, str) else None,
        "message": "",
    }
    if verdict["reason"] is not None:
        verdict["needs_upgrade"] = True
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
