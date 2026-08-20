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


def test_read_local_servers_top_level_not_dict_raises(tmp_path):
    """최상위가 객체가 아니면 '서버 0개'가 아니라 읽기 실패다."""
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(mc.LocalConfigUnavailable):
        mc.read_local_servers(str(p))


def test_read_local_servers_mcp_servers_not_dict_raises(tmp_path):
    """mcpServers가 객체가 아니면 읽기 실패로 취급해 삭제 판정을 막는다."""
    path = write_claude_json(tmp_path, {"mcpServers": "nope"})
    with pytest.raises(mc.LocalConfigUnavailable):
        mc.read_local_servers(path)


def test_read_local_servers_null_mcp_servers_raises(tmp_path):
    """키가 있는데 값이 null이면 '서버 0개'가 아니라 읽기 실패다 — 잘못된 삭제 판정 방지."""
    path = write_claude_json(tmp_path, {"mcpServers": None})
    with pytest.raises(mc.LocalConfigUnavailable):
        mc.read_local_servers(path)


def test_redact_masks_header_values_keeps_key_names():
    servers = {"context7": {
        "type": "http",
        "url": "https://mcp.context7.com/mcp",
        "headers": {"CONTEXT7_API_KEY": "sk-real-secret"},
    }}
    out = mc.redact(servers)
    assert out["context7"]["headers"] == {"CONTEXT7_API_KEY": mc.SENTINEL}
    assert out["context7"]["url"] == "https://mcp.context7.com/mcp"
    assert out["context7"]["type"] == "http"


def test_redact_masks_env_values():
    servers = {"notion": {"command": "npx", "env": {"NOTION_TOKEN": "ntn_xxx"}}}
    out = mc.redact(servers)
    assert out["notion"]["env"] == {"NOTION_TOKEN": mc.SENTINEL}
    assert out["notion"]["command"] == "npx"


def test_redact_does_not_mutate_input():
    servers = {"c7": {"headers": {"K": "secret"}}}
    mc.redact(servers)
    assert servers["c7"]["headers"]["K"] == "secret"


def test_redact_handles_non_dict_secret_field():
    servers = {"weird": {"headers": "not-a-dict"}}
    assert mc.redact(servers)["weird"]["headers"] == mc.SENTINEL


def test_redact_preserves_stdio_command_with_spaces():
    """공백이 든 command가 온전히 보존된다 — Bug #1 회귀."""
    cmd = "/Applications/Safari Technology Preview.app/Contents/MacOS/safaridriver"
    servers = {"safari-mcp-stp": {"command": cmd, "args": ["--mcp"]}}
    assert mc.redact(servers)["safari-mcp-stp"]["command"] == cmd


def test_secret_keys_lists_fields_and_keys():
    cfg = {"headers": {"B_KEY": "x", "A_KEY": "y"}, "env": {"TOKEN": "z"}}
    assert mc.secret_keys(cfg) == [("headers", "A_KEY"), ("headers", "B_KEY"), ("env", "TOKEN")]


def test_secret_keys_empty_when_no_secrets():
    assert mc.secret_keys({"command": "npx", "args": ["x"]}) == []


def test_redact_result_does_not_share_nested_objects():
    """반환값은 원본과 구조를 공유하지 않는다 — 결과를 변형해도 원본이 오염되지 않는다."""
    servers = {"c7": {"args": ["--flag"], "headers": {"K": "secret"}}}
    out = mc.redact(servers)
    out["c7"]["args"].append("MUTATED")
    assert servers["c7"]["args"] == ["--flag"]


def test_redact_is_idempotent():
    """이미 마스킹된 입력에 다시 적용해도 결과가 같다 — diff/merge 수렴의 전제."""
    servers = {
        "a": {"headers": {"K": "secret"}},
        "b": {"headers": "not-a-dict"},
        "c": {"env": {}},
        "d": {"command": "npx", "args": ["x"]},
    }
    once = mc.redact(servers)
    assert mc.redact(once) == once


def test_redact_passes_through_non_dict_server_config():
    servers = {"broken": "oops"}
    assert mc.redact(servers) == {"broken": "oops"}


def test_secret_keys_empty_for_non_dict_config():
    assert mc.secret_keys("oops") == []


def test_dump_and_load_roundtrip(tmp_path):
    servers = {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}
    path = str(tmp_path / "mcp-servers.json")
    mc.dump_backup(servers, path)
    assert mc.load_backup(path) == servers


def test_dump_writes_v2_envelope(tmp_path):
    path = str(tmp_path / "mcp-servers.json")
    mc.dump_backup({"a": {"command": "x"}}, path)
    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload["version"] == 2
    assert payload["scope"] == "user"
    assert payload["servers"] == {"a": {"command": "x"}}


def test_dump_is_byte_stable_regardless_of_key_order(tmp_path):
    p1, p2 = str(tmp_path / "a.json"), str(tmp_path / "b.json")
    mc.dump_backup({"b": {"y": 1, "x": 2}, "a": {"command": "c"}}, p1)
    mc.dump_backup({"a": {"command": "c"}, "b": {"x": 2, "y": 1}}, p2)
    assert open(p1, "rb").read() == open(p2, "rb").read()


def test_load_backup_missing_file_is_empty(tmp_path):
    assert mc.load_backup(str(tmp_path / "nope.json")) == {}


def test_load_backup_reads_v1_array(tmp_path):
    """구버전 배열 포맷을 이름 → 나머지 필드 매핑으로 승격한다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps([
        {"name": "context7", "url": "https://mcp.context7.com/mcp", "type": "HTTP"},
        {"name": "claude.ai Notion", "url": "https://mcp.notion.com/mcp", "type": "stdio"},
    ]), encoding="utf-8")
    loaded = mc.load_backup(str(path))
    assert set(loaded) == {"context7", "claude.ai Notion"}
    assert loaded["context7"] == {"url": "https://mcp.context7.com/mcp", "type": "HTTP"}


def test_parse_backup_garbage_is_empty():
    assert mc.parse_backup(b"{not json") == {}
