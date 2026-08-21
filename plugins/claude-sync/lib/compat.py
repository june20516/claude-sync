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


def _load_json(path):
    """JSON 파일을 읽는다. 못 읽거나 깨졌으면 None.

    metadata도 plugin.json도 "없음"과 "깨짐"의 처리가 같으므로 한 함수로 둔다.
    PermissionError 등 다른 OSError도 None으로 degrade한다 — 판정을 못 한다고
    백업을 막으면, 그 파일을 고치는 다음 백업까지 막혀 데드락이 된다.
    """
    try:
        with open(path, "rb") as f:
            return json.loads(f.read())
    except (OSError, ValueError):
        return None


def read_plugin_version(plugin_json_path):
    """plugin.json의 version 문자열. 읽지 못하면 None(예외 아님).

    '자기 버전을 모른다'는 정상적으로 표현 가능한 상태여야 한다. 예외로 만들면
    호출부마다 try가 생기고 그 처리가 갈린다.
    """
    obj = _load_json(plugin_json_path)
    if not isinstance(obj, dict):
        return None
    version = obj.get("version")
    return version if isinstance(version, str) else None


def load_metadata(path):
    """sync-metadata.json을 읽는다. 없거나 깨졌거나 dict가 아니면 None.

    깨진 metadata를 차단 근거로 삼으면 데드락이 된다 — 그 파일을 정상으로 되돌리는 것이
    다음 백업인데 그 백업이 막힌다. load_backup이 깨진 파일을 {}로 degrade하는 것과 같은
    이유다("레포 파일 하나가 깨졌다고 백업 전체를 막지 않는다").
    """
    obj = _load_json(path)
    return obj if isinstance(obj, dict) else None
