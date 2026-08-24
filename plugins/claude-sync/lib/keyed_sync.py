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
    """값을 키 정렬 JSON 문자열로 만들어 비교 가능한 형태로 바꾼다.

    어댑터의 디스크 직렬화와 같은 옵션(sort_keys, ensure_ascii=False)을 쓴다 —
    디스크 표현이 같으면 same()도 같다고 판정하도록 맞춘 것이다.
    (들여쓰기·봉투 구조는 공유하지 않으므로 결과 문자열이 파일 내용과 같지는 않다.)
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def same(a, b):
    """값 동등 비교. 키 순서에 무관하다."""
    return fingerprint(a) == fingerprint(b)


def parse_base(data, recognize):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None을 반환한다.

    "이력이 비어 있었다"({})와 "이력을 읽을 수 없다"(None)를 반드시 구별해야 한다.
    전자는 삭제·충돌 판정의 근거가 되지만, 후자는 근거가 될 수 없다.
    """
    if data is None:
        return None
    obj = decode(data)
    if obj is BROKEN:
        return None
    return recognize(obj)


def load_backup(path, recognize):
    """레포의 백업 파일을 안전하게 읽는다. 파일이 없으면 {}.

    구문이 깨진 파일은 {}로 degrade한다 — 레포 파일 하나가 깨졌다고 백업 전체를 막지
    않으며, 다음 백업이 그 파일을 정상 내용으로 되돌린다.
    구문은 유효한데 형식을 알아볼 수 없으면 UnknownBackupSchema를 던진다.
    (PermissionError 등 그 외 OSError는 전파한다.)
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}
    obj = decode(raw)
    if obj is BROKEN:
        return {}
    recognized = recognize(obj)
    if recognized is None:
        raise UnknownBackupSchema(
            "%s의 형식을 알아볼 수 없다 — 상위 버전이 쓴 백업일 수 있다" % path
        )
    return recognized


def parse_backup(data, recognize):
    """바이트/문자열에서 매핑을 읽는다(관대한 해석). 실패는 전부 {}.

    **레포 파일을 읽을 때는 이 함수가 아니라 load_backup을 쓴다** — 알아볼 수 없는
    문서를 "0개"로 읽으면 그 파일을 덮어써 파괴하기 때문이다.
    """
    obj = decode(data)
    if obj is BROKEN:
        return {}
    recognized = recognize(obj)
    return {} if recognized is None else recognized


def no_hold(local, repo):
    """보류가 없는 도메인을 위한 기본 훅. MCP 어댑터가 쓴다."""
    return {"value": frozenset(), "action": frozenset()}
