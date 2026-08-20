# MCP 서버 백업 데이터 소스 재설계 Implementation Plan

> **agentic worker에게:** REQUIRED SUB-SKILL: 이 plan을 task 단위로 구현하려면
> suberpower:subagent-driven-development(권장) 또는 suberpower:executing-plans를 사용하세요.
> Step은 추적을 위해 checkbox(`- [ ]`) 문법을 사용합니다.

**Goal:** MCP 서버 백업의 데이터 소스를 `claude mcp list` 텍스트 파싱에서 `~/.claude.json`의
user 스코프 `mcpServers` 직접 읽기로 전환하고, backup·status·restore를 단일 공용 모듈로 일원화한다.

**Architecture:** `lib/mcp_config.py`가 MCP를 다루는 유일한 경로가 된다. 백업 스키마는
서버 이름 → 원본 config 매핑(v2)으로 바뀌어 `command`/`args`/`env`/`headers`를 보존하며,
비밀 값만 마스킹한다. `mcp-servers.json`은 서버 이름 키 단위 3-way 병합 대상이 되고,
base 블롭은 기존 `sync_state`의 것을 그대로 재사용한다.

**Tech Stack:** Python 3 (표준 라이브러리만), pytest(uv로 실행), git

**Spec:** `docs/superpowers/specs/2026-08-20-mcp-config-source-design.md`

**테스트 실행:** 이 저장소에는 pytest가 설치되어 있지 않다. 항상 `uv`로 실행하며,
명령은 저장소 루트(`/Users/bran/personal/claude-sync`)에서 실행한다.
```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```
기준선: 착수 시점에 기존 테스트 32개가 통과한다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `plugins/claude-sync/lib/mcp_config.py` | **생성.** MCP 읽기·마스킹·직렬화·비교·병합·복원계획. 순수 함수 위주, 경로는 인자로 받는다 |
| `plugins/claude-sync/tests/test_mcp_config.py` | **생성.** 위 모듈의 단위·회귀 테스트 |
| `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py` | **생성.** 로컬을 읽어 레포 파일에 병합 저장, 결과를 JSON으로 보고 |
| `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py` | **생성.** 복원 계획을 JSON으로 출력 |
| `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py` | **삭제.** 정규식 파서 제거 |
| `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py` | **수정.** 정규식·stdin 제거, `mcp_config.diff()` 호출로 축소 |
| `plugins/claude-sync/skills/sync-backup/SKILL.md` | **수정.** 6단계 재작성, 동기화 대상 표 정정, base 게이트 |
| `plugins/claude-sync/skills/sync-status/SKILL.md` | **수정.** `claude mcp list` 파이프 제거 |
| `plugins/claude-sync/skills/sync-restore/SKILL.md` | **수정.** `add-json` 기반 재작성, 비밀 입력·local_stale 3지선다 |
| `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md` / `.ko.md` | **수정.** 백업 레포 README |
| `README.md` / `README.ko.md` | **수정.** 동작 모델·보장 범위 정정 |
| `.claude-plugin/marketplace.json`, `plugins/claude-sync/.claude-plugin/plugin.json` | **수정.** 2.0.0 → 3.0.0 |

base 갱신 스크립트는 새로 만들지 않는다. 기존 `update_base.py <source_root> <rel>...`와
`reconcile_restore.py --set-base-from <source_root> <rel>...`가 임의의 rel에 대해 동작한다.

---

## Task 1: `read_local_servers` — 데이터 소스와 안전장치

`~/.claude.json`을 읽지 못하는 상황을 "서버 0개"와 구별하는 것이 이 task의 핵심이다.
구별하지 못하면 병합이 레포의 모든 서버를 삭제할 수 있다.

**Files:**
- Create: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_config.py`를 새로 만든다.
(`tests/conftest.py`가 `../lib`를 `sys.path`에 넣어주므로 별도 경로 조작이 필요 없다.)

```python
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
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `ModuleNotFoundError: No module named 'mcp_config'`로 collection error

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/mcp_config.py`를 새로 만든다.

```python
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
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 5 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): ~/.claude.json user 스코프 읽기와 읽기 실패 구분"
```

---

## Task 2: `redact` / `secret_keys` — 비밀 마스킹

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

`test_mcp_config.py` 끝에 추가한다.

```python
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
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `AttributeError: module 'mcp_config' has no attribute 'redact'`로 7건 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`mcp_config.py`의 `read_local_servers` 아래에 추가한다.

```python
def _redact_field(value):
    """headers/env 한 필드의 값을 마스킹한다. 중첩 구조는 통째로 SENTINEL이 된다."""
    if isinstance(value, dict):
        return {k: SENTINEL for k in value}
    return SENTINEL


def redact(servers):
    """headers/env의 값만 SENTINEL로 치환한다. 키 이름과 나머지 필드는 보존한다.

    입력은 변경하지 않는다.
    """
    out = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            out[name] = cfg
            continue
        new = dict(cfg)
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
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 12 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): headers/env 값 마스킹, 키 이름은 보존"
```

---

## Task 3: 스키마 v2 직렬화와 v1 하위호환

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
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
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `AttributeError: module 'mcp_config' has no attribute 'dump_backup'`로 6건 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`mcp_config.py`의 `secret_keys` 아래에 추가한다.

```python
def parse_backup(data):
    """JSON 바이트/문자열에서 servers 매핑을 읽는다.

    v2 객체({"version":2, "servers":{...}})와 v1 배열([{name,url,type}, ...])을 모두 지원한다.
    깨진 입력은 {}로 degrade한다 — 레포 파일이 깨졌다고 백업 전체를 막지 않는다.
    """
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
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


def load_backup(path):
    """mcp-servers.json을 읽어 servers 매핑을 반환한다. 파일이 없으면 {}."""
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
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 18 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): 스키마 v2 직렬화와 v1 배열 하위호환 읽기"
```

---

## Task 4: `diff` — 마스킹 후 비교로 수렴 보장

status가 백업 직후에도 차이를 보고하던 원인(Bug #2)을 없애는 task다.
마스킹을 도입하면 로컬(평문) vs 레포(SENTINEL)가 항상 달라지므로,
비교 직전 **양쪽에** 마스킹을 적용하는 것이 핵심이다.

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
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
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `AttributeError: module 'mcp_config' has no attribute 'same'`로 6건 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`mcp_config.py`의 `dump_backup` 아래에 추가한다.

```python
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
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 24 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): 마스킹 적용 후 비교하는 diff"
```

---

## Task 5: `merge` — 서버 이름 키 단위 3-way 병합

spec 7.2 판정표 10줄을 그대로 구현한다. `local`은 호출부가 이미 `redact`를 적용한 상태로 넘긴다.

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
A = {"command": "a"}
B = {"command": "b"}
O = {"command": "o"}


def test_merge_case1_local_new():
    r = mc.merge({"x": A}, {}, {})
    assert r["servers"] == {"x": A}
    assert r["conflicts"] == [] and r["local_stale"] == [] and r["deleted"] == []


def test_merge_case2_remote_added_is_preserved():
    r = mc.merge({}, {"x": A}, {})
    assert r["servers"] == {"x": A}


def test_merge_case3_local_deleted_removes_from_repo():
    r = mc.merge({}, {"x": A}, {"x": A})
    assert r["servers"] == {}
    assert r["deleted"] == ["x"]


def test_merge_case4_remote_deleted_local_kept_is_stale():
    r = mc.merge({"x": A}, {}, {"x": A})
    assert r["servers"] == {}
    assert r["local_stale"] == ["x"]
    assert r["conflicts"] == []


def test_merge_case5_local_modified_vs_remote_deleted_is_conflict():
    r = mc.merge({"x": B}, {}, {"x": O})
    assert r["conflicts"] == ["x"]
    assert "x" not in r["servers"]


def test_merge_case6_in_sync():
    r = mc.merge({"x": A}, {"x": A}, {"x": O})
    assert r["servers"] == {"x": A}
    assert r["conflicts"] == []


def test_merge_case7_local_only_changed_pushes():
    r = mc.merge({"x": B}, {"x": O}, {"x": O})
    assert r["servers"] == {"x": B}


def test_merge_case8_remote_only_changed_keeps_repo():
    r = mc.merge({"x": O}, {"x": B}, {"x": O})
    assert r["servers"] == {"x": B}


def test_merge_case9_both_changed_is_conflict():
    r = mc.merge({"x": A}, {"x": B}, {"x": O})
    assert r["conflicts"] == ["x"]
    assert r["servers"] == {"x": B}


def test_merge_case9_without_base_entry_is_conflict():
    r = mc.merge({"x": A}, {"x": B}, {})
    assert r["conflicts"] == ["x"]
    assert r["servers"] == {"x": B}


def test_merge_case10_base_only_is_noop():
    r = mc.merge({}, {}, {"x": A})
    assert r["servers"] == {}
    assert r["deleted"] == [] and r["conflicts"] == [] and r["local_stale"] == []


def test_merge_without_base_is_union_no_delete():
    r = mc.merge({"a": A}, {"b": B}, None)
    assert r["servers"] == {"a": A, "b": B}
    assert r["deleted"] == []


def test_merge_without_base_prefers_local():
    r = mc.merge({"x": A}, {"x": B}, None)
    assert r["servers"] == {"x": A}
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `AttributeError: module 'mcp_config' has no attribute 'merge'`로 13건 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`mcp_config.py`의 `diff` 아래에 추가한다.

```python
def merge(local, repo, base):
    """서버 이름 키 단위 3-way 병합 (spec 7.2 판정표).

    local은 redact가 적용된 상태여야 한다(호출부 책임).
    base가 None이면 삭제 없이 합집합으로 degrade한다 — "타 기기 추가"와
    "내 삭제"를 구별할 수 없기 때문이다.
    conflicts 또는 local_stale이 비어 있지 않으면 호출부는 base를 갱신해서는 안 된다.
    """
    servers, conflicts, deleted, local_stale = {}, [], [], []
    for name in sorted(set(local) | set(repo) | set(base or {})):
        in_l, in_r = name in local, name in repo
        if base is None:
            if in_l:
                servers[name] = local[name]
            elif in_r:
                servers[name] = repo[name]
            continue
        in_s = name in base
        if in_l and not in_r and not in_s:                  # 1 로컬 신규
            servers[name] = local[name]
        elif not in_l and in_r and not in_s:                # 2 타 기기 추가
            servers[name] = repo[name]
        elif not in_l and in_r and in_s:                    # 3 로컬에서 삭제
            deleted.append(name)
        elif in_l and not in_r and in_s:
            if same(local[name], base[name]):               # 4 타 기기 삭제, 로컬 잔존
                local_stale.append(name)
            else:                                           # 5 로컬 수정 vs 리모트 삭제
                conflicts.append(name)
        elif in_l and in_r:
            if same(local[name], repo[name]):               # 6 in_sync
                servers[name] = local[name]
            elif in_s and same(repo[name], base[name]):     # 7 로컬만 변경
                servers[name] = local[name]
            elif in_s and same(local[name], base[name]):    # 8 타 기기 변경
                servers[name] = repo[name]
            else:                                           # 9 충돌
                conflicts.append(name)
                servers[name] = repo[name]
        # 10 L·R 모두 없고 base에만 존재 → no-op
    return {
        "servers": servers,
        "conflicts": conflicts,
        "deleted": deleted,
        "local_stale": local_stale,
    }
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 37 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): 서버 이름 키 단위 3-way 병합"
```

---

## Task 6: 멱등성·수렴 회귀 테스트

병합 규칙 자체는 Task 5에서 끝났다. 이 task는 **여러 번 실행했을 때 상태가 흔들리지 않는지**를
못 박는다. 새 production 코드는 없고 테스트만 추가한다. 두 회귀를 막는다.

1. base 게이트가 없으면 `local_stale` 서버가 다음 백업에서 되살아난다.
2. 게이트에 `conflicts`를 넣지 않으면 충돌이 2회차에 조용히 "로컬 승"으로 자동 해소된다.

**Files:**
- Modify: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
def apply_backup_round(local, repo, base):
    """SKILL.md backup 1회분: merge → 레포 반영 → 게이트 통과 시에만 base 갱신."""
    result = mc.merge(local, repo, base)
    new_repo = dict(result["servers"])
    blocked = bool(result["conflicts"]) or bool(result["local_stale"])
    new_base = base if blocked else dict(new_repo)
    return new_repo, new_base, result


def test_backup_is_stable_while_local_stale_unresolved():
    local, repo, base = {"X": A, "Y": B}, {"Y": B}, {"X": A, "Y": B}
    for _ in range(3):
        repo, base, result = apply_backup_round(local, repo, base)
        assert result["local_stale"] == ["X"]
        assert set(repo) == {"Y"}
        assert "X" in base


def test_restore_remove_converges_and_is_idempotent():
    local, repo, base = {"X": A, "Y": B}, {"Y": B}, {"X": A, "Y": B}
    repo, base, _ = apply_backup_round(local, repo, base)
    local.pop("X")
    base = dict(repo)
    repo, base, result = apply_backup_round(local, repo, base)
    assert result["local_stale"] == [] and result["conflicts"] == []
    assert set(repo) == {"Y"}
    repeat, _, _ = apply_backup_round(local, repo, base)
    assert repeat == repo


def test_restore_keep_returns_server_to_repo():
    local, repo, base = {"X": A, "Y": B}, {"Y": B}, {"X": A, "Y": B}
    repo, base, _ = apply_backup_round(local, repo, base)
    base = dict(repo)
    repo, base, _ = apply_backup_round(local, repo, base)
    assert set(repo) == {"X", "Y"}
    repeat, _, _ = apply_backup_round(local, repo, base)
    assert repeat == repo


def test_restore_later_does_not_resurrect():
    local, repo, base = {"X": A, "Y": B}, {"Y": B}, {"X": A, "Y": B}
    for _ in range(3):
        repo, base, result = apply_backup_round(local, repo, base)
    assert set(repo) == {"Y"}
    assert result["local_stale"] == ["X"]


def test_conflict_case9_does_not_auto_resolve():
    local, repo, base = {"Z": A}, {"Z": B}, {"Z": O}
    for _ in range(3):
        repo, base, result = apply_backup_round(local, repo, base)
        assert result["conflicts"] == ["Z"]
        assert repo == {"Z": B}


def test_conflict_case5_does_not_resurrect():
    local, repo, base = {"X": B}, {}, {"X": O}
    for _ in range(3):
        repo, base, result = apply_backup_round(local, repo, base)
        assert result["conflicts"] == ["X"]
        assert repo == {}
```

- [ ] **Step 2: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 43 passed

이 task는 이미 구현된 `merge`의 성질을 검증하므로 처음부터 통과한다.
**하나라도 실패하면 Task 5의 `merge`가 판정표와 어긋난 것이므로 Task 5로 돌아간다.**

- [ ] **Step 3: 게이트가 실제로 필요한지 확인 (수동 검증, 커밋하지 않음)**

`apply_backup_round`의 `blocked` 줄을 임시로 `blocked = False`로 바꾸고 실행한다.

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `test_restore_later_does_not_resurrect`와 `test_conflict_case9_does_not_auto_resolve`가 FAIL

확인 후 `blocked` 줄을 원래대로 되돌린다.

- [ ] **Step 4: 되돌린 뒤 다시 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: 43 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests/test_mcp_config.py
git commit -m "test(mcp): base 게이트 멱등성·수렴 회귀 테스트"
```

---

## Task 7: `restore_plan` — 복원 계획

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
def test_restore_plan_add_server_without_secrets():
    plan = mc.restore_plan({}, {"playwright": {"command": "npx"}}, {})
    assert plan["add"] == ["playwright"]
    assert plan["needs_secret"] == []


def test_restore_plan_needs_secret_for_redacted_server():
    backed = {"c7": {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}}
    plan = mc.restore_plan({}, backed, {})
    assert plan["needs_secret"] == ["c7"]
    assert plan["add"] == []


def test_restore_plan_in_sync_with_local_secret():
    """로컬에 실제 비밀, 레포에 SENTINEL → differs가 아니라 in_sync — 영구 미수렴 회귀."""
    local = {"c7": {"type": "http", "headers": {"K": "sk-real"}}}
    backed = mc.redact(local)
    plan = mc.restore_plan(local, backed, {})
    assert plan["in_sync"] == ["c7"]
    assert plan["differs"] == []


def test_restore_plan_differs_on_command_change():
    local = {"p": {"command": "npx", "args": ["a"]}}
    backed = {"p": {"command": "npx", "args": ["b"]}}
    assert mc.restore_plan(local, backed, {})["differs"] == ["p"]


def test_restore_plan_local_stale():
    assert mc.restore_plan({"X": A}, {}, {"X": A})["local_stale"] == ["X"]


def test_restore_plan_no_local_stale_without_base():
    assert mc.restore_plan({"X": A}, {}, None)["local_stale"] == []
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q`
기대: `AttributeError: module 'mcp_config' has no attribute 'restore_plan'`로 6건 FAIL

- [ ] **Step 3: 최소한의 implementation 작성**

`mcp_config.py`의 `merge` 아래에 추가한다.

```python
def restore_plan(local, backed, base):
    """복원 계획.

    diff와 동일하게 비교 직전 양쪽에 redact를 적용한다. 그러지 않으면
    로컬의 실제 비밀과 레포의 SENTINEL이 매번 differs로 보고된다.
    """
    L, R = redact(local), redact(backed)
    add, needs_secret, differs, in_sync = [], [], [], []
    for name in sorted(R):
        if name not in L:
            if secret_keys(R[name]):
                needs_secret.append(name)
            else:
                add.append(name)
        elif same(L[name], R[name]):
            in_sync.append(name)
        else:
            differs.append(name)
    local_stale = []
    if base is not None:
        local_stale = sorted(
            n for n in L if n not in R and n in base and same(L[n], base[n])
        )
    return {
        "add": add,
        "needs_secret": needs_secret,
        "differs": differs,
        "in_sync": in_sync,
        "local_stale": local_stale,
    }
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 81 passed (기존 32 + 신규 49)

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): 복원 계획 산출 (마스킹 비교, local_stale 분류)"
```

---

## Task 8: `collect_mcp.py` — backup 스크립트, `parse_mcp.py` 삭제

**Files:**
- Create: `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py`
- Delete: `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_scripts.py`를 새로 만든다.

```python
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-status", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
import collect_mcp
import mcp_config as mc
import sync_state as ss


def make_claude_json(tmp_path, servers):
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return str(p)


def test_collect_writes_v2_and_masks_secrets(tmp_path):
    claude_json = make_claude_json(tmp_path, {
        "playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]},
        "context7": {"type": "http", "url": "u", "headers": {"K": "sk-secret"}},
    })
    repo = tmp_path / "repo"
    repo.mkdir()

    result = collect_mcp.collect(str(repo), claude_json, base_dir=str(tmp_path / "base"))

    assert result["written"] is True
    assert result["servers"] == ["context7", "playwright"]
    assert result["base_update_allowed"] is True
    written = mc.load_backup(str(repo / "mcp-servers.json"))
    assert written["playwright"]["args"] == ["@playwright/mcp@latest"]
    assert written["context7"]["headers"] == {"K": mc.SENTINEL}


def test_collect_skips_when_claude_json_unreadable(tmp_path):
    """읽기 실패 시 레포 파일을 건드리지 않는다 — 전체 삭제 방지."""
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_file = repo / "mcp-servers.json"
    mc.dump_backup({"keep": {"command": "x"}}, str(repo_file))
    before = repo_file.read_bytes()

    result = collect_mcp.collect(
        str(repo), str(tmp_path / "nope.json"), base_dir=str(tmp_path / "base")
    )

    assert result["written"] is False
    assert "skipped" in result
    assert repo_file.read_bytes() == before


def test_collect_blocks_base_update_on_local_stale(tmp_path):
    claude_json = make_claude_json(tmp_path, {"X": {"command": "a"}})
    repo = tmp_path / "repo"
    repo.mkdir()
    base_dir = str(tmp_path / "base")
    ss.write_base(
        mc.BACKUP_RELPATH,
        json.dumps({"version": 2, "servers": {"X": {"command": "a"}}}).encode("utf-8"),
        base_dir=base_dir,
    )
    mc.dump_backup({}, str(repo / "mcp-servers.json"))

    result = collect_mcp.collect(str(repo), claude_json, base_dir=base_dir)

    assert result["local_stale"] == ["X"]
    assert result["base_update_allowed"] is False
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q`
기대: `ModuleNotFoundError: No module named 'collect_mcp'`로 collection error

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py`를 새로 만든다.

```python
#!/usr/bin/env python3
"""~/.claude.json의 user 스코프 MCP 서버를 레포 mcp-servers.json으로 병합 저장한다.

사용: collect_mcp.py <repo_path>
JSON 출력:
  {"written": true, "servers": [...], "conflicts": [...], "deleted": [...],
   "local_stale": [...], "base_update_allowed": bool}
  또는 {"written": false, "skipped": "<이유>"}

`claude mcp list`는 호출하지 않는다 — 출력이 손실 압축이고 실행 디렉토리에 의존한다.
base 갱신은 푸시 성공 이후 SKILL.md 흐름에서 update_base.py로 수행한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402


def collect(repo_path, claude_json_path=None, base_dir=ss.BASE_DIR):
    """병합 결과를 레포에 쓰고 요약을 반환한다.

    ~/.claude.json을 읽지 못하면 아무것도 쓰지 않는다. 그 상태로 병합하면
    로컬이 빈 것으로 오인되어 레포의 모든 서버가 삭제될 수 있다.
    """
    try:
        local = mc.redact(mc.read_local_servers(claude_json_path))
    except mc.LocalConfigUnavailable as e:
        return {"written": False, "skipped": str(e)}

    repo_file = os.path.join(repo_path, mc.BACKUP_RELPATH)
    repo = mc.load_backup(repo_file)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))

    result = mc.merge(local, repo, base)
    mc.dump_backup(result["servers"], repo_file)
    return {
        "written": True,
        "servers": sorted(result["servers"]),
        "conflicts": result["conflicts"],
        "deleted": result["deleted"],
        "local_stale": result["local_stale"],
        "base_update_allowed": not result["conflicts"] and not result["local_stale"],
    }


def main():
    if len(sys.argv) < 2:
        print("사용: collect_mcp.py <repo_path>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(collect(sys.argv[1]), ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q`
기대: 3 passed

- [ ] **Step 5: `parse_mcp.py` 삭제**

```bash
git rm plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py
```

- [ ] **Step 6: 남은 참조가 없는지 확인**

실행: `grep -rn "parse_mcp" --include='*.py' --include='*.md' --include='*.sh' plugins docs README.md README.ko.md`
기대: SKILL.md의 6단계 한 줄만 남는다(Task 11에서 제거). Python 파일에는 남지 않아야 한다.

- [ ] **Step 7: Commit**

```bash
git add plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "feat(backup): collect_mcp.py 도입, 정규식 파서 parse_mcp.py 제거"
```

---

## Task 9: `compare_mcp.py` 재작성

**Files:**
- Modify: `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`test_mcp_scripts.py` 상단 import에 `import compare_mcp`를 추가하고, 파일 끝에 추가한다.

```python
def test_compare_reports_identical():
    servers = {"p": {"command": "npx"}}
    assert compare_mcp.render(servers, servers) == ["", "MCP 서버: 동일"]


def test_compare_converges_with_redacted_repo():
    """로컬 평문 vs 레포 마스킹이 '동일'로 수렴한다 — Bug #2 회귀."""
    local = {"c7": {"headers": {"K": "sk-real"}}}
    assert compare_mcp.render(local, mc.redact(local)) == ["", "MCP 서버: 동일"]


def test_compare_reports_three_categories():
    lines = compare_mcp.render(
        {"onlyLocal": {"command": "a"}, "both": {"command": "x"}},
        {"onlyRepo": {"command": "b"}, "both": {"command": "y"}},
    )
    assert "  + 레포에만: onlyRepo" in lines
    assert "  - 로컬에만: onlyLocal" in lines
    assert "  ~ 설정 다름: both" in lines
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q`
기대: `AttributeError: module 'compare_mcp' has no attribute 'render'`로 3건 FAIL

(기존 `compare_mcp.py`는 import 시점에 stdin을 읽는 모듈 레벨 코드라 collection이 멈출 수 있다.
Step 3에서 `main()` 가드로 감싸면 해소된다.)

- [ ] **Step 3: `compare_mcp.py` 전체를 다음으로 교체**

```python
#!/usr/bin/env python3
"""로컬 user 스코프 MCP 서버와 레포 mcp-servers.json의 차이를 출력한다.

사용: compare_mcp.py <mcp_servers_json_path>
`claude mcp list`를 호출하지 않는다 — 데이터 소스는 ~/.claude.json이다.
stdin을 읽지 않는다.
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402


def render(local, backed):
    """출력할 줄 목록. 비교는 mcp_config.diff가 담당한다(양쪽 마스킹 후 비교)."""
    result = mc.diff(local, backed)
    if not any(result.values()):
        return ["", "MCP 서버: 동일"]
    lines = ["", "MCP 서버 차이:"]
    lines += ["  + 레포에만: " + n for n in result["only_repo"]]
    lines += ["  - 로컬에만: " + n for n in result["only_local"]]
    lines += ["  ~ 설정 다름: " + n for n in result["changed"]]
    return lines


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else mc.BACKUP_RELPATH
    try:
        local = mc.read_local_servers()
    except mc.LocalConfigUnavailable as e:
        print("\nMCP 서버: 확인 불가 — %s" % e)
        return
    print("\n".join(render(local, mc.load_backup(path))))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 87 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "refactor(status): compare_mcp를 mcp_config.diff 기반으로 재작성"
```

---

## Task 10: `plan_mcp.py` — restore 스크립트

**Files:**
- Create: `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`test_mcp_scripts.py` 상단 import에 `import plan_mcp`를 추가하고, 파일 끝에 추가한다.

```python
def test_plan_mcp_builds_add_json(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mc.dump_backup(
        {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}},
        str(repo / "mcp-servers.json"),
    )
    claude_json = make_claude_json(tmp_path, {})

    plan = plan_mcp.build(str(repo), claude_json, base_dir=str(tmp_path / "base"))

    assert plan["add"] == ["playwright"]
    assert json.loads(plan["add_json"]["playwright"]) == {
        "command": "npx",
        "args": ["@playwright/mcp@latest"],
    }


def test_plan_mcp_marks_secret_keys(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    mc.dump_backup(
        {"c7": {"type": "http", "url": "u", "headers": {"CONTEXT7_API_KEY": mc.SENTINEL}}},
        str(repo / "mcp-servers.json"),
    )
    claude_json = make_claude_json(tmp_path, {})

    plan = plan_mcp.build(str(repo), claude_json, base_dir=str(tmp_path / "base"))

    assert plan["needs_secret"] == ["c7"]
    assert plan["secret_keys"]["c7"] == [("headers", "CONTEXT7_API_KEY")]


def test_plan_mcp_unavailable_when_claude_json_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    plan = plan_mcp.build(
        str(repo), str(tmp_path / "nope.json"), base_dir=str(tmp_path / "base")
    )
    assert "unavailable" in plan
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q`
기대: `ModuleNotFoundError: No module named 'plan_mcp'`로 collection error

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py`를 새로 만든다.

```python
#!/usr/bin/env python3
"""MCP 서버 복원 계획을 JSON으로 출력한다.

사용: plan_mcp.py <repo_path>
JSON 출력:
  {"add": [...], "needs_secret": [...], "differs": [...], "in_sync": [...],
   "local_stale": [...], "add_json": {name: "<json 문자열>"},
   "secret_keys": {name: [[field, key], ...]}}
  또는 {"unavailable": "<이유>"}

add_json의 값은 `claude mcp add-json "<name>" '<json>' --scope user`에 그대로 넘긴다.
needs_secret 서버는 add_json 안의 "<REDACTED>"를 사용자 입력으로 바꾼 뒤 등록한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402


def build(repo_path, claude_json_path=None, base_dir=ss.BASE_DIR):
    """복원 계획을 만든다. 등록은 SKILL.md 흐름에서 수행한다."""
    try:
        local = mc.read_local_servers(claude_json_path)
    except mc.LocalConfigUnavailable as e:
        return {"unavailable": str(e)}

    backed = mc.load_backup(os.path.join(repo_path, mc.BACKUP_RELPATH))
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))

    plan = mc.restore_plan(local, backed, base)
    targets = plan["add"] + plan["needs_secret"]
    plan["add_json"] = {
        n: json.dumps(backed[n], ensure_ascii=False, sort_keys=True) for n in targets
    }
    plan["secret_keys"] = {n: mc.secret_keys(backed[n]) for n in plan["needs_secret"]}
    return plan


def main():
    if len(sys.argv) < 2:
        print("사용: plan_mcp.py <repo_path>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(build(sys.argv[1]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 90 passed

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "feat(restore): add-json 기반 MCP 복원 계획 스크립트"
```

---

## Task 11: SKILL.md 3개 갱신

스크립트가 바뀌었으므로 스킬의 실행 절차도 함께 바꾼다. 여기까지 오면 `claude mcp list`
호출이 저장소에서 완전히 사라진다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md`
- Modify: `plugins/claude-sync/skills/sync-status/SKILL.md`
- Modify: `plugins/claude-sync/skills/sync-restore/SKILL.md`

- [ ] **Step 1: sync-backup SKILL.md — 동기화 대상 표 정정**

찾기:
```
| `claude mcp list` → 추출 | `mcp-servers.json` | MCP 서버 이름과 URL |
```
바꾸기:
```
| `~/.claude.json` (user 스코프) → 추출 | `mcp-servers.json` | MCP 서버 설정, 비밀 값은 마스킹 |
```

- [ ] **Step 2: sync-backup SKILL.md — 6단계 전체 교체**

찾기(6단계 제목부터 코드블록까지):
```
### 6. mcp-servers.json 생성

`claude mcp list`의 출력을 파싱하여 MCP 서버 목록을 추출한다. 복원에 필요한 name, url, type만 저장한다.

```bash
claude mcp list 2>/dev/null | python3 $SYNC_SCRIPTS/parse_mcp.py mcp-servers.json
```
```
바꾸기:
````
### 6. mcp-servers.json 생성

`~/.claude.json`의 user 스코프 `mcpServers`를 읽어 레포의 `mcp-servers.json`에 병합한다.
`claude mcp list`는 호출하지 않는다 — 출력이 손실 압축이고 실행 디렉토리에 따라 결과가 달라진다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" > /tmp/claude-sync-mcp.json
cat /tmp/claude-sync-mcp.json
```

출력 JSON에 따라 처리한다:

- `"written": false` — `skipped` 사유를 사용자에게 알리고 **MCP 단계만** 건너뛴다. 파일 백업은 계속 진행한다.
- `conflicts` — 해당 서버 이름과 함께 "`/sync-restore`를 먼저 실행하세요"를 안내한다.
- `local_stale` — "다른 기기에서 삭제된 서버가 로컬에 남아 있습니다. `/sync-restore`에서 정리하세요"를 안내한다.
- `deleted` — 이 기기에서 지운 서버가 레포에서도 제거됐다는 뜻이므로 결과 보고에 포함한다.
- `base_update_allowed` — 11단계에서 사용한다.

계정 레벨 커넥터(`claude.ai *`), 플러그인 제공 서버(`plugin:*`), 프로젝트/local 스코프 서버는
`~/.claude.json`의 user 스코프에 존재하지 않으므로 별도 필터 없이 제외된다.
````

- [ ] **Step 3: sync-backup SKILL.md — 11단계에 MCP base 갱신 추가**

11단계 본문 마지막(“…push 실패 후 실행되지 않는다.”) 바로 뒤에 다음을 덧붙인다.

````
`mcp-servers.json`의 base는 조건이 하나 더 있다. 푸시에 성공했고 **6단계 출력의
`base_update_allowed`가 참일 때만** 갱신한다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_BASE_OK=$(python3 -c "import json; print(json.load(open('/tmp/claude-sync-mcp.json')).get('base_update_allowed', False))")
if [ "$MCP_BASE_OK" = "True" ]; then
  python3 "$SYNC_SCRIPTS/update_base.py" "$SYNC_REPO" mcp-servers.json
fi
```

충돌이나 `local_stale`이 남은 상태에서 base를 갱신하면, 다음 백업이 그것을 "로컬만 변경"으로
오판한다. 그러면 사용자가 아무것도 해소하지 않았는데 충돌이 조용히 로컬 승으로 바뀌거나,
다른 기기가 삭제한 서버가 되살아난다.
````

- [ ] **Step 4: sync-status SKILL.md — MCP 비교 블록 교체**

찾기:
```
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  claude mcp list 2>/dev/null | python3 $SYNC_SCRIPTS/compare_mcp.py "$SYNC_REPO/mcp-servers.json"
fi
```
바꾸기:
```
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"
fi
```

- [ ] **Step 5: sync-status SKILL.md — 제외 대상 설명 정정**

찾기:
```
이 명령은 아무것도 바꾸지 않는다. `plugin:`으로 시작하는 MCP 서버는 플러그인이 제공하므로 비교에서 제외한다.
```
바꾸기:
```
이 명령은 아무것도 바꾸지 않는다. MCP 비교의 데이터 소스는 `~/.claude.json`의 user 스코프이므로,
계정 레벨 커넥터(`claude.ai *`)·플러그인 제공 서버(`plugin:*`)·프로젝트/local 스코프 서버는
비교 대상에 들어오지 않는다. `~ 설정 다름`은 이름은 같고 설정이 달라진 서버다.
```

- [ ] **Step 6: sync-restore SKILL.md — 6단계 전체 교체**

찾기(“### 6. MCP 서버 복원 (additive, plugin: 제외)” 제목부터
“`claude mcp` 명령어가 실패하면 `mcp-servers.json` 내용을 보여주고 수동 등록을 안내한다.”까지)
바꾸기:

````
### 6. MCP 서버 복원 (additive)

레포 `mcp-servers.json`과 로컬 `~/.claude.json`의 user 스코프를 비교해 복원 계획을 얻는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/plan_mcp.py" "$SYNC_REPO" > /tmp/claude-sync-mcp-plan.json
cat /tmp/claude-sync-mcp-plan.json
```

`unavailable` 키가 있으면 사유를 알리고 이 단계를 건너뛴다.

#### 6-1. 비밀이 없는 서버 추가 (`add`)

`add_json`의 값을 그대로 넘긴다. 이름에 공백이 있을 수 있으므로 반드시 인용한다.

```bash
claude mcp add-json "<name>" '<add_json 값>' --scope user
```

#### 6-2. 비밀이 필요한 서버 (`needs_secret`)

`secret_keys`에 어떤 필드의 어떤 키가 필요한지 들어 있다. 사용자에게 값을 물어
`add_json` 안의 `"<REDACTED>"` 자리를 채운 뒤 위와 같은 형식으로 등록한다.
사용자가 건너뛰겠다고 하면 **등록하지 않는다.** 인증이 깨진 서버를 만들지 않는 편이 낫다.

#### 6-3. 로컬에만 남은 서버 (`local_stale`)

다른 기기에서 삭제됐는데 이 기기에 남아 있는 서버다. 사용자에게 세 선택지를 제시하고 그대로 수행한다.

- **제거**: `claude mcp remove "<name>" -s user`
- **유지**: 그대로 둔다. 다음 `/sync-backup`에서 레포로 되돌아간다.
- **나중에**: 아무것도 하지 않는다. 다음 restore에서 다시 묻는다.

#### 6-4. 설정이 다른 서버 (`differs`)

restore는 additive이므로 덮어쓰지 않는다. 차이만 알리고
"로컬 설정을 레포에 올리려면 `/sync-backup`"을 안내한다.

#### 6-5. base 갱신

`local_stale`을 **"나중에"로 미룬 서버가 하나도 없을 때만** 실행한다.

```bash
python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" mcp-servers.json
```

미룬 서버가 있는데 base를 갱신하면 다음 백업이 그 서버를 "로컬 신규"로 오판해 레포에 되살린다.

개별 서버 등록이 실패하면 **그 서버만 실패로 기록하고 나머지는 계속 진행한다.**
`claude mcp` 명령 자체가 없거나 전부 실패하면 계획 JSON을 보여주고 수동 등록을 안내한다.
````

- [ ] **Step 7: `claude mcp list` 참조가 사라졌는지 확인**

실행: `grep -rn "claude mcp list\|parse_mcp" plugins README.md README.ko.md`
기대: 출력 없음

- [ ] **Step 8: 전체 테스트가 여전히 통과하는지 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 90 passed

- [ ] **Step 9: Commit**

```bash
git add plugins/claude-sync/skills
git commit -m "docs(skills): MCP 절차를 파일 소스·add-json·base 게이트 기준으로 재작성"
```

---

## Task 12: 사용자 문서 정정

문서가 지키지 못하는 보장을 내걸고 있던 부분을 바로잡는다.
`plugins.json`은 이번에 고치지 않으므로 **사실대로 예외를 명시**한다.

**Files:**
- Modify: `README.md`, `README.ko.md`
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md`, `backup-readme.ko.md`

- [ ] **Step 1: README.ko.md — 동기화 대상 정정**

찾기:
```
- `claude mcp list` -> `mcp-servers.json` — MCP 서버 목록 (이름, URL, 타입)
```
바꾸기:
```
- `~/.claude.json` (user 스코프) -> `mcp-servers.json` — MCP 서버 설정 (`command`/`args`/`env`/`headers` 포함, 비밀 값은 마스킹)
```

- [ ] **Step 2: README.ko.md — 안전 장치의 보장 범위 정정**

찾기:
```
- **충돌 감지**: 마지막 공유 base 이후 양쪽에서 변경된 파일만 충돌로 표시하며, 로컬 파일은 절대 자동으로 덮어쓰지 않습니다.
```
바꾸기:
```
- **충돌 감지**: 마지막 공유 base 이후 양쪽에서 변경된 파일만 충돌로 표시하며, 로컬 파일은 절대 자동으로 덮어쓰지 않습니다.
- **MCP 서버는 서버 이름 단위로 3-way 병합됩니다.** 다른 기기가 추가한 서버가 백업에서 사라지지 않고, 이 기기에서 지운 서버는 레포에도 반영됩니다. 다른 기기가 삭제했는데 로컬에 남아 있는 서버는 `/sync-restore`에서 제거 / 유지 / 나중에 중 하나를 고르게 됩니다.
- **비밀은 백업되지 않습니다.** MCP 서버의 `headers`/`env` 값은 `<REDACTED>`로 저장되고 키 이름만 남습니다. 새 기기에서 복원할 때 값을 입력받습니다. 그래서 **비밀 값만 바뀐 변경은 동기화되지 않습니다.**
- **예외 — `plugins.json`은 3-way 대상이 아닙니다.** 매 백업마다 로컬 `settings.json`에서 새로 생성되어 통째로 덮어쓰입니다. 여러 기기를 쓰는 경우, 다른 기기에만 설치된 플러그인이 백업에서 빠질 수 있습니다(git 히스토리에는 남고, 복원은 additive이므로 로컬에서 삭제되지는 않습니다).
```

- [ ] **Step 3: README.md — 같은 두 곳을 영어로 정정**

찾기:
```
- `claude mcp list` -> `mcp-servers.json` — MCP server list (name, URL, type)
```
바꾸기:
```
- `~/.claude.json` (user scope) -> `mcp-servers.json` — MCP server configs (including `command`/`args`/`env`/`headers`; secret values are masked)
```

찾기:
```
- **Conflict detection**: Files changed on both sides since the last known base are flagged as conflicts; local copies are never silently overwritten.
```
바꾸기:
```
- **Conflict detection**: Files changed on both sides since the last known base are flagged as conflicts; local copies are never silently overwritten.
- **MCP servers are merged 3-way, per server name.** Servers added on another machine are not dropped from the backup, and servers you delete locally are removed from the repo too. A server another machine deleted but that still exists locally is surfaced during `/sync-restore` with three choices: remove / keep / decide later.
- **Secrets are not backed up.** `headers`/`env` values of MCP servers are stored as `<REDACTED>`, keeping only the key names; you are prompted for the values when restoring on a new machine. As a consequence, **a change to a secret value alone is never synced.**
- **Exception — `plugins.json` is not 3-way merged.** It is regenerated from the local `settings.json` on every backup and overwrites the repo copy wholesale. With multiple machines, plugins installed only on another machine may disappear from the backup (they remain in git history, and restore is additive so they are never removed locally).
```

- [ ] **Step 4: 백업 레포 README 2개 — MCP 항목 정정**

`backup-readme.md`에서 찾기:
```
- `mcp-servers.json` — MCP server list (name, URL, type)
```
바꾸기:
```
- `mcp-servers.json` — MCP server configs from the user scope of `~/.claude.json`. Secret values in `headers`/`env` are stored as `<REDACTED>`; `/sync-restore` asks you for them. Account-level `claude.ai` connectors and plugin-provided servers are intentionally excluded — they cannot be restored with `claude mcp add-json`. **Note: only `headers` and `env` are masked.** If a server passes its API key through `args` (`--api-key=...`) or a `url` query string, that value is backed up in cleartext — keep the backup repo private.
```

`backup-readme.ko.md`에서 찾기:
```
- `mcp-servers.json` — MCP 서버 목록 (이름, URL, 타입)
```
바꾸기:
```
- `mcp-servers.json` — `~/.claude.json`의 user 스코프 MCP 서버 설정. `headers`/`env`의 비밀 값은 `<REDACTED>`로 저장되며 `/sync-restore`가 값을 물어봅니다. 계정 레벨 `claude.ai` 커넥터와 플러그인 제공 서버는 `claude mcp add-json`으로 복원할 수 없으므로 의도적으로 제외합니다. **주의: 마스킹 대상은 `headers`와 `env`뿐입니다.** API 키를 `args`(`--api-key=...`)나 `url` 쿼리스트링으로 전달하는 서버가 있다면 그 값은 평문으로 백업되므로, 백업 레포는 private으로 두세요.
```

- [ ] **Step 5: Commit**

```bash
git add README.md README.ko.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.ko.md
git commit -m "docs: MCP 동기화 범위·비밀 처리·plugins.json 예외 명시"
```

---

## Task 13: 버전 3.0.0과 최종 검증

`mcp-servers.json`이 배열에서 객체로 바뀌므로 구버전 `compare_mcp.py`는
`[s["name"] for s in backed]`에서 `TypeError`로 죽는다. 역호환이 없으므로 MAJOR를 올린다.

**Files:**
- Modify: `plugins/claude-sync/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: 버전 올리기**

`plugins/claude-sync/.claude-plugin/plugin.json`에서 `"version": "2.0.0"` → `"version": "3.0.0"`
`.claude-plugin/marketplace.json`에서 `"version": "2.0.0"` → `"version": "3.0.0"`

확인: `grep -rn '"version"' .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json`
기대: 두 곳 모두 `3.0.0`

- [ ] **Step 2: 전체 테스트**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 90 passed

- [ ] **Step 3: 실환경 스모크 — 백업 산출물 확인 (레포에 쓰지 않는다)**

```bash
SMOKE=$(mktemp -d)
python3 plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py "$SMOKE"
cat "$SMOKE/mcp-servers.json"
```

기대:
- `written: true`
- `servers`에 `~/.claude.json`의 user 스코프 서버가 **전부** 들어 있다(공백이 든 stdio 명령 포함).
- `claude.ai `로 시작하는 이름과 `plugin:`으로 시작하는 이름은 **없다.**
- `headers`/`env`가 있는 서버는 값이 `"<REDACTED>"`이고 키 이름은 남아 있다.
- stdio 서버에 `command`와 `args`가 그대로 있다.

- [ ] **Step 4: 실환경 스모크 — status 수렴 확인**

```bash
python3 plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py "$SMOKE/mcp-servers.json"
```

기대: `MCP 서버: 동일`
(방금 만든 백업과 로컬이 같으므로 차이가 없어야 한다. 여기서 차이가 나오면
마스킹 비교가 어딘가에서 빠진 것이다 — Bug #2의 재발이다.)

- [ ] **Step 5: 실환경 스모크 — cwd 비의존 확인**

```bash
SMOKE2=$(mktemp -d)
(cd /tmp && python3 /Users/bran/personal/claude-sync/plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py "$SMOKE2" > /dev/null)
diff "$SMOKE/mcp-servers.json" "$SMOKE2/mcp-servers.json" && echo "cwd 비의존 OK"
```

기대: 차이 없음 + `cwd 비의존 OK` (Bug #5 확인)

- [ ] **Step 6: 실환경 스모크 — 복원 계획 확인**

```bash
python3 plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py "$SMOKE"
```

기대: `add`/`needs_secret`이 비어 있고 모든 서버가 `in_sync`에 있다
(로컬과 방금 만든 백업이 같으므로). `differs`가 비어 있어야 한다 —
비어 있지 않으면 `restore_plan`의 마스킹 비교가 빠진 것이다.

- [ ] **Step 7: 스모크 디렉토리 정리**

```bash
rm -rf "$SMOKE" "$SMOKE2"
```

- [ ] **Step 8: Commit**

```bash
git add .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
git commit -m "chore: 버전 3.0.0 (MAJOR — mcp-servers.json 스키마 변경으로 역호환 없음)"
```

---

## 배포 (사용자 승인 후)

푸시는 외부 동작이므로 **사용자에게 확인받은 뒤에만** 실행한다.

```bash
git push -u origin fix/mcp-config-source
```

머지 후 플러그인 갱신:

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync
ls ~/.claude/plugins/cache/claude-sync/claude-sync/
```
기대: `3.0.0` 디렉토리가 생긴다.

**여러 기기를 쓰는 경우 주의:** `mcp-servers.json`이 v2 객체가 되면 구버전(2.0.0 이하)의
`compare_mcp.py`는 `TypeError`로 죽는다. **모든 기기를 3.0.0으로 올린 뒤에 첫 백업을 실행한다.**
