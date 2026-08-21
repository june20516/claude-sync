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

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)")


def parse_version(text):
    """'3.10.0' -> (3, 10, 0). 파싱 못 하면 None.

    문자열 비교를 쓰면 "3.10.0" > "3.9.0"이 거짓이 된다. 반드시 정수 튜플로 비교한다.
    선행 v('v3.0.0')와 접미사('3.0.0-rc1')는 허용하고 코어 3자리만 읽는다.
    'unknown'은 None이다 — claude plugin list가 실제로 내는 값이다.
    """
    if not isinstance(text, str):
        return None
    m = _VERSION_RE.match(text)
    if m is None:
        return None
    return tuple(int(g) for g in m.groups())
