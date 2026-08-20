#!/usr/bin/env python3
"""claude-sync의 MCP 서버 동기화 코어.

데이터 소스는 ~/.claude.json의 top-level mcpServers(user 스코프)다.
`claude mcp list`의 텍스트 출력은 쓰지 않는다 — 손실 압축이고 cwd에 의존한다.
backup/status/restore는 이 모듈만 통해 MCP를 다룬다(파서 드리프트 차단).
"""
import copy
import json
import os

SENTINEL = "<REDACTED>"
SECRET_FIELDS = ("headers", "env")
SCHEMA_VERSION = 2
BACKUP_RELPATH = "mcp-servers.json"
DEFAULT_CLAUDE_JSON = os.path.expanduser("~/.claude.json")


class LocalConfigUnavailable(Exception):
    """~/.claude.json을 읽지 못했다.

    "서버 0개"와 반드시 구별해야 한다. 이 예외가 발생하면 삭제 판정을 해서는 안 된다.
    """


def read_local_servers(claude_json_path=None):
    """user 스코프 mcpServers를 반환한다.

    mcpServers 키가 아예 없으면 {} (서버 0개라는 정상 상태).
    키가 있는데 값이 dict가 아니면(null 포함) 읽기 실패로 취급해 예외를 던진다 —
    잘못된 삭제 판정을 막기 위해서다.
    파일이 없거나 JSON 파싱에 실패해도 LocalConfigUnavailable을 던진다.
    projects[*].mcpServers(local 스코프)는 읽지 않는다.
    PermissionError 등 그 외 OSError는 전파한다(LocalConfigUnavailable로 감싸지 않는다).
    """
    path = DEFAULT_CLAUDE_JSON if claude_json_path is None else claude_json_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise LocalConfigUnavailable("%s 없음" % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LocalConfigUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise LocalConfigUnavailable("%s 최상위가 객체가 아님" % path)
    if "mcpServers" not in data:
        return {}
    servers = data["mcpServers"]
    if not isinstance(servers, dict):
        raise LocalConfigUnavailable("mcpServers가 객체가 아님")
    return dict(servers)


def _redact_field(value):
    """headers/env 한 필드의 값을 마스킹한다. 중첩 구조는 통째로 SENTINEL이 된다.

    값이 dict가 아니면(None 포함) 필드 전체가 dict가 아닌 문자열 SENTINEL로 바뀐다 —
    타입이 dict에서 str로 바뀌므로 secret_keys는 이 필드에 대해 키를 하나도 묻지 않는다.
    """
    if isinstance(value, dict):
        return {k: SENTINEL for k in value}
    return SENTINEL


def redact(servers):
    """headers/env의 값만 SENTINEL로 치환한다. 키 이름과 나머지 필드는 보존한다.

    입력은 변경하지 않으며, 반환값은 입력과 어떤 중첩 객체도 공유하지 않는다
    (deepcopy) — 후속 가공이 반환값을 다듬어도 원본 로컬 설정이 오염되지 않는다.
    이미 마스킹된 입력에 다시 적용해도 결과가 같다(멱등) — diff/merge가 로컬(평문)과
    레포(마스킹됨) 양쪽에 이 함수를 적용해 수렴시키는 전제다.
    """
    out = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            out[name] = cfg
            continue
        new = copy.deepcopy(cfg)
        for field in SECRET_FIELDS:
            if field in new:
                new[field] = _redact_field(new[field])
        out[name] = new
    return out


def secret_keys(cfg):
    """복원 시 사용자에게 값을 물어야 하는 (field, key) 목록."""
    found = []
    if not isinstance(cfg, dict):
        return found
    for field in SECRET_FIELDS:
        value = cfg.get(field)
        if isinstance(value, dict):
            found.extend((field, k) for k in sorted(value))
    return found


def _servers_from_obj(obj):
    """이미 디코딩된 JSON 객체에서 servers 매핑을 뽑는다. v2 객체와 v1 배열을 지원한다."""
    if isinstance(obj, list):
        out = {}
        for item in obj:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                out[item["name"]] = {k: v for k, v in item.items() if k != "name"}
        return out
    if isinstance(obj, dict):
        servers = obj.get("servers")
        return dict(servers) if isinstance(servers, dict) else {}
    return {}


def parse_backup(data):
    """JSON 바이트/문자열에서 servers 매핑을 읽는다.

    v2 객체({"version":2, "servers":{...}})와 v1 배열([{name,url,type}, ...])을 모두 지원한다.
    깨진 입력은 {}로 degrade한다 — 레포 파일이 깨졌다고 백업 전체를 막지 않는다.
    """
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return _servers_from_obj(obj)


def parse_base(data):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None을 반환한다.

    "이력이 비어 있었다"({})와 "이력을 읽을 수 없다"(None)를 반드시 구별해야 한다.
    전자는 삭제·충돌 판정의 근거가 되지만, 후자는 근거가 될 수 없다.

    백업 문서로 알아볼 수 있는 형태 — v1 배열, 또는 servers가 dict인 v2 객체 — 일 때만
    매핑을 돌려준다. 구문은 유효하지만 스키마가 아닌 JSON(null, 문자열, 숫자,
    servers가 없거나 dict가 아닌 객체)은 신뢰할 수 없는 이력이므로 None이다.
    """
    if data is None:
        return None
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(obj, list):
        return _servers_from_obj(obj)
    if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
        return _servers_from_obj(obj)
    return None


def load_backup(path):
    """mcp-servers.json을 읽어 servers 매핑을 반환한다. 파일이 없으면 {}.

    (PermissionError 등 그 외 OSError는 전파한다.)
    """
    try:
        with open(path, "rb") as f:
            return parse_backup(f.read())
    except FileNotFoundError:
        return {}


def dump_backup(servers, path):
    """v2 형식으로 저장한다. sort_keys로 git diff를 안정화한다."""
    payload = {"version": SCHEMA_VERSION, "scope": "user", "servers": servers}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def _fingerprint(cfg):
    return json.dumps(cfg, sort_keys=True, ensure_ascii=False)


def same(a, b):
    """설정 동등 비교. 키 순서에 무관하다."""
    return _fingerprint(a) == _fingerprint(b)


def diff(local, backed):
    """상태 비교. 비교 직전 양쪽에 redact를 적용한다.

    비밀 값은 로컬에 평문, 레포에 SENTINEL로 저장되므로 원본끼리 비교하면
    비밀을 가진 서버가 영구히 "변경됨"으로 보고된다(Bug #2와 같은 미수렴).
    """
    L, R = redact(local), redact(backed)
    return {
        "only_local": sorted(set(L) - set(R)),
        "only_repo": sorted(set(R) - set(L)),
        "changed": sorted(n for n in set(L) & set(R) if not same(L[n], R[n])),
    }
