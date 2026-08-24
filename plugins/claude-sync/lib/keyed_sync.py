#!/usr/bin/env python3
"""claude-sync의 값 무관 키 단위 3-way 동기화 코어.

MCP 서버와 플러그인이 같은 판정표·인식 계층·예외 클래스를 공유한다.
도메인 지식(마스킹·판정 보류·복원 가능성)은 전부 훅으로 주입된다 — 이 모듈은 값을 모른다.

이 모듈을 복사하지 말 것. 과거 Critical 세 건이 전부 상태 기계에서 나왔고,
복사하면 위험도 복사된다.
"""
import copy
import json

BROKEN = object()   # JSON 구문 오류 센티널. None·0·false와 구별해야 한다


class LocalConfigUnavailable(Exception):
    """로컬 설정을 읽지 못했다.

    "항목 0개"와 반드시 구별해야 한다. 이 예외가 발생하면 삭제 판정을 해서는 안 된다.
    어댑터가 re-export하므로 `except adapter.LocalConfigUnavailable`이 이 클래스를 잡는다.
    """


class UnknownBackupSchema(Exception):
    """레포의 백업 파일이 이 버전이 아는 형식이 아니다.

    상위 버전이 쓴 문서일 수 있으므로 "항목 0개"로 읽어서는 안 된다. 그렇게 읽으면
    merge가 레포를 빈 것으로 보고 이 기기의 로컬만 남긴 결과를 덮어써 상위 버전의
    백업을 파괴한다.
    """


def claims_newer_schema(version, schema_version):
    """version이 schema_version보다 높다고 주장하는가.

    float까지 본다. {"version": 3.0}은 파이썬이 아닌 도구(jq, YAML 변환기, 다른 언어의
    v3 writer)가 실제로 만드는 형태다. int만 막고 float를 통과시키면 게이트의 존재
    이유 자체가 무력화된다.
    bool은 제외한다 — True는 int의 인스턴스지만 버전 주장이 아니다.
    문자열("3")은 통과시킨다. 손으로 고친 문서를 막지 않기 위해서다.
    """
    if isinstance(version, bool):
        return False
    return isinstance(version, (int, float)) and version > schema_version


def decode(data):
    """JSON 디코드. 구문이 깨졌으면 BROKEN 센티널."""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return BROKEN


def fingerprint(value):
    """키 정렬 JSON 문자열. 디스크 표현과 같은 직렬화 옵션을 쓴다."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def same(a, b):
    """값 동등 비교. 키 순서에 무관하다."""
    return fingerprint(a) == fingerprint(b)


def no_hold(local, repo):
    """보류가 없는 도메인을 위한 기본 훅. MCP 어댑터가 쓴다."""
    return {"value": frozenset(), "action": frozenset()}
