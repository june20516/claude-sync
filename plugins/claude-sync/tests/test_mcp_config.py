import json

import pytest

import mcp_config as mc


def write_claude_json(tmp_path, payload):
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_read_local_servers_returns_user_scope(tmp_path):
    path = write_claude_json(tmp_path, {
        "mcpServers": {
            "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},
        },
        "projects": {"/some/repo": {"mcpServers": {"atlassian": {"command": "npx"}}}},
    })
    servers = mc.read_local_servers(path)
    assert servers == {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}


def test_read_local_servers_excludes_project_scope(tmp_path):
    """local 스코프(projects[*].mcpServers)는 user 백업 대상이 아니다 — Bug #5."""
    path = write_claude_json(tmp_path, {
        "mcpServers": {},
        "projects": {"/some/repo": {"mcpServers": {"atlassian": {"command": "npx"}}}},
    })
    assert mc.read_local_servers(path) == {}


def test_read_local_servers_missing_key_is_zero_servers(tmp_path):
    """mcpServers 키 없음 = 서버 0개라는 정상 상태. 예외가 아니다."""
    path = write_claude_json(tmp_path, {"theme": "dark"})
    assert mc.read_local_servers(path) == {}


def test_read_local_servers_missing_file_raises(tmp_path):
    """파일 없음은 '서버 0개'가 아니다. 삭제 판정을 막기 위해 예외여야 한다."""
    with pytest.raises(mc.LocalConfigUnavailable):
        mc.read_local_servers(str(tmp_path / "nope.json"))


def test_read_local_servers_broken_json_raises(tmp_path):
    p = tmp_path / ".claude.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(mc.LocalConfigUnavailable):
        mc.read_local_servers(str(p))
