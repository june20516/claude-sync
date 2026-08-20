# MCP 설정 소스 전환 — 스킬 통합 Implementation Plan

> **agentic worker에게:** REQUIRED SUB-SKILL: 이 plan을 task 단위로 구현하려면
> suberpower:subagent-driven-development(권장) 또는 suberpower:executing-plans를 사용하세요.
> Step은 추적을 위해 checkbox(`- [ ]`) 문법을 사용합니다.

**Goal:** `lib/mcp_config.py`를 backup·status·restore 세 스킬에 실제로 연결해, `claude mcp list` 텍스트 파싱으로 사실상 동작하지 않던 MCP 서버 백업을 `~/.claude.json` 기반의 복원 가능한 동기화로 바꾼다.

**Architecture:** 데이터 소스는 `~/.claude.json`의 top-level `mcpServers`(user 스코프) 하나뿐이며, 세 스킬은 `lib/mcp_config.py`만 통해 MCP를 다룬다(파서 드리프트 구조적 차단). 스크립트는 판정·계산·파일 쓰기만 하고 `claude mcp` CLI 실행과 비밀 값 입력은 SKILL.md의 대화 흐름이 맡는다. base(`~/.claude/.sync-state/base/mcp-servers.json`)는 서버 이름 키 단위로 "로컬이 동의한 값만" 전진하며, 기록 주체는 기존 `update_base.py` 하나다.

**Tech Stack:** Python 3 표준 라이브러리만 (`json`/`os`/`re`/`copy`), pytest(uv로 실행), bash + `claude mcp` CLI, git.

**Spec:** `docs/superpowers/specs/2026-08-20-mcp-config-source-design.md`

---

## 시작 전에 반드시 읽을 것

**현재 지점.** `lib/mcp_config.py`는 `restore_plan`을 뺀 전 API가 구현·테스트되어 있고 기존 테스트는 전부 통과한다. 그러나 **어떤 스킬도 이 모듈을 호출하지 않는다.** 지금 `/sync-backup`을 실행하면 옛 정규식 파서(`parse_mcp.py`)가 돌고 보고된 버그가 그대로 재현된다. 이 plan을 끝내야 사용자의 버그가 고쳐진다.

**기준선 확인 (Task 1 시작 전 1회):**

```bash
cd /Users/bran/personal/claude-sync
git branch --show-current          # → fix/mcp-config-source
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: `N passed` (pytest는 이 환경에 설치되어 있지 않다 — 반드시 `uv run --with pytest`로 실행한다). **이 N을 적어 두고, 이후 각 task에서 "직전 대비 몇 개 증가"로만 판단한다. 테스트 총 개수를 목표 숫자로 못박지 않는다.**

### 다섯 가지 불변식 (STATUS 문서 5장) — 각 task에서 다시 상기시킨다

1. **base는 로컬이 동의한 값만 전진한다.** "푸시 성공 && 충돌 없음 → base ← 레포 파일 전체"는 폐기된 규칙이다. 타 기기가 추가·변경한 값을 base에 기록하면 다음 백업이 그것을 "내가 삭제했다"로 오독한다. **전역 게이트는 제거되었다. 되살리지 말 것.**
2. **신뢰할 수 없는 이력은 `{}`가 아니라 `None`이다.** 손상된 base를 `{}`로 읽으면 "이력이 비어 있었다"로 오인되어 삭제 판정의 근거가 된다. `parse_base`가 이 구별을 담당하고, 같은 이유로 `read_local_servers`는 파일을 못 읽으면 예외를 던진다.
3. **모든 상태에 탈출구가 있어야 한다.** 케이스 4(타 기기가 삭제, 로컬 잔존)와 케이스 8(타 기기가 변경, 로컬은 옛 값)은 *안정 상태*라 사용자가 명시적으로 선택하지 않으면 영원히 유지된다. 안정적인 것과 해소 가능한 것은 다르다.
4. **마스킹은 양쪽에 적용한 뒤 비교한다.** `diff`·`merge`·`restore_plan`·`next_base` 넷 모두 내부에서 `redact`를 적용한다. 하나만 빠져도 그 함수를 지나는 경로에서 영구 미수렴이 되살아난다.
5. **`claude mcp add-json`의 실제 제약**(실측): 이름은 영숫자·하이픈·언더스코어만(`^[A-Za-z0-9_-]+$`), 기존 이름은 덮어쓰지 못한다(`already exists`, exit 1). 값을 바꾸려면 `remove` → `add-json` 2단계다.

### 커밋 규칙

- 커밋 명령에는 **반드시 경로를 명시**한다: `git commit -m "..." -- <paths>`. 경로를 안 주면 다른 프로세스가 staging한 파일이 섞인다(실제로 발생했다).
- 커밋 메시지는 이 레포 관례대로 한국어 conventional commit 제목을 쓰고, 끝에 `Co-Authored-By:` / `Claude-Session:` 트레일러를 붙인다(아래 명령에서는 지면상 생략한다).

### 코드베이스 관례

- 한국어 docstring, `%` 포매팅(f-string 미사용), 서술적 snake_case.
- 스크립트에서 lib를 쓸 때는 `sys.path.insert(0, .../"..", "..", "..", "lib")` 후 `import mcp_config as mc`.
- 테스트에서 lib는 `tests/conftest.py`가 이미 path에 넣어 준다. **스크립트**를 import하는 테스트는 `test_reconcile.py`처럼 테스트 파일 상단에서 직접 `sys.path.insert`한다.
- 테스트는 실제 `~/.claude.json`·`~/.claude/.sync-state`를 절대 건드리지 않는다. 인프로세스 호출은 `claude_json_path=`/`base_dir=` 키워드로, 서브프로세스 호출은 `env HOME=<tmp>`로 격리한다.

---

## File Structure

| 파일 | 책임 | 이 plan에서 |
|---|---|---|
| `plugins/claude-sync/lib/mcp_config.py` | MCP 판정의 단일 진입점. read/redact/parse/dump/same/diff/merge/next_base/restore_plan | Task 1·2에서 `next_base` 계약 수정 + `restore_plan` 신설 |
| `plugins/claude-sync/lib/sync_state.py` | base 블롭 I/O(`read_base`/`write_base`), 파일 단위 3-way | 변경 없음 (재사용) |
| `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py` | 로컬×레포×base를 merge하여 레포 파일과 **스테이징** base 파일을 쓴다 | **신설** (Task 4) |
| `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py` | (구) `claude mcp list` 정규식 파서 | **삭제** (Task 5) |
| `plugins/claude-sync/skills/sync-backup/scripts/update_base.py` | base 블롭을 기록하는 **유일한 주체**. `<source_root>/<rel>` → base | 변경 없음 (스테이징 디렉토리를 source_root로 받아 재사용) |
| `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py` | 읽기 전용 diff 보고 | **재작성** (Task 6) |
| `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py` | `plan`(복원 계획) / `apply-base`(override 적용 후 스테이징 기록) | **신설** (Task 7·8) |
| `plugins/claude-sync/skills/sync-backup/SKILL.md` | backup 대화·bash 흐름. MCP 수집 → 커밋/푸시 → base 갱신 분기 | Task 5 |
| `plugins/claude-sync/skills/sync-status/SKILL.md` | status 대화·bash 흐름, 상태 어휘 | Task 6 |
| `plugins/claude-sync/skills/sync-restore/SKILL.md` | restore 대화. 세 선택지, 비밀 입력, `remove`→`add-json`, base override | Task 10 |
| `plugins/claude-sync/tests/test_mcp_config.py` | 모듈 단위 테스트 | Task 1·2 |
| `plugins/claude-sync/tests/test_mcp_state_machine.py` | **신설** — merge 반복 적용 수렴(spec 13 멱등성 표) | Task 3 |
| `plugins/claude-sync/tests/test_mcp_scripts.py` | **신설** — 세 스크립트의 인프로세스/CLI 계약 | Task 4·6·7·8 |
| `plugins/claude-sync/tests/test_mcp_cycle.py` | **신설** — 스크립트를 경유한 backup↔restore 교대 시나리오 | Task 9 |
| `README.md` / `README.ko.md` | 사용자 문서 (동기화 대상 표, 동작 모델, 안전 장치) | Task 11 |
| `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md` / `.ko.md` | 백업 레포에 복사되는 README | Task 11 |
| `plugins/claude-sync/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | 버전 | Task 12 (2.0.0 → 3.0.0) |

---

## Task 1: `next_base`에 `redact` 내부 적용

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

**왜.** spec 5장은 `diff`·`merge`·`next_base`·`restore_plan` 네 함수 모두 "비교 직전 양쪽에 `redact`를 적용한다"를 **호출부 규약이 아니라 함수의 계약**으로 두었다(불변식 4). 현재 `next_base`만 이 적용이 빠져 있다. `merge`는 이미 마스킹된 값을 넘기므로 지금까지 드러나지 않았지만, Task 8의 restore는 `read_local_servers()`의 **원본(비밀 평문)** 을 그대로 넘긴다. 그러면 `same(레포의 <REDACTED>, 로컬 평문)`이 거짓이 되어 (a) 비밀을 가진 서버의 base가 영원히 전진하지 않고(불변식 1이 한 라운드 깨진다), (b) 평문 API 키가 base 블롭에 새 사본으로 기록된다. `redact`는 멱등이므로 이미 마스킹된 `merge` 경로에는 영향이 없다.

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_config.py` **맨 끝**에 추가한다:

```python
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
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q -k next_base_redacts_input_so_secret_server_advances
```

기대: `1 failed`. 실패 지점은 `assert out["context7"]["url"] == "u"` — 실제 값은 `"old"`(로컬이 동의했다고 판정되지 못해 이전 base가 유지된다).

- [ ] **Step 3: 최소한의 implementation 작성**

`plugins/claude-sync/lib/mcp_config.py`의 `next_base`에서 아래 두 줄을

```python
    old = base or {}
    out = {}
```

다음으로 교체한다:

```python
    local, servers = redact(local), redact(servers)
    old = redact(base) if base else {}
    out = {}
```

이어서 같은 함수의 docstring 끝에 계약을 명시하는 한 문단을 추가한다(spec 5장 문언 그대로):

```python
    입력에 redact를 내부 적용한다 — merge·diff와 같은 계약이다. restore는
    read_local_servers()의 원본(비밀 평문)을 넘기게 되는데, 내부 적용이 없으면
    same(레포의 <REDACTED>, 로컬 평문)이 거짓이 되어 비밀을 가진 서버의 base가
    전진하지 않고, 평문 키가 base 블롭에 새 사본으로 기록된다.
    redact는 멱등이므로 이미 마스킹된 merge 경로에는 영향이 없다.
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건. 새 테스트 2개가 통과하고 **기존 테스트는 하나도 깨지지 않는다**(직전 대비 2개 증가). 특히 `test_merge_redacts_input_internally`, `test_next_base_does_not_share_objects_with_servers`가 계속 통과해야 한다.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "fix(mcp): next_base도 입력에 redact 적용 — diff·merge와 계약 통일" -- plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
```

---

## Task 2: `restore_plan` 신설 (버킷 9개)

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py`
- Test: `plugins/claude-sync/tests/test_mcp_config.py`

**왜.** restore는 "레포에 있는데 로컬에 없는 서버"를 셋(`add`/`needs_secret`/`unrestorable`)으로, "양쪽에 있는 서버"를 넷(`in_sync`/`local_ahead`/`repo_ahead`/`both_changed`)으로, "로컬에만 있는 서버"를 둘(`local_stale`/`local_only`)로 갈라야 한다. **케이스 7·8·9를 `differs` 한 버킷으로 뭉치면 케이스 7(아직 백업되지 않은 이 기기의 변경)에도 "레포 값 채택"이 제시되어 사용자의 미백업 변경이 파괴된다**(spec 7.7, 불변식 3). 판정 조건식은 `merge`가 7.2 판정표에서 쓰는 것과 같아야 한다 — 새로 만들면 두 곳의 케이스 구분이 갈라진다. `local_stale`은 `merge.local_stale`(케이스 4만)보다 넓어 **케이스 5까지 담는다**: 담지 않으면 backup은 매번 "충돌 — `/sync-restore` 먼저"라고 안내하는데 restore가 아무것도 보여주지 않는 탈출구 없는 상태가 된다.

- [ ] **Step 1: R에만 있는 이름의 분류 test 작성**

`plugins/claude-sync/tests/test_mcp_config.py` 맨 끝에 추가한다:

```python
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
```

- [ ] **Step 2: L∩R·L-only 분류 test 작성**

같은 파일 맨 끝에 이어서 추가한다:

```python
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
```

- [ ] **Step 3: test를 실행하여 실패를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_config.py -q -k restore_plan
```

기대: 위 11개가 전부 `AttributeError: module 'mcp_config' has no attribute 'restore_plan'`로 실패한다(`11 failed`).

- [ ] **Step 4: `restorable` 판정과 `restore_plan` 구현**

`plugins/claude-sync/lib/mcp_config.py` 상단의 `import copy` 블록에 `import re`를 추가하고(알파벳 순: `copy`, `json`, `os`, `re`), `DEFAULT_CLAUDE_JSON` 아래에 상수를 추가한다:

```python
VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")   # claude mcp add-json의 실측 제약
```

파일 **맨 끝**에 두 함수를 추가한다:

```python
def restorable(name, cfg):
    """claude mcp add-json으로 재현할 수 있는 항목인가.

    둘 중 하나만 어겨도 거짓이다 —
    (a) 이름이 CLI 규칙(영숫자·하이픈·언더스코어)을 어김,
    (b) config에 command도 없고 url+type(http/sse)도 없음.
    v1 배열에서 승격된 항목이 정확히 (b)의 형태다(10장). type은 소문자만 인정한다 —
    v1이 저장하던 "HTTP"는 add-json 스키마와 맞지 않는다.
    """
    if not VALID_NAME.match(name):
        return False
    if not isinstance(cfg, dict):
        return False
    if isinstance(cfg.get("command"), str) and cfg["command"]:
        return True
    return isinstance(cfg.get("url"), str) and cfg.get("type") in ("http", "sse")


def restore_plan(local, backed, base):
    """복원 계획. diff·merge와 마찬가지로 비교 직전 양쪽에 redact를 적용한다.

    버킷 9개: add / needs_secret / unrestorable / in_sync / local_ahead /
    repo_ahead / both_changed / local_stale / local_only.
    케이스 7·8·9를 한 버킷으로 뭉치지 않는 이유는 7.7에 있다 — 처방이 서로 다르고,
    특히 케이스 7에 "레포 값 채택"을 제시하면 아직 백업되지 않은 로컬 변경이 파괴된다.
    조건식은 merge가 7.2 판정표의 7·8·9행에서 쓰는 것과 같다.
    local_stale은 케이스 4와 5를 모두 담는다(merge.local_stale ⊆ restore_plan.local_stale) —
    담지 않으면 케이스 5가 탈출구 없는 상태가 된다.
    """
    local, backed = redact(local), redact(backed)
    known = redact(base) if base else {}
    plan = {key: [] for key in (
        "add", "needs_secret", "unrestorable", "in_sync", "local_ahead",
        "repo_ahead", "both_changed", "local_stale", "local_only",
    )}
    for name in sorted(set(local) | set(backed)):
        in_local, in_repo = name in local, name in backed
        if in_repo and not in_local:
            cfg = backed[name]
            if not restorable(name, cfg):
                plan["unrestorable"].append(name)
            elif secret_keys(cfg):
                plan["needs_secret"].append(name)
            else:
                plan["add"].append(name)
        elif in_local and in_repo:
            if same(local[name], backed[name]):                          # 6
                plan["in_sync"].append(name)
            elif name in known and same(backed[name], known[name]):      # 7
                plan["local_ahead"].append(name)
            elif name in known and same(local[name], known[name]):       # 8
                plan["repo_ahead"].append(name)
            else:                                                        # 9
                plan["both_changed"].append(name)
        elif name in known:                                              # 4·5
            plan["local_stale"].append(name)
        else:                                                            # 1
            plan["local_only"].append(name)
    return plan
```

- [ ] **Step 5: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건, 직전 대비 11개 증가.

- [ ] **Step 6: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
git commit -m "feat(mcp): restore_plan 신설 — 케이스 7·8·9를 분리한 복원 버킷 9개" -- plugins/claude-sync/lib/mcp_config.py plugins/claude-sync/tests/test_mcp_config.py
```

---

## Task 3: 상태 기계 검증 — backup 반복 적용 수렴

**Files:**
- Create: `plugins/claude-sync/tests/test_mcp_state_machine.py`

**왜.** **판정표를 100% 덮은 단발 호출 테스트가 전부 통과하는데도 시스템이 데이터를 잃을 수 있다.** 이전 설계에서 실제로 그랬다 — 케이스 2·8의 값을 base에 기록하는 규칙 아래에서, 새 기기가 restore 없이 backup을 두 번 하면 다른 기기의 서버가 경고 없이 전멸했고, 단발 테스트는 전부 초록이었다. spec 13장은 그래서 **`merge`를 반복 적용해 고정점을 확인하는** 검증 열 줄을 완료 정의에 넣었다. 이 task는 그 열 줄을 테스트로 옮긴다(불변식 1·3).

이 task는 **회귀 검증 task**다. 새 구현이 없으므로 Step 2에서 곧바로 통과하는 것이 정상이다. 실패한다면 그것은 테스트가 아니라 `merge`/`next_base` 쪽 결함이므로, spec 7.2·7.3을 근거로 모듈을 고치고 그 수정도 같은 커밋에 넣는다.

- [ ] **Step 1: 반복 적용 harness와 시나리오 test 작성**

`plugins/claude-sync/tests/test_mcp_state_machine.py`를 새로 만든다:

```python
"""backup을 반복 적용했을 때 고정점에 도달하는지 검증한다 (spec 13장 멱등성 표).

단발 호출 테스트는 상태 기계 결함을 잡지 못한다. 이전 설계의 Critical 결함
("base ← 레포 파일 전체")은 판정표를 100% 덮은 테스트를 전부 통과했지만,
2회차 백업에서 타 기기의 서버를 전멸시켰다.
"""
import mcp_config as mc

A = {"command": "a"}
B = {"command": "b"}
ORIG = {"command": "o"}


def backup_round(local, repo, base):
    """푸시에 성공한 backup 1회를 흉내낸다: 레포 ← servers, base ← next_base.

    반환 (보고, 다음 레포, 다음 base).
    """
    result = mc.merge(local, repo, base)
    return result, result["servers"], result["next_base"]


def repeat_backup(local, repo, base, rounds=3):
    """같은 로컬로 backup을 rounds회 반복하고 매 회차의 (보고, 레포, base)를 모은다."""
    snapshots = []
    for _ in range(rounds):
        result, repo, base = backup_round(local, repo, base)
        report = {k: v for k, v in result.items() if k not in ("servers", "next_base")}
        snapshots.append((report, repo, base))
    return snapshots


def assert_fixed_point_from_second_round(snapshots):
    """2회차부터 레포 내용과 보고가 변하지 않아야 한다."""
    assert snapshots[1] == snapshots[2], "2회차와 3회차가 다르다 — 고정점이 아니다"


def test_repeated_backup_without_cleanup_keeps_reporting_local_stale():
    """케이스 4를 정리하지 않고 반복해도 서버가 되살아나지 않고 base[X]가 전진하지 않는다."""
    local = {"X": A, "y": A}
    snapshots = repeat_backup(local, {"y": A}, {"X": A})
    for report, repo, base in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo                 # 되살아나지 않는다
        assert base["X"] == A                  # base[X] 고정
        assert base["y"] == A                  # 다른 이름의 base는 정상 전진
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_removed_backup_converges_without_stale():
    """restore '제거' 경로: X가 L·R·S 어디에도 없는 상태로 안정된다."""
    local = {"y": A}
    base = mc.next_base(local, {"X": A, "y": A}, {"y": A})   # restore의 base 갱신(①)
    assert "X" not in base
    snapshots = repeat_backup(local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == [] and report["deleted"] == []
        assert sorted(repo) == ["y"]
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_kept_backup_pushes_server_back():
    """restore '유지' 경로: base에서 X를 지웠으므로 케이스 1로 push되고 이후 불변."""
    local = {"X": A, "y": A}
    base = mc.next_base(local, {"X": A}, {"y": A})
    base.pop("X", None)                                     # override ② (7.4)
    snapshots = repeat_backup(local, {"y": A}, base)
    assert sorted(snapshots[0][1]) == ["X", "y"]            # 1회차에 복귀
    for report, _, _ in snapshots:
        assert report["local_stale"] == []
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_deferred_backup_keeps_case4():
    """restore '나중에' 경로: 아무것도 바뀌지 않고 케이스 4가 반복된다."""
    local = {"X": A, "y": A}
    base = mc.next_base(local, {"X": A}, {"y": A})           # override 없음
    assert base["X"] == A
    snapshots = repeat_backup(local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case9_conflict_freezes_base():
    """케이스 9: 매회 conflicts=[Z], 레포는 R 유지, base[Z] 고정."""
    snapshots = repeat_backup({"Z": A}, {"Z": B}, {"Z": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert repo["Z"] == B
        assert base["Z"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case5_conflict_freezes_base():
    """케이스 5: 매회 conflicts=[X], 레포에 X 없음, base[X] 고정."""
    snapshots = repeat_backup({"X": A}, {}, {"X": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["X"]
        assert "X" not in repo
        assert base["X"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_conflicted_name_freezes_only_its_own_base():
    """전역 게이트를 되살리면 안 되는 이유 — 충돌 하나가 전체 base를 동결하지 않는다."""
    snapshots = repeat_backup({"Z": A, "n": B}, {"Z": B}, {"Z": ORIG})
    for report, _, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert base["Z"] == ORIG      # 충돌 이름의 base는 고정
        assert base["n"] == B         # 정상 서버의 base는 전진
    assert_fixed_point_from_second_round(snapshots)


def test_case2_remote_added_survives_repeated_backup():
    """타 기기가 추가한 서버가 2회차에도 레포에 남는다 — 옛 설계가 여기서 데이터를 잃었다."""
    snapshots = repeat_backup({"x": A}, {"x": A, "z": B}, {"x": A})
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["z"] == B
        assert report["repo_ahead"] == ["z"]
    assert_fixed_point_from_second_round(snapshots)


def test_case8_remote_change_survives_repeated_backup():
    """타 기기의 변경이 로컬 값으로 되돌아가지 않는다."""
    snapshots = repeat_backup({"x": ORIG}, {"x": B}, {"x": ORIG})
    for report, repo, base in snapshots:
        assert repo["x"] == B
        assert base["x"] == ORIG
        assert report["repo_ahead"] == ["x"]
    assert_fixed_point_from_second_round(snapshots)


def test_new_machine_without_base_does_not_delete_others_on_second_round():
    """base=None으로 시작한 새 기기가 2회차에 남의 서버를 삭제하지 않는다."""
    snapshots = repeat_backup({"mine": A}, {"theirs": B}, None)
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["theirs"] == B
    assert_fixed_point_from_second_round(snapshots)
```

- [ ] **Step 2: test를 실행하여 결과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_state_machine.py -q
```

기대: 새 파일의 테스트 10개가 전부 통과한다. **하나라도 실패하면 테스트가 아니라 `merge`/`next_base`가 spec 7.2·7.3을 어긴 것이다** — 모듈을 고치고 이 task 안에서 함께 커밋한다.

- [ ] **Step 3: 전체 suite 실행**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건, 직전 대비 10개 증가.

- [ ] **Step 4: Commit**

```bash
git add plugins/claude-sync/tests/test_mcp_state_machine.py
git commit -m "test(mcp): backup 반복 적용 고정점 검증 10종 (spec 13장 멱등성 표)" -- plugins/claude-sync/tests/test_mcp_state_machine.py
```

---

## Task 4: `collect_mcp.py` 신설

**Files:**
- Create: `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py`
- Create: `plugins/claude-sync/tests/test_mcp_scripts.py`

**왜.** backup의 MCP 단계를 `claude mcp list` 파이프에서 `~/.claude.json` 읽기로 바꾼다. 두 가지가 특히 중요하다.

1. **이 스크립트는 base를 쓰지 않는다.** 커밋 **전에** 실행되기 때문이다(spec 7.5, 불변식 1). `merge`가 돌려준 `next_base`를 **스테이징 디렉토리**에 `mcp-servers.json`이라는 이름으로 써 두고, 레포가 실제로 그 내용을 갖게 된 뒤 SKILL.md가 `update_base.py <스테이징> mcp-servers.json`을 호출한다. `update_base.py`에 **레포를 `source_root`로 넘기면 안 된다** — `base ← 레포 파일 바이트`가 되어 7.3을 정면으로 위반한다.
2. **읽기 실패는 "서버 0개"가 아니다**(불변식 2). `LocalConfigUnavailable`이나 `PermissionError`면 레포 파일도 스테이징 파일도 건드리지 않고 `{"status": "skipped"}`를 stdout에 내고 **종료 코드 0**으로 끝낸다. 스크립트가 traceback으로 죽으면 SKILL.md 흐름 전체가 중단되므로 예외를 잡는 주체는 스크립트다.

`conflicts`를 `repo_kept`(케이스 9)/`repo_absent`(케이스 5)로, `repo_ahead`를 `present`(케이스 8)/`absent`(케이스 2)로 갈라서 내보내는 이유는, 그 구분이 이미 스크립트 안에 있기 때문이다. 뭉쳐 내보내면 SKILL.md가 판정을 재구현해야 하고 그것이 이 spec이 없애려는 드리프트의 형태다.

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_scripts.py`를 새로 만든다:

```python
"""세 스크립트(collect_mcp / compare_mcp / plan_mcp)의 계약 테스트.

실제 ~/.claude.json과 ~/.claude/.sync-state는 절대 건드리지 않는다 —
인프로세스 호출은 claude_json_path=/base_dir= 로, CLI 호출은 env HOME= 으로 격리한다.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-status", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import mcp_config as mc  # noqa: E402
import collect_mcp  # noqa: E402

A = {"command": "a"}
B = {"command": "b"}
ORIG = {"command": "o"}
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")


def write_local(tmp_path, servers):
    """~/.claude.json 역할의 임시 파일."""
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return str(path)


def write_repo(tmp_path, servers):
    """레포 디렉토리와 mcp-servers.json을 만든다. servers가 None이면 파일 없음."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if servers is not None:
        mc.dump_backup(servers, str(repo / mc.BACKUP_RELPATH))
    return str(repo)


def write_base_blob(tmp_path, servers):
    """base 블롭 디렉토리를 만든다. servers가 None이면 이력 없음."""
    base_dir = tmp_path / "base"
    base_dir.mkdir(exist_ok=True)
    if servers is not None:
        mc.dump_backup(servers, str(base_dir / mc.BACKUP_RELPATH))
    return str(base_dir)


def repo_servers(repo):
    return mc.load_backup(os.path.join(repo, mc.BACKUP_RELPATH))


def staged_servers(staging):
    return mc.load_backup(os.path.join(staging, mc.BACKUP_RELPATH))


def test_collect_writes_repo_and_staging(tmp_path):
    """merge 결과는 레포로, next_base는 스테이징으로 — base 블롭은 건드리지 않는다."""
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    staging = str(tmp_path / "staging")
    out = collect_mcp.collect(repo, staging, claude_json_path=local, base_dir=base_dir)
    assert out["status"] == "ok"
    assert repo_servers(repo) == {"x": A}
    assert staged_servers(staging) == {"x": A}
    assert not os.path.exists(os.path.join(base_dir, mc.BACKUP_RELPATH))


def test_collect_splits_conflicts_by_repo_presence(tmp_path):
    """케이스 9는 repo_kept, 케이스 5는 repo_absent — SKILL.md가 판정을 재구현하지 않게 한다."""
    local = write_local(tmp_path, {"nine": A, "five": B})
    repo = write_repo(tmp_path, {"nine": B})
    base_dir = write_base_blob(tmp_path, {"nine": ORIG, "five": ORIG})
    out = collect_mcp.collect(repo, str(tmp_path / "staging"),
                              claude_json_path=local, base_dir=base_dir)
    assert out["conflicts"] == {"repo_kept": ["nine"], "repo_absent": ["five"]}
    assert repo_servers(repo)["nine"] == B


def test_collect_splits_repo_ahead_by_local_presence(tmp_path):
    """케이스 8은 present(선택 필요), 케이스 2는 absent(restore가 설치) — 안내 문구가 다르다."""
    local = write_local(tmp_path, {"eight": ORIG})
    repo = write_repo(tmp_path, {"eight": B, "two": B})
    base_dir = write_base_blob(tmp_path, {"eight": ORIG})
    out = collect_mcp.collect(repo, str(tmp_path / "staging"),
                              claude_json_path=local, base_dir=base_dir)
    assert out["repo_ahead"] == {"present": ["eight"], "absent": ["two"]}


def test_collect_masks_secrets_in_repo_file(tmp_path):
    """레포 파일에 평문 비밀이 실려서는 안 된다."""
    local = write_local(tmp_path, {"c7": {"type": "http", "url": "u", "headers": {"K": "sk-real"}}})
    repo = write_repo(tmp_path, None)
    collect_mcp.collect(repo, str(tmp_path / "staging"),
                        claude_json_path=local, base_dir=write_base_blob(tmp_path, None))
    raw = open(os.path.join(repo, mc.BACKUP_RELPATH), encoding="utf-8").read()
    assert "sk-real" not in raw
    assert mc.SENTINEL in raw


def test_collect_raises_without_touching_repo_or_staging(tmp_path):
    """읽기 실패는 '서버 0개'가 아니다 — 레포도 스테이징도 그대로 둔다(9장 안전장치).

    예외를 잡아 skipped로 보고하는 주체는 main()이다(9장). 여기서는 삭제 판정을
    하지 않고 아무것도 쓰지 않는다는 것만 확인한다.
    """
    repo = write_repo(tmp_path, {"z": B})
    staging = str(tmp_path / "staging")
    with pytest.raises(mc.LocalConfigUnavailable):
        collect_mcp.collect(repo, staging,
                            claude_json_path=str(tmp_path / "missing.json"),
                            base_dir=write_base_blob(tmp_path, {"z": B}))
    assert repo_servers(repo) == {"z": B}
    assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))


def test_collect_cli_exits_zero_on_skip(tmp_path):
    """MCP 단계 실패로 backup 전체를 실패시키지 않는다 — 종료 코드 0."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"z": B})
    script = os.path.join(SCRIPTS_DIR, "sync-backup", "scripts", "collect_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), repo, str(tmp_path / "staging")],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_collect_cli_rejects_wrong_argument_count():
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다."""
    script = os.path.join(SCRIPTS_DIR, "sync-backup", "scripts", "collect_mcp.py")
    proc = subprocess.run([sys.executable, os.path.abspath(script)], capture_output=True, text=True)
    assert proc.returncode == 1
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q
```

기대: 수집 단계에서 `ModuleNotFoundError: No module named 'collect_mcp'`로 `errors`가 발생한다.

- [ ] **Step 3: `collect_mcp.py` 구현**

`plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py`를 새로 만든다:

```python
#!/usr/bin/env python3
"""로컬 user 스코프 MCP 설정을 레포와 키 단위 3-way 병합한다.

사용: collect_mcp.py <레포 경로> <스테이징 디렉토리>

`claude mcp list`를 호출하지 않고 stdin도 받지 않는다 — 데이터 소스는
~/.claude.json의 top-level mcpServers뿐이다(spec 3장).

base는 이 스크립트가 쓰지 않는다. 커밋 전에 실행되기 때문이다(7.5).
next_base를 스테이징 디렉토리에 mcp-servers.json이라는 이름으로 써 두고,
레포가 실제로 그 내용을 갖게 된 뒤 SKILL.md가
update_base.py <스테이징 디렉토리> mcp-servers.json 으로 옮긴다.
레포를 source_root로 넘기면 base ← 레포 파일 바이트가 되어 7.3을 위반한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402


def collect(repo_path, staging_dir, claude_json_path=None, base_dir=ss.BASE_DIR):
    """merge 결과를 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    스테이징을 먼저 쓴다 — 레포 쓰기가 실패하면 status가 skipped가 되고
    SKILL.md가 update_base.py를 호출하지 않으므로 base는 전진하지 않는다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo_file = os.path.join(repo_path, mc.BACKUP_RELPATH)
    repo = mc.load_backup(repo_file)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    result = mc.merge(local, repo, base)
    servers = result["servers"]
    os.makedirs(staging_dir, exist_ok=True)
    mc.dump_backup(result["next_base"], os.path.join(staging_dir, mc.BACKUP_RELPATH))
    mc.dump_backup(servers, repo_file)
    return {
        "status": "ok",
        "conflicts": {
            "repo_kept": [n for n in result["conflicts"] if n in servers],
            "repo_absent": [n for n in result["conflicts"] if n not in servers],
        },
        "deleted": result["deleted"],
        "local_stale": result["local_stale"],
        "repo_ahead": {
            "present": [n for n in result["repo_ahead"] if n in local],
            "absent": [n for n in result["repo_ahead"] if n not in local],
        },
    }


def main():
    if len(sys.argv) != 3:
        print("사용: collect_mcp.py <레포 경로> <스테이징 디렉토리>", file=sys.stderr)
        sys.exit(1)
    try:
        out = collect(sys.argv[1], sys.argv[2])
    except (mc.LocalConfigUnavailable, OSError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("MCP 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건, 직전 대비 7개 증가.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "feat(backup): collect_mcp.py 신설 — ~/.claude.json 기반 MCP 수집·병합" -- plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
```

---

## Task 5: sync-backup SKILL.md 재작성 + `parse_mcp.py` 삭제

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md`
- Delete: `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py`

**왜 — 이 task가 이 plan에서 가장 실수하기 쉬운 지점이다.** `collect_mcp.py`는 base를 쓰지 않으므로, **SKILL.md가 `update_base.py`를 호출하지 않으면 base는 영원히 부트스트랩되지 않는다.** 그 기기는 `merge(base=None)`의 합집합 degrade에 머물러 로컬 삭제가 영영 전파되지 않는다. 게다가 호출 지점이 **두 곳**이어야 한다(spec 7.5):

- ① 커밋·푸시 성공
- ② **커밋할 변경이 없음** — 레포가 이미 `next_base`와 정합하다는 뜻이다. **이 경로를 빠뜨리면 restore 없이 backup만 하는 기기에서 base가 영원히 부트스트랩되지 않는다.**

현재 SKILL.md의 base 갱신은 `git commit && git push` 성공 블록 **안에만** 있으므로 그 자리에 그대로 끼워 넣으면 안 된다. 푸시가 **실패하면 기록하지 않는다**(레포가 그 내용을 갖지 않으므로). MCP 단계가 `skipped`면 스테이징 파일이 없으므로 호출하지 않는다. 전역 게이트(`conflicts`/`local_stale`이 비었는지)는 **걸지 않는다** — 불변식 1.

- [ ] **Step 1: 동기화 대상 표와 주석 정정**

`plugins/claude-sync/skills/sync-backup/SKILL.md`의 동기화 대상 표에서 마지막 행

```
| `claude mcp list` → 추출 | `mcp-servers.json` | MCP 서버 이름과 URL |
```

을 다음으로 교체하고, 표 아래 문단 뒤에 설명 세 줄을 추가한다:

```
| `~/.claude.json` (user 스코프) → 추출 | `mcp-servers.json` | MCP 서버 설정 (비밀 값은 마스킹) |
```

```markdown
MCP 서버는 `~/.claude.json`의 top-level `mcpServers`(user 스코프)만 대상으로 한다. 계정 레벨 커넥터(`claude.ai *`), 플러그인이 제공하는 서버(`plugin:*`), project(`.mcp.json`)·local 스코프 서버는 애초에 그 객체에 없으므로 자동으로 제외된다. `headers`와 `env`의 **값만** `<REDACTED>`로 마스킹하고 키 이름은 보존한다.

`mcp-servers.json`은 파일 통째로 덮어쓰지 않고 **서버 이름 키 단위 3-way 병합** 대상이다. 다른 기기가 추가·변경한 서버는 이 기기의 백업으로 사라지지 않는다.

반면 `plugins.json`은 여전히 매 백업마다 통째로 새로 생성되어 덮어쓰인다(reconcile 대상이 아니다). 여러 기기에서 서로 다른 플러그인을 쓰면 마지막에 백업한 기기의 목록이 남는다.
```

- [ ] **Step 2: 6단계를 `collect_mcp.py` 호출로 재작성**

같은 파일의 `### 6. mcp-servers.json 생성` 절 전체(제목 아래 설명 문단과 `claude mcp list ... parse_mcp.py` 코드 블록)를 다음으로 교체한다:

````markdown
### 6. mcp-servers.json 생성 (키 단위 3-way 병합)

`~/.claude.json`의 user 스코프 `mcpServers`를 읽어 레포의 `mcp-servers.json`과 서버 이름 키 단위로 병합한다. `claude mcp list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"
rm -rf "$MCP_STAGING"
python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$MCP_STAGING" > /tmp/claude-sync-mcp.json
cat /tmp/claude-sync-mcp.json
```

출력 JSON의 `status`로 분기한다.

- `"skipped"`: `~/.claude.json`을 읽지 못한 것이다. **레포의 `mcp-servers.json`은 손대지 않았고 base도 전진시키지 않는다.** `reason`을 사용자에게 알리고 MCP 단계만 건너뛴다. **파일 동기화는 그대로 진행한다.**
- `"ok"`: 아래 항목을 결과 보고(12단계)에 포함하고 각각 다음 행동을 안내한다.

| 키 | 의미 | 안내 |
|---|---|---|
| `conflicts.repo_kept` | 케이스 9 — 양쪽이 바뀜 | "양쪽이 바뀌었습니다. 레포 값을 그대로 두었습니다. `/sync-restore`에서 해소하세요" |
| `conflicts.repo_absent` | 케이스 5 — 타 기기 삭제 + 로컬 수정 | "다른 기기가 삭제했는데 이 기기에서 수정했습니다. `/sync-restore` 먼저 실행하세요" |
| `local_stale` | 케이스 4 — 타 기기가 삭제, 로컬 잔존 | "`/sync-restore`에서 로컬을 정리하세요" |
| `repo_ahead.absent` | 케이스 2 — 타 기기가 추가 | "다른 기기가 추가했습니다. `/sync-restore`가 이 기기에 설치합니다" |
| `repo_ahead.present` | 케이스 8 — 타 기기가 **변경** | "다른 기기가 이 서버를 **변경**했습니다. `/sync-restore`에서 채택할지 선택이 필요합니다" |
| `deleted` | 이 기기에서 지운 서버 | 레포에서도 제거되었음을 알린다 |

`repo_ahead.present`(케이스 8)에 케이스 2와 같은 문구("restore를 실행하면 반영됩니다")를 쓰면 안 된다. restore는 케이스 8을 자동 반영하지 않으므로 그 안내는 사실이 아니고, 사용자가 빠져나갈 수 없는 루프에 갇힌다. 실제로 필요한 것은 사용자의 선택이다.

충돌이 있어도 백업 전체를 막지 않는다. 해당 서버만 건너뛴다.
````

- [ ] **Step 3: 10·11단계를 두 경로 모두에서 base를 갱신하도록 재작성**

같은 파일의 `### 10. 커밋 & 푸시` 절 본문(코드 블록 두 개와 사이의 설명)과 `### 11. base(.sync-state) 갱신` 절 본문을 다음으로 교체한다:

````markdown
### 10. 커밋 & 푸시

```bash
cd "${TMPDIR:-/tmp}/claude-sync-repo"
git add -A
git diff --cached --stat
```

변경 내용을 간단히 요약한 뒤, 아래 블록을 그대로 실행한다. **MCP base 갱신 호출이 "푸시 성공"과 "커밋할 변경 없음" 두 경로 모두에 있어야 한다** — 하나라도 빠지면 그 경로의 기기에서 base가 전진하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"
cd "$SYNC_REPO"
REPO_HAS_CONTENT=0

if git diff --cached --quiet; then
  echo "변경사항이 없습니다. 모든 설정이 최신 상태입니다."
  REPO_HAS_CONTENT=1          # 레포가 이미 이번 결과와 정합하다
elif git commit -m "sync: backup claude settings ($(date '+%Y-%m-%d %H:%M'))" && git push; then
  REPO_HAS_CONTENT=1
  mapfile -t PUSHED_RELS < <(python3 -c "
import json
data = json.load(open('/tmp/claude-sync-reconcile.json'))
for r in data.get('push', []):
    print(r)
")
  if [ "${#PUSHED_RELS[@]}" -gt 0 ]; then
    python3 "$SYNC_SCRIPTS/update_base.py" "$HOME/.claude" "${PUSHED_RELS[@]}"
  fi
else
  echo "푸시에 실패했습니다. base를 갱신하지 않습니다."
fi

# MCP base: 레포가 실제로 그 내용을 갖게 된 뒤에만 기록한다.
# 스테이징 파일은 collect_mcp.py가 status=ok일 때만 쓰므로, 파일 존재가 곧 'skip 아님'이다.
if [ "$REPO_HAS_CONTENT" = "1" ] && [ -f "$MCP_STAGING/mcp-servers.json" ]; then
  python3 "$SYNC_SCRIPTS/update_base.py" "$MCP_STAGING" mcp-servers.json
  echo "MCP base 갱신됨"
fi
```

### 11. base(.sync-state) 갱신 규칙

**파일**: 커밋 & 푸시에 성공한 경우에만 push된 각 파일의 base를 방금 올린 로컬 내용으로 갱신한다. **핵심 계약: push 성공 파일의 base ← 로컬 내용.**

**MCP 서버**: base는 레포 파일의 사본이 아니라 **"이 기기의 로컬이 동의한 부분"만 담는 파생 문서**다. `collect_mcp.py`가 계산한 `next_base`를 스테이징 디렉토리에 써 두었다가 여기서 옮긴다.

- `update_base.py "$MCP_STAGING" mcp-servers.json` — 올바른 호출.
- `update_base.py "$SYNC_REPO" mcp-servers.json` — **금지.** `base ← 레포 파일 바이트`가 되어, 타 기기가 추가·변경한 서버(케이스 2·8)의 값이 base에 실린다. 그러면 다음 백업이 그것을 "이 기기가 삭제했다"로 오독해 **다른 기기의 서버를 경고 없이 지운다.**
- 기록을 건너뛰는 경우는 **푸시 실패**와 **MCP 단계 skip** 둘뿐이다. 충돌(`conflicts`)이나 `local_stale`이 있다고 해서 전역으로 막지 않는다 — `next_base`가 이름 단위로 이미 그 서버의 base를 고정하고 있고, 전역 게이트는 나머지 서버의 base까지 얼려 정확도를 떨어뜨린다.
````

- [ ] **Step 4: `parse_mcp.py` 삭제**

```bash
cd /Users/bran/personal/claude-sync
grep -rn "parse_mcp" --include="*.md" --include="*.py" --include="*.sh" plugins .claude-plugin README.md README.ko.md
```

기대: 위 Step들을 마쳤다면 **출력이 비어 있다**(SKILL.md의 참조가 사라졌다). 비어 있음을 확인한 뒤:

```bash
git rm plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py
```

- [ ] **Step 5: bash 분기 드릴 — 세 경로를 실제로 실행해 검증**

임시 git 레포와 임시 HOME으로 10단계 블록의 분기를 실행한다. **실제 `~/.claude`나 사용자 레포는 건드리지 않는다.**

```bash
cd /Users/bran/personal/claude-sync
T=$(mktemp -d)
export SYNC_SCRIPTS="$PWD/plugins/claude-sync/skills/sync-backup/scripts"
mkdir -p "$T/home/.claude" "$T/repo"
echo '{"mcpServers":{"x":{"command":"a"}}}' > "$T/home/.claude.json"
git init -q --bare "$T/remote"
git -C "$T/repo" init -q && git -C "$T/repo" remote add origin "$T/remote"
git -C "$T/repo" config user.email t@example.com && git -C "$T/repo" config user.name tester
git -C "$T/repo" config commit.gpgsign false   # 전역 서명 설정이 켜져 있으면 드릴 커밋이 실패한다
git -C "$T/repo" commit -q --allow-empty -m init && git -C "$T/repo" push -q -u origin HEAD

drill() {   # $1 = 라벨
  rm -rf "$T/staging"
  HOME="$T/home" python3 "$SYNC_SCRIPTS/collect_mcp.py" "$T/repo" "$T/staging" > "$T/mcp.json"
  git -C "$T/repo" add -A
  if git -C "$T/repo" diff --cached --quiet; then
    RESULT="no-change"; HAS=1
  elif git -C "$T/repo" commit -q -m "drill" && git -C "$T/repo" push -q; then
    RESULT="pushed"; HAS=1
  else
    RESULT="push-failed"; HAS=0
  fi
  if [ "$HAS" = "1" ] && [ -f "$T/staging/mcp-servers.json" ]; then
    HOME="$T/home" python3 "$SYNC_SCRIPTS/update_base.py" "$T/staging" mcp-servers.json
  fi
  echo "$1: path=$RESULT status=$(python3 -c "import json;print(json.load(open('$T/mcp.json'))['status'])") base=$( [ -f "$T/home/.claude/.sync-state/base/mcp-servers.json" ] && echo written || echo none )"
}

show_base() { python3 -c "
import json
print(json.load(open('$T/home/.claude/.sync-state/base/mcp-servers.json'))['servers'])
"; }

drill "1회차(변경 있음)"
drill "2회차(변경 없음)"
rm -rf "$T/home/.claude/.sync-state"
drill "3회차(base 삭제 후 변경 없음 — 부트스트랩)"
echo "  drill4 직전 base: $(show_base)"
git -C "$T/repo" remote set-url origin "$T/nonexistent"
echo '{"mcpServers":{"x":{"command":"b"}}}' > "$T/home/.claude.json"
drill "4회차(푸시 실패)"
echo "  drill4 직후 base: $(show_base)"
rm -f "$T/home/.claude.json"
drill "5회차(MCP skip)"
echo "최종 레포 파일:" && cat "$T/repo/mcp-servers.json"
rm -rf "$T"
```

기대 출력:

```
1회차(변경 있음): path=pushed status=ok base=written
2회차(변경 없음): path=no-change status=ok base=written
3회차(base 삭제 후 변경 없음 — 부트스트랩): path=no-change status=ok base=written
  drill4 직전 base: {'x': {'command': 'a'}}
4회차(푸시 실패): path=push-failed status=ok base=written
  drill4 직후 base: {'x': {'command': 'a'}}
5회차(MCP skip): path=no-change status=skipped base=written
최종 레포 파일:
{
  "scope": "user",
  "servers": {
    "x": {
      "command": "b"
    }
  },
  "version": 2
}
```

(4회차에서 `git push`가 실패하며 `fatal: ... does not appear to be a git repository`를 stderr에 낸다 — 의도한 것이다.)

확인 포인트:
- **3회차**가 `base=written`이어야 한다 — "커밋할 변경 없음" 경로에서도 base가 부트스트랩된다는 뜻이다. `none`이면 Step 3의 `REPO_HAS_CONTENT=1`을 `git diff --cached --quiet` 분기에 넣지 않은 것이다.
- **4회차 직전/직후 base가 둘 다 `{'x': {'command': 'a'}}`** 여야 한다. `b`로 바뀌면 푸시 실패 경로가 base를 갱신한 것이다 — 레포가 갖지 않은 내용이 base에 실린다.
- **5회차의 `status=skipped`에서 레포 파일이 변하지 않아야 한다.** 마지막 `cat`은 `"command": "b"`인데, 이는 4회차의 `collect_mcp.py`가 쓴 값이 그대로 남은 것이다(4회차는 커밋·푸시만 실패했다). 5회차가 이 파일을 다시 건드렸다면 로컬을 못 읽는 상태에서 서버 목록을 지웠다는 뜻이므로 결함이다.

- [ ] **Step 6: 참조 정합성 확인**

```bash
grep -n "claude mcp list\|parse_mcp\|collect_mcp\|MCP_STAGING\|update_base" plugins/claude-sync/skills/sync-backup/SKILL.md
```

기대: `claude mcp list`와 `parse_mcp`는 **한 건도 나오지 않는다.** `collect_mcp.py`·`MCP_STAGING`·`update_base.py`는 여러 건 나오는데, 그중 **10단계 코드 블록 안에 `update_base.py` 호출이 정확히 두 번**(파일용 1 + MCP용 1) 있는지, MCP용 호출의 첫 인자가 `"$MCP_STAGING"`인지(`"$SYNC_REPO"`가 아닌지) 눈으로 확인한다.

- [ ] **Step 7: 전체 suite 실행**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건(테스트 수는 직전과 동일).

- [ ] **Step 8: Commit**

```bash
git add plugins/claude-sync/skills/sync-backup/SKILL.md
git commit -m "feat(backup): SKILL.md를 collect_mcp 기반으로 재작성, parse_mcp 삭제

base 갱신 호출을 푸시 성공 경로와 '커밋할 변경 없음' 경로 양쪽에 둔다.
후자를 빠뜨리면 restore 없이 backup만 하는 기기에서 base가 영원히
부트스트랩되지 않아 로컬 삭제가 전파되지 않는다." -- plugins/claude-sync/skills/sync-backup/SKILL.md plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py
```

---

## Task 6: `compare_mcp.py` 재작성 + sync-status SKILL.md

**Files:**
- Modify: `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py`
- Modify: `plugins/claude-sync/skills/sync-status/SKILL.md`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

**왜.** 현재 `compare_mcp.py`는 backup과 **다른 정규식**(`^(.+?):\s+`)을 쓴다. status는 11개를 인식하고 backup은 8개만 기록하므로 백업 직후에도 `/sync-status`가 영구적으로 차이를 보고한다(Bug #2). 판정의 단일 진입점을 `mcp_config`로 옮기면 이 드리프트가 구조적으로 사라진다. `diff`가 양쪽에 `redact`를 적용하므로 로컬 평문과 레포 마스킹이 `in_sync`로 수렴한다(불변식 4).

또한 **status의 어휘는 파일과 갈라야 한다.** SKILL.md의 "local_ahead / local_only: 로컬이 앞섬 → backup 시 push"는 MCP에는 틀리다 — 케이스 4(타 기기가 삭제, 로컬 잔존)의 서버도 `only_local`로 나오지만 backup에서 push되지 않고 `local_stale`로 보고된다. status는 base를 읽지 않으므로 둘을 구분할 수 없고, **읽기 전용 요약이라는 이 스킬의 성격을 유지하기 위해 구분하게 만들지도 않는다.**

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_scripts.py`의 import 블록에 `import compare_mcp  # noqa: E402`를 `import collect_mcp` 다음 줄에 추가하고, 파일 맨 끝에 추가한다:

```python
def test_compare_converges_when_local_secret_is_plaintext(tmp_path):
    """백업 직후 '동일'로 수렴한다 — Bug #2(영구 미수렴) 회귀."""
    repo_cfg = {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}
    local = write_local(tmp_path, {"c7": dict(repo_cfg, headers={"K": "sk-real"})})
    repo = write_repo(tmp_path, {"c7": repo_cfg})
    out = compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)
    assert out == {"status": "ok", "only_local": [], "only_repo": [], "changed": []}


def test_compare_reports_three_buckets(tmp_path):
    local = write_local(tmp_path, {"mine": A, "both": A})
    repo = write_repo(tmp_path, {"theirs": B, "both": B})
    out = compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)
    assert out["only_local"] == ["mine"]
    assert out["only_repo"] == ["theirs"]
    assert out["changed"] == ["both"]


def test_compare_preserves_command_with_spaces(tmp_path):
    """공백이 든 command도 온전히 비교된다 — Bug #1 회귀."""
    cfg = {"command": "/Applications/Safari Technology Preview.app/Contents/MacOS/safaridriver",
           "args": ["--mcp"]}
    local = write_local(tmp_path, {"safari-mcp-stp": cfg})
    repo = write_repo(tmp_path, {"safari-mcp-stp": cfg})
    out = compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)
    assert out["only_local"] == [] and out["changed"] == []


def test_compare_raises_instead_of_reporting_everything_as_only_repo(tmp_path):
    """읽기 실패를 '서버 0개'로 오인하면 레포의 서버가 전부 only_repo가 된다.

    main()이 이 예외를 잡아 skipped로 바꾼다 — 아래 CLI 테스트에서 확인한다.
    """
    repo = write_repo(tmp_path, {"z": B})
    with pytest.raises(mc.LocalConfigUnavailable):
        compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH),
                            claude_json_path=str(tmp_path / "missing.json"))


def test_compare_cli_exits_zero_on_skip(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"z": B})
    script = os.path.join(SCRIPTS_DIR, "sync-status", "scripts", "compare_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), os.path.join(repo, mc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q -k compare
```

기대: `AttributeError: module 'compare_mcp' has no attribute 'compare'`로 전부 실패한다(옛 스크립트는 모듈 로드 시 `sys.stdin`을 읽으려 하지 않으므로 import 자체는 성공하지만 함수가 없다).

- [ ] **Step 3: `compare_mcp.py`를 전면 교체**

`plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py`의 **내용을 통째로** 다음으로 바꾼다:

```python
#!/usr/bin/env python3
"""로컬 user 스코프 MCP 설정과 레포 백업의 차이를 보고한다 (읽기 전용).

사용: compare_mcp.py <레포의 mcp-servers.json 경로>

정규식도 `claude mcp list` 파이프도 쓰지 않는다. 판정은 mcp_config.diff 하나만
쓴다 — status와 backup이 서로 다른 파서를 갖는 것이 Bug #2의 원인이었다.
base는 읽지도 갱신하지도 않는다(읽기 전용 스킬).
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402


def compare(backup_path, claude_json_path=None):
    """{"status": "ok", "only_local": [...], "only_repo": [...], "changed": [...]}

    diff가 양쪽에 redact를 적용하므로 로컬 평문과 레포 마스킹이 in_sync로 수렴한다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    out = {"status": "ok"}
    out.update(mc.diff(local, repo))
    return out


def main():
    if len(sys.argv) != 2:
        print("사용: compare_mcp.py <레포의 mcp-servers.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = compare(sys.argv[1])
    except (mc.LocalConfigUnavailable, OSError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("MCP 비교 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: sync-status SKILL.md의 호출과 어휘 정정**

`plugins/claude-sync/skills/sync-status/SKILL.md`에서 MCP 비교 코드 블록

```bash
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  claude mcp list 2>/dev/null | python3 $SYNC_SCRIPTS/compare_mcp.py "$SYNC_REPO/mcp-servers.json"
fi
```

을 다음으로 교체한다:

````markdown
```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"
fi
```

출력 JSON의 `status`가 `"skipped"`면 `~/.claude.json`을 읽지 못한 것이다. `reason`을 알리고 MCP 비교만 생략한다 — 읽기 실패를 "서버 0개"로 오인해 레포의 서버를 전부 `only_repo`로 보고하지 않기 위해서다. 세 목록이 모두 비어 있으면 "MCP 서버: 동일"이라고 보고한다.
````

이어서 `### 3. 결과 요약`의 상태 분류 목록 **아래**에 MCP 전용 어휘를 추가하고, 맨 끝의 `plugin:` 문장을 교체한다:

```markdown
**MCP 서버의 어휘는 파일과 다르다.** 위의 "local_ahead / local_only: 로컬이 앞섬 → backup 시 push"는 MCP에 적용되지 않는다.

- **only_local**: 로컬에만 있음 — 신규이거나, 다른 기기가 삭제한 뒤 남은 것일 수 있습니다. `/sync-backup`이 판정합니다.
- **only_repo**: 레포에만 있음 — `/sync-restore`가 이 기기에 설치합니다.
- **changed**: 양쪽에 있으나 설정이 다름 — 어느 쪽이 앞선 것인지는 `/sync-backup`이 base를 읽어 판정합니다.

status는 base를 읽지 않으므로 케이스를 확정하지 않는다. 판정의 단일 진입점은 backup의 `merge` 하나다.

MCP 서버 비교 대상은 `~/.claude.json`의 user 스코프뿐이다. 계정 커넥터(`claude.ai *`), 플러그인 제공 서버(`plugin:*`), project·local 스코프 서버는 그 객체에 없으므로 자동으로 제외된다.
```

- [ ] **Step 5: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
grep -n "claude mcp list" plugins/claude-sync/skills/sync-status/SKILL.md
```

기대: 테스트 실패 0건(직전 대비 5개 증가). `grep`은 **아무것도 출력하지 않는다**.

- [ ] **Step 6: Commit**

```bash
git add plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py plugins/claude-sync/skills/sync-status/SKILL.md plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "fix(status): compare_mcp를 mcp_config.diff 기반으로 재작성, MCP 어휘 정정" -- plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py plugins/claude-sync/skills/sync-status/SKILL.md plugins/claude-sync/tests/test_mcp_scripts.py
```

---

## Task 7: `plan_mcp.py` — `plan` 모드

**Files:**
- Create: `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

**왜.** restore의 계획 수립을 스크립트로 옮긴다. **CLI 실행과 비밀 값 입력은 SKILL.md의 대화 흐름이 맡는다** — 비밀이 스크립트 인자에 남지 않게 하려는 것과, 7.4·7.7의 세 선택지가 대화형 확인이어야 하는 것이 같은 이유다(spec 8.3). 스크립트는 판정과 base 계산만 한다.

`plan` 출력에는 spec 5장의 버킷 9개 외에 **`configs`와 `secret_keys`를 함께 싣는다.** SKILL.md가 `claude mcp add-json <name> '<json>'`을 만들려면 레포 값이 필요한데, SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이 되살아난다 — 이 spec이 없애려는 드리프트의 형태 그대로다. `configs`는 `redact`를 거친 값이므로 비밀이 실리지 않는다.

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_scripts.py`의 import 블록에 `import plan_mcp  # noqa: E402`를 추가하고, 파일 맨 끝에 추가한다:

```python
def test_plan_emits_buckets_and_configs(tmp_path):
    """SKILL.md가 레포 파일을 직접 파싱하지 않도록 등록용 config를 함께 낸다."""
    repo_cfg = {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}
    local = write_local(tmp_path, {})
    repo = write_repo(tmp_path, {"c7": repo_cfg, "pw": {"command": "npx"}})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["status"] == "ok"
    assert out["add"] == ["pw"] and out["needs_secret"] == ["c7"]
    assert out["configs"]["pw"] == {"command": "npx"}
    assert out["secret_keys"]["c7"] == [("headers", "K")]   # JSON으로 나가면 배열이 된다


def test_plan_config_values_are_masked(tmp_path):
    """configs는 레포 값(마스킹됨)이다 — 계획 출력에 비밀이 실리지 않는다."""
    local = write_local(tmp_path, {})
    repo = write_repo(tmp_path, {"c7": {"type": "http", "url": "u", "headers": {"K": "sk-real"}}})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["configs"]["c7"]["headers"]["K"] == mc.SENTINEL


def test_plan_omits_configs_for_unrestorable(tmp_path):
    """등록을 시도하지 않는 항목에는 등록용 config를 주지 않는다."""
    local = write_local(tmp_path, {})
    repo = write_repo(tmp_path, {"claude.ai Notion": {"url": "u", "type": "stdio"}})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["unrestorable"] == ["claude.ai Notion"]
    assert out["configs"] == {}


def test_plan_uses_base_to_split_cases_7_8_9(tmp_path):
    local = write_local(tmp_path, {"seven": A, "eight": ORIG, "nine": A})
    repo = write_repo(tmp_path, {"seven": ORIG, "eight": B, "nine": B})
    base_dir = write_base_blob(tmp_path, {"seven": ORIG, "eight": ORIG, "nine": ORIG})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local, base_dir=base_dir)
    assert out["local_ahead"] == ["seven"]
    assert out["repo_ahead"] == ["eight"]
    assert out["both_changed"] == ["nine"]


def test_plan_cli_exits_zero_on_skip(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"z": B})
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), "plan", os.path.join(repo, mc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_plan_cli_rejects_unknown_mode():
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run([sys.executable, os.path.abspath(script), "bogus"],
                          capture_output=True, text=True)
    assert proc.returncode == 1
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q -k plan
```

기대: `ModuleNotFoundError: No module named 'plan_mcp'`로 수집 단계에서 에러.

- [ ] **Step 3: `plan` 모드만 구현**

`plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py`를 새로 만든다:

```python
#!/usr/bin/env python3
"""복원 계획 수립과 base 계산. 로컬 상태를 직접 바꾸지 않는다.

사용:
  plan_mcp.py plan <레포의 mcp-servers.json 경로>
    복원 계획 JSON을 stdout에 낸다 (버킷 9개 + configs + secret_keys).

CLI 실행과 비밀 값 입력은 SKILL.md의 대화 흐름이 맡는다(8.3) — 비밀이 스크립트
인자에 남지 않게 하려는 것과, 7.4·7.7의 세 선택지가 대화형 확인이어야 하는 것이
같은 이유다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402

# 등록·채택 대상 버킷. SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이 되살아나므로
# 등록에 쓸 config를 계획에 함께 실어 준다. 값은 redact를 거쳐 비밀이 없다.
NEEDS_CONFIG = ("add", "needs_secret", "repo_ahead", "both_changed")


def build_plan(backup_path, claude_json_path=None, base_dir=ss.BASE_DIR):
    """restore_plan 결과에 등록용 레포 config(마스킹됨)를 덧붙여 반환한다."""
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    plan = mc.restore_plan(local, repo, base)
    masked = mc.redact(repo)
    names = sorted({n for bucket in NEEDS_CONFIG for n in plan[bucket]})
    out = {"status": "ok"}
    out.update(plan)
    out["configs"] = {n: masked[n] for n in names}
    out["secret_keys"] = {
        n: mc.secret_keys(masked[n]) for n in names if mc.secret_keys(masked[n])
    }
    return out


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    else:
        print("사용: plan_mcp.py plan <레포의 mcp-servers.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = runner()
    except (mc.LocalConfigUnavailable, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("MCP 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건, 직전 대비 6개 증가.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "feat(restore): plan_mcp.py plan 모드 — 복원 계획과 등록용 config 출력" -- plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
```

---

## Task 8: `plan_mcp.py` — `apply-base` 모드

**Files:**
- Modify: `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

**왜.** restore가 로컬을 실제로 바꾼 뒤 base를 갱신하는 절차다. 한 줄이 아니라 다섯 단계이며(spec 8.3), **override 두 개를 빠뜨리면 두 종류의 "유지"가 고정점에 도달하지 못한다**(불변식 3).

```
① B ← next_base(복원 후 로컬, 이전 base, 레포)      # next_base가 입력에 redact를 적용한다
② 케이스 4·5에서 "유지"를 고른 이름 x  →  B에서 x를 삭제       (7.4 — 그 이력은 잊는다)
③ 케이스 8·9에서 "로컬 유지"를 고른 이름 x  →  B[x] ← 레포 값  (7.7 — 그 이력은 잊는다)
④ B를 <스테이징 디렉토리>/mcp-servers.json 으로 dump_backup
⑤ SKILL.md가 update_base.py <스테이징 디렉토리> mcp-servers.json 호출
```

②가 없으면 케이스 4가, ③이 없으면 케이스 8이 다음 백업에서 그대로 반복되어 **"유지"와 "나중에"가 구별되지 않는다.** 반대로 **"레포 값 채택"과 "제거"에는 override가 없다** — 채택 후에는 로컬이 레포 값에 동의하므로 ①이 스스로 전진시키고, 제거 후에는 이름이 L·R 어디에도 없으므로 ①이 스스로 base에서 지운다. `next_base`가 이미 하는 일을 override로 중복하지 않는 것이 규칙이다.

선택 결과 JSON에는 **이름과 선택만** 담긴다(`{"keep_stale": [...], "keep_local": [...]}`). 비밀 값은 절대 담기지 않으므로 스크립트 인자로 안전하게 넘길 수 있다.

- [ ] **Step 1: 실패하는 test 작성**

`plugins/claude-sync/tests/test_mcp_scripts.py` 맨 끝에 추가한다:

```python
def write_choices(tmp_path, payload):
    path = tmp_path / "choices.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_apply_base_advances_where_local_agrees(tmp_path):
    """① 기본 전진 — 로컬이 동의한 이름만 base로 간다."""
    local = write_local(tmp_path, {"x": A, "mine": A})
    repo = write_repo(tmp_path, {"x": A, "theirs": B})
    staging = str(tmp_path / "staging")
    out = plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging,
                              {"keep_stale": [], "keep_local": []},
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["status"] == "ok"
    staged = staged_servers(staging)
    assert staged == {"x": A}          # theirs는 로컬이 동의하지 않았고 이전 base에도 없다


def test_apply_base_keep_stale_forgets_the_name(tmp_path):
    """② 케이스 4 '유지' — base에서 이름을 지워 다음 backup이 push하게 만든다."""
    local = write_local(tmp_path, {"X": A, "y": A})
    repo = write_repo(tmp_path, {"y": A})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging,
                        {"keep_stale": ["X"]},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, {"X": A, "y": A}))
    assert "X" not in staged_servers(staging)


def test_apply_base_keep_local_moves_base_to_repo_value(tmp_path):
    """③ 케이스 8 '로컬 유지' — base ← 레포 값. 없으면 '나중에'와 구별되지 않는다."""
    local = write_local(tmp_path, {"x": ORIG})
    repo = write_repo(tmp_path, {"x": B})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging,
                        {"keep_local": ["x"]},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, {"x": ORIG}))
    assert staged_servers(staging)["x"] == B


def test_apply_base_without_choices_is_defer(tmp_path):
    """'나중에' — override 없음. 케이스 8의 base가 이전 값(로컬 값)에 머문다."""
    local = write_local(tmp_path, {"x": ORIG})
    repo = write_repo(tmp_path, {"x": B})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging, {},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, {"x": ORIG}))
    assert staged_servers(staging)["x"] == ORIG


def test_apply_base_never_writes_plaintext_secret(tmp_path):
    """복원 후 로컬은 평문이지만 base에는 SENTINEL만 들어간다 — next_base의 redact 계약."""
    cfg_plain = {"type": "http", "url": "u", "headers": {"K": "sk-real"}}
    cfg_masked = {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}
    local = write_local(tmp_path, {"c7": cfg_plain})
    repo = write_repo(tmp_path, {"c7": cfg_masked})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging, {},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, None))
    raw = open(os.path.join(staging, mc.BACKUP_RELPATH), encoding="utf-8").read()
    assert "sk-real" not in raw
    assert staged_servers(staging)["c7"] == cfg_masked   # base가 전진했다


def test_apply_base_cli_writes_staging_file(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"x": A}}), encoding="utf-8")
    repo = write_repo(tmp_path, {"x": A})
    staging = str(tmp_path / "staging")
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), "apply-base",
         os.path.join(repo, mc.BACKUP_RELPATH), staging,
         write_choices(tmp_path, {"keep_stale": [], "keep_local": []})],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "ok"
    assert staged_servers(staging) == {"x": A}


def test_apply_base_cli_skips_on_broken_choices(tmp_path):
    """선택 결과 JSON이 깨져도 restore 전체를 중단시키지 않는다 — 종료 코드 0."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    repo = write_repo(tmp_path, {"x": A})
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), "apply-base",
         os.path.join(repo, mc.BACKUP_RELPATH), str(tmp_path / "staging"), str(bad)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -q -k apply_base
```

기대: `AttributeError: module 'plan_mcp' has no attribute 'apply_base'`로 7개 실패.

- [ ] **Step 3: `apply_base`와 모드 분기 구현**

`plan_mcp.py`의 모듈 docstring 사용법에 한 줄을 추가한다:

```python
  plan_mcp.py apply-base <레포의 mcp-servers.json 경로> <스테이징 디렉토리> <선택 결과 JSON 경로>
    복원 후 로컬을 다시 읽어 next_base를 계산하고, 선택 override 두 개를 적용해
    스테이징 디렉토리에 기록한다. base 블롭 기록은 update_base.py가 한다(7.5).
```

`build_plan` 다음에 두 함수를 추가한다:

```python
def apply_base(backup_path, staging_dir, choices, claude_json_path=None, base_dir=ss.BASE_DIR):
    """복원 후 로컬 기준으로 다음 base를 계산하고 override 두 개를 적용해 스테이징에 쓴다.

    ① next_base(복원 후 로컬, 이전 base, 레포)  — 입력의 redact는 next_base가 한다
    ② keep_stale(케이스 4·5의 "유지")   → base에서 이름 삭제  (그 이력은 잊는다)
    ③ keep_local(케이스 8·9의 "로컬 유지") → base[x] ← 레포 값 (그 이력은 잊는다)

    override가 없으면 두 종류의 "유지"가 "나중에"와 구별되지 않아 고정점에 도달하지
    못한다(7.4·7.7). 반대로 "레포 값 채택"과 "제거"에는 override가 없다 —
    next_base가 이미 하는 일을 중복하지 않는 것이 규칙이다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    nb = mc.next_base(local, base, repo)
    keep_stale = [n for n in choices.get("keep_stale", []) if isinstance(n, str)]
    keep_local = [n for n in choices.get("keep_local", []) if isinstance(n, str)]
    for name in keep_stale:
        nb.pop(name, None)
    masked = mc.redact(repo)
    kept_local = []
    for name in keep_local:
        if name in masked:
            nb[name] = masked[name]
            kept_local.append(name)
    os.makedirs(staging_dir, exist_ok=True)
    mc.dump_backup(nb, os.path.join(staging_dir, mc.BACKUP_RELPATH))
    return {
        "status": "ok",
        "kept_stale": keep_stale,
        "kept_local": kept_local,
        "base_names": sorted(nb),
    }


def read_choices(path):
    """{"keep_stale": [...], "keep_local": [...]} — 이름과 선택만 담긴다. 비밀은 없다."""
    with open(path, "rb") as f:
        data = json.loads(f.read())
    if not isinstance(data, dict):
        raise ValueError("선택 결과 JSON의 최상위가 객체가 아님: %s" % path)
    return data
```

`main()`의 분기를 다음으로 교체한다:

```python
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    elif len(args) == 4 and args[0] == "apply-base":
        runner = lambda: apply_base(args[1], args[2], read_choices(args[3]))  # noqa: E731
    else:
        print("사용: plan_mcp.py plan <레포의 mcp-servers.json 경로>", file=sys.stderr)
        print("      plan_mcp.py apply-base <레포의 mcp-servers.json 경로>"
              " <스테이징 디렉토리> <선택 결과 JSON 경로>", file=sys.stderr)
        sys.exit(1)
```

(`json.JSONDecodeError`는 `ValueError`의 하위 클래스이므로 기존 `except` 절이 깨진 선택 JSON도 함께 잡는다.)

- [ ] **Step 4: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건, 직전 대비 7개 증가.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "feat(restore): plan_mcp.py apply-base 모드 — base override 두 개 적용" -- plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
```

---

## Task 9: 교대 시나리오 통합 테스트 (backup ↔ restore)

**Files:**
- Create: `plugins/claude-sync/tests/test_mcp_cycle.py`

**왜 — 이것이 이 plan에서 가장 중요한 검증 task다.** Task 3의 열 줄은 전부 *backup 반복*이다. 사용자가 7.4·7.7의 선택지를 고른 뒤 무슨 일이 일어나는지는 backup만 반복해서는 드러나지 않는다. **실제로 8.3의 base override 누락(케이스 8의 "로컬 유지"가 "나중에"와 구별되지 않는 결함)은 Task 3의 표를 전부 통과했다.** 표가 잡지 못한 이유가 교대 시나리오의 부재였다.

이 테스트는 모듈 함수가 아니라 **실제 스크립트를 서브프로세스로 호출**한다(`collect_mcp.py` → `update_base.py` → `plan_mcp.py plan` → `plan_mcp.py apply-base` → `update_base.py`). base 블롭 경로·스테이징 계약·`update_base.py` 재사용이 실제로 맞물리는지가 여기서만 드러나기 때문이다. `claude mcp add-json`/`remove`는 테스트 환경에서 실행할 수 없으므로 `~/.claude.json`을 직접 수정해 CLI의 결과를 흉내낸다.

- [ ] **Step 1: harness 작성**

`plugins/claude-sync/tests/test_mcp_cycle.py`를 새로 만든다:

```python
"""backup과 restore를 교대로 적용했을 때의 수렴을 스크립트 경유로 검증한다 (spec 13장).

Task 3의 backup 반복만으로는 사용자가 선택지를 고른 뒤의 전이가 드러나지 않는다.
실제로 8.3의 base override 누락은 backup 반복 표를 전부 통과했다.

claude mcp add-json/remove는 테스트에서 실행할 수 없으므로 ~/.claude.json을 직접
수정해 CLI의 결과를 흉내낸다. 그 밖의 모든 단계는 실제 스크립트를 호출한다.
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import mcp_config as mc  # noqa: E402

SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
COLLECT = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "collect_mcp.py"))
UPDATE_BASE = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "update_base.py"))
PLAN = os.path.abspath(os.path.join(SKILLS, "sync-restore", "scripts", "plan_mcp.py"))

A = {"command": "a"}
B = {"command": "b"}
ORIG = {"command": "o"}


class Device:
    """한 기기(임시 HOME) + 공유 레포 디렉토리."""

    def __init__(self, root, repo, servers):
        self.home = os.path.join(root, "home")
        self.repo = repo
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        self.set_local(servers)

    # --- 로컬 상태 (claude mcp add-json / remove의 결과를 흉내낸다) ---
    def set_local(self, servers):
        with open(os.path.join(self.home, ".claude.json"), "w", encoding="utf-8") as f:
            json.dump({"mcpServers": servers}, f)

    def local(self):
        with open(os.path.join(self.home, ".claude.json"), encoding="utf-8") as f:
            return json.load(f)["mcpServers"]

    def base(self):
        path = os.path.join(self.home, ".claude", ".sync-state", "base", mc.BACKUP_RELPATH)
        return mc.parse_base(open(path, "rb").read()) if os.path.exists(path) else None

    # --- 스크립트 호출 ---
    def _run(self, *args):
        proc = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                              env=dict(os.environ, HOME=self.home))
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    @property
    def staging(self):
        return os.path.join(self.home, "staging")

    def backup(self, push=True):
        """SKILL.md 6·10단계의 흐름: collect → (푸시 성공 시) update_base."""
        shutil.rmtree(self.staging, ignore_errors=True)
        report = json.loads(self._run(COLLECT, self.repo, self.staging))
        staged = os.path.join(self.staging, mc.BACKUP_RELPATH)
        if push and report["status"] == "ok" and os.path.exists(staged):
            self._run(UPDATE_BASE, self.staging, mc.BACKUP_RELPATH)
        return report

    def restore(self, adopt=(), keep_stale=(), keep_local=(), remove=()):
        """SKILL.md 6단계의 흐름: plan → CLI 실행 → apply-base → update_base."""
        backup_path = os.path.join(self.repo, mc.BACKUP_RELPATH)
        plan = json.loads(self._run(PLAN, "plan", backup_path))
        servers = self.local()
        for name in list(plan["add"]) + list(adopt):     # add-json
            servers[name] = plan["configs"][name]
        for name in remove:                              # mcp remove
            servers.pop(name, None)
        self.set_local(servers)
        choices_path = os.path.join(self.home, "choices.json")
        with open(choices_path, "w", encoding="utf-8") as f:
            json.dump({"keep_stale": list(keep_stale), "keep_local": list(keep_local)}, f)
        shutil.rmtree(self.staging, ignore_errors=True)
        self._run(PLAN, "apply-base", backup_path, self.staging, choices_path)
        self._run(UPDATE_BASE, self.staging, mc.BACKUP_RELPATH)
        return plan


def repo_servers(repo):
    return mc.load_backup(os.path.join(repo, mc.BACKUP_RELPATH))


def set_repo(repo, servers):
    """다른 기기가 레포를 바꾼 상황을 만든다."""
    mc.dump_backup(servers, os.path.join(repo, mc.BACKUP_RELPATH))


def make_device(tmp_path, servers, repo_init=None):
    root = str(tmp_path)
    repo = os.path.join(root, "repo")
    os.makedirs(repo, exist_ok=True)
    if repo_init is not None:
        set_repo(repo, repo_init)
    return Device(root, repo, servers)
```

- [ ] **Step 2: 케이스 8의 세 선택지 test 작성**

같은 파일 맨 끝에 이어서 추가한다:

```python
def test_case8_adopt_then_backup_converges_to_repo_value(tmp_path):
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()                                  # base 부트스트랩
    set_repo(dev.repo, {"x": B})                  # 타 기기가 변경
    assert dev.backup()["repo_ahead"]["present"] == ["x"]
    plan = dev.restore(adopt=["x"])
    assert plan["repo_ahead"] == ["x"]
    report = dev.backup()
    assert dev.local()["x"] == B
    assert repo_servers(dev.repo)["x"] == B
    assert dev.base()["x"] == B
    assert report["repo_ahead"] == {"present": [], "absent": []}
    assert dev.backup()["repo_ahead"] == {"present": [], "absent": []}


def test_case8_keep_local_pushes_local_value(tmp_path):
    """'로컬 유지'는 반드시 '나중에'와 다른 결과여야 한다 — override ③ 회귀."""
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()
    set_repo(dev.repo, {"x": B})
    dev.backup()
    dev.restore(keep_local=["x"])
    assert dev.base()["x"] == B                   # 그 이력은 잊는다
    report = dev.backup()
    assert repo_servers(dev.repo)["x"] == ORIG    # 케이스 7 경유로 push
    assert report["repo_ahead"] == {"present": [], "absent": []}
    dev.backup()
    assert repo_servers(dev.repo)["x"] == ORIG    # 이후 불변


def test_case8_defer_keeps_reporting(tmp_path):
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()
    set_repo(dev.repo, {"x": B})
    dev.backup()
    dev.restore()                                  # 무선택
    report = dev.backup()
    assert repo_servers(dev.repo)["x"] == B
    assert dev.local()["x"] == ORIG
    assert report["repo_ahead"]["present"] == ["x"]


def test_case9_three_choices(tmp_path):
    """채택 → in_sync / 로컬 유지 → 케이스 7 → push / 나중에 → 케이스 9 유지."""
    def setup(sub):
        dev = make_device(tmp_path / sub, {"Z": ORIG})
        dev.backup()
        set_repo(dev.repo, {"Z": B})               # 타 기기가 변경
        dev.set_local({"Z": A})                    # 이 기기도 변경 → 케이스 9
        assert dev.backup()["conflicts"]["repo_kept"] == ["Z"]
        return dev

    dev = setup("adopt")
    assert dev.restore(adopt=["Z"])["both_changed"] == ["Z"]
    assert dev.backup()["conflicts"] == {"repo_kept": [], "repo_absent": []}
    assert repo_servers(dev.repo)["Z"] == B

    dev = setup("keep")
    dev.restore(keep_local=["Z"])
    assert dev.backup()["conflicts"] == {"repo_kept": [], "repo_absent": []}
    assert repo_servers(dev.repo)["Z"] == A

    dev = setup("later")
    dev.restore()
    assert dev.backup()["conflicts"]["repo_kept"] == ["Z"]
    assert repo_servers(dev.repo)["Z"] == B


def test_case7_restore_does_not_touch_local(tmp_path):
    """케이스 7에는 선택지를 주지 않는다 — 미백업 로컬 변경이 파괴되면 안 된다."""
    dev = make_device(tmp_path, {"x": ORIG})
    dev.backup()
    dev.set_local({"x": A})                        # 아직 백업하지 않은 로컬 변경
    plan = dev.restore()
    assert plan["local_ahead"] == ["x"]
    assert dev.local()["x"] == A
```

- [ ] **Step 3: 케이스 4·마이그레이션·흐름 분기 test 작성**

같은 파일 맨 끝에 이어서 추가한다:

```python
def test_case4_keep_brings_server_back_and_stabilizes(tmp_path):
    """기기 A가 삭제, 기기 B가 '유지' — X가 레포로 복귀한 뒤 부활·소멸이 반복되지 않는다."""
    dev = make_device(tmp_path, {"X": A, "y": A})
    dev.backup()
    set_repo(dev.repo, {"y": A})                   # 기기 A가 X를 지우고 백업한 결과
    assert dev.backup()["local_stale"] == ["X"]
    plan = dev.restore(keep_stale=["X"])
    assert plan["local_stale"] == ["X"]
    assert "X" not in dev.base()
    dev.backup()
    assert sorted(repo_servers(dev.repo)) == ["X", "y"]
    report = dev.backup()
    assert report["local_stale"] == [] and report["deleted"] == []
    assert sorted(repo_servers(dev.repo)) == ["X", "y"]


def test_case4_remove_converges(tmp_path):
    dev = make_device(tmp_path, {"X": A, "y": A})
    dev.backup()
    set_repo(dev.repo, {"y": A})
    dev.backup()
    dev.restore(remove=["X"])
    assert "X" not in dev.local()
    report = dev.backup()
    assert report["local_stale"] == []
    assert sorted(repo_servers(dev.repo)) == ["y"]


def test_two_cycles_reach_fixed_point(tmp_path):
    """backup→restore를 반복하면 2주기째부터 레포·base·보고가 변하지 않는다.

    1주기째는 restore가 케이스 2의 서버를 실제로 설치하므로 2주기와 다를 수 있다 —
    그 설치는 정당한 상태 변화다. 고정점은 2주기와 3주기가 같은지로 판정한다.
    """
    dev = make_device(tmp_path, {"X": A, "x": ORIG})
    dev.backup()                                   # base 부트스트랩: X·x는 이 기기가 올렸다
    set_repo(dev.repo, {"x": B, "z": B})           # 타 기기: X 삭제, x 변경, z 추가
    snapshots = []
    for _ in range(3):
        report = dev.backup()
        plan = dev.restore()                       # 무선택
        snapshots.append((repo_servers(dev.repo), dev.base(), report,
                          {k: v for k, v in plan.items() if isinstance(v, list) and v}))
    assert snapshots[1] == snapshots[2], "2주기와 3주기가 다르다 — 고정점이 아니다"
    assert snapshots[2][2]["local_stale"] == ["X"]
    assert snapshots[2][2]["repo_ahead"]["present"] == ["x"]


def test_v1_migration_restore_reports_unrestorable_without_failures(tmp_path):
    """마이그레이션 직후 restore가 add-json 실패를 0건으로 유지한다 — 10장."""
    dev = make_device(tmp_path, {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}})
    v1 = [{"name": "claude.ai Notion", "url": "https://mcp.notion.com/mcp", "type": "stdio"},
          {"name": "context7", "url": "https://mcp.context7.com/mcp", "type": "HTTP"}]
    with open(os.path.join(dev.repo, mc.BACKUP_RELPATH), "w", encoding="utf-8") as f:
        json.dump(v1, f)
    plan = dev.restore()
    assert sorted(plan["unrestorable"]) == ["claude.ai Notion", "context7"]
    assert plan["add"] == [] and plan["needs_secret"] == []
    dev.backup()
    assert sorted(repo_servers(dev.repo)) == ["claude.ai Notion", "context7", "playwright"]


def test_backup_without_changes_still_bootstraps_base(tmp_path):
    """'커밋할 변경 없음' 경로에서도 base가 기록되어야 삭제가 전파된다."""
    dev = make_device(tmp_path, {"x": A})
    dev.backup()
    assert dev.base() == {"x": A}
    dev.backup()                                   # 두 번째는 레포에 변경이 없다
    assert dev.base() == {"x": A}
    dev.set_local({})
    assert dev.backup()["deleted"] == ["x"]
    assert repo_servers(dev.repo) == {}


def test_backup_without_push_does_not_advance_base(tmp_path):
    """푸시 실패 — 레포가 그 내용을 갖지 않으므로 base를 기록하지 않는다."""
    dev = make_device(tmp_path, {"x": A})
    dev.backup(push=False)
    assert dev.base() is None


def test_skipped_backup_touches_neither_repo_nor_base(tmp_path):
    """MCP 단계 skip — 레포 파일 불변, base 불변."""
    dev = make_device(tmp_path, {"x": A})
    dev.backup()
    os.remove(os.path.join(dev.home, ".claude.json"))
    report = dev.backup()
    assert report["status"] == "skipped"
    assert repo_servers(dev.repo) == {"x": A}
    assert dev.base() == {"x": A}
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

```bash
uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_cycle.py -q
```

기대: 새 파일의 테스트 12개가 전부 통과한다. 실패하면 **해당 시나리오의 처방이 spec 7.4·7.7·8.3과 어긋난 것이다.** 특히 `test_case8_keep_local_pushes_local_value`가 실패하면 Task 8의 override ③이 빠졌거나 잘못 적용된 것이고, `test_backup_without_changes_still_bootstraps_base`가 실패하면 harness가 아니라 `collect_mcp.py`의 스테이징 계약이 틀린 것이다.

- [ ] **Step 5: 전체 suite 실행**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건, 직전 대비 12개 증가.

- [ ] **Step 6: Commit**

```bash
git add plugins/claude-sync/tests/test_mcp_cycle.py
git commit -m "test(mcp): 스크립트 경유 backup↔restore 교대 시나리오 검증" -- plugins/claude-sync/tests/test_mcp_cycle.py
```

---

## Task 10: sync-restore SKILL.md 재작성

**Files:**
- Modify: `plugins/claude-sync/skills/sync-restore/SKILL.md`

**왜.** 현재 6단계는 `claude mcp add <name> <url> --transport ...`를 쓰는데, 이 명령으로는 **stdio 복원이 불가능하다**(`command`/`args`를 전달할 수 없다). `add-json`으로 바꾸고, 7.4·7.7의 세 선택지 대화, 비밀 값 입력, `remove`→`add-json` 2단계와 실패 경고, `apply-base` + `update_base.py` 호출을 넣는다.

주의할 점 셋:
- **`update_base.py`는 `sync-backup/scripts`에 있다.** restore SKILL.md의 `$SYNC_SCRIPTS`는 `sync-restore/scripts`를 가리키므로 별도 변수가 필요하다. base를 기록하는 주체는 `update_base.py` 하나뿐이며 새 스크립트를 만들지 않는다(spec 7.5).
- **`add-json`은 기존 이름을 덮어쓰지 못한다**(불변식 5). 채택은 `remove` → `add-json` 2단계이고, 그 사이가 위험 구간이므로 **JSON을 먼저 완성한다.**
- **레포의 비밀 값은 항상 `<REDACTED>`다.** 그대로 로컬에 쓰면 인증이 깨진 서버가 남는다. 값을 받아 채우고, 사용자가 건너뛰면 **등록하지 않는다.**

- [ ] **Step 1: 0단계에 `update_base.py` 경로 탐색 추가**

`plugins/claude-sync/skills/sync-restore/SKILL.md`의 `### 0. 스크립트 경로 확인` 코드 블록을 다음으로 교체한다:

````markdown
```bash
SYNC_SCRIPTS=$(find ~/.claude -path "*/sync-restore/scripts" -type d 2>/dev/null | head -1)
SYNC_BACKUP_SCRIPTS=$(find ~/.claude -path "*/sync-backup/scripts" -type d 2>/dev/null | head -1)
echo "Scripts: $SYNC_SCRIPTS"
echo "Backup scripts: $SYNC_BACKUP_SCRIPTS"
```

`SYNC_BACKUP_SCRIPTS`가 필요한 이유는 base 블롭을 기록하는 주체가 `sync-backup/scripts/update_base.py` **하나뿐**이기 때문이다(파일 쪽과 같은 규칙을 공유한다).
````

- [ ] **Step 2: 6단계를 계획 수립 + 자동 적용 절로 재작성**

`### 6. MCP 서버 복원 (additive, plugin: 제외)` 절 전체를 다음으로 교체한다:

````markdown
### 6. MCP 서버 복원

`~/.claude.json`의 user 스코프 `mcpServers`와 레포 `mcp-servers.json`을 비교해 계획을 세운다. `claude mcp list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"
python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json" > /tmp/claude-sync-mcp-plan.json
cat /tmp/claude-sync-mcp-plan.json
```

`status`가 `"skipped"`면 `reason`을 알리고 MCP 단계 전체를 건너뛴다(파일 복원은 그대로 진행한다). `"ok"`면 버킷별로 처리한다.

| 버킷 | 처방 |
|---|---|
| `add` | 그대로 등록한다 (6-1) |
| `needs_secret` | 값을 물어 채운 뒤 등록한다. 건너뛰면 등록하지 않는다 (6-2) |
| `unrestorable` | 등록을 **시도하지 않고 한 번만** 안내한다. 실패 건수로 세지 않는다 (6-3) |
| `in_sync` | 아무것도 하지 않는다 |
| `local_only` | 보고만 — "다음 `/sync-backup`에서 레포로 올라갑니다" |
| `local_ahead` | 보고만 — "이 기기의 변경이 아직 백업되지 않았습니다. `/sync-backup`을 실행해 올리세요". **선택지를 주지 않는다** |
| `repo_ahead` | 세 선택지 (6-4) |
| `both_changed` | 세 선택지 + "양쪽이 모두 바뀌었습니다" 안내 (6-4) |
| `local_stale` | 세 선택지 (6-5) |

#### 6-1. `add` — 그대로 등록

`configs`에 등록용 JSON이 이미 들어 있다. 레포 파일을 직접 파싱하지 않는다.

```bash
NAME="<서버 이름>"
SERVER_JSON=$(python3 -c "
import json, sys
plan = json.load(open('/tmp/claude-sync-mcp-plan.json'))
print(json.dumps(plan['configs'][sys.argv[1]]))
" "$NAME")
claude mcp add-json "$NAME" "$SERVER_JSON" --scope user
```

`--scope user`를 **반드시** 붙인다. 기본값이 `local`이라 빠뜨리면 현재 디렉토리 전용으로 등록된다. 하나가 실패해도 나머지는 계속 진행하고, 마지막에 실패 목록을 모아 보고한다.

#### 6-2. `needs_secret` — 값을 받아 채운 뒤 등록

`secret_keys`에 어떤 필드의 어떤 키가 필요한지 들어 있다(예: `[["headers", "CONTEXT7_API_KEY"]]`).

값을 묻기 전에 **반드시 다음을 고지한다**: "`claude mcp add-json`은 JSON을 위치 인자로만 받으므로, 입력한 값이 프로세스 목록과 이 대화 기록에 남습니다. 현재 CLI에 대안이 없습니다."

```bash
python3 - <<'PY' > /tmp/claude-sync-mcp-one.json
import json
plan = json.load(open('/tmp/claude-sync-mcp-plan.json'))
cfg = plan['configs']['<서버 이름>']
cfg['headers']['<KEY>'] = '<사용자가 입력한 값>'   # secret_keys의 항목마다 반복
print(json.dumps(cfg))
PY
claude mcp add-json '<서버 이름>' "$(cat /tmp/claude-sync-mcp-one.json)" --scope user
rm -f /tmp/claude-sync-mcp-one.json
```

**사용자가 입력을 건너뛰면 그 서버는 등록하지 않는다.** 인증이 깨진 서버를 만드는 것보다 낫다.

#### 6-3. `unrestorable` — 시도하지 않고 한 번만 안내

이름이 CLI 규칙(영숫자·하이픈·언더스코어)을 어겼거나, config에 `command`도 `url`+`type`(http/sse)도 없는 항목이다. 옛 v1 형식에서 승격된 항목이 정확히 이 형태다. 목록을 한 번만 보여주고 "이 항목들은 옛 형식이거나 이름 규칙에 맞지 않아 복원할 수 없습니다"라고 안내한다. **실패 건수로 세지 않는다.**

#### 6-4. `repo_ahead`(케이스 8) · `both_changed`(케이스 9) — 세 선택지

서버마다 로컬 값과 레포 값의 차이를 보여주고 셋 중 하나를 고르게 한다.

- `repo_ahead`: "다른 기기가 이 서버를 변경했습니다."
- `both_changed`: "**양쪽이 모두 바뀌었습니다. 채택하면 이 기기의 변경이 사라집니다.**"

| 선택 | 동작 | 도달 상태 |
|---|---|---|
| **레포 값 채택** | 아래 5단계 | 양쪽 레포 값 |
| **로컬 유지** | 로컬 그대로 두고 이름을 `keep_local`에 넣는다 | 다음 backup이 로컬 값을 push |
| **나중에** | 아무것도 하지 않는다 | 변화 없음, 다시 보고 |

**"레포 값 채택" 5단계 — 순서를 바꾸면 안 된다.**

```
1. 그 이름이 unrestorable 목록에 있으면 채택 선택지를 제시하지 않는다.
2. secret_keys에 있으면 **먼저** 값을 물어 넣을 JSON을 완성한다(6-2와 같은 흐름).
   건너뛰면 여기서 중단하고 "나중에"와 동일하게 처리한다(로컬 불변, base 불변).
3. claude mcp remove <name> -s user
4. claude mcp add-json <name> '<완성된 JSON>' --scope user
5. 4가 실패하면 서버가 로컬에서 사라진 상태로 남는다.
```

`add-json`은 이미 있는 이름에 대해 `already exists`로 exit 1이므로 3이 필요하고, remove 뒤에 값을 묻다가 사용자가 중단하면 아무것도 채택되지 않은 채 서버만 사라지므로 2가 3보다 앞이다. **5의 실패는 크게 경고하고 넣으려던 JSON을 그대로 보여주어** 사용자가 직접 다시 등록할 수 있게 한다. 이때 base는 건드리지 않는다.

기존 로컬 비밀을 조용히 이월하지 않는다 — 레포 값이 바뀐 이유가 키 교체일 수 있고, 그때 이월은 "동작하는 것처럼 보이다가 인증에서 실패하는" 더 나쁜 상태를 만든다.

**"레포 값 채택"에는 base override가 없다.** 채택 후에는 로컬이 레포 값에 동의하므로 6-6의 `apply-base`가 스스로 전진시킨다.

#### 6-5. `local_stale`(케이스 4·5) — 세 선택지

레포에서 사라졌지만 로컬에 남아 있는 서버다. 안내 문구를 둘로 가른다.

- 케이스 4(로컬 값이 base와 같음): "다른 기기가 이 서버를 삭제했습니다."
- 케이스 5(로컬에서 수정도 했음): "다른 기기가 삭제했는데 이 기기에서 수정했습니다."

| 선택 | 동작 | 도달 상태 |
|---|---|---|
| **제거** | `claude mcp remove <name> -s user` | 레포·로컬 모두 없음 |
| **유지** | 로컬 그대로 두고 이름을 `keep_stale`에 넣는다 | 다음 backup이 레포로 되돌린다 |
| **나중에** | 아무것도 하지 않는다 | 변화 없음, 다시 보고 |

"유지"가 base에서 이름을 지우는 것은 **"그 이력은 잊는다"는 명시적 선언**이다. 이 동작이 없으면 케이스 4가 영원히 유지되어 사용자가 그 서버를 레포에 되돌릴 방법이 없다.

#### 6-6. base 갱신

**사용자가 아무 선택도 하지 않았어도 실행한다.** 무선택은 "이전 base 유지"로 계산되므로 결과가 달라지지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"

# 6-4에서 "로컬 유지"를, 6-5에서 "유지"를 고른 이름만 적는다.
# 나머지 선택(제거·채택·나중에)에는 base override가 필요 없다.
# 이 파일에는 이름과 선택만 들어간다 — 비밀 값은 절대 담지 않는다.
cat > /tmp/claude-sync-mcp-choices.json << 'EOF'
{"keep_stale": [], "keep_local": []}
EOF

rm -rf "$MCP_STAGING"
python3 "$SYNC_SCRIPTS/plan_mcp.py" apply-base "$SYNC_REPO/mcp-servers.json" "$MCP_STAGING" /tmp/claude-sync-mcp-choices.json
if [ -f "$MCP_STAGING/mcp-servers.json" ]; then
  python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$MCP_STAGING" mcp-servers.json
  echo "MCP base 갱신됨"
fi
rm -f /tmp/claude-sync-mcp-choices.json
```

`apply-base`는 `~/.claude.json`을 **다시 읽어** 계산하므로, 위 6-1~6-5의 CLI 실행이 **모두 끝난 뒤**에 호출해야 한다. `update_base.py`에 `"$SYNC_REPO"`를 넘기면 안 된다 — `base ← 레포 파일 바이트`가 되어 타 기기의 서버를 다음 백업이 삭제한다.
````

- [ ] **Step 3: 7단계 결과 보고 항목 갱신**

같은 파일 `### 7. 결과 보고`의 MCP 관련 항목 세 줄

```markdown
- **추가한 MCP 서버** (있으면)
- **인증이 필요한 MCP 서버** (있으면)
- **설치/등록 실패한 항목** (있으면)
```

을 다음으로 교체한다:

```markdown
- **등록한 MCP 서버** (`add` / `needs_secret`에서 값을 받아 등록한 것)
- **건너뛴 MCP 서버**: 비밀 값 입력을 건너뛴 것, `unrestorable`(옛 형식·이름 규칙 위반 — 실패로 세지 않는다)
- **해소한 MCP 충돌**: 서버명과 선택(채택 / 로컬 유지 / 유지 / 제거 / 나중에)
- **`local_ahead` MCP 서버** → "올리려면 `/sync-backup`을 실행하세요"
- **등록 실패한 MCP 서버**: `add-json`이 실패한 것. "레포 값 채택"의 `remove` **이후** 실패는 서버가 로컬에서 사라진 상태이므로 넣으려던 JSON과 함께 크게 경고한다
```

- [ ] **Step 4: 모델 설명 절에 MCP 문단 추가**

같은 파일 `## 모델 (git-like, pull-only)` 절의 파일별 판정 목록 **아래**에 추가한다:

```markdown
**MCP 서버는 파일이 아니라 서버 이름 키 단위로 판정한다.** 로컬 `~/.claude.json`(user 스코프) / 레포 `mcp-servers.json` / base의 3-way이며, 레포에만 있는 서버는 등록하고, 양쪽이 다르거나 한쪽에서 사라진 서버는 **서버마다 물어본다**(제거·유지·나중에 / 레포 값 채택·로컬 유지·나중에). restore는 로컬 서버를 임의로 지우거나 덮어쓰지 않는다.
```

- [ ] **Step 5: 참조 정합성 확인**

```bash
grep -n "claude mcp add \|claude mcp list\|--transport" plugins/claude-sync/skills/sync-restore/SKILL.md
grep -c "add-json" plugins/claude-sync/skills/sync-restore/SKILL.md
grep -n "SYNC_BACKUP_SCRIPTS" plugins/claude-sync/skills/sync-restore/SKILL.md
```

기대: 첫 `grep`은 **아무것도 출력하지 않는다**(옛 명령이 남아 있지 않다). 둘째는 4 이상. 셋째는 3건(0단계의 정의와 `echo`, 6-6의 사용).

- [ ] **Step 6: 전체 suite 실행**

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
```

기대: 실패 0건.

- [ ] **Step 7: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/SKILL.md
git commit -m "feat(restore): SKILL.md 6단계를 add-json 기반 대화 흐름으로 재작성" -- plugins/claude-sync/skills/sync-restore/SKILL.md
```

---

## Task 11: 사용자 문서 4개 정정

**Files:**
- Modify: `README.md`, `README.ko.md`
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md`, `backup-readme.ko.md`

**왜.** 동기화 대상 표는 **다섯 곳**에 흩어져 있고(SKILL.md는 Task 5에서 이미 고쳤다), 한 곳만 고치면 나머지가 계속 옛 서술을 말한다. 특히 `README.ko.md`의 "**로컬 파일은 절대 자동으로 덮어쓰지 않습니다**"는 파일 단위 보장인데 `plugins.json`이 그 예외이며, **이 예외는 어느 문서에도 적혀 있지 않다.** 이번에 고치지 않는 결함이므로 사실대로 명시한다(spec 12장).

- [ ] **Step 1: `README.md` 갱신**

`## What Gets Synced` 목록의 마지막 줄

```markdown
- `claude mcp list` -> `mcp-servers.json` — MCP server list (name, URL, type)
```

을 교체하고 목록 아래에 문단을 추가한다:

```markdown
- `~/.claude.json` (user scope) -> `mcp-servers.json` — MCP server configs, with secret values masked

Only the top-level `mcpServers` object in `~/.claude.json` (the *user* scope) is synced. Account-level connectors (`claude.ai *`), plugin-provided servers (`plugin:*`), and project/local scope servers (`.mcp.json`, `projects[*].mcpServers`) are not in that object, so they are excluded automatically. Values under `headers` and `env` are replaced with `<REDACTED>` while the key names are preserved, so a restore knows which credentials to ask for. Keys passed through `args` or a URL query string are **not** masked.
```

`## Sync Behavior Model (v2.0.0+)` 제목을 `## Sync Behavior Model (v3.0.0+)`으로 바꾸고, 그 목록 끝에 두 줄을 추가한다:

```markdown
- **MCP servers merge per server name.** `mcp-servers.json` is reconciled key by key, so a backup from one machine never drops servers that only exist on another. Deletions do propagate, and `/sync-restore` asks per server before removing anything locally.
- **`plugins.json` is still overwritten wholesale.** It is not part of the per-file reconcile, so the last machine to back up wins for the plugin list. This is a known limitation.
```

`### Restore on a new device` 이하의 `/sync-restore` 설명(`## Usage` 절)에 한 줄을 추가한다:

```markdown
If a server was deleted or changed on another machine, `/sync-restore` asks about it one server at a time (remove / keep / later, or adopt repo value / keep local / later).
```

`## Safety`의 두 번째 항목을 다음으로 교체한다:

```markdown
- **Sensitive data protection**: The raw `settings.json` is never pushed — only the plugin list is extracted. MCP server configs are pushed with `headers`/`env` values masked as `<REDACTED>`
```

- [ ] **Step 2: `README.ko.md` 갱신**

`## 동기화 대상` 목록의 마지막 줄을 교체하고 아래에 문단을 추가한다:

```markdown
- `~/.claude.json` (user 스코프) -> `mcp-servers.json` — MCP 서버 설정 (비밀 값은 마스킹)

MCP 서버는 `~/.claude.json`의 top-level `mcpServers`(user 스코프)만 동기화합니다. 계정 레벨 커넥터(`claude.ai *`), 플러그인이 제공하는 서버(`plugin:*`), project·local 스코프 서버(`.mcp.json`, `projects[*].mcpServers`)는 그 객체에 없으므로 자동으로 제외됩니다. `headers`와 `env`의 **값만** `<REDACTED>`로 마스킹하고 키 이름은 남기므로, 복원할 때 어떤 자격 증명이 필요한지는 전달되고 값은 유출되지 않습니다. 다만 `args`나 URL 쿼리스트링에 담긴 키는 마스킹되지 않습니다.
```

`## 동작 모델 (v2.0.0+)` 제목을 `## 동작 모델 (v3.0.0+)`으로 바꾸고 목록 끝에 두 줄을 추가한다:

```markdown
- **MCP 서버는 서버 이름 키 단위로 병합됩니다.** `mcp-servers.json`은 파일 통째로 덮어쓰지 않으므로, 한 기기의 백업이 다른 기기에만 있는 서버를 지우지 않습니다. 삭제는 전파되지만 로컬 제거는 `/sync-restore`가 서버마다 물어본 뒤에만 이루어집니다.
- **`plugins.json`은 여전히 매 백업마다 통째로 덮어쓰입니다.** 파일별 reconcile 대상이 아니라서 마지막에 백업한 기기의 플러그인 목록이 남습니다. 알려진 한계입니다.
```

`## 안전 장치`의 첫 두 항목을 다음으로 교체한다:

```markdown
- **충돌 감지**: 마지막 공유 base 이후 양쪽에서 변경된 파일만 충돌로 표시하며, 로컬 파일은 절대 자동으로 덮어쓰지 않습니다. **예외: `plugins.json`은 백업할 때마다 새로 생성되어 레포의 내용을 덮어씁니다.**
- **민감 정보 보호**: `settings.json` 원본은 레포에 올리지 않고 플러그인 목록만 추출하며, MCP 서버 설정은 `headers`/`env` 값을 `<REDACTED>`로 마스킹해 올립니다
```

`## 사용 흐름`의 `/sync-restore` 설명에 한 줄을 추가한다:

```markdown
다른 기기에서 서버를 지웠거나 바꿨다면 `/sync-restore`가 서버마다 물어봅니다(제거/유지/나중에, 레포 값 채택/로컬 유지/나중에).
```

- [ ] **Step 3: 백업 레포 README 두 개 갱신**

`plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md`의 `## Contents` 목록에서

```markdown
- `mcp-servers.json` — MCP server list (name, URL, type)
```

을 교체하고 목록 아래에 문단을 추가한다:

```markdown
- `mcp-servers.json` — MCP server configs from `~/.claude.json` (user scope), merged per server name

### About `mcp-servers.json`

Values under `headers` and `env` are stored as `<REDACTED>`; the key names are kept so a restore knows what to ask for. **Secrets passed through `args` or a URL query string are not masked** — keep this repository private. When you restore, `/sync-restore` prompts for each masked value; skipping a prompt leaves that server unregistered rather than creating one with broken auth.

This file is merged **per server name**, so backing up from one machine will not drop servers that only exist on another. `plugins.json`, in contrast, is regenerated and overwritten on every backup.
```

`backup-readme.ko.md`의 `## 포함된 내용` 목록에서

```markdown
- `mcp-servers.json` — MCP 서버 목록 (이름, URL, 타입)
```

을 교체하고 목록 아래에 문단을 추가한다:

```markdown
- `mcp-servers.json` — `~/.claude.json`(user 스코프)의 MCP 서버 설정, 서버 이름 키 단위 병합

### `mcp-servers.json`에 대하여

`headers`와 `env`의 값은 `<REDACTED>`로 저장되고 키 이름은 남습니다 — 복원할 때 무엇을 물어야 하는지 알기 위해서입니다. **`args`나 URL 쿼리스트링에 담긴 비밀은 마스킹되지 않으므로** 이 레포는 private으로 두세요. 복원 시 `/sync-restore`가 마스킹된 값을 하나씩 물어보며, 입력을 건너뛰면 인증이 깨진 서버를 만들지 않고 그 서버를 등록하지 않습니다.

이 파일은 **서버 이름 키 단위로 병합**되므로 한 기기에서 백업해도 다른 기기에만 있는 서버가 사라지지 않습니다. 반면 `plugins.json`은 매 백업마다 새로 생성되어 덮어쓰입니다.
```

- [ ] **Step 4: 다섯 곳이 모두 정정되었는지 확인**

```bash
cd /Users/bran/personal/claude-sync
grep -rn "claude mcp list" README.md README.ko.md plugins/claude-sync/skills/
grep -rn "이름, URL, 타입\|name, URL, type" README.md README.ko.md plugins/claude-sync/skills/
grep -rln "plugins.json" README.md README.ko.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.ko.md
```

기대: 앞의 두 `grep`은 **아무것도 출력하지 않는다**. 세 번째는 네 파일이 모두 나온다(덮어쓰기 한계가 각 문서에 명시되었다).

- [ ] **Step 5: Commit**

```bash
git add README.md README.ko.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.ko.md
git commit -m "docs: MCP 데이터 소스·마스킹·키 단위 병합 반영, plugins.json 한계 명시" -- README.md README.ko.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md plugins/claude-sync/skills/sync-backup/scripts/backup-readme.ko.md
```

---

## Task 12: 버전 3.0.0

**Files:**
- Modify: `plugins/claude-sync/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**왜.** **역호환이 없다.** 구버전 `compare_mcp.py`는 `[s["name"] for s in backed]`로 배열을 가정하므로 v2 객체 스키마를 만나면 `TypeError`로 죽는다. 한 기기가 3.0.0으로 백업하면 2.0.0 기기의 `/sync-status`가 깨지므로 MAJOR 상승이 필요하다(spec 10장).

- [ ] **Step 1: 두 파일의 버전 변경**

`plugins/claude-sync/.claude-plugin/plugin.json`의 `"version": "2.0.0"` → `"version": "3.0.0"`.
`.claude-plugin/marketplace.json`의 `"version": "2.0.0"` → `"version": "3.0.0"`.

- [ ] **Step 2: 확인**

```bash
grep -rn '"version"' .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
grep -rn "v2.0.0\|v3.0.0" README.md README.ko.md
```

기대: 첫 `grep`은 두 파일 모두 `"3.0.0"`. 둘째는 Task 11에서 바꾼 `v3.0.0+` 두 건만 나온다(`v2.0.0`이 남아 있으면 Task 11이 덜 된 것이다).

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
git commit -m "chore: 3.0.0 — MCP 백업 스키마 v2는 역호환되지 않는다" -- .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
```

---

## Task 13: 실환경 스모크 (spec 13장 통합 시나리오)

**Files:** 없음 (검증 전용)

**왜.** 여기까지의 테스트는 전부 합성 데이터다. spec 13장의 통합 시나리오는 **실제 `~/.claude.json`** 으로 확인해야 의미가 있다 — 특히 "user 스코프 서버가 전부 기록되고 `claude.ai *`는 없다"와 "프로젝트 디렉토리에서 백업해도 local 스코프 서버가 섞이지 않는다"(Bug #5)는 실환경에서만 드러난다.

**안전 규칙:**
- 이 task의 어떤 step도 **사용자의 실제 `~/.claude/.sync-state`, 실제 백업 레포, `~/.claude.json`을 영구적으로 바꾸지 않는다.** 모든 확인은 임시 디렉토리와 `~/.claude.json`의 **복사본**으로 한다.
- 예외는 Step 5의 임시 MCP 서버 등록 하나뿐이며, **Step 6의 제거를 반드시 함께 수행한다.**

- [ ] **Step 1: 전체 테스트 통과 확인**

```bash
cd /Users/bran/personal/claude-sync
uv run --with pytest pytest plugins/claude-sync/tests -q
git status --short
```

기대: 실패 0건. `git status`는 깨끗하다(Task 1~12가 모두 커밋되었다).

- [ ] **Step 2: 격리된 스모크 환경 준비**

```bash
export SMOKE=$(mktemp -d)
mkdir -p "$SMOKE/home/.claude" "$SMOKE/repo"
cp ~/.claude.json "$SMOKE/home/.claude.json"      # 읽기 전용 사본
export SB="$PWD/plugins/claude-sync/skills/sync-backup/scripts"
export SS="$PWD/plugins/claude-sync/skills/sync-status/scripts"
export SR="$PWD/plugins/claude-sync/skills/sync-restore/scripts"
python3 -c "
import json
d = json.load(open('$SMOKE/home/.claude.json'))
print('user 스코프 서버:', sorted(d.get('mcpServers', {})))
print('local 스코프가 있는 프로젝트 수:', sum(1 for v in d.get('projects', {}).values() if v.get('mcpServers')))
"
```

기대: user 스코프 서버 이름 목록이 출력된다. `claude.ai *`나 `plugin:*`은 이 목록에 **없어야 한다**.

- [ ] **Step 3: 백업 스모크 — 수집 결과와 cwd 무관성**

```bash
HOME="$SMOKE/home" python3 "$SB/collect_mcp.py" "$SMOKE/repo" "$SMOKE/staging"
python3 -c "
import json
d = json.load(open('$SMOKE/repo/mcp-servers.json'))
print('version:', d['version'], 'scope:', d['scope'])
for name, cfg in sorted(d['servers'].items()):
    print(' ', name, '->', json.dumps(cfg, ensure_ascii=False)[:100])
"
cp "$SMOKE/repo/mcp-servers.json" "$SMOKE/from-home.json"
rm -rf "$SMOKE/repo2" "$SMOKE/staging2" && mkdir -p "$SMOKE/repo2"
( cd "$(python3 -c "
import json, sys
d = json.load(open('$SMOKE/home/.claude.json'))
cands = [k for k, v in d.get('projects', {}).items() if v.get('mcpServers')]
print(cands[0] if cands else '/tmp')
")" && HOME="$SMOKE/home" python3 "$SB/collect_mcp.py" "$SMOKE/repo2" "$SMOKE/staging2" > /dev/null )
diff "$SMOKE/from-home.json" "$SMOKE/repo2/mcp-servers.json" && echo "cwd 무관 확인 (Bug #5 해소)"
```

기대:
- `version: 2 scope: user`
- 서버 목록이 Step 2의 user 스코프 목록과 **정확히 일치**한다. `claude.ai *` 없음, `plugin:*` 없음.
- 공백이 든 `command`(예: Safari Technology Preview 경로)가 온전히 보존된다.
- `headers`/`env`가 있는 서버는 값이 `<REDACTED>`이고 키 이름은 남아 있다.
- 마지막 `diff`가 차이 없이 `cwd 무관 확인 (Bug #5 해소)`를 출력한다 — local 스코프 서버가 섞이지 않는다.

- [ ] **Step 4: status 스모크 — 백업 직후 "동일"로 수렴**

```bash
HOME="$SMOKE/home" python3 "$SS/compare_mcp.py" "$SMOKE/repo/mcp-servers.json"
```

기대: `{"status": "ok", "only_local": [], "only_repo": [], "changed": []}`. **비어 있지 않으면 Bug #2(영구 미수렴)가 남아 있는 것이다** — 어느 서버가 걸리는지 확인하고 원인을 규명한다.

- [ ] **Step 5: 복원 스모크 — 임시 서버 등록**

레포에만 있는 서버가 실제로 `add-json`으로 등록되는지 확인한다. **이 step은 실제 `~/.claude.json`을 변경하므로 Step 6과 반드시 짝을 이룬다.**

```bash
python3 -c "
import json
p = '$SMOKE/repo/mcp-servers.json'
d = json.load(open(p))
d['servers']['sync-smoke-test'] = {'command': 'echo', 'args': ['smoke']}
json.dump(d, open(p, 'w'), indent=2, sort_keys=True, ensure_ascii=False)
"
HOME="$SMOKE/home" python3 "$SR/plan_mcp.py" plan "$SMOKE/repo/mcp-servers.json" \
  | python3 -c "import json,sys; p=json.load(sys.stdin); print('add:', p['add']); print('unrestorable:', p['unrestorable']); print('json:', json.dumps(p['configs'].get('sync-smoke-test')))"
claude mcp add-json sync-smoke-test '{"command":"echo","args":["smoke"]}' --scope user
claude mcp get sync-smoke-test
```

기대: `add: ['sync-smoke-test']`, `claude mcp get`이 등록된 서버 정보를 출력한다. `unrestorable`에 무엇이 나오는지도 기록해 둔다(옛 v1 항목이 있으면 여기 나온다).

- [ ] **Step 6: 임시 서버 제거 (반드시 실행)**

```bash
claude mcp remove sync-smoke-test -s user
claude mcp get sync-smoke-test 2>&1 | head -3
python3 -c "
import json, os
d = json.load(open(os.path.expanduser('~/.claude.json')))
assert 'sync-smoke-test' not in d.get('mcpServers', {}), '임시 서버가 남아 있다'
print('임시 서버 제거 확인. 현재 user 스코프:', sorted(d.get('mcpServers', {})))
"
```

기대: `claude mcp get`이 "찾을 수 없음" 취지의 메시지를 내고, 마지막 python이 `임시 서버 제거 확인`과 **Step 2와 동일한 서버 목록**을 출력한다. 목록이 다르면 즉시 원인을 확인한다.

- [ ] **Step 7: 스모크 환경 정리**

```bash
rm -rf "$SMOKE"
unset SMOKE SB SS SR
ls ~/.claude/.sync-state/base/ 2>/dev/null
git status --short
```

기대: 임시 디렉토리가 사라진다. `~/.claude/.sync-state/base/`는 **이 task 이전과 같다**(스모크는 `HOME`을 덮어썼으므로 실제 base를 건드리지 않았다). `git status`는 깨끗하다.

- [ ] **Step 8: 완료 보고 (커밋 없음)**

사용자에게 다음을 보고한다:

- 전체 테스트 결과(실패 0건)와 Task 1~12의 커밋 목록
- Step 3에서 백업된 실제 user 스코프 서버 이름들 — **이슈 보고 당시 "복원 가능한 형태로 백업된 서버 0개"가 몇 개가 되었는지**
- Step 4의 수렴 확인 결과
- Step 5의 `unrestorable` 목록(있으면) — 옛 v1 백업에서 넘어온 항목이며 첫 백업 이후 v2로 승격된다
- **다음 단계는 사용자 승인이 필요하다**(spec 14장): `origin`에 푸시 → `claude plugin marketplace update claude-sync` → `claude plugin update claude-sync` → 캐시 디렉토리가 3.0.0 신코드로 교체됐는지 확인. **푸시는 외부 동작이므로 승인 없이 실행하지 않는다.**

---

## 부록: spec 13장 검증 항목 ↔ task 대응

| spec 13장 항목 | 구현 task |
|---|---|
| 단위 — 공백 든 command 보존(Bug #1) | Task 6 `test_compare_preserves_command_with_spaces`, 기존 `test_redact_preserves_stdio_command_with_spaces` |
| 단위 — http type/url/headers 보존·마스킹(Bug #3·#4) | 기존 `test_redact_masks_header_values_keeps_key_names`, Task 4 `test_collect_masks_secrets_in_repo_file` |
| 단위 — diff 수렴(Bug #2) | 기존 `test_diff_converges_when_repo_is_redacted`, Task 6 `test_compare_converges_when_local_secret_is_plaintext` |
| 단위 — merge 판정표 10줄, base 없음, 케이스 4 | 기존 `test_merge_case1`~`case10` (Task 1~2에서 계속 통과) |
| 순환 정합성 (케이스 4 반복) | Task 3 `test_repeated_backup_without_cleanup_keeps_reporting_local_stale` |
| restore_plan — local_stale(4·5), needs_secret, 7·8·9 분리, unrestorable | Task 2 |
| restore_plan — 비밀 평문 vs 마스킹 in_sync | Task 2 `test_restore_plan_in_sync_when_local_secret_is_plaintext` |
| next_base — redact 계약 | Task 1 |
| read_local_servers / load_backup v1 / 안전장치 | 기존 테스트 + Task 4 `test_collect_skips_without_touching_repo_or_staging` |
| 멱등성·수렴 표 10줄 | Task 3 (10개 시나리오) |
| 해소 경로 교대 표 13줄 | Task 9 (13개 시나리오) |
| 통합 — 실제 `~/.claude.json`, cwd 무관, status 수렴, add-json 등록 | Task 13 |

### plan을 쓰며 spec에서 발견한 문제 (구현자가 알아야 할 것)

1. **13장 "backup→restore→backup→restore 2주기(무선택): 2주기째가 1주기째와 완전히 같다"는 문언 그대로는 성립하지 않는다.** 1주기째 restore가 케이스 2의 서버를 실제로 설치하면 그것은 정당한 상태 변화이고, 2주기의 보고는 1주기와 다를 수밖에 없다(`add` → `in_sync`). 시뮬레이션으로 확인했다. 고정점은 **2주기와 3주기가 같은지**로 판정해야 하며, Task 9의 `test_two_cycles_reach_fixed_point`가 그렇게 쓰여 있다.
2. **8.3의 `plan` 출력 계약에 등록용 config가 빠져 있다.** 명시된 것은 버킷 9개뿐인데, SKILL.md가 `add-json`에 넘길 JSON을 얻으려면 레포 값이 필요하고 SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이 되살아난다. Task 7에서 `configs`·`secret_keys` 두 키를 추가로 싣는다(값은 `redact`를 거치므로 비밀이 실리지 않는다).
3. **8.3이 `update_base.py`의 위치 문제를 다루지 않는다.** 그 스크립트는 `sync-backup/scripts`에 있는데 restore SKILL.md의 `$SYNC_SCRIPTS`는 `sync-restore/scripts`를 가리킨다. Task 10 Step 1에서 `SYNC_BACKUP_SCRIPTS`를 별도로 탐색한다.
4. **5장의 `unrestorable` 판정에서 `type`의 대소문자를 명시하지 않는다.** v1이 저장하던 `"HTTP"`(대문자)를 허용하면 `add-json`이 스키마 불일치로 실패한다. Task 2는 소문자 `"http"`/`"sse"`만 인정하며, 이 결정으로 v1 승격 항목이 전부 `unrestorable`로 빠져 10장의 의도와 맞는다.
