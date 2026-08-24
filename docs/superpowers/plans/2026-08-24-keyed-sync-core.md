# 공용 키 단위 3-way 코어 추출 Implementation Plan

> **agentic worker에게:** REQUIRED SUB-SKILL: 이 plan을 task 단위로 구현하려면 suberpower:subagent-driven-development(권장) 또는 suberpower:executing-plans를 사용하세요. Step은 추적을 위해 checkbox(`- [ ]`) 문법을 사용합니다.

**Goal:** `lib/mcp_config.py`의 키 단위 3-way 판정·인식 계층을 값에 무관한 `lib/keyed_sync.py`로 빼내고, `mcp_config`를 얇은 어댑터로 남긴다. **공개 계약과 기존 테스트는 그대로다**(이 plan 착수 시점 385개).

**Architecture:** 코어는 값을 모른다 — 마스킹(`normalize`), 판정 보류(`hold`), 복원 가능성(`restorable`), 비밀 키 목록(`secret_keys`)을 전부 훅으로 주입받는다. `mcp_config`는 `normalize=redact`와 "보류 없음"을 주입하는 래퍼가 되고, 나중에 `plugin_config`가 두 번째 어댑터로 붙는다.

**Tech Stack:** Python 3.13 표준 라이브러리만. 테스트는 pytest (`uv run --with pytest pytest`).

---

## 이 plan의 범위

| 포함 | 제외 (다른 plan) |
|---|---|
| `lib/keyed_sync.py` 신규 | `lib/plugin_config.py`, `collect_plugins.py` 등 플러그인 본체 |
| `lib/mcp_config.py` 어댑터화 | `lib/compat.py` shape 확장, `detect_downgrade.py` |
| `collect_mcp.py`의 스테이징 결함 수정 | **spec 7.4 배선 구현** + 세 `SKILL.md`·README 문서 정정 |
| `test_mcp_state_machine.py` 파라미터화 | 플러그인 테스트 전부 |

**근거 절 표기.** 각 task 머리에 `**근거:** spec N.M` 을 적었다. spec의 그 절이 바뀌면 그 task는 무효다 — 폭발 반경을 기계적으로 식별하기 위한 장치이고, 이 plan을 재생성할 때 어디부터 다시 쓸지를 정한다.

**사용자 가치.** 이 plan이 끝나도 사용자에게 보이는 변화는 **Task 1 하나뿐**이다(스테이징 결함 수정). 나머지는 전부 다음 plan의 토대다. spec 부록 A 참조.

**변조 확인은 각 task의 필수 스텝이다.** 이 plan의 테스트 블록은 불변식 7("테스트는 의미
반전을 잡아야 한다")을 통과하지 못한 채 실려 왔다 — Task 2에서만 **다섯 개 중 세 개가
공허했다**(`claims_newer_schema(True, 2)`는 bool 가드를 지워도 통과, `BROKEN = None`으로
바꿔도 통과, `same`을 `a == b`로 바꿔도 통과). 셋 다 기존 스위트도 잡지 못하므로 Task 8의
"기존 테스트 그대로 통과" 게이트로는 영영 걸리지 않는다. 성실한 구현일수록 plan의 결함을
그대로 재생산하므로, **각 task의 통과 확인 스텝에서 대응 구현 줄을 지우거나 뒤집어 실제로
FAIL하는지 임시 복사본에서 확인한다.** Task 5의 `next_base` deepcopy와 Task 6의 판정표
10케이스가 특히 "단언은 참인데 그 참이 구현의 가드에서 나오지 않는" 형태가 되기 쉽다.

**I/O 층도 변조 대상이다.** Task 3에서 구현자가 돌린 변조 다섯은 전부 순수 함수 층이었고
전부 CAUGHT였는데, 리뷰어가 파일 읽기 층을 건드리자 **둘이 SURVIVED**했다 —
`except FileNotFoundError`를 `except OSError`로 넓혀도, `open(path, "rb")`를 `"r"`로
바꿔도 전체가 통과했다. 앞의 것은 **권한이 없어 못 읽은 백업을 "항목 0개"로 만드는** 변조인데
docstring이 그러지 않겠다고 명시적으로 약속한 자리였다. 순수 함수에만 시선이 가는 것이
자연스러운 사각지대이므로 **`open` 모드·`except` 절·파일 부재 처리를 반드시 변조 목록에
넣는다.**

**실행 중 확정된 것.**

| 결정 | 근거 |
|---|---|
| `fingerprint`는 **공개로 둔다**(`_fingerprint`로 되돌리지 않는다) | spec 5.2 표에는 없지만, spec 6.4가 `plugins-held.json`에 "레포 값의 sha256 지문"을 저장하도록 정했다. 다음 plan의 `plugin_config`가 그 지문을 만들려면 코어와 **동일한 정규 직렬화**가 필요하고, 거기서 옵션을 다시 적으면 이 추출이 막으려는 표류가 그대로 재발한다 |
| `mcp_config` 쪽 원본 테스트는 **강화하지 않는다** | `test_mcp_config.py`의 `same`·`_BROKEN`·`_decode` 테스트가 코어와 똑같은 구멍을 갖고 있지만, Task 8이 그 구현들을 삭제하고 코어에 위임하므로 코어만 고치면 최종 상태가 안전하다. Task 8 이전에 누가 `mcp_config`를 건드리면 감지되지 않는 창이 남는다는 것은 알고 받아들인 위험이다 |
| **`plugin_config`는 Task 8보다 먼저 붙일 수 없다** | Task 2~7 동안 `mcp_config`의 예외 두 클래스·`_BROKEN`과 코어의 동명 객체가 **서로 다른 객체**로 공존한다. `except mc.UnknownBackupSchema`가 `ks.UnknownBackupSchema`를 잡지 못한다. Task 8의 re-export가 이것을 닫으므로 현 순서에서는 안전하지만, 순서가 바뀌면 두 도메인이 다른 예외 계층을 쓰게 된다 |

---

## File Structure

| 파일 | 책임 |
|---|---|
| `plugins/claude-sync/lib/keyed_sync.py` | **신규.** 값 무관 코어 — 예외 두 클래스, JSON 디코드, 상위 버전 판정, 인식 계층, 지문·비교, `diff`/`next_base`/`merge`/`restore_plan` |
| `plugins/claude-sync/lib/mcp_config.py` | MCP 어댑터 — `redact`/`secret_keys`/`restorable`/`read_local_servers`/`dump_backup`과 상수를 갖고, 판정은 코어에 위임 |
| `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py` | 스테이징을 `.tmp`로 쓰고 레포 쓰기 성공 후 rename |
| `plugins/claude-sync/tests/test_keyed_sync.py` | **신규.** 코어 단위 — 훅이 실제로 주입되는지, 값 무관인지 |
| `plugins/claude-sync/tests/test_mcp_state_machine.py` | 어댑터·값 픽스처를 주입받는 형태로 재작성 |

`tests/conftest.py`가 이미 `lib`를 `sys.path`에 넣으므로 테스트는 `import keyed_sync as ks`로 바로 쓴다.

---

## 코어의 훅 계약 (Task 2~7이 공유한다)

```python
recognize(obj)      -> mapping | None   # 알아볼 수 있으면 매핑(비었으면 {}), 아니면 None
normalize(mapping) -> mapping      # 값 층위 변환만. 멱등. 키를 더하거나 빼지 않는다
hold(local, repo)   -> {"value": set[str], "action": set[str]}   # 정규화된 입력을 받는다
restorable(key, value) -> bool
secret_keys(value)  -> list        # 복원 시 사용자에게 물어야 하는 항목
```

**`recognize`의 두 갈래를 헷갈리면 곧바로 파괴로 이어진다.** spec 4.4가 정한 규약이다 —
인식된 문서에서 **없는 섹션은 `{}`**("이력이 비어 있었다"), **문서 자체를 인식하지 못하면
`None`**. "유효한데 항목 0개"에 `None`을 돌려주면 `load_backup`이 정상 문서에
`UnknownBackupSchema`를 던져 **모든 백업이 영구히 막힌다.** 반대로 "알아볼 수 없음"에
`{}`를 돌려주면 상위 버전 백업이 파괴된다. 그리고 `parse_base`·`load_backup`·`parse_backup`
세 함수가 **반드시 같은 훅을 받아야 한다** — 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이
생기고, 코어는 파라미터로 받으므로 그 공유를 강제할 수 없다(어댑터 측에서 가드해야 한다).

(이 절은 처음에 `recognize`를 빠뜨렸다. Task 3이 오직 그 훅만 도입하는 task인데도 그랬고,
그 결과 `mcp_config._recognized_servers`에 있던 공통 기준 설명이 추출 과정에서 어느 쪽에도
남지 않고 증발했다 — Task 3 quality review가 잡았다.)

**`normalize`의 키 불변 조건은 코어가 집행한다.** `_normalized(mapping, normalize)`가 키 집합이
바뀌면 `ValueError`를 던지고, `diff`·`next_base`·`merge`·`restore_plan`이 모두 그것을 쓴다.
가드 없이 실측했더니 `normalize`가 키 하나를 빼면 `diff`의 **네 버킷 어디에도 나타나지 않고
통째로 증발**했다 — 예외도 경고도 없이. `merge`에서는 같은 일이 케이스 3(삭제)이 되어
이 개정이 없애려던 손실 경로가 부활한다. **멱등성은 집행하지 않는다** — 코어가 값을 모르므로
두 번 적용해 비교하는 것 외에 방법이 없고, 어댑터 테스트가 책임진다(spec 5.2).

**`hold`는 좌우 대칭이 아니다.** spec 7.3의 H3는 **레포** 값을 보고, H1·H2는 로컬 쪽 사실을 본다.
`hold(local, repo)` 순서가 뒤집히면 `plugin_config`의 보류 판정이 조용히 반대로 선다.
MCP는 `no_hold`뿐이라 이 실수가 Task 8 게이트를 정상 통과한 뒤 다음 plan에서야 발현한다 —
그래서 Task 4가 `recording_hold` 훅으로 **인자·순서·정규화 여부·호출 횟수**를 고정했다.
**Task 6·7은 그 훅을 재사용한다.**

**리스트 버킷의 순서는 계약이다.** `diff`·`merge`·`restore_plan`이 반환하는 리스트
(`only_local`·`conflicts`·`deleted`·`local_stale`·`repo_ahead`·`held` …)는 전부 정렬 순서다 —
`diff`는 `sorted()`를 직접 쓰고, `merge`·`restore_plan`은 `sorted(...)`를 순회하며 append하므로
결과가 정렬된다. 이 목록들은 **사용자에게 그대로 보고되는 것**이므로 순서가 결정론적이어야 한다.
테스트는 멤버십이 아니라 **정확 등호**로 건다 — 멤버십만 보면 "과다 분류"(정상 항목이 충돌
버킷에도 실리는) 변조가 통과한다. (반환 dict 자체의 키 순서는 계약이 아니다 — 디스크
직렬화가 `sort_keys=True`다.)

**버킷 이름 `held`가 뜻하는 것.** `diff`·`merge`의 `held`는 **값 보류**다. `restore_plan`만
두 축이 같은 dict에 함께 나타나므로 거기서는 `value_held`와 **`action_held`**로 이름을 갈랐다
(`held`라는 이름을 쓰지 않는다). 즉 **`diff`/`merge`의 `held` = `restore_plan`의 `value_held`**다.

**`next_base`만 `hold` 콜러블이 아니라 `value_held` 집합을 받는다.** `hold`는 `(local, repo)`가 필요한데 `next_base`의 인자에는 `repo`가 없고 `merged`뿐이기 때문이다. `merge`가 한 번 계산해 넘기고, 단독 호출자(restore)는 스스로 계산해 넘긴다. spec 15장 오픈이슈 1이 이 결정을 plan에 맡겼다.

---

### Task 1: `collect_mcp.py`의 스테이징 순서 결함 수정

**근거:** spec 7.4, 9.1.1, 12장

현행 `collect_mcp.py`는 스테이징을 레포보다 **먼저** 쓴다. 레포 쓰기가 실패하면 `status`는 `skipped`가 되지만 스테이징 파일은 남고, `SKILL.md:398`의 게이트 `[ -f ... ]`가 통과해 **base가 전진한다.** 그러면 다음 백업에서 이 기기 자신의 서버가 케이스 4가 되어 restore가 "다른 기기가 지웠습니다"라는 거짓 문구를 띄운다. `collect_mcp.py:29`의 docstring이 그 반대를 안전 성질로 적고 있다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py:26-56`
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_mcp_scripts.py` 끝에 추가한다.

이 파일의 기존 헬퍼(`write_local`·`write_repo`·`write_base_blob`)를 그대로 쓴다.

```python
def test_collect_does_not_stage_when_repo_write_fails(tmp_path, monkeypatch):
    """레포 쓰기가 실패하면 스테이징 최종 파일이 남지 않아야 base가 전진하지 않는다.

    남으면 SKILL.md의 게이트 `[ -f ... ]`가 통과해 base가 전진하고,
    다음 백업이 이 기기 자신의 서버를 케이스 4로 오독한다.
    """
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    staging = str(tmp_path / "staging")
    real_dump = mc.dump_backup

    def fail_on_repo(servers, path):
        if path.endswith(os.path.join("repo", mc.BACKUP_RELPATH)):
            raise OSError("disk full")
        return real_dump(servers, path)

    monkeypatch.setattr(mc, "dump_backup", fail_on_repo)
    with pytest.raises(OSError):
        collect_mcp.collect(repo, staging, claude_json_path=local, base_dir=base_dir)
    assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))
```

`collect_mcp`가 `import mcp_config as mc`로 참조하므로 `mc` 모듈의 속성을 갈아끼우면
호출 시점에 교체된 함수가 쓰인다.

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `cd /Users/bran/personal/claude-sync && uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py::test_collect_does_not_stage_when_repo_write_fails -v`
기대: FAIL — 스테이징 파일이 이미 존재한다 (`assert not os.path.exists(...)`)

- [ ] **Step 3: 구현**

`collect_mcp.py`의 `collect()`를 아래로 교체한다. docstring도 함께 고친다.

```python
def collect(repo_path, staging_dir, claude_json_path=None, base_dir=ss.BASE_DIR):
    """merge 결과를 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    스테이징은 <rel>.tmp로 먼저 쓰고 **레포 쓰기가 성공한 뒤에** <rel>로 rename한다.
    스테이징 최종 파일의 존재가 곧 "레포까지 반영됨"을 뜻해야 하기 때문이다 —
    SKILL.md의 base 갱신 게이트가 그 파일의 존재만 보고 판단한다.
    먼저 최종 이름으로 쓰면 레포 쓰기가 실패해도 게이트가 통과해 base가 전진하고,
    다음 백업이 이 기기 자신의 서버를 케이스 4로 오독한다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo_file = os.path.join(repo_path, mc.BACKUP_RELPATH)
    repo = mc.load_backup(repo_file)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    result = mc.merge(local, repo, base)
    servers = result["servers"]

    os.makedirs(staging_dir, exist_ok=True)
    staged = os.path.join(staging_dir, mc.BACKUP_RELPATH)
    tmp = staged + ".tmp"
    mc.dump_backup(result["next_base"], tmp)
    mc.dump_backup(servers, repo_file)

    out = {
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
    try:
        os.replace(tmp, staged)
    except OSError as e:
        # 레포는 이미 갱신됐다. skipped로 접으면 "레포를 손대지 않았다"가 거짓이 된다.
        out["base_staging"] = "failed"
        out["reason"] = "레포는 갱신됐으나 base 스테이징에 실패했다: %s (다음 백업이 복구한다)" % e
    return out
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py -v`
기대: 새 테스트 PASS, 기존 테스트 전부 PASS

- [ ] **Step 5: 전체 회귀 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `384 passed` (기존 383 + 신규 1)

- [ ] **Step 6: Commit**

```bash
git add plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py plugins/claude-sync/tests/test_mcp_scripts.py
git commit -m "fix(backup): 레포 쓰기가 실패해도 base가 전진하던 경로를 막는다"
```

---

### Task 2: `keyed_sync` 기반 — 예외·디코드·버전 판정·지문

**근거:** spec 5.2, 4.4 조건 2

**Files:**
- Create: `plugins/claude-sync/lib/keyed_sync.py`
- Create: `plugins/claude-sync/tests/test_keyed_sync.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
"""값 무관 코어의 단위 테스트. 도메인 지식은 전부 훅으로 들어온다."""
import keyed_sync as ks


def test_claims_newer_schema_blocks_float_bypass():
    """float 버전 주장을 막는다. jq·YAML 변환기·다른 언어 writer가 실제로 만드는 형태다."""
    assert ks.claims_newer_schema(3, 2) is True
    assert ks.claims_newer_schema(3.0, 2) is True
    assert ks.claims_newer_schema(2, 2) is False


def test_claims_newer_schema_ignores_bool_and_string():
    """True는 int의 인스턴스지만 버전 주장이 아니다. 문자열은 손으로 고친 문서를 막지 않는다."""
    assert ks.claims_newer_schema(True, 2) is False
    assert ks.claims_newer_schema("3", 2) is False
    assert ks.claims_newer_schema(None, 2) is False


def test_decode_distinguishes_broken_from_falsy():
    """None·0·false 같은 유효한 falsy 값과 디코드 실패를 구별해야 한다."""
    assert ks.decode(b"null") is None
    assert ks.decode(b"0") == 0
    assert ks.decode(b"{oops") is ks.BROKEN


def test_same_ignores_key_order():
    assert ks.same({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True
    assert ks.same({"a": 1}, {"a": 2}) is False


def test_no_hold_returns_two_empty_sets():
    """어댑터가 '보류 없음'을 표현하는 기본 훅."""
    h = ks.no_hold({"x": 1}, {"y": 2})
    assert h["value"] == frozenset() and h["action"] == frozenset()
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: `ModuleNotFoundError: No module named 'keyed_sync'`로 전부 FAIL

- [ ] **Step 3: 구현**

`plugins/claude-sync/lib/keyed_sync.py`를 새로 만든다.

```python
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
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: 신규 테스트가 전부 통과. **절대 개수를 적지 않는다** — 리뷰 후속 커밋이 테스트를 더하므로 계획 시점 숫자는 항상 어긋난다. 전체 스위트로 확인한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests/test_keyed_sync.py
git commit -m "feat(core): 값 무관 코어의 기반 — 예외·디코드·버전 판정·지문"
```

---

### Task 3: `keyed_sync` 인식 계층

**근거:** spec 4.4, 5.1(이유 셋), 5.2

세 함수가 같은 `recognize` 훅을 공유해야 한다. 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고, 그 비대칭이 상위 버전 백업을 파괴한다.

**Files:**
- Modify: `plugins/claude-sync/lib/keyed_sync.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_keyed_sync.py`에 추가한다. **`import json`·`import pytest`는 파일 맨 위
`import keyed_sync as ks` 앞에 놓는다** (표준 라이브러리 → 서드파티 → 로컬 순서).

```python
def only_dict_with_items(obj):
    """테스트용 recognize 훅 — {"items": {...}} 만 인정한다."""
    if isinstance(obj, dict) and isinstance(obj.get("items"), dict):
        if ks.claims_newer_schema(obj.get("version"), 2):
            return None
        return dict(obj["items"])
    return None


def test_parse_base_returns_none_for_untrusted_history():
    """이력을 못 믿으면 {}가 아니라 None이다. {}는 삭제 판정의 근거가 된다."""
    assert ks.parse_base(None, only_dict_with_items) is None
    assert ks.parse_base(b"{oops", only_dict_with_items) is None
    assert ks.parse_base(b'{"nope": 1}', only_dict_with_items) is None
    assert ks.parse_base(b'{"items": {}}', only_dict_with_items) == {}


def test_load_backup_raises_on_unrecognized_document(tmp_path):
    """알아볼 수 없는 문서는 {}로 degrade하지 않는다 — 덮어쓰면 파괴한다."""
    path = tmp_path / "backup.json"
    path.write_text(json.dumps({"version": 3, "items": {"a": 1}}), encoding="utf-8")
    with pytest.raises(ks.UnknownBackupSchema):
        ks.load_backup(str(path), only_dict_with_items)


def test_load_backup_returns_empty_when_file_missing(tmp_path):
    assert ks.load_backup(str(tmp_path / "none.json"), only_dict_with_items) == {}


def test_load_backup_degrades_broken_syntax_to_empty(tmp_path):
    """구문이 깨진 파일 하나가 백업 전체를 막지 않는다. 다음 백업이 되돌린다."""
    path = tmp_path / "backup.json"
    path.write_text("{oops", encoding="utf-8")
    assert ks.load_backup(str(path), only_dict_with_items) == {}


def test_parse_backup_is_lenient():
    assert ks.parse_backup(b"{oops", only_dict_with_items) == {}
    assert ks.parse_backup(b'{"nope": 1}', only_dict_with_items) == {}
    assert ks.parse_backup(b'{"items": {"a": 1}}', only_dict_with_items) == {"a": 1}
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: `AttributeError: module 'keyed_sync' has no attribute 'parse_base'`로 새 테스트 5개 FAIL

- [ ] **Step 3: 구현**

`keyed_sync.py`의 `no_hold` 앞에 추가한다.

```python
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
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: 신규 테스트가 전부 통과. **절대 개수를 적지 않는다** — 리뷰 후속 커밋이 테스트를 더하므로 계획 시점 숫자는 항상 어긋난다. 전체 스위트로 확인한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests/test_keyed_sync.py
git commit -m "feat(core): 인식 계층 — 세 함수가 같은 recognize 훅을 공유한다"
```

---

### Task 4: `keyed_sync.diff`

**근거:** spec 5.2, 5.3(값 보류의 `diff` 동작)

**Files:**
- Modify: `plugins/claude-sync/lib/keyed_sync.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
def mask_secret(mapping):
    """테스트용 normalize 훅 — 'secret' 필드 값을 가린다. 멱등이다."""
    out = {}
    for key, value in mapping.items():
        if isinstance(value, dict) and "secret" in value:
            copied = dict(value)
            copied["secret"] = "<X>"
            out[key] = copied
        else:
            out[key] = value
    return out


def hold_keys(value=(), action=()):
    """지정한 키를 보류로 만드는 훅 팩토리."""
    def _hold(local, repo):
        return {"value": frozenset(value), "action": frozenset(action)}
    return _hold


def test_diff_applies_normalize_to_both_sides():
    """로컬은 평문, 레포는 마스킹됨. 정규화 없이 비교하면 영원히 changed가 된다."""
    local = {"a": {"secret": "plain"}}
    repo = {"a": {"secret": "<X>"}}
    out = ks.diff(local, repo, normalize=mask_secret, hold=ks.no_hold)
    assert out["changed"] == []


def test_diff_reports_three_buckets():
    out = ks.diff({"a": 1, "b": 1}, {"b": 2, "c": 1},
                  normalize=lambda m: m, hold=ks.no_hold)
    assert out["only_local"] == ["a"]
    assert out["only_repo"] == ["c"]
    assert out["changed"] == ["b"]
    assert out["held"] == []


def test_diff_moves_held_keys_out_of_all_three_buckets():
    """보류 키는 only_local/only_repo/changed 어디에도 들어가지 않는다."""
    out = ks.diff({"a": 1, "b": 1}, {"b": 2, "c": 1},
                  normalize=lambda m: m, hold=hold_keys(value=("a", "b", "c")))
    assert out["only_local"] == [] and out["only_repo"] == [] and out["changed"] == []
    assert out["held"] == ["a", "b", "c"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -k diff -v`
기대: `AttributeError: module 'keyed_sync' has no attribute 'diff'`로 3개 FAIL

- [ ] **Step 3: 구현**

`keyed_sync.py` 끝에 추가한다.

```python
def _normalized(mapping, normalize):
    """normalize를 적용하되 키 집합이 보존됐는지 확인한다.

    키 층위 제외는 전부 hold의 몫이다(spec 5.2). normalize가 키를 빼면
    merge가 그것을 "로컬에서 삭제됨"(케이스 3)으로 읽어 레포에서 지운다.
    조용히 통과시키면 이 개정이 없애려던 손실 경로가 그대로 부활한다.
    """
    out = normalize(mapping)
    if set(out) != set(mapping):
        raise ValueError("normalize가 키 집합을 바꿨다 — 키 층위 제외는 hold가 맡는다")
    return out


def diff(local, repo, *, normalize, hold):
    """상태 비교. 비교 직전 양쪽에 normalize를 적용한다.

    비밀 값은 로컬에 평문, 레포에 마스킹된 형태로 저장되므로 원본끼리 비교하면
    비밀을 가진 항목이 영구히 "변경됨"으로 보고된다(미수렴).
    값 보류 키는 세 버킷 어디에도 넣지 않고 held에만 넣는다.
    키 층위 제외는 normalize가 아니라 hold의 몫이므로 _normalized가 그것을 강제한다.
    """
    local, repo = _normalized(local, normalize), _normalized(repo, normalize)
    value_held = set(hold(local, repo)["value"])
    return {
        "only_local": sorted(set(local) - set(repo) - value_held),
        "only_repo": sorted(set(repo) - set(local) - value_held),
        "changed": sorted(
            name for name in (set(local) & set(repo)) - value_held
            if not same(local[name], repo[name])
        ),
        "held": sorted(value_held),
    }
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: 신규 테스트가 전부 통과. **절대 개수를 적지 않는다** — 리뷰 후속 커밋이 테스트를 더하므로 계획 시점 숫자는 항상 어긋난다. 전체 스위트로 확인한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests/test_keyed_sync.py
git commit -m "feat(core): diff — 정규화를 양쪽에 적용하고 보류 키를 분리한다"
```

---

### Task 5: `keyed_sync.next_base`

**근거:** spec 5.2, 5.3("base에서 제거하는 이유"), MCP spec 7.3

이 함수가 이 프로젝트의 최대 불변식을 담는다 — **base는 로컬이 동의한 값만 전진한다.** 그리고 **값 보류 키는 base에서 제거한다** — 남기면 보류가 풀리는 순간 얼어붙은 base로 케이스 3(삭제)이 난다.

**Files:**
- Modify: `plugins/claude-sync/lib/keyed_sync.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
def test_next_base_advances_only_where_local_agrees():
    """타 기기가 추가·변경한 값을 base에 기록하면 다음 백업이 '내가 삭제했다'로 오독한다."""
    out = ks.next_base({"mine": 1}, {"mine": 1, "theirs": 0}, {"mine": 1, "theirs": 9},
                       normalize=lambda m: m)
    assert out["mine"] == 1      # 로컬이 동의 → 전진
    assert out["theirs"] == 0    # 로컬이 동의 안 함 → 이전 base 유지


def test_next_base_drops_keys_absent_from_both_sides():
    out = ks.next_base({}, {"gone": 1}, {}, normalize=lambda m: m)
    assert "gone" not in out


def test_next_base_removes_value_held_keys():
    """값 보류 키를 base에 남기면 해제 시 케이스 3(삭제)이 난다."""
    out = ks.next_base({"h": 1, "n": 1}, {"h": 1, "n": 1}, {"h": 1, "n": 1},
                       normalize=lambda m: m, value_held={"h"})
    assert "h" not in out
    assert out["n"] == 1


def test_next_base_applies_normalize_so_secrets_do_not_leak():
    """restore가 평문 로컬을 넘겨도 base 블롭에 평문이 기록되면 안 된다."""
    out = ks.next_base({"a": {"secret": "plain"}}, None, {"a": {"secret": "<X>"}},
                       normalize=mask_secret)
    assert out["a"]["secret"] == "<X>"


def test_next_base_does_not_share_nested_objects_with_inputs():
    """반환값을 호출부가 가공해도 원본이 오염되면 안 된다."""
    merged = {"a": {"n": [1]}}
    out = ks.next_base({"a": {"n": [1]}}, None, merged, normalize=lambda m: m)
    out["a"]["n"].append(2)
    assert merged["a"]["n"] == [1]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -k next_base -v`
기대: `AttributeError: module 'keyed_sync' has no attribute 'next_base'`로 5개 FAIL

- [ ] **Step 3: 구현**

```python
def next_base(local, base, merged, *, normalize, value_held=frozenset()):
    """다음 base 매핑. base[key]는 로컬이 그 값에 동의할 때만 전진한다.

    로컬이 동의하지 않은 값(타 기기가 추가·변경한 항목, 충돌 중인 항목)을 base에 기록하면
    다음 백업이 그 차이를 "로컬이 바뀌었다"로 오독해, 타 기기의 항목을 삭제하거나
    타 기기의 변경을 되돌린다.

    **값 보류 키는 base에서 제거한다.** base의 의미는 "이 기기가 마지막으로 동의한 값"인데
    보류 키는 정의상 이 기기가 동의하지 않기로 한 키다. 남기면 보류가 풀리는 순간
    얼어붙은 base로 케이스 3(삭제)이 난다.

    hold 콜러블이 아니라 이미 계산된 집합을 받는다 — hold는 (local, repo)가 필요한데
    이 함수의 인자에는 repo가 없기 때문이다. merge가 한 번 계산해 넘기고,
    단독 호출자(restore)는 스스로 계산해 넘긴다.

    반환값은 입력의 어떤 nested 객체도 공유하지 않는다(deepcopy).
    """
    local, merged = _normalized(local, normalize), _normalized(merged, normalize)
    old = _normalized(base, normalize) if base else {}
    out = {}
    for name in sorted(set(old) | set(merged)):
        if name in value_held:
            continue                                    # 값 보류 → base에서 제거
        if name in merged and name in local and same(merged[name], local[name]):
            out[name] = copy.deepcopy(merged[name])     # 로컬이 동의 → 전진
        elif name not in merged and name not in local:
            continue                                    # 양쪽에서 사라짐 → 제거
        elif name in old:
            out[name] = copy.deepcopy(old[name])        # 동의 안 함 → 이전 base 유지
    return out
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: 신규 테스트가 전부 통과. **절대 개수를 적지 않는다** — 리뷰 후속 커밋이 테스트를 더하므로 계획 시점 숫자는 항상 어긋난다. 전체 스위트로 확인한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests/test_keyed_sync.py
git commit -m "feat(core): next_base — 로컬이 동의한 키만 전진하고 보류 키는 제거한다"
```

---

### Task 6: `keyed_sync.merge`

**근거:** spec 5.2, 5.3(값 보류의 `merge` 동작), 7.1, MCP spec 7.2 판정표

**Files:**
- Modify: `plugins/claude-sync/lib/keyed_sync.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
def test_merge_covers_decision_table():
    """케이스 1~10을 한 번에 건다."""
    local = {"c1": 1, "c4": 1, "c5": 2, "c6": 1, "c7": 2, "c8": 1, "c9": 2}
    repo = {"c2": 1, "c3": 1, "c6": 1, "c7": 1, "c8": 2, "c9": 3}
    base = {"c3": 1, "c4": 1, "c5": 1, "c7": 1, "c8": 1, "c9": 1, "c10": 1}
    r = ks.merge(local, repo, base, normalize=lambda m: m, hold=ks.no_hold)
    assert r["merged"]["c1"] == 1                 # 1 로컬 신규
    assert r["merged"]["c2"] == 1                 # 2 타 기기 추가
    assert "c3" not in r["merged"]                # 3 로컬에서 삭제
    assert r["deleted"] == ["c3"]
    assert r["local_stale"] == ["c4"]             # 4 타 기기 삭제, 로컬 잔존
    assert "c5" in r["conflicts"] and "c5" not in r["merged"]   # 5
    assert r["merged"]["c6"] == 1                 # 6 in_sync
    assert r["merged"]["c7"] == 2                 # 7 로컬만 변경
    assert r["merged"]["c8"] == 2                 # 8 타 기기 변경
    assert "c9" in r["conflicts"] and r["merged"]["c9"] == 3    # 9
    assert "c10" not in r["merged"]               # 10 base에만 존재
    assert sorted(r["repo_ahead"]) == ["c2", "c8"]


def test_merge_degrades_to_union_when_base_is_none():
    """base가 없으면 삭제 없이 합집합. 단 양쪽에 있는 키는 로컬이 이긴다."""
    r = ks.merge({"a": 1, "both": 9}, {"b": 1, "both": 8}, None,
                 normalize=lambda m: m, hold=ks.no_hold)
    assert r["deleted"] == []
    assert r["merged"] == {"a": 1, "b": 1, "both": 9}


def test_merge_keeps_repo_value_for_value_held_keys():
    """값 보류 키는 판정표를 타지 않고 레포 값이 그대로 실린다."""
    r = ks.merge({"h": "local"}, {"h": "repo"}, {"h": "old"},
                 normalize=lambda m: m, hold=hold_keys(value=("h",)))
    assert r["merged"]["h"] == "repo"
    assert r["conflicts"] == [] and r["deleted"] == [] and r["local_stale"] == []
    assert r["held"] == ["h"]


def test_merge_does_not_delete_value_held_key_missing_from_local():
    """로컬에서 사라져도 보류 키는 케이스 3이 되지 않는다."""
    r = ks.merge({}, {"h": "repo"}, {"h": "repo"},
                 normalize=lambda m: m, hold=hold_keys(value=("h",)))
    assert r["deleted"] == []
    assert r["merged"]["h"] == "repo"


def test_merge_removes_value_held_key_from_next_base():
    r = ks.merge({"h": 1, "n": 1}, {"h": 1, "n": 1}, {"h": 1, "n": 1},
                 normalize=lambda m: m, hold=hold_keys(value=("h",)))
    assert "h" not in r["next_base"]
    assert r["next_base"]["n"] == 1
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -k merge -v`
기대: `AttributeError: module 'keyed_sync' has no attribute 'merge'`로 5개 FAIL

- [ ] **Step 2b: `next_base`의 본체를 `_next_base_normalized`로 뽑아낸다**

**근거:** Task 5 quality review I2-②

`merge`는 `local`·`base`를 이미 `_normalized`로 통과시키고 `merged`를 그 값들로 조립한다.
그 상태로 공개 `next_base`를 부르면 정규화가 **두 번** 적용된다. 코어는 멱등성을 집행하지
않기로 했으므로(spec 5.2), 비멱등 훅에서는 그 이중 적용이 base를 과전진시키거나 base와
레포를 즉시 어긋나게 만든다. `merge` 경로에서 그 의존 자체를 없앤다.

`keyed_sync.py`의 `next_base`를 아래 두 함수로 가른다. **루프 본문은 한 글자도 바꾸지 않는다** —
옮기기만 한다.

```python
def _next_base_normalized(local, old, merged, value_held):
    """이미 정규화된 세 매핑으로 다음 base를 만든다. next_base의 본체다.

    merge는 세 인자를 모두 정규화해 넘기므로 공개 next_base를 부르면 정규화가 두 번
    적용된다. 코어는 멱등성을 집행하지 않으므로(spec 5.2) 비멱등 훅에서는 그 이중 적용이
    base를 과전진시킬 수 있다. merge가 이 함수를 직접 불러 그 의존을 없앤다.
    단독 호출자(restore)는 공개 next_base를 쓴다.
    """
    out = {}
    for name in sorted(set(old) | set(merged)):
        if name in value_held:
            continue                                    # 값 보류 → base에서 제거
        if name in merged and name in local and same(merged[name], local[name]):
            out[name] = copy.deepcopy(merged[name])     # 로컬이 동의 → 전진
        elif name not in merged and name not in local:
            continue                                    # 양쪽에서 사라짐 → 제거
        elif name in old:
            out[name] = copy.deepcopy(old[name])        # 동의 안 함 → 이전 base 유지
    return out


def next_base(local, base, merged, *, normalize, value_held=frozenset()):
    """(기존 docstring 유지 — 정규화를 내부 적용하는 이유와 멱등 요구를 그대로 둔다.)"""
    return _next_base_normalized(
        _normalized(local, normalize),
        _normalized(base, normalize) if base else {},
        _normalized(merged, normalize),
        value_held,
    )
```

**확인:** 이 추출만으로 Task 5의 테스트가 **전부 그대로 통과해야 한다.** 하나라도 깨지면
옮기는 과정에서 의미가 바뀐 것이므로 되돌린다.

- [ ] **Step 3: 구현**

```python
def merge(local, repo, base, *, normalize, hold):
    """키 단위 3-way 병합 (판정표 케이스 1~10).

    base가 None이면 삭제 없이 합집합으로 degrade한다 — "타 기기 추가"와 "내 삭제"를
    구별할 수 없기 때문이다. 단 **양쪽에 있는 키는 로컬 값이 레포를 덮는다.**

    반환하는 next_base는 키 단위로 전진한다. 그래서 호출부가 conflicts 유무로 base 갱신을
    전역으로 게이트할 필요가 없다 — 항목 하나가 충돌 중이어도 나머지 base는 계속 전진한다.
    **전역 게이트를 되살리지 말 것.**

    conflicts에는 케이스 5(로컬 수정 vs 리모트 삭제)와 케이스 9(양쪽 변경)가 함께
    들어가는데 결과가 다르다 — 9는 merged에 레포 값이 남고 5는 merged에서 아예 빠진다.
    "name in result['merged']"로 둘을 구분할 수 있다.
    """
    local, repo = _normalized(local, normalize), _normalized(repo, normalize)
    base = None if base is None else _normalized(base, normalize)
    held = hold(local, repo)
    value_held = set(held["value"])

    merged, conflicts, deleted, local_stale, repo_ahead = {}, [], [], [], []
    for name in sorted(set(local) | set(repo) | set(base or {})):
        if name in value_held:
            if name in repo:
                merged[name] = repo[name]      # 레포 값 보존. 판정표를 타지 않는다
            continue
        in_l, in_r = name in local, name in repo
        if base is None:
            if in_l:
                merged[name] = local[name]
            elif in_r:
                merged[name] = repo[name]
            continue
        in_s = name in base
        if in_l and not in_r and not in_s:                  # 1 로컬 신규
            merged[name] = local[name]
        elif not in_l and in_r and not in_s:                # 2 타 기기 추가
            merged[name] = repo[name]
            repo_ahead.append(name)
        elif not in_l and in_r and in_s:                    # 3 로컬에서 삭제
            deleted.append(name)
        elif in_l and not in_r and in_s:                    # 4·5
            if same(local[name], base[name]):               # 4 타 기기 삭제, 로컬 잔존
                local_stale.append(name)
            else:                                           # 5 로컬 수정 vs 리모트 삭제
                conflicts.append(name)
        elif in_l and in_r:
            if same(local[name], repo[name]):               # 6 in_sync
                merged[name] = local[name]
            elif in_s and same(repo[name], base[name]):     # 7 로컬만 변경
                merged[name] = local[name]
            elif in_s and same(local[name], base[name]):    # 8 타 기기 변경
                merged[name] = repo[name]
                repo_ahead.append(name)
            else:                                           # 9 충돌
                conflicts.append(name)
                merged[name] = repo[name]
        # (암묵) 케이스 10: base에만 존재 → 어느 리스트에도 넣지 않는다
    return {
        "merged": merged,
        "conflicts": conflicts,
        "deleted": deleted,
        "local_stale": local_stale,
        "repo_ahead": repo_ahead,
        "held": sorted(value_held),
        # 공개 next_base가 아니라 내부 함수를 부른다 — local·base·merged가 이미
        # 정규화돼 있으므로 다시 정규화하면 멱등성에 의존하게 된다(Task 5 리뷰 I2).
        "next_base": _next_base_normalized(local, base or {}, merged, value_held),
    }
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: 신규 테스트가 전부 통과. **절대 개수를 적지 않는다** — 리뷰 후속 커밋이 테스트를 더하므로 계획 시점 숫자는 항상 어긋난다. 전체 스위트로 확인한다

- [ ] **Step 4b: 변조 확인 (필수)**

Task 2~5에서 **매번** SURVIVE가 나왔다. 성실성이 아니라 제도로 막는다. 임시 복사본에서
아래를 각각 적용하고 대응 테스트가 FAIL하는지 확인한다. 원본 작업 트리를 오염시키지 말 것.

이 task가 도입한 **가드 절을 하나씩** 뒤집는다:
- 판정표 열 갈래의 `elif` 조건을 하나씩 앞 갈래로 흡수 (특히 케이스 4↔5, 7↔8, 9)
- `base is None` degrade 갈래에서 `if in_l ... elif in_r`의 우선순위를 뒤집기 (**로컬이 이겨야 한다**)
- `value_held` 조기 `continue`에서 `if name in repo: merged[name] = repo[name]`을 지우기
- `repo_ahead.append(name)`를 케이스 2·8 중 하나에서 지우기
- `_next_base_normalized(local, base or {}, ...)`를 공개 `next_base(...)`로 되돌리기
- `same(local[name], base[name])`과 `same(repo[name], base[name])`을 서로 바꾸기 (**케이스 7↔8 반전**)

`merge`가 만드는 `next_base`를 **케이스 8·9에 대해 직접 단언한다** — 현재 블록은
`test_merge_removes_value_held_key_from_next_base` 한 곳에서만 본다. Task 5의 C1과
중복 방어를 이룬다.

**SURVIVE하면 구현이 아니라 테스트를 보강한다.** 보강한 줄 옆에 어떤 변조를 잡는지 주석으로 남긴다.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests/test_keyed_sync.py
git commit -m "feat(core): merge — 판정표 열 케이스와 값 보류 통과"
```

---

### Task 7: `keyed_sync.restore_plan`

**근거:** spec 5.2, 5.3(값 보류의 `restore_plan` 동작 — `value_held` 버킷), MCP spec 7.7

**Files:**
- Modify: `plugins/claude-sync/lib/keyed_sync.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py`

- [ ] **Step 1: 실패하는 test 작성**

```python
def always_restorable(key, value):
    return True


def no_secrets(value):
    return []


def test_restore_plan_separates_cases_7_8_9():
    """세 케이스를 한 버킷으로 뭉치면 안 된다 — 처방이 다르다."""
    local = {"c7": 2, "c8": 1, "c9": 2}
    repo = {"c7": 1, "c8": 2, "c9": 3}
    base = {"c7": 1, "c8": 1, "c9": 1}
    plan = ks.restore_plan(local, repo, base, normalize=lambda m: m, hold=ks.no_hold,
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["local_ahead"] == ["c7"]
    assert plan["repo_ahead"] == ["c8"]
    assert plan["both_changed"] == ["c9"]


def test_restore_plan_local_stale_holds_cases_4_and_5():
    """케이스 5를 담지 않으면 탈출구 없는 상태가 된다."""
    plan = ks.restore_plan({"c4": 1, "c5": 2}, {}, {"c4": 1, "c5": 1},
                           normalize=lambda m: m, hold=ks.no_hold,
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["local_stale"] == ["c4", "c5"]


def test_restore_plan_routes_add_needs_secret_and_unrestorable():
    plan = ks.restore_plan({}, {"ok": 1, "sec": 1, "bad": 1}, {},
                           normalize=lambda m: m, hold=ks.no_hold,
                           restorable=lambda k, v: k != "bad",
                           secret_keys=lambda v: ["k"] if v == 1 else [])
    assert plan["unrestorable"] == ["bad"]
    assert plan["needs_secret"] == ["ok", "sec"]
    assert plan["add"] == []


def test_restore_plan_action_held_goes_to_its_own_bucket_only():
    """행동 보류 키는 어떤 CLI 명령의 대상도 되지 않는다."""
    plan = ks.restore_plan({}, {"h": 1}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("h",), action=("h",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["action_held"] == ["h"]
    assert plan["add"] == [] and plan["value_held"] == []


def test_restore_plan_value_held_installs_when_absent_locally():
    """값 보류지만 행동 보류가 아니면 설치 대상이다 (H3)."""
    plan = ks.restore_plan({}, {"h": ["1.0.0"]}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("h",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["add"] == ["h"]
    assert plan["value_held"] == [] and plan["action_held"] == []


def test_restore_plan_value_held_uses_own_bucket_when_present_locally():
    """이미 설치돼 있으면 전용 버킷 — 케이스 9로 부르면 금지된 문구가 나간다."""
    plan = ks.restore_plan({"h": True}, {"h": ["1.0.0"]}, {}, normalize=lambda m: m,
                           hold=hold_keys(value=("h",)),
                           restorable=always_restorable, secret_keys=no_secrets)
    assert plan["value_held"] == ["h"]
    assert plan["both_changed"] == [] and plan["add"] == []
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -k restore_plan -v`
기대: `AttributeError: module 'keyed_sync' has no attribute 'restore_plan'`로 6개 FAIL

- [ ] **Step 3: 구현**

```python
BUCKETS = (
    "add", "needs_secret", "unrestorable", "in_sync", "local_ahead",
    "repo_ahead", "both_changed", "local_stale", "local_only",
    "value_held", "action_held",
)


def restore_plan(local, repo, base, *, normalize, hold, restorable, secret_keys):
    """복원 계획. diff·merge와 마찬가지로 비교 직전 양쪽에 normalize를 적용한다.

    케이스 7·8·9를 한 버킷으로 뭉치지 않는다 — 처방이 서로 다르고, 특히 케이스 7에
    "레포 값 채택"을 제시하면 아직 백업되지 않은 로컬 변경이 파괴된다.
    local_stale은 케이스 4와 5를 모두 담는다 — 담지 않으면 케이스 5가 탈출구 없는 상태가 된다.

    보류 키는 두 축으로 갈린다(spec 5.3):
      행동 보류        → action_held 버킷에만. 어떤 CLI 명령의 대상도 되지 않는다
      값 보류(행동 아님) → 로컬에 없으면 add(설치 대상), 있으면 value_held 전용 버킷
    value_held를 판정표에 태우면 케이스 9로 분류되어 "양쪽이 모두 바뀌었습니다"가 뜨는데,
    그것은 사실이 아니고 "레포 따르기"를 실행할 수단도 없다.
    """
    local, repo = _normalized(local, normalize), _normalized(repo, normalize)
    known = _normalized(base, normalize) if base else {}
    held = hold(local, repo)
    value_held, action_held = set(held["value"]), set(held["action"])

    plan = {key: [] for key in BUCKETS}

    def route_new(name, value):
        """레포에만 있는 항목을 add/needs_secret/unrestorable로 보낸다."""
        if not restorable(name, value):
            plan["unrestorable"].append(name)
        elif secret_keys(value):
            plan["needs_secret"].append(name)
        else:
            plan["add"].append(name)

    for name in sorted(set(local) | set(repo)):
        if name in action_held:
            plan["action_held"].append(name)
            continue
        if name in value_held:
            if name in local:
                plan["value_held"].append(name)
            elif name in repo:
                route_new(name, repo[name])
            continue
        in_local, in_repo = name in local, name in repo
        if in_repo and not in_local:
            route_new(name, repo[name])
        elif in_local and in_repo:
            if same(local[name], repo[name]):                        # 6
                plan["in_sync"].append(name)
            elif name in known and same(repo[name], known[name]):    # 7
                plan["local_ahead"].append(name)
            elif name in known and same(local[name], known[name]):   # 8
                plan["repo_ahead"].append(name)
            else:                                                    # 9
                plan["both_changed"].append(name)
        elif name in known:                                          # 4·5
            plan["local_stale"].append(name)
        else:                                                        # 1
            plan["local_only"].append(name)
    return plan
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -v`
기대: 신규 테스트가 전부 통과. **절대 개수를 적지 않는다** — 리뷰 후속 커밋이 테스트를 더하므로 계획 시점 숫자는 항상 어긋난다. 전체 스위트로 확인한다

- [ ] **Step 4b: 변조 확인 (필수)**

임시 복사본에서 아래를 각각 적용하고 대응 테스트가 FAIL하는지 확인한다.
원본 작업 트리를 오염시키지 말 것.

**세 축은 템플릿이다 — 매 task마다 반드시 넣는다.** Task 6에서 이 셋이 변조 목록에 없었고,
성실히 목록을 따른 구현자가 정확히 그 자리에 착지했다(구현자가 돌린 9종은 전부 CAUGHT였고
목록 밖 15종에서만 구멍이 나왔다). `restore_plan`은 **두 축이 같은 dict에 함께 나타나는
유일한 함수**라 축 혼동의 폭발 반경이 가장 크다.

1. **`hold` 호출 계약** — `hold`를 정규화 **전** 값으로 부르기, `hold(repo, local)`로 좌우 뒤집기.
   `recording_hold`로 잡는다. MCP는 `no_hold`뿐이라 **Task 8 게이트를 정상 통과한 뒤
   다음 plan에서야 발현한다.**
2. **축 분리** — `value_held`와 `action_held`를 합치기(`set(held["value"]) | set(held["action"])`),
   그리고 서로 바꾸기. 두 축이 **동시에 비어 있지 않은** 픽스처가 반드시 있어야 잡힌다.
3. **`{}` vs `None`** — `base` 인자에 `{}`를 넣는 경로가 없으면 degrade 판정이 미고정이다.
   `base={}`는 **첫 백업 직후에 실제로 나오는 값**이다.

그 위에 이 task 고유의 것들:

- `if name in action_held` 갈래를 `value_held` 갈래 **뒤로** 옮기기 (**두 축의 우선순위가 계약이다**)
- `route_new`의 `restorable`/`secret_keys` 호출 순서 바꾸기
- `route_new`에서 `not restorable(...)` 갈래를 지우기
- `value_held`인데 로컬에 있는 경우를 `value_held` 버킷 대신 판정표로 보내기
- 케이스 7·8의 `same(repo[name], known[name])`과 `same(local[name], known[name])` 바꾸기
- `elif name in known` (케이스 4·5) 갈래를 `else`로 바꾸기

**SURVIVE하면 구현이 아니라 테스트를 보강한다.**

- [ ] **Step 4c: `hold` 소비 함수 전수 가드를 넣는다**

**근거:** Task 6 quality review — "예고된 위험을 예고만 하고 게이트를 안 걸었다"

`hold`를 소비하는 함수는 이제 셋이다(`diff`·`merge`·`restore_plan`). MCP 어댑터는 `no_hold`만
주입하므로 **호출 계약이 틀려도 Task 8의 기존 테스트 게이트가 절대 잡지 못한다.** 다음 plan의
`plugin_config`가 붙는 순간에야 발현한다. 소스 스캔 가드로 못박는다 —
`test_mcp_config.py:654`가 이미 같은 형태(`PARSE_BACKUP_CALL`)를 쓴다.

`tests/test_keyed_sync.py`에 추가한다.

```python
HOLD_CONSUMER = re.compile(r"^def (\w+)\(.*\bhold\b", re.M)


def test_every_hold_consuming_function_has_a_recording_hold_test():
    """hold를 받는 코어 함수는 인자·순서·정규화 여부를 거는 테스트를 하나씩 가져야 한다.

    MCP는 no_hold뿐이라 호출 계약이 틀려도 기존 테스트 게이트가 잡지 못한다 —
    plugin_config가 붙는 순간에야 발현한다(spec 7.3의 H1~H4는 좌우 비대칭이다).
    """
    source = open(os.path.join(LIB_DIR, "keyed_sync.py"), encoding="utf-8").read()
    consumers = {name for name in HOLD_CONSUMER.findall(source)
                 if not name.startswith("_") and name != "no_hold"}
    tests = open(__file__, encoding="utf-8").read()
    missing = [name for name in sorted(consumers)
               if "recording_hold" not in _test_body_for(tests, name)]
    assert missing == [], "recording_hold 테스트가 없는 hold 소비 함수: %s" % missing
```

`_test_body_for(tests, name)`는 `def test_<name>_...`로 시작하는 모든 테스트 본문을 이어
붙여 돌려주는 헬퍼다. 이 파일 상단에 `import os`·`import re`와 `LIB_DIR` 상수가 필요하면 함께 더한다.

**변조 확인:** `merge`의 `recording_hold` 테스트를 임시로 지우고 이 가드가 FAIL하는지,
지우지 않았을 때 오탐 0인지 확인한다.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests/test_keyed_sync.py
git commit -m "feat(core): restore_plan — 버킷 열한 개와 두 축의 보류"
```

---

### Task 8: `mcp_config`를 어댑터로 교체

**근거:** spec 5.4, 5.5(회귀 금지 목록)

**이 task의 합격 기준은 단 하나 — `test_mcp_config.py`·`test_mcp_scripts.py`·`test_mcp_cycle.py`가 한 줄도 수정하지 않고 통과하는 것이다.** 통과하지 않으면 추출이 틀린 것이다.

**Files:**
- Modify: `plugins/claude-sync/lib/mcp_config.py` (전체 교체)
- Test: 기존 `tests/test_mcp_config.py`, `tests/test_mcp_scripts.py`, `tests/test_mcp_cycle.py` (수정 없음)

- [ ] **Step 1: 교체 전 기준선 기록**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: **Task 7 종료 시점의 개수 그대로.** 절대값을 적지 않는다 — 리뷰 후속 커밋이
테스트를 추가하면 계획 시점의 숫자는 항상 어긋난다(실제로 어긋났다: 기준선은 383이
아니라 385였다).

**여기서 나온 숫자를 적어 두고 Step 4에서 같은 숫자가 나오는지 본다.** Step 4까지는
테스트를 한 개도 더하지 않으므로 두 숫자는 반드시 같아야 한다. (그 뒤 Step 4.5가
어댑터 가드 하나를 더하므로 최종 개수는 +1이다.)

- [ ] **Step 2: `mcp_config.py`의 판정·인식 부분을 코어 호출로 교체**

아래 다섯 덩어리를 삭제한다 — `_BROKEN`, `_decode`, `_claims_newer_schema`, `_fingerprint`, 그리고 `LocalConfigUnavailable`·`UnknownBackupSchema`의 클래스 정의.
`_servers_from_obj`와 `_recognized_servers`는 **남긴다**(MCP 고유의 형식 지식이다).

파일 상단 import와 예외 re-export를 이렇게 바꾼다.

```python
import copy
import json          # read_local_servers·dump_backup이 여전히 쓴다. 지우지 말 것
import os
import re

import keyed_sync as ks

SENTINEL = "<REDACTED>"
SECRET_FIELDS = ("headers", "env")
SCHEMA_VERSION = 2
BACKUP_RELPATH = "mcp-servers.json"
DEFAULT_CLAUDE_JSON = os.path.expanduser("~/.claude.json")
VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")   # claude mcp add-json의 실측 제약

# 코어의 예외를 그대로 re-export한다. 클래스가 두 벌이 되면 스크립트의
# `except (mc.LocalConfigUnavailable, mc.UnknownBackupSchema, OSError)`가 갈라지고,
# 갱신을 잊으면 traceback으로 죽어 "읽기 실패로 백업 중단" 결함이 되살아난다.
LocalConfigUnavailable = ks.LocalConfigUnavailable
UnknownBackupSchema = ks.UnknownBackupSchema
```

- [ ] **Step 3: 인식·판정 함수를 위임 형태로 교체**

```python
def _recognized_servers(obj):
    """알아볼 수 있는 백업 문서면 servers 매핑, 아니면 None.

    v1 배열과 servers가 dict인 v2 객체만 인정한다. 이 판정이 parse_base·parse_backup·
    load_backup의 공통 기준이다 — 세 곳이 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이
    생기고, 그 비대칭이 상위 버전 백업을 파괴한다.
    """
    if isinstance(obj, list):
        return _servers_from_obj(obj)          # v1 배열에는 version 개념이 없다
    if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
        if ks.claims_newer_schema(obj.get("version"), SCHEMA_VERSION):
            return None
        return _servers_from_obj(obj)
    return None


def parse_backup(data):
    """JSON 바이트/문자열에서 servers 매핑을 읽는다(관대한 해석)."""
    return ks.parse_backup(data, _recognized_servers)


def parse_base(data):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None."""
    return ks.parse_base(data, _recognized_servers)


def load_backup(path):
    """레포의 mcp-servers.json을 안전하게 읽는다. 파일이 없으면 {}."""
    return ks.load_backup(path, _recognized_servers)


def same(a, b):
    """설정 동등 비교. 키 순서에 무관하다."""
    return ks.same(a, b)


def diff(local, backed):
    """상태 비교. 비교 직전 양쪽에 redact를 적용한다."""
    out = ks.diff(local, backed, normalize=redact, hold=ks.no_hold)
    return {"only_local": out["only_local"],
            "only_repo": out["only_repo"],
            "changed": out["changed"]}


def next_base(local, base, servers):
    """다음 base 매핑. base[name]은 로컬이 그 값에 동의할 때만 전진한다."""
    return ks.next_base(local, base, servers, normalize=redact)


def merge(local, repo, base):
    """서버 이름 키 단위 3-way 병합 (spec 7.2 판정표)."""
    r = ks.merge(local, repo, base, normalize=redact, hold=ks.no_hold)
    return {"servers": r["merged"],
            "conflicts": r["conflicts"],
            "deleted": r["deleted"],
            "local_stale": r["local_stale"],
            "repo_ahead": r["repo_ahead"],
            "next_base": r["next_base"]}


def restore_plan(local, backed, base):
    """복원 계획. 버킷 9개 — MCP에는 보류가 없으므로 held·value_held는 노출하지 않는다."""
    plan = ks.restore_plan(local, backed, base, normalize=redact, hold=ks.no_hold,
                           restorable=restorable, secret_keys=secret_keys)
    return {key: plan[key] for key in (
        "add", "needs_secret", "unrestorable", "in_sync", "local_ahead",
        "repo_ahead", "both_changed", "local_stale", "local_only")}
```

**`merge`·`diff`의 반환 dict에 `held`를, `restore_plan`의 반환 dict에 `value_held`·`action_held`를 넣지 않는다.** 공개 계약을 넓히지 않기 위해서다 — MCP에서 보류는 항상 비어 있으므로 정보도 없다.

**이 화이트리스트는 장식이 아니라 기존 테스트가 강제하는 요구사항이다.** `compare_mcp.py:28`이
`out.update(mc.diff(local, repo))`로 **반환 dict를 통째로 사용자 JSON에 펼치므로**, 어댑터가
`held`를 걸러내지 않으면 status 출력에 없던 필드가 생긴다. 그리고 `test_mcp_scripts.py:150`이
`assert out == {"status": "ok", "only_local": [], "only_repo": [], "changed": []}`로 **정확한
dict 동등**을 보므로, 화이트리스트를 빼먹으면 그 테스트가 FAIL한다. 나중에 누가 이것을
"불필요한 복사"로 오해해 지우지 않도록 여기 적어 둔다.

- [ ] **Step 4: 전체 회귀 확인 — 이 task의 합격 기준**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: **Step 1에서 적어 둔 숫자와 동일.** 하나라도 실패하면 추출이 틀린 것이므로 되돌리고 원인을 찾는다.

실행: `git diff --stat plugins/claude-sync/tests/`
기대: **출력 없음** (기존 테스트를 한 줄도 고치지 않았다. Step 4.5가 더하는 새 테스트는 이 확인 **뒤에** 넣는다)

- [ ] **Step 4.5: 세 함수가 같은 `recognize`를 받는지 어댑터에서 가드한다**

**근거:** spec 4.4 / Task 3 quality review 권고 3

코어는 `recognize`를 파라미터로 받으므로 **셋이 같은 훅인지 강제할 수 없다.** 어댑터가
셋에 다른 훅을 넘겨도 코어는 막지 못하고, 그것이 spec 4.4가 파괴 요인으로 지목한
"이력은 못 믿는데 레포는 믿는" 비대칭이다. 어댑터 쪽에서 걸어야 한다.

`tests/test_keyed_sync.py` 끝에 추가한다(`import mcp_config as mc`를 파일 상단
`import keyed_sync as ks` 옆에 함께 둔다).

```python
def test_mcp_adapter_passes_one_recognize_hook_to_all_three(tmp_path, monkeypatch):
    """어댑터가 세 함수에 같은 recognize를 넘겨야 한다.

    코어는 훅을 파라미터로 받으므로 공유를 강제할 수 없다. 갈리면 "이력은 못 믿는데
    레포는 믿는" 비대칭이 생기고 상위 버전 백업이 파괴된다(spec 4.4).
    """
    seen = []

    def capture(*args):
        seen.append(args[-1])   # 세 코어 함수 모두 recognize가 마지막 위치 인자다
        return {}

    monkeypatch.setattr(mc.ks, "parse_base", capture)
    monkeypatch.setattr(mc.ks, "load_backup", capture)
    monkeypatch.setattr(mc.ks, "parse_backup", capture)

    mc.parse_base(b'{"version": 2, "scope": "user", "servers": {}}')
    mc.load_backup(str(tmp_path / "none.json"))
    mc.parse_backup(b'{"version": 2, "scope": "user", "servers": {}}')

    assert len(seen) == 3
    assert len({id(hook) for hook in seen}) == 1
```

**변조 확인:** 임시 복사본에서 어댑터의 `parse_backup`이 다른 훅(예: `lambda obj: obj`)을
넘기도록 바꾸고 이 테스트가 FAIL하는지 본다.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/mcp_config.py
git commit -m "refactor(mcp): 판정·인식을 코어에 위임하고 어댑터만 남긴다"
```

---

### Task 9: `test_mcp_state_machine.py` 파라미터화

**근거:** spec 5.4, 5.5(단정 약화 금지)

지금은 `mcp_config`에 직접 묶여 있다. 어댑터와 값 픽스처를 주입받는 형태로 재작성해, 나중에 `plugin_config`가 붙으면 **같은 상태 기계 테스트를 두 어댑터에 대해** 돌린다.

**재작성 전후로 MCP 어댑터에 대한 단정이 하나도 약해지면 안 된다.** 테스트 10개가 그대로 10개여야 하고, 각 단정의 의미가 같아야 한다.

**Files:**
- Modify: `plugins/claude-sync/tests/test_mcp_state_machine.py` (전체 교체)

- [ ] **Step 1: 파라미터화된 형태로 재작성**

파일 전체를 아래로 교체한다.

```python
"""backup을 반복 적용했을 때 고정점에 도달하는지 검증한다.

단발 호출 테스트는 상태 기계 결함을 잡지 못한다. 이전 설계의 Critical 결함
("base ← 레포 파일 전체")은 판정표를 100% 덮은 테스트를 전부 통과했지만,
2회차 백업에서 타 기기의 서버를 전멸시켰다.

**어댑터와 값 픽스처를 주입받는다.** 플러그인 어댑터가 추가되면 ADAPTERS에
한 줄을 더해 같은 열 개의 시나리오를 그대로 돌린다 — 상태 기계를 복사하지 않기 위해서다.
"""
import pytest

import mcp_config as mc


class Adapter:
    """상태 기계 테스트가 어댑터에 요구하는 최소 표면."""

    def __init__(self, name, merge, next_base, values):
        self.name = name
        self.merge = merge
        self.next_base = next_base
        self.A, self.B, self.ORIG = values


ADAPTERS = [
    Adapter("mcp", mc.merge, mc.next_base,
            ({"command": "a"}, {"command": "b"}, {"command": "o"})),
]


@pytest.fixture(params=ADAPTERS, ids=lambda a: a.name)
def adapter(request):
    return request.param


def backup_round(adapter, local, repo, base):
    """푸시에 성공한 backup 1회를 흉내낸다: 레포 ← 병합 결과, base ← next_base."""
    result = adapter.merge(local, repo, base)
    merged = result.get("servers", result.get("merged"))
    return result, merged, result["next_base"]


def repeat_backup(adapter, local, repo, base, rounds=3):
    """같은 로컬로 backup을 rounds회 반복하고 매 회차의 (보고, 레포, base)를 모은다."""
    snapshots = []
    for _ in range(rounds):
        result, repo, base = backup_round(adapter, local, repo, base)
        report = {k: v for k, v in result.items()
                  if k not in ("servers", "merged", "next_base")}
        snapshots.append((report, repo, base))
    return snapshots


def assert_fixed_point_from_second_round(snapshots):
    """2회차부터 레포 내용과 보고가 변하지 않아야 한다."""
    assert snapshots[1] == snapshots[2], "2회차와 3회차가 다르다 — 고정점이 아니다"


def test_repeated_backup_without_cleanup_keeps_reporting_local_stale(adapter):
    """케이스 4를 정리하지 않고 반복해도 항목이 되살아나지 않고 base[X]가 전진하지 않는다."""
    A = adapter.A
    local = {"X": A, "y": A}
    snapshots = repeat_backup(adapter, local, {"y": A}, {"X": A})
    for report, repo, base in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo
        assert base["X"] == A
        assert base["y"] == A
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_removed_backup_converges_without_stale(adapter):
    """restore '제거' 경로: X가 L·R·S 어디에도 없는 상태로 안정된다."""
    A = adapter.A
    local = {"y": A}
    base = adapter.next_base(local, {"X": A, "y": A}, {"y": A})
    assert "X" not in base
    snapshots = repeat_backup(adapter, local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == [] and report["deleted"] == []
        assert sorted(repo) == ["y"]
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_kept_backup_pushes_entry_back(adapter):
    """restore '유지' 경로: base에서 X를 지웠으므로 케이스 1로 push되고 이후 불변."""
    A = adapter.A
    local = {"X": A, "y": A}
    base = adapter.next_base(local, {"X": A}, {"y": A})
    base.pop("X", None)
    snapshots = repeat_backup(adapter, local, {"y": A}, base)
    assert sorted(snapshots[0][1]) == ["X", "y"]
    for report, _, _ in snapshots:
        assert report["local_stale"] == []
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_deferred_backup_keeps_case4(adapter):
    """restore '나중에' 경로: 아무것도 바뀌지 않고 케이스 4가 반복된다."""
    A = adapter.A
    local = {"X": A, "y": A}
    base = adapter.next_base(local, {"X": A}, {"y": A})
    assert base["X"] == A
    snapshots = repeat_backup(adapter, local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case9_conflict_freezes_base(adapter):
    """케이스 9: 매회 conflicts=[Z], 레포는 R 유지, base[Z] 고정."""
    A, B, ORIG = adapter.A, adapter.B, adapter.ORIG
    snapshots = repeat_backup(adapter, {"Z": A}, {"Z": B}, {"Z": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert repo["Z"] == B
        assert base["Z"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case5_conflict_freezes_base(adapter):
    """케이스 5: 매회 conflicts=[X], 레포에 X 없음, base[X] 고정."""
    A, ORIG = adapter.A, adapter.ORIG
    snapshots = repeat_backup(adapter, {"X": A}, {}, {"X": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["X"]
        assert "X" not in repo
        assert base["X"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_conflicted_name_freezes_only_its_own_base(adapter):
    """전역 게이트를 되살리면 안 되는 이유 — 충돌 하나가 전체 base를 동결하지 않는다."""
    A, B, ORIG = adapter.A, adapter.B, adapter.ORIG
    snapshots = repeat_backup(adapter, {"Z": A, "n": B}, {"Z": B}, {"Z": ORIG})
    for report, _, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert base["Z"] == ORIG
        assert base["n"] == B
    assert_fixed_point_from_second_round(snapshots)


def test_case2_remote_added_survives_repeated_backup(adapter):
    """타 기기가 추가한 항목이 2회차에도 레포에 남는다 — 옛 설계가 여기서 데이터를 잃었다."""
    A, B = adapter.A, adapter.B
    snapshots = repeat_backup(adapter, {"x": A}, {"x": A, "z": B}, {"x": A})
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["z"] == B
        assert report["repo_ahead"] == ["z"]
    assert_fixed_point_from_second_round(snapshots)


def test_case8_remote_change_survives_repeated_backup(adapter):
    """타 기기의 변경이 로컬 값으로 되돌아가지 않는다."""
    B, ORIG = adapter.B, adapter.ORIG
    snapshots = repeat_backup(adapter, {"x": ORIG}, {"x": B}, {"x": ORIG})
    for report, repo, base in snapshots:
        assert repo["x"] == B
        assert base["x"] == ORIG
        assert report["repo_ahead"] == ["x"]
    assert_fixed_point_from_second_round(snapshots)


def test_new_machine_without_base_does_not_delete_others_on_second_round(adapter):
    """base=None으로 시작한 새 기기가 2회차에 남의 항목을 삭제하지 않는다."""
    A, B = adapter.A, adapter.B
    snapshots = repeat_backup(adapter, {"mine": A}, {"theirs": B}, None)
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["theirs"] == B
    assert_fixed_point_from_second_round(snapshots)
```

- [ ] **Step 2: 개수와 단정이 약해지지 않았는지 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_state_machine.py -v`
기대: **10 passed**, 각 이름이 `[mcp]` 접미사를 갖는다.

실행: `git diff plugins/claude-sync/tests/test_mcp_state_machine.py | grep '^-' | grep 'assert' | wc -l`
실행: `git diff plugins/claude-sync/tests/test_mcp_state_machine.py | grep '^+' | grep 'assert' | wc -l`
기대: 두 숫자가 같다. 다르면 단정이 사라졌거나 늘었으므로 확인한다.

- [ ] **Step 3: 전체 회귀 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: **Task 8 종료 시점의 개수와 동일** (Task 9는 테스트를 재작성할 뿐 개수를 바꾸지 않는다)

- [ ] **Step 4: Commit**

```bash
git add plugins/claude-sync/tests/test_mcp_state_machine.py
git commit -m "test: 상태 기계 시나리오를 어댑터·값 픽스처 주입 형태로 바꾼다"
```

---

## 완료 정의

- [ ] `uv run --with pytest pytest plugins/claude-sync/tests -q` → **Task 8 Step 1의 기준선 +1(Step 4.5의 어댑터 가드), 0 failed**
- [ ] `git diff --stat main..HEAD -- plugins/claude-sync/tests/test_mcp_config.py plugins/claude-sync/tests/test_mcp_cycle.py` → **출력 없음** (두 파일을 고치지 않았다)
- [ ] `lib/mcp_config.py`에서 `_BROKEN`·`_decode`·`_claims_newer_schema`·`_fingerprint`가 사라졌고, 예외 두 클래스가 `keyed_sync`의 것을 가리킨다
- [ ] `python3 -c "import sys; sys.path.insert(0,'plugins/claude-sync/lib'); import mcp_config as m, keyed_sync as k; assert m.UnknownBackupSchema is k.UnknownBackupSchema"` → 조용히 종료
- [ ] `test_mcp_state_machine.py`의 테스트 10개가 `[mcp]` 파라미터로 돈다

## 다음 plan으로 넘길 것

| 항목 | 근거 |
|---|---|
| `lib/plugin_config.py`와 세 스크립트, 세 SKILL.md | spec 6·7·8·9장 |
| `lib/compat.py` shape 확장, `detect_downgrade.py`, `generate_metadata.py` | spec 11장 |
| 문서 정정 열 곳 | spec 13장 |
| `test_plugin_cycle.py`와 CLI 에뮬레이터 | spec 5.6, 14.3 |

### 실행 중 발견된 인계 항목

Task 1의 두 리뷰가 범위 밖으로 판정했지만 기록해 둔 것들이다. 다음 plan을 쓸 때
"문서 정정"으로 뭉뚱그리면 조용히 누락되는 자리다.

| 항목 | 무엇 | 근거 |
|---|---|---|
| **`dump_backup` 비원자성** | `lib/mcp_config.py:228-234`가 `open(path,"w")`로 먼저 truncate한다. 쓰기 도중 실패(ENOSPC/EIO)하면 레포 파일이 잘린 채 남고, 다음 백업이 그것을 `{}`로 degrade해 **모든 서버를 케이스 4로 판정**한다 → restore가 "다른 기기가 삭제했습니다"를 띄운다. Task 1이 막은 것과 **같은 거짓 문구로 가는 두 번째 문**이다. `detect_downgrade`는 `shape=broken`을 분기하지 않아 조용하다. tmp+`os.replace` 4줄. `plan_mcp.apply_base:74`·`sync_state.write_base:47-58`도 같은 형태 | Task 1 quality review I1 |
| **`base_staging:"failed"` 보고 배선** | `collect_mcp.py`가 이 키를 반환만 하고 소비하는 곳이 없다. `SKILL.md:290-292`의 `status` 분기는 `skipped`일 때만 `reason`을 보고한다. spec 7.4는 "보고한다"고 썼다 | spec 7.4 / quality review P1 |
| **`SKILL.md:397` 주석 근거 교체** | 현재: "collect_mcp.py가 status=ok일 때만 쓰므로, 파일 존재가 곧 'skip 아님'이다". 결론은 이제 참이지만 근거가 낡았다. spec 7.4가 docstring과 **함께** 고치라고 지목했고 docstring만 고쳤다 | spec 7.4 / quality review M3 |
| **`reason` 키 이름 충돌** | `status:"ok"` payload에 `reason`이 실린다. `reason`은 `SKILL.md:292`가 skipped 경로의 필드로 문서화한 이름이다. 배선을 붙일 때 `base_staging_reason` 등으로 정할 것 | quality review M6 |
| **스테이징 위생의 근거가 코드 밖에 있다** | `os.replace` 실패 시 남는 `.tmp`가 무해한 이유는 호출부(`SKILL.md:285`, `sync-restore/SKILL.md:369`)가 실행마다 `rm -rf`하기 때문이다. spec 7.4의 미래 배선이 `BASE_STAGING`을 공유하고 `rm -rf`를 앞으로 옮기므로, "실행당 한 번 비운다"가 유지되어야 이 성질이 산다. docstring에 전제로 한 줄 남길 것 | quality review M4 |
| **`chmod(0)` 기반 권한 테스트가 root에서 판별력을 잃는다** | `test_keyed_sync.py`의 `test_load_backup_propagates_permission_error`, `test_downgrade.py:137`, `test_compat.py:134,153`이 모두 이 관행을 쓴다. root는 권한 비트를 무시하므로 정상 구현에서도 `DID NOT RAISE`로 **거짓 실패**한다 — 조용히 통과하는 것이 아니라 상시 빨간 테스트가 되고, 누군가 skip 처리하면 그 시점부터 보호가 사라진다. 현재 root로 도는 CI 설정은 없다. 다루려면 저장소 전역으로 `os.getuid() == 0`일 때 skip | Task 3 quality r2 N-1 |
| **`apply_base`와의 패턴 비대칭** | `plan_mcp.apply_base:73-74`는 여전히 최종 이름으로 직접 쓴다. 앞에 "레포 쓰기"가 없어 같은 결함이 성립하지 않는 **정당한 비대칭**이지만, 두 스크립트가 다른 패턴을 쓰게 됐으니 근거를 한 줄 남길 것 | quality review 교차 패스 |

**이 plan이 끝나야 다음 plan을 쓸 수 있다.** Task 8의 결과가 코어 시그니처를 확정하고, 다음 plan의 모든 task가 그 시그니처에 의존한다.
