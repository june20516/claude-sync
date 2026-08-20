#!/usr/bin/env python3
"""claude-sync의 MCP 서버 동기화 코어.

데이터 소스는 ~/.claude.json의 top-level mcpServers(user 스코프)다.
`claude mcp list`의 텍스트 출력은 쓰지 않는다 — 손실 압축이고 cwd에 의존한다.
backup/status/restore는 이 모듈만 통해 MCP를 다룬다(파서 드리프트 차단).
"""
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

    mcpServers 키가 없으면 {} (서버 0개라는 정상 상태).
    파일이 없거나 JSON 파싱에 실패하면 LocalConfigUnavailable을 던진다.
    projects[*].mcpServers(local 스코프)는 읽지 않는다.
    """
    path = claude_json_path or DEFAULT_CLAUDE_JSON
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise LocalConfigUnavailable("%s 없음" % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LocalConfigUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise LocalConfigUnavailable("%s 최상위가 객체가 아님" % path)
    servers = data.get("mcpServers")
    if servers is None:
        return {}
    if not isinstance(servers, dict):
        raise LocalConfigUnavailable("mcpServers가 객체가 아님")
    return dict(servers)
