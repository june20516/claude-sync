# 플러그인 동기화 본체 Implementation Plan

> **agentic worker에게:** REQUIRED SUB-SKILL: 이 plan을 task 단위로 구현하려면 suberpower:subagent-driven-development(권장) 또는 suberpower:executing-plans를 사용하세요. Step은 추적을 위해 checkbox(`- [ ]`) 문법을 사용합니다.

**Goal:** `plugins.json`을 키 단위 3-way 병합 대상으로 만든다. 세 섹션(`enabledPlugins`·`extraKnownMarketplaces`·`pluginConfigs`)이 각각 값 무관 코어를 타고, 세 스킬이 새 스크립트를 부른다. **결함 A(통째 덮어쓰기)·B(켬/끔 미감지)·C(예외 처리 부재)가 여기서 해소된다**(spec 부록 A).

**Architecture:** `lib/plugin_config.py`가 코어(`lib/keyed_sync.py`)의 **두 번째 어댑터**다. 섹션마다 다른 `normalize`·`hold`·`restorable`·`secret_keys`를 클로저로 만들어 주입한다. 문서 하나·base 블롭 하나 안에서 세 섹션이 **독립적으로** 판정된다(섹션 간 게이트 없음). 보류는 **두 축**(값 보류 = push 금지 / 행동 보류 = CLI 금지)이고 **네 종류**(H1~H4)다.

**Tech Stack:** Python 3.13 표준 라이브러리만. 테스트는 pytest (`uv run --with pytest pytest`).

---

## 이 plan의 범위

| 포함 | 제외 (plan ③) |
|---|---|
| `lib/plugin_config.py` 신규 (spec 3·4·6·7·8) | `lib/compat.py` shape 확장 (spec 11.6) |
| `collect_plugins.py`·`compare_plugins.py`·`plan_plugins.py` 신규 (spec 9·10) | `detect_downgrade.py`의 relpath 파라미터화 (spec 11.6) |
| 세 `SKILL.md` 배선 + `extract_plugins.py` 삭제 (spec 7.4·9·12장) | `generate_metadata.py`의 `schema` 맵 (spec 11.3) |
| 문서 정정 **열 곳** + 새 한계 (spec 13장 첫 표) | 다운그레이드 대화 문단 셋 (spec 13장 마지막 세 행) |
| 보류 상태 기계 시나리오·교대 시나리오 (spec 14) | 2.x 배포 순서 경고 **네 곳** (spec 13장 두 번째 표) |
| plan ①이 넘긴 인계 12건 전부 | 실환경 스모크 (spec 14.5) |

**착수 시점:** 브랜치 `feat/plugin-config`, `release/3.0.0`(`0972b7d`)에서 분기, **446 passed**.

**근거 절 표기.** 각 task 머리에 `**근거:** spec N.M`을 적었다. spec의 그 절이 바뀌면 그 task는 무효다 — 폭발 반경을 기계적으로 식별하기 위한 장치다. **전제가 깨지면 plan이 아니라 spec부터 고친다.**

**사용자 가치는 Task 14에서 처음 나온다.** Task 4~13이 전부 끝나도 스킬이 새 스크립트를 부르지 않으면 사용자에게 보이는 변화는 0이다(spec 부록 A). Task 1·2는 예외 — MCP 경로의 실제 결함을 고친다.

---

## plan ①이 넘긴 인계 12건이 어디로 갔나

`plans/2026-08-24-keyed-sync-core.md` 말미의 표를 이 plan이 흡수한다. **"문서 정정"으로 뭉뚱그리면 조용히 누락되는 자리**라고 그 표가 경고했으므로 대응을 명시한다.

| 인계 항목 | 흡수한 task |
|---|---|
| `dump_backup` 비원자성 (`plan_mcp.apply_base`·`sync_state.write_base` 포함) | **Task 1** |
| `base_staging:"failed"` 보고 배선 | **Task 2** |
| `SKILL.md:397` 주석 근거 교체 | **Task 2** |
| `reason` 키 이름 충돌 → `base_staging_reason` | **Task 2** |
| 스테이징 위생의 근거가 코드 밖에 있다 (docstring 전제) | **Task 2** |
| `restore_plan`의 `base=None`/`{}` 동일 처리가 docstring에 없다 | **Task 2** |
| `apply_base`와의 패턴 비대칭 근거 | **Task 2** |
| `chmod(0)` 권한 테스트가 root에서 판별력을 잃는다 | **Task 3** |
| `recognize` 공유 가드가 `mc`에 하드코딩 | **Task 3**(파라미터화) + **Task 4**(`plugin_config` 등록) |
| 보류 상태 기계 커버리지가 0이다 | **Task 11** |
| `test_plugin_cycle.py`와 CLI 에뮬레이터 | **Task 12·13** |
| 어댑터 테스트 ~25개가 코어 로직을 중복 검증 | **조치 없음.** 회귀 안전망이므로 삭제하지 않는다(최종 리뷰 m-4). 이 plan은 `test_mcp_config.py`를 건드리지 않는다 |

---

## File Structure

| 파일 | 책임 |
|---|---|
| `lib/keyed_sync.py` | `dump_json` 추가(Task 1), `restore_plan` docstring 보강(Task 2). **판정 로직은 건드리지 않는다** |
| `lib/plugin_config.py` | **신규.** 플러그인 어댑터 — 두 파일 읽기, 인식, 섹션별 정규화·보류·복원 가능성, 지문 |
| `lib/sync_state.py` | `write_base` 원자화(Task 1) |
| `lib/mcp_config.py` | `dump_backup`이 `ks.dump_json`을 쓴다(Task 1) |
| `skills/sync-backup/scripts/collect_plugins.py` | **신규.** 세 섹션 merge → 레포·스테이징 기록 |
| `skills/sync-backup/scripts/collect_mcp.py` | `base_staging_reason` 개명 + docstring 전제(Task 2) |
| `skills/sync-backup/scripts/extract_plugins.py` | **삭제**(Task 14 — 스킬이 새 스크립트를 부르게 된 뒤에) |
| `skills/sync-status/scripts/compare_plugins.py` | **신규.** 읽기 전용 섹션별 diff + 보류 보고 |
| `skills/sync-status/scripts/check_status.py` | 59~76행(키 집합 비교) 삭제(Task 14) |
| `skills/sync-restore/scripts/plan_plugins.py` | **신규.** `plan` + `apply-base`. `plugins-held.json`의 **소유자** |
| `skills/sync-restore/scripts/plan_mcp.py` | `apply_base` docstring에 `.tmp` 제외 근거(Task 2) |
| 세 `SKILL.md` | 배선 교체(Task 14) + 서술 정정(Task 15) |
| `tests/marks.py` | **신규.** root에서 판별력을 잃는 테스트의 skip 마커 |
| `tests/test_plugin_config.py` | **신규.** 어댑터 단위 |
| `tests/test_plugin_scripts.py` | **신규.** 세 스크립트 계약 |
| `tests/plugin_cli.py` | **신규.** CLI 에뮬레이터(spec 14.3) — 테스트가 아니다 |
| `tests/test_plugin_cycle.py` | **신규.** 교대 시나리오(spec 14.2) |
| `tests/test_mcp_state_machine.py` | 보류 시나리오 + 회차별 오버라이드 훅 + 플러그인 어댑터 둘(Task 11) |
| `tests/test_script_root.py` | 앵커 갱신(Task 14) |

`tests/conftest.py`가 `lib`를 `sys.path`에 넣으므로 테스트는 `import plugin_config as pc`로 바로 쓴다. pytest가 `tests/` 자체도 `sys.path`에 넣으므로 `from marks import ...`·`import plugin_cli`가 동작한다.

---

## 어댑터가 코어에 주입하는 것 (Task 4~10이 공유한다)

```python
recognize(obj)          -> mapping | None   # 알아보면 매핑(비었으면 {}), 아니면 None
normalize(mapping)      -> mapping          # 값 층위 변환만. 멱등. 키를 더하거나 빼지 않는다
hold(local, repo)       -> {"value": set[str], "action": set[str]}   # 정규화된 입력을 받는다
restorable(key, value)  -> bool
secret_keys(value)      -> list             # 복원 시 사용자에게 물어야 하는 항목
```

**세 가지를 헷갈리면 곧바로 데이터 손실이다.** plan ①의 실행에서 실측으로 확인된 것들이다.

1. **`normalize`는 키를 지우지 않는다.** 키 층위 제외는 전부 `hold`의 몫이다. 코어의 `_normalized`가 키 집합 변화를 `ValueError`로 막지만, **막힌다는 것은 스크립트가 그 섹션을 skip한다는 뜻**이지 알아서 고쳐 준다는 뜻이 아니다.
2. **`hold`는 좌우 비대칭이다.** H3는 **레포** 값을 보고, H1·H2는 로컬 쪽 사실을 본다. `(local, repo)` 순서가 뒤집히면 예외도 빈 결과도 나지 않고 판정이 **조용히 반대로 선다.** MCP는 `no_hold`뿐이라 446개가 이 실수를 잡지 못한다.
3. **두 축은 다른 연산이다.** `diff`·`merge`·`next_base`는 **value 축만** 본다. `action` 축은 `restore_plan` 전용이다. H3만 값 보류이면서 행동 보류가 아니다 — **설치는 한다.**

**`recognize`가 돌려주는 것이 이 어댑터에서는 매핑 하나가 아니다.** `plugins.json`은 세 섹션을 담으므로 `{섹션 이름: 매핑}`을 돌려주고, 코어 함수(`merge`·`diff`·`restore_plan`·`next_base`)는 **섹션 하나씩** 부른다. 코어는 이 dict의 내부를 들여다보지 않는다 — `None`인지만 본다.

**부재 섹션과 인식 실패는 다르다.** 인식된 문서에서 없는 섹션은 `{}`("이력이 비어 있었다"), 문서 자체를 인식하지 못하면 **세 섹션 모두 `None`**(신뢰할 수 없는 이력). 전자는 삭제 판정의 근거가 되지만 후자는 근거가 될 수 없다.

**섹션 단위 skip은 base·레포 **양쪽** pass-through다**(spec 7.5). 레포 쪽을 빠뜨리면 `status: "ok"`인 채로 타 기기 항목이 전멸한다 — 4.3의 "세 섹션 키를 항상 기록한다"를 문언대로만 읽으면 정확히 그 코드가 나온다.

---

## 변조 확인은 각 task의 필수 스텝이다

plan ①의 실행에서 Task 2~7 **매번** SURVIVE가 나왔고 대부분 plan이 실어 온 결함이었다. 핵심 불변식(`next_base`의 값 동의 검사)을 지워도 414개가 전부 통과했다. **성실한 구현일수록 plan의 결함을 그대로 재생산한다.**

각 task의 `Step 4b`에서 **그 task가 도입한 가드 절을 하나씩** 뒤집고 대응 테스트가 FAIL하는지 임시 복사본에서 확인한다. 원본 작업 트리를 오염시키지 말 것. 네 축이 템플릿이다:

| 축 | 이 plan에서의 형태 |
|---|---|
| **훅 호출 계약** | `hold(local, repo)` 인자 순서·정규화 여부, `recognize`를 세 함수가 공유하는지, `build_hooks`를 레포 읽기 **뒤에** 부르는지 |
| **축 분리** | `value` ↔ `action` 맞바꾸기, `merge`에 `action`을 흘리기, `restore_plan`에서 `value_held`를 판정표에 태우기 |
| **`{}` vs `None`** | 부재 섹션을 `None`으로, 인식 실패를 `{}`로, `base=None` degrade를 `{}`로 |
| **I/O 층** | `open` 모드(`"rb"`→`"r"`), `except FileNotFoundError`→`except OSError`, 파일 부재를 예외로/예외를 부재로, `os.replace` 제거 |

**SURVIVE하면 구현이 아니라 테스트를 보강한다.** 보강한 줄 옆에 어떤 변조를 잡는지 주석으로 남긴다.

**변조 하네스 자체가 거짓말을 할 수 있다.** Task 5 실행에서 실측됐다 — 두 변조가 **같은 크기의
파일을 같은 초에** 쓰면 `__pycache__`의 `.pyc`가 재사용되어(pyc 헤더는 mtime을 **초 단위**로
저장한다) 앞 변조의 코드가 그대로 돌고, 결과가 엉뚱한 테스트에 잡힌 것처럼 나온다.
**임시 복사본에서 변조를 돌릴 때는 `PYTHONDONTWRITEBYTECODE=1`을 주고 매회 `__pycache__`를
지운다.** 이 함정에 빠지면 CAUGHT/SURVIVED 판정이 통째로 무의미해진다.

---

### Task 1: 원자적 쓰기 — 잘린 백업 파일이 거짓 삭제로 가는 두 번째 문을 막는다

**근거:** spec 7.4의 정신 / plan ① 인계 표(Task 1 quality review I1)

`mcp_config.dump_backup`은 `open(path, "w")`로 **먼저 truncate한다.** 쓰기 도중 실패(ENOSPC/EIO)하면 레포 파일이 잘린 채 남고, 다음 백업의 `load_backup`이 그것을 구문 오류로 보아 `{}`로 degrade한다. 그러면 **모든 서버가 케이스 4로 판정**되어 restore가 *"다른 기기가 삭제했습니다"* 를 띄운다. plan ① Task 1이 막은 것과 **같은 거짓 문구로 가는 두 번째 문**이다. `sync_state.write_base`도 같은 형태다.

`plan_mcp.apply_base`는 `mc.dump_backup`을 부르므로 이 수정으로 함께 고쳐진다.

**두 어댑터가 각자 원자화하면 안 된다.** 그것이 이 프로젝트가 코어를 뽑은 이유다 — 다음 우회가 한쪽에만 반영된다. 직렬화 옵션(`sort_keys`·`indent`·`ensure_ascii`)도 이미 `ks.fingerprint`와 맞춰져 있어야 하는 자리다.

**Files:**
- Modify: `plugins/claude-sync/lib/keyed_sync.py` (`dump_json` 신규)
- Modify: `plugins/claude-sync/lib/mcp_config.py:228-234` (`dump_backup`)
- Modify: `plugins/claude-sync/lib/sync_state.py:47-58` (`write_base`)
- Test: `plugins/claude-sync/tests/test_keyed_sync.py`, `tests/test_mcp_config.py`, `tests/test_sync_state.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_keyed_sync.py` 끝에 추가한다. 이 파일은 이미 `import json`·`import os`·`import pytest`를 갖고 있다.

```python
def test_dump_json_leaves_old_file_intact_when_write_fails(tmp_path, monkeypatch):
    """쓰기 도중 실패해도 이전 내용이 온전해야 한다.

    open(path, "w")는 truncate가 먼저 일어난다. 잘린 파일은 다음 load_backup에서
    {}로 degrade하고, 그러면 모든 항목이 케이스 4로 판정되어 restore가
    "다른 기기가 삭제했습니다"라는 거짓 문구를 띄운다.
    """
    path = str(tmp_path / "x.json")
    ks.dump_json({"a": 1}, path)

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(ks.json, "dump", boom)
    with pytest.raises(OSError):
        ks.dump_json({"b": 2}, path)
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}


def test_dump_json_removes_its_temp_file_when_write_fails(tmp_path, monkeypatch):
    """실패가 남긴 .tmp를 지운다 — 레포 디렉토리에 남으면 `git add -A`가 커밋한다."""
    path = str(tmp_path / "x.json")

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(ks.json, "dump", boom)
    with pytest.raises(OSError):
        ks.dump_json({"b": 2}, path)
    assert os.listdir(str(tmp_path)) == []


def test_dump_json_writes_the_same_bytes_as_before(tmp_path):
    """직렬화 옵션은 바뀌지 않는다 — 지문 비교와 디스크 표현의 일치가 계약이다."""
    path = str(tmp_path / "x.json")
    ks.dump_json({"b": 1, "a": {"ko": "한글"}}, path)
    with open(path, encoding="utf-8") as f:
        assert f.read() == '{\n  "a": {\n    "ko": "한글"\n  },\n  "b": 1\n}\n'
```

`tests/test_mcp_config.py` 끝에 추가한다.

```python
def test_dump_backup_is_atomic(tmp_path, monkeypatch):
    """어댑터가 코어의 원자적 writer를 거쳐야 한다 — 두 벌이 되면 다음 수정이 한쪽만 간다."""
    path = str(tmp_path / mc.BACKUP_RELPATH)
    mc.dump_backup({"x": {"command": "a"}}, path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(mc.ks.json, "dump", boom)
    with pytest.raises(OSError):
        mc.dump_backup({"y": {"command": "b"}}, path)
    assert mc.load_backup(path) == {"x": {"command": "a"}}
    assert not os.path.exists(path + ".tmp")
```

`tests/test_sync_state.py` 끝에 추가한다.

```python
def test_write_base_leaves_old_blob_intact_when_write_fails(tmp_path, monkeypatch):
    """base 블롭도 같다 — 잘린 base는 parse_base가 None으로 읽어 합집합 degrade를 부른다."""
    base_dir = str(tmp_path / "base")
    ss.write_base("plugins.json", b'{"version": 2}', base_dir=base_dir)
    real_open = open

    def fail_on_tmp(path, *args, **kwargs):
        if str(path).endswith(".tmp"):
            raise OSError("disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fail_on_tmp)
    with pytest.raises(OSError):
        ss.write_base("plugins.json", b"truncated", base_dir=base_dir)
    monkeypatch.undo()
    assert ss.read_base("plugins.json", base_dir=base_dir) == b'{"version": 2}'


def test_write_base_removes_its_temp_file_when_the_write_itself_fails(tmp_path):
    """.tmp가 **만들어진 뒤에** 실패하는 경로를 잡는다.

    위 테스트의 fail_on_tmp는 open이 열리기 **전에** 터지므로 .tmp가 애초에 생기지
    않는다 — 그래서 "디렉토리에 .tmp가 없다"는 단정이 정리 코드 유무와 무관하게 참이고
    공허하다. bytes가 아닌 값을 넘기면 open은 성공하고 f.write가 TypeError를 낸다.
    OSError가 아닌 예외라서 `except Exception:`을 `except OSError:`로 좁히는 변조도
    함께 잡는다.
    """
    base_dir = str(tmp_path / "base")
    ss.write_base("plugins.json", b'{"version": 2}', base_dir=base_dir)
    with pytest.raises(TypeError):
        ss.write_base("plugins.json", "bytes가 아니다", base_dir=base_dir)
    assert ss.read_base("plugins.json", base_dir=base_dir) == b'{"version": 2}'
    assert os.listdir(base_dir) == ["plugins.json"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `cd /Users/bran/personal/claude-sync && uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py plugins/claude-sync/tests/test_mcp_config.py plugins/claude-sync/tests/test_sync_state.py -q`
기대: 새 테스트 다섯이 FAIL (`ks.dump_json` 없음 / 이전 내용이 잘림 / `.tmp` 잔존)

- [ ] **Step 3: 구현**

`lib/keyed_sync.py`의 `same()` 아래에 추가한다.

```python
def dump_json(payload, path):
    """키 정렬 JSON을 원자적으로 쓴다 — 같은 디렉토리의 .tmp에 쓰고 os.replace한다.

    직접 open(path, "w")하면 truncate가 먼저 일어나므로, 쓰기 도중 실패(ENOSPC/EIO)가
    **파일을 잘린 채로 남긴다.** 잘린 백업 파일은 다음 load_backup에서 구문 오류로 {}로
    degrade하고, 그러면 모든 항목이 케이스 4로 판정되어 restore가 "다른 기기가
    삭제했습니다"라는 거짓 문구를 띄운다. 이 프로젝트가 이미 한 번 고친 거짓 문구다.

    실패하면 임시 파일을 지운다 — 레포 디렉토리에 남으면 `git add -A`가 그것을 커밋한다.

    직렬화 옵션은 fingerprint()와 맞춰져 있다(sort_keys, ensure_ascii=False).
    두 어댑터가 각자 이 함수를 복사하면 다음 수정이 한쪽에만 반영된다.
    """
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
```

`keyed_sync.py` 상단의 import에 `os`를 더한다 — 현재는 `copy`·`json`뿐이다.

```python
import copy
import json
import os
```

`lib/mcp_config.py`의 `dump_backup`을 교체한다.

```python
def dump_backup(servers, path):
    """v2 형식으로 저장한다. sort_keys로 git diff를 안정화한다.

    코어의 원자적 writer를 쓴다 — 쓰기 도중 실패가 레포 파일을 잘린 채로 남기면
    다음 백업이 그것을 "서버 0개"로 읽어 전부 케이스 4로 판정한다.
    """
    payload = {"version": SCHEMA_VERSION, "scope": "user", "servers": servers}
    ks.dump_json(payload, path)
```

`lib/sync_state.py`의 `write_base`를 교체한다.

```python
def write_base(relpath, data, base_dir=BASE_DIR):
    """base 블롭 기록(불변식 갱신). data가 None이면 삭제.

    .tmp에 쓰고 os.replace한다 — 잘린 base 블롭은 parse_base가 None으로 읽어
    합집합 degrade를 부르고, 그러면 삭제 전파가 조용히 죽는다.
    """
    path = base_blob_path(relpath, base_dir)
    if data is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 신규 5개 포함 **451 passed**. 개수는 참고값이고 게이트는 `0 failed`다

- [ ] **Step 4b: 변조 확인 (필수)**

임시 복사본에서 아래를 각각 적용하고 대응 테스트가 FAIL하는지 확인한다.

- `os.replace(tmp, path)`를 지우고 `open(path, "w")`로 직접 쓰기 → 원자성 테스트 셋이 잡아야 한다
- `except Exception:` 블록의 `os.remove(tmp)`를 지우기 → `.tmp` 잔존 테스트가 잡아야 한다
- `except Exception:`을 `except OSError:`로 좁히기 → `json.dump`가 `TypeError`를 내는 값(집합 등)에서 `.tmp`가 남는다. **테스트가 이것을 잡지 못하면 보강한다**(직렬화 불가능한 값으로 테스트 하나 추가)
- `sort_keys=True`를 지우기 / `ensure_ascii=False`를 지우기 → 바이트 동등 테스트가 잡아야 한다
- `mc.dump_backup`을 옛 `open(path, "w")` 구현으로 되돌리기 → 어댑터 원자성 테스트가 잡아야 한다
- **`sync_state.write_base`에도 같은 변조 셋을 각각 적용한다** — `os.replace` 제거 / `os.remove(tmp)` 제거 /
  `except Exception:`을 `except OSError:`로 좁히기. `write_base`는 `dump_json`을 쓰지 않고 같은 패턴을
  **복제**하므로, `dump_json`만 변조해서는 이 세 구멍이 드러나지 않는다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/lib/mcp_config.py \
        plugins/claude-sync/lib/sync_state.py plugins/claude-sync/tests/test_keyed_sync.py \
        plugins/claude-sync/tests/test_mcp_config.py plugins/claude-sync/tests/test_sync_state.py
git commit -m "fix(core): 백업 파일과 base 블롭을 원자적으로 쓴다"
```

---

### Task 2: `base_staging` 보고 배선과 낡은 근거 넷

**근거:** spec 7.4, 9.3.7 / plan ① 인계 표(quality review P1·M3·M4·M6, 최종 리뷰 m-1, 교차 패스)

`collect_mcp.py`가 `base_staging: "failed"`를 **반환만 하고 소비하는 곳이 없다.** spec 7.4는 "보고한다"고 썼다. 그리고 그 payload의 `reason` 키는 `SKILL.md:292`가 **skipped 경로의 필드**로 문서화한 이름이라 충돌한다 — `status: "ok"`인데 `reason`이 실린다.

함께 고치는 낡은 근거 셋:
- `SKILL.md:397`의 주석 *"collect_mcp.py가 status=ok일 때만 쓰므로, 파일 존재가 곧 'skip 아님'이다"* — 결론은 이제 참이지만 근거가 낡았다. 참인 이유는 **rename 계약**이다.
- `collect_mcp.collect`의 스테이징 위생 전제가 코드 밖에 있다 — `os.replace` 실패가 남기는 `.tmp`가 무해한 이유는 **호출부가 실행마다 스테이징 디렉토리를 비우기 때문**이다.
- `plan_mcp.apply_base`가 최종 이름으로 직접 쓰는 것은 **정당한 비대칭**이다(앞에 레포 쓰기가 없다). 근거가 없으면 다음 사람이 "일관성"을 이유로 `.tmp`를 적용하고, 그러면 rename 트리거가 영영 오지 않아 restore 경로의 base가 전혀 전진하지 않는다.
- `keyed_sync.restore_plan`은 `base=None`과 `{}`를 같게 다루는데(`if base else {}`) `merge`는 구별한다. 테스트가 그 동일성을 고정하지만 docstring은 침묵한다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py:26-67`
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md` (6단계 `"ok"` 분기, 10단계 주석)
- Modify: `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py:48-58` (docstring)
- Modify: `plugins/claude-sync/lib/keyed_sync.py` (`restore_plan` docstring)
- Test: `plugins/claude-sync/tests/test_mcp_scripts.py`, `tests/test_script_root.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_mcp_scripts.py` 끝에 추가한다.

```python
def test_collect_names_the_staging_failure_reason_apart_from_skipped(tmp_path, monkeypatch):
    """status=ok payload에 `reason`을 실으면 skipped 경로의 필드 이름과 충돌한다.

    SKILL.md:292가 `reason`을 "레포 파일은 손대지 않았다"의 사유로 문서화했다.
    같은 이름을 ok 경로에 쓰면 스킬이 두 상태를 한 이름으로 읽는다.
    """
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    real_replace = os.replace

    staged = os.path.join(str(tmp_path / "staging"), mc.BACKUP_RELPATH)

    def fail_on_staging(src, dst):
        # 정확 경로로 비교한다 — endswith로는 레포 파일 rename까지 가로챈다.
        # Task 1 이후 dump_backup도 내부적으로 os.replace를 쓰므로 basename이 겹친다.
        if str(dst) == staged:
            raise OSError("rename failed")
        return real_replace(src, dst)

    monkeypatch.setattr(collect_mcp.os, "replace", fail_on_staging)
    out = collect_mcp.collect(repo, str(tmp_path / "staging"),
                              claude_json_path=local, base_dir=base_dir)
    assert out["status"] == "ok"
    assert out["base_staging"] == "failed"
    assert "reason" not in out
    assert "다음 백업이 복구한다" in out["base_staging_reason"]
```

`tests/test_script_root.py` 끝에 추가한다.

```python
def test_backup_reports_staging_failure_to_the_user():
    """spec 7.4는 "보고한다"고 썼다. 반환만 하고 아무도 읽지 않으면 보고가 아니다."""
    sec = section("sync-backup", "6. mcp-servers.json 생성 (키 단위 3-way 병합)")
    assert "`base_staging`" in sec
    assert "`base_staging_reason`" in sec


def test_backup_base_gate_cites_the_rename_contract_not_the_old_reason():
    """게이트가 참인 근거는 rename 계약이다 — "status=ok일 때만 쓴다"가 아니다.

    옛 근거는 거짓이었다: 수집 스크립트가 스테이징을 레포보다 먼저 썼으므로
    레포 쓰기가 실패해도 파일이 남았다. 근거를 갱신하지 않으면 다음 사람이
    그 문장을 믿고 rename을 지운다.
    """
    text = read_skill("sync-backup")
    assert "status=ok일 때만 쓰므로" not in text
    assert "rename" in section("sync-backup", "10. 커밋 & 푸시")
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_scripts.py plugins/claude-sync/tests/test_script_root.py -q`
기대: 세 테스트 FAIL

- [ ] **Step 3: 구현**

`collect_mcp.py`의 docstring 끝(현재 `:34`)에 전제 한 줄을 더하고, 실패 payload의 키를 갈아 끼운다.

```python
    """merge 결과를 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    스테이징은 <rel>.tmp로 먼저 쓰고 **레포 쓰기가 성공한 뒤에** <rel>로 rename한다.
    스테이징 최종 파일의 존재가 곧 "레포까지 반영됨"을 뜻해야 하기 때문이다 —
    SKILL.md의 base 갱신 게이트가 그 파일의 존재만 보고 판단한다.
    먼저 최종 이름으로 쓰면 레포 쓰기가 실패해도 게이트가 통과해 base가 전진하고,
    다음 백업이 이 기기 자신의 서버를 케이스 4로 오독한다.

    **전제: 호출부가 실행마다 스테이징 디렉토리를 한 번 비운다**(SKILL.md의 rm -rf).
    os.replace가 실패하면 <rel>.tmp가 남는데, 그것이 무해한 이유가 이 전제다.
    spec 7.4의 배선이 스테이징 디렉토리를 플러그인 수집과 공유하므로 이 성질이
    유지되려면 rm -rf가 **수집 단계들보다 앞에서 딱 한 번** 실행되어야 한다.
    """
```

`out["reason"]` 대입 줄만 바꾼다.

```python
    try:
        os.replace(tmp, staged)
    except OSError as e:
        # 레포는 이미 갱신됐다. skipped로 접으면 "레포를 손대지 않았다"가 거짓이 된다.
        # 키 이름을 reason과 가른다 — reason은 skipped 경로의 필드다(SKILL.md:292).
        out["base_staging"] = "failed"
        out["base_staging_reason"] = (
            "레포는 갱신됐으나 base 스테이징에 실패했다: %s (다음 백업이 복구한다)" % e)
    return out
```

**11단계의 "기록을 건너뛰는 경우는 둘뿐이다"도 함께 고친다.** `base_staging` 실패가 세 번째
경우다. 단 **게이트는 두 축이다** — 뒤의 둘(skip·스테이징 실패)은 스테이징 최종 파일 부재가
막고, **푸시 실패는 `REPO_HAS_CONTENT=0`이 막는다**(그때 스테이징 파일은 이미 존재한다).
"세 경우 모두 파일이 없어서 막힌다"고 쓰면 거짓이고, 그 문장을 믿는 사람이
`REPO_HAS_CONTENT` 조건을 중복으로 보고 지운다.

`sync-backup/SKILL.md`의 6단계 `"ok"` 분기 표 아래(현행 `:305` *"충돌이 있어도 백업 전체를 막지 않는다"* 문단 앞)에 문단을 넣는다.

```markdown
`base_staging`이 `"failed"`이면 **레포는 갱신됐지만 base 스테이징이 실패한 것이다.** `base_staging_reason`을 그대로 보여준다. 이 실행에서는 base가 전진하지 않으므로 다음 백업이 같은 내용을 다시 계산해 복구한다. **`skipped`로 오해하지 않는다** — `skipped`의 표준 문구는 "레포 파일은 손대지 않았다"인데 이 경로에서는 그것이 거짓이다.
```

`sync-backup/SKILL.md` 10단계의 주석 두 줄을 교체한다.

```bash
# MCP base: 레포가 실제로 그 내용을 갖게 된 뒤에만 기록한다.
# 스테이징 최종 파일은 collect_mcp.py가 레포 쓰기에 성공한 뒤 rename으로 만든다.
# 따라서 파일 존재가 곧 "레포까지 반영됨"이다 — status 값을 다시 읽을 필요가 없다.
```

`plan_mcp.py`의 `apply_base` docstring에 마지막 문단을 더한다.

```python
    **이 함수는 .tmp+rename 규칙에서 제외된다.** 그 규칙은 "레포 쓰기가 성공한 뒤에
    rename"인데 apply-base에는 **레포 쓰기가 없다.** 그대로 적용하면 rename 트리거가
    영영 오지 않아 SKILL.md의 게이트가 언제나 거짓이 되고, restore 경로의 base가
    전혀 전진하지 않는다 — keep_stale/keep_local 선택이 전부 무효가 된다.
    여기서는 **파일 존재가 곧 "계산 성공"**이다(spec 9.3.7).
```

`keyed_sync.py`의 `restore_plan` docstring에 한 줄을 더한다.

```python
    **base가 None이든 {}이든 같게 다룬다**(`if base else {}`). merge는 둘을 구별하지만
    (None은 합집합 degrade, {}는 판정표) 복원 쪽은 `known`이 비면 **삭제 후보(local_stale,
    케이스 4·5)로 가는 경로 자체가 닫히고**(`name in known`이 항상 거짓) 7·8도 both_changed로
    뭉친다 — 두 입력이 같은 결과 버킷으로 수렴하므로 구별할 실익이 없다.
    (**"복원은 삭제를 하지 않는다"고 쓰지 말 것** — restore_plan의 local_stale이 정확히
    삭제 후보이고 restore가 그것을 사용자에게 묻는다. 근거가 틀리면 다음 사람이 `known`을
    레포로 채우는 변경을 안전하다고 오해하고, 그러면 이력 없는 기기가 전 항목을 local_stale로
    몰아 "다른 기기가 삭제했습니다"라는 거짓 문구를 띄운다.)
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: **453 passed**

- [ ] **Step 4b: 변조 확인 (필수)**

- `out["base_staging_reason"]`을 `out["reason"]`으로 되돌리기 → 개명 테스트가 잡아야 한다
- `out["base_staging"] = "failed"` 대입을 지우기 → 같은 테스트가 잡아야 한다
- `except OSError`를 `except FileNotFoundError`로 좁히기 → rename 실패가 그대로 전파되어 **전체가 skipped로 접힌다.** 테스트가 잡지 못하면 보강한다
- SKILL.md의 새 문단·주석을 지우기 → `test_script_root.py`의 두 테스트가 잡아야 한다
- docstring 문단들을 지우기 → **어떤 테스트도 잡지 못한다.** 이것은 알고 받아들이는 구멍이다. 문서 앵커를 테스트로 거는 것은 `SKILL.md`까지이고 lib docstring은 리뷰가 본다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills plugins/claude-sync/lib/keyed_sync.py plugins/claude-sync/tests
git commit -m "fix(backup): base 스테이징 실패를 사용자에게 보고하고 낡은 근거 넷을 고친다"
```

---

### Task 3: 테스트 위생 — root 판별력과 `recognize` 공유 가드 파라미터화

**근거:** plan ① 인계 표(Task 3 quality r2 N-1, 최종 리뷰 m-3)

**(a) `chmod(0)` 기반 권한 테스트가 root에서 판별력을 잃는다.** root는 권한 비트를 무시하므로 정상 구현에서도 `DID NOT RAISE`로 **거짓 실패**한다 — 조용히 통과하는 것이 아니라 상시 빨간 테스트가 되고, 누군가 skip 처리하면 그 시점부터 보호가 사라진다. 네 자리가 이 관행을 쓴다.

**(b) `recognize` 공유 가드가 `mc`에 하드코딩돼 있다.** 바로 위의 `hold` 소비 함수 가드는 소스를 훑어 자동 확장되는데 이쪽은 아니다. 손으로 복제해야 하고, **잊으면 "이력은 못 믿는데 레포는 믿는" 비대칭이 무증상으로 들어온다.** 어댑터 목록을 파라미터화하고, **그 목록이 완전한지를 소스 스캔으로 강제한다** — Task 4가 `plugin_config.py`를 만드는 순간 이 가드가 FAIL해야 한다.

**Files:**
- Create: `plugins/claude-sync/tests/marks.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py:98`, `tests/test_downgrade.py:137`, `tests/test_compat.py:134,153`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py:694-715`

- [ ] **Step 1: 실패하는 test 작성**

`tests/marks.py`를 만든다. 테스트 파일이 아니므로 pytest가 수집하지 않는다.

```python
"""테스트 환경 때문에 판별력을 잃는 단정에 붙이는 마커."""
import os

import pytest

# chmod(0)로 읽기를 막는 테스트는 root에서 무의미하다 — root는 권한 비트를 무시하므로
# 정상 구현에서도 예외가 나지 않아 **거짓 실패**한다. 조용히 통과하는 것이 아니라 상시
# 빨간 테스트가 되고, 누군가 skip 처리하면 그 시점부터 보호가 사라진다.
# 현재 root로 도는 CI 설정은 없다. 이 마커는 그런 환경이 생겼을 때를 위한 것이다.
requires_permission_bits = pytest.mark.skipif(
    hasattr(os, "getuid") and os.getuid() == 0,
    reason="root는 권한 비트를 무시한다 — chmod(0) 단정이 거짓 실패한다",
)
```

`tests/test_keyed_sync.py`의 `test_mcp_adapter_passes_one_recognize_hook_to_all_three`를 아래로 **교체**한다.

```python
# recognize를 코어 세 함수에 넘기는 어댑터 전수. (모듈, 인식되는 최소 문서) 쌍이다.
# 손으로 복제하는 대신 파라미터화한다 — 복제를 잊으면 그 어댑터의 비대칭이 무증상으로
# 들어오고, 그 비대칭이 상위 버전 백업을 파괴한다(spec 4.4).
RECOGNIZE_ADAPTERS = [
    (mc, b'{"version": 2, "scope": "user", "servers": {}}'),
]


@pytest.mark.parametrize("adapter,sample", RECOGNIZE_ADAPTERS,
                         ids=lambda x: x.__name__ if hasattr(x, "__name__") else "")
def test_adapter_passes_one_recognize_hook_to_all_three(adapter, sample, tmp_path, monkeypatch):
    """어댑터가 세 함수에 같은 recognize를 넘겨야 한다.

    코어는 훅을 파라미터로 받으므로 공유를 강제할 수 없다. 갈리면 "이력은 못 믿는데
    레포는 믿는" 비대칭이 생기고 상위 버전 백업이 파괴된다(spec 4.4).
    """
    seen = []

    def capture(*args):
        seen.append(args[-1])   # 세 코어 함수 모두 recognize가 마지막 위치 인자다
        return {}

    monkeypatch.setattr(adapter.ks, "parse_base", capture)
    monkeypatch.setattr(adapter.ks, "load_backup", capture)
    monkeypatch.setattr(adapter.ks, "parse_backup", capture)

    adapter.parse_base(sample)
    adapter.load_backup(str(tmp_path / "none.json"))
    adapter.parse_backup(sample)

    assert len(seen) == 3
    assert len({id(hook) for hook in seen}) == 1


def test_recognize_adapter_list_covers_every_keyed_sync_importer():
    """lib/에서 코어를 import하는 모듈은 전부 위 목록에 있어야 한다.

    목록을 손으로 관리하면 새 어댑터가 붙을 때 조용히 빠진다 — 그것이 이 가드가
    mc에 하드코딩돼 있던 동안의 상태였다. 소스를 훑어 강제한다.
    """
    found = set()
    for name in sorted(os.listdir(LIB_DIR)):
        if not name.endswith(".py") or name == "keyed_sync.py":
            continue
        with open(os.path.join(LIB_DIR, name), encoding="utf-8") as f:
            if re.search(r"^import keyed_sync\b", f.read(), re.M):
                found.add(name[:-3])
    assert found == {module.__name__ for module, _ in RECOGNIZE_ADAPTERS}
```

권한 테스트 네 자리에 마커를 붙인다. 각 파일 상단에 `from marks import requires_permission_bits`를 더하고 데코레이터를 얹는다.

```python
@requires_permission_bits
def test_load_backup_propagates_permission_error(tmp_path):
```

`tests/test_downgrade.py:137`·`tests/test_compat.py:134,153`도 같은 형태로 붙인다. **함수 이름은 바꾸지 않는다.**

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_keyed_sync.py -q`
기대: `test_recognize_adapter_list_covers_every_keyed_sync_importer`는 PASS(아직 `plugin_config.py`가 없다), 파라미터화된 가드는 `[mcp_config-...]` 하나로 PASS. **이 task는 리팩터링이므로 빨강에서 시작하지 않는다** — 대신 Step 4b가 판별력을 확인한다.

- [ ] **Step 3: 구현**

Step 1의 편집이 곧 구현이다. `tests/test_keyed_sync.py` 상단에 `re`가 이미 import돼 있는지 확인하고 없으면 더한다(`HOLD_CONSUMER`가 쓰므로 이미 있다). `LIB_DIR` 상수도 이미 있다.

- [ ] **Step 4: 전체 회귀 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: **454 passed** (신규 완전성 가드 1개)

- [ ] **Step 4b: 변조 확인 (필수)**

- 임시 복사본에 빈 `lib/plugin_config.py`를 만들고 `import keyed_sync as ks` 한 줄만 넣기 → **완전성 가드가 FAIL해야 한다.** 이것이 Task 4에서 실제로 일어날 일이다. FAIL하지 않으면 정규식이 잘못됐다

> **실행 중 확정:** Task 1의 I1 수정으로 `lib/sync_state.py`가 `ks.dump_bytes`를 쓰게 되면서
> **어댑터가 아닌 모듈이 이 스캔에 걸린다.** 위 코드를 문언대로 쓰면 즉시 FAIL한다.
> 해법은 `NON_ADAPTER_KEYED_SYNC_IMPORTERS = {"sync_state"}`를 두되 **그 목록이 거짓이
> 되는 순간 잡히도록** 하는 것이다 — 목록의 모듈이 `ks.parse_base|load_backup|parse_backup`을
> 호출하기 시작하면 같은 테스트가 FAIL한다. "import 기준 스캔 + 자기검증 예외 목록"이
> "호출 기준 스캔"보다 이른 시점에 걸리므로 이쪽을 택했다(빈 스텁도 분류를 강제한다).
- `RECOGNIZE_ADAPTERS`에서 `mc`를 빼기 → 완전성 가드가 FAIL해야 한다
- `mc.parse_backup`이 다른 훅(`lambda obj: obj`)을 쓰도록 바꾸기 → 파라미터화된 가드가 FAIL해야 한다
- root가 아닌 환경에서 `requires_permission_bits`의 조건을 `True`로 바꾸기 → 네 테스트가 skip으로 표시되는지 확인한다(마커가 실제로 붙었는지 검증)

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests
git commit -m "test: recognize 공유 가드를 어댑터 전수로 넓히고 권한 테스트를 root에서 skip한다"
```

---

### Task 4: `lib/plugin_config.py` — 읽기 계층과 인식 규칙

**근거:** spec 3.1·3.2·3.3·3.4, 4.1·4.3·4.4, 6.4(파일 읽기 부분), 5.4

로컬은 **두 파일**에서 읽되 역할이 다르다. `settings.json`은 값의 유일한 원천, `installed_plugins.json`은 `auto` 플래그 하나만. 셋째 파일 `plugins-held.json`은 기기별 보류 선택이다.

**세 파일 모두 "없음"과 "깨짐"을 구별한다.** 그 구별이 무너지면 각각 다른 방식으로 데이터를 잃는다 — `{"enabledPlugins": null}`인 기기가 "플러그인 0개"로 읽히면 base에 있던 항목 전부가 케이스 3으로 판정되어 레포에서 전멸하고, `auto` 판정 불가를 통과로 접으면 되돌릴 수 없는 수동 승격이 타 기기에서 일어난다.

**Files:**
- Create: `plugins/claude-sync/lib/plugin_config.py`
- Create: `plugins/claude-sync/tests/test_plugin_config.py`
- Modify: `plugins/claude-sync/tests/test_keyed_sync.py` (`RECOGNIZE_ADAPTERS`에 등록)

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_config.py`를 만든다.

```python
"""플러그인 어댑터 단위 테스트 (spec 3·4·6·7·8장).

실제 ~/.claude는 절대 건드리지 않는다 — 모든 읽기 함수가 경로 인자를 받는다.
"""
import json
import os

import pytest

import keyed_sync as ks
import plugin_config as pc
from marks import requires_permission_bits


def write_settings(tmp_path, data, name="settings.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def write_installed(tmp_path, plugins):
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2, "plugins": plugins}), encoding="utf-8")
    return str(path)


def write_held(tmp_path, data):
    path = tmp_path / "plugins-held.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(path)


GH = {"source": {"source": "github", "repo": "june20516/suberpower"}}


# --- 3.2 로컬 읽기 ---

def test_read_local_returns_three_sections_with_empty_defaults(tmp_path):
    """키가 없으면 {} — 0개는 정상 상태다."""
    local = pc.read_local_sections(write_settings(tmp_path, {}))
    assert local == {"enabledPlugins": {}, "extraKnownMarketplaces": {}, "pluginConfigs": {}}


def test_read_local_rejects_null_section(tmp_path):
    """{"enabledPlugins": null}을 "0개"로 읽으면 base의 항목 전부가 케이스 3이 된다."""
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(write_settings(tmp_path, {"enabledPlugins": None}))


def test_read_local_rejects_non_object_sections(tmp_path):
    for bad in ([], "x", 3, True):
        with pytest.raises(pc.LocalConfigUnavailable):
            pc.read_local_sections(write_settings(tmp_path, {"pluginConfigs": bad}))


def test_read_local_rejects_missing_and_broken_file(tmp_path):
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(str(tmp_path / "none.json"))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(str(broken))
    top = tmp_path / "top.json"
    top.write_text("[]", encoding="utf-8")
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(str(top))


@requires_permission_bits
def test_read_local_propagates_permission_error(tmp_path):
    """권한 오류를 LocalConfigUnavailable로 감싸면 "설정 0개"로 접힌다 — 전파한다."""
    path = write_settings(tmp_path, {})
    os.chmod(path, 0)
    try:
        with pytest.raises(PermissionError):
            pc.read_local_sections(path)
    finally:
        os.chmod(path, 0o600)


# --- 3.3 별칭 키 ---

def test_read_local_reads_the_alias_key(tmp_path):
    """additionalMarketplaces만 있는 기기의 마켓플레이스를 놓치면 안 된다."""
    local = pc.read_local_sections(write_settings(tmp_path, {"additionalMarketplaces": {"m": GH}}))
    assert local["extraKnownMarketplaces"] == {"m": GH}


def test_read_local_ignores_the_alias_when_both_exist(tmp_path):
    """CLI와 같은 규칙 — 둘 다 있으면 별칭을 무시한다."""
    local = pc.read_local_sections(write_settings(
        tmp_path, {"extraKnownMarketplaces": {"canonical": GH},
                   "additionalMarketplaces": {"alias": GH}}))
    assert local["extraKnownMarketplaces"] == {"canonical": GH}


def test_read_local_validates_only_the_adopted_alias(tmp_path):
    """채택하지 않은 쪽이 깨져 있어도 읽기는 성공한다 — 그 값을 쓰지 않기 때문이다."""
    local = pc.read_local_sections(write_settings(
        tmp_path, {"extraKnownMarketplaces": {"canonical": GH},
                   "additionalMarketplaces": "손상"}))
    assert local["extraKnownMarketplaces"] == {"canonical": GH}
    with pytest.raises(pc.LocalConfigUnavailable):
        pc.read_local_sections(write_settings(tmp_path, {"additionalMarketplaces": "손상"},
                                              name="only-alias.json"))


# --- 3.4 auto 집합 ---

def test_read_auto_ids_takes_user_scope_true_only(tmp_path):
    path = write_installed(tmp_path, {
        "dep@m": [{"scope": "user", "auto": True}],
        "manual@m": [{"scope": "user", "auto": False}],
        "other@m": [{"scope": "project", "auto": True}],
        "mixed@m": [{"scope": "project", "auto": False}, {"scope": "user", "auto": True}],
    })
    assert pc.read_auto_ids(path) == frozenset({"dep@m", "mixed@m"})


def test_read_auto_ids_rejects_missing_or_broken_file(tmp_path):
    """판정 불가를 빈 집합으로 접으면 auto 항목이 레포로 승격 전파된다 (N6)."""
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(tmp_path / "none.json"))
    broken = tmp_path / "installed_plugins.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(broken))


def test_read_auto_ids_rejects_unknown_shape(tmp_path):
    """plugins[<id>]는 배열이다 — 형태가 다르면 판정 불가다."""
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"plugins": {"x@m": {"scope": "user"}}}), encoding="utf-8")
    with pytest.raises(pc.AutoFlagsUnavailable):
        pc.read_auto_ids(str(path))


# --- 6.4 보류 상태 파일 ---

def test_read_held_state_treats_missing_file_as_empty(tmp_path):
    """파일 부재는 첫 실행의 정상 상태다 — 예외가 아니다."""
    assert pc.read_held_state(str(tmp_path / "none.json")) == pc.EMPTY_HELD


def test_read_held_state_rejects_broken_or_unknown_shape(tmp_path):
    for bad in ("{not json", {"pluginConfigs": []}, {"pluginConfigs": {"x@m": 3}},
                {"release": {"enabledPlugins": "x@m"}}, {"version": 3}):
        with pytest.raises(pc.HeldStateUnavailable):
            pc.read_held_state(write_held(tmp_path, bad))


def test_read_held_state_returns_both_axes(tmp_path):
    state = pc.read_held_state(write_held(tmp_path, {
        "version": 1, "pluginConfigs": {"delta@m": "abc"},
        "release": {"enabledPlugins": ["p@m"]}}))
    assert state == {"pluginConfigs": {"delta@m": "abc"},
                     "release": {"enabledPlugins": ["p@m"]}}


# --- 4.4 인식 규칙 ---

def recognized(obj):
    return pc.parse_backup(json.dumps(obj).encode("utf-8"))


def test_recognizes_v2_document_and_fills_absent_sections(tmp_path):
    """인식된 문서에서 없는 섹션은 {} — "이력이 비어 있었다"는 뜻이다."""
    out = recognized({"version": 2, "scope": "user", "enabledPlugins": {"p@m": True}})
    assert out == {"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": {},
                   "pluginConfigs": {}}


def test_recognizes_v1_document_without_version(tmp_path):
    """v1(두 필드만, version 없음)은 그대로 통과한다 — 마이그레이션 스크립트가 없다."""
    out = recognized({"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": {"m": GH}})
    assert out["pluginConfigs"] == {}
    assert out["enabledPlugins"] == {"p@m": True}


def test_does_not_recognize_document_without_any_known_section():
    """조건 3 — {"foo": 1}이나 {}를 "항목 0개"로 읽으면 그 문서를 덮어써 파괴한다."""
    assert recognized({}) == {}
    assert recognized({"foo": 1}) == {}
    assert pc.parse_base(json.dumps({"foo": 1}).encode("utf-8")) is None


def test_does_not_recognize_when_any_known_section_is_not_an_object():
    """조건 4 — 손상된 섹션이 "0개"로 읽혀 로컬 값으로 덮이는 것을 막는다."""
    assert pc.parse_base(json.dumps(
        {"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": "손상"}
    ).encode("utf-8")) is None


def test_does_not_recognize_higher_schema_version():
    """숫자로 상위 버전을 주장하면 알아보지 않는다. float 우회 포함."""
    for version in (3, 3.0, 2.5):
        assert pc.parse_base(json.dumps(
            {"version": version, "enabledPlugins": {}}).encode("utf-8")) is None


def test_recognizes_string_and_bool_version_claims():
    """문자열은 손으로 고친 문서를 막지 않기 위해, bool은 버전 주장이 아니라서 통과한다."""
    assert recognized({"version": "3", "enabledPlugins": {}}) is not None
    assert recognized({"version": True, "enabledPlugins": {}}) is not None


def test_load_backup_raises_on_unrecognized_document(tmp_path):
    path = tmp_path / pc.BACKUP_RELPATH
    path.write_text(json.dumps({"version": 3, "enabledPlugins": {}}), encoding="utf-8")
    with pytest.raises(pc.UnknownBackupSchema):
        pc.load_backup(str(path))


def test_load_backup_returns_empty_sections_when_file_missing(tmp_path):
    """레포에 파일이 없으면 세 섹션 모두 {} — 첫 백업의 정상 상태다."""
    assert pc.load_backup(str(tmp_path / "none.json")) == {
        "enabledPlugins": {}, "extraKnownMarketplaces": {}, "pluginConfigs": {}}


# --- 4.3 쓰기 규칙 ---

def test_dump_backup_always_writes_three_sections(tmp_path):
    """빈 섹션을 생략하면 다음 백업의 인식 규칙에 걸려 영구 skip된다 (4.3)."""
    path = str(tmp_path / pc.BACKUP_RELPATH)
    pc.dump_backup({"enabledPlugins": {"p@m": True}}, path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["version"] == 2 and raw["scope"] == "user"
    assert set(raw) == {"version", "scope", *pc.SECTIONS}
    assert raw["pluginConfigs"] == {}


def test_dump_backup_round_trips_through_load(tmp_path):
    path = str(tmp_path / pc.BACKUP_RELPATH)
    doc = {"enabledPlugins": {"p@m": ["1.0.0"]}, "extraKnownMarketplaces": {"m": GH},
           "pluginConfigs": {"p@m": {"options": {"k": "v"}}}}
    pc.dump_backup(doc, path)
    assert pc.load_backup(path) == doc
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_config.py -q`
기대: 전부 FAIL (`ModuleNotFoundError: No module named 'plugin_config'`)

- [ ] **Step 3: 구현**

`lib/plugin_config.py`를 만든다.

```python
#!/usr/bin/env python3
"""claude-sync의 플러그인 동기화 어댑터.

데이터 소스는 두 파일이고 역할이 다르다(spec 3장) —
  ~/.claude/settings.json                    세 섹션 값의 **유일한** 원천
  ~/.claude/plugins/installed_plugins.json   각 항목의 auto 플래그 **하나만**
installed_plugins.json을 값의 원천으로 삼지 않는 이유는 그것이 settings.json에서
파생되기 때문이다. `claude plugin list --json`을 쓰지 않는 이유는 "키 부재"와 false를
구별하지 못하기 때문이다.

키 단위 3-way 판정·인식은 값 무관 코어(keyed_sync)에 있다. 이 모듈은 플러그인의 도메인
지식만 얹는다 — 인식(4.4)·정규화(7.2)·보류(7.3)·복원 가능성(8장)·비밀 키(6.1).

**한 문서 안에 세 섹션이 있다.** load_backup·parse_base·parse_backup이 돌려주는 것은
매핑 하나가 아니라 {섹션 이름: 매핑}이고, 코어 함수는 **섹션 하나씩** 부른다.
"""
import copy
import hashlib
import json
import os

import keyed_sync as ks

SCHEMA_VERSION = 2
BACKUP_RELPATH = "plugins.json"
SENTINEL = "<REDACTED>"
SECTIONS = ("enabledPlugins", "extraKnownMarketplaces", "pluginConfigs")

# 별칭은 같은 뜻이다. 둘 다 있으면 앞의 것을 채택한다 — CLI와 같은 규칙이고,
# 순서가 곧 우선순위다. 이 튜플의 순서를 바꾸면 규칙이 뒤집힌다.
MARKETPLACE_ALIASES = ("extraKnownMarketplaces", "additionalMarketplaces")

DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")
DEFAULT_INSTALLED = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
DEFAULT_HELD = os.path.expanduser("~/.claude/.sync-state/plugins-held.json")

HELD_SCHEMA_VERSION = 1
EMPTY_HELD = {"pluginConfigs": {}, "release": {"enabledPlugins": []}}

# 코어의 예외를 그대로 re-export한다. 클래스가 두 벌이 되면 스크립트의 except 튜플이
# 갈라지고, 갱신을 잊으면 traceback으로 죽어 결함 C가 되살아난다.
LocalConfigUnavailable = ks.LocalConfigUnavailable
UnknownBackupSchema = ks.UnknownBackupSchema


class AutoFlagsUnavailable(Exception):
    """installed_plugins.json에서 auto 판정을 할 수 없다 (spec 3.4).

    **전체 skip이 아니라 두 섹션(enabledPlugins·pluginConfigs)만 skip하는 근거다.**
    extraKnownMarketplaces는 auto와 무관하므로 계속 진행한다.
    "전량 포함 + 경고"로 접으면 auto 항목이 레포에 실리고 base가 전진해, 타 기기의
    restore가 그것을 설치하며 **되돌릴 수 없는 수동 승격**을 일으킨다(N6).
    """


class HeldStateUnavailable(Exception):
    """plugins-held.json을 알아볼 수 없다 (spec 6.4).

    **파일 부재는 이 예외가 아니다** — 보류 없음이 첫 실행의 정상 상태다.
    이 예외는 pluginConfigs 한 섹션만 skip하는 근거다.
    """


# ---------------------------------------------------------------- 로컬 읽기 (3.2)

def _section_of(data, key):
    """settings.json의 한 섹션. 키가 없으면 {}, 있는데 객체가 아니면 읽기 실패다.

    이 구별이 없으면 {"enabledPlugins": null}인 기기에서 "0개"로 읽혀 base에 있던
    항목 전부가 케이스 3(삭제)으로 판정되고 레포에서 전멸한다.
    """
    if key not in data:
        return {}
    value = data[key]
    if not isinstance(value, dict):
        raise LocalConfigUnavailable("%s가 객체가 아님" % key)
    return dict(value)


def _marketplaces_of(data):
    """별칭 둘 중 **먼저 존재하는 쪽**만 읽고 검증한다 (3.3).

    둘 다 있으면 additionalMarketplaces를 무시한다 — CLI와 같은 규칙이다.
    채택하지 않은 쪽의 형태는 보지 않는다. 쓰지 않는 값이기 때문이다.
    """
    for key in MARKETPLACE_ALIASES:
        if key in data:
            return _section_of(data, key)
    return {}


def read_local_sections(settings_path=None):
    """settings.json에서 세 섹션을 읽는다. backup·status·restore가 **같은 정의**를 쓴다.

    스킬마다 다른 필터를 적용하면 같은 기기에서 backup↔restore를 교대할 때 base가 두
    정의 사이를 오간다(spec 3.1). auto 항목도 여기서는 빼지 않는다 — local에 그대로 두고
    hold 집합에 넣는다. 그래야 restore가 "이미 있다"로 보고 재설치하지 않는다(N6).
    PermissionError 등 그 외 OSError는 전파한다(감싸지 않는다).
    """
    path = DEFAULT_SETTINGS if settings_path is None else settings_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise LocalConfigUnavailable("%s 없음" % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LocalConfigUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise LocalConfigUnavailable("%s 최상위가 객체가 아님" % path)
    return {
        "enabledPlugins": _section_of(data, "enabledPlugins"),
        "extraKnownMarketplaces": _marketplaces_of(data),
        "pluginConfigs": _section_of(data, "pluginConfigs"),
    }


def read_auto_ids(installed_path=None):
    """의존성으로 자동 설치된 플러그인 id 집합 (3.4).

    plugins[<id>]는 **배열**이다 — 같은 플러그인이 스코프별로 여러 벌 설치될 수 있다.
    user 스코프 항목 중 auto가 True인 것이 하나라도 있으면 그 id는 auto다.

    이 집합은 hold 계산의 입력이다. **로컬에서 키를 지우는 데 쓰지 않는다.**
    읽지 못하면 AutoFlagsUnavailable — 판정 불가를 통과로 접지 않는다.
    """
    path = DEFAULT_INSTALLED if installed_path is None else installed_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise AutoFlagsUnavailable("%s 없음" % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AutoFlagsUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise AutoFlagsUnavailable("%s 최상위가 객체가 아님" % path)
    plugins = data.get("plugins", {})
    if not isinstance(plugins, dict):
        raise AutoFlagsUnavailable("plugins가 객체가 아님")
    out = set()
    for plugin_id, entries in plugins.items():
        if not isinstance(entries, list):
            raise AutoFlagsUnavailable("plugins[%s]가 배열이 아님" % plugin_id)
        if any(isinstance(e, dict) and e.get("scope") == "user" and e.get("auto") is True
               for e in entries):
            out.add(plugin_id)
    return frozenset(out)


def read_held_state(held_path=None):
    """이 기기의 보류 선택 (6.4·7.3). 파일이 없으면 보류 없음.

    {"pluginConfigs": {id: 지문}, "release": {"enabledPlugins": [id]}}

    **없음과 깨짐을 구별한다.** 부재는 첫 실행의 정상 상태이고, 깨짐은 pluginConfigs
    섹션을 skip할 사유다. 형태를 알아볼 수 없는데 빈 상태로 접으면 사용자의 보류 선택이
    조용히 사라지고 restore가 매번 다시 묻는다.

    이 파일의 **소유자는 plan_plugins.py apply-base 하나뿐이다.** 다른 스크립트는 읽기만 한다.
    """
    path = DEFAULT_HELD if held_path is None else held_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError:
        return copy.deepcopy(EMPTY_HELD)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HeldStateUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise HeldStateUnavailable("%s 최상위가 객체가 아님" % path)
    if ks.claims_newer_schema(data.get("version"), HELD_SCHEMA_VERSION):
        raise HeldStateUnavailable("%s가 상위 버전을 주장한다" % path)
    configs = data.get("pluginConfigs", {})
    if not isinstance(configs, dict) or not all(
            isinstance(v, str) for v in configs.values()):
        raise HeldStateUnavailable("pluginConfigs가 {id: 지문} 형태가 아님")
    release = data.get("release", {})
    if not isinstance(release, dict):
        raise HeldStateUnavailable("release가 객체가 아님")
    released = release.get("enabledPlugins", [])
    if not isinstance(released, list) or not all(isinstance(v, str) for v in released):
        raise HeldStateUnavailable("release.enabledPlugins가 문자열 배열이 아님")
    return {"pluginConfigs": dict(configs),
            "release": {"enabledPlugins": list(released)}}


# ---------------------------------------------------------------- 인식 계층 (4.4)

def _recognized_sections(obj):
    """알아볼 수 있는 백업 문서면 {섹션: 매핑}, 아니면 None.

    네 조건이 **전부** 참일 때만 인식한다(spec 4.4):
      1. 최상위가 객체다
      2. version이 없거나 SCHEMA_VERSION 이하다 (float 우회 포함, bool·문자열은 제외)
      3. 아는 섹션 중 **적어도 하나**가 존재한다
      4. 존재하는 **모든** 아는 섹션이 객체다

    조건 4가 없으면 {"enabledPlugins": {...}, "extraKnownMarketplaces": "손상"}이
    인식되어 손상된 섹션이 "0개"로 읽히고 로컬 값으로 덮인다 — 조건 3이 {"foo": 1}에
    대해 막는 것과 같은 사고가 섹션 단위로 열린다.

    **부재 섹션은 {}로 채운다**("이력이 비어 있었다"). 문서 자체를 인식하지 못하면
    None이고, 그때는 세 섹션 모두 신뢰할 수 없는 이력이다. 이 구별이 불변식 2의
    섹션 단위 판이다.

    이 판정이 parse_base·parse_backup·load_backup의 공통 기준이다 — 세 곳이 갈리면
    "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고, 그 비대칭이 상위 버전 백업을 파괴한다.
    """
    if not isinstance(obj, dict):
        return None
    if ks.claims_newer_schema(obj.get("version"), SCHEMA_VERSION):
        return None
    present = [name for name in SECTIONS if name in obj]
    if not present:
        return None
    if any(not isinstance(obj[name], dict) for name in present):
        return None
    return {name: dict(obj[name]) if name in obj else {} for name in SECTIONS}


def parse_backup(data):
    """JSON 바이트/문자열에서 섹션 dict를 읽는다(관대한 해석). 실패는 전부 {}.

    **레포 파일을 읽을 때는 이 함수가 아니라 load_backup을 쓴다** — 알아볼 수 없는
    문서를 "0개"로 읽으면 그 파일을 덮어써 파괴하기 때문이다.
    """
    return ks.parse_backup(data, _recognized_sections)


def parse_base(data):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None (합집합 degrade)."""
    return ks.parse_base(data, _recognized_sections)


def load_backup(path):
    """레포의 plugins.json을 안전하게 읽는다. 파일이 없으면 세 섹션 모두 {}.

    구문이 깨진 파일은 {}로 degrade하고, 구문은 유효한데 형식을 알아볼 수 없으면
    UnknownBackupSchema를 던진다. (PermissionError 등 그 외 OSError는 전파한다.)
    """
    loaded = ks.load_backup(path, _recognized_sections)
    return loaded if loaded else {name: {} for name in SECTIONS}


def dump_backup(sections, path):
    """v2 형식으로 저장한다. **세 섹션 키를 항상 기록한다**(4.3).

    빈 섹션을 생략하면 플러그인 0개인 기기의 백업 결과가 {"version":2,"scope":"user"}가
    되고, 다음 백업의 인식 규칙(조건 3)에 걸려 **영구 skip**된다. 파일을 지워도 같은
    모양이 다시 만들어져 탈출구가 통하지 않는다.

    "항상 기록한다"는 **"판정한 섹션이 비면 {}로 쓴다"**는 뜻이지 **"skipped 섹션을 {}로
    덮는다"**는 뜻이 아니다 — 후자는 타 기기 항목의 전량 소실이다(7.5). 호출부가 skipped
    섹션에 레포 원래 값을 넣어 이 함수에 넘긴다.
    """
    payload = {"version": SCHEMA_VERSION, "scope": "user"}
    for name in SECTIONS:
        payload[name] = sections.get(name, {})
    ks.dump_json(payload, path)
```

`ks.load_backup`은 파일이 없을 때 `{}`를 돌려주므로 `load_backup`이 그것을 세 섹션 dict로 펴 준다. **이 정규화가 없으면 호출부가 `repo["enabledPlugins"]`에서 `KeyError`를 낸다.**

`tests/test_keyed_sync.py`의 `RECOGNIZE_ADAPTERS`에 등록한다. 상단 import에 `import plugin_config as pc`를 더한다.

```python
RECOGNIZE_ADAPTERS = [
    (mc, b'{"version": 2, "scope": "user", "servers": {}}'),
    (pc, b'{"version": 2, "scope": "user", "enabledPlugins": {}}'),
]
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 신규 테스트 전부 PASS. **개수는 적지 않는다** — 리뷰 후속 커밋이 테스트를 더한다. 게이트는 `0 failed`다.

`test_recognize_adapter_list_covers_every_keyed_sync_importer`가 통과하는지 반드시 확인한다 — Task 3이 이 순간을 위해 만든 가드다.

- [ ] **Step 4b: 변조 확인 (필수)**

- `_recognized_sections`의 조건 4(`any(not isinstance(...))`)를 지우기 → 섹션 손상 테스트가 잡아야 한다
- 조건 3(`if not present: return None`)을 지우기 → `{}`·`{"foo": 1}` 테스트가 잡아야 한다
- 부재 섹션을 `{}` 대신 `None`으로 채우기 → 라운드트립·부재 섹션 테스트가 잡아야 한다
- `claims_newer_schema` 호출을 지우기 → 상위 버전 테스트가 잡아야 한다
- `_marketplaces_of`의 루프 순서를 뒤집기(별칭 우선) → "둘 다 있으면 무시" 테스트가 잡아야 한다
- `_section_of`의 `raise`를 `return {}`으로 바꾸기 → null 섹션 테스트가 잡아야 한다
- **I/O 층:** `open(path, "rb")`를 `"r"`로 / `except FileNotFoundError`를 `except OSError`로 / `read_held_state`의 `FileNotFoundError` 갈래를 `raise`로 바꾸기 → 부재/깨짐 구별 테스트가 잡아야 한다. **`read_auto_ids`의 부재 갈래를 `return frozenset()`으로 바꾸는 변조를 반드시 포함한다** — 이것이 N6 승격 전파의 입구다
- `dump_backup`에서 `payload[name] = sections.get(name, {})` 루프를 `payload.update(sections)`로 바꾸기 → 세 섹션 항상 기록 테스트가 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/plugin_config.py plugins/claude-sync/tests
git commit -m "feat(plugins): 어댑터의 읽기 계층과 인식 규칙"
```

---

### Task 5: `plugin_config` — 섹션별 정규화, 비밀 키, 보류 네 종류

**근거:** spec 6.1·6.2·6.4, 7.2, 7.3, 5.3

**정규화는 값 층위 변환만 한다.** 세 섹션이 서로 다른 정규화를 쓴다 — `enabledPlugins`는 항등(값을 좁히지 않는다), `extraKnownMarketplaces`는 `autoUpdate` **필드 제거**(키 제거가 아니다), `pluginConfigs`는 마스킹.

**보류는 두 축·네 종류다.** H3만 행동 보류가 아니다 — **이 기기는 그 플러그인을 설치해야 한다.** 설치하지 않으면 어느 기기에도 설치되지 않고, 모두가 값 보류라 아무도 push하지 않아 레포 값이 영원히 고정되며, 삭제 판정에서도 빠져 **설치도 삭제도 안 되는 항목**이 된다.

**`hold`는 레포를 읽은 뒤에만 만들 수 있다.** H3는 *"레포 값이 불리언이 아님"*, H4는 *"지문이 현재 레포 값과 일치"* 다. 순서를 뒤집으면 둘 다 **항상 빈 집합**이 되어 버전 제약이 `true`로 덮이고 6.4의 탈출구가 무증상으로 죽는다.

**Files:**
- Modify: `plugins/claude-sync/lib/plugin_config.py` (추가)
- Modify: `plugins/claude-sync/tests/test_plugin_config.py` (추가)

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_config.py` 끝에 추가한다.

```python
# --- 7.2 섹션별 정규화 ---

def test_enabled_plugins_normalize_is_identity_on_all_three_value_types():
    """값을 좁히지 않는다 — bool로 좁히면 확장 포맷을 파괴한다 (G5)."""
    norm = pc.SECTION_NORMALIZE["enabledPlugins"]
    values = {"a@m": True, "b@m": ["1.0.0"], "c@m": {"version": "1.0.0"}}
    assert norm(values) == values


def test_marketplace_normalize_drops_auto_update_field_only():
    """autoUpdate는 marketplace add로 설정할 수 없어 수렴시킬 CLI 수단이 없다 (7.2).

    필드 제거이지 키 제거가 아니다 — 값 층위에서 안전하다.
    """
    norm = pc.SECTION_NORMALIZE["extraKnownMarketplaces"]
    out = norm({"m": {"source": {"source": "github", "repo": "a/b"}, "autoUpdate": True}})
    assert out == {"m": {"source": {"source": "github", "repo": "a/b"}}}


def test_plugin_configs_normalize_masks_values_and_keeps_key_names():
    """키 이름을 보존해야 레포 파일만 보고 "어떤 값을 물어야 하는지"를 안다 (6.1)."""
    norm = pc.SECTION_NORMALIZE["pluginConfigs"]
    out = norm({"p@m": {"options": {"apiKey": "sk-real", "region": "kr"}, "other": 1}})
    assert out == {"p@m": {"options": {"apiKey": pc.SENTINEL, "region": pc.SENTINEL},
                           "other": 1}}


def test_plugin_configs_normalize_replaces_non_object_options_wholesale():
    """options가 객체가 아니면 필드 전체를 문자열 SENTINEL로 바꾼다 (6.1)."""
    norm = pc.SECTION_NORMALIZE["pluginConfigs"]
    assert norm({"p@m": {"options": ["secret"]}}) == {"p@m": {"options": pc.SENTINEL}}


@pytest.mark.parametrize("section", pc.SECTIONS)
def test_every_normalize_is_idempotent_and_key_preserving(section):
    """멱등하지 않으면 로컬(원본)과 레포(정규화됨)가 수렴하지 않는다.

    코어는 키 보존만 집행하고 멱등성은 집행하지 않는다(spec 5.2) — 어댑터의 책임이다.
    """
    norm = pc.SECTION_NORMALIZE[section]
    sample = {"a@m": True, "b@m": {"source": {"source": "directory", "path": "/x"},
                                   "autoUpdate": True},
              "c@m": {"options": {"k": "v"}}}
    once = norm(sample)
    assert set(once) == set(sample)
    assert once == norm(once)


def test_normalize_does_not_mutate_its_input():
    """입력을 바꾸면 원본 로컬 설정이 오염되고 비밀 평문이 사라진다."""
    original = {"p@m": {"options": {"apiKey": "sk-real"}}}
    pc.SECTION_NORMALIZE["pluginConfigs"](original)
    assert original == {"p@m": {"options": {"apiKey": "sk-real"}}}


# --- 6.1·6.2 비밀 키 ---

def test_secret_keys_lists_option_names_for_plugin_configs():
    assert pc.SECTION_SECRET_KEYS["pluginConfigs"](
        {"options": {"region": "x", "apiKey": "y"}}) == ["apiKey", "region"]


def test_secret_keys_is_empty_when_there_is_nothing_to_ask():
    """options가 비었거나 없으면 물어볼 것이 없다 — add 버킷으로 간다 (6.2)."""
    ask = pc.SECTION_SECRET_KEYS["pluginConfigs"]
    assert ask({"options": {}}) == [] and ask({}) == [] and ask("x") == []


@pytest.mark.parametrize("section", ("enabledPlugins", "extraKnownMarketplaces"))
def test_secret_keys_is_always_empty_for_the_other_two_sections(section):
    """다른 섹션에 비밀이 있다고 말하면 정상 항목이 needs_secret으로 새어 나간다."""
    assert pc.SECTION_SECRET_KEYS[section]({"options": {"k": "v"}}) == []


# --- 7.3 보류 ---

def hooks_for(local, repo, auto_ids=frozenset(), held=None):
    return pc.build_hooks(local, repo, auto_ids=auto_ids,
                          held_state=held or pc.EMPTY_HELD)


def hold_of(section, local, repo, **kw):
    """코어가 부르는 방식 그대로 — 정규화된 입력을 넘긴다."""
    norm = pc.SECTION_NORMALIZE[section]
    hooks = hooks_for({section: local}, {section: repo}, **kw)
    return hooks[section]["hold"](norm(local), norm(repo))


def test_h1_holds_auto_dependency_on_both_axes():
    """의존성 플러그인은 값도 행동도 보류다 — 명시적 install이 auto 표식을 영구 소실시킨다."""
    held = hold_of("enabledPlugins", {"dep@m": True}, {}, auto_ids=frozenset({"dep@m"}))
    assert held["value"] == {"dep@m"} and held["action"] == {"dep@m"}


def test_h1_also_holds_the_plugin_configs_entry():
    held = hold_of("pluginConfigs", {"dep@m": {"options": {}}}, {},
                   auto_ids=frozenset({"dep@m"}))
    assert held["value"] == {"dep@m"} and held["action"] == {"dep@m"}


def test_h2_holds_directory_marketplace_and_its_plugins_in_all_three_sections():
    """마켓플레이스만 빼면 소속 플러그인이 기기 B에서 해소 불가 상태가 된다 (7.3)."""
    local = {"enabledPlugins": {"p@mylocal": True, "q@gh": True},
             "extraKnownMarketplaces": {"mylocal": {"source": {"source": "directory",
                                                               "path": "/x"}},
                                        "gh": GH},
             "pluginConfigs": {"p@mylocal": {"options": {}}}}
    hooks = hooks_for(local, {name: {} for name in pc.SECTIONS})
    for section, expected in (("enabledPlugins", {"p@mylocal"}),
                              ("extraKnownMarketplaces", {"mylocal"}),
                              ("pluginConfigs", {"p@mylocal"})):
        norm = pc.SECTION_NORMALIZE[section]
        held = hooks[section]["hold"](norm(local[section]), norm({}))
        assert held["value"] == expected and held["action"] == expected


def test_h2_sees_directory_source_on_the_repo_side_too():
    """이미 레포에 실린 옛 directory 항목도 보류한다 — 등록할 소스가 이 기기에 없다."""
    repo = {"extraKnownMarketplaces": {"theirs": {"source": {"source": "directory",
                                                             "path": "/x"}}},
            "enabledPlugins": {"p@theirs": True}, "pluginConfigs": {}}
    hooks = hooks_for({name: {} for name in pc.SECTIONS}, repo)
    norm = pc.SECTION_NORMALIZE["enabledPlugins"]
    assert hooks["enabledPlugins"]["hold"](norm({}), norm(repo["enabledPlugins"])) == {
        "value": {"p@theirs"}, "action": {"p@theirs"}}


def test_h3_holds_value_only_and_judges_by_the_repo_side():
    """H3는 값만 보류한다 — 설치는 한다. 그리고 **레포** 값을 본다 (7.3)."""
    held = hold_of("enabledPlugins", {"p@m": True}, {"p@m": ["1.0.0"]})
    assert held["value"] == {"p@m"}
    assert held["action"] == set()


def test_h3_covers_objects_as_well_as_arrays():
    """1차 개정은 객체만 잡았다. 새 기기에는 키가 없으므로 install이 true를 쓴다 (0.1)."""
    assert hold_of("enabledPlugins", {}, {"p@m": {"version": "1.0.0"}})["value"] == {"p@m"}


def test_h3_does_not_hold_when_only_the_local_side_is_extended():
    """레포 기준이라 새 값의 등록을 막지 않는다 — 로컬 배열은 정상 push된다."""
    assert hold_of("enabledPlugins", {"p@m": ["1.0.0"]}, {})["value"] == set()


def test_h3_is_lifted_by_the_release_marker():
    """7.3의 탈출구 — release에 있는 키는 H3 값 보류에서 뺀다."""
    held = hold_of("enabledPlugins", {"p@m": True}, {"p@m": ["1.0.0"]},
                   held={"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}})
    assert held["value"] == set()


def test_h4_holds_only_when_the_fingerprint_matches_the_masked_repo_value():
    """지문 대상은 **레포 값(마스킹 후)**이다. 로컬 값이나 입력값을 넣으면 영영 매치되지
    않아 탈출구가 무증상으로 죽는다 (6.4)."""
    repo = {"delta@m": {"options": {"apiKey": "x"}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo)
    good = {"pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
            "release": {"enabledPlugins": []}}
    assert hold_of("pluginConfigs", {}, repo, held=good)["value"] == {"delta@m"}
    stale = {"pluginConfigs": {"delta@m": "0" * 64}, "release": {"enabledPlugins": []}}
    assert hold_of("pluginConfigs", {}, repo, held=stale)["value"] == set()


def test_h4_holds_both_axes():
    repo = {"delta@m": {"options": {"apiKey": "x"}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo)
    held = hold_of("pluginConfigs", {}, repo, held={
        "pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
        "release": {"enabledPlugins": []}})
    assert held["action"] == {"delta@m"}


def test_value_fingerprint_is_a_sha256_of_the_canonical_serialization():
    """코어와 같은 정규 직렬화를 써야 디스크 표현과 지문이 어긋나지 않는다."""
    import hashlib
    value = {"options": {"b": 1, "a": 2}}
    assert pc.value_fingerprint(value) == hashlib.sha256(
        ks.fingerprint(value).encode("utf-8")).hexdigest()


def test_build_hooks_gives_the_core_exactly_the_two_hook_contract():
    """코어가 보는 계약은 hold(local, repo)와 normalize(mapping) 둘뿐이다.

    자기 섹션 밖의 입력(auto_ids·다른 섹션의 출처·보류 파일)은 어댑터가 클로저로 닫는다.
    """
    hooks = hooks_for({name: {} for name in pc.SECTIONS},
                      {name: {} for name in pc.SECTIONS})
    for section in pc.SECTIONS:
        assert set(hooks[section]) >= {"normalize", "hold"}
        assert hooks[section]["hold"]({}, {}) == {"value": set(), "action": set()}


# --- 보류 종류 보고 ---

def test_held_kinds_splits_by_reason_and_covers_every_key():
    """사용자에게는 종류별 문구로 보고한다 — 한 키가 여러 종류에 걸릴 수 있다."""
    repo = {"ext@m": ["1.0.0"], "dep@m": True}
    kinds = pc.held_kinds("enabledPlugins", ["ext@m", "dep@m"],
                          auto_ids=frozenset({"dep@m"}), directory_names=frozenset(),
                          held_configs={}, repo_norm=repo)
    assert kinds == {"auto": ["dep@m"], "local_marketplace": [], "extended_value": ["ext@m"]}


def test_held_kinds_uses_the_section_specific_key_set():
    """섹션마다 나올 수 있는 종류가 다르다. 화이트리스트를 기계로 고정한다."""
    assert set(pc.held_kinds("extraKnownMarketplaces", [], auto_ids=frozenset(),
                             directory_names=frozenset(), held_configs={},
                             repo_norm={})) == {"local_marketplace"}
    assert set(pc.held_kinds("pluginConfigs", [], auto_ids=frozenset(),
                             directory_names=frozenset(), held_configs={},
                             repo_norm={})) == {"auto", "local_marketplace", "declined"}


def test_held_kinds_refuses_to_drop_an_unclassified_key():
    """분류되지 않은 보류 키를 조용히 빠뜨리면 사용자 보고에서 통째로 사라진다.

    불변식 6 — 조용한 fail-open 금지. 스크립트의 except 튜플이 ValueError를 잡아
    그 섹션을 skipped로 접고 사유를 보여준다.
    """
    with pytest.raises(ValueError):
        pc.held_kinds("enabledPlugins", ["ghost@m"], auto_ids=frozenset(),
                      directory_names=frozenset(), held_configs={}, repo_norm={})
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_config.py -q`
기대: 신규 테스트가 전부 FAIL (`AttributeError: module 'plugin_config' has no attribute ...`)

- [ ] **Step 3: 구현**

`lib/plugin_config.py`의 인식 계층 아래에 추가한다.

```python
# ------------------------------------------------------- 정규화·비밀 키 (6.1, 7.2)

def _identity(mapping):
    """enabledPlugins의 정규화 — 값을 좁히지 않는다.

    값 스키마는 union([array, boolean, object])이고 버전 제약 표현이 실재한다.
    bool로 좁히면 데이터를 파괴한다(G5). deepcopy로 돌려주는 것은 호출부가 결과를
    다듬어도 원본 설정이 오염되지 않게 하기 위해서다.
    """
    return copy.deepcopy(dict(mapping))


def _drop_auto_update(marketplaces):
    """extraKnownMarketplaces의 정규화 — autoUpdate 필드를 제거한다 (7.2).

    값에는 실재하지만 `marketplace add`에 이를 설정하는 옵션이 없다(실측). 비교에 넣으면
    한 기기가 켜고 다른 기기가 껐을 때 **수렴시킬 CLI 수단이 없어** 영구 보고된다.
    **필드 제거이지 키 제거가 아니므로** 값 층위에서 안전하다 — 코어의 _normalized 가드를
    통과한다.
    """
    out = {}
    for name, value in marketplaces.items():
        if not isinstance(value, dict):
            out[name] = copy.deepcopy(value)
            continue
        new = copy.deepcopy(value)
        new.pop("autoUpdate", None)
        out[name] = new
    return out


def _redact_configs(configs):
    """pluginConfigs의 정규화 — options의 **값만** 마스킹하고 키 이름은 보존한다 (6.1).

    키 이름을 보존해야 복원 시 레포 파일만 보고 "어떤 값을 물어야 하는지"를 알 수 있다.
    options가 객체가 아니면 필드 전체를 문자열 SENTINEL로 바꾼다 — 타입이 dict에서
    str로 바뀌므로 secret_keys는 그 항목에 대해 키를 하나도 묻지 않는다.
    이미 마스킹된 입력에 다시 적용해도 결과가 같다(멱등) — 로컬(평문)과 레포(마스킹됨)를
    수렴시키는 전제다.
    """
    out = {}
    for plugin_id, cfg in configs.items():
        if not isinstance(cfg, dict):
            out[plugin_id] = copy.deepcopy(cfg)
            continue
        new = copy.deepcopy(cfg)
        if "options" in new:
            options = new["options"]
            new["options"] = ({k: SENTINEL for k in options}
                              if isinstance(options, dict) else SENTINEL)
        out[plugin_id] = new
    return out


SECTION_NORMALIZE = {
    "enabledPlugins": _identity,
    "extraKnownMarketplaces": _drop_auto_update,
    "pluginConfigs": _redact_configs,
}


def _config_secret_keys(cfg):
    """복원 시 사용자에게 값을 물어야 하는 option 키 이름 목록 (6.1·6.2).

    비어 있으면 물어볼 것이 없다 — add 버킷으로 간다.
    """
    if not isinstance(cfg, dict):
        return []
    options = cfg.get("options")
    return sorted(options) if isinstance(options, dict) else []


def _no_secrets(value):
    """enabledPlugins·extraKnownMarketplaces에는 되물을 비밀이 없다.

    여기서 비어 있지 않은 목록을 돌려주면 정상 항목이 needs_secret 버킷으로 새어 나가
    설치되지 않는다.
    """
    return []


SECTION_SECRET_KEYS = {
    "enabledPlugins": _no_secrets,
    "extraKnownMarketplaces": _no_secrets,
    "pluginConfigs": _config_secret_keys,
}


# ------------------------------------------------------------------ 보류 (7.3)

def value_fingerprint(value):
    """정규화된 레포 값의 sha256 지문. plugins-held.json에 저장되는 형태다 (6.4).

    코어와 **같은 정규 직렬화**(ks.fingerprint)를 쓴다 — 여기서 옵션을 다시 적으면
    디스크 표현과 지문이 어긋난다.
    """
    return hashlib.sha256(ks.fingerprint(value).encode("utf-8")).hexdigest()


def marketplace_of(plugin_id):
    """'<plugin>@<marketplace>'의 마켓플레이스 부분. 그 형태가 아니면 None."""
    if not isinstance(plugin_id, str) or plugin_id.count("@") != 1:
        return None
    name, _, marketplace = plugin_id.partition("@")
    return marketplace if name and marketplace else None


def _source_kind(value):
    """마켓플레이스 값의 source.source. 알아볼 수 없으면 None."""
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    if not isinstance(source, dict):
        return None
    kind = source.get("source")
    return kind if isinstance(kind, str) else None


def directory_marketplaces(local_marketplaces, repo_marketplaces):
    """로컬 디렉토리에서 등록한 마켓플레이스 이름 집합 (H2).

    **양쪽을 다 본다.** 로컬 쪽은 생산 측 방어(기기 A가 애초에 올리지 않는다)이고,
    레포 쪽은 이미 실린 옛 항목의 소비 측 방어다(기기 B에는 등록할 소스가 없다).
    """
    names = set()
    for mapping in (local_marketplaces, repo_marketplaces):
        for name, value in mapping.items():
            if _source_kind(value) == "directory":
                names.add(name)
    return frozenset(names)


def _make_hold(section, *, auto_ids, directory_names, held_configs, released):
    """섹션 하나의 hold 훅을 만든다. 코어가 (local, repo)로 부른다.

    **좌우 비대칭이다** — H3·H4는 레포 값을 보고, H1·H2는 로컬 쪽 사실(auto 플래그,
    마켓플레이스 출처)을 본다. 인자 순서가 뒤집히면 예외도 빈 결과도 나지 않고
    판정이 조용히 반대로 선다.

    **입력은 이미 정규화돼 있다** — H4의 지문이 마스킹된 레포 값으로 계산되는 근거다.
    """
    def hold(local, repo):
        value, action = set(), set()
        for key in set(local) | set(repo):
            if section != "extraKnownMarketplaces" and key in auto_ids:      # H1
                value.add(key)
                action.add(key)
            owner = key if section == "extraKnownMarketplaces" else marketplace_of(key)
            if owner is not None and owner in directory_names:               # H2
                value.add(key)
                action.add(key)
            if (section == "enabledPlugins" and key in repo                  # H3
                    and not isinstance(repo[key], bool) and key not in released):
                value.add(key)                    # 행동 보류가 아니다 — 설치한다
            if (section == "pluginConfigs" and key in repo                   # H4
                    and held_configs.get(key) == value_fingerprint(repo[key])):
                value.add(key)
                action.add(key)
        return {"value": value, "action": action}
    return hold


HELD_KINDS = {
    "enabledPlugins": ("auto", "local_marketplace", "extended_value"),
    "extraKnownMarketplaces": ("local_marketplace",),
    "pluginConfigs": ("auto", "local_marketplace", "declined"),
}


def held_kinds(section, keys, *, auto_ids, directory_names, held_configs, repo_norm):
    """보류 키를 종류별로 가른다. status·backup이 종류별 문구로 보고하기 위해서다.

    한 키가 여러 종류에 걸칠 수 있으므로 첫 종류에서 멈추지 않는다.
    **어느 종류에도 걸리지 않는 키가 있으면 ValueError다** — 조용히 빠뜨리면 그 키가
    사용자 보고에서 통째로 사라진다(불변식 6). 스크립트가 그 섹션을 skipped로 접는다.
    """
    kinds = {name: [] for name in HELD_KINDS[section]}
    for key in sorted(keys):
        owner = key if section == "extraKnownMarketplaces" else marketplace_of(key)
        if "auto" in kinds and key in auto_ids:
            kinds["auto"].append(key)
        if owner is not None and owner in directory_names:
            kinds["local_marketplace"].append(key)
        if ("extended_value" in kinds and key in repo_norm
                and not isinstance(repo_norm[key], bool)):
            kinds["extended_value"].append(key)
        if ("declined" in kinds and key in repo_norm
                and held_configs.get(key) == value_fingerprint(repo_norm[key])):
            kinds["declined"].append(key)
    covered = {key for names in kinds.values() for key in names}
    missing = sorted(set(keys) - covered)
    if missing:
        raise ValueError("%s의 보류 사유를 분류할 수 없다: %s" % (section, missing))
    return kinds


def build_hooks(local, repo, *, auto_ids, held_state):
    """섹션별 훅 묶음 {섹션: {"normalize":..., "hold":...}}.

    **레포를 읽은 뒤에 불러야 한다**(spec 9.1.1의 4단계 > 2단계). H3는 "레포 값이
    불리언이 아님", H4는 "지문이 현재 레포 값과 일치"이므로 레포 없이는 둘 다 계산할 수
    없고, 순서를 뒤집으면 둘 다 항상 빈 집합이 되어 버전 제약이 true로 덮이고 6.4의
    탈출구가 무증상으로 죽는다.

    훅 넷은 섹션마다 다른 함수다 — 자기 섹션 밖의 입력(auto 집합, **다른 섹션**인
    extraKnownMarketplaces의 출처, 보류 파일)을 필요로 하기 때문이다. 코어가 보는
    계약은 hold(local, repo)와 normalize(mapping) 둘뿐이고 나머지는 여기서 닫는다.
    """
    directory_names = directory_marketplaces(
        local.get("extraKnownMarketplaces", {}), repo.get("extraKnownMarketplaces", {}))
    held_configs = dict(held_state.get("pluginConfigs", {}))
    released = frozenset(held_state.get("release", {}).get("enabledPlugins", []))
    return {
        section: {
            "normalize": SECTION_NORMALIZE[section],
            "hold": _make_hold(section, auto_ids=auto_ids,
                               directory_names=directory_names,
                               held_configs=held_configs, released=released),
        }
        for section in SECTIONS
    }
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

**축 분리와 훅 호출 계약이 이 task의 중심이다.** MCP는 `no_hold`뿐이라 아래 변조를 446개가 하나도 잡지 못한다.

- H3의 `value.add(key)` 옆에 `action.add(key)`를 더하기 → **H3가 설치되지 않는다.** 전용 테스트가 잡아야 한다
- H1·H2·H4에서 `action.add(key)`를 지우기 → 두 축 테스트가 잡아야 한다
- H3의 `key in repo`를 `key in local`로, `repo[key]`를 `local[key]`로 바꾸기 → **좌우 반전.** "레포 기준" 테스트 둘이 잡아야 한다
- H4의 `value_fingerprint(repo[key])`를 `value_fingerprint(local[key])`로 바꾸기 → 지문 대상 테스트가 잡아야 한다
- H3의 `not isinstance(repo[key], bool)`을 `isinstance(repo[key], dict)`로 좁히기(배열 누락) → 배열 테스트가 잡아야 한다
- `released` 검사를 지우기 → 탈출구 테스트가 잡아야 한다
- `_drop_auto_update`가 `value.pop("autoUpdate")` 대신 그 **키를 dict에서 제거**하도록 바꾸기 → 코어의 `_normalized`가 `ValueError`를 던져야 한다. 던지지 않으면 코어 가드가 깨진 것이다
- `_redact_configs`가 options 키까지 지우도록 바꾸기 → 같은 가드
- `_identity`가 `{k: bool(v) for ...}`로 좁히기 → 세 값 타입 테스트가 잡아야 한다
- `build_hooks`의 `directory_marketplaces` 인자에서 `repo`를 빼기 → 레포 쪽 H2 테스트가 잡아야 한다
- `held_kinds`의 `raise ValueError`를 지우기 → 미분류 테스트가 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/plugin_config.py plugins/claude-sync/tests/test_plugin_config.py
git commit -m "feat(plugins): 섹션별 정규화와 보류 네 종류(두 축)"
```

---

### Task 6: `plugin_config` — 복원 가능성, 마켓플레이스 인자, 정합성 검사

**근거:** spec 8.1·8.2·8.3·8.6, 7.6, 10.2

**시도하면 반드시 실패하는 것만 거른다.** 실패할 수도 있는 것은 시도하고 실패를 수집한다(10장). 그래서 `restorable`이 거짓인 갈래는 넷뿐이다 — id 형태 위반, 의사 출처, **레포 어디에도 소스가 없는 마켓플레이스**, 인자를 만들 수 없는 출처.

**always-known 다섯과 예약 열여섯은 다른 것이다.** 다섯은 등록 대상에서 빼고(`claude-plugins-official`은 설치는 한다), 예약 이름은 **미리 거르지 않는다** — 정당한 소유자일 수 있으므로 시도하고 실패 갈래를 구별해 보고한다. 두 집합은 `claude-plugins-official` 하나에서 교차하고 **always-known 판정이 우선한다.**

**Files:**
- Modify: `plugins/claude-sync/lib/plugin_config.py` (추가, `build_hooks` 확장)
- Modify: `plugins/claude-sync/tests/test_plugin_config.py` (추가)

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_config.py` 끝에 추가한다.

```python
# --- 8.2·8.3 열거형 대조 (14.4) ---

def test_always_known_marketplaces_are_exactly_these_five():
    """상수 import만으로 대조하면 이름 하나가 빠져도 테스트와 코드가 함께 바뀌어 통과한다.

    개수 + 이름 전수를 리터럴로 적어 "목록이 줄어들면 실패"하게 만든다 (spec 14.4).
    """
    assert pc.ALWAYS_KNOWN == frozenset({
        "inline", "skills-dir", "synced", "builtin", "claude-plugins-official"})
    assert len(pc.ALWAYS_KNOWN) == 5


def test_pseudo_sources_are_the_four_that_cannot_be_registered():
    """claude-plugins-official만 always-known이면서 복원 가능하다 (8.1)."""
    assert pc.PSEUDO_SOURCES == frozenset({"inline", "skills-dir", "synced", "builtin"})
    assert "claude-plugins-official" not in pc.PSEUDO_SOURCES


def test_reserved_marketplace_names_are_exactly_these_sixteen():
    assert pc.RESERVED_MARKETPLACE_NAMES == frozenset({
        "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
        "anthropic-marketplace", "anthropic-plugins", "agent-skills",
        "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins",
        "claude-for-legal", "claude-for-financial-services",
        "financial-services-plugins", "first-party-plugins",
        "claude-community", "claude-plugins-community", "healthcare"})
    assert len(pc.RESERVED_MARKETPLACE_NAMES) == 16


# --- 8.6 마켓플레이스 인자 ---

def test_marketplace_arg_from_github_repo():
    assert pc.marketplace_arg(GH) == "june20516/suberpower"


def test_marketplace_arg_from_url_sources():
    for kind in ("url", "git"):
        assert pc.marketplace_arg(
            {"source": {"source": kind, "url": "https://x/y.git"}}) == "https://x/y.git"


def test_marketplace_arg_is_none_when_no_command_can_be_built():
    """"시도한다"가 실행 가능한 명령으로 번역되지 않으면 unrestorable이다 (8.6)."""
    for value in ({"source": {"source": "directory", "path": "/x"}},
                  {"source": {"source": "github"}},
                  {"source": {"source": "github", "repo": ""}},
                  {"source": {"source": "novel"}}, {"source": "x"}, "x", None):
        assert pc.marketplace_arg(value) is None


# --- 8.1 복원 가능성 ---

def restorable_for(section, repo):
    return pc.build_hooks({name: {} for name in pc.SECTIONS}, repo,
                          auto_ids=frozenset(), held_state=pc.EMPTY_HELD)[section]["restorable"]


def test_plugin_is_unrestorable_when_id_is_not_plugin_at_marketplace():
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {"m": GH}})
    assert ok("p@m", True) is True
    for bad in ("noat", "@m", "p@", "a@b@c", ""):
        assert ok(bad, True) is False


def test_plugin_is_unrestorable_under_pseudo_sources():
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {}})
    for name in sorted(pc.PSEUDO_SOURCES):
        assert ok("p@%s" % name, True) is False


def test_official_marketplace_plugin_is_restorable_without_registration():
    """내장이라 등록이 무의미할 뿐 설치는 된다 (8.1)."""
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {}})
    assert ok("p@claude-plugins-official", True) is True


def test_plugin_is_unrestorable_when_the_repo_has_no_source_for_its_marketplace():
    """H2의 소비 측 안전망 — 등록할 소스가 레포 어디에도 없으면 시도해도 반드시 실패한다."""
    ok = restorable_for("enabledPlugins", {"extraKnownMarketplaces": {"known": GH}})
    assert ok("p@known", True) is True
    assert ok("p@unknown", True) is False


def test_plugin_configs_uses_the_same_rule_as_its_plugin():
    """설정을 채우는 명령이 `install --config`이므로 판정 기준이 같다."""
    ok = restorable_for("pluginConfigs", {"extraKnownMarketplaces": {"m": GH}})
    assert ok("p@m", {"options": {}}) is True
    assert ok("p@nowhere", {"options": {}}) is False


def test_marketplace_restorability_is_decided_by_the_argument():
    ok = restorable_for("extraKnownMarketplaces", {"extraKnownMarketplaces": {}})
    assert ok("m", GH) is True
    assert ok("m", {"source": {"source": "directory", "path": "/x"}}) is False


# --- 10.2 갈래별 사유 ---

def test_unrestorable_reason_distinguishes_the_four_branches():
    """"복원 불가"만 말하면 사용자가 무엇을 해야 하는지 알 수 없다 (10.2)."""
    repo = {"extraKnownMarketplaces": {"known": GH}}
    reason = lambda section, key, value: pc.unrestorable_reason(section, key, value, repo)
    assert "id 형태" in reason("enabledPlugins", "noat", True)
    assert "의사 출처" in reason("enabledPlugins", "p@inline", True)
    assert "소스가 없" in reason("enabledPlugins", "p@unknown", True)
    assert "인자" in reason("extraKnownMarketplaces", "m",
                            {"source": {"source": "directory", "path": "/x"}})


# --- 7.6 정합성 ---

def test_orphaned_reports_plugins_whose_marketplace_is_gone():
    """런타임은 조용히 건너뛰고 새 기기 restore는 "플러그인이 없다"로 실패한다 (7.6)."""
    assert pc.orphaned({"alpha@bar": True, "beta@known": True},
                       {"known": GH}) == ["alpha@bar"]


def test_orphaned_accepts_always_known_marketplaces():
    """내장 마켓플레이스는 extraKnownMarketplaces에 없는 것이 정상이다 (4.1·8.2)."""
    assert pc.orphaned({"p@claude-plugins-official": True}, {}) == []


def test_orphaned_reports_malformed_ids_too():
    """마켓플레이스 부분이 없는 id는 어떤 마켓플레이스에도 속하지 않는다."""
    assert pc.orphaned({"noat": True}, {}) == ["noat"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_config.py -q`
기대: 신규 테스트 FAIL

- [ ] **Step 3: 구현**

`lib/plugin_config.py`의 보류 절 아래에 추가하고, `build_hooks`를 확장한다.

```python
# ------------------------------------------------- 복원 가능성 (8장)·정합성 (7.6)

# 마켓플레이스 등록 대상에서 빼는 다섯. claude-plugins-official은 이미 자동 설치되어
# 등록이 무의미하고, 나머지 넷은 마켓플레이스가 아닌 **의사 출처**라 등록이 실패한다.
ALWAYS_KNOWN = frozenset({
    "inline", "skills-dir", "synced", "builtin", "claude-plugins-official"})

# 그 넷. 소속 플러그인은 복원할 수 없다 — claude-plugins-official만 설치가 가능하다.
PSEUDO_SOURCES = ALWAYS_KNOWN - {"claude-plugins-official"}

# 제3자가 쓸 수 없는 예약 이름. **미리 거르지 않는다** — 정당한 소유자일 수 있으므로
# 시도하고, 실패하면 "예약된 이름이라 거부되었다"로 갈래를 구별해 보고한다(8.3·10.2).
# always-known 판정이 우선한다 — claude-plugins-official은 등록 대상에서 먼저 빠지므로
# 이 갈래에 도달하지 않는다.
RESERVED_MARKETPLACE_NAMES = frozenset({
    "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official",
    "anthropic-marketplace", "anthropic-plugins", "agent-skills",
    "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins",
    "claude-for-legal", "claude-for-financial-services",
    "financial-services-plugins", "first-party-plugins",
    "claude-community", "claude-plugins-community", "healthcare",
})

# 출처 종류별로 `marketplace add`에 넘길 문자열을 어느 필드에서 뽑는가 (8.6).
# github은 실측된 형태다. url·git의 필드 이름은 측정되지 않았으므로 후보를 순서대로
# 훑고, 문자열을 하나도 찾지 못하면 **인자를 만들 수 없음 = unrestorable**로 접는다 —
# 짐작해서 잘못된 인자를 넘기면 CLI가 모호한 문구로 실패해 사용자가 원인을 못 찾는다.
_SOURCE_ARG_FIELDS = {"github": ("repo",), "url": ("url",), "git": ("url", "repo")}


def marketplace_arg(value):
    """`claude plugin marketplace add`에 넘길 문자열. 만들 수 없으면 None (8.6).

    directory 출처는 여기 오지 않는다 — H2로 보류되기 때문이다. 와도 None이 된다.
    """
    kind = _source_kind(value)
    source = value.get("source") if isinstance(value, dict) else None
    for field in _SOURCE_ARG_FIELDS.get(kind, ()):
        candidate = source.get(field)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _plugin_restorable(key, repo_marketplaces):
    """플러그인 id를 이 도구가 재현할 수 있는가 (8.1)."""
    marketplace = marketplace_of(key)
    if marketplace is None or marketplace in PSEUDO_SOURCES:
        return False
    return marketplace in ALWAYS_KNOWN or marketplace in repo_marketplaces


def unrestorable_reason(section, key, value, repo):
    """복원 불가의 **갈래**를 문장으로 (10.2). 복원 가능하면 None.

    "복원 불가"만 말하면 사용자가 무엇을 해야 하는지 알 수 없다 — 종류별 사유가
    "의사 출처라 원래 불가능하다"와 "레포에 소스가 없으니 백업한 기기에서 올려라"를 가른다.
    """
    if section == "extraKnownMarketplaces":
        if marketplace_arg(value) is None:
            return "등록 인자를 만들 수 없는 출처다 (%s)" % (_source_kind(value),)
        return None
    marketplace = marketplace_of(key)
    if marketplace is None:
        return "플러그인 id 형태(<plugin>@<marketplace>)가 아니다"
    if marketplace in PSEUDO_SOURCES:
        return "'%s'는 마켓플레이스가 아닌 의사 출처다" % marketplace
    if marketplace not in ALWAYS_KNOWN and marketplace not in repo.get(
            "extraKnownMarketplaces", {}):
        return "레포에 '%s' 마켓플레이스의 소스가 없다" % marketplace
    return None


def orphaned(merged_plugins, merged_marketplaces):
    """마켓플레이스가 결과 문서에 없는 플러그인 id (7.6). **차단하지 않는다.**

    런타임은 조용히 건너뛰고("Skipping orphaned enabledPlugins entry"), 새 기기의
    restore는 "플러그인이 없다"와 **똑같은 문구**로 실패해 원인을 알 수 없다.
    섹션 간에 게이트를 두지 않는 대신 이 검사로 보고만 한다.
    """
    known = set(merged_marketplaces) | ALWAYS_KNOWN
    return sorted(plugin_id for plugin_id in merged_plugins
                  if (marketplace_of(plugin_id) or "") not in known)
```

`build_hooks`의 반환 dict를 확장한다. `repo_marketplaces`를 클로저로 닫는 것이 8.1의 *"레포의 extraKnownMarketplaces"* 요구다.

```python
def build_hooks(local, repo, *, auto_ids, held_state):
    """... (기존 docstring 유지) ...

    restorable도 자기 섹션 밖을 본다 — 8.1의 판정이 **레포의** extraKnownMarketplaces를
    필요로 한다. 코어의 계약은 restorable(key, value) 둘뿐이므로 여기서 닫는다.
    """
    directory_names = directory_marketplaces(
        local.get("extraKnownMarketplaces", {}), repo.get("extraKnownMarketplaces", {}))
    held_configs = dict(held_state.get("pluginConfigs", {}))
    released = frozenset(held_state.get("release", {}).get("enabledPlugins", []))
    repo_marketplaces = frozenset(repo.get("extraKnownMarketplaces", {}))

    def restorable_for(section):
        if section == "extraKnownMarketplaces":
            return lambda key, value: marketplace_arg(value) is not None
        return lambda key, value: _plugin_restorable(key, repo_marketplaces)

    return {
        section: {
            "normalize": SECTION_NORMALIZE[section],
            "hold": _make_hold(section, auto_ids=auto_ids,
                               directory_names=directory_names,
                               held_configs=held_configs, released=released),
            "restorable": restorable_for(section),
            "secret_keys": SECTION_SECRET_KEYS[section],
        }
        for section in SECTIONS
    }
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `_plugin_restorable`에서 `marketplace in ALWAYS_KNOWN` 갈래를 지우기 → 공식 마켓플레이스 테스트가 잡아야 한다
- `PSEUDO_SOURCES` 검사를 `ALWAYS_KNOWN` 검사로 바꾸기 → **공식 마켓플레이스 플러그인이 복원 불가가 된다.** 두 테스트가 함께 잡아야 한다
- `marketplace in repo_marketplaces` 갈래를 `True`로 바꾸기 → H2 소비 측 테스트가 잡아야 한다
- `build_hooks`의 `repo_marketplaces`를 `local`에서 뽑도록 바꾸기 → 같은 테스트가 잡아야 한다(레포 기준이 계약이다)
- `marketplace_of`의 `count("@") != 1`을 `"@" not in`으로 완화 → **원문 그대로의 테스트로는 잡히지 않는다**(Task 6 실행에서 실측). `partition`이 첫 `@`로 자르므로 `a@b@c`의 마켓플레이스가 `b@c`가 되고, 그것도 레포에 없어 `restorable`이 그대로 `False`다 — 판정은 같고 **사유만 "소스가 없다"로 바뀐다.** 실제 피해는 사용자가 **존재한 적 없는 마켓플레이스를 백업하라는 안내**를 받는 것이므로, id 형태 테스트에 **사유가 "id 형태" 갈래인지** 보는 단정을 함께 걸어야 잡힌다
- `build_hooks`가 `secret_keys`를 섹션 무관하게 배선(`SECTION_SECRET_KEYS["enabledPlugins"]` 고정) → **조용한 fail-open이다.** `pluginConfigs`에 `_no_secrets`가 달리면 마스킹된 값이 `needs_secret`으로 가지 않고 `add` 버킷에 실려 **restore가 `<REDACTED>`를 진짜 옵션 값으로 설치한다.** 표를 직접 검사하는 테스트만으로는 배선이 끊겨도 잡히지 않으므로 `build_hooks`의 배선을 거는 단정이 따로 필요하다
- `marketplace_arg`가 빈 문자열을 통과시키도록 `and candidate`를 지우기 → 인자 생성 테스트가 잡아야 한다
- `orphaned`의 `| ALWAYS_KNOWN`을 지우기 → 내장 마켓플레이스 테스트가 잡아야 한다
- `ALWAYS_KNOWN`·`RESERVED_MARKETPLACE_NAMES`에서 이름을 하나씩 지우기 → 열거형 대조 테스트가 잡아야 한다(14.4가 요구하는 성질이다)

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/plugin_config.py plugins/claude-sync/tests/test_plugin_config.py
git commit -m "feat(plugins): 복원 가능성 판정과 마켓플레이스 인자, 정합성 검사"
```

---

### Task 7: `collect_plugins.py` — 백업 수집

**근거:** spec 9.1.1·9.1.2·9.1.3, 7.4, 7.5, 7.6, 4.3, 10.3

흐름의 **순서가 곧 안전 성질**이다. 4단계(hold 계산)가 2단계(레포 읽기)보다 뒤여야 H3·H4가 계산되고, 7단계(스테이징)가 8단계(레포)보다 먼저여야 하며, **그 둘에는 rename이 함께 필요하다.** 보고를 쓰기보다 **먼저** 만드는 것도 계약이다 — `held_kinds`가 `ValueError`를 던지면 그 섹션이 skipped로 접히는데, 레포를 이미 고친 뒤라면 *"레포 파일은 손대지 않았다"* 가 거짓이 된다.

**Files:**
- Create: `plugins/claude-sync/skills/sync-backup/scripts/collect_plugins.py`
- Create: `plugins/claude-sync/tests/test_plugin_scripts.py`
- Modify: `plugins/claude-sync/lib/plugin_config.py` (`read_hold_inputs`·`held_context` 추가)

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_scripts.py`를 만든다.

```python
"""세 스크립트(collect_plugins / compare_plugins / plan_plugins)의 계약 테스트.

실제 ~/.claude와 ~/.claude/.sync-state는 절대 건드리지 않는다 —
인프로세스 호출은 경로 인자로, CLI 호출은 env HOME= 으로 격리한다.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-status", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import plugin_config as pc  # noqa: E402
import collect_plugins  # noqa: E402

GH = {"source": {"source": "github", "repo": "june20516/suberpower"}}
DIR_SOURCE = {"source": {"source": "directory", "path": "/x"}}


def write_settings(tmp_path, **sections):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(sections), encoding="utf-8")
    return str(path)


def write_installed(tmp_path, plugins=None):
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2, "plugins": plugins or {}}), encoding="utf-8")
    return str(path)


def write_repo(tmp_path, sections=None):
    """레포 디렉토리. sections가 None이면 plugins.json이 없다."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if sections is not None:
        pc.dump_backup(sections, str(repo / pc.BACKUP_RELPATH))
    return str(repo)


def write_base_blob(tmp_path, sections=None):
    base_dir = tmp_path / "base"
    base_dir.mkdir(exist_ok=True)
    if sections is not None:
        pc.dump_backup(sections, str(base_dir / pc.BACKUP_RELPATH))
    return str(base_dir)


def repo_doc(repo):
    return pc.load_backup(os.path.join(repo, pc.BACKUP_RELPATH))


def staged_doc(staging):
    return pc.load_backup(os.path.join(staging, pc.BACKUP_RELPATH))


def collect(tmp_path, local=None, repo=None, base=None, installed=None, held=None):
    """기본값이 정상 경로다 — 각 테스트는 어긋나게 만들 것 하나만 지정한다."""
    return collect_plugins.collect(
        write_repo(tmp_path, repo),
        str(tmp_path / "staging"),
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path, base),
    )


def test_collect_writes_repo_and_staging_without_touching_base(tmp_path):
    out = collect(tmp_path, local={"enabledPlugins": {"p@m": True}})
    assert out["status"] == "ok"
    repo = write_repo(tmp_path)
    assert repo_doc(repo)["enabledPlugins"] == {"p@m": True}
    assert staged_doc(str(tmp_path / "staging"))["enabledPlugins"] == {"p@m": True}
    assert not os.path.exists(os.path.join(str(tmp_path / "base"), pc.BACKUP_RELPATH))


def test_collect_keeps_other_devices_entries(tmp_path):
    """결함 A — 한 기기의 백업이 다른 기기의 플러그인을 지우지 않는다 (G1)."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"mine@m": True}},
                  repo={"enabledPlugins": {"theirs@m": True}},
                  base={"enabledPlugins": {"mine@m": True}})
    assert out["sections"]["enabledPlugins"]["deleted"] == []
    assert sorted(repo_doc(write_repo(tmp_path))["enabledPlugins"]) == ["mine@m", "theirs@m"]


def test_collect_reports_value_change_not_just_key_set(tmp_path):
    """결함 B — true→false가 보고되어야 한다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"p@m": False}},
                  repo={"enabledPlugins": {"p@m": True}},
                  base={"enabledPlugins": {"p@m": True}})
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"p@m": False}


def test_collect_skips_everything_when_settings_is_unreadable(tmp_path):
    """결함 C — 종료 코드 0으로 계속하고, 레포·스테이징 둘 다 손대지 않는다."""
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    with pytest.raises(pc.LocalConfigUnavailable):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=str(tmp_path / "none.json"),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}
    assert not os.path.exists(os.path.join(str(tmp_path / "staging"), pc.BACKUP_RELPATH))


def test_collect_skips_everything_when_enabled_plugins_is_null(tmp_path):
    """14.1 — {"enabledPlugins": null}을 "0개"로 읽으면 레포에서 전멸한다."""
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"enabledPlugins": None}), encoding="utf-8")
    with pytest.raises(pc.LocalConfigUnavailable):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=str(settings),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}


def test_collect_skips_everything_when_the_repo_document_is_unrecognized(tmp_path):
    """14.1 — version: 3을 주장하는 문서를 만나면 레포 파일을 건드리지 않는다.

    "0개"로 읽어 덮어쓰면 상위 버전의 백업이 파괴된다. 조건 3(아는 섹션 없음)과
    조건 4(섹션이 객체가 아님)도 같은 갈래로 떨어진다.
    """
    repo = write_repo(tmp_path)
    repo_file = os.path.join(repo, pc.BACKUP_RELPATH)
    for raw in ('{"version": 3, "enabledPlugins": {}}',
                '{"foo": 1}',
                '{"enabledPlugins": {"p@m": true}, "extraKnownMarketplaces": "손상"}'):
        with open(repo_file, "w", encoding="utf-8") as f:
            f.write(raw)
        with pytest.raises(pc.UnknownBackupSchema):
            collect_plugins.collect(repo, str(tmp_path / "staging"),
                                    settings_path=write_settings(tmp_path),
                                    installed_path=write_installed(tmp_path),
                                    held_path=str(tmp_path / "none-held.json"),
                                    base_dir=write_base_blob(tmp_path))
        with open(repo_file, encoding="utf-8") as f:
            assert f.read() == raw
        assert not os.path.exists(os.path.join(str(tmp_path / "staging"),
                                               pc.BACKUP_RELPATH))


def test_collect_skips_two_sections_when_auto_flags_are_unavailable(tmp_path):
    """3.4 — 판정 불가를 통과로 접으면 되돌릴 수 없는 승격이 타 기기에서 일어난다.

    14.1: 레포가 그대로여야 한다. 마켓플레이스는 auto와 무관하므로 계속 진행한다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {"mine@m": True},
                         "extraKnownMarketplaces": {"m": GH}},
                  repo={"enabledPlugins": {"theirs@m": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["status"] == "ok"
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["extraKnownMarketplaces"]["status"] == "ok"
    doc = repo_doc(write_repo(tmp_path))
    assert doc["enabledPlugins"] == {"theirs@m": True}      # 레포 pass-through (7.5)
    assert doc["extraKnownMarketplaces"] == {"m": GH}


def test_skipped_section_passes_the_previous_base_through(tmp_path):
    """base 쪽 pass-through — 이전 base를 잃으면 다음 회차가 케이스 3을 낸다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"mine@m": True}},
                  base={"enabledPlugins": {"mine@m": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert staged_doc(str(tmp_path / "staging"))["enabledPlugins"] == {"mine@m": True}


def test_collect_skips_only_plugin_configs_when_held_file_is_broken(tmp_path):
    """6.4 — 없음은 정상이고 깨짐은 한 섹션만 skip이다."""
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    out = collect(tmp_path, local={"enabledPlugins": {"p@m": True}}, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["enabledPlugins"]["status"] == "ok"


def test_auto_plugin_is_neither_backed_up_nor_deleted(tmp_path):
    """14.1 — H1 위반 + C2형 삭제 전파를 함께 막는다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"dep@m": True, "mine@m": True}},
                  base={"enabledPlugins": {"dep@m": True, "mine@m": True}},
                  installed=write_installed(tmp_path, {"dep@m": [{"scope": "user",
                                                                  "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    assert section["deleted"] == []
    assert section["held"]["auto"] == ["dep@m"]
    assert sorted(repo_doc(write_repo(tmp_path))["enabledPlugins"]) == ["mine@m"]


def test_repo_extended_value_survives_when_local_lacks_the_key(tmp_path):
    """14.1의 첫 줄 — 출발점이 "로컬에 키가 없다"여야 복원 구간 파괴를 잡는다 (H3)."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {}},
                  repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"p@m": ["1.0.0"]}
    assert out["sections"]["enabledPlugins"]["held"]["extended_value"] == ["p@m"]


def test_extended_value_key_is_removed_from_next_base(tmp_path):
    """5.3 — 값 보류 키의 base를 남기면 해제되는 순간 케이스 3이 난다."""
    collect(tmp_path,
            local={"enabledPlugins": {"p@m": True}},
            repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
            base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in staged_doc(str(tmp_path / "staging"))["enabledPlugins"]


def test_plugin_config_secrets_never_reach_the_repo_file(tmp_path):
    """14.1 — 비밀 유출."""
    collect(tmp_path, local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}})
    with open(os.path.join(write_repo(tmp_path), pc.BACKUP_RELPATH), encoding="utf-8") as f:
        raw = f.read()
    assert "sk-real" not in raw
    assert pc.SENTINEL in raw


def test_absent_base_section_does_not_delete_anything(tmp_path):
    """14.1 — base에 pluginConfigs가 없으면 어떤 항목도 deleted로 판정되지 않는다.

    부재 섹션은 "이력이 비어 있었다"({})이므로 in_s가 거짓이고 케이스 3이 성립하지
    않는다. 레포에만 있는 항목은 케이스 2(타 기기 추가)로 보존된다.
    """
    out = collect(tmp_path,
                  local={"pluginConfigs": {}},
                  repo={"pluginConfigs": {"p@m": {"options": {"k": pc.SENTINEL}}}},
                  base={"enabledPlugins": {}})
    assert out["sections"]["pluginConfigs"]["deleted"] == []
    assert "p@m" in repo_doc(write_repo(tmp_path))["pluginConfigs"]


def test_second_backup_of_an_empty_device_is_not_skipped(tmp_path):
    """14.1 — 빈 섹션을 생략하면 다음 백업의 인식 규칙에 걸려 영구 skip된다 (4.3)."""
    first = collect(tmp_path, local={})
    assert first["status"] == "ok"
    repo = write_repo(tmp_path)
    second = collect_plugins.collect(
        repo, str(tmp_path / "staging2"),
        settings_path=write_settings(tmp_path),
        installed_path=write_installed(tmp_path),
        held_path=str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path))
    assert second["status"] == "ok"


def test_collect_reports_orphaned_without_blocking(tmp_path):
    """7.6 — 차단하지 않는다. 최상위 orphaned로 보고만 한다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"alpha@bar": True}},
                  repo={"extraKnownMarketplaces": {}})
    assert out["status"] == "ok"
    assert out["orphaned"] == ["alpha@bar"]


def test_collect_does_not_stage_when_repo_write_fails(tmp_path, monkeypatch):
    """레포 쓰기가 실패하면 스테이징 최종 파일이 남지 않아야 base가 전진하지 않는다."""
    repo = write_repo(tmp_path)
    real_dump = pc.dump_backup

    def fail_on_repo(sections, path):
        if os.path.dirname(path).endswith("repo"):
            raise OSError("disk full")
        return real_dump(sections, path)

    monkeypatch.setattr(collect_plugins.pc, "dump_backup", fail_on_repo)
    with pytest.raises(OSError):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=write_settings(tmp_path),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert not os.path.exists(os.path.join(str(tmp_path / "staging"), pc.BACKUP_RELPATH))


def test_collect_builds_the_report_before_touching_the_repo(tmp_path, monkeypatch):
    """보고 생성이 실패하면 레포가 이미 바뀐 뒤여서는 안 된다.

    held_kinds는 분류할 수 없는 보류 키에 ValueError를 던진다. 그 예외는 섹션을
    skipped로 접는데, 레포를 먼저 고쳤다면 "레포 파일은 손대지 않았다"가 거짓이 된다.
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})

    def boom(*args, **kwargs):
        raise ValueError("분류 불가")

    monkeypatch.setattr(collect_plugins.pc, "held_kinds", boom)
    with pytest.raises(ValueError):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=write_settings(tmp_path),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}


def test_collect_exits_zero_and_reports_skip_from_the_cli(tmp_path):
    """10.3 — 종료 코드는 0이다. 그래야 안내가 보인다."""
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills",
                          "sync-backup", "scripts", "collect_plugins.py")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    proc = subprocess.run([sys.executable, script, write_repo(tmp_path),
                           str(tmp_path / "staging")],
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["status"] == "skipped"
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_scripts.py -q`
기대: 전부 FAIL (`ModuleNotFoundError: No module named 'collect_plugins'`)

- [ ] **Step 3: 구현**

먼저 `lib/plugin_config.py`에 둘을 더한다. **세 스크립트가 공유해야 하는 것들이므로 스크립트 안에 두지 않는다** — 섹션 skip의 범위(9.1.2·9.3.6)가 스크립트마다 갈리면 backup은 두 섹션을 접는데 restore는 안 접는 상태가 생긴다.

```python
def read_hold_inputs(installed_path=None, held_path=None):
    """auto 집합과 보류 상태를 읽고, 실패에 대응하는 **섹션 skip 사유**를 함께 돌려준다.

    반환: (auto_ids, held_state, {섹션: 사유})

    두 실패는 범위가 다르다(spec 9.1.2·9.3.6):
      installed_plugins.json 판정 불가 → enabledPlugins·pluginConfigs 두 섹션
      plugins-held.json 깨짐          → pluginConfigs 한 섹션
    어느 쪽도 전체 skip이 아니다 — extraKnownMarketplaces는 auto와도 보류 파일과도
    무관하므로 계속 진행한다.

    실패한 쪽의 값은 "보류 없음"으로 채우지만 **그 섹션은 어차피 skip되므로 쓰이지
    않는다.** 채우는 이유는 나머지 섹션의 훅을 만들 수 있게 하기 위해서다.
    """
    skipped = {}
    try:
        auto_ids = read_auto_ids(installed_path)
    except AutoFlagsUnavailable as e:
        auto_ids = frozenset()
        skipped["enabledPlugins"] = str(e)
        skipped["pluginConfigs"] = str(e)
    try:
        held_state = read_held_state(held_path)
    except HeldStateUnavailable as e:
        held_state = copy.deepcopy(EMPTY_HELD)
        # setdefault다 — auto 실패 사유가 이미 있으면 그것이 더 넓은 원인이다.
        skipped.setdefault("pluginConfigs", str(e))
    return auto_ids, held_state, skipped


# **주: `held_context`는 Task 5가 이미 만들었다**(quality review I-1로 앞당겼다).
# 아래 정의는 참고용이고, 실제로 더할 것은 `read_hold_inputs` 하나다.
def held_context(local, repo, *, auto_ids, held_state):
    """hold 훅과 held_kinds가 **같은 입력에서 같은 값**을 보게 하는 컨텍스트.

    두 곳이 각자 계산하면 "보류로 판정했는데 보고에서는 종류를 못 찾는" 상태가 생기고,
    held_kinds가 그것을 ValueError로 막으므로 섹션이 통째로 skipped가 된다.
    """
    return {
        "auto_ids": auto_ids,
        "directory_names": directory_marketplaces(
            local.get("extraKnownMarketplaces", {}),
            repo.get("extraKnownMarketplaces", {})),
        "held_configs": dict(held_state.get("pluginConfigs", {})),
    }
```

`build_hooks`의 앞 세 줄을 교체한다(나머지는 그대로).

```python
    context = held_context(local, repo, auto_ids=auto_ids, held_state=held_state)
    released = frozenset(held_state.get("release", {}).get("enabledPlugins", []))
    repo_marketplaces = frozenset(repo.get("extraKnownMarketplaces", {}))
    ...
            "hold": _make_hold(section, released=released, **context),
```

`skills/sync-backup/scripts/collect_plugins.py`를 만든다.

```python
#!/usr/bin/env python3
"""로컬 플러그인 상태를 레포와 **섹션별** 키 단위 3-way 병합한다.

사용: collect_plugins.py <레포 경로> <스테이징 디렉토리>

`claude plugin list --json`을 호출하지 않고 stdin도 받지 않는다 — 데이터 소스는
settings.json(세 섹션의 값)과 installed_plugins.json(auto 플래그)뿐이다(spec 3장).

base는 이 스크립트가 쓰지 않는다. 커밋 전에 실행되기 때문이다. next_base를 스테이징
디렉토리에 plugins.json으로 써 두고, 레포가 실제로 그 내용을 갖게 된 뒤 SKILL.md가
update_base.py로 옮긴다. **레포를 source_root로 넘기면** base ← 레포 파일 바이트가 되어
타 기기가 추가·변경한 항목이 base에 실리고, 다음 백업이 그것을 "이 기기가 삭제했다"로
오독해 다른 기기의 플러그인을 경고 없이 지운다.

**전제: 호출부가 실행마다 스테이징 디렉토리를 한 번 비운다**(SKILL.md의 rm -rf).
collect_mcp.py와 같은 디렉토리를 공유하므로 그 rm -rf는 두 수집 단계보다 앞에서
딱 한 번 실행되어야 한다(spec 7.4).
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import keyed_sync as ks  # noqa: E402
import plugin_config as pc  # noqa: E402
import sync_state as ss  # noqa: E402


def collect(repo_path, staging_dir, settings_path=None, installed_path=None,
            held_path=None, base_dir=ss.BASE_DIR):
    """세 섹션을 병합해 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    순서가 곧 안전 성질이다(spec 9.1.1):
      1 로컬 읽기 → 2 레포 읽기 → 3 이력 읽기 → 4 **hold 계산** → 5 섹션별 merge
      → 6 정합성 → 보고 생성 → 7 스테이징(.tmp) → 8 레포 → rename

    4단계가 2단계보다 뒤인 것이 중요하다. **근거는 H3·H4가 아니다** — 그 둘은 코어가
    호출 시점에 넘기는 repo 인자를 읽으므로 훅을 만드는 시점의 레포와 무관하다(실측).
    빈 레포로 훅을 만들면 죽는 것은 H2의 **레포 쪽** 방어와 restorable·reason 셋이다 —
    전부 build 시점의 레포를 클로저로 닫기 때문이다.

    **보고를 쓰기보다 먼저 만든다.** held_kinds가 분류 불가에 ValueError를 던지는데,
    레포를 이미 고친 뒤라면 그 예외가 부르는 skipped의 표준 문구("레포 파일은 손대지
    않았다")가 거짓이 된다.

    스테이징은 <rel>.tmp로 쓰고 **레포 쓰기가 성공한 뒤에** rename한다 — 최종 파일의
    존재가 곧 "레포까지 반영됨"을 뜻해야 SKILL.md의 base 갱신 게이트가 참이 된다.
    """
    local = pc.read_local_sections(settings_path)
    repo_file = os.path.join(repo_path, pc.BACKUP_RELPATH)
    repo = pc.load_backup(repo_file)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))

    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    # 두 진입점을 따로 부르면 두 입력이 같다는 보장이 호출부의 규율뿐이고,
    # 어긋나면 held_kinds가 분류에 실패해 섹션이 통째로 skipped가 된다(Task 7 리뷰 I-4).
    hooks, context = pc.hooks_and_context(local, repo, auto_ids=auto_ids, held_state=held_state)

    previous_base = base or {}
    merged_doc, base_doc, sections = {}, {}, {}
    for section in pc.SECTIONS:
        if section in skipped:
            # 7.5 — base도 레포도 pass-through. 레포 쪽을 빠뜨리면 4.3을 문언대로 읽어
            # {}를 쓰게 되고, 타 기기의 항목이 status:"ok"인 채로 전량 소실된다.
            merged_doc[section] = repo[section]
            base_doc[section] = previous_base.get(section, {})
            sections[section] = pc.skipped_section(skipped[section])
            continue
        normalize = hooks[section]["normalize"]
        result = ks.merge(local[section], repo[section],
                          None if base is None else base.get(section, {}),
                          normalize=normalize, hold=hooks[section]["hold"])
        merged = result["merged"]
        merged_doc[section] = merged
        base_doc[section] = result["next_base"]
        sections[section] = {
            "status": "ok",
            # 케이스 9는 레포 값이 남고 케이스 5는 아예 빠진다 — 처방이 다르므로 가른다.
            "conflicts": {
                "repo_kept": [k for k in result["conflicts"] if k in merged],
                "repo_absent": [k for k in result["conflicts"] if k not in merged],
            },
            "deleted": result["deleted"],
            "local_stale": result["local_stale"],
            # 케이스 2(타 기기 추가)와 케이스 8(타 기기 변경)은 안내 문구가 다르다.
            "repo_ahead": {
                "present": [k for k in result["repo_ahead"] if k in local[section]],
                "absent": [k for k in result["repo_ahead"] if k not in local[section]],
            },
            "held": pc.held_kinds(section, result["held"],
                                  repo_norm=normalize(repo[section]), **context),
        }

    out = {
        "status": "ok",
        "orphaned": pc.orphaned(merged_doc["enabledPlugins"],
                                merged_doc["extraKnownMarketplaces"]),
        "sections": sections,
    }

    os.makedirs(staging_dir, exist_ok=True)
    staged = os.path.join(staging_dir, pc.BACKUP_RELPATH)
    tmp = staged + ".tmp"
    pc.dump_backup(base_doc, tmp)
    pc.dump_backup(merged_doc, repo_file)
    try:
        os.replace(tmp, staged)
    except OSError as e:
        # 레포는 이미 갱신됐다. skipped로 접으면 "레포를 손대지 않았다"가 거짓이 된다.
        out["base_staging"] = "failed"
        out["base_staging_reason"] = (
            "레포는 갱신됐으나 base 스테이징에 실패했다: %s (다음 백업이 복구한다)" % e)
    return out


def main():
    if len(sys.argv) != 3:
        print("사용: collect_plugins.py <레포 경로> <스테이징 디렉토리>", file=sys.stderr)
        sys.exit(1)
    try:
        out = collect(sys.argv[1], sys.argv[2])
    # collect_mcp·compare_plugins·plan_plugins와 같은 튜플을 쓴다. 갈리면 한쪽만
    # traceback으로 죽는다. ValueError는 코어의 normalize 계약 위반(훅이 키 집합을 바꿈)과
    # held_kinds의 분류 불가에서 온다 — 어느 쪽도 backup 흐름 전체를 세우지 않는다.
    # AutoFlagsUnavailable·HeldStateUnavailable은 여기 없다 — 섹션 단위로 이미 흡수됐다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `_read_hold_inputs`의 `skipped["pluginConfigs"]` 대입을 지우기 → 두 섹션 skip 테스트가 잡아야 한다
- `skipped.setdefault(...)`를 `skipped[...] =`로 바꾸기 → **auto 실패 사유가 보류 파일 사유로 덮인다.** 잡는 테스트가 없으면 보강한다
- skipped 갈래의 `merged_doc[section] = repo[section]`을 `{}`로 바꾸기 → 레포 pass-through 테스트가 잡아야 한다(**7.5의 전량 소실**)
- `base_doc[section] = previous_base.get(section, {})`를 `{}`로 바꾸기 → base pass-through 테스트가 잡아야 한다
- `build_hooks` 호출을 `pc.load_backup` **앞으로** 옮기기(레포 대신 `{}`를 넘기기) → H3 보존 테스트가 잡아야 한다. **이것이 9.1.1이 경고한 순서 뒤집기다**
- `None if base is None else base.get(section, {})`를 `base.get(section, {}) if base else {}`로 바꾸기 → **`None` degrade가 사라진다.** 새 기기 테스트가 잡지 못하면 보강한다
- 스테이징과 레포 쓰기 순서를 맞바꾸기 / `os.replace`를 지우기 → 레포 쓰기 실패 테스트가 잡아야 한다
- 보고 생성을 쓰기 **뒤로** 옮기기 → 보고 우선 테스트가 잡아야 한다
- `except` 튜플에서 `ValueError`를 빼기 → CLI 종료 코드 테스트로는 안 잡힌다. `held_kinds`가 던지는 경로로 CLI 테스트를 하나 더 만들지 판단한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-backup/scripts/collect_plugins.py \
        plugins/claude-sync/lib/plugin_config.py plugins/claude-sync/tests/test_plugin_scripts.py
git commit -m "feat(backup): collect_plugins.py — 섹션별 3-way 병합과 단계별 skip"
```

---

### Task 8: `compare_plugins.py` — 읽기 전용 상태 비교

**근거:** spec 9.2, 6.5, 3.1

`compare_mcp.py`는 **base를 읽지 않는다.** 그 구조를 그대로 쓰면 6.4의 탈출구가 status를 조용하게 만들지 못한다 — restore만 조용해지고 `/sync-status`는 매번 보고한다. `hold`는 `plugins-held.json`·`installed_plugins.json`·로컬/레포 값만 있으면 계산되므로 **base 없이도 보류를 안다.** 읽기 전용 성질은 그대로다.

**값 보류 키는 `only_local`/`changed`에 넣지 않는다.** 의존성으로 설치된 플러그인이 매번 *"backup 시 추가"* 로 보고되면 **거짓이고 해소 불가능하다** — 3.1에 따라 백업하지 않으므로 다음 백업에도 추가되지 않는다.

**보류 키 중 로컬에 없는 것의 이름은 `absent_locally`이지 `not_installed`가 아니다.** 그 식이 계산하는 것은 "로컬 섹션 문서에 그 키가 없다"이고, 그것이 *"레포 값을 보존합니다"* 가 거짓이 되는 정확한 조건이다(8.4). **이 스크립트는 설치 여부를 알 수 없다** — `installed_plugins.json`에서 읽는 것은 `read_auto_ids`가 돌려주는 auto 집합뿐이고, auto 키는 그 파일에 있다는 것 자체가 이 기기에 설치되어 있다는 뜻이라(3.4) `not_installed`로 부르면 실측으로 거짓이 된다(auto 플러그인이 `settings.json`에 없는 조합에서 재현된다).

**`changed`에는 값도 함께 싣는다(`changed_detail`).** 키 목록만으로는 켬→끔인지 그 반대인지, 레포 값이 확장 포맷(`["1.0.0"]`)인지가 출력 어디에도 없어 **소비자가 9.2가 요구하는 문구를 만들 수 없다.** 만들려면 `settings.json`과 `plugins.json`을 직접 다시 읽어야 하고 그 순간 status 경로에 두 번째 파서가 생긴다 — 그것이 정확히 결함 B의 형태이고 이 스크립트가 존재하는 이유가 무효가 된다. H3는 보통 `held["extended_value"]`로 종류가 드러나지만 **6.4의 release 탈출구를 쓴 키는 보류가 풀려 `changed`로 떨어지므로** 그때는 `changed_detail`만이 남는 근거다. 값은 반드시 **정규화된** 쪽을 싣는다 — 원본을 실으면 로컬 평문 option 값이 보고로 새어 6.1이 깨진다. 그리고 `out["changed"]` 하나에서 파생시킨다(두 곳에서 만들면 갈리고, 갈려도 증상이 없다).

**Files:**
- Create: `plugins/claude-sync/skills/sync-status/scripts/compare_plugins.py`
- Modify: `plugins/claude-sync/tests/test_plugin_scripts.py` (추가)

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_scripts.py` 끝에 추가한다. 상단 import에 `import compare_plugins  # noqa: E402`를 더한다.

```python
def compare(tmp_path, local=None, repo=None, installed=None, held=None):
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    return compare_plugins.compare(
        os.path.join(repo_dir, pc.BACKUP_RELPATH),
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "none-held.json"))


def test_compare_reports_value_changes_not_just_key_sets(tmp_path):
    """결함 B — check_status.py의 키 집합 비교는 켬/끔 변경을 못 봤다."""
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": False}},
                  repo={"enabledPlugins": {"p@m": True}})
    section = out["sections"]["enabledPlugins"]
    assert section["changed"] == ["p@m"]
    assert section["only_local"] == [] and section["only_repo"] == []


def test_compare_converges_masked_secrets_to_in_sync(tmp_path):
    """로컬 평문과 레포 마스킹을 원본끼리 비교하면 영구히 "변경됨"이 된다."""
    out = compare(tmp_path,
                  local={"pluginConfigs": {"p@m": {"options": {"k": "sk-real"}}}},
                  repo={"pluginConfigs": {"p@m": {"options": {"k": pc.SENTINEL}}}})
    assert out["sections"]["pluginConfigs"]["changed"] == []


def test_compare_keeps_held_keys_out_of_the_three_buckets(tmp_path):
    """9.2 — "backup 시 추가"는 거짓이고 사용자가 해소할 수도 없다."""
    out = compare(tmp_path, local={"enabledPlugins": {"dep@m": True}},
                  installed=write_installed(tmp_path,
                                            {"dep@m": [{"scope": "user", "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    assert section["only_local"] == []
    assert section["held"]["auto"] == ["dep@m"]


def test_compare_stays_silent_after_the_user_declined_a_config(tmp_path):
    """6.5 — base를 읽지 않고도 보류를 알아야 status가 조용해진다."""
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({
        "version": 1,
        "pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
        "release": {"enabledPlugins": []}}), encoding="utf-8")
    out = compare(tmp_path, local={}, repo=repo, held=str(held))
    section = out["sections"]["pluginConfigs"]
    assert section["only_repo"] == []
    assert section["held"]["declined"] == ["delta@m"]


def test_compare_reports_again_when_the_repo_value_changes(tmp_path):
    """지문이 달라지면 자동으로 해제된다 — 6.4가 약속한 동작이다."""
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({"pluginConfigs": {"delta@m": "0" * 64},
                                "release": {"enabledPlugins": []}}), encoding="utf-8")
    out = compare(tmp_path, local={},
                  repo={"pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}},
                  held=str(held))
    assert out["sections"]["pluginConfigs"]["only_repo"] == ["delta@m"]


def test_compare_marks_unrestorable_repo_only_entries(tmp_path):
    """9.2 — "restore 시 설치"가 아니라 "이 기기에서는 복원할 수 없습니다"로 말해야 한다."""
    out = compare(tmp_path, local={}, repo={"enabledPlugins": {"p@nowhere": True}})
    assert out["sections"]["enabledPlugins"]["unrestorable"] == ["p@nowhere"]


def test_compare_distinguishes_installed_extended_values(tmp_path):
    """9.2·8.4 — H3는 행동 보류가 아니므로 "설치됨"과 "미설치"를 문구가 갈라야 한다."""
    installed = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert installed["sections"]["enabledPlugins"]["held"]["extended_value"] == ["p@m"]
    assert installed["sections"]["enabledPlugins"]["absent_locally"] == []
    missing = compare(tmp_path, local={}, repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert missing["sections"]["enabledPlugins"]["absent_locally"] == ["p@m"]


def test_absent_locally_is_not_a_claim_that_the_plugin_is_not_installed(tmp_path):
    """이름이 뜻하는 것은 "로컬 섹션 문서에 값이 없다"이지 "미설치"가 아니다.

    installed_plugins.json에 있다는 것 자체가 이 기기에 설치되어 있다는 뜻인데(3.4),
    그 파일에서 auto 플래그만 읽는 이 스크립트는 설치 여부를 알 수 없다.
    """
    out = compare(tmp_path, local={}, repo={"enabledPlugins": {"dep@m": True}},
                  installed=write_installed(tmp_path,
                                            {"dep@m": [{"scope": "user", "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    assert section["status"] == "ok"
    assert section["held"]["auto"] == ["dep@m"]      # 설치되어 있다
    assert section["absent_locally"] == ["dep@m"]    # 그런데도 여기 들어온다


def test_compare_says_which_way_an_on_off_change_went(tmp_path):
    """9.2 — changed가 키 목록뿐이면 켬→끔인지 그 반대인지가 출력 어디에도 없다."""
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                  repo={"enabledPlugins": {"p@m": False}})
    section = out["sections"]["enabledPlugins"]
    assert section["changed"] == ["p@m"]
    assert section["changed_detail"] == {"p@m": {"local": True, "repo": False}}


def test_released_extended_value_still_shows_it_is_a_version_constraint(tmp_path):
    """6.4의 탈출구를 쓴 키는 보류가 풀려 changed로 떨어진다 — 종류가 held에서 사라진다."""
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({"version": 1, "pluginConfigs": {},
                                "release": {"enabledPlugins": ["p@m"]}}),
                    encoding="utf-8")
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                  repo={"enabledPlugins": {"p@m": ["1.0.0"]}}, held=str(held))
    section = out["sections"]["enabledPlugins"]
    assert section["held"]["extended_value"] == []      # 보류가 풀렸다
    assert section["changed_detail"]["p@m"] == {"local": True, "repo": ["1.0.0"]}


def test_changed_detail_is_derived_from_changed_and_cannot_drift(tmp_path):
    """같은 값을 두 곳에서 만들면 갈리고, 갈려도 증상이 없다 — 한 곳에서 파생시킨다."""
    out = compare(tmp_path,
                  local={"enabledPlugins": {"a@m": True, "b@m": False, "same@m": True}},
                  repo={"enabledPlugins": {"a@m": False, "b@m": True, "same@m": True}})
    section = out["sections"]["enabledPlugins"]
    assert section["changed"] == ["a@m", "b@m"]
    assert sorted(section["changed_detail"]) == section["changed"]


def test_changed_detail_carries_normalized_values_not_plaintext(tmp_path):
    """changed_detail에 원본을 실으면 마스킹 계층 전체를 우회한다 (6.1).

    섹션이 접히거나 changed가 비면 "평문이 없다"가 저절로 참이 된다 — 앞에서 막는다.
    """
    out = compare(tmp_path,
                  local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}},
                  repo={"pluginConfigs": {"p@m": {"options": {"apiKey": pc.SENTINEL,
                                                             "region": pc.SENTINEL}}}})
    section = out["sections"]["pluginConfigs"]
    assert section["status"] == "ok"
    assert section["changed"] == ["p@m"]
    assert "sk-real" not in json.dumps(out, ensure_ascii=False)


def test_compare_never_reads_or_writes_base(tmp_path, monkeypatch):
    """읽기 전용 스킬이다 — base를 읽으면 status와 backup의 판정이 갈린다."""
    def boom(*args, **kwargs):
        raise AssertionError("compare_plugins가 base를 읽었다")

    monkeypatch.setattr(compare_plugins.pc, "parse_base", boom)
    assert compare(tmp_path, local={"enabledPlugins": {"p@m": True}})["status"] == "ok"


def test_compare_skips_sections_the_same_way_backup_does(tmp_path):
    """스킬마다 다른 범위로 접으면 사용자가 두 명령에서 다른 상태를 본다."""
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert out["sections"]["extraKnownMarketplaces"]["status"] == "ok"
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_scripts.py -q`
기대: 신규 테스트 FAIL

- [ ] **Step 3: 구현**

`skills/sync-status/scripts/compare_plugins.py`를 만든다.

```python
#!/usr/bin/env python3
"""로컬 플러그인 상태와 레포 백업의 차이를 섹션별로 보고한다 (읽기 전용).

사용: compare_plugins.py <레포의 plugins.json 경로>

판정은 keyed_sync.diff 하나만 쓴다 — status와 backup이 서로 다른 파서를 갖는 것이
결함 B의 원인이었다(check_status.py는 enabledPlugins의 **키 집합만** 비교했다).

**base는 읽지도 갱신하지도 않는다.** 그래도 보류는 안다 — hold는 plugins-held.json·
installed_plugins.json·로컬/레포 값만 있으면 계산되기 때문이다(spec 6.5). base를 읽지
않으면서 보류를 아는 이 성질이 없으면 6.4의 탈출구가 restore만 조용하게 만들고
/sync-status는 매번 보고한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import keyed_sync as ks  # noqa: E402
import plugin_config as pc  # noqa: E402


def compare(backup_path, settings_path=None, installed_path=None, held_path=None):
    """{"status": "ok", "sections": {섹션: {...}}}

    diff가 양쪽에 정규화를 적용하므로 로컬 평문과 레포 마스킹이 in_sync로 수렴한다.
    값 보류 키는 세 버킷 어디에도 넣지 않고 종류별 held로만 보고한다 — "backup 시
    추가"는 거짓이고 사용자가 해소할 수도 없다(spec 9.2).
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    # 두 진입점을 따로 부르면 두 입력이 같다는 보장이 호출부의 규율뿐이고,
    # 어긋나면 held_kinds가 분류에 실패해 섹션이 통째로 skipped가 된다(Task 7 리뷰 I-4).
    hooks, context = pc.hooks_and_context(local, repo, auto_ids=auto_ids, held_state=held_state)

    sections = {}
    for section in pc.SECTIONS:
        if section in skipped:
            sections[section] = pc.skipped_section(skipped[section])
            continue
        normalize = hooks[section]["normalize"]
        restorable = hooks[section]["restorable"]
        repo_norm = normalize(repo[section])
        local_norm = normalize(local[section])
        out = ks.diff(local[section], repo[section],
                      normalize=normalize, hold=hooks[section]["hold"])
        sections[section] = {
            "status": "ok",
            "only_local": out["only_local"],
            "only_repo": out["only_repo"],
            "changed": out["changed"],
            # 키 목록만으로는 켬→끔인지, 레포 값이 확장 포맷인지를 말할 수 없다. 소비자가
            # 그 문구를 만들려고 두 파일을 다시 읽으면 결함 B가 부활한다(9.2).
            # **out["changed"] 하나에서 파생**시키고, 값은 반드시 **정규화된** 쪽을
            # 싣는다 — 원본이면 로컬 평문 option 값이 보고로 샌다(6.1).
            "changed_detail": {k: {"local": local_norm[k], "repo": repo_norm[k]}
                               for k in out["changed"]},
            # "restore 시 설치"가 거짓인 항목을 갈라 낸다 — 이 기기에서는 복원할 수 없다.
            "unrestorable": [k for k in out["only_repo"]
                             if not restorable(k, repo_norm[k])],
            "held": pc.held_kinds(section, out["held"], repo_norm=repo_norm, **context),
            # **값 보류 키 중 로컬 섹션 문서에 값이 없는 것.** H3만이 아니라
            # out["held"] 전부를 훑는다 — "레포 값을 보존합니다"가 거짓이 되는 조건이
            # 종류와 무관하게 정확히 이것이다(spec 8.4).
            # **not_installed이라 부르지 않는다** — 이 스크립트는 설치 여부를 알 수 없다.
            # installed_plugins.json에서 읽는 것은 auto 집합뿐이고, auto 키는 그 파일에
            # 있다는 것 자체가 설치되어 있다는 뜻이다(3.4).
            "absent_locally": [k for k in out["held"] if k not in local[section]],
        }
    return {"status": "ok", "sections": sections}


def main():
    if len(sys.argv) != 2:
        print("사용: compare_plugins.py <레포의 plugins.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = compare(sys.argv[1])
    # collect_plugins·plan_plugins와 같은 튜플을 쓴다. 갈리면 한쪽만 traceback으로 죽는다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 비교 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `ks.diff` 대신 키 집합 비교(`set(local) - set(repo)`)로 되돌리기 → 값 변경 테스트가 잡아야 한다
- `normalize=normalize`를 지우고 원본끼리 비교하기 → 마스킹 수렴 테스트가 잡아야 한다
- `hold=hooks[section]["hold"]`를 `ks.no_hold`로 바꾸기 → 보류 테스트 셋이 잡아야 한다
- `absent_locally`를 빈 목록(`[]`)으로 만들기 → `absent_locally` 테스트 셋이 잡아야 한다
- `absent_locally`를 `out["held"]`가 아니라 `out["only_repo"]`에서 만들기 → 보류 키가 통째로 빠지므로 같은 셋이 잡아야 한다
- `changed_detail`을 `{}`로 비우기 → 켬/끔 방향·release 탈출구·파생 잠금 테스트가 잡아야 한다
- `changed_detail`에 정규화 대신 원본(`local[section]`·`repo[section]`)을 싣기 → 평문 유출 테스트가 잡아야 한다
- `unrestorable` 계산에 `repo_norm[k]` 대신 `local`을 넘기기 → `KeyError`가 나는지, 아니면 조용히 빈 목록이 되는지 확인한다. 조용하면 테스트를 보강한다
- `pc.parse_base`를 부르는 줄을 **추가**해 보기 → 읽기 전용 테스트가 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-status/scripts/compare_plugins.py plugins/claude-sync/tests/test_plugin_scripts.py
git commit -m "feat(status): compare_plugins.py — 값 변경과 보류를 보고한다"
```

**인계:** spec 9.2의 *"H3 항목은 '설치됨'과 '미설치'를 구별해 말한다"* 는 문구는 **설치 집합 전체**가 있어야 만들 수 있다. compare가 `installed_plugins.json`에서 읽는 것은 auto 집합뿐이므로 **현재 계약으로는 "로컬 섹션 문서에 값이 없다"까지만 말할 수 있다**(그래서 필드 이름이 `absent_locally`다). 배선 task(Task 14)에서 문구를 그 범위로 확정할지, 설치 집합 읽기를 추가할지 그때 정한다.

---

### Task 9: `plan_plugins.py plan` — 복원 계획

**근거:** spec 9.3.1·9.3.2·9.3.3·9.3.4·9.3.6, 8.4, 10.1·10.2

계획은 **판정의 단일 진입점**이다. SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이 되살아나므로, 등록 인자·설정 키 목록·의존 관계·복원 불가 사유를 전부 계획에 실어 준다.

**`enable`/`disable`은 멱등이 아니다**(같은 상태면 exit 1). 그래서 값을 맞추는 명령은 **현재 상태와 다를 때만** 낸다. 판정에는 **로컬의 현재 값**을 쓴다 — "설치 직후의 값은 `true`"는 `enabledPlugins`에서 온 설치 대상에만 참이다. `pluginConfigs`에서 온 키는 **이미 로컬에 설치돼 있을 수 있다**: 그 섹션의 `route_new`는 "그 섹션에" 레포 전용인 키를 훑을 뿐 플러그인 자체의 설치 여부와 무관하기 때문이다. 로컬에 값이 **없을 때만** 설치 직후의 `true`로 떨어진다. 그 로컬 값은 `local_values` 페이로드와 **같은 정규화 훅**을 통과한 것을 쓴다 — 한쪽만 마스킹된 두 값을 비교하면 없어야 할 `enable`/`disable`이 CLI 명령으로 나간다. 상수 `true`를 쓰면 이미 꺼진 플러그인에 `disable`이 나가 `exit 1`의 거짓 실패가 되고, spec 10.1의 실패 수집에 실려 "복원이 실패했다"로 읽힌다.

**부재는 `false`가 아니다.** 레포에 키가 아예 없는 항목을 `disable` 대상으로 삼지 않는다 — 매니페스트 기본값에 위임하는 상태이므로 의미가 반대다.

**Files:**
- Create: `plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py`
- Modify: `plugins/claude-sync/lib/plugin_config.py` (`value_command` 추가)
- Modify: `plugins/claude-sync/tests/test_plugin_config.py`, `tests/test_plugin_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_config.py` 끝에 추가한다.

```python
def test_value_command_is_silent_when_the_state_already_matches():
    """14.1 — enable/disable은 멱등이 아니다. 같은 상태면 exit 1로 거짓 실패를 낸다."""
    assert pc.value_command(True, True) is None
    assert pc.value_command(False, False) is None


def test_value_command_names_the_direction():
    assert pc.value_command(False, True) == "enable"
    assert pc.value_command(True, False) == "disable"


def test_value_command_refuses_extended_repo_values():
    """배열·객체를 쓸 CLI가 없다 — H3의 값은 밀지 않는다."""
    assert pc.value_command(True, ["1.0.0"]) is None
    assert pc.value_command(True, {"version": "1"}) is None


def test_value_command_treats_absent_local_as_needing_the_command():
    """부재는 false가 아니다 — 매니페스트 기본값에 위임하는 상태다 (9.3.3)."""
    assert pc.value_command(None, False) == "disable"
    assert pc.value_command(None, True) == "enable"
```

`tests/test_plugin_scripts.py` 끝에 추가한다. 상단 import에 `import plan_plugins  # noqa: E402`를 더한다.

```python
def build_plan(tmp_path, local=None, repo=None, base=None, installed=None, held=None):
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    return plan_plugins.build_plan(
        os.path.join(repo_dir, pc.BACKUP_RELPATH),
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path, base))


def test_plan_exposes_exactly_eleven_buckets_per_section(tmp_path):
    """코어가 버킷을 늘리면 여기서 걸린다 — 화이트리스트는 조용히 빠뜨린다.

    MCP는 아홉이지만 플러그인은 두 축을 **노출한다** — H3의 value_held는 사용자에게
    별도 문구로 말해야 하고, action_held는 어떤 명령의 대상도 아님을 알려야 한다.
    """
    out = build_plan(tmp_path)
    for section in pc.SECTIONS:
        assert set(out["sections"][section]) == set(ks.BUCKETS) | {"status"}


def test_plan_routes_new_repo_entries_by_secret_need(tmp_path):
    repo = {"enabledPlugins": {"plain@m": True, "conf@m": True},
            "extraKnownMarketplaces": {"m": GH},
            "pluginConfigs": {"conf@m": {"options": {"apiKey": pc.SENTINEL}}}}
    out = build_plan(tmp_path, local={}, repo=repo)
    assert out["sections"]["enabledPlugins"]["add"] == ["conf@m", "plain@m"]
    assert out["sections"]["pluginConfigs"]["needs_secret"] == ["conf@m"]
    assert out["config_keys"] == {"conf@m": ["apiKey"]}
    # conf@m은 두 섹션의 설치 버킷에 **동시에** 있다. 목록에 두 번 실리면 설치 명령이
    # 두 번 나가고, 두 번째는 이미 설치된 상태에서 실패해 거짓 실패로 보고된다.
    assert out["install"] == ["conf@m", "plain@m"]


def test_plan_installs_a_plugin_that_only_plugin_configs_names(tmp_path):
    """9.3.1의 4단계(설정 채우기)도 `install --config`다 — 설치 목록에서 빠지면
    그 플러그인의 설정을 채울 명령이 어디에서도 나오지 않는다.

    enabledPlugins의 add가 **비어 있는** 것을 함께 못박는다 — 그 섹션이 install을
    대신 채우면 이 단정이 pluginConfigs 기여를 재지 못한다.

    같은 fixture로 "부재는 false가 아니다"를 계획 층위에서 못박는다 (1-c C4) —
    conf@m은 **설치 대상이면서** 레포 enabledPlugins에 없다(= 매니페스트 기본값에
    위임). disable 가드가 부재를 false로 접으면 이 플러그인이 설치 직후 꺼진다.
    **여기가 그 가드를 재는 유일한 자리다** — 아래
    test_plan_never_disables_a_key_absent_from_the_repo의 키는 레포에 없어
    install에 애초에 들어오지 않으므로 그쪽 단정은 가드와 무관하게 참이다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"extraKnownMarketplaces": {"m": GH},
                           "pluginConfigs": {"conf@m": {"options":
                                                        {"apiKey": pc.SENTINEL}}}})
    assert out["sections"]["enabledPlugins"]["add"] == []
    assert out["install"] == ["conf@m"]
    assert out["depends_on"] == {"conf@m": "m"}
    assert out["disable_after_install"] == []


def test_plan_gives_marketplace_add_arguments(tmp_path):
    """SKILL.md가 레포 파일을 직접 파싱하면 파서 두 벌이 되살아난다 (8.6)."""
    out = build_plan(tmp_path, local={}, repo={"extraKnownMarketplaces": {"m": GH}})
    assert out["marketplace_add"] == [
        {"name": "m", "arg": "june20516/suberpower", "reserved": False}]


def test_plan_skips_always_known_marketplaces(tmp_path):
    """14.1 — 실패할 등록 시도를 애초에 만들지 않는다 (8.2)."""
    repo = {"extraKnownMarketplaces": {name: GH for name in sorted(pc.ALWAYS_KNOWN)}}
    out = build_plan(tmp_path, local={}, repo=repo)
    assert out["marketplace_add"] == []
    assert out["skipped_always_known"] == sorted(pc.ALWAYS_KNOWN)


def test_plan_flags_reserved_names_without_filtering_them(tmp_path):
    """8.3 — 정당한 소유자일 수 있으므로 시도한다. 다만 갈래를 미리 알려 준다."""
    out = build_plan(tmp_path, local={},
                     repo={"extraKnownMarketplaces": {"healthcare": GH}})
    assert out["marketplace_add"] == [
        {"name": "healthcare", "arg": "june20516/suberpower", "reserved": True}]


def test_plan_reports_dependency_of_each_install_on_its_marketplace(tmp_path):
    """9.3.2 — 1단계가 실패한 마켓플레이스의 플러그인은 2단계를 시도하지 않는다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@m": True},
                           "extraKnownMarketplaces": {"m": GH}})
    assert out["depends_on"] == {"p@m": "m"}


def test_plan_omits_dependency_for_always_known_marketplaces(tmp_path):
    """등록 단계가 없는 마켓플레이스에 blocked를 걸면 설치가 영영 차단된다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@claude-plugins-official": True}})
    # 설치 대상이 되었는데도 의존이 없다는 것이 요지다. install이 비면 저절로 참이 된다.
    assert out["install"] == ["p@claude-plugins-official"]
    assert out["depends_on"] == {}


def test_plan_disables_only_what_install_would_leave_wrong(tmp_path):
    """설치 직후 값은 true다. 레포가 false인 것만 disable 대상이다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"on@m": True, "off@m": False},
                           "extraKnownMarketplaces": {"m": GH}})
    assert out["disable_after_install"] == ["off@m"]


def test_plan_disables_nothing_outside_the_install_list(tmp_path):
    """disable은 **설치 직후**의 값 맞추기다 — 그 범위를 install 밖으로 넓히면 이미
    로컬에 있는 항목까지 대상이 된다.

    wait@m은 케이스 9로 사용자 선택을 기다리는 중인데 레포 값이 false다. 범위가
    넓어지면 선택을 묻기도 전에 disable 명령이 나간다. 같은 fixture에서 install에
    **있는** off@m은 대상이 되는 것을 함께 못박는다 — 안 그러면 "아무것도 disable하지
    않는다"로 저절로 참이 된다.
    """
    out = build_plan(tmp_path, local={"enabledPlugins": {"wait@m": True}},
                     repo={"enabledPlugins": {"wait@m": False, "off@m": False},
                           "extraKnownMarketplaces": {"m": GH}})
    section = out["sections"]["enabledPlugins"]
    assert section["both_changed"] == ["wait@m"]     # 레포 값이 false인 미설치 대상
    assert out["install"] == ["off@m"]
    assert out["disable_after_install"] == ["off@m"]


def test_plan_does_not_disable_a_plugin_that_is_already_off_locally(tmp_path):
    """install의 절반은 "설치 직후"가 아니다 — pluginConfigs 기여로 들어온 키는 이미
    로컬에 설치돼 있을 수 있다. 그 섹션의 route_new는 "그 섹션에" 레포 전용인 키를
    훑을 뿐 플러그인 자체의 설치 여부와 무관하기 때문이다.

    already@m은 로컬 enabledPlugins에 이미 false로 있고 레포도 false다(= in_sync).
    disable 판정이 로컬 값 자리에 상수 true를 넣으면 "true → false이니 disable"로 읽혀
    이미 꺼진 플러그인에 명령이 나가고, enable/disable은 멱등이 아니라 exit 1이다.

    같은 fixture에 진짜 신규 설치인 off@m을 함께 둔다 — 없으면 "아무것도 disable하지
    않는다"로 저절로 참이 되어 판별력을 잃는다.
    """
    out = build_plan(
        tmp_path,
        local={"enabledPlugins": {"already@m": False}},
        repo={"enabledPlugins": {"already@m": False, "off@m": False},
              "extraKnownMarketplaces": {"m": GH},
              "pluginConfigs": {"already@m": {"note": "x"}}})
    section = out["sections"]["enabledPlugins"]
    # 로컬 값이 이미 레포와 같다 — 이 단정이 없으면 아래가 "레포에 없어서"로도 참이 된다.
    assert section["in_sync"] == ["already@m"]
    assert out["install"] == ["already@m", "off@m"]
    assert out["disable_after_install"] == ["off@m"]


def test_plan_sorts_install_across_both_contributing_sections(tmp_path):
    """install은 두 섹션의 기여를 이어 붙인다 — 정렬하지 않으면 순서가 섹션 순서에
    끌려가 비결정적으로 보인다.

    **삽입 순서와 정렬 순서가 다른** 이름을 쓴다: enabledPlugins가 zeta@m을,
    pluginConfigs가 alpha@m을 낸다. 이어 붙인 그대로면 [zeta@m, alpha@m]이다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"zeta@m": True},
                           "extraKnownMarketplaces": {"m": GH},
                           "pluginConfigs": {"alpha@m": {"options":
                                                         {"apiKey": pc.SENTINEL}}}})
    section = out["sections"]
    assert section["enabledPlugins"]["add"] == ["zeta@m"]
    assert section["pluginConfigs"]["needs_secret"] == ["alpha@m"]
    assert out["install"] == ["alpha@m", "zeta@m"]


def test_plan_carries_both_values_for_every_decided_key(tmp_path):
    """8.6 — SKILL.md가 케이스 8·9의 값을 알아야 한다. 없으면 레포 파일을 다시 파싱해야
    하고 그것이 "파서 두 벌"이다.

    세 갈래(repo_ahead·both_changed·value_held)와 install을 **동시에** 채우고, 같은 키의
    레포 값과 로컬 값이 **서로 다르게** 만든다 — 한쪽을 비우거나 두 출처를 뒤바꾸는
    회귀가 각각 따로 드러나야 하기 때문이다. 판정 대상이 아닌 두 키(local_ahead의
    mine@m, local_only의 solo@m)를 함께 두어 목록이 decided로 좁혀지는 것도 잰다.

    **decided는 set이므로 정렬 전 순서를 이름으로 통제할 수 없다**(plan_plugins의 set
    comprehension). 그 순서는 버킷 순회 순서가 아니라 **문자열 해시 순서**이고 실행마다
    PYTHONHASHSEED에 끌려간다. 그래서 아래 정렬 단정은 정상 코드에서 **항상** 참이고,
    sorted를 없앤 회귀는 원소 수가 n일 때 약 1 - 1/n! 확률로 잡힌다 — 결정적이지 않다.
    **원소를 줄이면 그 확률이 떨어진다**(2원소면 절반을 놓친다). 그래서 decided를 여섯으로
    채운다 — repo_ahead 둘 + both_changed 하나 + value_held 하나 + install 둘 → 1/720.
    """
    base = {"enabledPlugins": {"zeta@m": True, "bravo@m": True, "both@m": True,
                               "mine@m": True}}
    local = {"enabledPlugins": {"zeta@m": True, "bravo@m": True, "both@m": ["2.0.0"],
                                "mine@m": False, "alpha@m": True, "solo@m": True}}
    repo = {"enabledPlugins": {"zeta@m": False, "bravo@m": False, "both@m": False,
                               "mine@m": True, "alpha@m": ["1.0.0"], "new@m": True,
                               "delta@m": True},
            "extraKnownMarketplaces": {"m": GH}}
    out = build_plan(tmp_path, local=local, repo=repo, base=base)
    section = out["sections"]["enabledPlugins"]
    assert section["repo_ahead"] == ["bravo@m", "zeta@m"]  # 케이스 8
    assert section["both_changed"] == ["both@m"]           # 케이스 9
    assert section["value_held"] == ["alpha@m"]            # H3
    assert section["local_ahead"] == ["mine@m"]            # 케이스 7 — 판정 대상이 아니다
    assert section["local_only"] == ["solo@m"]             # 케이스 1 — 판정 대상이 아니다
    assert out["install"] == ["delta@m", "new@m"]
    assert out["repo_values"] == {"zeta@m": False, "bravo@m": False, "both@m": False,
                                  "alpha@m": ["1.0.0"], "new@m": True, "delta@m": True}
    # new@m·delta@m은 로컬에 없다 — 없는 키를 넣으면 SKILL.md가 "값이 바뀐다"고 잘못 말한다.
    assert out["local_values"] == {"zeta@m": True, "bravo@m": True,
                                   "both@m": ["2.0.0"], "alpha@m": True}
    # decided를 정렬하지 않으면 집합 순회가 문자열 해시에 끌려가 **JSON 출력의 키 순서가
    # 실행마다 바뀐다.** dict를 ==로 비교하는 위의 두 단정은 순서를 보지 못하므로, install만
    # 정렬이 고정되고 같은 파일의 다른 출력은 아닌 비대칭이 남는다. 그것을 여기서 닫는다.
    assert list(out["repo_values"]) == sorted(out["repo_values"])
    assert list(out["local_values"]) == sorted(out["local_values"])


def test_plan_reads_base_of_each_section_from_that_section(tmp_path):
    """base를 안 읽거나 엉뚱한 섹션에서 읽으면 삭제 후보(케이스 4·5)가 통째로 사라진다 —
    로컬 신규(케이스 1)로 보이므로 예외도 빈 결과도 나지 않는다.

    세 섹션의 base 키를 **모두 다르게** 둔다. 한 섹션의 base를 세 섹션에 돌려 쓰면
    나머지 둘의 키가 base에 없어 local_only로 새는 것이 드러난다.
    """
    local = {"enabledPlugins": {"gone@m": True},
             "extraKnownMarketplaces": {"m": GH},
             "pluginConfigs": {"conf@m": {"options": {"token": "t"}}}}
    base = {"enabledPlugins": {"gone@m": True},
            "extraKnownMarketplaces": {"m": GH},
            "pluginConfigs": {"conf@m": {"options": {"token": pc.SENTINEL}}}}
    out = build_plan(tmp_path, local=local, repo={}, base=base)
    for section, key in (("enabledPlugins", "gone@m"),
                         ("extraKnownMarketplaces", "m"),
                         ("pluginConfigs", "conf@m")):
        assert out["sections"][section]["local_stale"] == [key]
        # base를 못 읽었을 때 이 키가 흘러가는 곳이다. 비어 있어야 위 단정이 공허하지 않다.
        assert out["sections"][section]["local_only"] == []


def test_plan_never_disables_a_key_absent_from_the_repo(tmp_path):
    """14.1 — 부재는 꺼짐이 아니다 (1-c C4).

    **이 fixture는 disable 가드를 타지 않는다** — local@m은 레포에 없어 install에
    애초에 들어오지 않으므로 disable_after_install 단정은 가드와 무관하게 참이다.
    가드 자체는 test_plan_installs_a_plugin_that_only_plugin_configs_names가 잰다.
    여기서 재는 것은 repo_values의 범위다.
    """
    out = build_plan(tmp_path, local={"enabledPlugins": {"local@m": True}},
                     repo={"enabledPlugins": {}})
    # 케이스 1(로컬 신규)로 떨어진 것을 먼저 못박는다 — 이것이 없으면 두 단정이
    # "레포에 없으므로 어느 목록에도 없다"로 저절로 참이 되어 판별력을 잃는다.
    assert out["sections"]["enabledPlugins"]["local_only"] == ["local@m"]
    assert out["disable_after_install"] == []
    assert "local@m" not in out["repo_values"]


def test_plan_puts_installed_extended_values_in_their_own_bucket(tmp_path):
    """8.4 — both_changed로 부르면 "양쪽이 바뀌었습니다"라는 거짓 문구가 뜬다."""
    out = build_plan(tmp_path, local={"enabledPlugins": {"p@m": True}},
                     repo={"enabledPlugins": {"p@m": ["1.0.0"]},
                           "extraKnownMarketplaces": {"m": GH}})
    section = out["sections"]["enabledPlugins"]
    assert section["value_held"] == ["p@m"]
    assert section["both_changed"] == [] and section["repo_ahead"] == []
    # 이 버킷의 키는 **이미 로컬에 있다.** 설치 목록에 넣으면 SKILL.md가 설치를 다시
    # 시도한다 — 새 기기 갈래(add)와 값만 다른 갈래(value_held)를 가른 이유가 이것이다.
    assert out["install"] == []


def test_extended_value_is_installed_on_a_new_machine(tmp_path):
    """14.1 — 값 보류를 행동 보류로 잘못 구현하는 회귀를 막는다 (5.3).

    설치하지 않으면 어느 기기에도 설치되지 않고, 모두가 값 보류라 아무도 push하지
    않아 레포 값이 영원히 고정되며, 삭제 판정에서도 빠진다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@m": ["1.0.0"]},
                           "extraKnownMarketplaces": {"m": GH}})
    assert out["sections"]["enabledPlugins"]["add"] == ["p@m"]
    assert out["install"] == ["p@m"]


def test_action_held_entries_become_no_command_at_all(tmp_path):
    """5.3 — 행동 보류 키는 어떤 CLI 명령의 대상도 되지 않는다."""
    out = build_plan(tmp_path, local={}, repo={"enabledPlugins": {"dep@m": True},
                                               "extraKnownMarketplaces": {"m": GH}},
                     installed=write_installed(tmp_path,
                                               {"dep@m": [{"scope": "user",
                                                           "auto": True}]}))
    assert out["sections"]["enabledPlugins"]["action_held"] == ["dep@m"]
    assert out["install"] == []
    assert out["disable_after_install"] == []


def test_plan_gives_reasons_for_unrestorable_entries(tmp_path):
    out = build_plan(tmp_path, local={}, repo={"enabledPlugins": {"p@nowhere": True}})
    assert out["sections"]["enabledPlugins"]["unrestorable"] == ["p@nowhere"]
    assert "소스가 없" in out["unrestorable_reasons"]["p@nowhere"]


def test_unrestorable_reason_and_the_verdict_read_the_same_repo(tmp_path):
    """10.2 — 판정(restorable)은 레포를 보는데 사유가 다른 문서를 보면 사유가 None이 되고,
    그 항목은 "복원 불가"로만 남아 사용자가 무엇을 해야 하는지 알 수 없다.

    **로컬에만 있는 마켓플레이스**가 있어야 두 입력이 갈린다 — 레포와 같으면 어느 쪽을
    넘겨도 같은 문장이 나와 이 단정이 판별력을 잃는다.
    """
    out = build_plan(tmp_path, local={"extraKnownMarketplaces": {"m": GH}},
                     repo={"enabledPlugins": {"p@m": True}})
    assert out["sections"]["enabledPlugins"]["unrestorable"] == ["p@m"]
    assert "소스가 없" in out["unrestorable_reasons"]["p@m"]


def test_plan_gives_reasons_for_unrestorable_marketplaces(tmp_path):
    """10.2 — 사유가 **value를 실제로 보는** 갈래는 마켓플레이스뿐이다.

    플러그인 갈래의 unrestorable_reason은 키만 보고 value를 보지 않으므로, 이 스크립트가
    reason에 넘기는 masked[section].get(k)가 옳은 섹션의 옳은 값인지 위의 두 테스트는
    재지 못한다. 마켓플레이스 갈래는 _source_kind(value)와 _SOURCE_ARG_FIELDS로 **세 개의
    서로 다른 사용자 안내**를 만들므로 배선이 어긋나면 여기서만 증상이 난다 — value가
    None으로 새면 "출처 종류를 읽을 수 없다"(c)가 나와 멀쩡한 github 출처를 범인으로
    지목하고, 사유 루프가 enabledPlugins 한 섹션으로 좁혀지면 사유 자체가 사라진다.

    복원 **가능한** good을 함께 둔다 — 없으면 "전부 복원 불가"로도 단정이 참이 된다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"extraKnownMarketplaces": {
                         # github 출처인데 인자로 쓸 repo 필드가 없다 → 갈래 (a)
                         "m": {"source": {"source": "github"}},
                         "good": GH}})
    section = out["sections"]["extraKnownMarketplaces"]
    assert section["unrestorable"] == ["m"]
    assert [entry["name"] for entry in out["marketplace_add"]] == ["good"]
    assert "필드가 비어 있다" in out["unrestorable_reasons"]["m"]


def test_plan_carries_no_secret_values(tmp_path):
    """계획은 SKILL.md의 대화로 흘러가고 임시 파일에 남는다 — 평문이 있으면 안 된다."""
    out = build_plan(tmp_path,
                     local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}},
                     repo={"pluginConfigs": {"p@m": {"options": {"apiKey": pc.SENTINEL}}}})
    # 섹션이 접히면 평문이 실릴 자리 자체가 없어 단정이 공허해진다 — 먼저 확인한다.
    assert out["sections"]["pluginConfigs"]["status"] == "ok"
    assert out["sections"]["pluginConfigs"]["in_sync"] == ["p@m"]
    assert "sk-real" not in json.dumps(out, ensure_ascii=False)


def test_plan_skips_plugin_sections_when_auto_flags_are_unavailable(tmp_path):
    """9.3.6 — backup과 같은 규율을 restore에도 적용한다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@m": True},
                           "extraKnownMarketplaces": {"m": GH}},
                     installed=str(tmp_path / "none-installed.json"))
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    # **최상위는 섹션 skip을 반영하지 않는다(계약).** 여기를 skipped로 접으면 아래
    # marketplace_add 단정이 지키는 "부분 skip은 전체 skip이 아니다"와 어긋나고,
    # 반대로 이 줄이 없으면 두 의미 중 어느 쪽이 계약인지 아무것도 정해지지 않는다 —
    # 소비자는 최상위 ok를 "복원할 것이 없다"로 읽으면 안 된다(build_plan docstring).
    assert out["status"] == "ok"
    # 레포에 마켓플레이스 m이 **있어야** 이 단정이 skip을 잰다. 없으면 p@m이 skip과
    # 무관하게 unrestorable로 떨어져 install이 어차피 빈다.
    assert out["install"] == []
    # 부분 skip이 전체 skip으로 조용히 바뀌지 않았음을 함께 본다 (9.3.6).
    assert [m["name"] for m in out["marketplace_add"]] == ["m"]


def plan_script():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                        "skills", "sync-restore", "scripts",
                                        "plan_plugins.py"))


@pytest.mark.parametrize("args",
                         [[], ["bogus"], ["bogus", "x"], ["plan"], ["plan", "a", "b"]])
def test_plan_cli_rejects_wrong_invocations(tmp_path, args):
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다.

    서브커맨드 검사와 **개수 검사가 둘 다** 필요하다. 개수 검사가 빠지면
    `plan_plugins.py plan`이 usage 대신 IndexError traceback이 되는데, **종료 코드만
    보면 그 회귀가 보이지 않는다** — 처리되지 않은 예외도 1로 끝나기 때문이다.
    사용자가 자기 호출의 잘못을 알 수 있는 유일한 신호가 stderr의 usage다.

    ["bogus", "x"]가 **이름 검사를 재는 유일한 케이스다.** 나머지 넷은 개수만으로도
    걸리므로, 이 항목이 없으면 관문에서 `args[0] == "plan"`을 지워도 아무 테스트도
    실패하지 않고 `plan_plugins.py bogus <경로>`가 usage 없이 계획을 낸다.

    HOME을 격리한다 — 지금은 인자 검증에서 먼저 나가 실제 ~/.claude를 읽지 않지만,
    갈래를 넓힌 뒤 검사가 느슨해지는 순간 진짜 홈을 읽는다(파일 상단 규율).
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    proc = subprocess.run([sys.executable, plan_script()] + args,
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 1
    assert "사용:" in proc.stderr


def test_plan_cli_skips_when_normalize_drops_a_key(tmp_path, monkeypatch, capsys):
    """normalize 계약 위반(ValueError)도 traceback이 아니라 skipped로 접힌다.

    restore_plan은 diff와 **같은** normalize 계약 검사를 통과한다 — 훅이 키 집합을
    바꾸면 코어가 ValueError를 던진다. main()의 except 튜플에서 ValueError가 빠지면
    어댑터 훅의 결함 하나가 restore 흐름 전체를 traceback으로 세우고, 10.3("종료 코드는
    0이다 — 그래야 안내가 보인다")이 깨진다. 형제 둘(collect·compare)에만 이 테스트가
    있으면 세 스크립트 중 restore만 이 성질이 무보증으로 남는다.
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"gone@m": True}})
    monkeypatch.setitem(pc.SECTION_NORMALIZE, "enabledPlugins", drops_a_key)
    monkeypatch.setattr(pc, "DEFAULT_SETTINGS",
                        write_settings(tmp_path, enabledPlugins={"gone@m": True}))
    monkeypatch.setattr(pc, "DEFAULT_INSTALLED", write_installed(tmp_path))
    monkeypatch.setattr(pc, "DEFAULT_HELD", str(tmp_path / "none-held.json"))
    # 실제 ~/.claude/.sync-state를 읽지 않게 한다. base 이력은 이 회귀와 무관하다.
    monkeypatch.setattr(plan_plugins.ss, "read_base", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["plan_plugins.py", "plan",
                                      os.path.join(repo, pc.BACKUP_RELPATH)])
    plan_plugins.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped"
    assert out["reason"]


def test_plan_cli_exits_zero_and_reports_skip(tmp_path):
    """10.3 — 종료 코드는 0이다. 그래야 안내가 보인다.

    레포에 항목이 **있는** 상태로 건너뛴다 — 비어 있으면 "할 일이 없어서 조용한 것"과
    "읽기 실패로 접힌 것"을 출력이 구별하지 못한다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    proc = subprocess.run(
        [sys.executable, plan_script(), "plan", os.path.join(repo, pc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
    assert json.loads(proc.stdout)["reason"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_scripts.py plugins/claude-sync/tests/test_plugin_config.py -q`
기대: 신규 테스트 FAIL

- [ ] **Step 3: 구현**

`lib/plugin_config.py`에 `value_command`를 더한다.

```python
def value_command(local_value, repo_value):
    """레포 값에 맞추려면 실행해야 할 CLI 명령. 필요 없으면 None (9.3.1의 3단계).

    enable/disable은 **멱등이 아니다** — 이미 그 상태면 exit 1이다(실측). 현재 상태와
    같은데 부르면 거짓 실패를 양산한다.

    레포 값이 불리언이 아니면 None이다 — 배열·객체를 쓸 CLI가 없다(H3의 값은 밀지
    않는다). **로컬의 부재는 false가 아니다** — 매니페스트 기본값(defaultEnabled)에
    위임하는 상태이므로 의미가 반대다. 따라서 부재는 "명령이 필요하다"로 다룬다.
    """
    if not isinstance(repo_value, bool):
        return None
    if isinstance(local_value, bool) and local_value == repo_value:
        return None
    return "enable" if repo_value else "disable"
```

`skills/sync-restore/scripts/plan_plugins.py`를 만든다(`apply-base`는 Task 10에서 더한다).

```python
#!/usr/bin/env python3
"""플러그인 복원 계획 수립과 base 계산. 로컬 상태를 직접 바꾸지 않는다.

사용:
  plan_plugins.py plan <레포의 plugins.json 경로>
    복원 계획 JSON을 stdout에 낸다 (섹션별 버킷 11개 + 실행 보조).

CLI 실행과 비밀 값 입력은 SKILL.md의 대화 흐름이 맡는다 — 비밀이 스크립트 인자에
남지 않게 하려는 것과, 9.3.4의 세 선택지가 대화형 확인이어야 하는 것이 같은 이유다.

**계획이 판정의 단일 진입점이다.** SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이
되살아나므로 등록 인자·설정 키 목록·의존 관계·복원 불가 사유를 전부 여기 싣는다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import keyed_sync as ks  # noqa: E402
import plugin_config as pc  # noqa: E402
import sync_state as ss  # noqa: E402

# 설치 대상이 되는 버킷. 값 보류만인 키(H3)는 add로 들어오므로 여기 포함된다 —
# **설치는 한다.** 행동 보류 키는 코어가 action_held 버킷에만 넣으므로 자동으로 빠진다.
INSTALL_BUCKETS = ("add", "needs_secret")

# 등록 후보가 되는 버킷. to_register와 skipped_always_known이 **같은 집합**을 훑어야
# 한다 — 후자는 전자가 always-known으로 걸러 낸 나머지를 보고하는 자리라, 두 열거가
# 갈리면 등록도 보고도 되지 않는 항목이 생긴다. needs_secret을 넣는 것은 **방어다**:
# route_new는 secret_keys(value)가 비지 않을 때만 그 버킷에 넣는데 이 섹션의 훅은
# _no_secrets(SECTION_SECRET_KEYS)라 오늘은 **항상** 빈다. 그래서 지금은 어느 쪽을
# 써도 결과가 같고, 증상이 없는 채로 그 섹션에 되물을 키가 생기는 날 조용히 갈린다.
REGISTER_BUCKETS = ("add", "needs_secret")


def _plan_sections(local, repo, base, hooks, skipped):
    """섹션별 restore_plan. skipped 섹션은 계획을 내지 않는다."""
    out = {}
    for section in pc.SECTIONS:
        if section in skipped:
            out[section] = pc.skipped_section(skipped[section])
            continue
        plan = ks.restore_plan(
            local[section], repo[section],
            None if base is None else base.get(section, {}),
            normalize=hooks[section]["normalize"], hold=hooks[section]["hold"],
            restorable=hooks[section]["restorable"],
            secret_keys=hooks[section]["secret_keys"])
        plan["status"] = "ok"
        out[section] = plan
    return out


def _install_dependencies(install):
    """설치 키 → 먼저 등록해야 할 마켓플레이스 이름 (9.3.2).

    등록이 실패한 마켓플레이스의 플러그인은 설치를 시도하지 않는다 — 시도하면 CLI가
    모호한 문구로 실패해 거짓 실패를 양산한다. always-known 다섯은 등록 단계가 애초에
    없으므로 의존을 걸지 않는다(걸면 설치가 영영 차단된다).

    **marketplace_of가 None인 갈래는 오늘 도달할 수 없다** — install ⊆ restorable이고
    _plugin_restorable은 marketplace_of(key)가 None이면 거짓을 돌려주므로 그런 키는
    unrestorable로 빠져 install에 들어오지 않는다. 그래도 거르는 이유는 빠졌을 때의
    실패 모양이다: None은 ALWAYS_KNOWN에 없으므로 그대로 통과해 {"키": null}이 실리고,
    SKILL.md는 존재하지 않는 등록 단계를 기다리며 그 플러그인을 영영 차단한다 —
    조용하다. **도달 가능한 경로가 있다는 뜻으로 읽지 말 것.**
    """
    out = {}
    for key in install:
        marketplace = pc.marketplace_of(key)
        if marketplace is not None and marketplace not in pc.ALWAYS_KNOWN:
            out[key] = marketplace
    return out


def build_plan(backup_path, settings_path=None, installed_path=None, held_path=None,
               base_dir=ss.BASE_DIR):
    """복원 계획.

    **평문 비밀이 실리지 않는 근거는 "값이 전부 정규화된다"가 아니다.** sections는 코어가
    키 목록만 담아 돌려주므로(restore_plan) 값이 실리는 자리는 **넷**이다 —
    marketplace_add[].arg(마스킹된 레포 값에서 뽑은 source 문자열), config_keys(값이
    아니라 물어야 할 option 키 **이름**), repo_values/local_values(enabledPlugins 전용 —
    도메인상 비밀이 없는 섹션이다), 그리고 unrestorable_reasons(아래). 그 넷을 전부
    마스킹 훅에 통과시키는 것은 근거를 구조로 바꾸기 위해서다: enabledPlugins의 정규화가
    오늘 항등(_identity)이라는 사실에 기대면, 그 섹션에 마스킹이 도입되는 순간 훅을
    우회하는 자리 하나만 조용히 남는다.

    **넷째는 값이 문자열 안에 들어가 있어 세는 눈에 걸리지 않는다.** unrestorable_reasons의
    마켓플레이스 갈래는 레포 값의 source.source를 사유 문장에 **보간한다**
    (plugin_config.unrestorable_reason의 (a)·(b) 갈래). 레포에
    {"m": {"source": {"source": "X"}}}가 있으면 사유가 "'X' 출처로는 …"이 된다. 오늘
    안전한 근거는 둘이다 — 그 값도 masked[section]을 거치고(위와 같은 훅), 그리고
    extraKnownMarketplaces에는 도메인상 비밀이 없다. 나머지 두 섹션의 갈래는 값이 아니라
    **키**에서 뽑은 마켓플레이스 이름만 넣으므로 값이 실리지 않는다.
    **10.2의 사유 갈래를 늘릴 때 이 자리를 다시 셀 것** — pluginConfigs는 마스킹 대상
    섹션이라(_redact_configs) 그 갈래가 값을 보간하기 시작하면 성질이 달라진다.

    **최상위 status는 섹션 skip을 반영하지 않는다(의도).** 그 값은 "계획 수립을
    수행했는가"다 — 접힌 섹션이 있어도 나머지 섹션의 계획은 유효하고, 최상위를 skipped로
    접으면 마켓플레이스 등록처럼 멀쩡히 낼 수 있는 단계까지 함께 버려진다(9.3.6의 부분
    skip이 전체 skip으로 바뀐다). 그 대가로 **restore에서는 반대 방향이 위험하다**:
    installed_plugins.json 판정 불가로 두 섹션이 접힌 실행의 출력은
    {"status": "ok", "install": [], "disable_after_install": [], "config_keys": {}}이라
    소비자가 최상위만 읽으면 "복원할 것이 없습니다"로 보고하고 **조용히 아무것도
    복원하지 않는다.** 섹션 단위 사실은 sections[<섹션>]["status"]에만 있고, 소비자는
    그것을 **반드시 따로 읽어야 한다.**
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=held_state)
    sections = _plan_sections(local, repo, base, hooks, skipped)

    masked = {section: hooks[section]["normalize"](repo[section])
              for section in pc.SECTIONS}
    # 로컬 값도 **같은 훅**을 통과시킨다. compare_plugins.changed_detail이 양쪽을 둘 다
    # 정규화하는 것과 같은 규약이다 — 원본을 실으면 그 섹션에 마스킹이 도입될 때
    # 로컬 값만 마스킹 계층 전체를 우회하고, 예외도 빈 결과도 나지 않는다(6.1).
    # **싣는 자리와 비교하는 자리가 같은 값을 봐야 한다.** local_values의 페이로드만
    # 훅에 통과시키고 disable 판정은 원본으로 비교하면, 한쪽만 마스킹된 두 값이
    # value_command에 들어가 없어야 할 enable/disable이 **CLI 명령으로** 나간다.
    # 그래서 이 파일에는 **정규화를 거치지 않은 로컬 값을 꺼내 쓰는 자리가 없다** —
    # local을 그대로 넘기는 곳은 코어와 훅뿐이고, 그쪽은 스스로 정규화한다.
    local_masked = hooks["enabledPlugins"]["normalize"](local["enabledPlugins"])
    plugins = sections["enabledPlugins"]
    markets = sections["extraKnownMarketplaces"]
    configs = sections["pluginConfigs"]

    # 1단계 — 등록. always-known 다섯은 건너뛴다(등록이 무의미하거나 반드시 실패한다).
    to_register = [name for bucket in REGISTER_BUCKETS
                   for name in markets.get(bucket, [])
                   if name not in pc.ALWAYS_KNOWN]
    marketplace_add = [
        {"name": name,
         "arg": pc.marketplace_arg(masked["extraKnownMarketplaces"][name]),
         "reserved": name in pc.RESERVED_MARKETPLACE_NAMES}
        for name in to_register]

    # 2단계 — 설치. 3단계 — 값 맞추기. 부재는 여기 오지 않는다(레포에 있는 키만 본다).
    install = [k for bucket in INSTALL_BUCKETS for k in plugins.get(bucket, [])]
    install += [k for bucket in INSTALL_BUCKETS for k in configs.get(bucket, [])
                if k not in install]
    install = sorted(install)
    # **install의 절반은 "설치 직후"가 아니다.** enabledPlugins 경로의 키는 정의상 로컬에
    # 없으므로 설치 직후의 값 true가 맞지만, pluginConfigs 경로의 키는 이미 로컬에 설치돼
    # 있을 수 있다 — 그 섹션의 route_new는 "그 섹션에" 레포 전용인 키를 훑을 뿐 플러그인
    # 자체의 설치 여부와 무관하기 때문이다. 그래서 로컬에 값이 있으면 **그 값**을 쓰고,
    # 없을 때만 설치 직후의 true로 떨어진다. 상수 true를 넣으면 value_command가 지키라고
    # 받는 규칙("현재 상태와 다를 때만 낸다")을 유일한 호출부가 우회하고, 이미 꺼진
    # 플러그인에 disable이 나가 exit 1의 거짓 실패가 된다(enable/disable은 멱등이 아니다).
    disable_after_install = [
        k for k in install
        if k in masked["enabledPlugins"]
        and pc.value_command(local_masked.get(k, True),
                             masked["enabledPlugins"][k]) == "disable"]

    # 값을 맞춰야 하는 세 갈래에 양쪽 값을 실어 준다 — 케이스 8·9(repo_ahead·
    # both_changed)의 선택 뒤, 8.4의 값 보류 문구("레포 값을 보존합니다"), 그리고 설치
    # 직후의 3단계. SKILL.md가 value_command와 같은 규칙을 손으로 재구현하지 않게 하려는
    # 것이다 — 재구현하면 멱등이 아닌 명령을 같은 상태에 내어 거짓 실패를 양산한다.
    decided = sorted({k for bucket in ("repo_ahead", "both_changed", "value_held")
                      for k in plugins.get(bucket, [])} | set(install))

    return {
        "status": "ok",
        "sections": sections,
        "marketplace_add": marketplace_add,
        "skipped_always_known": sorted(
            name for bucket in REGISTER_BUCKETS for name in markets.get(bucket, [])
            if name in pc.ALWAYS_KNOWN),
        "install": install,
        "disable_after_install": disable_after_install,
        # 코어가 needs_secret으로 라우팅할 때 부른 것과 **같은 훅**으로 키 목록을 만든다.
        # 자유 함수(SECTION_SECRET_KEYS)를 따로 부르면 라우팅과 보고가 갈릴 수 있고,
        # 갈려도 증상이 없다 — 사용자는 되물어야 할 키를 하나 덜 받을 뿐이다.
        "config_keys": {k: hooks["pluginConfigs"]["secret_keys"](
            masked["pluginConfigs"][k])
            for k in configs.get("needs_secret", [])},
        "repo_values": {k: masked["enabledPlugins"][k] for k in decided
                        if k in masked["enabledPlugins"]},
        "local_values": {k: local_masked[k] for k in decided if k in local_masked},
        "depends_on": _install_dependencies(install),
        # 훅 묶음의 reason을 쓴다 — 자유 함수 unrestorable_reason에 repo를 따로 넘기면
        # 판정(restorable)과 사유가 **다른 repo**를 볼 수 있고 양쪽 다 무증상이다
        # (Task 6 quality review I2). build_hooks가 둘에 같은 repo를 닫아 준다.
        "unrestorable_reasons": {
            k: hooks[section]["reason"](k, masked[section].get(k))
            for section in pc.SECTIONS
            for k in sections[section].get("unrestorable", [])},
    }


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    else:
        print("사용: plan_plugins.py plan <레포의 plugins.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = runner()
    # collect_plugins·compare_plugins와 같은 튜플을 쓴다. 갈리면 한쪽만 traceback으로 죽는다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 복원 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

`tests/test_plugin_scripts.py` 상단에 `import keyed_sync as ks  # noqa: E402`를 더한다(버킷 게이트가 쓴다).

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `INSTALL_BUCKETS`에 `"value_held"`를 더하기 → **H3 항목이 두 번 설치 목록에 든다.** 잡는 테스트가 없으면 보강한다
- `install`에서 `action_held` 키가 새어 들어오도록 `plugins.get("action_held", [])`를 더하기 → 행동 보류 테스트가 잡아야 한다
- `to_register`의 `if name not in pc.ALWAYS_KNOWN`을 지우기 → always-known 테스트가 잡아야 한다
- `reserved` 계산을 `False` 고정으로 바꾸기 → 예약 이름 테스트가 잡아야 한다
- `disable_after_install`의 `pc.value_command(True, ...)`를 `pc.value_command(False, ...)`로 바꾸기 → **레포가 true인 항목까지 enable 대상이 된다.** disable 테스트가 잡아야 한다
- `masked["enabledPlugins"][k]` 대신 `repo["enabledPlugins"][k]`(원본)를 쓰기 → `enabledPlugins`는 항등 정규화라 **통과한다.** 이것은 알고 받아들이는 무해한 변조다
- `config_keys`를 `local` 기준으로 계산하기 → `test_plan_routes_new_repo_entries_by_secret_need`가 잡아야 한다. **비밀 미유출 테스트는 잡지 못한다** — `_config_secret_keys`가 돌려주는 것은 값이 아니라 **키 이름**뿐이라 `local`로 바꿔도 평문이 실릴 자리가 없다. 실제로 잡히는 이유는 그 키가 로컬에 아예 없어서다(직접 색인이면 KeyError, 방어적으로 쓰면 `config_keys == {}`)
- `depends_on`에서 `ALWAYS_KNOWN` 제외를 지우기 → 그 테스트가 잡아야 한다
- 버킷 화이트리스트를 `{k: v for k, v in plan.items() if k in NINE}`로 좁히기 → 11버킷 게이트가 잡아야 한다

**부재·범위·정렬·값 페이로드·base 배선** — 이 다섯은 "단정이 참인데 그 참이 가드에서 나오지 않는" 자리라 위 목록만으로는 전부 SURVIVED한다. 반드시 함께 돌린다.

- `disable_after_install`의 `if k in masked["enabledPlugins"]` 가드를 지우고 `masked["enabledPlugins"].get(k, False)`로 색인하기(= **부재를 false 취급**) → `test_plan_installs_a_plugin_that_only_plugin_configs_names`가 잡아야 한다. `test_plan_never_disables_a_key_absent_from_the_repo`는 **잡지 못한다** — 그 fixture의 키가 `install`에 들어오지 않기 때문이다
- `disable_after_install`의 `for k in install`을 `for k in masked["enabledPlugins"]`로 넓히기 → `test_plan_disables_nothing_outside_the_install_list`가 잡아야 한다
- `install = sorted(install)`의 `sorted`를 지우기 → `test_plan_sorts_install_across_both_contributing_sections`가 잡아야 한다
- `decided = []` / `"local_values"`를 `{}` 고정 / `"repo_values"`를 `local["enabledPlugins"]`에서 꺼내기 → 셋 다 `test_plan_carries_both_values_for_every_decided_key`가 **각각** 잡아야 한다(그러려면 세 갈래가 실제로 채워지고 같은 키의 양쪽 값이 달라야 한다)
- `_plan_sections`의 base 인자를 `None` 고정 / `build_plan`의 `pc.parse_base(...)`를 `None` 고정 → `test_plan_reads_base_of_each_section_from_that_section`과 `test_plan_carries_both_values_for_every_decided_key`가 잡아야 한다
- `base.get(section, {})`를 `base.get("enabledPlugins", {})`로 바꾸기(= **엉뚱한 섹션**) → `test_plan_reads_base_of_each_section_from_that_section`이 잡아야 한다. 세 섹션의 base 키가 서로 달라야만 잡힌다

**로컬 상태·예외 흡수·최상위 status·사유 배선** — quality review가 SURVIVED로 실측한 자리다. 반드시 함께 돌린다.

- `disable_after_install`의 `local_masked.get(k, True)`를 상수 `True`로 되돌리기 → `test_plan_does_not_disable_a_plugin_that_is_already_off_locally`가 잡아야 한다. 부재의 기본값을 `False`로 접는 반대 방향의 잘못된 fix도 함께 돌린다 — 그쪽은 disable 테스트 셋이 잡는다. **두 방향을 다 돌려야** "부재는 `true`"와 "로컬에 있으면 그 값"이 각각 고정된 것이 된다
- `main()`의 except 튜플에서 `ValueError`를 빼기 → `test_plan_cli_skips_when_normalize_drops_a_key`가 잡아야 한다. 형제 둘과 같은 튜플을 쓴다는 주석의 주장이 그 항목에 대해 무보증이었던 자리다
- 최상위 `"status": "ok"`를 `"skipped" if skipped else "ok"`로 바꾸기(= 섹션 skip을 반영) → `test_plan_skips_plugin_sections_when_auto_flags_are_unavailable`이 잡아야 한다. **두 의미 중 어느 쪽이 계약인지 정하는 것**이 이 변조의 요지다 — 정하지 않으면 SKILL.md가 최상위 `ok`만 읽고 "복원할 것이 없습니다"로 조용히 끝낸다
- `unrestorable_reasons`의 `for section in pc.SECTIONS`를 `("enabledPlugins",)`로 좁히기 / `reason`에 넘기는 `value` 인자를 `None`으로 고정하기 → 둘 다 `test_plan_gives_reasons_for_unrestorable_marketplaces`가 잡아야 한다. 플러그인 갈래는 `value`를 **아예 보지 않으므로**(키만 본다) 마켓플레이스 케이스가 없으면 둘 다 SURVIVED한다
- `decided = sorted(...)`의 `sorted`를 `list`로 바꾸기 → `test_plan_carries_both_values_for_every_decided_key`가 잡아야 한다. **다만 결정적이지 않다** — `decided`는 set이라 정렬 전 순서가 이름이 아니라 **문자열 해시 순서**로 정해지고, 그것은 `PYTHONHASHSEED`에 끌려간다. 원소 수가 n일 때 약 1 - 1/n! 확률로 잡히므로 그 fixture는 decided를 **여섯**으로 채운다(1/720). 실측: 4원소 58/60, 6원소 60/60(`PYTHONHASHSEED` 1..60)
- CLI의 `len(args) == 2` 검사를 지우기 / `args[0] == "plan"` 검사**만** 지우기 → 둘 다 `test_plan_cli_rejects_wrong_invocations`가 잡아야 한다. 개수 검사 쪽은 **종료 코드만 보면 잡히지 않는다** — 처리되지 않은 `IndexError`도 1로 끝나므로 stderr의 usage를 함께 봐야 한다. 이름 검사 쪽은 **인자가 정확히 둘인데 서브커맨드가 틀린** 케이스(`["bogus", "x"]`)가 parametrize에 있어야만 잡힌다 — 나머지 넷은 개수만으로도 걸리므로, 없으면 `plan_plugins.py bogus <경로>`가 usage 없이 계획을 낸다
- `"local_values"`를 정규화 전 원본(`local["enabledPlugins"]`)에서 꺼내기 / **disable 판정의 로컬 쪽을 `local_masked` 대신 원본으로 되돌리기** / `REGISTER_BUCKETS`에서 `"needs_secret"`을 빼기 / `_install_dependencies`의 `marketplace is not None` 가드를 지우기 → **넷 다 통과한다.** 앞의 둘은 `enabledPlugins`의 정규화가 항등(`_identity`)이라 동작이 같고, 셋째는 그 섹션의 `secret_keys`가 `_no_secrets`라 `needs_secret`이 항상 비며, 넷째는 `install ⊆ restorable`이라 도달할 수 없는 방어다. 알고 받아들이는 무해한 변조이고, 그래서 넷의 근거는 **주석과 docstring으로만** 고정한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py \
        plugins/claude-sync/lib/plugin_config.py plugins/claude-sync/tests
git commit -m "feat(restore): plan_plugins.py plan — 섹션별 복원 계획과 실행 보조"
```

---

### Task 10: `plan_plugins.py apply-base` — 선택 반영과 `plugins-held.json` 소유

**근거:** spec 9.3.7, 9.3.4, 9.3.5, 7.3, 6.4, 5.3

**"유지"의 구현은 케이스에 따라 다르다. 한 조작이 아니다.**

| 케이스 | 선택 | base 조작 | 다음 백업의 착지 |
|---|---|---|---|
| 4·5 (`local_stale`) | 유지 | **`keep_stale` — base에서 그 키를 삭제** | 케이스 1(로컬 신규) → push |
| 8·9 (`repo_ahead`/`both_changed`) | 로컬 유지 | **`keep_local` — `base[k] ← 레포 값`** | 케이스 7(로컬만 변경) → push |

문언대로 케이스 4·5에 `base[k] = repo.get(k)`를 쓰면 base에 `null`이 들어가 **다시 케이스 4**가 되고, 사용자의 선택이 아무 효과가 없이 영원히 다시 묻는다.

**H3 해제는 두 조각이다.** 해제 표식만 남기면 base에 그 키가 없어(5.3) **케이스 9로 착지**한다 — 약속과 반대다. 그래서 해제와 **동시에** `keep_local`을 적용해 착지를 케이스 7로 만든다.

**`apply-base`는 `.tmp`+rename 규칙에서 제외된다.** 앞에 레포 쓰기가 없으므로 rename 트리거가 영영 오지 않아 게이트가 언제나 거짓이 되고, restore 경로의 base가 전혀 전진하지 않는다.

**선택 결과 JSON은 섹션 키로 중첩한다.** `enabledPlugins`와 `pluginConfigs`는 키가 같은 문자열이므로 평면 목록이면 한쪽 선택이 다른 섹션의 base까지 조작한다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py` (`apply_base`·`read_choices`·`main`)
- Modify: `plugins/claude-sync/lib/plugin_config.py` (`choice_list`·`next_held_state`·`write_held_state`)
- Modify: `plugins/claude-sync/tests/test_plugin_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_scripts.py` 끝에 추가한다.

```python
EMPTY_CHOICES = {section: {"keep_stale": [], "keep_local": []} for section in pc.SECTIONS}


def apply_base(tmp_path, choices=None, local=None, repo=None, base=None,
               installed=None, held=None, staging="staging"):
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    merged = json.loads(json.dumps(EMPTY_CHOICES))
    for section, values in (choices or {}).items():
        merged.setdefault(section, {}).update(values)
    result = plan_plugins.apply_base(
        os.path.join(repo_dir, pc.BACKUP_RELPATH),
        str(tmp_path / staging), merged,
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "plugins-held.json"),
        base_dir=write_base_blob(tmp_path, base))
    return result, staged_doc(str(tmp_path / staging))


def test_apply_base_writes_the_final_name_directly(tmp_path):
    """9.3.7 — .tmp+rename을 적용하면 rename 트리거가 없어 base가 영영 전진하지 않는다."""
    _, doc = apply_base(tmp_path, local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": True}})
    assert doc["enabledPlugins"] == {"p@m": True}
    assert not os.path.exists(os.path.join(str(tmp_path / "staging"),
                                           pc.BACKUP_RELPATH + ".tmp"))


def test_keep_stale_forgets_the_history_so_the_entry_returns(tmp_path):
    """9.3.4 케이스 4·5 — base에서 지워야 다음 백업이 케이스 1로 push한다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_stale": ["X@m"]}},
                        local={"enabledPlugins": {"X@m": True}},
                        repo={"enabledPlugins": {}},
                        base={"enabledPlugins": {"X@m": True}})
    assert "X@m" not in doc["enabledPlugins"]


def test_keep_local_records_the_repo_value_so_the_landing_is_case7(tmp_path):
    """9.3.4 케이스 8·9 — base[k] ← 레포 값. base에서 지우면 케이스 1이 되어 뜻이 달라진다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_local": ["p@m"]}},
                        local={"enabledPlugins": {"p@m": False}},
                        repo={"enabledPlugins": {"p@m": True}},
                        base={"enabledPlugins": {"p@m": True}})
    assert doc["enabledPlugins"]["p@m"] is True


def test_choices_are_nested_by_section(tmp_path):
    """9.3.7 — 평면 목록이면 한쪽 선택이 다른 섹션의 base를 조작한다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_stale": ["p@m"]}},
                        local={"enabledPlugins": {"p@m": True},
                               "pluginConfigs": {"p@m": {"options": {}}}},
                        repo={"enabledPlugins": {}, "pluginConfigs": {}},
                        base={"enabledPlugins": {"p@m": True},
                              "pluginConfigs": {"p@m": {"options": {}}}})
    assert "p@m" not in doc["enabledPlugins"]
    assert "p@m" in doc["pluginConfigs"]


def test_value_held_keys_are_removed_from_base_without_any_override(tmp_path):
    """5.3 — 보류가 있는 어댑터는 restore 경로에서 스스로 value_held를 넘겨야 한다.

    넘기지 않으면 보류 키가 base에 얼어붙고, 보류가 풀리는 순간 케이스 3(삭제)이 난다.
    """
    _, doc = apply_base(tmp_path,
                        local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
                        base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in doc["enabledPlugins"]


def test_release_lifts_the_hold_and_lands_on_case7(tmp_path):
    """7.3 — 해제만 하면 base에 키가 없어 케이스 9로 떨어진다. 약속과 반대다."""
    held_path = str(tmp_path / "plugins-held.json")
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"release": ["p@m"]}},
                        local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
                        held=held_path)
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # keep_local이 동시에 걸렸다
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == ["p@m"]


def test_release_entry_is_cleared_once_the_repo_value_is_boolean(tmp_path):
    """조건이 사라지면 항목도 사라진다 — H4의 지문 규칙과 같은 형태다."""
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}}, f)
    apply_base(tmp_path, local={"enabledPlugins": {"p@m": True}},
               repo={"enabledPlugins": {"p@m": True}}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == []


def test_declined_config_is_recorded_with_the_masked_repo_fingerprint(tmp_path):
    """6.4 — 로컬 값이나 사용자 입력값을 지문에 넣으면 영영 매치되지 않는다."""
    held_path = str(tmp_path / "plugins-held.json")
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {
            "delta@m": pc.value_fingerprint(masked["delta@m"])}


def test_configured_entry_is_dropped_from_the_held_file(tmp_path):
    """6.4 — 사용자가 마음을 바꿔 값을 입력하면 그 항목을 파일에서 지운다."""
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {"delta@m": "0" * 64},
                   "release": {"enabledPlugins": []}}, f)
    apply_base(tmp_path, choices={"pluginConfigs": {"configured": ["delta@m"]}},
               local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {}


def test_held_file_is_not_written_when_it_could_not_be_read(tmp_path):
    """깨진 파일을 빈 상태로 덮으면 사용자의 보류 선택이 조용히 사라진다."""
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        f.write("{not json")
    out, _ = apply_base(tmp_path, local={}, repo={}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert f.read() == "{not json"
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"


def test_apply_base_ignores_unknown_and_non_string_choice_entries(tmp_path):
    """선택 결과 JSON은 사용자 대화에서 만들어진다 — 형태가 어긋나도 죽지 않는다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_stale": [None, 3, "p@m"]},
                                 "nonsense": {"keep_local": ["x"]}},
                        local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {}},
                        base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in doc["enabledPlugins"]


def test_failed_restore_does_not_advance_the_base(tmp_path):
    """10.4 — 로컬이 그 값에 동의하지 않았으므로 base가 전진하면 안 된다.

    "복원을 시도한 목록"이 아니라 **복원 후 다시 읽은 로컬**을 넘기는 것이 그 안전장치다.
    """
    _, doc = apply_base(tmp_path, local={"enabledPlugins": {}},
                        repo={"enabledPlugins": {"failed@m": True}})
    assert "failed@m" not in doc["enabledPlugins"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_scripts.py -q`
기대: 신규 테스트 FAIL (`AttributeError: module 'plan_plugins' has no attribute 'apply_base'`)

- [ ] **Step 3: 구현**

`lib/plugin_config.py`에 셋을 더한다.

```python
def choice_list(choices, section, key):
    """선택 결과 JSON에서 문자열 목록만 꺼낸다.

    이 JSON은 SKILL.md의 대화가 만든다 — 형태가 어긋나도 restore 전체를 세우지 않는다.
    **섹션 키로 중첩한다**(9.3.7): enabledPlugins와 pluginConfigs는 키가 같은 문자열이라
    평면 목록이면 어느 섹션의 선택인지 구별할 수 없고, 한쪽 선택이 다른 섹션의 base까지
    조작한다.
    """
    section_choices = choices.get(section)
    if not isinstance(section_choices, dict):
        return []
    values = section_choices.get(key)
    return [v for v in values if isinstance(v, str)] if isinstance(values, list) else []


def next_held_state(previous, repo, choices):
    """apply-base가 기록할 다음 보류 상태 (6.4·7.3).

    declined — 이번에 값을 입력한 항목(configured)은 빼고 이번에 건너뛴 항목을 더한다.
               레포에 없는 항목은 정리한다. 지문은 **마스킹된 레포 값**으로 만든다.
    release  — 레포 값이 불리언이 되었거나 키가 사라진 항목을 정리한다. 조건이 사라지면
               항목도 사라진다(H4의 지문 규칙과 같은 형태).

    configured가 필요한 이유: 사용자가 마음을 바꿔 값을 입력했는데 항목이 남아 있으면
    지문이 그대로 매치되어 **영영 보류 상태로 남는다** — 6.4가 "그때 항목을 파일에서
    지운다"고 정한 자리다.
    """
    masked = SECTION_NORMALIZE["pluginConfigs"](repo.get("pluginConfigs", {}))
    configured = set(choice_list(choices, "pluginConfigs", "configured"))
    declined = {key: value for key, value in previous["pluginConfigs"].items()
                if key in masked and key not in configured}
    for key in choice_list(choices, "pluginConfigs", "declined"):
        if key in masked:
            declined[key] = value_fingerprint(masked[key])

    plugins = repo.get("enabledPlugins", {})
    def still_extended(key):
        return key in plugins and not isinstance(plugins[key], bool)
    released = [key for key in previous["release"]["enabledPlugins"] if still_extended(key)]
    released += [key for key in choice_list(choices, "enabledPlugins", "release")
                 if still_extended(key) and key not in released]
    return {"pluginConfigs": declined, "release": {"enabledPlugins": sorted(released)}}


def write_held_state(state, held_path=None):
    """보류 상태를 기록한다. **이 함수의 호출자는 plan_plugins.py apply-base 하나뿐이다.**

    다른 스크립트가 쓰면 소유자가 둘이 되고, 그러면 backup이 사용자의 선택을 덮어쓴다.
    ~/.claude/.sync-state/는 iter_synced_relpaths가 열거하지 않으므로 이 파일은
    동기화 대상이 아니다 — 보류 선택이 타 기기로 번지지 않는다(기기별 선택이 의도다).
    """
    path = DEFAULT_HELD if held_path is None else held_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": HELD_SCHEMA_VERSION,
               "pluginConfigs": state["pluginConfigs"],
               "release": state["release"]}
    ks.dump_json(payload, path)
```

`skills/sync-restore/scripts/plan_plugins.py`에 `apply_base`·`read_choices`를 더하고 `main`을 확장한다. 모듈 docstring의 사용법에도 서브명령을 더한다.

```python
def apply_base(backup_path, staging_dir, choices, settings_path=None, installed_path=None,
               held_path=None, base_dir=ss.BASE_DIR):
    """복원 후 로컬 기준으로 다음 base를 계산하고 override 셋을 적용해 스테이징에 쓴다.

    ① next_base(복원 후 로컬, 이전 base, 레포 값)  — 정규화는 코어가 한다
    ② keep_stale(케이스 4·5의 "유지")   → base에서 키 삭제  (그 이력은 잊는다)
    ③ keep_local(케이스 8·9의 "로컬 유지") → base[k] ← 레포 값 (그 이력은 잊는다)
    ④ release(H3 탈출구) → ②③과 별개로 보류를 풀고 **동시에 ③을 적용한다**

    ④가 ③을 함께 걸지 않으면 base에 그 키가 없어(5.3) 다음 백업이 케이스 9로 떨어지고
    레포 값이 그대로 남는다 — 약속과 반대다. ③을 함께 걸면 same(repo, base)이므로
    케이스 7(로컬만 변경) → 로컬 값 push → 레포 값이 불리언 → H3 자연 해제로 이어진다.

    **value_held를 스스로 계산해 next_base에 넘긴다.** merge 경로와 달리 여기서는
    아무도 대신 계산해 주지 않는다. 넘기지 않으면 보류 키가 base에 얼어붙어, 보류가
    풀리는 순간 케이스 3(삭제)이 난다.

    **레포 매핑 전체를 세 번째 인자로 넘긴다.** next_base의 계약은 "local과 merged가
    같은 값을 갖는 키만 전진"이므로, 그 교집합이 곧 "실제로 복원에 성공한 항목"이 된다 —
    실패했거나 사용자가 건너뛴 항목은 로컬에 없으니 자동으로 빠진다(10.4).
    여기에 "복원을 시도한 목록"을 넘기면 그 안전장치가 사라진다.

    **파일 두 개를 쓰는 순서가 계약이다.** 스테이징(base) 먼저, 보류 파일 나중.
    반대로 하면 release가 기록된 뒤 base 쓰기가 실패했을 때 H3가 풀린 채로 base에 키가
    없어 다음 백업이 케이스 9로 떨어진다. 이 순서에서는 보류 파일 쓰기가 실패해도
    "다시 묻는다"에 그친다.
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)

    # 새 release가 반영된 상태로 훅을 만든다 — 그래야 해제된 키가 value_held에서 빠지고
    # next_base가 그 키를 base에 남긴다.
    next_held = pc.next_held_state(held_state, repo, choices)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=next_held)

    previous_base = base or {}
    doc, report = {}, {}
    for section in pc.SECTIONS:
        if section in skipped:
            doc[section] = previous_base.get(section, {})
            report[section] = pc.skipped_section(skipped[section])
            continue
        normalize = hooks[section]["normalize"]
        masked = normalize(repo[section])
        # 손으로 조립하지 않는다 — hold는 정규화된 입력을 받고 (local, repo) 순서가
        # 뒤집히면 예외도 빈 결과도 없이 판정이 반대로 선다(Task 6 quality review I1).
        value_held = pc.value_held_for(section, hooks, local[section], repo[section])
        nb = ks.next_base(local[section],
                          None if base is None else base.get(section, {}),
                          repo[section],
                          normalize=normalize, value_held=value_held)
        stale = pc.choice_list(choices, section, "keep_stale")
        for key in stale:
            nb.pop(key, None)
        keep_local = list(pc.choice_list(choices, section, "keep_local"))
        if section == "enabledPlugins":
            keep_local += [key for key in next_held["release"]["enabledPlugins"]
                           if key not in keep_local]
        kept_local = []
        for key in keep_local:
            if key in masked:
                nb[key] = masked[key]
                kept_local.append(key)
        doc[section] = nb
        report[section] = {"status": "ok", "kept_stale": stale, "kept_local": kept_local,
                           "base_keys": sorted(nb)}

    os.makedirs(staging_dir, exist_ok=True)
    pc.dump_backup(doc, os.path.join(staging_dir, pc.BACKUP_RELPATH))
    # 보류 파일을 읽지 못했다면 쓰지 않는다 — 빈 상태로 덮으면 사용자의 선택이 조용히
    # 사라진다. 그 경우 SKILL.md가 파일을 지울 경로를 안내한다(6.4).
    if "pluginConfigs" not in skipped:
        pc.write_held_state(next_held, held_path)
    return {"status": "ok", "sections": report}


def read_choices(path):
    """섹션으로 중첩된 선택 결과. **비밀 값은 담기지 않는다.**

    사용자가 입력한 pluginConfigs 값은 여기 실리지 않고 `install --config`로 곧바로
    전달된다 — 담으면 임시 파일에 평문 비밀이 남는다(9.3.7).
    """
    with open(path, "rb") as f:
        data = json.loads(f.read())
    if not isinstance(data, dict):
        raise ValueError("선택 결과 JSON의 최상위가 객체가 아님: %s" % path)
    return data
```

`main`의 분기를 넓힌다.

```python
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    elif len(args) == 4 and args[0] == "apply-base":
        runner = lambda: apply_base(args[1], args[2], read_choices(args[3]))  # noqa: E731
    else:
        print("사용: plan_plugins.py plan <레포의 plugins.json 경로>", file=sys.stderr)
        print("      plan_plugins.py apply-base <레포의 plugins.json 경로>"
              " <스테이징 디렉토리> <선택 결과 JSON 경로>", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `value_held=value_held`를 지우기(코어 기본값 `frozenset()`) → 보류 키 base 제거 테스트가 잡아야 한다. **MCP 어댑터가 구조적으로 검증하지 못하는 경로다**
- release의 `keep_local` 동시 적용을 지우기 → 케이스 7 착지 테스트가 잡아야 한다
- `keep_stale`을 `nb[key] = masked.get(key)`로 바꾸기 → base에 `None`이 들어가 **영원히 다시 묻는** 상태가 된다. `keep_stale` 테스트가 잡아야 한다
- `next_held_state`의 `still_extended` 정리를 지우기 → release 정리 테스트가 잡아야 한다
- `configured` 차감을 지우기 → 그 테스트가 잡아야 한다
- 지문 대상을 `masked` 대신 `repo`(원본)로 바꾸기 → `pluginConfigs`는 마스킹이 값을 바꾸므로 지문 테스트가 잡아야 한다
- `if "pluginConfigs" not in skipped` 가드를 지우기 → 깨진 파일 보존 테스트가 잡아야 한다
- 두 파일의 쓰기 순서를 맞바꾸기 → **어떤 테스트도 잡지 못한다.** 알고 받아들이는 구멍이고, 근거는 docstring에 남긴다
- `pc.dump_backup(doc, ...)`의 경로에 `.tmp`를 붙이기 → 직접 쓰기 테스트가 잡아야 한다
- `choice_list`의 `isinstance(v, str)` 필터를 지우기 → 형태 어긋남 테스트가 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py \
        plugins/claude-sync/lib/plugin_config.py plugins/claude-sync/tests/test_plugin_scripts.py
git commit -m "feat(restore): apply-base — 선택 override 넷과 plugins-held.json 소유"
```

---

### Task 11: 상태 기계 — 보류의 다회차 커버리지

**근거:** spec 7.3, 5.3, 14.2 #4 / plan ① Task 9 quality review I2

**지금 보류의 상태 기계 커버리지는 0이다.** 열 시나리오 어디에도 보류 키가 없다. 실측으로 확인된 것: 가짜 플러그인 어댑터를 붙이고 **코어의 "보류 키는 레포 값을 그대로 싣는다"를 지워도 20 passed 그대로**였다.

**왜 다회차여야 하는가.** 단발 테스트가 잡는 것은 1회차다. *"레포가 그 키를 잃은 채로 고정점에 든다"* 는 다회차 결과를 보는 것이 그 파일의 존재 이유이고, 그 결함 계열이 정확히 이 개정이 없애려던 "타 기기 항목의 전멸"이다. 게다가 7.3이 스스로 경고한 **H3 탈출구의 착지 지점**은 정의상 회차 사이에 상태가 변해야 표현되는데, 현재 `repeat_backup`은 회차마다 같은 `local`과 같은 `hold`를 넘기므로 **구조적으로 표현할 수 없다.**

**`ADAPTERS`에 한 줄만 더하면 된다는 것은 사실이 아니다.** plan ① Task 9 리뷰가 실측으로 반증했다 — `pluginConfigs`·`extraKnownMarketplaces`는 그대로 돌지만(20 passed), `enabledPlugins`는 **불리언이든 배열이든 돌지 않는다**(각각 3 failed / 5 failed). 불리언은 값이 둘뿐이라 케이스 9를 표현할 수 없고, 배열이면 H3로 전부 보류된다.

**보류 훅은 테스트 더블이 아니라 실제 어댑터의 것을 쓴다.** 가짜 훅을 쓰면 `_make_hold`의 회귀를 이 파일이 하나도 잡지 못한다.

**Files:**
- Modify: `plugins/claude-sync/tests/test_mcp_state_machine.py`

- [ ] **Step 1: 실패하는 test 작성**

파일 상단의 docstring과 `Adapter`·`ADAPTERS`·`repeat_backup`을 교체하고 보류 시나리오를 더한다.

```python
"""backup을 반복 적용했을 때 고정점에 도달하는지 검증한다.

단발 호출 테스트는 상태 기계 결함을 잡지 못한다. 이전 설계의 Critical 결함
("base ← 레포 파일 전체")은 판정표를 100% 덮은 테스트를 전부 통과했지만,
2회차 백업에서 타 기기의 서버를 전멸시켰다.

**어댑터와 값 픽스처를 주입받는다.** 열 개의 판정표 시나리오는 세 어댑터가 공유한다 —
MCP, 그리고 플러그인의 두 섹션이다.

**enabledPlugins는 이 시나리오 집합을 쓸 수 없다.** 케이스 9가 서로 다른 값 셋을
요구하는데 불리언은 값이 둘뿐이고, 값을 확장 포맷으로 늘리면 H3가 전부 보류해 판정표를
타지 않는다. 그 섹션은 아래 **보류 시나리오**가 맡는다 — 보류의 진입·유지·이탈은
회차 사이에 상태가 변해야 표현되므로 애초에 다른 하네스가 필요하다.

(파일 이름이 여전히 test_mcp_state_machine.py인 것은 앵커를 늘리지 않기 위해서다.
내용은 더 이상 MCP 전용이 아니다.)
"""
import pytest

import keyed_sync as ks
import mcp_config as mc
import plugin_config as pc


class Adapter:
    """상태 기계 테스트가 어댑터에 요구하는 최소 표면.

    merge(local, repo, base)와 next_base(local, base, merged)를 **위치 인자 셋**으로
    부른다 — normalize·hold는 어댑터가 클로저로 닫아 넣는다(spec 5.5의 위치 인자 순서).
    merge는 병합 결과를 merged_key에, 다음 base를 "next_base"에 담아 돌려줘야 한다.

    values는 (A, B, ORIG)이고 **정규화 후에도 셋이 서로 달라야 한다.** 케이스 9가
    local·repo·base 세 값이 모두 다를 것을 요구하기 때문이다. 마스킹이 값을 뭉개는
    섹션(pluginConfigs)에서는 **키 이름으로** 값을 갈라야 한다 — 값만 다르게 두면
    정규화 후 셋이 같아져 케이스 9가 조용히 케이스 6이 된다.
    """

    def __init__(self, name, merge, next_base, values, merged_key="servers", normalize=None):
        self.name, self.merge, self.next_base = name, merge, next_base
        self.merged_key = merged_key
        self.A, self.B, self.ORIG = values
        self.normalize = normalize or (lambda mapping: mapping)
        one = lambda value: self.normalize({"k": value})["k"]  # noqa: E731
        pairs = ((self.A, self.B), (self.B, self.ORIG), (self.A, self.ORIG))
        assert not any(ks.same(one(x), one(y)) for x, y in pairs), (
            "%s: A·B·ORIG가 정규화 후에도 서로 달라야 한다 — 케이스 9를 표현할 수 없다"
            % name)


def plugin_adapter(section, values, hold=None):
    """플러그인 한 섹션을 상태 기계 하네스에 맞춘다.

    hold를 주면 그것을 쓰고, 주지 않으면 보류 없음이다 — 판정표 시나리오는 보류가 없는
    상태를 전제한다(보류 키는 판정표를 타지 않는다).
    next_base가 value_held를 **스스로 계산해 넘기는 것**이 restore 경로의 계약이다
    (plan_plugins.apply_base와 같은 형태). 넘기지 않으면 보류 키가 base에 얼어붙는다.
    """
    normalize = pc.SECTION_NORMALIZE[section]
    held = hold if hold is not None else ks.no_hold

    def merge(local, repo, base):
        return ks.merge(local, repo, base, normalize=normalize, hold=held)

    def next_base(local, base, merged):
        value_held = set(held(normalize(local), normalize(merged))["value"])
        return ks.next_base(local, base, merged, normalize=normalize,
                            value_held=value_held)

    return Adapter("plugins:%s" % section, merge, next_base, values,
                   merged_key="merged", normalize=normalize)


ADAPTERS = [
    Adapter("mcp", mc.merge, mc.next_base,
            ({"command": "a"}, {"command": "b"}, {"command": "o"})),
    plugin_adapter("extraKnownMarketplaces",
                   ({"source": {"source": "github", "repo": "o/a"}},
                    {"source": {"source": "github", "repo": "o/b"}},
                    {"source": {"source": "github", "repo": "o/orig"}})),
    # 값이 아니라 **키 이름**으로 셋을 가른다 — redact가 값을 전부 SENTINEL로 만들므로
    # 값만 다르게 두면 정규화 후 셋이 같아진다.
    plugin_adapter("pluginConfigs",
                   ({"options": {"ka": "x"}}, {"options": {"kb": "x"}},
                    {"options": {"ko": "x"}})),
]


def test_adapters_cover_every_section_that_can_run_the_decision_table():
    """어느 하나가 빠지면 그 섹션에서 판정표가 검증되지 않는다.

    enabledPlugins가 없는 것은 의도다 — 값이 둘뿐이라 케이스 9를 표현할 수 없다.
    그 섹션은 아래 보류 시나리오가 맡는다.
    """
    assert {adapter.name for adapter in ADAPTERS} == {
        "mcp", "plugins:extraKnownMarketplaces", "plugins:pluginConfigs"}
```

`repeat_backup`에 회차별 오버라이드 훅을 더한다.

```python
def repeat_backup(adapter, local, repo, base, rounds=3, before_round=None):
    """같은 로컬로 backup을 rounds회 반복하고 매 회차의 (보고, 레포, base)를 모은다.

    before_round(index, local, repo, base) -> (local, repo, base) 를 주면 그 회차 **직전에**
    셋을 갈아끼운다. 보류 상태(hold 클로저가 읽는 dict)도 여기서 바꾼다.

    이 훅이 없으면 보류의 **이탈**을 표현할 수 없다 — 회차마다 같은 local과 같은 hold를
    넘기게 되므로, 7.3이 경고한 "해제 후 착지"(케이스 9가 아니라 케이스 7이어야 한다)가
    정의상 표현 불가능하다.
    """
    snapshots = []
    exclude = (adapter.merged_key, "next_base")
    for index in range(rounds):
        if before_round is not None:
            local, repo, base = before_round(index, local, repo, base)
        result, repo, base = backup_round(adapter, local, repo, base)
        report = {k: v for k, v in result.items() if k not in exclude}
        snapshots.append((report, repo, base))
    return snapshots
```

파일 끝에 보류 시나리오를 더한다.

```python
# ---------------------------------------------------------------- 보류 시나리오
#
# 위 열 개는 보류가 **없는** 상태의 판정표다. 아래는 보류가 걸린 키가 회차를 넘어
# 어떻게 움직이는지를 본다 — 진입해서 유지될 때, 이탈할 때, 그리고 보류 중에 레포에서
# 사라졌을 때. 셋 다 다회차가 아니면 표현되지 않는다.

def held_state(released=()):
    return {"pluginConfigs": {}, "release": {"enabledPlugins": sorted(released)}}


def live_hold(section, state):
    """**실제 어댑터의 hold**를 회차마다 현재 상태로 다시 만든다.

    테스트 더블을 쓰면 _make_hold의 회귀를 이 파일이 하나도 잡지 못한다.
    state는 before_round가 바꾼다 — 그것이 보류의 진입·이탈이다.
    """
    def hold(local, repo):
        hooks = pc.build_hooks({section: local}, {section: repo},
                               auto_ids=state["auto_ids"], held_state=state["held"])
        return hooks[section]["hold"](local, repo)
    return hold


def enabled_adapter(state):
    """enabledPlugins 전용 값 도메인 — 불리언 둘과 확장 포맷 하나."""
    return plugin_adapter("enabledPlugins", (True, False, ["1.0.0"]),
                          hold=live_hold("enabledPlugins", state))


def test_h3_hold_preserves_the_repo_value_across_rounds():
    """보류 유지 — 레포의 버전 제약이 회차를 거쳐도 true로 덮이지 않는다.

    코어의 "보류 키는 레포 값을 그대로 싣는다"를 지우면 여기서 걸린다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)
    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {})
    for report, repo, base in snapshots:
        assert repo["p@m"] == ["1.0.0"]
        assert report["held"] == ["p@m"]
        assert report["deleted"] == [] and report["conflicts"] == []
        assert "p@m" not in base            # 값 보류 키는 base에서 제거된다 (5.3)
    assert_fixed_point_from_second_round(snapshots)


def test_h3_release_lands_on_case7_not_case9():
    """보류 해제 후 착지 — 7.3이 스스로 경고한 자리다.

    해제만 하면 base에 그 키가 없어 케이스 9로 떨어지고 레포 값이 그대로 남는다.
    apply-base가 해제와 **동시에** keep_local(base[k] ← 레포 값)을 걸어야 케이스 7이 되고,
    그때서야 로컬 값이 push되어 레포 값이 불리언이 되고 H3가 자연 해제된다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 2:                                  # restore의 "이 기기 값으로 통일"
            state["held"] = held_state(["p@m"])         # 해제 표식
            base = dict(base, **{"p@m": repo["p@m"]})   # 동시에 keep_local
        return local, repo, base

    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {},
                              rounds=4, before_round=before)
    assert snapshots[1][1]["p@m"] == ["1.0.0"]          # 해제 전에는 보존
    report, repo, base = snapshots[2]
    assert repo["p@m"] is True                          # 케이스 7 → 로컬 값 push
    assert report["conflicts"] == []                    # 케이스 9가 **아니다**
    assert base["p@m"] is True
    assert snapshots[3][1]["p@m"] is True               # 이후 불변
    assert snapshots[3][0]["held"] == []                # 레포 값이 불리언 → 자연 해제


def test_h3_release_without_keep_local_would_land_on_case9():
    """왜 두 조각이 함께여야 하는지를 고정한다 — 해제만 하면 반대 결과가 난다.

    이 테스트가 실패하면 keep_local 동시 적용이 불필요해진 것이므로 apply-base와
    spec 7.3을 함께 고쳐야 한다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 2:
            state["held"] = held_state(["p@m"])         # 해제만 한다
        return local, repo, base

    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {},
                              rounds=3, before_round=before)
    report, repo, _ = snapshots[2]
    assert report["conflicts"] == ["p@m"]
    assert repo["p@m"] == ["1.0.0"]


def test_held_key_missing_from_the_repo_does_not_become_a_deletion():
    """보류 키가 레포에서 사라졌을 때 — 이탈이 케이스 3·4·5로 착지하지 않는다.

    보류 중에는 판정표를 타지 않으므로 조용하고, 이탈하면 base에 그 키가 없으므로
    케이스 1(로컬 신규)로 착지해 **레포로 되돌아간다.** 이것이 base 제거 규칙(5.3)이
    보장하는 성질이고, 14.2 #4가 테스트로 강제하라고 지목한 것이다.
    """
    state = {"auto_ids": frozenset({"z@m"}), "held": held_state()}
    adapter = plugin_adapter("enabledPlugins", (True, False, ["1.0.0"]),
                             hold=live_hold("enabledPlugins", state))

    def before(index, local, repo, base):
        if index == 0:
            repo = {}                                   # 타 기기가 z를 지웠다
        if index == 2:
            state["auto_ids"] = frozenset()             # prune 이후 — 보류 이탈
        return local, repo, base

    snapshots = repeat_backup(adapter, {"z@m": True}, {"z@m": True}, {"z@m": True},
                              rounds=4, before_round=before)
    for report, repo, base in snapshots[:2]:
        assert report["deleted"] == [] and report["local_stale"] == []
        assert "z@m" not in repo                        # 보류 중에는 조용하다
        assert "z@m" not in base
    assert snapshots[2][1]["z@m"] is True               # 이탈 → 케이스 1로 push
    assert snapshots[2][0]["deleted"] == []
    assert snapshots[3][1]["z@m"] is True               # 이후 불변


def test_auto_hold_keeps_the_entry_out_of_the_repo_across_rounds():
    """H1 — 의존성 플러그인이 반복 백업에서도 레포로 승격되지 않는다 (N6)."""
    state = {"auto_ids": frozenset({"dep@m"}), "held": held_state()}
    adapter = enabled_adapter(state)
    snapshots = repeat_backup(adapter, {"dep@m": True, "mine@m": True}, {}, {})
    for report, repo, base in snapshots:
        assert "dep@m" not in repo and "dep@m" not in base
        assert repo["mine@m"] is True
        assert report["held"] == ["dep@m"]
    assert_fixed_point_from_second_round(snapshots)
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_state_machine.py -v`
기대: 보류 시나리오 다섯이 FAIL 또는 ERROR(헬퍼 미정의). 판정표 열 개는 **세 어댑터로 30개**가 되어야 한다.

- [ ] **Step 3: 구현**

Step 1의 편집이 곧 구현이다. **소스 코드는 바꾸지 않는다** — 이 task는 기존 구현의 미검증 경로를 덮는 것이 목적이다. 보류 시나리오가 FAIL한다면 그것은 실제 결함이므로 `lib/plugin_config.py` 또는 `lib/keyed_sync.py`를 고치고 **왜 고쳤는지 커밋 메시지에 남긴다.**

- [ ] **Step 4: 개수와 단정이 약해지지 않았는지 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_state_machine.py -v`
기대: 판정표 시나리오 10개 × 어댑터 3 = **30개**, 어댑터 목록 가드 1개, 보류 시나리오 5개.

실행: `git diff plugins/claude-sync/tests/test_mcp_state_machine.py | grep '^-' | grep -c assert`
실행: `git diff plugins/claude-sync/tests/test_mcp_state_machine.py | grep '^+' | grep -c assert`
기대: 뒤의 수가 앞의 수보다 크다. 작거나 같으면 단정이 사라진 것이므로 확인한다.

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

**이 task의 존재 이유가 변조 확인이다.** 아래는 전부 446개가 잡지 못했던 것들이다.

- `keyed_sync.merge`의 값 보류 갈래에서 `if name in repo: merged[name] = repo[name]`을 지우기 → **보류 유지 시나리오가 잡아야 한다.** 잡지 못하면 이 task는 실패다
- `_next_base_normalized`의 `if name in value_held: continue`를 지우기 → base 제거 단정이 잡아야 한다
- `plugin_adapter.next_base`에서 `value_held=`를 빼기 → 같은 단정이 잡아야 한다
- `plugin_config._make_hold`의 H3에서 `key not in released` 검사를 지우기 → 해제 착지 시나리오가 잡아야 한다
- H1의 `action.add`/`value.add` 중 하나를 지우기 → auto 시나리오가 잡아야 한다
- `Adapter.__init__`의 정규화 단정을 지우고 `pluginConfigs`의 값을 `{"options": {"k": "a"}}`류로 되돌리기 → **케이스 9 시나리오가 조용히 케이스 6이 된다.** 단정이 그것을 잡아야 한다
- `repeat_backup`의 `before_round` 호출을 루프 **뒤로** 옮기기 → 해제 시나리오의 회차 인덱스가 어긋나 FAIL해야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests/test_mcp_state_machine.py
git commit -m "test: 보류의 다회차 시나리오와 플러그인 두 섹션의 판정표를 더한다"
```

---

### Task 12: CLI 에뮬레이터와 교대 하네스

**근거:** spec 14.3, 5.6, 14.2 #1·#6

`test_mcp_cycle.py`는 **승계할 수 없다** — `collect_mcp.py`/`plan_mcp.py`의 절대 경로 상수, `~/.claude.json`을 직접 쓰는 `Device.set_local`, `add-json`을 dict 대입으로 흉내 내는 `Device.restore`가 전부 MCP에 묶여 있다. 플러그인은 **두 파일**을 흉내 내야 하고 CLI 의미론이 훨씬 복잡하다.

**에뮬레이터가 곧 CLI 동작의 정의가 된다.** 1-b의 실측표를 그대로 구현하지 않으면 아무것도 검증하지 않는 테스트가 된다. 특히 `installed_plugins.json`을 재현하지 않으면 **H1을 교대 테스트가 전혀 검증하지 못한다** — `auto`가 항상 비어 있어 `hold`가 항상 빈 집합이 되기 때문이다.

**Files:**
- Create: `plugins/claude-sync/tests/plugin_cli.py`
- Create: `plugins/claude-sync/tests/test_plugin_cycle.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_cycle.py`를 만든다(에뮬레이터 자체의 계약 테스트 + 두 시나리오).

```python
"""backup과 restore를 교대로 적용했을 때의 수렴을 스크립트 경유로 검증한다 (spec 14.2).

반복 backup만으로는 사용자가 선택지를 고른 뒤의 전이가 드러나지 않는다.
claude plugin 명령은 테스트에서 실행할 수 없으므로 plugin_cli.PluginCLI가 흉내낸다 —
그 밖의 모든 단계는 실제 스크립트를 서브프로세스로 호출한다.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import plugin_config as pc  # noqa: E402
from plugin_cli import PluginCLI  # noqa: E402

SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
COLLECT = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "collect_plugins.py"))
UPDATE_BASE = os.path.abspath(os.path.join(SKILLS, "sync-backup", "scripts", "update_base.py"))
PLAN = os.path.abspath(os.path.join(SKILLS, "sync-restore", "scripts", "plan_plugins.py"))
GH = {"source": {"source": "github", "repo": "o/r"}}


class Device:
    """한 기기(임시 HOME) + 공유 레포 디렉토리."""

    def __init__(self, root, repo):
        self.home = os.path.join(root, "home")
        self.repo = repo
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        self.cli = PluginCLI(self.home)

    # --- 로컬 상태 ---
    def local(self):
        return pc.read_local_sections(self.cli.settings_path)

    def base(self):
        path = os.path.join(self.home, ".claude", ".sync-state", "base", pc.BACKUP_RELPATH)
        return pc.parse_base(open(path, "rb").read()) if os.path.exists(path) else None

    def held(self):
        return pc.read_held_state(self.cli.held_path)

    # --- 스크립트 호출 ---
    def _run(self, *args, check=True):
        proc = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                              env=dict(os.environ, HOME=self.home))
        if check:
            assert proc.returncode == 0, proc.stderr
        return proc.stdout

    @property
    def staging(self):
        return os.path.join(self.home, "base-staging")

    def backup(self, push=True):
        """SKILL.md 5·10단계의 흐름: rm -rf → collect → (푸시 성공 시) update_base."""
        shutil.rmtree(self.staging, ignore_errors=True)
        report = json.loads(self._run(COLLECT, self.repo, self.staging))
        staged = os.path.join(self.staging, pc.BACKUP_RELPATH)
        if push and os.path.exists(staged):
            self._run(UPDATE_BASE, self.staging, pc.BACKUP_RELPATH)
        return report

    def restore(self, choices=None, secrets=None, fail_marketplaces=()):
        """SKILL.md 5단계의 흐름: plan → CLI 실행 → apply-base → update_base.

        secrets는 {plugin_id: {key: value}} — 사용자가 값을 입력한 항목만이다.
        fail_marketplaces는 등록이 실패하는 이름 — 9.3.2의 blocked를 만든다.
        """
        backup_path = os.path.join(self.repo, pc.BACKUP_RELPATH)
        plan = json.loads(self._run(PLAN, "plan", backup_path))
        if plan["status"] == "skipped":
            return plan
        blocked = set()
        for entry in plan["marketplace_add"]:                       # 1단계
            if entry["name"] in fail_marketplaces:
                blocked.add(entry["name"])
                continue
            self.cli.marketplace_add(entry["name"], entry["arg"])
        for plugin_id in plan["install"]:                           # 2단계
            if plan["depends_on"].get(plugin_id) in blocked:
                continue
            self.cli.install(plugin_id)
        for plugin_id in plan["disable_after_install"]:             # 3단계
            if plan["depends_on"].get(plugin_id) in blocked:
                continue
            self.cli.disable(plugin_id)
        for plugin_id, options in (secrets or {}).items():          # 4단계
            self.cli.install(plugin_id, config=options)
        return self._apply_base(backup_path, plan, choices or {})

    def _apply_base(self, backup_path, plan, choices):
        merged = {section: {"keep_stale": [], "keep_local": []} for section in pc.SECTIONS}
        for section, values in choices.items():
            merged.setdefault(section, {}).update(values)
        path = os.path.join(self.home, "choices.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(merged, f)
        shutil.rmtree(self.staging, ignore_errors=True)
        self._run(PLAN, "apply-base", backup_path, self.staging, path)
        self._run(UPDATE_BASE, self.staging, pc.BACKUP_RELPATH)
        return plan


def repo_doc(repo):
    return pc.load_backup(os.path.join(repo, pc.BACKUP_RELPATH))


def set_repo(repo, sections):
    """다른 기기가 레포를 바꾼 상황을 만든다."""
    pc.dump_backup(sections, os.path.join(repo, pc.BACKUP_RELPATH))


def make_device(tmp_path, repo_init=None):
    root = str(tmp_path)
    repo = os.path.join(root, "repo")
    os.makedirs(repo, exist_ok=True)
    if repo_init is not None:
        set_repo(repo, repo_init)
    return Device(root, repo)


# --- 에뮬레이터 계약 (14.3) — 이것이 틀리면 아래 시나리오가 전부 무의미하다 ---

def test_install_writes_true_but_preserves_an_existing_array(tmp_path):
    cli = PluginCLI(str(tmp_path))
    assert cli.install("p@m") == 0
    assert cli.settings()["enabledPlugins"]["p@m"] is True
    cli.set_enabled("q@m", ["1.0.0"])
    assert cli.install("q@m") == 0
    assert cli.settings()["enabledPlugins"]["q@m"] == ["1.0.0"]


def test_install_flattens_an_existing_object_value(tmp_path):
    """실측 — 객체 형태 한 갈래만 true로 평탄화된다 (1.2)."""
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("o@m", {"version": "1.0.0"})
    cli.install("o@m")
    assert cli.settings()["enabledPlugins"]["o@m"] is True


def test_enable_and_disable_are_not_idempotent(tmp_path):
    """이미 그 상태면 exit 1 — 이 성질이 없으면 "현재 상태와 다를 때만"이 무의미해진다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m")
    assert cli.enable("p@m") == 1
    assert cli.disable("p@m") == 0
    assert cli.disable("p@m") == 1


def test_uninstall_removes_the_config_too_and_fails_when_absent(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m", config={"k": "v"})
    assert cli.uninstall("p@m") == 0
    assert cli.settings()["enabledPlugins"] == {}
    assert cli.settings()["pluginConfigs"] == {}
    assert cli.uninstall("p@m") == 1


def test_install_config_merges_partially(tmp_path):
    """N2 — 지정하지 않은 키는 보존된다. 6.3의 부분 입력이 여기 걸려 있다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m", config={"a": "1", "b": "2"})
    cli.install("p@m", config={"b": "3"})
    assert cli.settings()["pluginConfigs"]["p@m"]["options"] == {"a": "1", "b": "3"}


def test_marketplace_remove_cascades_to_member_plugins(tmp_path):
    """실측 — 연쇄 삭제. restore가 이 명령을 실행하지 않는 이유다 (9.3.5)."""
    cli = PluginCLI(str(tmp_path))
    cli.marketplace_add("m", "o/r")
    cli.install("p@m", config={"k": "v"})
    cli.install("q@other")
    assert cli.marketplace_remove("m") == 0
    assert cli.settings()["enabledPlugins"] == {"q@other": True}
    assert cli.settings()["pluginConfigs"] == {}


def test_dependency_install_marks_auto_and_explicit_install_clears_it(tmp_path):
    """N6 — 명시적 설치는 auto 표식을 **되돌릴 수 없게** 지운다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("parent@m", dependencies=["child@m"])
    assert pc.read_auto_ids(cli.installed_path) == frozenset({"child@m"})
    cli.install("child@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_prune_removes_orphaned_auto_entries(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.install("parent@m", dependencies=["child@m"])
    cli.uninstall("parent@m")
    cli.prune()
    assert "child@m" not in cli.settings()["enabledPlugins"]
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


# --- 14.2 #1 부트스트랩 / #6 레포 쓰기 실패 ---

def test_backup_bootstraps_the_base_blob_with_three_sections(tmp_path):
    """7.4의 배선 결함을 잡는 유일한 테스트 — base가 영영 생성되지 않으면 삭제 전파가 죽는다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("p@m")
    for _ in range(3):
        dev.backup()
    base = dev.base()
    assert set(base) == set(pc.SECTIONS)
    assert base["enabledPlugins"] == {"p@m": True}


def test_backup_without_push_does_not_advance_base(tmp_path):
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup(push=False)
    assert dev.base() is None


def test_base_does_not_advance_when_the_repo_file_cannot_be_written(tmp_path):
    """14.2 #6 — rename 계약. 레포가 그 내용을 갖지 않았는데 base가 전진하면
    다음 백업이 이 기기 자신의 플러그인을 케이스 4로 오독한다."""
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup()
    dev.cli.install("q@m")
    os.chmod(os.path.join(dev.repo, pc.BACKUP_RELPATH), 0o400)
    os.chmod(dev.repo, 0o500)
    try:
        report = json.loads(dev._run(COLLECT, dev.repo, dev.staging))
    finally:
        os.chmod(dev.repo, 0o700)
        os.chmod(os.path.join(dev.repo, pc.BACKUP_RELPATH), 0o600)
    assert report["status"] == "skipped"
    assert dev.base()["enabledPlugins"] == {"p@m": True}


def test_skipped_backup_touches_neither_repo_nor_base(tmp_path):
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup()
    os.remove(dev.cli.settings_path)
    report = dev.backup()
    assert report["status"] == "skipped"
    assert repo_doc(dev.repo)["enabledPlugins"] == {"p@m": True}
    assert dev.base()["enabledPlugins"] == {"p@m": True}
```

권한 기반 테스트에는 `from marks import requires_permission_bits`를 붙인다(`test_base_does_not_advance_when_the_repo_file_cannot_be_written`).

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_cycle.py -q`
기대: 전부 FAIL (`ModuleNotFoundError: No module named 'plugin_cli'`)

- [ ] **Step 3: 구현**

`tests/plugin_cli.py`를 만든다.

```python
"""`claude plugin` CLI 에뮬레이터 (spec 14.3).

**이 파일이 곧 CLI 동작의 정의가 된다.** 브리프 1-b의 실측표를 그대로 구현하지 않으면
교대 테스트가 아무것도 검증하지 않는다. 실측되지 않은 갈래는 주석에 그렇게 적는다.

두 파일을 모두 재현한다 — settings.json(값)과 installed_plugins.json(auto 플래그).
후자를 빼면 hold가 항상 빈 집합이 되어 **H1을 교대 테스트가 전혀 검증하지 못한다.**
"""
import json
import os


class PluginCLI:
    """임시 HOME 하나에 대한 claude plugin 명령. 반환값은 exit code다."""

    def __init__(self, home):
        self.home = home
        self.settings_path = os.path.join(home, ".claude", "settings.json")
        self.installed_path = os.path.join(home, ".claude", "plugins",
                                           "installed_plugins.json")
        self.held_path = os.path.join(home, ".claude", ".sync-state", "plugins-held.json")
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.installed_path), exist_ok=True)
        self._write(self.settings_path, {"enabledPlugins": {}, "extraKnownMarketplaces": {},
                                         "pluginConfigs": {}})
        self._write(self.installed_path, {"version": 2, "plugins": {}})
        self._parents = {}          # 부모 → 의존성으로 끌려온 자식들

    # --- 파일 ---
    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)

    def settings(self):
        return self._read(self.settings_path)

    def installed(self):
        return self._read(self.installed_path)

    def set_enabled(self, plugin_id, value):
        """테스트가 확장 포맷 값을 심을 때 쓴다. CLI 명령이 아니다."""
        data = self.settings()
        data["enabledPlugins"][plugin_id] = value
        self._write(self.settings_path, data)
        self._mark_installed(plugin_id, auto=False)

    # --- installed_plugins.json ---
    def _mark_installed(self, plugin_id, auto):
        data = self.installed()
        entries = [e for e in data["plugins"].get(plugin_id, [])
                   if e.get("scope") != "user"]
        entries.append({"scope": "user", "auto": auto})
        data["plugins"][plugin_id] = entries
        self._write(self.installed_path, data)

    def _forget_installed(self, plugin_id):
        data = self.installed()
        data["plugins"].pop(plugin_id, None)
        self._write(self.installed_path, data)

    # --- 명령 ---
    def install(self, plugin_id, config=None, dependencies=()):
        """키를 true로. **단 기존 값이 배열이면 보존**하고 객체는 평탄화한다 (1.2).

        이미 설치돼 있어도 exit 0(멱등). 명시적 설치는 auto 표식을 지운다(N6) —
        되돌릴 수 없다. config는 **부분 병합**이다(N2).
        """
        data = self.settings()
        current = data["enabledPlugins"].get(plugin_id)
        if not isinstance(current, list):
            data["enabledPlugins"][plugin_id] = True
        if config:
            entry = data["pluginConfigs"].setdefault(plugin_id, {})
            options = entry.setdefault("options", {})
            options.update(config)
        for child in dependencies:
            if child not in data["enabledPlugins"]:
                data["enabledPlugins"][child] = True
        self._write(self.settings_path, data)
        self._mark_installed(plugin_id, auto=False)
        for child in dependencies:
            if child not in self.installed()["plugins"]:
                self._mark_installed(child, auto=True)
        if dependencies:
            self._parents[plugin_id] = list(dependencies)
        return 0

    def enable(self, plugin_id):
        return self._set_value(plugin_id, True)

    def disable(self, plugin_id):
        return self._set_value(plugin_id, False)

    def _set_value(self, plugin_id, value):
        """값만 변경한다. **이미 그 상태면 exit 1.**

        설치되지 않은 id에 대한 동작은 미측정이다 — 여기서는 exit 1로 둔다.
        복원 흐름은 설치 뒤에만 부르므로 이 갈래에 의존하지 않는다.
        """
        data = self.settings()
        if plugin_id not in data["enabledPlugins"]:
            return 1
        if data["enabledPlugins"][plugin_id] == value:
            return 1
        data["enabledPlugins"][plugin_id] = value
        self._write(self.settings_path, data)
        return 0

    def uninstall(self, plugin_id):
        """enabledPlugins·pluginConfigs에서 **키를 삭제**한다. 없으면 exit 1."""
        data = self.settings()
        if plugin_id not in data["enabledPlugins"]:
            return 1
        data["enabledPlugins"].pop(plugin_id)
        data["pluginConfigs"].pop(plugin_id, None)
        self._write(self.settings_path, data)
        self._forget_installed(plugin_id)
        return 0

    def marketplace_add(self, name, source):
        """멱등. exit 0. source는 marketplace_arg가 만든 문자열이다."""
        data = self.settings()
        data["extraKnownMarketplaces"][name] = {
            "source": {"source": "github", "repo": source}}
        self._write(self.settings_path, data)
        return 0

    def marketplace_remove(self, name):
        """**소속 플러그인 키를 연쇄 삭제한다** — restore가 이 명령을 실행하지 않는 이유다."""
        data = self.settings()
        if name not in data["extraKnownMarketplaces"]:
            return 1
        data["extraKnownMarketplaces"].pop(name)
        doomed = [pid for pid in data["enabledPlugins"] if pid.endswith("@" + name)]
        for plugin_id in doomed:
            data["enabledPlugins"].pop(plugin_id)
            data["pluginConfigs"].pop(plugin_id, None)
        self._write(self.settings_path, data)
        for plugin_id in doomed:
            self._forget_installed(plugin_id)
        return 0

    def set_directory_marketplace(self, name, path):
        """로컬 디렉토리 출처를 심는다 (H2). `marketplace add <경로>`의 결과다."""
        data = self.settings()
        data["extraKnownMarketplaces"][name] = {
            "source": {"source": "directory", "path": path}}
        self._write(self.settings_path, data)
        return 0

    def prune(self):
        """부모가 사라진 auto 항목을 제거한다."""
        data = self.settings()
        installed = self.installed()["plugins"]
        removed = []
        for plugin_id, entries in list(installed.items()):
            auto = any(e.get("scope") == "user" and e.get("auto") is True for e in entries)
            parents = [p for p, children in self._parents.items()
                       if plugin_id in children and p in data["enabledPlugins"]]
            if auto and not parents:
                removed.append(plugin_id)
        for plugin_id in removed:
            data["enabledPlugins"].pop(plugin_id, None)
            data["pluginConfigs"].pop(plugin_id, None)
        self._write(self.settings_path, data)
        for plugin_id in removed:
            self._forget_installed(plugin_id)
        return 0
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

**에뮬레이터가 틀리면 Task 13이 통째로 무의미해진다.** 그래서 에뮬레이터 자체에도 변조를 건다.

- `install`에서 `isinstance(current, list)` 보존을 지우기 → 배열 보존 테스트가 잡아야 한다
- `_set_value`의 "이미 그 상태면 1"을 0으로 바꾸기 → 비멱등 테스트가 잡아야 한다
- `uninstall`에서 `pluginConfigs.pop`을 지우기 → 설정 삭제 테스트가 잡아야 한다
- `marketplace_remove`의 연쇄 삭제를 지우기 → 연쇄 테스트가 잡아야 한다
- `install`의 `_mark_installed(plugin_id, auto=False)`를 지우기 → auto 해제 테스트가 잡아야 한다
- `install --config`의 `options.update`를 `entry["options"] = config`로 바꾸기 → 부분 병합 테스트가 잡아야 한다
- `Device.backup`의 게이트 `os.path.exists(staged)`를 `report["status"] == "ok"`로 바꾸기 → **rename 계약이 무의미해진다.** 레포 쓰기 실패 테스트가 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests/plugin_cli.py plugins/claude-sync/tests/test_plugin_cycle.py
git commit -m "test: CLI 에뮬레이터와 교대 하네스, 부트스트랩·rename 계약"
```

---

### Task 13: 교대 시나리오 — 선택지 실행 후의 수렴

**근거:** spec 14.2 #2·#3·#4·#5·#7·#8, 6.4, 7.3, 9.3.4, 9.3.5

**판정표를 100% 덮은 테스트가 전부 통과하는데도 시스템이 데이터를 잃을 수 있다.** 아래 여섯은 단위 테스트로 잡히지 않는 것들이고, 특히 #4·#5·#8은 서로를 대체하지 못한다 — #2·#3은 보류가 **유지되는 동안만** 보고, #2는 "사라지지 않음"만 보므로 **영원히 다시 묻는** 실패를 통과시킨다.

**Files:**
- Modify: `plugins/claude-sync/tests/test_plugin_cycle.py`

- [ ] **Step 1: 실패하는 test 작성**

`Device`에 status 호출을 더한다.

```python
COMPARE = os.path.abspath(os.path.join(SKILLS, "sync-status", "scripts", "compare_plugins.py"))

    def status(self):
        """읽기 전용 비교. 아무것도 바꾸지 않는다."""
        return json.loads(self._run(COMPARE, os.path.join(self.repo, pc.BACKUP_RELPATH)))
```

파일 끝에 시나리오를 더한다.

```python
# --- 14.2 #2 선택지 실행 후 2회 백업 ---

def test_case4_keep_brings_the_plugin_back_and_stabilizes(tmp_path):
    """9.3.4 케이스 4의 "유지" — 레포로 되돌아간 뒤 부활·소멸이 반복되지 않는다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("X@m")
    dev.cli.install("y@m")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {"y@m": True},
                        "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}})
    assert dev.backup()["sections"]["enabledPlugins"]["local_stale"] == ["X@m"]
    dev.restore(choices={"enabledPlugins": {"keep_stale": ["X@m"]}})
    assert "X@m" not in dev.base()["enabledPlugins"]
    dev.backup()
    assert sorted(repo_doc(dev.repo)["enabledPlugins"]) == ["X@m", "y@m"]
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["local_stale"] == []
    assert report["sections"]["enabledPlugins"]["deleted"] == []
    assert sorted(repo_doc(dev.repo)["enabledPlugins"]) == ["X@m", "y@m"]


def test_marketplace_keep_returns_it_without_running_remove(tmp_path):
    """9.3.5 — 마켓플레이스는 삭제를 자동 실행하지 않지만 "유지"는 반드시 효과가 있어야 한다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {}, "extraKnownMarketplaces": {},
                        "pluginConfigs": {}})
    dev.backup()
    dev.restore(choices={"extraKnownMarketplaces": {"keep_stale": ["m"]}})
    dev.backup()
    assert "m" in repo_doc(dev.repo)["extraKnownMarketplaces"]
    assert "m" in dev.local()["extraKnownMarketplaces"]


# --- 14.2 #3 보류 후 침묵 ---

def test_declined_config_silences_status_until_the_repo_value_changes(tmp_path):
    """6.4 — 보류를 고른 뒤 status가 조용해야 하고, 레포 값이 바뀌면 다시 보고해야 한다."""
    repo_init = {"enabledPlugins": {"delta@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}
    dev = make_device(tmp_path, repo_init=repo_init)
    dev.restore(choices={"pluginConfigs": {"declined": ["delta@m"]}})
    assert dev.held()["pluginConfigs"]["delta@m"]
    section = dev.status()["sections"]["pluginConfigs"]
    assert section["only_repo"] == [] and section["changed"] == []
    assert section["held"]["declined"] == ["delta@m"]

    changed = json.loads(json.dumps(repo_init))
    changed["pluginConfigs"]["delta@m"]["options"]["extra"] = pc.SENTINEL
    set_repo(dev.repo, changed)
    assert dev.status()["sections"]["pluginConfigs"]["only_repo"] == ["delta@m"]


def test_declined_config_keeps_the_repo_entry_across_two_backups(tmp_path):
    """6.4 — 초판의 "base에 레포 값 기록"이 케이스 3으로 착지시켰던 자리다.

    기기 B가 "이 기기에서는 안 쓴다"고 말했을 뿐인데 기기 A가 백업해 둔 설정 키 목록이
    레포에서 사라지면 안 된다.
    """
    repo_init = {"enabledPlugins": {"delta@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}
    dev = make_device(tmp_path, repo_init=repo_init)
    dev.restore(choices={"pluginConfigs": {"declined": ["delta@m"]}})
    dev.backup()
    dev.backup()
    assert repo_doc(dev.repo)["pluginConfigs"]["delta@m"]["options"] == {
        "apiKey": pc.SENTINEL}


def test_partially_entered_config_does_not_drop_the_other_keys(tmp_path):
    """14.1 — 세 키 중 두 개만 입력해도 레포의 세 번째 키가 사라지지 않는다 (6.3)."""
    repo_init = {"enabledPlugins": {"p@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"p@m": {"options": {k: pc.SENTINEL
                                                       for k in ("a", "b", "c")}}}}
    dev = make_device(tmp_path, repo_init=repo_init)
    dev.restore(secrets={"p@m": {"a": "1", "b": "2"}},
                choices={"pluginConfigs": {"declined": ["p@m"]}})
    dev.backup()
    dev.backup()
    assert sorted(repo_doc(dev.repo)["pluginConfigs"]["p@m"]["options"]) == ["a", "b", "c"]


# --- 14.2 #4 보류 진입 → 이탈 ---

def test_auto_dependency_round_trip_keeps_the_entry_in_the_repo(tmp_path):
    """14.2 #4의 H1 — z를 손으로 설치 → 백업 → z가 의존성이 됨 → 백업 →
    부모 제거 + prune → 백업. **z가 레포에 남아 있어야 한다.**

    1·2·3은 held가 유지되는 동안만 확인하므로 이 결함을 하나도 잡지 못한다.
    """
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("z@m")
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True

    dev.cli.uninstall("z@m")
    dev.cli.install("p@m", dependencies=["z@m"])        # z가 auto로 다시 들어온다
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["held"]["auto"] == ["z@m"]
    assert report["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True

    dev.cli.uninstall("p@m")
    dev.cli.prune()
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["deleted"] == ["p@m"]
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True
    assert dev.backup()["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(dev.repo)["enabledPlugins"]["z@m"] is True


def test_local_directory_marketplace_never_reaches_the_repo(tmp_path):
    """H2 — 마켓플레이스와 **그 소속 플러그인**이 둘 다 올라가지 않아야 한다.

    플러그인 키만 올라가면 기기 B의 restore가 매번 "먼저 마켓플레이스를 등록해야
    합니다"를 내는데, 기기 B에는 등록할 소스 자체가 없다.
    """
    dev = make_device(tmp_path)
    dev.cli.set_directory_marketplace("mylocal", "/tmp/x")
    dev.cli.install("p@mylocal")
    dev.cli.marketplace_add("gh", "o/r")
    dev.cli.install("q@gh")
    dev.backup()
    doc = repo_doc(dev.repo)
    assert doc["extraKnownMarketplaces"] == {"gh": {"source": {"source": "github",
                                                               "repo": "o/r"}}}
    assert doc["enabledPlugins"] == {"q@gh": True}
    assert dev.backup()["sections"]["enabledPlugins"]["deleted"] == []


# --- 14.2 #5 선택 후 고정점 ---

def test_keep_choice_is_not_asked_again(tmp_path):
    """14.2 #5 — #2는 "사라지지 않음"만 보므로 **영원히 다시 묻는** 실패를 통과시킨다."""
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("X@m")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {}, "extraKnownMarketplaces": {"m": GH},
                        "pluginConfigs": {}})
    dev.backup()
    dev.restore(choices={"enabledPlugins": {"keep_stale": ["X@m"]}})
    dev.backup()
    dev.backup()
    plan = dev.restore()
    assert plan["sections"]["enabledPlugins"]["local_stale"] == []
    assert plan["sections"]["enabledPlugins"]["in_sync"] == ["X@m"]


# --- 14.2 #7 부분 실패 후 재실행 수렴 ---

def test_blocked_install_is_recovered_by_the_next_restore(tmp_path):
    """9.3.2 — 등록이 실패한 마켓플레이스의 플러그인은 시도하지 않는다.

    시도하면 CLI가 "플러그인이 없다"와 똑같은 문구로 실패해 거짓 실패를 양산한다.
    원인을 없애고 다시 돌리면 남은 항목이 복원되어야 한다.
    """
    dev = make_device(tmp_path, repo_init={
        "enabledPlugins": {"p@m": True, "q@other": True},
        "extraKnownMarketplaces": {"m": GH, "other": {"source": {"source": "github",
                                                                 "repo": "o/o"}}},
        "pluginConfigs": {}})
    dev.restore(fail_marketplaces=["m"])
    assert "p@m" not in dev.local()["enabledPlugins"]
    assert dev.local()["enabledPlugins"]["q@other"] is True
    assert "p@m" not in (dev.base() or {}).get("enabledPlugins", {})   # 10.4
    dev.restore()
    assert dev.local()["enabledPlugins"]["p@m"] is True


# --- 14.2 #8 H3 탈출구 왕복 ---

def test_extended_value_escape_hatch_round_trip(tmp_path):
    """7.3 — 탈출구 실행 → backup 2회 → 레포 값이 true → 그 뒤 uninstall이 케이스 3으로 전파.

    #4·#5 어느 것도 이 경로를 덮지 않는다. "지우려면 먼저 불리언화"가 실제로 성립하는지가
    여기서 판정된다.
    """
    dev = make_device(tmp_path, repo_init={
        "enabledPlugins": {"p@m": ["1.0.0"]},
        "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}})
    plan = dev.restore()
    assert plan["sections"]["enabledPlugins"]["add"] == ["p@m"]     # 설치는 한다
    assert dev.local()["enabledPlugins"]["p@m"] is True
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] == ["1.0.0"]  # 값은 밀지 않는다

    dev.restore(choices={"enabledPlugins": {"release": ["p@m"]}})    # 탈출구
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] is True
    dev.backup()
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] is True
    assert dev.held()["release"]["enabledPlugins"] == []             # 조건이 사라져 정리됨

    dev.cli.uninstall("p@m")
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["deleted"] == ["p@m"]
    assert "p@m" not in repo_doc(dev.repo)["enabledPlugins"]


def test_uninstall_before_the_escape_hatch_does_not_propagate(tmp_path):
    """7.3 — H3의 조건은 **레포 값**이므로 로컬에서 지워도 보류가 유지된다.

    삭제가 전파되지 않고 다음 restore가 다시 설치한다. 안내 문구가 "먼저 불리언화"를
    적어야 하는 이유이고, 이 성질이 깨지면 그 안내가 거짓이 된다.
    """
    dev = make_device(tmp_path, repo_init={
        "enabledPlugins": {"p@m": ["1.0.0"]},
        "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}})
    dev.restore()
    dev.backup()
    dev.cli.uninstall("p@m")
    report = dev.backup()
    assert report["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(dev.repo)["enabledPlugins"]["p@m"] == ["1.0.0"]
    assert dev.restore()["sections"]["enabledPlugins"]["add"] == ["p@m"]


# --- 주기 고정점 ---

def test_two_cycles_reach_a_fixed_point(tmp_path):
    """backup→restore를 반복하면 2주기째부터 레포·base·보고가 변하지 않는다.

    1주기째는 restore가 케이스 2의 항목을 실제로 설치하므로 2주기와 다를 수 있다 —
    그 설치는 정당한 상태 변화다.
    """
    dev = make_device(tmp_path)
    dev.cli.marketplace_add("m", "o/r")
    dev.cli.install("X@m")
    dev.cli.install("x@m")
    dev.backup()
    set_repo(dev.repo, {"enabledPlugins": {"x@m": False, "z@m": True},
                        "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}})
    snapshots = []
    for _ in range(3):
        report = dev.backup()
        plan = dev.restore()
        snapshots.append((repo_doc(dev.repo), dev.base(), report,
                          plan["sections"]["enabledPlugins"]))
    assert snapshots[1] == snapshots[2], "2주기와 3주기가 다르다 — 고정점이 아니다"
    assert snapshots[2][2]["sections"]["enabledPlugins"]["local_stale"] == ["X@m"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_cycle.py -q`
기대: 신규 시나리오가 FAIL 또는 ERROR

- [ ] **Step 3: 구현**

`Device.status` 외에 **소스 코드 변경은 예정에 없다.** 시나리오가 FAIL하면 그것은 실제 결함이므로 `lib/` 또는 스크립트를 고치고 **왜 고쳤는지 커밋 메시지에 남긴다.** 특히 아래 셋은 실패할 가능성이 높은 자리다.

- `test_auto_dependency_round_trip_keeps_the_entry_in_the_repo` — 이탈 회차에서 `z@m`이 케이스 2로 되살아나는지
- `test_extended_value_escape_hatch_round_trip` — 해제 회차의 착지가 케이스 7인지
- `test_keep_choice_is_not_asked_again` — `keep_stale` 뒤 `in_sync`로 수렴하는지

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `plan_plugins.apply_base`의 release + `keep_local` 동시 적용을 지우기 → H3 왕복이 잡아야 한다
- `pc.next_held_state`의 release 정리를 지우기 → 왕복의 `release == []` 단정이 잡아야 한다
- `collect_plugins`의 H2 보류를 마켓플레이스 섹션에만 적용하기 → directory 시나리오가 잡아야 한다
- `Device.restore`의 `blocked` 검사를 지우기 → 부분 실패 시나리오가 **통과해 버린다**(에뮬레이터는 실패하지 않으므로). 이것은 하네스의 한계다 — `depends_on`이 비면 잡히도록 단정을 하나 더 건다
- `keyed_sync.next_base`의 "로컬이 동의한 키만 전진"을 지우기 → 부분 실패의 base 단정(10.4)이 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests/test_plugin_cycle.py
git commit -m "test: 선택지 실행 후의 교대 시나리오 여섯"
```

---

### Task 14: 세 스킬 배선 — **사용자 가치가 여기서 처음 나온다**

**근거:** spec 7.4, 9.1·9.2·9.3, 12장, 부록 A / 13장 표의 9·10행

여기까지는 사용자에게 보이는 변화가 0이다. 스킬이 새 스크립트를 부르는 순간 결함 A·B·C가 동시에 해소된다.

**배선 셋이 겹쳐 있다**(7.4가 확인한 충돌):
1. `SKILL.md:285`의 `rm -rf "$MCP_STAGING"`이 MCP 수집 **직전**에 있다 → 플러그인 수집을 앞에 두면 그 산출물이 지워진다.
2. `:398`의 게이트가 `mcp-servers.json` **한 파일에만** 걸려 있다 → MCP가 skipped이고 플러그인이 ok인 실행에서는 블록 자체가 실행되지 않는다.
3. `update_base.py:27`은 파일이 없으면 경고만 내고 조용히 건너뛴다.

셋이 겹치면 `base/plugins.json`이 **영원히 생성되지 않고**, `merge`가 매번 `base=None` 합집합 degrade를 타 **케이스 3·4가 영영 발생하지 않는다.** G1은 지켜지지만 삭제 전파가 죽고, **조용하다.**

**다운그레이드 탐지를 4.5단계로 옮긴다.** 현재 5.5는 플러그인 수집(5단계) **뒤**에 있다. plan ③이 탐지를 `plugins.json`으로 넓히면 그 순서에서는 "레포가 옛 형식"이라는 증거가 이미 지워진 뒤다. 절 번호만 바꾸고 내용은 그대로 둔다.

**Files:**
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md` (4.5·5·6·10단계)
- Modify: `plugins/claude-sync/skills/sync-status/SKILL.md` (2단계)
- Modify: `plugins/claude-sync/skills/sync-restore/SKILL.md` (5절 전면 교체, 6-6단계)
- Modify: `plugins/claude-sync/skills/sync-status/scripts/check_status.py:59-76`
- Delete: `plugins/claude-sync/skills/sync-backup/scripts/extract_plugins.py`
- Modify: `plugins/claude-sync/tests/test_script_root.py` (앵커)

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_script_root.py`의 표 셋을 갱신하고 가드를 더한다.

```python
COMPAT_WIRING = {
    "sync-backup": {
        "section": "2.5 호환성 검사",
        "after_section": "### 2. 레포 준비",
        "before_section": "### 3. Git User 설정",
        "before_calls": (
            'python3 $SYNC_SCRIPTS/reconcile_backup.py "$SYNC_REPO"',
            # extract_plugins.py를 지우면서 **앵커를 지우지 않는다** — 이 항목은
            # "호환성 검사가 이 실행줄보다 앞에 있어야 한다"를 거는 자리다.
            'python3 "$SYNC_SCRIPTS/collect_plugins.py" "$SYNC_REPO" "$BASE_STAGING"',
            'python3 "$SYNC_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$BASE_STAGING"',
            'python3 "$SYNC_SCRIPTS/generate_metadata.py" "$SYNC_REPO/sync-metadata.json"',
        ),
    },
    "sync-status": {
        "section": "1.5 호환성 검사",
        "after_section": "### 1. 설정 확인 및 레포 준비",
        "before_section": "### 2. 메타데이터 기반 상태 분석",
        "before_calls": (
            'python3 $SYNC_SCRIPTS/check_status.py "$SYNC_REPO"',
            'python3 "$SYNC_SCRIPTS/compare_plugins.py" "$SYNC_REPO/plugins.json"',
            'python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"',
        ),
    },
    "sync-restore": {
        "section": RESTORE_CHECK_SECTION,
        "after_section": "### 2. 레포에서 최신 상태 가져오기",
        "before_section": "### 3. 파일별 reconcile",
        "before_calls": (
            'python3 "$SYNC_SCRIPTS/reconcile_restore.py" "$SYNC_REPO" --apply',
            'python3 "$SYNC_SCRIPTS/plan_plugins.py" plan "$SYNC_REPO/plugins.json"',
            'python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json"',
            'python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"',
        ),
    },
}

DOWNGRADE_SECTION = {
    "sync-backup": "4.5 다운그레이드 사고 탐지",
    "sync-status": "1.5 호환성 검사",
    "sync-restore": RESTORE_CHECK_SECTION,
}

DOWNGRADE_BEFORE = {
    # 수집이 레포 파일을 v2로 덮어쓰면 "레포가 옛 형식"이라는 증거가 사라진다.
    # **가장 앞선 수집 단계**를 앵커로 쓴다 — plan ③이 탐지를 plugins.json으로
    # 넓히면 그 순서가 곧 정확도가 된다.
    "sync-backup": 'python3 "$SYNC_SCRIPTS/collect_plugins.py" "$SYNC_REPO" "$BASE_STAGING"',
    "sync-restore": 'python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json"',
}
```

파일 끝에 가드를 더한다.

```python
STAGING_CLEAR = 'rm -rf "$BASE_STAGING"'


def test_backup_clears_the_shared_staging_once_before_both_collectors():
    """7.4 — 각 단계가 제 앞에서 rm -rf하면 앞 단계의 산출물이 지워진다."""
    text = read_skill("sync-backup")
    assert text.count(STAGING_CLEAR) == 1
    clear = index_of(text, STAGING_CLEAR, "sync-backup")
    for call in (COMPAT_WIRING["sync-backup"]["before_calls"][1],
                 COMPAT_WIRING["sync-backup"]["before_calls"][3]):
        assert clear < index_of(text, call, "sync-backup")


def test_backup_base_gate_covers_both_relpaths():
    """게이트가 한 파일에만 걸리면 MCP가 skipped인 실행에서 플러그인 base가 전진하지 않는다."""
    block = section("sync-backup", "10. 커밋 & 푸시")
    assert "for rel in plugins.json mcp-servers.json" in block
    assert '"$BASE_STAGING" "${RELS[@]}"' in block
    assert '[ -f "$MCP_STAGING/mcp-servers.json" ]' not in read_skill("sync-backup")


def test_restore_clears_the_shared_staging_before_both_apply_base_calls():
    """apply-base 산출물이 같은 디렉토리를 쓴다 — rm -rf는 둘보다 앞에서 한 번이다."""
    text = read_skill("sync-restore")
    assert text.count(STAGING_CLEAR) == 1
    clear = index_of(text, STAGING_CLEAR, "sync-restore")
    for call in ('"$SYNC_SCRIPTS/plan_plugins.py" apply-base',
                 '"$SYNC_SCRIPTS/plan_mcp.py" apply-base'):
        assert clear < index_of(text, call, "sync-restore")


def plugin_restore_section():
    text = read_skill("sync-restore")
    return text[text.index("### 5. 플러그인 복원"):text.index("### 6. MCP 서버 복원")]


def bash_blocks(text):
    """```bash 블록의 본문만 모은다 — 산문의 언급과 실행줄을 가른다."""
    out, rest = [], text
    while "```bash" in rest:
        _, rest = rest.split("```bash", 1)
        body, rest = rest.split("```", 1)
        out.append(body)
    return out


def test_restore_never_executes_marketplace_remove():
    """14.1 — 연쇄 삭제 방어. 안내는 하되 실행하지 않는다 (9.3.5).

    산문에는 나타나야 한다 — 사용자가 손으로 실행할 명령을 알려 주는 자리다.
    """
    sec = plugin_restore_section()
    assert "marketplace remove" in sec
    assert not any("marketplace remove" in block for block in bash_blocks(sec))


def test_restore_plugin_commands_carry_scope_user_and_never_dash_y():
    """14.1 — --scope user가 없으면 복원된 플러그인이 settings.json에 나타나지 않아
    backup이 못 보고 status가 only_repo를 영구 보고한다(I6). -y는 D2 위반이다."""
    blocks = bash_blocks(plugin_restore_section())
    commands = [line.strip() for block in blocks for line in block.splitlines()
                if line.strip().startswith("claude plugin")]
    assert commands
    for command in commands:
        assert "--scope user" in command, command
        assert " -y" not in command and "--yes" not in command, command


def test_status_reports_plugin_sections_through_the_new_script():
    """결함 B — check_status.py의 키 집합 비교를 지우고 새 스크립트를 부른다."""
    sec = section("sync-status", "2. 메타데이터 기반 상태 분석")
    assert '"$SYNC_SCRIPTS/compare_plugins.py"' in sec
    assert "skipped" in sec
    source = open(os.path.join(SKILLS_DIR, "sync-status", "scripts", "check_status.py"),
                  encoding="utf-8").read()
    assert "enabledPlugins" not in source


def test_extract_plugins_is_gone_everywhere():
    """12장 — 스킬이 새 스크립트를 부르게 된 뒤에 지운다. 그 전에 지우면 백업이 깨진다."""
    scripts = os.path.join(SKILLS_DIR, "sync-backup", "scripts")
    assert not os.path.exists(os.path.join(scripts, "extract_plugins.py"))
    for skill in ("sync-backup", "sync-status", "sync-restore"):
        assert "extract_plugins" not in read_skill(skill)
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_script_root.py -q`
기대: 다수 FAIL (앵커가 아직 SKILL.md에 없다)

- [ ] **Step 3: 구현**

**(a) `sync-backup/SKILL.md`.** 현행 `### 5. plugins.json 생성`(241~248행)을 아래로 교체하고, 그 **앞**으로 `### 5.5 다운그레이드 사고 탐지` 절을 통째로 옮기며 제목을 `### 4.5 다운그레이드 사고 탐지`로 바꾼다(본문은 그대로, 첫 문장의 *"MCP 수집보다 먼저 한다"* 만 *"수집 단계들보다 먼저 한다"* 로 고친다).

````markdown
### 5. plugins.json 생성 (키 단위 3-way 병합)

`~/.claude/settings.json`의 세 필드(`enabledPlugins`·`extraKnownMarketplaces`/`additionalMarketplaces`·`pluginConfigs`)와 `~/.claude/plugins/installed_plugins.json`의 `auto` 플래그를 읽어 레포의 `plugins.json`과 **섹션별 키 단위로 병합**한다. `claude plugin list`는 호출하지 않는다.

**`BASE_STAGING`은 수집 단계들보다 앞에서 딱 한 번 비운다.** 6단계의 MCP 수집이 같은 디렉토리를 쓰므로, 각 단계가 제 앞에서 `rm -rf`하면 앞 단계의 산출물이 지워지고 그 파일의 base가 영영 전진하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"
rm -rf "$BASE_STAGING"
python3 "$SYNC_SCRIPTS/collect_plugins.py" "$SYNC_REPO" "$BASE_STAGING" > /tmp/claude-sync-plugins.json
cat /tmp/claude-sync-plugins.json
```

출력 JSON의 `status`로 분기한다.

- `"skipped"`: `settings.json`을 읽지 못했거나, **레포 파일의 형식을 알아볼 수 없다**(상위 버전이 쓴 백업일 수 있다). 어느 쪽이든 **레포의 `plugins.json`은 손대지 않았고 base도 전진시키지 않는다.** `reason`을 알리고 플러그인 단계만 건너뛴다. **파일 동기화는 그대로 진행한다.**

  `reason`이 "형식을 알아볼 수 없다"이면 이 기기의 플러그인이 낡은 것이므로 **업데이트를 안내한다**: `claude plugin marketplace update claude-sync && claude plugin update claude-sync`.
- `"ok"`: `sections`의 세 섹션을 각각 보고한다. 섹션 하나가 `"skipped"`여도 **나머지는 정상 처리된 것이다** — 그 섹션의 레포 내용과 base는 이전 상태 그대로 보존된다.

| 섹션의 키 | 의미 | 안내 |
|---|---|---|
| `conflicts.repo_kept` | 케이스 9 — 양쪽이 바뀜 | "양쪽이 바뀌었습니다. 레포 값을 그대로 두었습니다. `/sync-restore`에서 해소하세요" |
| `conflicts.repo_absent` | 케이스 5 — 타 기기 삭제 + 로컬 수정 | "다른 기기가 삭제했는데 이 기기에서 바꿨습니다. `/sync-restore` 먼저 실행하세요" |
| `local_stale` | 케이스 4 — 타 기기가 삭제, 로컬 잔존 | "`/sync-restore`에서 정리하세요" |
| `repo_ahead.absent` | 케이스 2 — 타 기기가 추가 | "다른 기기가 추가했습니다. `/sync-restore`가 이 기기에 설치합니다" |
| `repo_ahead.present` | 케이스 8 — 타 기기가 **변경** | "다른 기기가 **변경**했습니다. `/sync-restore`에서 채택할지 선택이 필요합니다" |
| `deleted` | 이 기기에서 지운 항목 | 레포에서도 제거되었음을 알린다 |
| `held.auto` | 의존성으로 설치된 플러그인 | **백업하지 않는다.** 부모를 복원하면 따라옵니다 |
| `held.local_marketplace` | 로컬 디렉토리 마켓플레이스와 그 소속 플러그인 | **동기화되지 않습니다** — 다른 기기에는 등록할 소스가 없습니다 |
| `held.extended_value` | 버전 제약(배열·객체)이 있는 플러그인 | "레포의 값을 보존했습니다. 이 기기 값으로 통일하려면 `/sync-restore`에서 고르세요" |
| `held.declined` | 설정 입력을 건너뛴 항목 | 조용히 둔다. 레포 값이 바뀌면 다시 보고된다 |

`repo_ahead.present`(케이스 8)에 케이스 2와 같은 문구를 쓰면 안 된다 — restore는 케이스 8을 자동 반영하지 않으므로 그 안내는 사실이 아니고, 사용자가 빠져나갈 수 없는 루프에 갇힌다.

최상위 `orphaned`가 비어 있지 않으면 **마켓플레이스가 등록되지 않은 플러그인**이 레포에 있다는 뜻이다. 차단하지 않는다. 그 목록을 보여주고, 해당 마켓플레이스를 가진 기기에서 `/sync-backup`을 실행하면 해소된다고 안내한다.

`base_staging`이 `"failed"`이면 **레포는 갱신됐지만 base 스테이징이 실패한 것이다.** `base_staging_reason`을 그대로 보여준다. 다음 백업이 복구한다.

충돌이 있어도 백업 전체를 막지 않는다. 해당 항목만 건너뛴다.
````

**(b) 6단계.** 첫 bash 블록에서 `MCP_STAGING` 정의와 `rm -rf`를 지우고 `BASE_STAGING`을 쓴다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"
python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$BASE_STAGING" > /tmp/claude-sync-mcp.json
cat /tmp/claude-sync-mcp.json
```

**(c) 10단계.** MCP 전용 게이트를 두 relpath 루프로 교체한다.

```bash
# base: 레포가 실제로 그 내용을 갖게 된 뒤에만 기록한다.
# 스테이징 최종 파일은 수집 스크립트가 **레포 쓰기에 성공한 뒤** rename으로 만든다.
# 따라서 파일 존재가 곧 "레포까지 반영됨"이다 — status 값을 다시 읽을 필요가 없다.
RELS=()
for rel in plugins.json mcp-servers.json; do
  [ -f "$BASE_STAGING/$rel" ] && RELS+=("$rel")
done
if [ "$REPO_HAS_CONTENT" = "1" ] && [ ${#RELS[@]} -gt 0 ]; then
  python3 "$SYNC_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"
  echo "base 갱신됨: ${RELS[*]}"
fi
```

같은 절의 `MCP_STAGING=` 정의 줄도 `BASE_STAGING=`으로 바꾼다. 11단계의 설명에서 `$MCP_STAGING`을 `$BASE_STAGING`으로 고치고, 금지 예시(`update_base.py "$SYNC_REPO" ...`)는 **그대로 둔다.**

**(d) `sync-status/SKILL.md` 2단계.** MCP 호출 블록 **앞**에 플러그인 호출을 넣는다.

````markdown
파일 분석 이후, 플러그인과 MCP 서버 비교를 각각 수행한다:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -f "$SYNC_REPO/plugins.json" ]; then
  python3 "$SYNC_SCRIPTS/compare_plugins.py" "$SYNC_REPO/plugins.json"
fi
```

출력 JSON의 `status`가 `"skipped"`면 `settings.json`을 읽지 못했거나 레포 파일의 형식을 알아볼 수 없는 것이다. `reason`을 알리고 플러그인 비교만 생략한다 — 읽기 실패를 "0개"로 오인해 레포의 항목을 전부 `only_repo`로 보고하지 않기 위해서다. 섹션 하나만 `"skipped"`인 경우도 있다(`auto` 판정 불가 → `enabledPlugins`·`pluginConfigs`, 보류 파일 손상 → `pluginConfigs`).

섹션별로 보고한다.

- `only_local` — 로컬에만 있음. `/sync-backup`이 판정합니다
- `only_repo` — 레포에만 있음. `/sync-restore`가 이 기기에 설치합니다. **다만 `unrestorable`에 있는 항목은 "이 기기에서는 복원할 수 없습니다"로 말한다**
- `changed` — 양쪽에 있으나 값이 다름. **켬/끔 변경이 여기 포함된다.** 값이 확장 포맷이면 "버전 제약"으로 말한다. **방향과 값은 `changed_detail[<키>]["local"]`·`["repo"]`에서 읽는다** — 레포 파일을 다시 파싱하면 status 경로에 파서가 두 벌이 되어 결함 B가 되살아난다. 값은 이미 정규화돼 있어 비밀은 마스킹된 채로 온다
- `held.auto` / `held.local_marketplace` / `held.extended_value` / `held.declined` — 종류별 문구로 보고하거나 침묵한다. **`only_local`·`changed`로 말하지 않는다** — 백업하지 않는 항목을 "backup 시 추가"라고 하면 거짓이고 사용자가 해소할 수도 없다
- `absent_locally` — 보류 키 중 **로컬 섹션 문서에 값이 없는** 것. 여기 있는 항목에 "레포 값을 보존합니다"만 말하면 거짓이다(보존할 로컬 값이 없다). **"미설치"라고는 말하지 않는다** — compare는 설치 여부를 알 수 없다(`installed_plugins.json`에서 읽는 것은 auto 집합뿐이고, `enabledPlugins`의 키 부재는 매니페스트 기본값 위임이지 미설치가 아니다). 9.2의 "설치됨/미설치" 문구를 글자 그대로 쓰려면 설치 집합 전체를 읽어야 하며, **그럴지 말지는 이 task에서 정한다**

status는 아무것도 바꾸지 않는다. base를 읽지도 갱신하지도 않는다.
````

기존의 "파일/플러그인 분석 이후, MCP 서버 비교도 수행한다" 문장을 위 문단으로 대체하고, 3단계의 "플러그인" 관련 서술이 있으면 위 어휘와 맞춘다.

**(e) `check_status.py`.** 59~76행(플러그인 비교 블록)과 이제 쓰이지 않는 `import json`을 지운다. 마지막 `print()`는 남긴다.

**(f) `sync-restore/SKILL.md` 5절.** `### 5. 플러그인 복원 (additive)`을 아래로 교체한다. **제목의 `### 5. 플러그인 복원` 접두는 유지한다**(`test_script_root.py:195`가 그것으로 절을 자른다). **자기 업데이트 안내(206~212행)는 그대로 보존한다.**

````markdown
### 5. 플러그인 복원

**2.5단계에서 버전 경고가 있었다면 이 안내를 가장 먼저 보여준다.** (기존 자기 업데이트 문단 그대로)

레포 `plugins.json`과 로컬 상태를 비교해 계획을 세운다. `claude plugin list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"
rm -rf "$BASE_STAGING"
python3 "$SYNC_SCRIPTS/plan_plugins.py" plan "$SYNC_REPO/plugins.json" > /tmp/claude-sync-plugins-plan.json
cat /tmp/claude-sync-plugins-plan.json
```

`status`가 `"skipped"`면 `reason`을 알리고 플러그인 단계 전체를 건너뛴다(파일 복원은 그대로 진행한다). `reason`이 형식 문제이면 `claude plugin marketplace update claude-sync && claude plugin update claude-sync` 후 다시 시도하도록 안내한다. 섹션 하나만 `"skipped"`일 수도 있다 — 그 섹션의 복원만 건너뛴다.

#### 5-1. 마켓플레이스 등록

`marketplace_add`의 각 항목을 등록한다. `skipped_always_known`은 **등록하지 않는다** — 내장이거나 의사 출처라 시도하면 반드시 실패한다.

```bash
claude plugin marketplace add <arg> --scope user
```

`reserved`가 `true`인 항목은 실패할 수 있다. 실패하면 "이 이름은 공식 마켓플레이스용으로 예약되어 있습니다"로 갈래를 구별해 보고한다.

#### 5-2. 플러그인 설치

`install` 목록을 설치한다. **`depends_on`이 가리키는 마켓플레이스의 등록이 실패했다면 그 항목은 시도하지 않는다** — 등록되지 않은 상태로 install하면 CLI가 "플러그인이 없다"와 **똑같은 문구**로 실패해 사용자가 원인을 알 수 없다. `blocked`로 모아 "마켓플레이스 등록이 실패해 건너뛰었습니다"로 보고한다.

```bash
claude plugin install <id> --scope user
```

**`-y`를 붙이지 않는다.** 마켓플레이스가 명령으로 설치를 선언한 플러그인은 세션 안에서 설치할 수 없다 — 우회할 대상이 아니라 그대로 존중할 경계다. 실패하면 CLI가 출력한 문구를 **그대로** 전달한다. CLI가 이미 실행할 명령 전문과 승인 방법을 알려준다.

#### 5-3. 값 맞추기

`disable_after_install`의 항목만 끈다. 설치 직후 값은 `true`이므로 그 외에는 부를 것이 없다 — **`enable`/`disable`은 멱등이 아니라** 현재 상태와 같으면 exit 1로 거짓 실패를 낸다.

```bash
claude plugin disable <id> --scope user
```

#### 5-4. 설정 채우기

`config_keys`에 실린 키를 사용자에게 묻는다. **레포에는 마스킹된 값만 있으므로 그대로 등록하면 동작하지 않는 항목이 설치된다.**

```bash
claude plugin install <id> --config <key>=<value> --scope user
```

세 결과가 모두 1급 상태다.

| 결과 | 처리 |
|---|---|
| 전부 입력 | 그대로 실행. 다음 status에서 in_sync |
| **일부 입력** | 입력한 키만 채운다. 입력하지 않은 키 때문에 항목이 계속 `changed`가 되므로 그 항목을 **보류**로 만든다(`declined`) |
| 전부 건너뜀 | 플러그인은 설치하고 설정만 비운다. 항목을 **보류**로 만든다(`declined`) |

값을 입력하지 않아도 **플러그인 자체는 설치한다.** 나중에 채우는 방법을 보고서에 안내한다.

#### 5-5. 세 선택지 — 케이스 4·5·8·9

| 버킷 | 상황 | 문구 |
|---|---|---|
| `local_stale`(케이스 4) | 다른 기기가 지웠고 이 기기는 base와 같다 | "다른 기기가 지웠습니다" |
| `local_stale`(케이스 5) | 다른 기기가 지웠는데 이 기기에서 바꿨다 | "다른 기기가 지웠는데 이 기기에서 바꿨습니다" |
| `repo_ahead`(케이스 8) | 다른 기기가 바꿨고 이 기기는 옛 값이다 | "다른 기기가 변경했습니다" |
| `both_changed`(케이스 9) | 양쪽이 다르게 바꿨다 | "양쪽이 모두 바뀌었습니다. 채택하면 이 기기의 변경이 사라집니다" |

세 선택지: **레포 따르기 / 로컬 유지(다음 백업에 올리기) / 이번엔 넘어가기.** 넷 다 **안정 상태**이므로 사용자가 고르지 않으면 영원히 유지된다.

- 레포 따르기 — `repo_values`의 값에 맞춰 `enable`/`disable`을 실행한다(값이 같으면 부르지 않는다). base override는 없다.
- 로컬 유지 — 케이스 4·5는 `keep_stale`, 케이스 8·9는 `keep_local`에 넣는다. **한 조작이 아니다**(5-7).
- 이번엔 넘어가기 — 아무것도 하지 않는다.

**삭제 전파.** 레포에 키가 있고 값이 `false`면 다른 기기가 **껐다**는 뜻이므로 `disable`을 제안한다. 레포에 키가 **없고** base에 있었으면 다른 기기가 **지웠다**는 뜻이므로 `uninstall --scope user`를 제안한다. 둘 다 사용자 확인을 받고 실행한다. **부재는 `false`가 아니다** — 레포에 키가 아예 없는 항목을 `disable` 대상으로 삼지 않는다.

**마켓플레이스의 `local_stale`은 삭제를 자동 실행하지 않는다.** `claude plugin marketplace remove`가 **소속 플러그인 키를 연쇄 삭제**하기 때문이다. 선택지는 **유지**(`keep_stale` — 다음 백업이 레포로 되돌린다)와 **이번엔 넘어가기** 둘이다. 제거를 원하면 명령만 안내하고, 함께 적는다: `--scope`를 생략하면 **모든 스코프**에서 제거되고, 그 마켓플레이스 소속 플러그인 키가 **전부 사라지며**, 손으로 실행하면 다음 백업이 그 삭제를 레포로 전파한다.

#### 5-6. 확장 포맷 값 — `value_held`

`value_held`에 있는 항목은 **설치돼 있고 값만 레포를 따르는 상태**다. "양쪽이 모두 바뀌었습니다"라고 말하지 않는다 — 사실이 아니고, 배열 값을 쓸 CLI도 없다.

> "설치했습니다. 다만 이 기기는 버전 제약을 표현할 수 없어 레포의 값을 보존합니다."

`absent_locally`에 있는 항목에는 "보존합니다"만 말하지 않는다 — 보존할 로컬 값이 없으면 거짓이 된다.

**탈출구**: "버전 제약을 포기하고 이 기기 값으로 통일한다"를 고르면 그 id를 `release`에 넣는다. 다음 백업이 이 기기의 값을 push해 레포 값이 불리언이 되고 보류가 자연 해제된다.

**지우고 싶을 때도 이 탈출구를 먼저 써야 한다.** H3의 조건은 **레포 값**이므로 로컬에서 `uninstall`해도 보류가 유지되어 삭제가 전파되지 않고, 다음 restore가 **다시 설치한다.** 순서는 ① 탈출구로 값을 불리언화 → ② 백업 → ③ `uninstall` → ④ 백업이다.

`action_held`에 있는 항목에는 **어떤 명령도 실행하지 않는다.** 종류별로 한 번만 안내한다.

#### 5-7. base 갱신

**사용자가 아무 선택도 하지 않았어도 실행한다.** 무선택은 "이전 base 유지"로 계산되므로 결과가 달라지지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"

# 5-5에서 "로컬 유지"를, 5-4에서 "건너뜀"을, 5-6에서 "이 기기 값으로 통일"을 고른
# 항목만 적는다. 나머지 선택(레포 따르기·이번엔 넘어가기)에는 override가 필요 없다.
# **이 파일에는 이름과 선택만 들어간다 — 비밀 값은 절대 담지 않는다.**
cat > /tmp/claude-sync-plugins-choices.json << 'EOF'
{"enabledPlugins": {"keep_stale": [], "keep_local": [], "release": []},
 "extraKnownMarketplaces": {"keep_stale": [], "keep_local": []},
 "pluginConfigs": {"keep_stale": [], "keep_local": [], "declined": [], "configured": []}}
EOF

python3 "$SYNC_SCRIPTS/plan_plugins.py" apply-base "$SYNC_REPO/plugins.json" "$BASE_STAGING" /tmp/claude-sync-plugins-choices.json
rm -f /tmp/claude-sync-plugins-choices.json
```

`configured`에는 **5-4에서 값을 입력한** 항목을 적는다 — 적지 않으면 이전에 건너뛴 항목의 보류가 풀리지 않아 영영 조용한 상태로 남는다.

`apply-base`는 `settings.json`을 **다시 읽어** 계산하므로 5-1~5-6의 CLI 실행이 **모두 끝난 뒤**에 호출해야 한다. 실패했거나 건너뛴 항목은 로컬에 없으므로 base가 자동으로 전진하지 않는다.
````

**(g) `sync-restore/SKILL.md` 6-6.** MCP의 base 갱신 블록에서 `rm -rf`를 지우고(5절로 옮겼다) `BASE_STAGING`을 쓰며, `update_base.py` 호출을 두 relpath 루프로 바꾼다.

```bash
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"
python3 "$SYNC_SCRIPTS/plan_mcp.py" apply-base "$SYNC_REPO/mcp-servers.json" "$BASE_STAGING" /tmp/claude-sync-mcp-choices.json
rm -f /tmp/claude-sync-mcp-choices.json

RELS=()
for rel in plugins.json mcp-servers.json; do
  [ -f "$BASE_STAGING/$rel" ] && RELS+=("$rel")
done
if [ ${#RELS[@]} -gt 0 ]; then
  python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"
  echo "base 갱신됨: ${RELS[*]}"
fi
```

**(h) `extract_plugins.py` 삭제.**

```bash
git rm plugins/claude-sync/skills/sync-backup/scripts/extract_plugins.py
```

**(i) 7절 결과 보고**에 플러그인 항목을 더한다 — 설치/보류/실패/건너뛴 설정, `orphaned`, 그리고 **"버전 때문에 보류한 항목"과 `held`를 구별해 보고**한다.

실패는 **항목 단위로 독립**이고 종료 코드는 0이다(10.3) — 그래야 안내가 보인다. 수집 형태를 문단으로 못박는다(spec 10.1).

````markdown
플러그인 복원의 실패는 항목마다 아래 형태로 모아 보고한다. **`stderr`를 요약하지 않는다** — CLI의 문구가 가장 유용한 안내인 경우가 많다(명령 기반 설치가 그렇다).

```json
{ "id": "...", "step": "marketplace_add|install|enable|disable|config",
  "command": "실행한 명령 전문", "exit": 1, "stderr": "CLI가 낸 문구 전문" }
```

실행되지 않은 항목(5-2의 `blocked`, `unrestorable`)은 `command`도 `exit`도 없다. 별도 형태를 쓴다.

```json
{ "id": "...", "step": "install", "blocked_by": "marketplace_add:<name>",
  "reason": "마켓플레이스 등록이 실패해 건너뛰었습니다" }
```

`unrestorable`은 계획의 `unrestorable_reasons`를 그대로 쓴다. **실패 건수로 세지 않는다** — 시도하지 않았기 때문이다.
````

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

- `rm -rf "$BASE_STAGING"`을 6단계로 옮기기 → 순서 가드가 잡아야 한다
- 10단계 루프에서 `plugins.json`을 빼기 → 두 relpath 가드가 잡아야 한다
- `update_base.py "$BASE_STAGING"`을 `"$SYNC_REPO"`로 바꾸기 → **어떤 테스트도 잡지 못한다.** `test_plugin_cycle.py`에 "base가 레포 파일 바이트와 같지 않다"를 거는 단정을 하나 더할지 판단한다
- restore 5-2의 `--scope user`를 지우기 / `-y`를 붙이기 → 명령 가드가 잡아야 한다
- 5-5의 `marketplace remove`를 bash 블록 안으로 옮기기 → 실행 금지 가드가 잡아야 한다
- `check_status.py`의 플러그인 블록을 되살리기 → status 가드가 잡아야 한다
- 4.5단계를 다시 5.5로 되돌리기 → 탐지 순서 가드가 잡아야 한다

- [ ] **Step 5: Commit**

```bash
git add -A plugins/claude-sync/skills plugins/claude-sync/tests/test_script_root.py
git commit -m "feat(skills): 세 스킬을 새 플러그인 스크립트에 배선하고 extract_plugins를 지운다"
```

---

### Task 15: 문서 정정 여덟 곳과 새 한계

**근거:** spec 13장 첫 표의 1~8행, "새로 적어야 할 한계"

**한 곳만 고치면 나머지가 옛 서술을 계속 말한다.** 13장의 표는 `grep`으로 확인한 전수다. 9·10행(`sync-status/SKILL.md`·`sync-restore/SKILL.md`)은 Task 14가 배선과 함께 이미 고쳤다.

**영어 README를 빠뜨리지 말 것.** `README.ko.md:98`에 해당하는 문장이 영어판에는 없으므로, 한국어판 기준으로만 지시하면 **영어 README는 아무것도 고쳐지지 않는다.**

13장의 두 번째 표(2.x 배포 순서 경고 **네 곳**)와 마지막 세 행(다운그레이드 대화)은 **plan ③의 몫이다** — 그쪽은 `plugins.json`의 다운그레이드 탐지가 실제로 붙은 뒤에 고쳐야 문구가 사실이 된다.

**Files:**
- Modify: `README.md`, `README.ko.md`
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md`, `backup-readme.ko.md`
- Modify: `plugins/claude-sync/skills/sync-backup/SKILL.md:33·36·42`
- Modify: `plugins/claude-sync/tests/test_script_root.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_script_root.py` 끝에 추가한다.

```python
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
BACKUP_READMES = [os.path.join(SKILLS_DIR, "sync-backup", "scripts", name)
                  for name in ("backup-readme.md", "backup-readme.ko.md")]
USER_DOCS = [os.path.join(ROOT, "README.md"), os.path.join(ROOT, "README.ko.md")] + BACKUP_READMES

STALE_CLAIMS = (
    "overwritten wholesale", "regenerated and overwritten",
    "통째로 덮어쓰", "매 백업마다 새로 생성되어 덮어쓰",
    "no sensitive data", "민감 정보 미포함", "민감 정보 제외",
    "only the plugin list is extracted", "플러그인 목록만 추출",
)


@pytest.mark.parametrize("path", USER_DOCS, ids=os.path.basename)
def test_user_docs_do_not_repeat_the_old_plugins_story(path):
    """13장 — 한 곳만 고치면 나머지가 옛 서술을 계속 말한다.

    "통째로 덮어쓴다"는 이제 거짓이고, "민감 정보 제외"도 거짓이다 —
    pluginConfigs를 **마스킹해서** 싣기 때문이다.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    found = [claim for claim in STALE_CLAIMS if claim in text]
    assert found == [], "%s에 옛 서술이 남아 있다: %s" % (os.path.basename(path), found)


@pytest.mark.parametrize("path", USER_DOCS, ids=os.path.basename)
def test_user_docs_state_the_new_limits(path):
    """새 한계를 적지 않으면 사용자가 "동기화되겠지"라고 믿는다."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "key by key" in text or "키 단위" in text


def test_backup_skill_lists_all_three_fields_and_the_auto_source():
    """SKILL.md:33·36 — "두 필드만 추출"은 이제 거짓이다."""
    text = read_skill("sync-backup")
    for token in ("pluginConfigs", "additionalMarketplaces", "installed_plugins.json"):
        assert token in text, token
    assert "두 필드만" not in text
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_script_root.py -q`
기대: 문서 가드 FAIL

- [ ] **Step 3: 구현**

**`README.md`** — 세 곳.

```markdown
- `~/.claude/settings.json` -> `plugins.json` — Plugin list, marketplaces, and plugin config **key names** (config values are masked)
```

```markdown
- **`plugins.json` merges key by key.** Plugin entries, marketplaces, and plugin config keys are reconciled individually, so a backup from one machine never drops entries that only exist on another. Deletions propagate, and `/sync-restore` asks before removing anything locally.
```

```markdown
- **Sensitive data protection**: The raw `settings.json` is never pushed — three fields are extracted and `pluginConfigs` values are masked as `<REDACTED>` (key names are kept so a restore knows what to ask for). MCP server configs are pushed with `headers`/`env` values masked the same way
```

**`README.ko.md`** — 네 곳(영어판에 없는 `:98` 예외 문구 포함).

```markdown
- `~/.claude/settings.json` -> `plugins.json` — 플러그인 목록, 마켓플레이스, 플러그인 설정 **키 이름** (설정 값은 마스킹)
```

```markdown
- **`plugins.json`은 키 단위로 병합됩니다.** 플러그인 항목·마켓플레이스·설정 키가 각각 판정되므로, 한 기기의 백업이 다른 기기에만 있는 항목을 지우지 않습니다. 삭제는 전파되지만 로컬 제거는 `/sync-restore`가 물어본 뒤에만 이루어집니다.
```

`## 안전 장치`의 충돌 감지 항목에서 **`plugins.json` 예외 문구를 지운다**(더 이상 예외가 아니다).

```markdown
- **충돌 감지**: 마지막 공유 base 이후 양쪽에서 변경된 파일만 충돌로 표시하며, 로컬 파일은 절대 자동으로 덮어쓰지 않습니다.
- **민감 정보 보호**: `settings.json` 원본은 레포에 올리지 않고 세 필드만 추출하며, `pluginConfigs`의 값은 `<REDACTED>`로 마스킹합니다(키 이름은 복원 시 무엇을 물어야 하는지 알기 위해 남깁니다). MCP 서버 설정도 `headers`/`env` 값을 같은 방식으로 마스킹해 올립니다
```

**`backup-readme.md`** — 두 곳.

```markdown
- `plugins.json` — Plugin list, marketplaces, and plugin config key names (extracted from settings.json; config values masked)
```

```markdown
This file is merged **per server name**, so backing up from one machine will not drop servers that only exist on another. `plugins.json` is merged the same way, key by key, across its three sections.
```

**`backup-readme.ko.md`** — 두 곳.

```markdown
- `plugins.json` — 플러그인 목록·마켓플레이스·설정 키 이름 (settings.json에서 추출, 설정 값은 마스킹)
```

```markdown
이 파일은 **서버 이름 키 단위로 병합**되므로 한 기기에서 백업해도 다른 기기에만 있는 서버가 사라지지 않습니다. `plugins.json`도 세 섹션 각각에 대해 같은 방식으로 키 단위 병합됩니다.
```

**`sync-backup/SKILL.md:33·36·42`.**

```markdown
| `~/.claude/settings.json` → 추출 | `plugins.json` | 플러그인·마켓플레이스·설정 키 (설정 값은 마스킹) |
```

```markdown
settings.json에는 API 키 등 민감 정보가 포함될 수 있으므로 원본은 레포에 올리지 않는다. `enabledPlugins`, `extraKnownMarketplaces`(별칭 `additionalMarketplaces`도 읽는다), `pluginConfigs` 세 필드를 추출하고 `pluginConfigs`의 값은 `<REDACTED>`로 마스킹한다. 의존성으로 자동 설치된 플러그인을 가려내기 위해 `~/.claude/plugins/installed_plugins.json`의 `auto` 플래그도 읽는다(값의 원천으로는 쓰지 않는다).
```

`:42`의 *"반면 `plugins.json`은 여전히 매 백업마다 통째로 새로 생성되어 덮어쓰인다"* 문단을 교체한다.

```markdown
`plugins.json`도 **섹션별 키 단위 3-way 병합** 대상이다. 다른 기기가 추가·변경한 플러그인·마켓플레이스·설정 키는 이 기기의 백업으로 사라지지 않는다.
```

**새 한계**를 두 README와 두 backup-readme에 한 문단으로 더한다(영어판·한국어판 모두).

```markdown
동기화되지 않는 것:

- 마켓플레이스 **자동 업데이트 설정**(`autoUpdate`) — CLI에 이를 설정할 수단이 없습니다
- **로컬 디렉토리에서 등록한 마켓플레이스와 그 소속 플러그인** — 다른 기기에는 등록할 소스가 없습니다
- **의존성으로 자동 설치된 플러그인** — 부모를 복원하면 따라옵니다
- **명령으로 설치되는 플러그인** — 세션 안에서 복원할 수 없어 사용자 터미널이 필요합니다
- **버전 제약(배열·객체)의 값** — 설치는 되지만 그 값이 이 기기에 재현되지 않습니다. 레포의 값은 보존되며, 포기하려면 복원에서 "이 기기 값으로 통일"을 골라야 합니다. **지우려면 그것이 먼저입니다**
- **플러그인 설정 값** — 마스킹되어 저장되며 복원 시 다시 입력합니다. 건너뛸 수 있습니다
- **보류 선택**(`~/.claude/.sync-state/plugins-held.json`) — 이 기기에만 남고 다른 기기로 번지지 않습니다. 지우면 다시 묻습니다
```

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

실행: `grep -rn "통째로 덮어쓰\|overwritten wholesale\|민감 정보 제외\|no sensitive data" README.md README.ko.md plugins/claude-sync/skills/`
기대: **출력 없음.** 13장이 요구한 전수 확인이다.

- [ ] **Step 4b: 변조 확인 (필수)**

- `STALE_CLAIMS`에서 항목을 하나씩 지우기 → 그 문구를 되살렸을 때 가드가 통과해 버리는지 확인한다(목록이 실제로 전수인지 검증)
- 정정한 문장 하나를 옛 문장으로 되돌리기 → 대응 가드가 FAIL해야 한다
- **영어 README만 되돌리기** → 파라미터화된 가드가 그 파일에서 FAIL해야 한다. 한국어판만 보는 가드였다면 여기서 드러난다

- [ ] **Step 5: Commit**

```bash
git add README.md README.ko.md plugins/claude-sync/skills plugins/claude-sync/tests/test_script_root.py
git commit -m "docs: plugins.json이 키 단위로 병합된다는 사실을 여덟 곳에 반영한다"
```

---

## 완료 정의

- [ ] `uv run --with pytest pytest plugins/claude-sync/tests -q` → **0 failed.** 개수는 게이트가 아니다 — 리뷰 후속 커밋이 테스트를 더한다
- [ ] **`PLAN_SHA`를 정한다** — 이 plan 문서를 커밋한 지점의 sha다. `git log --oneline -1 -- docs/superpowers/plans/2026-08-25-plugins-sync-body.md`로 확인한다. `main..HEAD`를 쓰면 안 된다 — 이 테스트 파일들이 `main`에 없어 전부 신규 추가로 잡힌다
- [ ] `git diff --stat $PLAN_SHA..HEAD -- plugins/claude-sync/tests/test_mcp_cycle.py` → **출력 없음.** MCP 교대 시나리오는 이 plan이 건드리지 않는다
- [ ] `git diff --stat $PLAN_SHA..HEAD -- plugins/claude-sync/tests/test_mcp_config.py` → Task 1의 원자성 테스트 **하나만** 추가돼 있다. 그 외 변경이 있으면 어댑터 계약이 바뀐 것이다
- [ ] `grep -rn "extract_plugins" plugins/claude-sync/` → **출력 없음**
- [ ] `grep -rn "MCP_STAGING" plugins/claude-sync/` → **출력 없음** (`BASE_STAGING`으로 통일됐다)
- [ ] `python3 -c "import sys; sys.path.insert(0,'plugins/claude-sync/lib'); import plugin_config as p, keyed_sync as k; assert p.UnknownBackupSchema is k.UnknownBackupSchema"` → 조용히 종료
- [ ] `test_mcp_state_machine.py`의 판정표 시나리오가 **어댑터 셋**으로 돈다 (`-v`로 `[mcp]`·`[plugins:extraKnownMarketplaces]`·`[plugins:pluginConfigs]` 확인)
- [ ] `test_recognize_adapter_list_covers_every_keyed_sync_importer`가 `plugin_config`를 포함한 채 통과한다
- [ ] spec 14.1의 표 24행 각각에 대응하는 테스트를 짚을 수 있다. 짚지 못하는 행이 있으면 **그 행이 이 plan의 누락이다**
- [ ] `/sync-backup`을 **실행하지 않았다** — 이 개발 기기의 캐시는 아직 `claude-sync/2.0.0`이고, 실행하면 레포가 파괴된다

## 다음 plan으로 넘길 것

| 항목 | 근거 |
|---|---|
| `lib/compat.py`의 `plugins.json`용 shape 상수, `downgrade_suspected`의 relpath별 분기 | spec 11.6 |
| `detect_downgrade.py`의 형태 판정 파라미터화, `find_last_v2_commit` | spec 11.6 |
| `generate_metadata.py`의 `schema` 맵에 `plugins.json: 2`, `test_metadata.py:93`의 단정 뒤집기 | spec 11.3 |
| v1 → v2 승격 중 다운그레이드 사고 판별(레포에 `version` 없음 + base에 `version: 2`) | spec 11.4 |
| 다운그레이드 3선택지 대화 문단 셋(`sync-backup:262-278`·`sync-restore:142·144·331-338`·`sync-status:96`) | spec 13장 |
| 2.x 배포 순서 경고 **네 곳** — 전부 `mcp-servers.json` 전용이다 | spec 13장 두 번째 표 |
| 실환경 스모크 — 확장 포맷의 의도된 형태, 객체 평탄화의 성격, `install`의 기본 스코프 | spec 14.5 |
| **`update_base.py "$BASE_STAGING"` 오사용을 잡는 테스트가 없다** | Task 14 Step 4b에서 확인된 구멍 |
| **`reconcile_restore.py:108-111·126-129`의 비원자적 로컬 쓰기** — `open(local,"wb")`가 선-truncate한다. ENOSPC로 중간에 죽으면 `~/.claude/agents/foo.md`가 **잘린 채** 남고, 예외가 traceback으로 서서 `write_base`가 실행되지 않아 base는 옛 값 그대로다. 다음 판정이 `L≠S, R==S` → `local_ahead` → **다음 백업이 잘린 로컬을 레포의 온전한 사본 위에 push한다.** Task 1이 막은 것과 같은 계열이다. `ks.dump_bytes`가 생겼으므로 두 곳 다 한 줄 교체다 | Task 1 quality review I3 |
| 고정 `.tmp` 이름은 동시 실행에서 원자성이 무력화된다. 코드베이스에 락이 하나도 없어(전수 grep 0건) 동시 실행을 전제하지 않는 설계와는 일관된다. `mkstemp`로 바꾸면 잔존 파일 이름이 무작위가 되어 `.gitignore` 대응이 어려워지는 역효과가 있다 | Task 1 quality review M3 |
| `sync_state.write_base`의 `data is None` 삭제 분기가 `<path>.tmp`를 지우지 않는다. base 디렉토리를 walk하는 코드가 없어 현재 영향은 없다 | Task 1 quality review M4 |
| 백업 레포에 `.gitignore`가 없다(`bootstrap.sh`가 만들지 않는다). `*.tmp` 한 줄이 값싼 보험이다 | Task 1 quality review |
| `/sync-status`의 `unrestorable`이 **키 목록뿐**이라 "의사 출처라 원래 불가능"과 "레포에 소스가 없으니 백업한 기기에서 올려라"를 가르지 못한다. 어댑터가 훅 다섯 번째 키로 `reason`을 이미 준비해 뒀으므로 `unrestorable_reasons` 별도 키를 얹으면 기존 리스트 모양을 깨지 않고 해소된다. **spec 9.2는 status에 구별만 요구하고 사유는 요구하지 않으므로** 넣으려면 spec부터 고쳐야 한다 | Task 8 implementer 관찰 |
| `conflicts`·`repo_ahead`의 보고 분할이 `collect_mcp.py`와 `collect_plugins.py`에 축자 중복이다. 같은 소비자(SKILL.md)가 읽는 같은 모양인데 정의가 두 곳이라 한쪽만 고쳐질 수 있다. 코어에 넣는 것은 계층이 어긋나므로(코어는 값 무관 판정이지 보고 층이 아니다) 다른 자리를 찾아야 한다. 현재는 **양쪽 다 테스트로 잠겨** 표류 위험이 낮다 | Task 7 quality review I-3 |
| 보류 종류를 하나 더하려면 네 곳(`_make_hold`의 `if` / `HELD_KINDS` / `held_kinds`의 `if` / 배선)을 동시에 고쳐야 하고 어긋나면 런타임 `ValueError`로만 드러난다. 그 `ValueError`가 fail-closed 가드로 설계된 것이고 다섯 번째 종류는 계획에 없어 YAGNI로 미뤘다 | Task 5 quality review I-2 |
| `test_keyed_sync.py`의 `RECOGNIZE_HOOK_CALL`이 별칭 `ks.`를 하드코딩한다. `NON_ADAPTER_KEYED_SYNC_IMPORTERS`의 모듈이 **별칭을 바꾸면서** 세 함수를 부르기 시작하면 자기검증이 우회된다(이중 변경이라 실현 가능성은 낮고, `test_sync_state.py`의 `ss.ks` 몽키패치가 그 별칭을 못박고 있다). 면제 목록이 커지면 AST로 올릴 것 | Task 3 quality review M-1 |
| `test_mcp_state_machine.py`의 이름이 더 이상 내용과 맞지 않는다 | Task 11 |

**plan ③은 이 plan이 끝나야 쓸 수 있다.** `plugin_config`의 인식 규칙과 `plugins.json`의 실제 v2 형태가 확정되어야 shape 상수와 다운그레이드 판정을 정의할 수 있다.
