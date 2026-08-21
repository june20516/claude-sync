import json

import pytest

import mcp_config as mc

SERVER_A = {"command": "a"}
SERVER_B = {"command": "b"}
SERVER_ORIG = {"command": "o"}


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


def test_parse_base_none_input_is_none():
    assert mc.parse_base(None) is None


def test_parse_base_broken_json_is_none():
    """손상된 base는 '비어 있던 이력'이 아니라 '이력 없음'이어야 한다."""
    assert mc.parse_base(b"{not json") is None


def test_parse_base_empty_servers_is_empty_dict():
    """정상적으로 비어 있던 이력은 {}이며 None이 아니다 — 삭제 판정의 근거가 된다."""
    assert mc.parse_base(b'{"version": 2, "servers": {}}') == {}


def test_parse_base_reads_v2_servers():
    data = b'{"version": 2, "servers": {"a": {"command": "x"}}}'
    assert mc.parse_base(data) == {"a": {"command": "x"}}


def test_dump_load_dump_is_fixed_point(tmp_path):
    """load 후 재 dump해도 바이트가 같다 — 매 백업마다 diff가 생기지 않는다."""
    servers = {"b": {"command": "x", "args": ["2", "1"]}, "a": {"url": "u"}}
    p1, p2 = str(tmp_path / "1.json"), str(tmp_path / "2.json")
    mc.dump_backup(servers, p1)
    mc.dump_backup(mc.load_backup(p1), p2)
    assert open(p1, "rb").read() == open(p2, "rb").read()


def test_parse_backup_v2_null_servers_is_empty():
    assert mc.parse_backup(b'{"version": 2, "servers": null}') == {}
    assert mc.parse_backup(b'{"version": 2}') == {}


def test_dump_load_roundtrip_preserves_unicode_and_special_names(tmp_path):
    """공백·점·한글이 든 이름과 중첩 값이 손실 없이 왕복된다."""
    servers = {
        "claude.ai Notion": {"type": "http", "url": "https://mcp.notion.com/mcp"},
        "한글 서버": {"command": "/Applications/My App/bin", "args": ["--mcp", "-v"]},
        "nested": {"a": {"b": [1, True, None, "x"]}},
    }
    path = str(tmp_path / "mcp-servers.json")
    mc.dump_backup(servers, path)
    assert mc.load_backup(path) == servers


def test_parse_base_valid_json_but_not_a_backup_is_none():
    """구문은 유효하지만 백업 문서가 아닌 JSON은 신뢰할 수 없는 이력이다."""
    for data in (
        b"null",
        b'"just a string"',
        b"42",
        b'{"version": 2}',
        b'{"version": 2, "servers": null}',
    ):
        assert mc.parse_base(data) is None, data


def test_parse_base_empty_v1_array_is_empty_dict():
    """v1 배열이 비어 있던 것은 정상적으로 비어 있던 이력이다 — None이 아니다."""
    assert mc.parse_base(b"[]") == {}


def test_parse_backup_stays_lenient_where_parse_base_rejects():
    """두 함수의 계약이 다르다: parse_backup은 관대하게 {}, parse_base는 None."""
    data = b'{"version": 2}'
    assert mc.parse_backup(data) == {}
    assert mc.parse_base(data) is None


def test_same_ignores_key_order():
    assert mc.same({"a": 1, "b": 2}, {"b": 2, "a": 1})
    assert not mc.same({"a": 1}, {"a": 2})


def test_diff_all_equal():
    servers = {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}
    result = mc.diff(servers, servers)
    assert result == {"only_local": [], "only_repo": [], "changed": []}


def test_diff_converges_when_repo_is_redacted():
    """로컬 평문 vs 레포 마스킹이 in_sync로 수렴한다 — Bug #2 및 마스킹 함정 회귀."""
    local = {"context7": {"type": "http", "headers": {"CONTEXT7_API_KEY": "sk-real"}}}
    backed = mc.redact(local)
    assert mc.diff(local, backed)["changed"] == []


def test_diff_detects_changed_command():
    local = {"playwright": {"command": "npx", "args": ["@playwright/mcp@2.0"]}}
    backed = {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}
    assert mc.diff(local, backed)["changed"] == ["playwright"]


def test_diff_reports_only_local_and_only_repo():
    result = mc.diff({"a": {"command": "x"}}, {"b": {"command": "y"}})
    assert result["only_local"] == ["a"]
    assert result["only_repo"] == ["b"]


def test_diff_ignores_secret_value_change():
    """비밀 값만 바뀐 변경은 동기화되지 않는다 (spec 6장)."""
    local = {"c7": {"headers": {"K": "new-key"}}}
    backed = {"c7": {"headers": {"K": mc.SENTINEL}}}
    assert mc.diff(local, backed)["changed"] == []


def test_diff_detects_header_key_renamed():
    """비밀 값은 가려도 키 이름 변경은 보여야 한다 — 마스킹이 진짜 변경을 묻지 않는다."""
    local = {"c7": {"headers": {"A_KEY": "x"}}}
    backed = {"c7": {"headers": {"B_KEY": "x"}}}
    assert mc.diff(local, backed)["changed"] == ["c7"]


def test_diff_detects_secret_field_added_or_removed():
    """headers 필드가 통째로 생기거나 사라지는 것도 변경이다."""
    without = {"c7": {"url": "u"}}
    with_headers = {"c7": {"url": "u", "headers": {"K": "v"}}}
    assert mc.diff(with_headers, without)["changed"] == ["c7"]
    assert mc.diff(without, with_headers)["changed"] == ["c7"]


def test_diff_detects_env_emptied():
    """env가 빈 dict가 된 것도 변경이다 — 키가 사라졌으므로."""
    local = {"n": {"command": "npx", "env": {}}}
    backed = {"n": {"command": "npx", "env": {"TOKEN": "x"}}}
    assert mc.diff(local, backed)["changed"] == ["n"]


def test_merge_case1_local_new():
    r = mc.merge({"x": SERVER_A}, {}, {})
    assert r["servers"] == {"x": SERVER_A}
    assert r["conflicts"] == [] and r["local_stale"] == [] and r["deleted"] == []


def test_merge_case2_remote_added_is_preserved():
    r = mc.merge({}, {"x": SERVER_A}, {})
    assert r["servers"] == {"x": SERVER_A}


def test_merge_case3_local_deleted_removes_from_repo():
    r = mc.merge({}, {"x": SERVER_A}, {"x": SERVER_A})
    assert r["servers"] == {}
    assert r["deleted"] == ["x"]


def test_merge_case4_remote_deleted_local_kept_is_stale():
    r = mc.merge({"x": SERVER_A}, {}, {"x": SERVER_A})
    assert r["servers"] == {}
    assert r["local_stale"] == ["x"]
    assert r["conflicts"] == []


def test_merge_case5_local_modified_vs_remote_deleted_is_conflict():
    r = mc.merge({"x": SERVER_B}, {}, {"x": SERVER_ORIG})
    assert r["conflicts"] == ["x"]
    assert "x" not in r["servers"]


def test_merge_case6_in_sync():
    r = mc.merge({"x": SERVER_A}, {"x": SERVER_A}, {"x": SERVER_ORIG})
    assert r["servers"] == {"x": SERVER_A}
    assert r["conflicts"] == []


def test_merge_case7_local_only_changed_pushes():
    r = mc.merge({"x": SERVER_B}, {"x": SERVER_ORIG}, {"x": SERVER_ORIG})
    assert r["servers"] == {"x": SERVER_B}


def test_merge_case8_remote_only_changed_keeps_repo():
    r = mc.merge({"x": SERVER_ORIG}, {"x": SERVER_B}, {"x": SERVER_ORIG})
    assert r["servers"] == {"x": SERVER_B}


def test_merge_case9_both_changed_is_conflict():
    r = mc.merge({"x": SERVER_A}, {"x": SERVER_B}, {"x": SERVER_ORIG})
    assert r["conflicts"] == ["x"]
    assert r["servers"] == {"x": SERVER_B}


def test_merge_case9_without_base_entry_is_conflict():
    r = mc.merge({"x": SERVER_A}, {"x": SERVER_B}, {})
    assert r["conflicts"] == ["x"]
    assert r["servers"] == {"x": SERVER_B}


def test_merge_case10_base_only_is_noop():
    r = mc.merge({}, {}, {"x": SERVER_A})
    assert r["servers"] == {}
    assert r["deleted"] == [] and r["conflicts"] == [] and r["local_stale"] == []


def test_merge_without_base_is_union_no_delete():
    r = mc.merge({"a": SERVER_A}, {"b": SERVER_B}, None)
    assert r["servers"] == {"a": SERVER_A, "b": SERVER_B}
    assert r["deleted"] == []


def test_merge_without_base_prefers_local():
    r = mc.merge({"x": SERVER_A}, {"x": SERVER_B}, None)
    assert r["servers"] == {"x": SERVER_A}


def apply_round(local, repo, base):
    """백업 1회분: merge → 레포 반영 → base ← next_base."""
    result = mc.merge(local, repo, base)
    return dict(result["servers"]), dict(result["next_base"]), result


def test_next_base_keeps_remote_added_server_across_rounds():
    """케이스 2: 타 기기가 추가한 서버가 두 번째 백업에서 삭제되지 않는다 — Critical 1 회귀."""
    local = {"x": SERVER_A}
    repo, base = {"x": SERVER_A, "z": SERVER_B}, {"x": SERVER_A}
    for _ in range(3):
        repo, base, result = apply_round(local, repo, base)
        assert set(repo) == {"x", "z"}
        assert result["deleted"] == []


def test_next_base_keeps_remote_change_across_rounds():
    """케이스 8: 타 기기의 변경이 두 번째 백업에서 되돌려지지 않는다 — Critical 1 회귀."""
    local = {"y": SERVER_ORIG}
    repo, base = {"y": SERVER_B}, {"y": SERVER_ORIG}
    for _ in range(3):
        repo, base, _ = apply_round(local, repo, base)
        assert repo == {"y": SERVER_B}


def test_next_base_new_machine_does_not_wipe_others():
    """base=None인 새 기기가 두 번째 백업에서 남의 서버를 전멸시키지 않는다 — Critical 1 회귀."""
    local = {"x": SERVER_A}
    repo, base = {"x": SERVER_A, "z": SERVER_B}, None
    for _ in range(3):
        repo, base, result = apply_round(local, repo, base)
        assert set(repo) == {"x", "z"}
        assert result["deleted"] == []


def test_next_base_advances_when_local_agrees():
    """케이스 7: 로컬이 동의한 값은 base가 전진해 다음 라운드에 in_sync가 된다."""
    local = {"x": SERVER_B}
    repo, base, _ = apply_round(local, {"x": SERVER_ORIG}, {"x": SERVER_ORIG})
    assert repo == {"x": SERVER_B}
    assert base == {"x": SERVER_B}
    repo2, _, result2 = apply_round(local, repo, base)
    assert repo2 == {"x": SERVER_B}
    assert result2["conflicts"] == [] and result2["deleted"] == []


def test_next_base_drops_name_deleted_on_both_sides():
    """케이스 3: 로컬에서 지운 서버는 base에서도 빠져 다음 라운드가 no-op이 된다."""
    local = {}
    repo, base, result = apply_round(local, {"x": SERVER_A}, {"x": SERVER_A})
    assert result["deleted"] == ["x"]
    assert repo == {} and base == {}
    repo2, _, result2 = apply_round(local, repo, base)
    assert repo2 == {} and result2["deleted"] == []


def test_next_base_holds_old_value_while_stale_or_conflicted():
    """케이스 4·9: 로컬이 동의하지 않은 이름은 base가 이전 값을 유지해 판정이 고정된다."""
    stale_base = mc.merge({"x": SERVER_A}, {}, {"x": SERVER_A})["next_base"]
    assert stale_base == {"x": SERVER_A}
    conflict_base = mc.merge({"x": SERVER_A}, {"x": SERVER_B}, {"x": SERVER_ORIG})["next_base"]
    assert conflict_base == {"x": SERVER_ORIG}


def test_merge_redacts_input_internally():
    """호출부가 원본을 넘겨도 비밀이 결과에 실려 나가지 않는다 — Important 1 회귀."""
    raw = {"c7": {"url": "u", "headers": {"K": "sk-REAL-SECRET"}}}
    masked = mc.redact(raw)
    result = mc.merge(raw, masked, masked)
    assert "sk-REAL-SECRET" not in json.dumps(result["servers"])
    assert result["conflicts"] == []


def test_merge_result_does_not_share_objects_with_input():
    """반환된 config를 변형해도 입력이 오염되지 않는다."""
    local = {"x": {"command": "a", "args": ["1"]}}
    result = mc.merge(local, {}, {})
    result["servers"]["x"]["args"].append("MUTATED")
    assert local["x"]["args"] == ["1"]


def test_merge_reports_repo_ahead_for_cases_2_and_8():
    """타 기기가 추가·변경한 서버를 사용자에게 알릴 수 있어야 한다 — Important 2."""
    added = mc.merge({}, {"z": SERVER_B}, {})
    assert added["repo_ahead"] == ["z"]
    changed = mc.merge({"y": SERVER_ORIG}, {"y": SERVER_B}, {"y": SERVER_ORIG})
    assert changed["repo_ahead"] == ["y"]
    conflicted = mc.merge({"x": SERVER_A}, {"x": SERVER_B}, {"x": SERVER_ORIG})
    assert conflicted["repo_ahead"] == [] and conflicted["conflicts"] == ["x"]


def test_next_base_does_not_share_objects_with_servers():
    """servers를 가공해도 next_base가 오염되지 않는다 — 둘은 독립된 출력이다."""
    result = mc.merge({"x": {"command": "a", "args": ["1"]}}, {}, {})
    result["servers"]["x"]["args"].append("MUTATED")
    assert result["next_base"]["x"]["args"] == ["1"]


def test_next_base_redacts_input_so_secret_server_advances():
    """로컬 평문과 레포 SENTINEL이 동등으로 판정되어 base가 전진한다 — 5장 계약 회귀.

    이 계약이 없으면 비밀을 가진 서버의 base가 영영 전진하지 않는다(7.3 불변식이 깨진다).
    """
    local = {"context7": {"type": "http", "url": "u", "headers": {"K": "sk-real"}}}
    servers = {"context7": {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}}
    base = {"context7": {"type": "http", "url": "old", "headers": {"K": mc.SENTINEL}}}
    out = mc.next_base(local, base, servers)
    assert out["context7"]["url"] == "u"


def test_next_base_never_writes_plaintext_secret():
    """base 블롭에 평문 비밀이 새 사본으로 기록되면 안 된다."""
    local = {"context7": {"type": "http", "url": "u", "headers": {"K": "sk-real"}}}
    out = mc.next_base(local, None, local)
    assert out["context7"]["headers"]["K"] == mc.SENTINEL


REPO_HTTP = {
    "type": "http",
    "url": "https://mcp.context7.com/mcp",
    "headers": {"CONTEXT7_API_KEY": mc.SENTINEL},
}


def test_restore_plan_add_for_plain_repo_only_server():
    plan = mc.restore_plan({}, {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}, None)
    assert plan["add"] == ["playwright"]
    assert plan["needs_secret"] == [] and plan["unrestorable"] == []


def test_restore_plan_needs_secret_when_repo_has_masked_headers():
    plan = mc.restore_plan({}, {"context7": REPO_HTTP}, None)
    assert plan["needs_secret"] == ["context7"]
    assert plan["add"] == []


def test_restore_plan_accepts_sse_server():
    plan = mc.restore_plan({}, {"sse-one": {"type": "sse", "url": "https://x/sse"}}, None)
    assert plan["add"] == ["sse-one"]


def test_restore_plan_unrestorable_for_invalid_name():
    """이름 규칙(^[A-Za-z0-9_-]+$) 위반은 add-json이 exit 1이다 — 시도하지 않는다."""
    plan = mc.restore_plan({}, {"claude.ai Notion": {"command": "npx"}}, None)
    assert plan["unrestorable"] == ["claude.ai Notion"]
    assert plan["add"] == []


def test_restore_plan_unrestorable_for_v1_promoted_entry():
    """v1 승격 항목은 command도 url+type(http/sse)도 아니다 — 10장."""
    v1 = {"legacy": {"url": "npx @playwright/mcp@latest", "type": "stdio"}}
    plan = mc.restore_plan({}, v1, None)
    assert plan["unrestorable"] == ["legacy"]
    assert plan["add"] == [] and plan["needs_secret"] == []


def test_restore_plan_unrestorable_for_non_dict_config():
    """4장: config가 객체가 아닌 항목은 보존하되 복원은 하지 않는다."""
    plan = mc.restore_plan({}, {"broken": None}, None)
    assert plan["unrestorable"] == ["broken"]


def test_restore_plan_in_sync_when_local_secret_is_plaintext():
    """로컬 평문 vs 레포 SENTINEL이 in_sync로 수렴한다 — 영구 미수렴 회귀."""
    local = {"context7": dict(REPO_HTTP, headers={"CONTEXT7_API_KEY": "sk-real"})}
    plan = mc.restore_plan(local, {"context7": REPO_HTTP}, None)
    assert plan["in_sync"] == ["context7"]
    assert plan["both_changed"] == []


def test_restore_plan_splits_cases_7_8_9():
    """7·8·9를 한 버킷으로 뭉치면 케이스 7에 '레포 값 채택'이 제시되어 미백업 변경이 파괴된다."""
    local = {"seven": SERVER_A, "eight": SERVER_ORIG, "nine": SERVER_A}
    repo = {"seven": SERVER_ORIG, "eight": SERVER_B, "nine": SERVER_B}
    base = {"seven": SERVER_ORIG, "eight": SERVER_ORIG, "nine": SERVER_ORIG}
    plan = mc.restore_plan(local, repo, base)
    assert plan["local_ahead"] == ["seven"]
    assert plan["repo_ahead"] == ["eight"]
    assert plan["both_changed"] == ["nine"]


def test_restore_plan_local_stale_covers_case4_and_case5():
    """merge.local_stale(케이스 4만)보다 넓다 — 케이스 5에 탈출구를 주기 위해서다."""
    local = {"four": SERVER_A, "five": SERVER_B}
    base = {"four": SERVER_A, "five": SERVER_ORIG}
    plan = mc.restore_plan(local, {}, base)
    assert plan["local_stale"] == ["five", "four"]
    assert plan["local_only"] == []


def test_restore_plan_local_only_when_name_absent_from_base():
    """케이스 1(로컬 신규). restore는 아무것도 하지 않는다."""
    plan = mc.restore_plan({"fresh": SERVER_A}, {}, {"other": SERVER_B})
    assert plan["local_only"] == ["fresh"]
    assert plan["local_stale"] == []


def test_restore_plan_without_base_degrades_to_both_changed_and_local_only():
    """base가 None이면 케이스를 확정할 수 없다 — 삭제도 local_ahead도 단정하지 않는다."""
    plan = mc.restore_plan({"x": SERVER_A, "solo": SERVER_A}, {"x": SERVER_B}, None)
    assert plan["both_changed"] == ["x"]
    assert plan["local_only"] == ["solo"]
    assert plan["local_stale"] == []


FUTURE_V3 = b'{"version": 3, "scope": "user", "entries": {"x": {"command": "a"}}}'


def test_load_backup_raises_on_unrecognized_schema(tmp_path):
    """미래 버전이 쓴 백업을 '서버 0개'로 읽으면 안 된다 — 읽는 쪽이 레포를 비운다.

    parse_base는 이미 이 구별을 하는데(None), 레포 경로에는 적용되어 있지 않았다.
    불변식 2를 base에만 적용하고 레포 파일에는 적용하지 않은 결함이다.
    """
    path = str(tmp_path / "mcp-servers.json")
    open(path, "wb").write(FUTURE_V3)
    with pytest.raises(mc.UnknownBackupSchema):
        mc.load_backup(path)


def test_load_backup_stays_lenient_on_broken_json(tmp_path):
    """구문이 깨진 파일은 여전히 {}로 degrade한다 — 미지의 스키마와 구별한다."""
    path = str(tmp_path / "mcp-servers.json")
    open(path, "wb").write(b"{not json")
    assert mc.load_backup(path) == {}


# --- 상위 스키마 게이트 (spec 7장) ---

def _v3_doc():
    """형태는 v2와 같지만 version이 3인 문서. 형태만 보면 알아보게 된다."""
    return json.dumps({"version": 3, "scope": "user", "servers": {"a": {"command": "a"}}})


def test_load_backup_rejects_higher_schema_version(tmp_path):
    path = tmp_path / "mcp-servers.json"
    path.write_text(_v3_doc(), encoding="utf-8")
    with pytest.raises(mc.UnknownBackupSchema):
        mc.load_backup(str(path))


def test_parse_base_rejects_higher_schema_version():
    """레포와 base가 같은 기준을 써야 한다 — 비대칭이 상위 버전 백업을 파괴한다."""
    assert mc.parse_base(_v3_doc().encode("utf-8")) is None


def test_parse_backup_degrades_higher_schema_version():
    assert mc.parse_backup(_v3_doc()) == {}


def test_current_schema_version_still_accepted(tmp_path):
    path = tmp_path / "mcp-servers.json"
    mc.dump_backup({"a": {"command": "a"}}, str(path))
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


def test_v1_array_still_accepted(tmp_path):
    """v1 배열에는 version 개념이 없다. 게이트가 이것을 막으면 안 된다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps([{"name": "a", "command": "a"}]), encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


def test_object_without_version_still_accepted(tmp_path):
    """손으로 만든 문서를 막을 이유는 없다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"servers": {"a": {"command": "a"}}}), encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


@pytest.mark.parametrize("version", [3.0, 99.5])
def test_float_version_claiming_newer_is_rejected(version, tmp_path):
    """jq나 다른 언어의 writer가 만드는 형태다. int만 막으면 게이트가 무력화된다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"version": version, "servers": {"a": {"command": "a"}}}),
                    encoding="utf-8")
    with pytest.raises(mc.UnknownBackupSchema):
        mc.load_backup(str(path))


@pytest.mark.parametrize("version", ["3", True, None, [3]])
def test_non_numeric_version_is_still_recognized(version, tmp_path):
    """결정: 숫자가 아니면 버전 주장으로 보지 않는다. 손으로 고친 문서를 막지 않는다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"version": version, "servers": {"a": {"command": "a"}}}),
                    encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


@pytest.mark.parametrize("version", [1, 2, 2.0, 0])
def test_version_at_or_below_current_is_recognized(version, tmp_path):
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"version": version, "servers": {"a": {"command": "a"}}}),
                    encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}
