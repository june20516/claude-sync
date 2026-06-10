# git-like 동기화 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** claude-sync의 비교·복원 로직을 mtime 기반에서 내용 해시 3-way(git-like)로 바꾸고, additive 항상 적용·충돌 격리·해소 UX·순환 정합성·pull-only·`plugin:` MCP 제외를 구현한다.

**Architecture:** 순수 함수 코어를 `lib/sync_state.py`로 분리해 단위 테스트하고(해싱·3-way 분류·git merge-file 머지·base 블롭 I/O), 세 스킬의 스크립트는 이 코어를 import하는 얇은 CLI 래퍼로 만든다. 상호작용(충돌 해소·가드)은 각 SKILL.md 산문이 에이전트를 통해 수행한다. base(=마지막 reconcile한 remote 내용)는 기기 로컬 `~/.claude/.sync-state/base/<relpath>`에 보관한다.

**Tech Stack:** Python 3 (stdlib only: hashlib, subprocess, tempfile, os, json), pytest, git(`git merge-file`), `claude` CLI.

**Spec:** `docs/superpowers/specs/2026-06-10-git-like-sync-design.md`

**작업 브랜치:** `git-like-sync` (이미 분기됨)

**경로 표기:** 레포 루트 = `~/dev/claude-sync`. 플러그인 루트 = `plugins/claude-sync/`. 이하 경로는 레포 루트 기준.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `plugins/claude-sync/lib/sync_state.py` | (신규) 순수 코어: 해싱, 3-way `classify`, `three_way_merge`(git merge-file), base 블롭 I/O, 동기화 대상 파일 열거 |
| `plugins/claude-sync/tests/test_sync_state.py` | (신규) 코어 단위 테스트 |
| `plugins/claude-sync/tests/conftest.py` | (신규) `lib`를 sys.path에 추가 |
| `plugins/claude-sync/skills/sync-status/scripts/check_status.py` | (재작성) 코어로 3-way 분류 보고. mtime 제거 |
| `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py` | (수정) `plugin:` 서버 제외 |
| `plugins/claude-sync/skills/sync-restore/scripts/analyze_conflicts.py` | (재작성→`reconcile_restore.py`) 분류+비대화 적용+충돌 JSON 출력 |
| `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py` | (수정) `plugin:` 서버 제외 |
| `plugins/claude-sync/skills/sync-backup/scripts/generate_metadata.py` | (수정) mtime→sha256 |
| `plugins/claude-sync/skills/sync-backup/scripts/reconcile_backup.py` | (신규) 파일별 push 판정/적용, push-rejected 가드 |
| `plugins/claude-sync/skills/sync-restore/SKILL.md` | (재작성) pull-only·additive·충돌 UX·base 갱신·`plugin:` 제외 |
| `plugins/claude-sync/skills/sync-backup/SKILL.md` | (수정) per-file·push-rejected·`pull_only` 가드·base 갱신 |
| `plugins/claude-sync/skills/sync-status/SKILL.md` | (수정) 새 카테고리 보고 |
| `.claude-plugin/marketplace.json`, `plugins/claude-sync/.claude-plugin/plugin.json` | version 1.0.0→1.0.1 |
| `README.md`, `README.ko.md` | 동작 모델 갱신 |

---

## Phase 1 — 순수 코어 + 테스트

### Task 1: 테스트 하니스 + 해싱/ base I/O

**Files:**
- Create: `plugins/claude-sync/lib/sync_state.py`
- Create: `plugins/claude-sync/tests/conftest.py`
- Create: `plugins/claude-sync/tests/test_sync_state.py`

- [ ] **Step 1: conftest로 lib 경로 등록**

`plugins/claude-sync/tests/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
```

- [ ] **Step 2: 해싱/base I/O 실패 테스트 작성**

`plugins/claude-sync/tests/test_sync_state.py`:
```python
import sync_state as ss


def test_content_hash_stable():
    assert ss.content_hash(b"hello") == ss.content_hash(b"hello")
    assert ss.content_hash(b"a") != ss.content_hash(b"b")


def test_file_hash_missing_returns_none(tmp_path):
    assert ss.file_hash(str(tmp_path / "nope")) is None


def test_file_hash_matches_content(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"data")
    assert ss.file_hash(str(p)) == ss.content_hash(b"data")


def test_base_roundtrip(tmp_path):
    bd = str(tmp_path / "base")
    ss.write_base("agents/x.md", b"hello", base_dir=bd)
    assert ss.read_base("agents/x.md", base_dir=bd) == b"hello"
    assert ss.base_hash("agents/x.md", base_dir=bd) == ss.content_hash(b"hello")


def test_base_missing_returns_none(tmp_path):
    bd = str(tmp_path / "base")
    assert ss.read_base("nope.md", base_dir=bd) is None
    assert ss.base_hash("nope.md", base_dir=bd) is None


def test_write_base_none_deletes(tmp_path):
    bd = str(tmp_path / "base")
    ss.write_base("a.md", b"x", base_dir=bd)
    ss.write_base("a.md", None, base_dir=bd)
    assert ss.read_base("a.md", base_dir=bd) is None
```

- [ ] **Step 3: 실패 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'sync_state'`)

- [ ] **Step 4: sync_state.py 1차 구현 (해싱/base I/O)**

`plugins/claude-sync/lib/sync_state.py`:
```python
#!/usr/bin/env python3
"""claude-sync 공용 코어.

mtime을 일절 쓰지 않는다. 모든 판단은 내용 sha256과
base(이 기기가 마지막으로 reconcile한 remote 내용) 기준이다.
"""
import hashlib
import os
import subprocess
import tempfile

SYNC_STATE_DIR = os.path.expanduser("~/.claude/.sync-state")
BASE_DIR = os.path.join(SYNC_STATE_DIR, "base")


def content_hash(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    """파일의 sha256 hex. 없으면 None."""
    try:
        with open(path, "rb") as f:
            return content_hash(f.read())
    except FileNotFoundError:
        return None


def base_blob_path(relpath, base_dir=BASE_DIR):
    return os.path.join(base_dir, relpath)


def read_base(relpath, base_dir=BASE_DIR):
    """base(마지막 reconcile한 remote) 내용. 없으면 None."""
    try:
        with open(base_blob_path(relpath, base_dir), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def base_hash(relpath, base_dir=BASE_DIR):
    data = read_base(relpath, base_dir)
    return content_hash(data) if data is not None else None


def write_base(relpath, data, base_dir=BASE_DIR):
    """base 블롭 기록(불변식 갱신). data가 None이면 삭제."""
    path = base_blob_path(relpath, base_dir)
    if data is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
```

- [ ] **Step 5: 통과 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/lib/sync_state.py plugins/claude-sync/tests/
git commit -m "feat(lib): sync_state 코어 - 해싱과 base 블롭 I/O"
```

### Task 2: 3-way 분류 `classify`

**Files:**
- Modify: `plugins/claude-sync/lib/sync_state.py`
- Modify: `plugins/claude-sync/tests/test_sync_state.py`

- [ ] **Step 1: classify 실패 테스트 추가**

`tests/test_sync_state.py` 끝에 추가:
```python
def test_classify_repo_only():
    assert ss.classify(None, "r", None, local_exists=False, repo_exists=True) == "repo_only"


def test_classify_local_only():
    assert ss.classify("l", None, None, local_exists=True, repo_exists=False) == "local_only"


def test_classify_in_sync_equal():
    assert ss.classify("a", "a", "x", True, True) == "in_sync"


def test_classify_local_ahead():
    # 로컬만 변경(L!=S), remote는 그대로(R==S)
    assert ss.classify("L", "S", "S", True, True) == "local_ahead"


def test_classify_fast_forward():
    # remote만 변경(R!=S), 로컬은 그대로(L==S)
    assert ss.classify("S", "R", "S", True, True) == "fast_forward"


def test_classify_conflict_both_changed():
    assert ss.classify("L", "R", "S", True, True) == "conflict"


def test_classify_conflict_no_base():
    # base 없음 + 둘 다 존재 + 다름 → conflict
    assert ss.classify("L", "R", None, True, True) == "conflict"
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: FAIL (`AttributeError: module 'sync_state' has no attribute 'classify'`)

- [ ] **Step 3: classify 구현**

`lib/sync_state.py`에 추가:
```python
def classify(local_hash, repo_hash, seen_hash, local_exists, repo_exists):
    """3-way 분류.

    반환: in_sync | repo_only | local_only | local_ahead | fast_forward | conflict
    seen_hash는 base가 없으면 None.
    """
    if not repo_exists:
        return "local_only"
    if not local_exists:
        return "repo_only"
    if local_hash == repo_hash:
        return "in_sync"
    changed_local = local_hash != seen_hash
    changed_remote = repo_hash != seen_hash
    if changed_local and not changed_remote:
        return "local_ahead"
    if changed_remote and not changed_local:
        return "fast_forward"
    if changed_local and changed_remote:
        return "conflict"
    return "in_sync"  # L==S and R==S면 L==R이라 도달 불가 — 방어
```

- [ ] **Step 4: 통과 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/lib/sync_state.py plugins/claude-sync/tests/test_sync_state.py
git commit -m "feat(lib): 내용 해시 3-way classify"
```

### Task 3: 3-way 머지 `three_way_merge`

**Files:**
- Modify: `plugins/claude-sync/lib/sync_state.py`
- Modify: `plugins/claude-sync/tests/test_sync_state.py`

- [ ] **Step 1: 머지 실패 테스트 추가**

`tests/test_sync_state.py` 끝에 추가:
```python
def test_merge_clean_non_overlapping():
    base = b"a\nb\nc\nd\ne\n"
    local = b"a\nB\nc\nd\ne\n"   # 2번 줄 변경
    repo = b"a\nb\nc\nD\ne\n"    # 4번 줄 변경
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts == 0
    assert merged == b"a\nB\nc\nD\ne\n"


def test_merge_conflict_overlapping():
    base = b"a\nb\nc\n"
    local = b"a\nX\nc\n"
    repo = b"a\nY\nc\n"
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts > 0
    assert b"<<<<<<<" in merged


def test_merge_identical_change_no_conflict():
    base = b"a\nb\nc\n"
    local = b"a\nZ\nc\n"
    repo = b"a\nZ\nc\n"
    merged, conflicts = ss.three_way_merge(local, base, repo)
    assert conflicts == 0
    assert merged == b"a\nZ\nc\n"
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: FAIL (`AttributeError: ... 'three_way_merge'`)

- [ ] **Step 3: three_way_merge 구현**

`lib/sync_state.py`에 추가:
```python
def three_way_merge(local_bytes, base_bytes, repo_bytes):
    """git merge-file로 3-way 머지.

    반환 (merged_bytes, conflict_count).
    conflict_count == 0 이면 깨끗한 자동 병합(안 겹침).
    > 0 이면 그 수만큼 겹친 충돌 영역.
    """
    with tempfile.TemporaryDirectory() as d:
        lp = os.path.join(d, "local")
        bp = os.path.join(d, "base")
        rp = os.path.join(d, "repo")
        with open(lp, "wb") as f:
            f.write(local_bytes)
        with open(bp, "wb") as f:
            f.write(base_bytes)
        with open(rp, "wb") as f:
            f.write(repo_bytes)
        proc = subprocess.run(
            ["git", "merge-file", "-p", "--diff3", lp, bp, rp],
            capture_output=True,
        )
    if proc.returncode < 0:
        raise RuntimeError("git merge-file 실패: %r" % proc.stderr)
    return proc.stdout, proc.returncode
```

- [ ] **Step 4: 통과 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: PASS (16 passed)

- [ ] **Step 5: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/lib/sync_state.py plugins/claude-sync/tests/test_sync_state.py
git commit -m "feat(lib): git merge-file 기반 3-way 머지"
```

### Task 4: 동기화 대상 파일 열거 `iter_synced_relpaths`

**Files:**
- Modify: `plugins/claude-sync/lib/sync_state.py`
- Modify: `plugins/claude-sync/tests/test_sync_state.py`

- [ ] **Step 1: 열거 실패 테스트 추가**

`tests/test_sync_state.py` 끝에 추가:
```python
def test_iter_synced_relpaths(tmp_path):
    root = tmp_path
    (root / "agents").mkdir()
    (root / "agents" / "a.md").write_text("x")
    (root / "skills" / "s").mkdir(parents=True)
    (root / "skills" / "s" / "SKILL.md").write_text("y")
    (root / "CLAUDE.md").write_text("z")
    (root / "settings.json").write_text("{}")  # 대상 아님
    got = set(ss.iter_synced_relpaths(str(root)))
    assert got == {"agents/a.md", "skills/s/SKILL.md", "CLAUDE.md"}
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py::test_iter_synced_relpaths -q`
Expected: FAIL

- [ ] **Step 3: iter_synced_relpaths 구현**

`lib/sync_state.py`에 추가:
```python
SYNCED_DIRS = ("agents", "skills")
SYNCED_FILES = ("CLAUDE.md",)


def iter_synced_relpaths(root):
    """root(=~/.claude 또는 레포) 아래 동기화 대상 상대경로를 yield."""
    for name in SYNCED_DIRS:
        d = os.path.join(root, name)
        if os.path.isdir(d):
            for r, _, files in os.walk(d):
                for f in files:
                    yield os.path.relpath(os.path.join(r, f), root)
    for name in SYNCED_FILES:
        if os.path.isfile(os.path.join(root, name)):
            yield name
```

- [ ] **Step 4: 통과 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_sync_state.py -q`
Expected: PASS (17 passed)

- [ ] **Step 5: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/lib/sync_state.py plugins/claude-sync/tests/test_sync_state.py
git commit -m "feat(lib): 동기화 대상 파일 열거"
```

---

## Phase 2 — status

### Task 5: `plugin:` MCP 필터 (compare_mcp.py)

**Files:**
- Modify: `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py`
- Test: 수동 (스크립트가 stdin 파싱이라 픽스처로 검증)

- [ ] **Step 1: 현재 동작 확인**

Run:
```bash
cd ~/dev/claude-sync
printf 'plugin:figma:figma: https://x (HTTP) - ok\nctx: https://y (HTTP) - ok\n' \
  | python3 - <<'PY'
import sys, json, tempfile, os
# 임시 백업 json
servers=[{"name":"ctx","url":"https://y","type":"HTTP"}]
f=tempfile.NamedTemporaryFile("w",suffix=".json",delete=False); json.dump(servers,f); f.close()
import subprocess
print(open("skills/sync-status/scripts/compare_mcp.py").read()[:1])  # 존재 확인
PY
```
Expected: 파일 존재 확인(출력 `#`). (현재는 `plugin:figma:figma`가 "로컬에만"으로 표시됨)

- [ ] **Step 2: `plugin:` 제외 로직 추가**

`skills/sync-status/scripts/compare_mcp.py`에서 현재/백업 이름 집합 생성부를 수정:

기존:
```python
current = set()
for line in sys.stdin:
    m = re.match(r"^(.+?):\s+", line.strip())
    if m:
        current.add(m.group(1).strip())

with open(mcp_json_path) as f:
    backed = json.load(f)
backed_names = {s["name"] for s in backed}
```
변경:
```python
def is_plugin_server(name):
    return name.startswith("plugin:")

current = set()
for line in sys.stdin:
    m = re.match(r"^(.+?):\s+", line.strip())
    if m:
        name = m.group(1).strip()
        if not is_plugin_server(name):
            current.add(name)

with open(mcp_json_path) as f:
    backed = json.load(f)
backed_names = {s["name"] for s in backed if not is_plugin_server(s["name"])}
```

- [ ] **Step 3: 검증**

Run:
```bash
cd ~/dev/claude-sync
TMP=$(mktemp --suffix=.json)
printf '[{"name":"ctx","url":"y","type":"HTTP"}]' > "$TMP"
printf 'plugin:figma:figma: https://x (HTTP) - ok\nctx: y (HTTP) - ok\n' \
  | python3 skills/sync-status/scripts/compare_mcp.py "$TMP"
```
Expected: `MCP 서버: 동일` (plugin:figma:figma가 양쪽에서 무시됨)

- [ ] **Step 4: 커밋**

```bash
cd ~/dev/claude-sync
git add skills/sync-status/scripts/compare_mcp.py
git commit -m "fix(status): plugin: MCP 서버를 비교에서 제외"
```

> 주의: 위 경로는 레포 루트 기준 `skills/...`가 아니라 `plugins/claude-sync/skills/...`다. 실제 실행 시 `cd plugins/claude-sync` 후 상대경로를 쓰거나 풀 경로를 쓴다. 이하 모든 스크립트 경로 동일.

### Task 6: check_status.py 3-way 재작성

**Files:**
- Modify: `plugins/claude-sync/skills/sync-status/scripts/check_status.py` (전면 재작성)
- Test: 수동 통합 (Phase 5에서 시나리오 검증)

- [ ] **Step 1: lib import 가능하도록 경로 헬퍼 결정**

스크립트는 `plugins/claude-sync/skills/sync-status/scripts/check_status.py`. 런타임 캐시에서도 동일 트리. lib는 플러그인 루트의 `lib/`. scripts에서 플러그인 루트는 3단계 위(`scripts`→`sync-status`→`skills`→플러그인루트).

- [ ] **Step 2: check_status.py 재작성**

`plugins/claude-sync/skills/sync-status/scripts/check_status.py` 전체를 교체:
```python
#!/usr/bin/env python3
"""로컬 ~/.claude 와 레포 백업의 차이를 3-way(내용 해시)로 분석해 출력한다. mtime 미사용."""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402

repo_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "SYNC_REPO", "/tmp/claude-sync-repo"
)
HOME_CLAUDE = os.path.expanduser("~/.claude")

rels = sorted(set(ss.iter_synced_relpaths(repo_path)) | set(ss.iter_synced_relpaths(HOME_CLAUDE)))

buckets = {
    "in_sync": [],
    "repo_only": [],      # restore 시 추가
    "local_only": [],     # backup 시 push
    "local_ahead": [],    # backup 시 push
    "fast_forward": [],   # restore 시 업데이트
    "conflict": [],       # 양쪽 변경
}

for rel in rels:
    local = os.path.join(HOME_CLAUDE, rel)
    repo = os.path.join(repo_path, rel)
    L = ss.file_hash(local)
    R = ss.file_hash(repo)
    S = ss.base_hash(rel)
    cls = ss.classify(L, R, S, local_exists=L is not None, repo_exists=R is not None)
    buckets[cls].append(rel)

print("=" * 60)
print("git-like 동기화 상태 (내용 해시 기준, mtime 미사용)")
print("=" * 60)

labels = [
    ("conflict", "⚠ 충돌 — 양쪽 변경 (restore 시 해소 필요)"),
    ("fast_forward", "↓ 업데이트 가능 — 레포가 앞섬 (restore 시 적용)"),
    ("repo_only", "+ 새 파일 — 레포에만 있음 (restore 시 추가)"),
    ("local_ahead", "↑ 로컬 앞섬 (backup 시 push)"),
    ("local_only", "+ 로컬 전용 (backup 시 push)"),
    ("in_sync", "✓ 동일"),
]
for key, label in labels:
    items = buckets[key]
    if items:
        print("\n%s (%d개):" % (label, len(items)))
        for f in items:
            print("  " + f)

if not any(buckets[k] for k in buckets if k != "in_sync"):
    print("\n모든 파일이 동기화 상태입니다.")

# 플러그인 비교 (enabledPlugins 키 집합)
repo_plugins = os.path.join(repo_path, "plugins.json")
settings = os.path.join(HOME_CLAUDE, "settings.json")
if os.path.exists(repo_plugins) and os.path.exists(settings):
    with open(repo_plugins) as f:
        rp = set(json.load(f).get("enabledPlugins", {}).keys())
    with open(settings) as f:
        lp = set(json.load(f).get("enabledPlugins", {}).keys())
    only_repo, only_local = rp - lp, lp - rp
    if only_repo or only_local:
        print("\n플러그인 차이:")
        for p in sorted(only_repo):
            print("  + 레포에만(restore 시 설치): " + p)
        for p in sorted(only_local):
            print("  - 로컬에만(backup 시 추가): " + p)
    else:
        print("\n플러그인: 동일")

print()
```

- [ ] **Step 3: import/구문 검증**

Run:
```bash
cd ~/dev/claude-sync/plugins/claude-sync
python3 -c "import ast; ast.parse(open('skills/sync-status/scripts/check_status.py').read()); print('OK')"
python3 skills/sync-status/scripts/check_status.py /tmp/claude-sync-repo 2>&1 | head -20
```
Expected: `OK`, 그리고 실제 레포에 대해 분류 출력(현재는 `.sync-state`가 없어 동일 파일은 in_sync로 떨어져야 함 — base 없으면 L==R이라 in_sync).

- [ ] **Step 4: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-status/scripts/check_status.py
git commit -m "refactor(status): 3-way 내용 해시 분류로 재작성 (mtime 제거)"
```

### Task 7: sync-status SKILL.md 보고 카테고리 갱신

**Files:**
- Modify: `plugins/claude-sync/skills/sync-status/SKILL.md`

- [ ] **Step 1: 상태 분류 설명 갱신**

SKILL.md에서 기존 "상태 분류"(safe/conflict/repo_only/local_only) 설명 블록을 다음으로 교체:
```markdown
상태 분류 (내용 해시 3-way, mtime 미사용):
- **in_sync**: 로컬과 레포 내용 동일
- **fast_forward**: 레포가 앞섬 → restore 시 자동 업데이트
- **repo_only**: 레포에만 있는 새 파일 → restore 시 추가
- **local_ahead / local_only**: 로컬이 앞섬 → backup 시 push
- **conflict**: 양쪽 모두 base 이후 변경 → restore 시 해소 필요

이 명령은 아무것도 바꾸지 않는다. `plugin:`으로 시작하는 MCP 서버는 플러그인이 제공하므로 비교에서 제외한다.
```

- [ ] **Step 2: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-status/SKILL.md
git commit -m "docs(status): 3-way 카테고리로 SKILL 갱신"
```

---

## Phase 3 — backup

### Task 8: `plugin:` 필터 (parse_mcp.py) + 메타데이터 해시화 (generate_metadata.py)

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py`
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/generate_metadata.py`

- [ ] **Step 1: parse_mcp.py에 plugin: 제외**

`parse_mcp.py`의 append 직전에 가드 추가:
```python
servers = []
for line in sys.stdin:
    line = line.strip()
    m = re.match(r"^(.+?):\s+(\S+)\s+(?:\((\w+)\)\s+)?-\s+.+$", line)
    if m:
        name = m.group(1).strip()
        if name.startswith("plugin:"):
            continue  # 플러그인 제공 서버 → 백업 제외
        servers.append({
            "name": name,
            "url": m.group(2).strip(),
            "type": m.group(3) or "stdio",
        })
```

- [ ] **Step 2: generate_metadata.py를 sha256 기반으로 변경**

`generate_metadata.py` 전체 교체:
```python
#!/usr/bin/env python3
"""백업 시점의 파일별 내용 해시(sha256) 메타데이터를 생성한다. mtime 미사용."""
import hashlib
import json
import os
import sys

output_path = sys.argv[1] if len(sys.argv) > 1 else "sync-metadata.json"
claude_dir = os.path.expanduser("~/.claude")


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def collect(base, prefix):
    result = {}
    if os.path.isfile(base):
        result[prefix] = file_sha256(base)
        return result
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base)
                result[prefix + "/" + rel] = file_sha256(full)
    return result


metadata = {"files": {}}
metadata["files"].update(collect(os.path.join(claude_dir, "agents"), "agents"))
metadata["files"].update(collect(os.path.join(claude_dir, "skills"), "skills"))
metadata["files"].update(collect(os.path.join(claude_dir, "CLAUDE.md"), "CLAUDE.md"))

with open(output_path, "w") as f:
    json.dump(metadata, f, indent=2)
    f.write("\n")
```
(주의: `backup_timestamp`/`now` 제거 — 시간 의존 제거. plugins.json 항목도 제거; 플러그인은 plugins.json 자체로 관리.)

- [ ] **Step 3: 검증**

Run:
```bash
cd ~/dev/claude-sync/plugins/claude-sync
TMP=$(mktemp); python3 skills/sync-backup/scripts/generate_metadata.py "$TMP" && python3 -c "import json;d=json.load(open('$TMP'));print('files',len(d['files']));print(list(d['files'].values())[0] if d['files'] else 'empty')"
printf 'plugin:figma:figma: https://x (HTTP) - ok\nctx: https://y (HTTP) - ok\n' | python3 skills/sync-backup/scripts/parse_mcp.py /dev/stdout
```
Expected: 메타데이터 값이 64자 hex; parse 결과에 `plugin:figma:figma` 없음, `ctx`만 존재.

- [ ] **Step 4: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py plugins/claude-sync/skills/sync-backup/scripts/generate_metadata.py
git commit -m "fix(backup): plugin: MCP 제외, 메타데이터를 sha256으로"
```

### Task 9: reconcile_backup.py — 파일별 push 판정/적용 + push-rejected

**Files:**
- Create: `plugins/claude-sync/skills/sync-backup/scripts/reconcile_backup.py`
- Modify: `plugins/claude-sync/tests/test_reconcile.py` (신규)

- [ ] **Step 1: 판정 함수 실패 테스트**

`plugins/claude-sync/tests/test_reconcile.py` 생성:
```python
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
import reconcile_backup as rb


def test_backup_in_sync():
    assert rb.backup_action("a", "a", "x") == "in_sync"


def test_backup_local_ahead_push():
    # L!=R, R==S → push
    assert rb.backup_action("L", "S", "S") == "push"


def test_backup_remote_ahead_reject():
    # L!=R, R!=S → remote가 앞섬 → 거부
    assert rb.backup_action("L", "R", "S") == "reject"


def test_backup_new_local_push():
    # 레포에 없음(R None) → push(추가)
    assert rb.backup_action("L", None, None) == "push"
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_reconcile.py -q`
Expected: FAIL (`No module named 'reconcile_backup'`)

- [ ] **Step 3: reconcile_backup.py 구현**

`plugins/claude-sync/skills/sync-backup/scripts/reconcile_backup.py`:
```python
#!/usr/bin/env python3
"""백업(push) 방향 파일별 판정.

사용: reconcile_backup.py <repo_path>  (~/.claude 기준 로컬을 레포로 push)
JSON 출력: {"push":[...], "reject":[...], "in_sync":[...]}
실제 파일 복사/커밋은 SKILL.md 흐름에서 수행하며, push된 파일의 base는 로컬 내용으로 갱신한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402


def backup_action(local_hash, repo_hash, seen_hash):
    """반환: in_sync | push | reject"""
    if repo_hash is None:
        return "push"  # 레포에 없음 → 새로 추가
    if local_hash == repo_hash:
        return "in_sync"
    if repo_hash == seen_hash:
        return "push"  # 로컬만 변경(local ahead)
    return "reject"    # remote가 base 이후 변경됨 → restore 먼저


def main():
    repo_path = sys.argv[1]
    home = os.path.expanduser("~/.claude")
    out = {"push": [], "reject": [], "in_sync": []}
    for rel in sorted(ss.iter_synced_relpaths(home)):
        L = ss.file_hash(os.path.join(home, rel))
        R = ss.file_hash(os.path.join(repo_path, rel))
        S = ss.base_hash(rel)
        out[backup_action(L, R, S)].append(rel)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_reconcile.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-backup/scripts/reconcile_backup.py plugins/claude-sync/tests/test_reconcile.py
git commit -m "feat(backup): 파일별 push 판정 + push-rejected"
```

### Task 10: sync-backup SKILL.md — per-file·pull_only·base 갱신

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md`

- [ ] **Step 1: pull_only 가드를 1단계(설정 확인) 직후에 추가**

SKILL.md "### 1. 설정 확인" 끝에 추가:
```markdown
설정에 `"pull_only": true`가 있으면 이 기기는 백업 금지다. 즉시 중단하고 안내한다:
> "이 기기는 pull_only로 지정되어 있어 로컬→리모트 백업을 수행하지 않습니다. 설정을 바꾸려면 sync-config.json에서 pull_only를 제거하세요."
```

- [ ] **Step 2: 파일 수집(4단계)을 per-file reconcile로 교체**

기존 4단계의 `rm -rf agents/; cp -r ...` 무차별 복사를 다음 흐름으로 교체:
```markdown
### 4. 파일별 reconcile (push 판정)

무차별 복사 대신 파일별로 판정한다:
```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 $SYNC_SCRIPTS/reconcile_backup.py "$SYNC_REPO"
```
- `reject`가 하나라도 있으면: "리모트가 앞선 변경이 있습니다. 먼저 /sync-restore 하세요" 안내 후 그 파일은 건너뛴다(push하지 않는다).
- `push` 파일만 `~/.claude/<rel>` → `$SYNC_REPO/<rel>`로 복사한다.
- `.syncignore`가 있으면 해당 패턴은 push 목록에서 제외한다.
```

- [ ] **Step 3: base 갱신 단계 추가 (커밋·푸시 성공 직후)**

SKILL.md의 커밋/푸시 이후에 단계 추가:
```markdown
### N. base(.sync-state) 갱신

push에 성공한 각 파일에 대해, 그 파일의 base를 방금 올린 로컬 내용으로 갱신한다(다음 sync의 merge-base):
```bash
python3 - "$SYNC_REPO" <<'PY'
import os, sys
sys.path.insert(0, os.path.expanduser("~")+"/.claude")  # 사용 안함; 아래에서 lib 경로 사용
PY
```
실제로는 reconcile_backup.py가 보고한 push 목록 각 rel에 대해 다음을 수행한다:
```bash
python3 - <<'PY'
import os, sys
PLUGIN_LIB = os.path.join(os.path.dirname(os.path.realpath("$SYNC_SCRIPTS")), "..", "..", "lib")
sys.path.insert(0, PLUGIN_LIB)
import sync_state as ss
home = os.path.expanduser("~/.claude")
for rel in __import__("json").load(open("/tmp/claude-sync-push-list.json")):
    with open(os.path.join(home, rel), "rb") as f:
        ss.write_base(rel, f.read())
PY
```
(push 목록은 4단계에서 `/tmp/claude-sync-push-list.json`에 저장해 둔다.)
```

> 구현 주의: base 갱신은 lib의 `ss.write_base(rel, 로컬내용)` 호출이 핵심이다. 위 bash 인라인이 번거로우면 별도 스크립트 `update_base.py <rel...>`를 만들어 호출해도 된다(구현자 판단). 핵심 계약: **push 성공 파일의 base ← 로컬 내용**.

- [ ] **Step 4: 동기화 대상 표에 .sync-state 비포함 명시**

"## 동기화 대상" 표 아래 주석 추가:
```markdown
`~/.claude/.sync-state/`는 기기별 로컬 상태(merge-base)이므로 백업/복원 대상이 아니며 레포에 올리지 않는다.
```

- [ ] **Step 5: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-backup/SKILL.md
git commit -m "docs(backup): per-file push·pull_only 가드·base 갱신"
```

---

## Phase 4 — restore

### Task 11: reconcile_restore.py — 분류 + 비대화 적용 + 충돌 JSON

**Files:**
- Create: `plugins/claude-sync/skills/sync-restore/scripts/reconcile_restore.py`
- Delete: `plugins/claude-sync/skills/sync-restore/scripts/analyze_conflicts.py`
- Modify: `plugins/claude-sync/tests/test_reconcile.py`

- [ ] **Step 1: restore 판정 함수 실패 테스트 추가**

`tests/test_reconcile.py` 끝에 추가:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
import reconcile_restore as rr


def test_restore_in_sync():
    assert rr.restore_action("a", "a", "x", True, True) == "skip"

def test_restore_repo_only_add():
    assert rr.restore_action(None, "r", None, False, True) == "add"

def test_restore_fast_forward():
    assert rr.restore_action("S", "R", "S", True, True) == "overwrite"

def test_restore_local_ahead_keep():
    assert rr.restore_action("L", "S", "S", True, True) == "keep"

def test_restore_conflict_needs_merge():
    assert rr.restore_action("L", "R", "S", True, True) == "merge"

def test_restore_local_only_keep():
    assert rr.restore_action("L", None, None, True, False) == "keep"
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/test_reconcile.py -q`
Expected: FAIL (`No module named 'reconcile_restore'`)

- [ ] **Step 3: reconcile_restore.py 구현**

`plugins/claude-sync/skills/sync-restore/scripts/reconcile_restore.py`:
```python
#!/usr/bin/env python3
"""복원(pull) 방향 파일별 판정 + 비대화 적용.

사용: reconcile_restore.py <repo_path> [--apply]
- 분류: skip|add|overwrite|keep|merge
- --apply 시 비대화 동작(add/overwrite/clean-merge/skip)을 수행하고 base를 갱신한다.
- merge 중 git merge-file이 충돌(>0)이거나 base가 없으면 적용하지 않고 conflicts에 남긴다.
JSON 출력: {"applied":{...}, "conflicts":[{rel, reason, has_base}], "local_ahead":[...]}
"""
import json
import os
import shutil
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402


def restore_action(local_hash, repo_hash, seen_hash, local_exists, repo_exists):
    """반환: skip | add | overwrite | keep | merge"""
    cls = ss.classify(local_hash, repo_hash, seen_hash, local_exists, repo_exists)
    return {
        "in_sync": "skip",
        "repo_only": "add",
        "fast_forward": "overwrite",
        "local_ahead": "keep",
        "local_only": "keep",
        "conflict": "merge",
    }[cls]


def main():
    repo_path = sys.argv[1]
    apply = "--apply" in sys.argv[2:]
    home = os.path.expanduser("~/.claude")
    rels = sorted(set(ss.iter_synced_relpaths(repo_path)) | set(ss.iter_synced_relpaths(home)))
    result = {"applied": {}, "conflicts": [], "local_ahead": []}

    for rel in rels:
        local = os.path.join(home, rel)
        repo = os.path.join(repo_path, rel)
        L, R = ss.file_hash(local), ss.file_hash(repo)
        S = ss.base_hash(rel)
        action = restore_action(L, R, S, L is not None, R is not None)

        if action == "keep":
            if L is not None and R is not None and L != R:
                result["local_ahead"].append(rel)
            continue
        if action == "skip":
            if apply and R is not None:
                with open(repo, "rb") as f:
                    ss.write_base(rel, f.read())
            result["applied"].setdefault("skip", []).append(rel)
            continue
        if action in ("add", "overwrite"):
            if apply:
                os.makedirs(os.path.dirname(local), exist_ok=True)
                shutil.copyfile(repo, local)
                with open(repo, "rb") as f:
                    ss.write_base(rel, f.read())
            result["applied"].setdefault(action, []).append(rel)
            continue
        if action == "merge":
            base_bytes = ss.read_base(rel)
            if base_bytes is None:
                result["conflicts"].append({"rel": rel, "reason": "no_base", "has_base": False})
                continue
            with open(local, "rb") as f:
                lb = f.read()
            with open(repo, "rb") as f:
                rb = f.read()
            merged, nconf = ss.three_way_merge(lb, base_bytes, rb)
            if nconf == 0:
                if apply:
                    with open(local, "wb") as f:
                        f.write(merged)
                    ss.write_base(rel, rb)  # remote를 봤다 → base←R, 로컬은 ahead
                result["applied"].setdefault("auto_merge", []).append(rel)
            else:
                result["conflicts"].append({"rel": rel, "reason": "overlap", "has_base": True})

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인 + 옛 스크립트 삭제**

Run:
```bash
cd ~/dev/claude-sync
python3 -m pytest plugins/claude-sync/tests/test_reconcile.py -q
git rm plugins/claude-sync/skills/sync-restore/scripts/analyze_conflicts.py
```
Expected: PASS (10 passed), analyze_conflicts.py 삭제됨.

- [ ] **Step 5: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-restore/scripts/reconcile_restore.py plugins/claude-sync/tests/test_reconcile.py
git commit -m "feat(restore): 3-way reconcile 스크립트 (분류+비대화 적용+충돌 JSON), analyze_conflicts 제거"
```

### Task 12: sync-restore SKILL.md 재작성

**Files:**
- Modify: `plugins/claude-sync/skills/sync-restore/SKILL.md` (재작성)

- [ ] **Step 1: 안전 원칙·충돌 분석·복원 절차 교체**

기존 "## 안전 원칙"(전체 중단)과 3~8단계를 다음으로 교체. (0~2단계: 스크립트 경로 확인·설정·레포 pull은 유지.)
```markdown
## 모델 (git-like, pull-only)

restore는 `git pull`처럼 동작한다. **리모트에 자동 push하지 않는다.** 비교는 내용 해시 3-way(로컬 L / 레포 R / base S = 이 기기가 마지막으로 reconcile한 remote 내용, `~/.claude/.sync-state/base/<rel>`)로 한다. mtime은 쓰지 않는다.

### 3. 파일별 reconcile (비대화 적용)
```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 $SYNC_SCRIPTS/reconcile_restore.py "$SYNC_REPO" --apply
```
스크립트가 자동 처리하는 것(사용자 개입 없음):
- **skip**(in_sync), **add**(레포에만 있는 새 파일), **overwrite**(fast-forward: 레포가 앞섬), **keep**(local_ahead/local_only: 로컬 유지), **auto_merge**(양쪽 변경이나 안 겹쳐 깨끗이 병합).
- 위 모두 base를 적절히 갱신한다. **additive(add)는 충돌과 무관하게 항상 적용된다.**

출력 JSON의 `conflicts`(겹친 충돌 또는 base 없음)만 4단계로 넘어간다. `local_ahead` 목록은 "올리려면 backup" 안내용이다.

### 4. 충돌 해소 (스킬이 대신 수행 — 사용자는 선택만)
`conflicts`의 각 파일에 대해:
1. 간결한 diff를 보여준다: `diff <(cat $SYNC_REPO/<rel>) ~/.claude/<rel>` (필요 시 base와의 차이도).
2. 사용자에게 선택지를 제시: **로컬 유지 / 백업 채택 / 병합 / 나중에**.
3. 선택대로 스킬이 직접 적용한다 (사용자가 파일을 만지지 않는다):
   - **백업 채택**: `cp $SYNC_REPO/<rel> ~/.claude/<rel>` 후 `write_base(rel, 레포내용)`.
   - **로컬 유지**: 로컬 그대로, `write_base(rel, 레포내용)` (remote 봤고 거부 → 재충돌 방지). 로컬은 ahead가 된다.
   - **병합**(겹침/ base 없음): 에이전트가 로컬·레포(있으면 base) 내용을 읽어 병합안을 만들어 보여주고 확인받아 `~/.claude/<rel>`에 쓴 뒤 `write_base(rel, 레포내용)`. 로컬은 ahead가 된다.
   - **나중에**: 아무것도 하지 않는다. base 불변 → 다음 restore에서 또 표시된다.

base 갱신은 lib 헬퍼로 수행한다:
```bash
python3 - <<'PY'
import os, sys
sys.path.insert(0, os.path.join("$SYNC_SCRIPTS", "..", "..", "..", "lib"))
import sync_state as ss
rel = "<rel>"
with open(os.path.join("$SYNC_REPO", rel), "rb") as f:
    ss.write_base(rel, f.read())
PY
```

### 5. 플러그인 복원 (additive)
plugins.json의 enabledPlugins 중 로컬 settings.json에 없는 것만 설치. (마켓플레이스 누락 시 먼저 add.)
```bash
claude plugin install <name@marketplace>
```

### 6. MCP 서버 복원 (additive, plugin: 제외)
mcp-servers.json 중 현재 미등록이고 **이름이 `plugin:`으로 시작하지 않는** 서버만 추가한다. `plugin:` 서버는 플러그인 설치로 따라오므로 `mcp add`하지 않는다.
```bash
claude mcp add <name> <url> --transport <http|stdio> --scope user
```

### 7. 결과 보고
- 적용: add/overwrite/auto_merge/skip 개수
- 해소한 충돌과 방식
- **로컬이 앞선 파일(local_ahead)** → "올리려면 /sync-backup" 안내 (restore는 push하지 않음)
- 설치한 플러그인 / 추가한 MCP / 인증 필요한 MCP
```

- [ ] **Step 2: 옛 "안전 원칙(전체 중단)" 및 mtime 관련 서술 제거 확인**

Run:
```bash
cd ~/dev/claude-sync
grep -n "전체 중단\|mtime\|analyze_conflicts" plugins/claude-sync/skills/sync-restore/SKILL.md || echo "잔존 없음"
```
Expected: `잔존 없음`

- [ ] **Step 3: 커밋**

```bash
cd ~/dev/claude-sync
git add plugins/claude-sync/skills/sync-restore/SKILL.md
git commit -m "docs(restore): pull-only·additive·충돌 해소 UX·base 갱신으로 재작성"
```

---

## Phase 5 — 검증·문서·배포

### Task 13: 통합 시나리오 검증 (임시 HOME)

**Files:** (테스트 전용, 커밋 없음 — 산출물은 콘솔)

- [ ] **Step 1: 격리 환경에서 시나리오 스크립트 실행**

Run (임시 HOME으로 실제 `~/.claude` 오염 방지):
```bash
cd ~/dev/claude-sync/plugins/claude-sync
bash -c '
set -e
SB=$(mktemp -d)        # 가짜 HOME
export HOME="$SB"
mkdir -p "$HOME/.claude/agents"
REPO=$(mktemp -d); mkdir -p "$REPO/agents"
# 시나리오: 레포에 2,3 새 파일 + 공통 1
echo "v1" > "$REPO/agents/one.md";  echo "v1" > "$HOME/.claude/agents/one.md"   # 동일(1)
echo "two" > "$REPO/agents/two.md"                                              # 새 파일(2)
echo "three" > "$REPO/agents/three.md"                                          # 새 파일(3)
python3 skills/sync-restore/scripts/reconcile_restore.py "$REPO" --apply
echo "=== restore 후 로컬 ==="; ls "$HOME/.claude/agents"
test -f "$HOME/.claude/agents/two.md" && test -f "$HOME/.claude/agents/three.md" && echo "OK: 2,3 추가됨"
# 이제 양쪽 변경(conflict) 케이스: 1을 양쪽이 다르게 수정
echo "local-edit" > "$HOME/.claude/agents/one.md"
echo "repo-edit" > "$REPO/agents/one.md"
python3 skills/sync-restore/scripts/reconcile_restore.py "$REPO" | python3 -c "import sys,json;d=json.load(sys.stdin);print(\"conflicts:\",[c[\"rel\"] for c in d[\"conflicts\"]])"
'
'
```
Expected: `OK: 2,3 추가됨`, 그리고 `conflicts: ['agents/one.md']` (base가 v1로 잡혀 있어 양쪽 변경 → conflict). additive(2,3)는 충돌과 무관하게 적용됨을 확인.

- [ ] **Step 2: 전체 단위 테스트 그린 확인**

Run: `cd ~/dev/claude-sync && python3 -m pytest plugins/claude-sync/tests/ -q`
Expected: PASS (모든 테스트)

### Task 14: README 갱신 + 버전 bump

**Files:**
- Modify: `README.md`, `README.ko.md`
- Modify: `.claude-plugin/marketplace.json`, `plugins/claude-sync/.claude-plugin/plugin.json`

- [ ] **Step 1: README 동작 모델 한 단락 갱신**

`README.ko.md`(및 영문 README.md 대응 위치)의 동작 설명에 다음 취지 추가:
```markdown
비교는 내용 해시 기반 git-like 3-way로 동작합니다. restore는 pull 전용이며 리모트에 자동 push하지 않습니다. 새 파일·플러그인·MCP는 충돌과 무관하게 항상 추가되고, 같은 파일을 양쪽에서 다르게 고친 경우만 충돌로 처리해 로컬 유지 / 백업 채택 / 병합 / 나중에 중에서 고를 수 있습니다. pull_only로 지정한 기기는 백업하지 않습니다.
```

- [ ] **Step 2: 버전 1.0.0 → 1.0.1**

`.claude-plugin/marketplace.json`의 `"version": "1.0.0"` → `"1.0.1"`.
`plugins/claude-sync/.claude-plugin/plugin.json`의 `"version": "1.0.0"` → `"1.0.1"`.

Run: `cd ~/dev/claude-sync && grep -rn '"version"' .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json`
Expected: 둘 다 `1.0.1`.

- [ ] **Step 3: 커밋**

```bash
cd ~/dev/claude-sync
git add README.md README.ko.md .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
git commit -m "docs+chore: 동작 모델 문서화, 버전 1.0.1"
```

### Task 15: 배포 — push + CC 인식 (사용자 승인 게이트)

**Files:** (git/CLI 작업)

- [ ] **Step 1: main 병합**

```bash
cd ~/dev/claude-sync
git checkout main
git merge --no-ff git-like-sync -m "merge: git-like 동기화 재설계 (1.0.1)"
```

- [ ] **Step 2: 푸시 (⚠ 외부 동작 — 실행 직전 사용자에게 확인)**

```bash
cd ~/dev/claude-sync && git push origin main
```
사용자 승인 없이는 실행하지 않는다.

- [ ] **Step 3: CC가 신버전 인식하도록 업데이트**

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync
```

- [ ] **Step 4: 캐시 반영 확인**

```bash
ls ~/.claude/plugins/cache/claude-sync/claude-sync/
grep -rn "mtime\|local_mtime" ~/.claude/plugins/cache/claude-sync/claude-sync/*/skills/sync-restore/scripts/ || echo "신코드(mtime 없음) 반영됨"
```
Expected: `1.0.1` 디렉토리 존재, restore 스크립트에 mtime 잔존 없음.

---

## Self-Review

**Spec coverage 체크:**
- §3.1 개념/§3.2 .sync-state/§3.3 비교 → Task 1~4 (lib), 모든 스크립트가 사용. ✓
- §4.1 판정표 → Task 11 `restore_action`/`classify`. ✓
- §4.2 git merge-file → Task 3. ✓
- §4.3 충돌 해소 UX(4선택, seen 갱신) → Task 12 SKILL.md. ✓
- §4.4 plugin/MCP additive + plugin: 제외 → Task 12(restore), Task 5/8(필터). ✓
- §4.5 순환 정합 → base 갱신 규칙 Task 11/12, 검증 Task 13. ✓
- §5 backup(per-file, push-rejected, pull_only) → Task 9, 10. ✓
- §6 status → Task 6, 7. ✓
- §7 plugin: 필터 3곳 → Task 5(compare), 8(parse), 12(restore SKILL). ✓
- §8 첫 sync/마이그레이션(mtime 폐기, base 없을 때) → Task 8(metadata 해시), Task 11(no_base→conflict). ✓
- §9 영향 파일 → File Structure 표. ✓
- §10 배포 → Task 15. §11 검증 → Task 13. ✓

**Placeholder 스캔:** Task 10 Step 3의 base 갱신 bash 인라인은 번거로우므로 "별도 `update_base.py` 가능"이라 명시했고 핵심 계약(push 파일 base←로컬내용)을 못박음 — 구현자 재량 허용 범위. 그 외 TBD/TODO 없음.

**Type/이름 일관성:** `classify`(lib) → `restore_action`/`backup_action`이 래핑. `write_base/read_base/base_hash/file_hash/iter_synced_relpaths/three_way_merge` 이름이 전 Task에서 일관. ✓

**알려진 보완점(구현 중 처리):**
- Task 13 Step 1의 heredoc 따옴표 중첩은 구현자가 환경에 맞게 조정(핵심: 임시 HOME, additive 2·3 적용, one.md conflict 확인).
- `local_only` 파일을 backup이 push 대상에 포함(신규 로컬 파일 업로드)하는 동작은 reconcile_backup의 `R is None → push`로 커버.
