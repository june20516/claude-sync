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

각 task의 `Step 4b`에서 **그 task가 도입한 가드 절을 하나씩** 뒤집고 대응 테스트가 FAIL하는지 임시 복사본에서 확인한다. 원본 작업 트리를 오염시키지 말 것. 다섯 축이 템플릿이다:

| 축 | 이 plan에서의 형태 |
|---|---|
| **훅 호출 계약** | `hold(local, repo)` 인자 순서·정규화 여부, `recognize`를 세 함수가 공유하는지, `build_hooks`를 레포 읽기 **뒤에** 부르는지 |
| **축 분리** | `value` ↔ `action` 맞바꾸기, `merge`에 `action`을 흘리기, `restore_plan`에서 `value_held`를 판정표에 태우기 |
| **`{}` vs `None`** | 부재 섹션을 `None`으로, 인식 실패를 `{}`로, `base=None` degrade를 `{}`로 |
| **I/O 층** | `open` 모드(`"rb"`→`"r"`), `except FileNotFoundError`→`except OSError`, 파일 부재를 예외로/예외를 부재로, `os.replace` 제거 |
| **입력 축** | **테스트가 준 입력을 뺀다** — 선택 인자(`choices`의 한 항목·`secrets`), 픽스처 값(레포 값을 확장 포맷→불리언, options를 비움), 회차(backup 2회→1회), 에뮬레이터가 만드는 **상태**(의존성 자식을 넣지 않음), 에뮬레이터 명령의 **규약**(멱등성·exit code·값의 모양 — "상태"가 이것을 덮지 않는다) |

**다섯째 축은 Task 13 품질 리뷰의 발견이다(실측).** 앞의 넷은 전부 **프로덕션 가드**를 뒤집는데, 그 축에서는 *"테스트가 준 입력이 단정을 좌우하지 않는다"*는 결함이 **원리적으로 나오지 않는다.** 이 축을 돌려야만 드러나는 SURVIVE가 Task 13 초판에 **다섯** 있었다(그 밖에 의도적으로 남긴 회차 카나리아 SURVIVE가 **셋** 따로 있다 — 아래 셋째 항목). 다섯 중 둘은 시나리오가 자기 주제(spec 6.3의 부분 입력)를 하나도 재지 않는데도 초록이었고, 하나는 에뮬레이터가 인용한 **실측 행**(N1)이 저장소 어디에도 고정되지 않은 자리였다.

**한 줄로 줄이면 이렇다: 시나리오를 적을 때 "이 입력을 빼면 단정이 죽는가"를 물어야 하고, 그 물음은 Step 1의 코드를 적는 단계에서 한 번, Step 4b에서 다시 한 번 물어야 한다.** 죽지 않는다면 그 시나리오는 자기 이름이 약속한 것을 재지 않는다.

**SURVIVE하면 구현이 아니라 테스트를 보강한다.** 보강한 줄 옆에 어떤 변조를 잡는지 주석으로 남긴다.

**이 공통 절을 고쳤다면 분할 파일을 다시 만들 것.** 이 절은 `00-shared-context.md`로 배포되고, 남은 task의 실행자가 실제로 읽는 것은 그쪽이다. `split-plan.py`는 **처음에 이 머리 부분을 출력에 넣지 않았고**, 그래서 `--check`가 이 절의 드리프트를 **구조적으로 볼 수 없었다** — Task 13에서 실제로 사고가 났다(본문에만 다섯째 축을 넣은 커밋이 `--check` 초록을 받았고, 커밋한 사람도 리뷰어도 그 초록을 근거로 삼았다). 도구를 고쳐 머리 부분도 `00-shared-context.md`로 내고 `--check`에 포함하게 했다(저장소 밖 파일이라 이 plan의 커밋에는 들어가지 않는다). **고친 뒤 실측**: 본문 머리만 바꾸고 배포를 잊으면 `불일치: ['00-shared-context.md']` exit 1, 옛 도구는 같은 입력에 `불일치: 없음` exit 0.

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

> **[2026-08-31 갱신 — spec 7.3]** H1~H4의 정의와 두 축은 **바뀌지 않았다.** 바뀐 것은
> H3의 근거 한 줄이다 — *"새 기기에서 `install`이 만드는 값은 `true`다"* 가 실측으로
> **"매니페스트의 `defaultEnabled`(기본 `true`)"** 가 됐다(스모크 7장). **결론은 같다**:
> 어느 쪽이든 **불리언**이므로 레포의 배열이 조용히 덮인다. 이 task의 코드는 바뀌지 않는다.
> 아래 *"버전 제약이 `true`로 덮이고"* 도 같은 이유로 정확히는 **"불리언으로 덮이고"** 다.

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

> **[2026-08-31 갱신 — spec 4차 개정 ⑤]** spec 8.6의 표에 **측정 여부 열**이 생겼다.
> `github` 행은 **왕복이 닫혔다**(2026-08-29 스모크 9장 — CLI가 쓰는 `repo` 필드와
> `marketplace_arg`가 내는 `"o/r"`가 일치한다). **`url`·`git` 행은 여전히 미측정이다** —
> https github URL이 github으로 정규화되므로 그 갈래는 raw `.json` URL이나 비-github
> 호스트에서만 나오고, 스모크 픽스처로는 만들 수 없었다. `_SOURCE_ARG_FIELDS`의
> `url`/`git` 필드 이름은 **짐작이다.** 이 task의 코드는 바뀌지 않는다(어댑터는 이미
> 정직하다) — **spec만 그 구별이 없었다.** 미측정 목록의 정본은 spec 14.5다.

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

> **[2026-08-31 갱신 — spec 4차 개정 ⑤]** 이 task가 도입한 `read_hold_inputs`의 계약이
> 넓어졌다. 아래 본문은 **3-튜플**(Task 10.5가 4-튜플로, `4b17f68`이 5-튜플로 늘렸다)
> 시점의 기록이다. 현행 계약과 근거는 spec **3.5**(신설)에 있다:
>
> - 반환은 `(auto_ids, installed_ids, held_state, {섹션: skip 사유}, {섹션: 판정 불가 사유})`
> - **다섯째는 skip과 다른 층이다.** 접지 않은 섹션에 `pc.with_degraded`로 사유만 얹고
>   `status`는 `"ok"`로 남는다. 키 이름을 `reason`과 **가르는 것이 계약이다** —
>   세 SKILL.md가 `reason`을 *"건너뛰었다"* 의 분기에서 읽으므로 같은 이름을 쓰면
>   **정상 처리된 섹션이 접힌 것으로 렌더링된다**(7.4의 `base_staging_reason`과 같은 근거)
> - 그 층이 생긴 이유는 **skip 범위 표에 없던 fail-open**이다 — `plugins-held.json`이
>   깨지면 `pluginConfigs`만 접히는데, 함께 잃는 `held_state["release"]`를 읽는 자리(H3
>   해제)는 **접히지 않는** `enabledPlugins`에 있다. spec 9.1.2 표의 마지막 행이 이제
>   그것을 적는다.
>
> **레포 문서의 「구문」 깨짐은 backup에서 그대로 `{}` degrade다**(사용자 결정). restore만
> 전체 skip으로 갈렸다(9.3.6) — 그 비대칭이 규정이다.

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

> **[2026-08-31 갱신 — spec 4차 개정 ⑤]** spec 9.2에 행이 하나 늘었다. **복원 가능성을
> 묻는 대상은 `diff`의 `only_repo`가 아니라 `route_new_keys`가 정한다**(5.2).
> 이 task의 초판이 `only_repo`를 훑었고, `4b17f68`(A-I1)이 코어의 `_route_new_names`
> 하나로 통일했다 — 어댑터 쪽 짝은 `pc.route_new_for(section, hooks, local, repo)`다.
>
> 두 집합은 **H3(확장 값) 보류이면서 레포 전용인 키에서 갈린다.** 갈리면 status는
> *"미설치 → restore가 설치"*, restore는 *"복원 불가"* 를 말한다 — 같은 기기에서 같은
> 키를 두고 **두 스킬이 반대로 말하는데 예외도 빈 결과도 나지 않는다.** H1·H2는 행동
> 보류이기도 해서 이 갈래에 오지 않으므로 갈리는 것은 H3 하나뿐이고, 그래서 더 조용하다.

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

> **[2026-08-31 갱신 — spec 4차 개정 ①②③④]** 이 task가 근거로 삼은 절 넷이 바뀌었다.
> **코드는 다음 라운드가 고친다**(spec 12.1). 여기서는 규정만 갱신한다.
>
> - **①(9.3.6)** — **레포 문서의 「구문」 깨짐이 restore에서 전체 skip**이 됐다.
>   지금 `build_plan`은 `pc.load_backup`이 깨진 파일을 `{}`로 degrade한 것을 그대로 받아
>   **모든 로컬 키를 `local_stale`로 낸다**(실측: `local_stale: ['a@m','b@m']` + 최상위
>   `status: "ok"`). 그것이 9.3.3의 `uninstall --scope user` 제안으로 이어진다 —
>   **거짓 근거로 만든 파괴적 제안**이다. 다음 라운드가 `{"status": "skipped"}`로 접는다.
>   **`plan_mcp.py`도 같은 코어를 쓰므로 같은 결함이 있다.**
> - **②(9.3.1)** — **실행 순서가 `1 → 2 → 4 → 3`이 됐다. 번호는 그대로다.**
>   `depends_on`(2단계 ∪ 4단계)·`install`/`config_keys`의 대상 규정·
>   `skipped_already_installed`는 **한 글자도 바뀌지 않는다.** 이 task의 출력 스키마도 그대로다.
> - **③(9.3.1)** — 3단계의 *"현재 상태와 다를 때만"* 판정이 **실행 시점의 로컬 값**을
>   본다. 그래서 `disable_after_install`은 이제 **"계획 시점의 후보 목록"** 이고
>   최종 판정이 아니다 — SKILL.md가 3단계 직전에 로컬 값을 다시 읽는다.
>   아래 본문의 `local_masked.get(k, True)` 추정은 **그 재읽기 뒤에도 남는 갈래**
>   (2·4단계 어느 명령의 대상도 아니면서 로컬 키가 없는 id)에서만 쓰인다.
> - **④** — 아래 본문의 *"상수 `true`를 쓰면 … `exit 1`의 거짓 실패"* 는 **3단계**
>   (`enable`/`disable`) 이야기이고 **그대로 옳다.** 바뀐 것은 **2단계**의 근거다:
>   *"bare install은 이미 설치된 id에 exit 1"* 은 **거짓**이고 실측은 **exit 0**이다.
>   진짜 위험은 거짓 실패가 아니라 **조용한 상태 파괴**다(값이 매니페스트
>   `defaultEnabled`로 덮이고 객체 값이 평탄화된다). 이 task의 산문은 `2246227`이
>   이미 정정했다.

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
- Modify: `plugins/claude-sync/tests/test_plugin_config.py` (술어 공유 측정)

- [ ] **Step 1: 실패하는 test 작성**

먼저 헬퍼 하나를 `tests/test_plugin_scripts.py`의 `staged_doc` 옆에 더한다. 스테이징
파일의 **원문**을 재는 자리다 — dict 동등성 단정은 값을 담는 필드가 나중에 하나라도
생기면 그것을 보지 못한다(형제 `plan_mcp`의 `test_apply_base_never_writes_plaintext_secret`
이 같은 처방이다).

```python
def staged_text(staging):
    """스테이징 파일의 **원문**. dict 동등성으로는 새 필드에 실린 평문을 보지 못한다."""
    with open(os.path.join(staging, pc.BACKUP_RELPATH), encoding="utf-8") as f:
        return f.read()
```

그리고 같은 파일 끝에 추가한다.

```python
EMPTY_CHOICES = {section: {"keep_stale": [], "keep_local": []} for section in pc.SECTIONS}


def run_script(tmp_path, script, *args):
    """스크립트를 격리된 HOME으로 실행한다 (파일 상단 규율).

    tmp_path를 받는 것은 HOME을 pytest가 정리하게 하기 위해서다 — 인자 검증이
    느슨해지는 순간 스크립트가 진짜 ~/.claude를 읽는다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, script] + list(args),
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)))


def apply_base(tmp_path, choices=None, local=None, repo=None, base=None,
               installed=None, held=None, staging="staging"):
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    merged = json.loads(json.dumps(EMPTY_CHOICES))
    for section, values in (choices or {}).items():
        if isinstance(values, dict):
            merged.setdefault(section, {}).update(values)
        else:
            merged[section] = values    # 형태가 어긋난 섹션 값을 그대로 넘기는 갈래
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
    result, doc = apply_base(tmp_path,
                             choices={"enabledPlugins": {"release": ["p@m"]}},
                             local={"enabledPlugins": {"p@m": True}},
                             repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
                             held=held_path)
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # keep_local이 동시에 걸렸다
    # ④의 강제분도 **보고에 실린다.** 싣지 않으면 SKILL.md가 "로컬 유지를 고르신 항목"
    # 목록에서 이 키를 빼고 안내해, 사용자는 base가 전진한 사실을 볼 길이 없다.
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["p@m"]
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == ["p@m"]


def test_release_and_keep_local_naming_the_same_key_report_it_once(tmp_path):
    """④의 합류에는 중복 제거가 걸린다 — 없으면 kept_local에 같은 키가 두 번 실린다.

    SKILL.md가 그 목록을 그대로 렌더링하므로 사용자가 같은 항목을 두 줄로 본다.
    ③과 ④가 같은 키를 가리키는 것은 모순 입력이 아니다: 사용자가 케이스 8·9에서
    "로컬 유지"를 고르면서 같은 키의 H3를 함께 푸는 갈래가 그것이다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_local": ["p@m"], "release": ["p@m"]}},
        local={"enabledPlugins": {"p@m": True}},
        repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["p@m"]
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # 적용 자체는 됐다


def test_keep_local_wins_over_keep_stale_on_the_same_key(tmp_path):
    """②③이 겹치면 ③이 이긴다 — ③이 뒤에 돌기 때문이고, 그 순서에는 근거가 있다.

    ③은 `key in masked` 가드를 가지므로 **레포에 값이 있을 때만** 적용된다. 그런데
    ②(케이스 4·5)는 "레포가 그 키를 잃었다"는 뜻이라, 둘이 겹치는 입력은 이미 모순이다.
    순서를 뒤집으면 그 모순 입력이 정당한 선택을 조용히 덮어 base에서 키가 사라지고
    다음 백업이 케이스 1(로컬 신규)로 착지한다.

    **kept_stale은 그때도 요청을 그대로 보고한다** — 같은 보고의 base_keys가 그 키를
    담으므로 소비자가 대조할 수 있다는 것이 그 비대칭을 받아들이는 근거다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_stale": ["p@m"], "keep_local": ["p@m"]}},
        local={"enabledPlugins": {"p@m": False}},
        repo={"enabledPlugins": {"p@m": True}},
        base={"enabledPlugins": {"p@m": True}})
    assert doc["enabledPlugins"]["p@m"] is True
    section = result["sections"]["enabledPlugins"]
    assert section["kept_stale"] == ["p@m"]
    assert section["kept_local"] == ["p@m"]
    assert section["base_keys"] == ["p@m"]


def test_release_list_is_sorted_regardless_of_where_the_entries_came_from(tmp_path):
    """보고·기록의 순서가 실행마다 흔들리면 diff가 흔들린다.

    이 catch는 **결정적이다** — 정렬 대상 released는 set이 아니라 리스트이고(이전
    파일의 순서 + 이번 선택의 순서), 이 fixture는 그 결합 순서를 정렬의 역순
    ["z@m", "a@m"]으로 만든다. 해시 순서에 기대지 않는다.

    선택에 z@m을 함께 넣어 **중복 제거도 같이 잰다** — 빠지면 결과가
    ["a@m", "z@m", "z@m"]이 되어 같은 단정이 갈라낸다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {}, "release": {"enabledPlugins": ["z@m"]}}, f)
    apply_base(tmp_path,
               choices={"enabledPlugins": {"release": ["a@m", "z@m"]}},
               local={"enabledPlugins": {"a@m": True, "z@m": True}},
               repo={"enabledPlugins": {"a@m": ["1.0.0"], "z@m": ["2.0.0"]}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == ["a@m", "z@m"]


def test_release_entry_is_cleared_once_the_repo_value_is_boolean(tmp_path):
    """조건이 사라지면 항목도 사라진다 — H4의 지문 규칙과 같은 형태다.

    이전 파일과 이번 선택 **양쪽에** p@m을 넣는다 — 두 목록이 각자 조건을 재므로
    한쪽에만 넣으면 다른 쪽의 조건 검사를 지워도 이 단정이 통과한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}}, f)
    apply_base(tmp_path, choices={"enabledPlugins": {"release": ["p@m"]}},
               local={"enabledPlugins": {"p@m": True}},
               repo={"enabledPlugins": {"p@m": True}}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == []


def test_declined_config_is_recorded_with_the_masked_repo_fingerprint(tmp_path):
    """6.4 — 로컬 값이나 사용자 입력값을 지문에 넣으면 영영 매치되지 않는다.

    레포 값에 **평문**을 넣는다. SENTINEL을 넣으면 마스킹이 항등이 되어 지문이 같아지고,
    지문 대상을 masked에서 원본으로 바꾸는 회귀를 단정이 구별하지 못한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}}
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    assert masked["delta@m"] != repo["pluginConfigs"]["delta@m"]   # 마스킹이 값을 바꿨다
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {
            "delta@m": pc.value_fingerprint(masked["delta@m"])}


def test_declining_again_refreshes_the_fingerprint_of_a_changed_repo_value(tmp_path):
    """6.4 — 레포 값이 바뀐 뒤 같은 키를 다시 거절하면 지문이 **갱신돼야** 한다.

    갱신이 죽으면 낡은 지문이 남아 H4가 다시 매치되지 않고, 사용자는 같은 항목을
    **매 restore마다 다시** 받는다. 예외도 빈 결과도 없이 조용하다.

    이전 파일에 실재하지 않는 지문을 두어 "이전 값을 그대로 옮긴 것"과 구별한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {"delta@m": "0" * 64},
                   "release": {"enabledPlugins": []}}, f)
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-new"}}}}
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    fresh = pc.value_fingerprint(masked["delta@m"])
    assert fresh != "0" * 64
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {"delta@m": fresh}


def test_held_file_directory_is_created_on_a_machine_that_never_backed_up(tmp_path):
    """~/.claude/.sync-state/를 아무도 먼저 만들지 않는다 — write_base가 만드는 것은
    그 안의 base뿐이고, 백업을 한 번도 하지 않은 기기에는 그 디렉토리가 없다.

    빠지면 FileNotFoundError가 스크립트의 except 튜플에 걸려 {"status": "skipped"}로
    접히고, 사용자의 decline이 **영영 기록되지 않는다.** 다른 테스트는 전부 이미 있는
    tmp 디렉토리를 주므로 이 줄이 일하는 자리를 재지 못한다.
    """
    held_path = str(tmp_path / "fresh-state" / "plugins-held.json")
    assert not os.path.exists(os.path.dirname(held_path))
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] != {}


def test_the_held_file_is_untouched_when_the_staging_write_fails(tmp_path):
    """스테이징(base) 먼저, 보류 파일 나중 — 그 순서를 지키는 fixture.

    스테이징 디렉토리 자리에 **일반 파일**을 두면 os.makedirs가 OSError로 죽는다.
    순서가 뒤바뀌면 그 시점에 보류 파일이 이미 쓰여 있고, 그러면 H3가 풀린 채로 base에
    키가 없어 다음 백업이 케이스 9로 떨어진다 — 약속과 반대다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    (tmp_path / "blocked").write_text("not a directory", encoding="utf-8")
    with pytest.raises(OSError):
        apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
                   local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
                   held=held_path, staging="blocked")
    assert not os.path.exists(held_path)


def test_apply_base_never_writes_a_plaintext_secret(tmp_path):
    """형제 plan_mcp의 같은 가드와 짝이다 — dict 동등성이 아니라 **원문**을 훑는다.

    "값이 실리는 자리가 구조적으로 없다"는 결론은 오늘 참이지만, 값을 담는 필드가
    나중에 하나라도 생기면 dict 대조 단정은 그것을 보지 못한다. 전진 갈래(ahead@m)와
    keep_local 갈래(kept@m)를 한 fixture에 함께 둔다 — 값이 base로 들어가는 자리가
    그 둘뿐이라서다.
    """
    _, doc = apply_base(
        tmp_path,
        choices={"pluginConfigs": {"keep_local": ["kept@m"]}},
        local={"pluginConfigs": {"ahead@m": {"options": {"apiKey": "sk-ahead"}},
                                 "kept@m": {"options": {"other": "x"}}}},
        repo={"pluginConfigs": {"ahead@m": {"options": {"apiKey": "sk-ahead"}},
                                "kept@m": {"options": {"apiKey": "sk-kept"}}}})
    raw = staged_text(str(tmp_path / "staging"))
    assert "sk-ahead" not in raw
    assert "sk-kept" not in raw
    # 두 갈래가 실제로 base에 들어갔다 — 아니면 위 두 단정이 공허하다.
    assert doc["pluginConfigs"]["ahead@m"] == {"options": {"apiKey": pc.SENTINEL}}
    assert doc["pluginConfigs"]["kept@m"] == {"options": {"apiKey": pc.SENTINEL}}


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
    """선택 결과 JSON은 사용자 대화에서 만들어진다 — 형태가 어긋나도 죽지 않는다.

    **해시 불가능한 원소를 함께 넣는다.** None·3만 넣으면 필터를 지워도 nb.pop(None)과
    nb.pop(3)이 조용히 성공해 어떤 단정도 흔들리지 않는다 — 필터가 실제로 막는 것은
    리스트·객체가 dict 키 자리에 들어가 TypeError로 죽는 갈래다.
    그리고 보고에도 문자열만 실려야 한다 — SKILL.md가 그 목록을 사용자에게 보여 준다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_stale": [None, 3, ["x"], "p@m"],
                                    "keep_local": [{"k": 1}, "q@m"]},
                 "nonsense": {"keep_local": ["x"]}},
        local={"enabledPlugins": {"p@m": True}},
        repo={"enabledPlugins": {"q@m": True}},
        base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in doc["enabledPlugins"]
    assert result["sections"]["enabledPlugins"]["kept_stale"] == ["p@m"]
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["q@m"]


def test_failed_restore_does_not_advance_the_base(tmp_path):
    """10.4 — 로컬이 그 값에 동의하지 않았으므로 base가 전진하면 안 된다.

    "복원을 시도한 목록"이 아니라 **복원 후 다시 읽은 로컬**을 넘기는 것이 그 안전장치다.
    """
    _, doc = apply_base(tmp_path, local={"enabledPlugins": {}},
                        repo={"enabledPlugins": {"failed@m": True}})
    assert "failed@m" not in doc["enabledPlugins"]


def test_apply_base_status_stays_ok_when_a_section_is_skipped(tmp_path):
    """최상위 status는 "이 스크립트가 돌았는가"이고 섹션 skip을 반영하지 않는다.

    반영하게 만들면 두 섹션이 접힌 실행에서 SKILL.md가 "반영할 것이 없다"로 읽고
    **정상 처리된 마켓플레이스 섹션까지 조용히 버린다.** 섹션 사실은
    sections[<섹션>]["status"]에만 있고 소비자는 그것을 따로 읽어야 한다.
    collect_plugins·compare_plugins가 같은 계약을 쓴다.
    """
    result, _ = apply_base(tmp_path,
                           local={"enabledPlugins": {"p@m": True}},
                           repo={"enabledPlugins": {"p@m": True}},
                           installed=str(tmp_path / "none-installed.json"))
    assert result["status"] == "ok"
    assert result["sections"]["enabledPlugins"]["status"] == "skipped"
    assert result["sections"]["extraKnownMarketplaces"]["status"] == "ok"


def test_apply_base_report_matches_the_document_it_staged(tmp_path):
    """보고 세 필드가 비면 SKILL.md가 선택이 반영됐는지 확인할 길이 없다.

    base_keys를 **실제로 쓴 문서와 대조한다** — 따로 만들면 갈리고, 갈려도 증상이 없다.
    셋을 서로 다른 비지 않은 값으로 채워 하나만 하드코딩돼도 드러나게 한다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_stale": ["gone@m"], "keep_local": ["stay@m"]}},
        local={"enabledPlugins": {"gone@m": True, "stay@m": False, "plain@m": True}},
        repo={"enabledPlugins": {"stay@m": True, "plain@m": True}},
        base={"enabledPlugins": {"gone@m": True, "stay@m": True, "plain@m": True}})
    section = result["sections"]["enabledPlugins"]
    assert section["kept_stale"] == ["gone@m"]
    assert section["kept_local"] == ["stay@m"]
    assert section["base_keys"] == sorted(doc["enabledPlugins"])
    assert "gone@m" not in section["base_keys"]
    assert doc["enabledPlugins"]["stay@m"] is True


def test_keep_local_reports_only_what_it_could_apply(tmp_path):
    """kept_local은 **적용한 것**을 보고한다 — 레포에 없는 키에는 걸 값이 없다.

    kept_stale이 요청을 그대로 보고하는 것과 비대칭으로 보이지만 둘 다 "이 실행이
    만든 base 상태"를 말한다: keep_stale은 키가 base에 없든 있든 결과가 "없음"이라
    요청이 곧 결과이고, keep_local은 레포에 값이 없으면 만들 결과 자체가 없다.
    요청을 그대로 보고하면 SKILL.md가 반영되지 않은 선택을 반영됐다고 안내한다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_local": ["ghost@m", "stay@m"]}},
        local={"enabledPlugins": {"stay@m": False}},
        repo={"enabledPlugins": {"stay@m": True}},
        base={"enabledPlugins": {"stay@m": True}})
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["stay@m"]
    assert "ghost@m" not in doc["enabledPlugins"]


def test_apply_base_applies_choices_in_the_marketplace_section_too(tmp_path):
    """세 섹션을 도는 루프인데 두 섹션만 재면 셋째가 조용히 빠져도 통과한다.

    마켓플레이스는 auto·보류 파일 어느 실패로도 skip되지 않는 유일한 섹션이라,
    루프가 좁아지면 **그 섹션만 아무 선택도 반영되지 않는다.**
    """
    result, doc = apply_base(
        tmp_path,
        choices={"extraKnownMarketplaces": {"keep_stale": ["gone"]}},
        local={"extraKnownMarketplaces": {"gone": GH, "stay": GH}},
        repo={"extraKnownMarketplaces": {"stay": GH}},
        base={"extraKnownMarketplaces": {"gone": GH, "stay": GH}})
    assert result["sections"]["extraKnownMarketplaces"]["kept_stale"] == ["gone"]
    assert "gone" not in doc["extraKnownMarketplaces"]
    # 섹션 전체가 죽으면 위 단정이 공허해진다 — 살아남은 키가 있어야 한다.
    assert "stay" in doc["extraKnownMarketplaces"]


def test_apply_base_sorts_the_reported_base_keys(tmp_path):
    """정렬을 잃으면 보고가 삽입 순서를 따라가 diff가 실행마다 흔들린다.

    keep_local이 nb **뒤에** 덧붙이므로 삽입 순서를 정렬 역순으로 만들 수 있다 —
    zzz@m은 next_base가 먼저 얹고(aaa@m은 로컬에 없어 전진하지 못한다) aaa@m은
    keep_local이 나중에 얹으므로 nb의 삽입 순서는 [zzz@m, aaa@m]이다. 이 fixture는
    해시에 의존하지 않으므로 회귀를 **결정적으로** 잡는다.

    **삽입 순서를 스테이징 파일에서 볼 수는 없다** — ks.dump_json이 sort_keys=True로
    쓰기 때문에 doc은 언제나 정렬돼 있다. 그래서 정렬 회귀가 드러나는 자리는 보고의
    base_keys 하나뿐이고, doc 쪽 단정은 "두 키가 실제로 있다"(fixture가 비지 않았다)를
    맡는다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_local": ["aaa@m"]}},
        local={"enabledPlugins": {"zzz@m": True}},
        repo={"enabledPlugins": {"zzz@m": True, "aaa@m": True}},
        base={"enabledPlugins": {"zzz@m": True}})
    assert doc["enabledPlugins"] == {"zzz@m": True, "aaa@m": True}
    assert result["sections"]["enabledPlugins"]["base_keys"] == ["aaa@m", "zzz@m"]


@pytest.mark.parametrize("args", [[], ["apply-base"], ["apply-base", "a", "b"],
                                  ["apply-base", "a", "b", "c", "d"],
                                  ["bogus", "a", "b", "c"]])
def test_apply_base_cli_rejects_wrong_invocations(tmp_path, args):
    """서브커맨드 이름 검사와 개수 검사가 **둘 다** 필요하다.

    처리되지 않은 IndexError도 종료 코드 1이므로, usage 문구를 함께 확인하지 않으면
    개수 검사 제거를 잡지 못한다. plan 서브커맨드가 같은 모양의 테스트를 갖는다.
    """
    proc = run_script(tmp_path, plan_script(), *args)
    assert proc.returncode == 1
    assert "사용:" in proc.stderr


def test_apply_base_cli_skips_when_the_choices_json_is_not_an_object(tmp_path):
    """read_choices의 ValueError가 흡수되지 않으면 restore 흐름이 traceback으로 선다.

    "형제 셋과 같은 except 튜플"이라는 주석이 지키는 것이 이 항목이다 —
    10.3의 "종료 코드는 0이다, 그래야 안내가 보인다"가 여기서 깨진다.

    **격리된 HOME에 settings.json을 넣는다.** 없으면 read_local_sections가 먼저
    LocalConfigUnavailable로 접혀 status가 어차피 skipped가 되고, 그러면 이 단정은
    read_choices와 무관하게 참이 된다. 사유가 **선택 결과 파일을 가리키는지**까지
    확인해야 그 구별이 선다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    choices_path = tmp_path / "choices.json"
    choices_path.write_text("[]", encoding="utf-8")
    repo_dir = write_repo(tmp_path, {})
    proc = run_script(tmp_path, plan_script(), "apply-base",
                      os.path.join(repo_dir, pc.BACKUP_RELPATH),
                      str(tmp_path / "staging"), str(choices_path))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
    assert str(choices_path) in json.loads(proc.stdout)["reason"]


def test_apply_base_cli_writes_the_staging_file(tmp_path):
    """main()의 인자 배선을 **성공 경로로** 한 번 실행한다 (형제 plan_mcp와 같은 가드).

    거부 갈래만 재면 배선이 무가드로 남는다. backup_path와 staging_dir이 뒤바뀌면
    os.makedirs가 레포의 plugins.json 자리에 디렉토리를 만들려다 FileExistsError로
    접혀 {"status": "skipped"} + **종료 코드 0**이 된다 — SKILL.md는 그것을 정상으로
    읽고 base는 전혀 전진하지 않는다. 이 함수가 .tmp 규칙에서 스스로를 제외하면서까지
    막으려던 바로 그 실패 모양이다.

    격리 HOME에 settings.json과 installed_plugins.json을 함께 넣는다 — 하나라도 없으면
    섹션이 접혀 스테이징 문서가 비고, 아래 단정이 배선과 무관하게 참이 된다.
    """
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"p@m": True}}), encoding="utf-8")
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
    choices_path = tmp_path / "choices.json"
    choices_path.write_text(json.dumps(EMPTY_CHOICES), encoding="utf-8")
    repo_dir = write_repo(tmp_path, {"enabledPlugins": {"p@m": True}})
    staging = str(tmp_path / "staging")
    proc = run_script(tmp_path, plan_script(), "apply-base",
                      os.path.join(repo_dir, pc.BACKUP_RELPATH), staging,
                      str(choices_path))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "ok"
    assert staged_doc(staging)["enabledPlugins"] == {"p@m": True}


def test_skipped_section_keeps_the_previous_base_in_the_staged_document(tmp_path):
    """7.5 — 판정하지 못한 섹션을 {}로 덮으면 그 섹션의 이력이 통째로 사라진다.

    다음 백업이 그 섹션 전체를 "로컬 신규"로 읽어 타 기기 항목까지 되살리거나 지운다.
    collect_plugins가 같은 처방을 갖는다. 이전 base에 **비지 않은 값**을 넣어야
    "빈 base를 그대로 통과시킨 것"과 구별된다.
    """
    result, doc = apply_base(tmp_path,
                             local={"enabledPlugins": {"p@m": True}},
                             repo={"enabledPlugins": {"p@m": True}},
                             base={"enabledPlugins": {"kept@m": True}},
                             installed=str(tmp_path / "none-installed.json"))
    assert result["sections"]["enabledPlugins"]["status"] == "skipped"
    assert doc["enabledPlugins"] == {"kept@m": True}


def test_this_runs_decline_takes_effect_on_the_base_immediately(tmp_path):
    """6.4·5.3 — 훅에 **이번 실행의** 보류 상태를 넘겨야 declined 키가 base에서 빠진다.

    이전 상태를 넘기면 H4가 아직 걸리지 않아 그 키가 base로 전진하고, 다음 실행에서야
    보류로 판정되어 얼어붙은 base가 남는다. 로컬과 레포의 마스킹 결과가 **같아야**
    next_base가 전진을 시도하므로(그래야 이 단정이 공허하지 않다) 옵션 키 집합을 맞춘다.

    레포 값에 **평문**을 넣는다. SENTINEL을 넣으면 마스킹이 항등이 되어 원본과 마스킹된
    값의 지문이 같아지고, value_held를 **정규화 없이** 손으로 조립하는 회귀가 이 단정에
    드러나지 않는다 — H4의 지문은 마스킹된 레포 값으로 계산되므로, 평문을 그대로 hold에
    넘기면 지문이 어긋나 보류가 통째로 비고 이 키가 base로 전진한다.
    """
    _, doc = apply_base(
        tmp_path,
        choices={"pluginConfigs": {"declined": ["delta@m"]}},
        local={"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}},
        repo={"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-plain"}}}})
    assert "delta@m" not in doc["pluginConfigs"]


def test_keep_local_writes_the_masked_repo_value_into_the_base(tmp_path):
    """6.1 — keep_local이 얹는 값도 마스킹 훅을 거친다.

    거치지 않으면 base에 평문이 남고, 다음 비교가 **마스킹된 로컬과 평문 base**를
    견주게 되어 사라지지 않는 차이가 생긴다. enabledPlugins로 재면 그 섹션의 정규화가
    항등이라 이 회귀가 드러날 자리가 없으므로 pluginConfigs로 잰다.

    로컬의 option 키 집합을 레포와 어긋나게 두어 next_base가 스스로 전진하지 못하게
    한다 — 그래야 doc에 남은 값이 keep_local이 얹은 것임이 확실해진다.
    """
    _, doc = apply_base(
        tmp_path,
        choices={"pluginConfigs": {"keep_local": ["delta@m"]}},
        local={"pluginConfigs": {"delta@m": {"options": {"other": "x"}}}},
        repo={"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}})
    assert doc["pluginConfigs"]["delta@m"] == {"options": {"apiKey": pc.SENTINEL}}


def test_local_only_entries_do_not_enter_the_base(tmp_path):
    """10.4 — next_base의 세 번째 인자가 **레포**여야 하는 이유.

    로컬을 넘기면 모든 키가 자기 자신과 같아 base가 로컬 전체로 전진한다. 아직 레포에
    올라가지 않은 이 기기의 항목이 "합의된 이력"이 되고, 다음 백업이 그것을 케이스 4
    (타 기기 삭제)로 읽어 사용자에게 되묻는다.
    """
    _, doc = apply_base(tmp_path,
                        local={"enabledPlugins": {"mine@m": True, "shared@m": True}},
                        repo={"enabledPlugins": {"shared@m": True}})
    assert "mine@m" not in doc["enabledPlugins"]
    assert doc["enabledPlugins"]["shared@m"] is True     # 합의된 키는 전진한다


def test_held_file_carries_the_schema_version(tmp_path):
    """read_held_state의 버전 게이트(claims_newer_schema)가 읽는 필드다.

    빠져도 지금은 read_held_state가 통과하므로 **무증상이다** — 나중에 스키마를 올릴 때
    이 파일만 게이트를 타지 못하고 낡은 형태로 조용히 통과한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["pluginConfigs"] != {}        # 파일이 실제로 내용을 담았다
    assert payload["version"] == pc.HELD_SCHEMA_VERSION


@pytest.mark.parametrize("broken", [["p@m"], "p@m", 7, None])
def test_apply_base_ignores_a_section_whose_choices_are_not_an_object(tmp_path, broken):
    """choice_list가 약속한 "형태가 어긋나도 세우지 않는다"의 나머지 절반.

    원소 타입은 test_apply_base_ignores_unknown_and_non_string_choice_entries가 재지만
    **섹션 값** 자체가 dict가 아닌 갈래는 그 테스트가 닿지 않는다 — SKILL.md가
    {"enabledPlugins": ["p@m"]}처럼 평면 목록을 내보내면 section_choices.get이
    AttributeError로 restore를 세운다.

    정상 섹션의 선택을 함께 넣어 "선택을 통째로 무시한다"와 구별한다.
    **None 갈래만으로는 구별이 서지 않는다** — 검사를 `choices.get(section) or {}`로
    완화해도 None은 그대로 빈 선택이 된다. 리스트·문자열·정수 갈래가 그 회귀를 잡는다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": broken,
                 "extraKnownMarketplaces": {"keep_stale": ["gone"]}},
        local={"enabledPlugins": {"p@m": True},
               "extraKnownMarketplaces": {"gone": GH, "stay": GH}},
        repo={"enabledPlugins": {}, "extraKnownMarketplaces": {"stay": GH}},
        base={"enabledPlugins": {"p@m": True},
              "extraKnownMarketplaces": {"gone": GH, "stay": GH}})
    assert result["sections"]["enabledPlugins"]["kept_stale"] == []
    assert doc["enabledPlugins"] == {"p@m": True}        # 어긋난 섹션의 base는 그대로다
    assert result["sections"]["extraKnownMarketplaces"]["kept_stale"] == ["gone"]
    assert "gone" not in doc["extraKnownMarketplaces"]
    assert "stay" in doc["extraKnownMarketplaces"]


def test_declined_ids_absent_from_the_repo_are_ignored(tmp_path):
    """SKILL.md가 레포에 없는 id를 declined로 보내면 KeyError로 restore가 통째로 선다.

    레포에 있는 항목을 함께 넣어 "declined를 통째로 무시한다"와 구별한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}}
    apply_base(tmp_path,
               choices={"pluginConfigs": {"declined": ["ghost@m", "delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {
            "delta@m": pc.value_fingerprint(masked["delta@m"])}


def test_previous_declined_entries_are_dropped_when_the_repo_loses_the_key(tmp_path):
    """6.4 — 레포에 없는 항목은 정리한다.

    남겨 두면 같은 값이 레포에 되돌아왔을 때 사용자가 다시 고르지 않았는데도 지문이
    매치되어 **조용히 보류로 복귀한다.** 레포에 남아 있는 항목을 함께 두어 "전부
    지운다"와 구별한다 — 그쪽은 지문까지 그대로 옮겨져야 한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {"gone@m": "0" * 64, "stay@m": "1" * 64},
                   "release": {"enabledPlugins": []}}, f)
    apply_base(tmp_path, local={},
               repo={"pluginConfigs": {"stay@m": {"options": {}}}}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {"stay@m": "1" * 64}


def test_release_does_not_advance_the_base_of_the_other_section(tmp_path):
    """release의 keep_local 동시 적용은 **enabledPlugins 한 섹션의 것이다.**

    두 섹션은 키가 같은 문자열이라, 이 목록이 섹션을 넘어 새면 사용자가 고르지도 않은
    pluginConfigs 항목까지 base가 레포 값으로 전진한다 — 실제 설정 차이가 케이스 8·9
    대신 케이스 7로 착지해 로컬 값이 다음 백업에서 레포를 덮는다. 9.3.7의 섹션 중첩이
    막으려는 위험의 다른 입구다.

    로컬의 option 키 집합을 레포와 어긋나게 두어 next_base가 스스로 전진하지 못하게
    한다 — 그래야 pluginConfigs에 값이 생기는 유일한 경로가 이 누수뿐이다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"release": ["p@m"]}},
        local={"enabledPlugins": {"p@m": True},
               "pluginConfigs": {"p@m": {"options": {"other": "x"}}}},
        repo={"enabledPlugins": {"p@m": ["1.0.0"]},
              "pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}})
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # 해제 섹션은 전진한다
    assert "p@m" not in doc["pluginConfigs"]             # 다른 섹션은 전진하지 않는다
    assert result["sections"]["pluginConfigs"]["kept_local"] == []
```

`tests/test_plugin_config.py`에는 술어 공유를 재는 둘을 더한다(8.2 열거형 대조 절 앞).
**오늘 `enabledPlugins`의 정규화가 항등이라 이 갈림은 어떤 값 fixture로도 드러나지
않는다** — 그래서 재는 것이 값이 아니라 술어의 동일성이다.

```python
def test_h3_held_kinds_and_release_share_one_extended_value_predicate(monkeypatch):
    """"레포 값이 불리언이 아닌가"를 세 곳이 각자 적으면 그중 하나가 갈려도 무증상이다.

    갈리는 자리는 셋이다 — hold의 H3, held_kinds의 extended_value, next_held_state의
    release 정리. 한 곳만 **원본** 레포를 보게 되면 ⑴ release 항목이 조용히 유지되거나
    사라지고 ⑵ 같은 실행의 pluginConfigs 지문이 H4와 어긋나 decline이 영영 매치되지
    않는다. 오늘 enabledPlugins의 정규화가 항등이라 그 갈림은 **결과가 같아** 어떤
    fixture로도 드러나지 않는다 — 그래서 재는 것은 값이 아니라 술어의 **동일성**이다.

    술어를 뒤집어 셋이 함께 따라가는지 본다. 한 곳이라도 자기 판을 되살리면 그 자리만
    옛 판정(불리언 → 확장 값 아님)을 내어 그 줄이 갈라낸다.
    """
    monkeypatch.setattr(pc, "_extended_value", lambda repo_norm, key: True)
    repo = {"enabledPlugins": {"p@m": True}, "extraKnownMarketplaces": {},
            "pluginConfigs": {}}
    hooks = pc.build_hooks({}, repo, auto_ids=frozenset(), held_state=pc.EMPTY_HELD)
    assert hooks["enabledPlugins"]["hold"]({}, repo["enabledPlugins"])["value"] == {"p@m"}
    assert pc.held_kinds("enabledPlugins", ["p@m"], auto_ids=frozenset(),
                         directory_names=frozenset(), held_configs={},
                         repo_norm=repo["enabledPlugins"])["extended_value"] == ["p@m"]
    previous = {"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}}
    assert pc.next_held_state(previous, pc.normalized_sections(repo),
                              {})["release"]["enabledPlugins"] == ["p@m"]


def test_next_held_state_reads_only_normalized_values(monkeypatch):
    """정규화가 값을 바꾸는 섹션에서 이 함수가 **어느 쪽을 보는지** 고정한다.

    enabledPlugins의 정규화는 오늘 항등이라 이 갈림이 무증상이다. 정규화를 잠시
    "모든 값을 불리언으로 좁히는" 것으로 바꿔 두 세계를 갈라놓으면, 원본을 보는 판은
    release 항목을 유지하고 정규화된 값을 보는 판은 정리한다.

    normalized_sections를 거쳐 넘기는 것이 계약이므로 여기서도 그것을 거친다 — 그래야
    호출부가 원본을 그대로 넘기게 되는 회귀까지 같은 단정이 덮는다.
    """
    monkeypatch.setitem(pc.SECTION_NORMALIZE, "enabledPlugins",
                        lambda mapping: {k: True for k in mapping})
    repo = {"enabledPlugins": {"p@m": ["1.0.0"]}, "extraKnownMarketplaces": {},
            "pluginConfigs": {}}
    previous = {"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}}
    state = pc.next_held_state(previous, pc.normalized_sections(repo), {})
    assert state["release"]["enabledPlugins"] == []
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_plugin_scripts.py -q`
기대: 신규 테스트 FAIL (`AttributeError: module 'plan_plugins' has no attribute 'apply_base'`)

- [ ] **Step 3: 구현**

`lib/plugin_config.py`에 넷을 더하고 둘을 고친다.

정규화 표를 문서 층위로 여는 함수. **훅이 아니라 표를 직접 읽는 자리를 여기 하나로**
모은다 — `next_held_state`는 훅보다 **먼저** 계산돼야 하므로(훅의 H4가 이번 실행의
decline을 봐야 한다) 훅에서 `normalize`를 빌려 올 수 없다.

```python
def normalized_sections(sections):
    """문서 하나를 섹션별 정규화로 통과시킨다. 값만 좁히고 키 집합은 그대로다.

    **훅(build_hooks)이 아니라 표를 직접 읽는 자리가 있는 것은 순서 때문이다** —
    next_held_state는 훅보다 **먼저** 계산돼야 하고(훅의 H4가 이번 실행의 decline을
    봐야 한다), 그래서 훅에서 normalize를 빌려 올 수 없다. build_hooks가 싣는 것과
    **같은 표**를 쓰는 것이 그 대응이고, 직접 읽는 자리를 이 함수 하나로 모으는 것이
    그 대응을 지킬 수 있게 하는 조건이다 — build_hooks가 언젠가 이 표를 감싸면
    **여기도 같이 감싸야 한다.**
    """
    return {section: SECTION_NORMALIZE[section](sections.get(section, {}))
            for section in SECTIONS}
```

H3의 술어를 모듈 함수로 뽑는다. **세 곳이 같은 것을 부른다** — `_make_hold`의 H3,
`held_kinds`의 `extended_value`, `next_held_state`의 release 정리. 셋 중 하나만
원본 레포를 보게 되면 release 항목이 조용히 갈리고 지문이 H4와 어긋난다.

```python
def _extended_value(repo_norm, key):
    """레포 값이 불리언이 아닌가 — 버전 제약 등 **확장 값**인가 (H3의 술어).

    **세 곳이 같은 것을 물어야 한다** — _make_hold의 H3, held_kinds의 extended_value,
    next_held_state의 release 정리. 각자 적으면 한 곳만 원본 레포를 보게 되는 갈림이
    나고, 그러면 ⑴ release 항목이 조용히 유지되거나 사라지고 ⑵ 같은 실행의
    pluginConfigs 지문이 H4와 어긋나 **decline이 영영 매치되지 않는다**(매 restore마다
    다시 묻는다). 오늘 enabledPlugins의 정규화가 항등(_identity)이라 그 갈림은
    무증상이고, 그래서 어떤 변조도 그것을 잡지 못한다.

    **정규화된 매핑을 받는 것이 계약이다.** 원본을 넘기면 그 섹션에 마스킹이 도입되는
    날 예외도 빈 결과도 없이 판정만 반대로 선다.
    """
    return key in repo_norm and not isinstance(repo_norm[key], bool)
```

그 셋이 그것을 부르게 고친다(앞의 둘).

```python
            if (section == "enabledPlugins"                                  # H3
                    and _extended_value(repo, key) and key not in released):
```

```python
        if "extended_value" in kinds and _extended_value(repo_norm, key):
            kinds["extended_value"].append(key)
```

선택 반영·보류 기록 셋. `next_held_state`는 **정규화된 문서**를 받는다 — 원본을 받아
여기서 다시 정규화하면 계층을 우회하는 자리가 하나 더 생긴다.

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


def next_held_state(previous, repo_norm, choices):
    """apply-base가 기록할 다음 보류 상태 (6.4·7.3).

    declined — 이번에 값을 입력한 항목(configured)은 빼고 이번에 건너뛴 항목을 더한다.
               레포에 없는 항목은 정리한다. 지문은 **마스킹된 레포 값**으로 만든다.
    release  — 레포 값이 불리언이 되었거나 키가 사라진 항목을 정리한다. 조건이 사라지면
               항목도 사라진다(H4의 지문 규칙과 같은 형태).

    configured가 필요한 이유: 사용자가 마음을 바꿔 값을 입력했는데 항목이 남아 있으면
    지문이 그대로 매치되어 **영영 보류 상태로 남는다** — 6.4가 "그때 항목을 파일에서
    지운다"고 정한 자리다.

    **정규화된 문서(normalized_sections의 결과)를 받는다.** 원본을 받아 여기서 다시
    정규화하면 계층을 우회하는 자리가 하나 더 생긴다 — release 판정은 H3와, 지문은
    H4와 **같은 값**을 봐야 하고, 그 술어는 _extended_value 하나로 공유한다.
    """
    masked = repo_norm["pluginConfigs"]
    configured = set(choice_list(choices, "pluginConfigs", "configured"))
    declined = {key: value for key, value in previous["pluginConfigs"].items()
                if key in masked and key not in configured}
    for key in choice_list(choices, "pluginConfigs", "declined"):
        if key in masked:
            declined[key] = value_fingerprint(masked[key])

    plugins = repo_norm["enabledPlugins"]
    released = [key for key in previous["release"]["enabledPlugins"]
                if _extended_value(plugins, key)]
    released += [key for key in choice_list(choices, "enabledPlugins", "release")
                 if _extended_value(plugins, key) and key not in released]
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

`skills/sync-restore/scripts/plan_plugins.py`에 `_next_base_sections`·`apply_base`·
`read_choices`를 더하고 `main`을 확장한다. 모듈 docstring의 사용법에도 서브명령을 더한다.

**섹션 루프는 `_next_base_sections`가 맡는다** — `build_plan`이 `_plan_sections`에
위임하는 것과 같은 층위다. 같은 모양의 루프를 `apply_base` 몸통에 인라인하면 이 파일이
스스로 만든 대칭이 새 함수 하나에서 깨지고, `apply_base`의 몸통이 "읽기 → 계산 → 쓰기"
세 국면으로 읽히지 않는다.

```python
def _next_base_sections(local, repo, base, hooks, skipped, choices, next_held):
    """섹션별 다음 base와 그 보고. _plan_sections와 **같은 층위의 짝**이다.

    앞의 다섯 인자는 _plan_sections와 같고, 뒤의 둘만 base 경로에만 있는 입력이다 —
    사용자의 선택(choices)과 **이번 실행의** 보류 상태(next_held).

    **value_held를 스스로 계산해 next_base에 넘긴다.** merge 경로와 달리 여기서는
    아무도 대신 계산해 주지 않는다. 넘기지 않으면 보류 키가 base에 얼어붙어, 보류가
    풀리는 순간 케이스 3(삭제)이 난다.

    **레포 매핑 전체를 세 번째 인자로 넘긴다.** next_base의 계약은 "local과 merged가
    같은 값을 갖는 키만 전진"이므로, 그 교집합이 곧 "실제로 복원에 성공한 항목"이 된다 —
    실패했거나 사용자가 건너뛴 항목은 로컬에 없으니 자동으로 빠진다(10.4).
    여기에 "복원을 시도한 목록"을 넘기면 그 안전장치가 사라진다.

    **④의 keep_local 동시 적용은 enabledPlugins 한 섹션에만 건다.** 두 섹션은 키가 같은
    문자열이라 이 목록이 섹션을 넘어 새면 사용자가 고르지도 않은 pluginConfigs 항목까지
    base가 레포 값으로 전진한다 — 실제 설정 차이가 케이스 8·9 대신 케이스 7로 착지해
    다음 백업에서 로컬 값이 레포를 덮는다. 9.3.7의 섹션 중첩이 막으려는 위험의 다른
    입구이고, 선택 JSON의 중첩만으로는 막히지 않는다(release는 그 JSON이 아니라 보류
    파일에서도 온다). **불필요한 특수 케이스로 읽고 지우지 말 것.**

    **②와 ③이 같은 키에 겹치면 ③이 이긴다** — ③이 뒤에 돌기 때문이다. 임의의 순서가
    아니라 ③이 `key in masked` 가드를 갖는 데서 나온다: ③은 레포에 값이 있을 때만
    적용되고, 그때 ②(케이스 4·5 = "레포가 그 키를 잃었다")는 이미 모순 입력이다.
    순서를 뒤집으면 그 모순 입력이 정당한 선택을 조용히 덮는다.

    **kept_stale은 요청을, kept_local은 적용한 것을 보고한다.** 비대칭으로 보이지만 둘
    다 "이 실행이 만든 base 상태"를 말한다 — keep_stale은 그 키가 base에 있었든 없었든
    결과가 "없음"이라 요청이 곧 결과이고, keep_local은 레포에 값이 없으면 얹을 값 자체가
    없다. 그때도 요청을 그대로 보고하면 SKILL.md가 반영되지 않은 선택을 반영됐다고
    안내한다. **예외는 바로 위의 모순 입력 하나다** — 같은 키가 ②③에 함께 오면 ③이
    이겨 그 키가 nb에 남는데도 kept_stale에 실린다. 같은 보고의 base_keys가 그 키를
    담으므로 소비자가 대조할 수는 있다.

    **base_keys는 형제 plan_mcp의 base_names와 이름이 다르다(의도).** 그쪽은 서버
    "이름"의 평면 매핑이고 이쪽은 섹션 안의 "키"다 — 같은 restore 흐름이 두 출력을 함께
    읽으므로 이름이 같으면 층위가 다른 두 목록을 한 종류로 렌더링하게 된다.
    """
    previous_base = base or {}
    doc, report = {}, {}
    for section in pc.SECTIONS:
        if section in skipped:
            # 판정하지 못한 섹션은 이전 base를 그대로 통과시킨다 — {}로 덮으면 다음
            # 백업이 그 섹션 전체를 "로컬 신규"로 읽는다(collect_plugins와 같은 처방).
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
            # ④ — H3 탈출구의 동시 적용. **이 섹션에만 건다**(위 docstring).
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
    return doc, report


def apply_base(backup_path, staging_dir, choices, settings_path=None, installed_path=None,
               held_path=None, base_dir=ss.BASE_DIR):
    """복원 후 로컬 기준으로 다음 base를 계산하고 override 셋을 적용해 스테이징에 쓴다.

    ① next_base(복원 후 로컬, 이전 base, 레포 값)  — 정규화는 코어가 한다
    ② keep_stale(케이스 4·5의 "유지")   → base에서 키 삭제  (그 이력은 잊는다)
    ③ keep_local(케이스 8·9의 "로컬 유지") → base[k] ← 레포 값 (그 이력은 잊는다)
    ④ release(H3 탈출구) → ②③과 별개로 보류를 풀고 **동시에 ③을 적용한다**
       (**enabledPlugins 한 섹션에만 건다** — 근거는 _next_base_sections)

    ④가 ③을 함께 걸지 않으면 base에 그 키가 없어(5.3) 다음 백업이 케이스 9로 떨어지고
    레포 값이 그대로 남는다 — 약속과 반대다. ③을 함께 걸면 same(repo, base)이므로
    케이스 7(로컬만 변경) → 로컬 값 push → 레포 값이 불리언 → H3 자연 해제로 이어진다.

    **섹션 루프와 그 보고는 _next_base_sections가 맡는다** — build_plan이 _plan_sections에
    위임하는 것과 같은 층위다. 이 몸통에 남는 것은 읽기 → 계산 → 쓰기 세 국면뿐이다.

    **이 함수는 .tmp+rename 규칙에서 제외된다.** 그 규칙은 "레포 쓰기가 성공한 뒤에
    rename"인데 apply-base에는 **레포 쓰기가 없다** — 그대로 적용하면 rename 트리거가
    영영 오지 않아 게이트가 언제나 거짓이 되고 restore 경로의 base가 전혀 전진하지
    않는다. 여기서는 **파일 존재가 곧 "계산 성공"**이다(9.3.7).

    **최상위 status는 섹션 skip을 반영하지 않는다** — build_plan·collect_plugins·
    compare_plugins와 같은 계약이다. 접힌 섹션이 있어도 나머지 섹션의 base는 유효하고,
    최상위를 skipped로 접으면 소비자가 "반영할 것이 없다"로 읽어 정상 처리된 섹션까지
    함께 버린다. 섹션 사실은 sections[<섹션>]["status"]에만 있다.

    **파일 두 개를 쓰는 순서가 계약이다.** 스테이징(base) 먼저, 보류 파일 나중.
    반대로 하면 release가 기록된 뒤 base 쓰기가 실패했을 때 H3가 풀린 채로 base에 키가
    없어 다음 백업이 케이스 9로 떨어진다. 이 순서에서는 보류 파일 쓰기가 실패해도
    "다시 묻는다"에 그친다. **이 순서를 재는 fixture는 스테이징 디렉토리 자리에 일반
    파일을 두는 것이다** — os.makedirs가 그 자리에서 OSError로 죽으므로, 순서가 뒤집혀
    있으면 그 시점에 보류 파일이 이미 쓰여 있다.
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)

    # **이번 실행의** 보류 상태로 훅을 만든다. 이것이 실제로 결과를 가르는 곳은 H4다 —
    # 이번에 declined된 pluginConfigs 키가 곧바로 value_held가 되어 base에서 빠진다.
    # 이전 상태를 넘기면 그 키가 base로 전진했다가 다음 실행에서야 보류로 판정되어
    # 얼어붙은 base가 남는다(5.3).
    # release 쪽은 이 선택으로 결과가 갈리지 않는다 — 아래 ③이 그 키에 레포 값을 다시
    # 얹으므로 H3가 걸렸든 풀렸든 nb의 최종 값이 같다. 그래도 같은 상태를 넘기는 것은
    # 훅과 아래 루프가 **한 보류 상태**를 보게 하기 위해서다.
    next_held = pc.next_held_state(held_state, pc.normalized_sections(repo), choices)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=next_held)

    doc, report = _next_base_sections(local, repo, base, hooks, skipped, choices,
                                      next_held)

    os.makedirs(staging_dir, exist_ok=True)
    pc.dump_backup(doc, os.path.join(staging_dir, pc.BACKUP_RELPATH))
    # 보류 파일을 읽지 못했다면 쓰지 않는다 — 빈 상태로 덮으면 사용자의 선택이 조용히
    # 사라진다. 그 경우 SKILL.md가 파일을 지울 경로를 안내한다(6.4).
    # **게이트는 한 섹션에 걸리는데 파일은 두 섹션의 상태를 담는다.** pluginConfigs만
    # 접힌 실행에서는 enabledPlugins가 정상 처리되므로 release 선택이 base에는 반영되고
    # (④) 파일에는 남지 않아, 다음 백업에서 H3가 다시 걸려 **그 해제가 1회용이 된다.**
    # 그래도 이 게이트가 옳다 — 빈 상태로 덮으면 declined 전부가 조용히 사라진다.
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
- `next_held_state`의 release 정리(`_extended_value` 조건)를 지우기 → release 정리 테스트가 잡아야 한다
- `configured` 차감을 지우기 → 그 테스트가 잡아야 한다
- 지문 대상을 `masked` 대신 `repo`(원본)로 바꾸기 → `pluginConfigs`는 마스킹이 값을 바꾸므로 지문 테스트가 잡아야 한다
- `if "pluginConfigs" not in skipped` 가드를 지우기 → 깨진 파일 보존 테스트가 잡아야 한다
- 두 파일의 쓰기 순서를 맞바꾸기 → **닫힌다.** 스테이징 디렉토리 자리에 **일반 파일**을 두면 `os.makedirs`가 `FileExistsError`로 죽고, 그 시점에 보류 파일이 쓰였는지로 순서가 갈린다. `test_the_held_file_is_untouched_when_the_staging_write_fails`가 잡아야 한다. (**앞선 판의 "어떤 테스트도 잡지 못한다"는 틀렸다** — 실패를 두 쓰기 **사이**에 주입할 필요가 없다. 첫 쓰기 자체를 실패시키면 같은 것이 갈린다.)
- `pc.dump_backup(doc, ...)`의 경로에 `.tmp`를 붙이기 → 직접 쓰기 테스트가 잡아야 한다
- `choice_list`의 `isinstance(v, str)` 필터를 지우기 → 형태 어긋남 테스트가 잡아야 한다
- **최상위 `status`를 `"skipped" if skipped else "ok"`로 바꾸기** → 최상위 status 테스트가 잡아야 한다. 이 계약이 뒤집히면 두 섹션이 접힌 실행에서 정상 처리된 마켓플레이스 섹션까지 버려진다
- **`report[section]`의 `kept_stale`·`kept_local`·`base_keys`를 각각 `[]`로 비우기(셋을 따로)** → 보고 대조 테스트가 **각각** 잡아야 한다. 하나씩 비워야 뭉뚱그린 단정과 구별된다
- **`base_keys`의 `sorted(nb)`를 `list(nb)`로** → 정렬 테스트가 잡아야 한다(이 fixture는 해시에 의존하지 않아 결정적이다)
- **`next_held_state`의 `sorted(released)`를 `list(released)`로** → release 목록 테스트가 잡아야 한다. `released`는 `read_held_state`가 리스트로 돌려주고(`plugin_config.py:274-279`) 새 항목이 뒤에 덧붙으므로, **정렬 역순으로 들어오는 fixture를 만들면 catch가 결정적이다** — 해시 순서에 기대지 말 것. (set을 정렬하는 자리였다면 catch가 `1 - 1/n!`로 확률적이었을 것이다. Task 9에서 그 구별을 놓쳐 `M8 CAUGHT`를 결정적 판정으로 잘못 받았다.)
- **`for section in pc.SECTIONS`를 `("enabledPlugins", "pluginConfigs")`로 좁히기** → 마켓플레이스 섹션 테스트가 잡아야 한다
- **`main`의 `args[0] == "apply-base"` 검사만 제거** / **`len(args) == 4`를 `len(args) >= 4`로** → CLI parametrize가 각각 잡아야 한다
- **`except` 튜플에서 `ValueError` 제거** → 선택 결과 JSON 테스트가 잡아야 한다
- **`kept_local.append(key)`를 `if key in masked` 블록 **밖**으로 옮기기** → 보고가 "실제로 적용한 것"이 아니라 "요청받은 것"이 된다. **현재 규정은 `kept_stale`이 요청을, `kept_local`이 적용을 보고하는 비대칭이다** — 어느 쪽이 계약인지 구현자가 정하고 docstring에 근거를 남길 것. 어느 쪽이든 대응 테스트가 있어야 한다
- **`if section == "enabledPlugins"` 가드를 지워 release의 `keep_local` 동시 적용을 전 섹션으로 넓히기** → release한 id가 `pluginConfigs`에도 항목을 가지면, 사용자가 고르지도 않은 그 섹션의 base까지 레포 값으로 전진한다. 실제 설정 차이가 케이스 8·9 대신 **케이스 7로 착지**해 다음 백업에서 로컬 값이 레포를 덮는다. 앞머리가 말한 "한쪽 선택이 다른 섹션의 base를 조작한다"의 **다른 입구**이고, 선택 JSON의 섹션 중첩만으로는 막히지 않는다. 대응 테스트가 잡아야 한다 — **같은 fixture에서 `enabledPlugins` 쪽은 전진함을 함께 단정해야** 공허해지지 않는다
- **`next_held_state`의 이전 declined 정리에서 `key in masked`를 지우기** → 레포에서 사라진 항목이 보류 파일에 남고, 같은 값이 레포에 되돌아오면 **사용자가 다시 고르지 않았는데 조용히 보류로 복귀한다.** spec 6.4가 문장으로 정한 동작이다. 대응 테스트가 잡아야 한다 — **레포에 남아 있는 declined 항목을 함께 둔 fixture여야** "전부 지운다"와 구별된다
- **declined 기록의 `if key in masked` 가드를 지우기** → 레포에 없는 id가 `declined`로 오면 `KeyError`로 restore가 통째로 선다(SKILL.md의 대화가 만드는 JSON이므로 실재하는 갈래다). 대응 테스트가 잡아야 한다 — **레포에 있는 declined 항목을 함께 둔 fixture여야** "declined를 전부 무시한다"와 구별된다
- **`choice_list`의 `choices.get(section)`을 `choices.get(section) or {}`로 완화(섹션 값 타입 검사 제거)** → 섹션 값이 리스트·문자열·정수면 `section_choices.get`이 `AttributeError`로 restore를 세운다. 바로 위의 `isinstance(v, str)` 변조가 재는 것은 **원소** 타입뿐이라 **섹션 값** 타입은 이 변조가 처음 잰다 — `choice_list` docstring이 약속한 "형태가 어긋나도 세우지 않는다"의 나머지 절반이다. **`None` 갈래만으로는 잡히지 않는다**(`None or {}`가 그대로 빈 선택이 된다) — 리스트·문자열·정수 갈래를 fixture에 넣고, 다른 정상 섹션의 선택이 **적용됨**을 함께 단정할 것
- **보류 파일 payload에서 `"version": HELD_SCHEMA_VERSION`을 지우기** → `read_held_state`의 버전 게이트(`claims_newer_schema`)가 읽을 필드가 사라진다. **지금은 무증상이라** 스키마를 올리는 시점에야, 그것도 이 파일만 게이트를 못 타는 형태로 드러난다. 대응 테스트가 잡아야 한다

- **`value_held`를 `value_held_for` 대신 손으로 조립하기**(`hooks[section]["hold"]`를 **정규화 없이** 부르기) → 이 함수가 스스로 주석에 적은 함정 둘 중 **정규화 쪽**이다. H4의 지문이 마스킹된 레포 값에서 나오므로 평문을 그대로 넘기면 보류가 통째로 비고, 사용자가 보류해 둔 pluginConfigs가 base로 전진한다. `test_this_runs_decline_takes_effect_on_the_base_immediately`가 잡아야 한다 — **그 fixture의 레포 값은 평문이어야 한다.** `SENTINEL`을 두면 마스킹이 항등이 되어 원본과 마스킹된 값의 지문이 같아지고 이 변조가 무증상이 된다
- **release 강제분을 base에는 적용하되 `kept_local` 보고에서 빼기** → SKILL.md가 "로컬 유지를 고르신 항목"에서 그 키를 빼고 안내해 사용자가 base 전진을 볼 길이 없다. ④의 **보고 계약**이다
- **release 합류의 중복 제거 가드(`if key not in keep_local`) 지우기** → 사용자가 같은 키에 ③과 ④를 함께 고른 갈래에서 `kept_local`에 같은 키가 두 번 실린다. 모순 입력이 아니라 실재하는 조합이므로 대응 테스트가 있어야 한다
- **②③의 적용 순서 뒤집기**(`keep_stale`의 `pop`을 `keep_local` 뒤로) → **오늘 어떤 테스트도 잡지 못하는 것으로 판정됐으나 그것은 fixture 공백이었다.** 같은 키를 ②③에 함께 두면 갈린다: ③은 `key in masked` 가드를 가져 레포에 값이 있을 때만 적용되고, 그때 ②는 이미 모순 입력이라 ③이 이기는 것이 옳다. 뒤집으면 모순 입력이 정당한 선택을 조용히 덮는다. 대응 테스트가 있어야 한다
- **보류 파일의 `os.makedirs` 지우기** → 이 줄이 일하는 유일한 자리는 백업을 한 번도 하지 않은 기기의 `~/.claude/.sync-state/`다(`.sync-state/base`는 `write_base`가 만들지만 디렉토리 자체는 아무도 먼저 만들지 않는다). 빠지면 `FileNotFoundError` → `{"status": "skipped"}`로 접혀 **decline이 영영 기록되지 않는다.** 이미 존재하는 tmp 디렉토리를 주는 fixture로는 잡히지 않는다 — **없는 디렉토리를 주는 fixture**가 필요하다
- **재보류 시 지문 갱신 차단**(`declined[key] = ...`을 `setdefault`로) → 레포 값이 바뀐 뒤 같은 키를 다시 거절하면 낡은 지문이 남아 H4가 다시 매치되지 않고 **매 restore마다 다시 묻는다.** 이전 파일에 실재하지 않는 지문을 둔 fixture여야 "이전 값을 그대로 옮긴 것"과 구별된다
- **`main`의 `apply_base(args[1], args[2], ...)`를 맞바꾸기** → `staging_dir` 자리에 레포 `plugins.json`의 **파일 경로**가 들어가 `os.makedirs`가 `FileExistsError`로 접히고 `{"status": "skipped"}` + **종료 코드 0**이 된다. SKILL.md는 정상으로 읽고 base는 전혀 전진하지 않는다 — 이 task가 `.tmp` 규칙에서 스스로를 제외하면서까지 막으려던 실패 모양이다. **거부 갈래 둘만으로는 잡히지 않는다**; 형제 `plan_mcp`의 `test_apply_base_cli_writes_staging_file`과 같은 **성공 경로** 테스트가 있어야 한다(격리 HOME에 `settings.json`과 `installed_plugins.json`을 함께 넣을 것 — 하나라도 없으면 섹션이 접혀 단정이 배선과 무관하게 참이 된다)
- **`_extended_value`를 부르는 셋 중 하나가 자기 판을 되살리기**(`_make_hold`의 H3 / `held_kinds` / `next_held_state`, 각각 따로) → 오늘 `enabledPlugins`의 정규화가 항등이라 **결과가 같아 어떤 값 fixture로도 드러나지 않는다.** 술어를 monkeypatch로 뒤집어 셋이 함께 따라가는지를 재는 테스트가 각각 잡아야 한다
- **`next_held_state`에 `normalized_sections(repo)` 대신 `repo`(원본)를 넘기기** → `pluginConfigs`는 마스킹이 값을 바꾸므로 지문 테스트가 잡아야 한다. `enabledPlugins` 쪽은 오늘 무증상이고, 그 절반을 재는 것이 바로 위 항목이다

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py \
        plugins/claude-sync/lib/plugin_config.py \
        plugins/claude-sync/tests/test_plugin_scripts.py \
        plugins/claude-sync/tests/test_plugin_config.py
git commit -m "feat(restore): apply-base — 선택 override 넷과 plugins-held.json 소유"
```

---

### Task 10.5: 설치 집합 읽기 — "설치됨"을 실제로 아는 것

**근거:** spec 3.4, 9.2, 9.3.1, 9.3.2, 8.4

> **[2026-08-31 갱신 — spec 4차 개정 ②③④⑤]**
>
> - **2단계/4단계를 가른 결정은 유지된다.** 다만 **근거가 바뀌었다** — 아래 표의
>   *"bare install은 exit 0이지만 값을 덮는다"* 가 정본이고(이 자리는 `2246227`이 이미
>   정정했다), spec 9.3.1도 그렇게 다시 썼다.
> - **실행 순서만 `1 → 2 → 4 → 3`으로 바뀌었다.** 번호와 `depends_on`은 그대로이므로
>   이 task의 **설치 집합 판정은 한 글자도 바뀌지 않는다.**
> - **`read_hold_inputs`는 이제 5-튜플이다.** 이 task가 4-튜플로 확장한 뒤,
>   `4b17f68`이 다섯째 값 `degraded`를 더했다 — `plugins-held.json`이 깨지면
>   `pluginConfigs`만 접히는데 그 파일이 함께 잃는 `release`를 읽는 자리는 **접히지 않는**
>   `enabledPlugins`에 있기 때문이다. 아래 본문의 "4-튜플" 서술과 `test_..._returns_four_values`
>   는 **당시 기록**이고, 현행 계약은 spec **3.5**(신설: *"접는 값 × 그 값을 읽는 자리"*
>   전수 표)와 `read_hold_inputs`의 docstring이다. **그 표에 값을 새로 접을 때는 열거부터
>   늘린다** — 한 줄을 세다 말아서 넷째 행이 실제로 fail-open이었다.

**`enabledPlugins`의 키 부재는 미설치가 아니다.** 매니페스트 기본값(`defaultEnabled`)에 위임하는 상태다 — Task 9의 앞머리가 같은 사실을 `disable` 쪽에서 이미 명시한다. 그래서 로컬 문서만으로는 "설치됨"과 "미설치"를 가를 수 없고, `installed_plugins.json`을 읽어야 한다.

두 곳이 그 사실을 요구한다.

| 어디 | 무엇이 막혔나 |
|---|---|
| Task 8의 `absent_locally` | spec 9.2가 *"H3 항목은 '설치됨'과 '미설치'를 구별해 말한다"*를 요구하는데, 지금은 "로컬 섹션 문서에 값이 없다"까지만 말할 수 있어 이름을 그렇게 바꿨다 |
| Task 9의 `install` | spec 9.3.1이 **2단계**(`plugin install <id>`)와 **4단계**(`plugin install <id> --config k=v`)를 다른 단계로 정의하고 9.3.2가 단계 간 의존까지 규정하는데, 계획이 둘을 `install` 하나로 합쳤다. **이미 설치된 플러그인에 bare install이 나간다** — 그 명령은 `exit 0`이지만 값을 `true`로 덮어써 꺼 둔 플러그인을 켜고 객체 값을 평탄화한다(브리프 1-b #2 · 2026-08-29 스모크 2장 — 실측). *초판은 이 자리에 "exit 1의 거짓 실패"라고 적었다. 결함의 존재는 그대로이고 증상만 다르다 — 실패가 아니라 **조용한 상태 파괴**다.* |

**같은 파일을 두 번 파싱하지 않는다.** `read_auto_ids`가 이미 `installed_plugins.json`을 파싱하며 **auto 집합만** 뽑아 쓴다. 옆에 두 번째 파서를 두면 이 저장소가 반복해 막아 온 "파서 두 벌"이 어댑터 안에서 재생산되고, 두 판의 예외 갈래가 갈리면 부분 skip이 조용히 전체 skip이 된다.

**설치 판정의 스코프는 `user`다.** 이 동기화 전체가 `--scope user`로 동작하고(spec 9.3.1이 그것을 못 박는다), `read_auto_ids`도 `scope == "user"`로 좁힌다. 따라서 설치 집합은 **user 스코프 항목이 하나라도 있는 id**다 — `auto` 값과는 무관하다.

**예외 갈래는 `AutoFlagsUnavailable` 하나를 공유한다.** 같은 파일의 같은 파싱에서 나오므로 갈래를 나눌 근거가 없고, 나누면 `read_hold_inputs`의 skip 범위 표가 둘로 갈린다.

**Files:**
- Modify: `plugins/claude-sync/lib/plugin_config.py` (`read_installed` 신규, `read_auto_ids`는 위임, `read_hold_inputs`가 4-튜플)
- Modify: `plugins/claude-sync/skills/sync-status/scripts/compare_plugins.py`
- Modify: `plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py`
- Modify: `plugins/claude-sync/skills/sync-backup/scripts/collect_plugins.py` (4-튜플 언팩만)
- Modify: `plugins/claude-sync/tests/test_plugin_config.py`, `tests/test_plugin_scripts.py`

- [ ] **Step 1: 실패하는 test 작성**

`tests/test_plugin_config.py`와 `tests/test_plugin_scripts.py`에 더한다.

```python
def test_read_installed_returns_auto_and_installed_from_one_parse(tmp_path):
    """(auto_ids, installed_ids) — installed_ids는 auto 여부와 무관하다 (3.4).

    "이 기기에 설치되어 있는가"와 "의존성으로 딸려 왔는가"는 다른 질문이고, 9.3.1의
    2단계/4단계를 가르는 것은 전자뿐이다. auto가 아닌 manual@m과 auto 키가 아예 없는
    plain@m을 함께 두어 auto_ids ⊊ installed_ids가 **실측으로** 성립하게 한다 —
    두 집합이 같은 fixture만 있으면 installed_ids에 auto 조건이 섞여도 드러나지 않는다.
    """
    path = write_installed(tmp_path, {
        "dep@m": [{"scope": "user", "auto": True}],
        "manual@m": [{"scope": "user", "auto": False}],
        "plain@m": [{"scope": "user"}],
    })
    auto_ids, installed_ids = pc.read_installed(path)
    assert auto_ids == frozenset({"dep@m"})
    assert installed_ids == frozenset({"dep@m", "manual@m", "plain@m"})
    assert auto_ids < installed_ids


def test_read_installed_counts_user_scope_only(tmp_path):
    """설치 판정의 스코프는 user다 — auto 판정과 같은 근거다 (9.3.1).

    이 동기화 전체가 --scope user로 동작하므로 project 스코프에만 있는 플러그인은
    restore가 만들 수 있는 상태가 아니다. "설치됨"으로 세면 2단계를 건너뛰어 영영
    설치되지 않는다. user 스코프 항목을 **하나라도** 가진 both@m을 같은 fixture에 두어
    빈 결과가 "아무것도 세지 않았다"와 구별되게 한다.
    """
    path = write_installed(tmp_path, {
        "proj@m": [{"scope": "project", "auto": True}],
        "proj-plain@m": [{"scope": "project"}],
        "both@m": [{"scope": "project"}, {"scope": "user"}],
    })
    auto_ids, installed_ids = pc.read_installed(path)
    assert installed_ids == frozenset({"both@m"})
    assert auto_ids == frozenset()


def test_read_installed_shares_the_single_failure_branch(tmp_path):
    """실패 갈래는 read_auto_ids와 **같은 AutoFlagsUnavailable 하나**다.

    같은 파일의 같은 파싱에서 나오므로 나눌 근거가 없고, 나누면 read_hold_inputs의
    skip 범위 표가 둘로 갈린다. 정상 문서를 먼저 재어 "무엇을 넣어도 raise"와 구별한다.
    """
    ok = write_installed(tmp_path, {"p@m": [{"scope": "user"}]})
    assert pc.read_installed(ok) == (frozenset(), frozenset({"p@m"}))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    bad_entry = tmp_path / "entry.json"
    bad_entry.write_text(json.dumps({"version": 2, "plugins": {"p@m": "손상"}}),
                         encoding="utf-8")
    no_plugins = tmp_path / "nokey.json"
    no_plugins.write_text(json.dumps({"version": 2}), encoding="utf-8")
    for path in (tmp_path / "none.json", broken, bad_entry, no_plugins):
        with pytest.raises(pc.AutoFlagsUnavailable):
            pc.read_installed(str(path))


def test_read_auto_ids_delegates_instead_of_keeping_a_second_parser(tmp_path,
                                                                   monkeypatch):
    """위임 자체는 **값으로 잴 수 없다** — 옛 본문을 복사해 두어도 결과가 같기 때문이다.

    그래서 read_installed를 갈아끼우고 **그 반환의 첫 자리가 그대로 나오는지**를 잰다.
    본문 사본이 남아 있으면 이 단정이 실제 파일을 다시 파싱한 값을 돌려주어 실패한다.
    파일은 정상 문서로 둔다 — 사본이 예외로 죽는 것이 아니라 **다른 값**을 내는 것으로
    구별되어야 한다.
    """
    path = write_installed(tmp_path, {"dep@m": [{"scope": "user", "auto": True}]})
    assert pc.read_auto_ids(path) == frozenset({"dep@m"})
    monkeypatch.setattr(pc, "read_installed",
                        lambda p=None: (frozenset({"stub@m"}), frozenset({"other@m"})))
    assert pc.read_auto_ids(path) == frozenset({"stub@m"})


def test_read_hold_inputs_parses_the_installed_file_once(tmp_path, monkeypatch):
    """파서는 한 벌이다 — read_auto_ids가 read_installed에 **위임한다**.

    옆에 두 번째 파서를 두면 두 판의 예외 갈래가 갈리고, 갈리면 부분 skip이 조용히
    전체 skip이 된다.

    **이 단정이 지키는 것은 read_hold_inputs가 두 함수를 따로 부르는 형태다.** 위임
    자체는 여기서 잡히지 않는다 — read_auto_ids에 옛 본문 사본을 남겨도 read_hold_inputs가
    read_installed를 직접 부르므로 열림 횟수는 그대로 1이다(실측). 위임은
    test_read_auto_ids_delegates_instead_of_keeping_a_second_parser가 스텁으로 잡는다.
    """
    installed = write_installed(tmp_path, {
        "dep@m": [{"scope": "user", "auto": True}],
        "manual@m": [{"scope": "user", "auto": False}]})
    held = write_held(tmp_path, {"version": 1, "pluginConfigs": {"delta@m": "abc"}})
    opened = []
    real_open = builtins.open

    def counting_open(path, *args, **kwargs):
        opened.append(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)
    auto_ids, installed_ids, held_state, skipped = pc.read_hold_inputs(installed, held)
    monkeypatch.undo()
    assert opened.count(installed) == 1
    # 아래 넷이 비지 않아야 위의 1이 "한 번도 안 열었다"가 아님이 증명된다.
    assert auto_ids == frozenset({"dep@m"})
    assert installed_ids == frozenset({"dep@m", "manual@m"})
    assert held_state["pluginConfigs"] == {"delta@m": "abc"}
    assert skipped == {}


def test_read_hold_inputs_returns_four_values_and_folds_installed_on_failure(tmp_path):
    """(auto_ids, installed_ids, held_state, skipped).

    **빈 installed_ids가 조용한 fail-open이 아닌 근거는 같은 갈래의 skip이다** —
    enabledPlugins·pluginConfigs 두 섹션이 함께 접히므로 그 값이 쓰이지 않는다.
    접지 않고 전파하면 소비자가 그것을 "아무것도 설치 안 됨"으로 읽어 restore가 전부
    재설치를 시도한다. 정상 갈래를 먼저 재어 빈 집합 단정이 공허하지 않게 한다.
    """
    good = write_installed(tmp_path, {"p@m": [{"scope": "user"}]})
    ok = pc.read_hold_inputs(good, str(tmp_path / "none-held.json"))
    assert len(ok) == 4
    assert ok[1] == frozenset({"p@m"}) and ok[3] == {}
    auto_ids, installed_ids, held_state, skipped = pc.read_hold_inputs(
        str(tmp_path / "missing.json"), str(tmp_path / "none-held.json"))
    assert auto_ids == frozenset() and installed_ids == frozenset()
    assert held_state == pc.EMPTY_HELD
    assert sorted(skipped) == ["enabledPlugins", "pluginConfigs"]


# --- 6.4 보류 상태 파일 ---


def test_compare_splits_absent_locally_by_actual_installation(tmp_path):
    """9.2 — H3 항목은 "설치됨"과 "미설치"를 구별해 말한다.

    dep@m은 **설치되어 있으면서** settings.json에 없다(auto 의존성). ghost@m은 어디에도
    없다. 한 fixture에서 두 갈래가 **둘 다 비지 않아야** 이 배선이 "absent_locally를
    그대로 복사한 것"이나 하드코딩과 구별된다.

    absent_locally는 그대로 둔다 — "레포 값을 보존합니다"가 거짓이 되는 조건은 설치
    여부와 별개의 사실이고 spec 8.4가 그것을 요구한다.

    stale@m은 이 필드가 **absent_locally의 부분집합**임을 못박는다 — 로컬 문서에 값이
    있으면서 설치되지 않은 상태다. CLI는 그런 상태를 만들지 않는다(9.3.3: uninstall이
    키를 지운다). 보류 키 전체에서 뽑으면 이 키가 들어와, 문구가 값 차이를 말해야 할
    항목(8.4의 셋째 행)까지 "미설치"로 보고된다.
    """
    out = compare(tmp_path, local={"enabledPlugins": {"stale@m": True}},
                  repo={"enabledPlugins": {"dep@m": True, "ghost@m": ["1.0.0"],
                                           "stale@m": ["2.0.0"]}},
                  installed=write_installed(
                      tmp_path, {"dep@m": [{"scope": "user", "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    # 세 키가 전부 보류다 — 하나라도 빠지면 아래 두 목록이 저절로 좁아진다.
    assert section["held"] == {"auto": ["dep@m"], "local_marketplace": [],
                               "extended_value": ["ghost@m", "stale@m"]}
    assert section["absent_locally"] == ["dep@m", "ghost@m"]
    assert section["not_installed"] == ["ghost@m"]


def test_compare_splits_plugin_configs_by_installation_too(tmp_path):
    """설치 구별은 **두 섹션 모두**에 실린다 — 위의 enabledPlugins만 재면 절반이 미측정이다.

    INSTALL_KEYED_SECTIONS를 enabledPlugins 하나로 좁히는 회귀는 그 섹션을 재는 단정에
    걸리지 않는다 — 거기서는 필드가 그대로 남기 때문이다. 좁히면 pluginConfigs의
    "미설치" 문구가 통째로 사라지고, read_hold_inputs가 installed_ids를 접어도 되는
    근거("그 값을 읽는 자리가 전부 함께 접힌 **두** 섹션 안에 있다")의 절반이 검증되지
    않은 채 남는다.

    here@d는 **설치돼 있으면서 auto가 아니다.** auto 집합과 설치 집합이 같은 fixture에서는
    이 필드를 auto 집합으로 판정하는 회귀가 무증상이라, 그 변조가 compare 쪽에서 오래
    미측정으로 남아 있었다(Task 10.5 quality review Q9). 실제 증상은 수동 설치한
    플러그인을 전부 "미설치"로 보고하는 것이다.

    보류는 H2(레포의 directory 마켓플레이스)로 만든다. 다섯 키가 전부 보류여야 아래 두
    목록이 저절로 좁아진 것과 구별된다.

    **not_installed을 원소 넷으로 두는 것은 순서를 재기 위해서다** — 이 목록을 집합
    순회로 만드는 회귀는 정렬 순서를 깬다. 다만 그 가드는 **확률적이다**: 집합 순회
    순서가 우연히 정렬 순서와 같으면 통과한다(실측 — 원소 셋에서 PYTHONHASHSEED에 따라
    통과하는 시드가 있었다). 원소를 늘리는 것이 그 확률을 낮추는 유일한 수단이다.
    """
    out = compare(tmp_path, local={},
                  repo={"extraKnownMarketplaces": {"d": DIR_SOURCE},
                        "pluginConfigs": {"here@d": {"options": {}},
                                          "gone@d": {"options": {}},
                                          "also@d": {"options": {}},
                                          "mid@d": {"options": {}},
                                          "zap@d": {"options": {}},
                                          "brio@d": {"options": {}},
                                          "quix@d": {"options": {}}}},
                  installed=write_installed(tmp_path, {"here@d": [{"scope": "user"}]}))
    section = out["sections"]["pluginConfigs"]
    expected = ["also@d", "brio@d", "gone@d", "here@d", "mid@d", "quix@d", "zap@d"]
    assert section["status"] == "ok"
    assert section["held"] == {"auto": [], "declined": [],
                               "local_marketplace": expected}
    assert section["absent_locally"] == expected
    # here@d만 빠진다 — 설치돼 있기 때문이다(auto는 아니다).
    assert section["not_installed"] == [k for k in expected if k != "here@d"]


def test_compare_does_not_call_a_marketplace_uninstalled(tmp_path):
    """설치 구별은 **키가 플러그인 id인 두 섹션에만** 싣는다.

    extraKnownMarketplaces의 키는 마켓플레이스 이름이라 installed_ids와 이름 공간이
    다르다 — 실으면 등록만 안 된 마켓플레이스가 전부 "미설치 플러그인"으로 보고된다.
    같은 실행의 enabledPlugins가 그 필드를 **갖는** 것을 함께 재어, 필드가 어디에도
    없는 회귀와 구별한다.
    """
    doc = {"enabledPlugins": {"p@d": True}, "extraKnownMarketplaces": {"d": DIR_SOURCE}}
    out = compare(tmp_path, local={}, repo=doc)
    markets = out["sections"]["extraKnownMarketplaces"]
    # 비지 않았다 — 실을 값이 있었는데도 싣지 않은 것이다.
    assert markets["absent_locally"] == ["d"]
    assert "not_installed" not in markets
    assert out["sections"]["enabledPlugins"]["not_installed"] == ["p@d"]


def test_compare_does_not_claim_everything_is_uninstalled_when_a_section_is_skipped(
        tmp_path):
    """설치 집합을 못 읽었는데 "전부 미설치"로 접히면 restore가 전부 재설치를 시도한다.

    같은 fixture를 정상 installed 파일로 한 번 더 돌려 not_installed가 **비지 않게**
    나오는 것을 함께 잰다 — 없으면 "필드가 없다"가 설치 판정과 무관하게 참이 된다.
    """
    repo = {"enabledPlugins": {"ghost@m": ["1.0.0"]}}
    ok = compare(tmp_path, local={}, repo=repo)
    assert ok["sections"]["enabledPlugins"]["not_installed"] == ["ghost@m"]
    out = compare(tmp_path, local={}, repo=repo,
                  installed=str(tmp_path / "missing.json"))
    section = out["sections"]["enabledPlugins"]
    assert section == pc.skipped_section(section["reason"])
    assert "not_installed" not in section


def test_a_broken_held_file_does_not_empty_the_installed_set(tmp_path):
    """부분 실패 — 보류 파일만 깨진 실행에서 설치 집합은 **살아 있어야 한다**.

    read_hold_inputs가 installed_ids를 빈 frozenset으로 접는 갈래는 AutoFlagsUnavailable
    **하나뿐**이고, 그 갈래는 enabledPlugins·pluginConfigs를 함께 skip한다. 그 대응이 이
    접힘이 fail-open이 아닌 유일한 근거다. 보류 파일 갈래(HeldStateUnavailable)는
    pluginConfigs 하나만 skip하므로, 여기서도 설치 집합을 접으면 enabledPlugins가 살아
    있는 채로 그 집합만 비어 정확히 근거가 경고한 재앙이 일어난다 — compare는 설치된
    플러그인 전부를 "미설치"로 보고하고, build_plan은 그 전부를 2단계에 실어 bare install을
    낸다. **exit 0이라 죽지도 않고**(실측) 값이 전부 `true`로 덮여 꺼 둔 플러그인이 전부
    켜진다(9.3.1).

    **한 fixture를 두 스크립트에 함께 건다.** 설치 집합의 소비자가 그 둘뿐이라, 한쪽만
    재면 다른 쪽에서 조용히 갈릴 수 있다.

    ghost@m은 정말로 설치돼 있지 않다 — 없으면 "미설치가 비었다"와 "2단계가 비었다"가
    설치 판정과 무관하게 저절로 참이 된다.

    **설치된 넷은 skipped_already_installed의 순서를 재기 위한 개수다** — 이 목록을 설치
    집합 순회로 만드는 회귀는 정렬 순서를 깬다. 그 가드도 위와 같은 이유로 확률적이다.
    """
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    # 값이 확장 포맷이라 다섯 다 H3 보류다 — 보류여야 absent_locally에 들어온다.
    repo = {"enabledPlugins": {"one@m": ["1.0.0"], "two@m": ["2.0.0"],
                               "three@m": ["3.0.0"], "four@m": ["4.0.0"],
                               "five@m": ["5.0.0"], "six@m": ["6.0.0"],
                               "ghost@m": ["9.0.0"]},
            "extraKnownMarketplaces": {"m": GH}}
    installed = write_installed(tmp_path, {"one@m": [{"scope": "user"}],
                                           "two@m": [{"scope": "user"}],
                                           "three@m": [{"scope": "user"}],
                                           "four@m": [{"scope": "user"}],
                                           "five@m": [{"scope": "user"}],
                                           "six@m": [{"scope": "user"}]})
    out = compare(tmp_path, local={}, repo=repo, installed=installed, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    section = out["sections"]["enabledPlugins"]
    assert section["status"] == "ok"
    assert section["absent_locally"] == ["five@m", "four@m", "ghost@m", "one@m",
                                        "six@m", "three@m", "two@m"]
    assert section["not_installed"] == ["ghost@m"]

    plan = build_plan(tmp_path, local={}, repo=repo, installed=installed, held=str(held))
    assert plan["sections"]["pluginConfigs"]["status"] == "skipped"
    assert plan["install"] == ["ghost@m"]
    assert plan["skipped_already_installed"] == ["five@m", "four@m", "one@m",
                                                "six@m", "three@m", "two@m"]


def test_plan_splits_bare_install_from_the_config_step_by_the_installed_set(tmp_path):
    """9.3.1 — 2단계(`plugin install <id>`)와 4단계(`install --config k=v`)는 다른 단계다.

    이미 설치된 플러그인에 bare install이 나가면 그 값이 `true`로 덮인다 — **exit 0이라
    실패로 보이지도 않는다**(브리프 1-b #2 · 2026-08-29 스모크 2장 — 실측). old@m은 이
    기기에 **설치돼 있고** 레포에만 pluginConfigs가 있으므로 2단계가 아니라 4단계다.
    (*초판은 "exit 1로 죽어 거짓 실패"라고 적었다 — 같은 저장소의 1-b #2가 이미 반증하고
    있던 문장이다. 분리의 필요는 그대로이고 사유만 바뀐다.*)

    두 목록이 **서로 다른 비지 않은 값**을 갖는다 — 한쪽이 비면 분리 자체가 측정되지 않고
    "합쳐도 같은 결과"와 구별할 수 없다.
    """
    out = build_plan(
        tmp_path, local={},
        repo={"enabledPlugins": {"new@m": True},
              "extraKnownMarketplaces": {"m": GH},
              "pluginConfigs": {"old@m": {"options": {"apiKey": pc.SENTINEL}}}},
        installed=write_installed(tmp_path, {"old@m": [{"scope": "user"}]}))
    # 두 섹션이 각각 후보를 하나씩 냈다 — 한 섹션만 기여하면 분리가 절반만 측정된다.
    assert out["sections"]["enabledPlugins"]["add"] == ["new@m"]
    assert out["sections"]["pluginConfigs"]["needs_secret"] == ["old@m"]
    assert out["install"] == ["new@m"]
    assert out["skipped_already_installed"] == ["old@m"]
    assert out["config_keys"] == {"old@m": ["apiKey"]}


def test_plan_does_not_reinstall_what_only_the_manifest_default_enables(tmp_path):
    """**enabledPlugins의 키 부재는 미설치가 아니다** — 매니페스트 기본값(defaultEnabled)에
    위임하는 상태다. 이 task의 존재 이유가 그 구별이다.

    default@m은 settings.json의 enabledPlugins에 **없지만** 설치돼 있다. 2단계/4단계
    판정을 설치 집합 대신 **로컬 섹션 문서**로 하면 이 키가 2단계로 가서 bare install이
    나가고, 그 명령이 매니페스트 기본값에 위임하던 상태를 **명시적 `true` 키로 굳힌다**
    (exit 0이라 조용하다).

    miss@m은 어디에도 없다 — 2단계가 비지 않아야 위 단정이 "install이 늘 빈다"로 저절로
    참이 되지 않는다.
    """
    out = build_plan(
        tmp_path, local={},
        repo={"enabledPlugins": {"default@m": True, "miss@m": True},
              "extraKnownMarketplaces": {"m": GH}},
        installed=write_installed(tmp_path, {"default@m": [{"scope": "user"}]}))
    # 둘 다 add 버킷이다 — 로컬 섹션 문서만 보면 구별할 수 없다는 사실을 못박는다.
    assert out["sections"]["enabledPlugins"]["add"] == ["default@m", "miss@m"]
    assert out["install"] == ["miss@m"]
    assert out["skipped_already_installed"] == ["default@m"]


def test_plan_keeps_the_value_and_dependency_steps_on_both_lists(tmp_path):
    """3·4단계의 기준은 2단계 목록이 아니라 **두 목록의 합집합**이다.

    disable_after_install — 이미 설치된 id도 값 맞추기(3단계) 대상이다. here@m은 설치돼
      있고 로컬 enabledPlugins에 값이 없으며(매니페스트 기본값에 위임 = 켜짐으로 가정)
      레포가 false다. 2단계 목록으로 좁히면 이 disable이 사라져 플러그인이 켜진 채 남는다.
    depends_on — 근거는 명령의 형태다. 두 단계 모두 `plugin install <id@marketplace>`
      형태라 1단계 등록에 의존한다(9.3.2의 단계 종속이 아니다 — 그쪽은 2단계 실패를
      다루고 skipped_already_installed에는 2단계가 없다). 좁히면 등록에 실패한
      마켓플레이스로 4단계 명령이 나가 거짓 실패를 양산한다.
    config_keys — 코어의 needs_secret 버킷에서 나오고 설치 여부와 무관하다. 어느 한쪽으로
      좁히면 다른 쪽 id의 설정이 어디에서도 채워지지 않는다.

    세 필드가 **두 목록의 항목을 모두** 담는지가 요지이므로, 각 목록에 항목이 하나씩
    들어가는 fixture를 쓴다.
    """
    out = build_plan(
        tmp_path, local={},
        repo={"enabledPlugins": {"here@m": False, "gone@m": False},
              "extraKnownMarketplaces": {"m": GH},
              "pluginConfigs": {"here@m": {"options": {"apiKey": pc.SENTINEL}},
                                "gone@m": {"options": {"token": pc.SENTINEL}}}},
        installed=write_installed(tmp_path, {"here@m": [{"scope": "user"}]}))
    assert out["install"] == ["gone@m"]
    assert out["skipped_already_installed"] == ["here@m"]
    assert out["disable_after_install"] == ["gone@m", "here@m"]
    assert out["depends_on"] == {"gone@m": "m", "here@m": "m"}
    assert out["config_keys"] == {"gone@m": ["token"], "here@m": ["apiKey"]}
    # 값 페이로드도 합집합을 따른다 — 좁히면 SKILL.md가 3·4단계 문구를 만들 값을 잃는다.
    assert sorted(out["repo_values"]) == ["gone@m", "here@m"]
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: 신규 테스트 FAIL

- [ ] **Step 3: 구현**

`lib/plugin_config.py` — `read_auto_ids`의 본문을 `read_installed`로 옮기고, 두 집합을 **한 번의 순회**에서 모은다.

```python
def read_installed(installed_path=None):
    """(auto_ids, installed_ids) — 한 번의 파싱으로 둘을 만든다 (3.4).

    installed_ids는 **user 스코프 항목이 하나라도 있는 id**다. auto 여부와 무관하다 —
    "이 기기에 설치되어 있는가"와 "의존성으로 딸려 왔는가"는 다른 질문이고, 전자만이
    9.3.1의 2단계/4단계를 가른다.

    **스코프를 user로 좁히는 것이 auto 판정과 같은 근거다.** 이 동기화 전체가
    --scope user로 동작한다(9.3.1). project 스코프에만 있는 플러그인은 restore가
    만들 수 있는 상태가 아니므로 "설치됨"으로 세면 2단계를 건너뛰어 영영 안 깔린다.

    **파일을 두 번 파싱하지 않는다.** read_auto_ids가 이 함수에 위임한다 — 옆에 두 번째
    파서를 두면 두 판의 예외 갈래가 갈리고, 갈리면 부분 skip이 조용히 전체 skip이 된다.

    실패 갈래는 **AutoFlagsUnavailable 하나**다 — 같은 파싱에서 나오므로 나눌 근거가
    없다. **"알아볼 수 없다"의 전수 목록 열 가지를 이 docstring에 그대로 옮겨 온다** —
    read_auto_ids가 2줄 위임으로 줄어들므로 거기 두면 목록이 어디에도 남지 않는다.
    """
    # 기존 read_auto_ids 본문. 순회에서 auto 집합과 함께 user 스코프 id를 모은다.


def read_auto_ids(installed_path=None):
    """의존성으로 자동 설치된 플러그인 id 집합 (3.4). read_installed에 위임한다.

    서명을 유지하는 것은 이 함수에 테스트 열다섯이 걸려 있고, 그 열다섯이 실패 갈래
    열 가지의 전수 목록을 지키기 때문이다. 위임으로 바꿔도 그 보증이 그대로 남는다.
    """
    return read_installed(installed_path)[0]
```

`read_hold_inputs`는 `read_installed`를 한 번 부르고 **4-튜플**을 돌려준다. 실패 시 `installed_ids`도 `frozenset()`으로 접되, **그 접힘이 조용한 fail-open이 아닌 이유**(같은 갈래에서 두 섹션이 skip되므로 그 값이 쓰이지 않는다)를 docstring에 적는다.

세 스크립트의 언팩을 4-튜플로 바꾸고, `compare_plugins`와 `plan_plugins build_plan`이 `installed_ids`를 쓴다. **`collect_plugins`와 `apply_base`는 언팩만 바꾼다** — 설치 여부가 필요 없다.

**`compare_plugins`의 죽은 주석을 지운다.** 지금 `absent_locally` 옆에 *"이 스크립트는 설치 여부를 알 수 없다 — installed_plugins.json에서 읽는 것은 auto 집합뿐"*이라고 적혀 있고, 이 task가 그 전제를 없앤다. 남겨 두면 shipped 주석이 거짓이 된다.

**spec 9.2·9.3.1의 문구를 이 task가 확정한다.** 9.2의 *"H3 항목은 '설치됨'과 '미설치'를 구별해 말한다"*가 이제 실제로 가능해졌고, 9.3.1의 2·4단계가 계획 출력에서 갈린다. 두 절을 구현에 맞춰 갱신하되 **spec 수정은 orchestrator가 한다** — 구현자는 필요한 문구를 보고만 한다.

- [ ] **Step 4: test를 실행하여 통과를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

하네스: `python3 ~/.claude/suberpowers/tools/mutate.py --repo <저장소> --spec <json> --jobs 8`

- `read_installed`의 스코프 필터(`scope == "user"`)를 지워 전 스코프를 세기 → A-2가 잡아야 한다
- `installed_ids`에 `auto is True` 조건을 **추가**해 auto 집합과 같게 만들기 → A-1이 잡아야 한다
- `read_auto_ids`를 위임 대신 옛 본문 복사로 되돌리기 → **파싱 횟수 단정만으로는 잡히지 않는다**(실측 SURVIVED). `read_hold_inputs`가 `read_installed`를 직접 부르므로 `read_auto_ids`에 사본을 남겨도 파일 열림 횟수는 1이다. 위임 자체를 재려면 `read_installed`를 스텁으로 갈아끼워 `read_auto_ids`가 그것을 통과하는지 보는 단정이 필요하다. 파싱이 실제로 두 번 나는 형태는 `read_hold_inputs`가 두 함수를 따로 부르는 쪽이고, 그것을 A-4가 잡는다
- `read_hold_inputs`의 실패 갈래에서 `installed_ids`를 **접지 않고** 전파하기 → B-7이 잡아야 한다
- 2단계/4단계 분리를 되돌려 `install` 하나로 합치기 → D-11·D-12가 잡아야 한다
- 4단계 판정을 `local["enabledPlugins"]` 유무로 바꾸기(설치 집합 대신) → D-13이 잡아야 한다. **"유일한 검출자"는 아니다**(실측: 테스트 넷이 잡는다) — 이 task의 존재 이유가 그 구별이라 여러 단정이 겹친다
- `compare_plugins`의 설치 구별을 `absent_locally` 전체로 되돌리기 → C-8·C-9가 잡아야 한다
- 섹션 skip 시 설치 구별 필드를 "전부 미설치"로 채우기 → C-10이 잡아야 한다

- `INSTALL_KEYED_SECTIONS`를 `("enabledPlugins",)`로 좁히기 → `pluginConfigs` 쪽 설치 구별 테스트가 잡아야 한다. **이 변조가 없으면 두 섹션 중 하나가 통째로 미측정으로 남는다**(실측 SURVIVED였다)
- `compare`의 설치 판정을 `installed_ids` 대신 `auto_ids`로 바꾸기 → **auto가 아닌 설치 항목을 가진 fixture만이 잡는다.** 이 task의 존재 이유가 그 구별인데, 배선 쪽에서 처음엔 무보증이었다
- `read_hold_inputs`의 `HeldStateUnavailable` 갈래에도 `installed_ids`를 접기 → 부분 실패 테스트가 잡아야 한다. 보류 파일만 깨진 실행에서 `enabledPlugins`는 살아 있는데 설치 집합이 비면, 설치된 플러그인 전부가 "미설치"로 보고되고 restore가 전부 bare install을 시도한다 — **docstring이 스스로 경고한 fail-open이다**
- `not_installed`·`skipped_already_installed`의 집합 차 순서를 뒤집기 → 해당 테스트가 잡는다. **다만 이 catch는 확률적이다**(집합 순회 순서에 의존). 원소 수를 넷으로 두면 시드당 통과율이 5% 아래이고, 결정적으로 만들려면 프로덕션 코드를 건드려야 한다 — 그 성질을 테스트 docstring에 적을 것

**SURVIVE가 나오면 인계 전에 닫는다.** 등가 변이라면 왜 관측 불가능한지 근거를 적는다.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/lib/plugin_config.py \
        plugins/claude-sync/skills/sync-status/scripts/compare_plugins.py \
        plugins/claude-sync/skills/sync-restore/scripts/plan_plugins.py \
        plugins/claude-sync/skills/sync-backup/scripts/collect_plugins.py \
        plugins/claude-sync/tests/test_plugin_config.py \
        plugins/claude-sync/tests/test_plugin_scripts.py
git commit -m "feat(plugins): 설치 집합을 읽어 2단계와 4단계를 가른다"
```

---

### Task 11: 상태 기계 — 보류의 다회차 커버리지

**근거:** spec 7.3, 5.3, 14.2 #4 / plan ① Task 9 quality review I2

**지금 보류의 상태 기계 커버리지는 0이다.** 열 시나리오 어디에도 보류 키가 없다. 실측으로 확인된 것: 가짜 플러그인 어댑터를 붙이고 **코어의 "보류 키는 레포 값을 그대로 싣는다"를 지워도 20 passed 그대로**였다.

**왜 다회차여야 하는가.** 단발 테스트가 잡는 것은 1회차다. *"레포가 그 키를 잃은 채로 고정점에 든다"* 는 다회차 결과를 보는 것이 그 파일의 존재 이유이고, 그 결함 계열이 정확히 이 개정이 없애려던 "타 기기 항목의 전멸"이다. 게다가 7.3이 스스로 경고한 **H3 탈출구의 착지 지점**은 정의상 회차 사이에 상태가 변해야 표현되는데, 현재 `repeat_backup`은 회차마다 같은 `local`과 같은 `hold`를 넘기므로 **구조적으로 표현할 수 없다.**

**`ADAPTERS`에 한 줄만 더하는 것으로는 부족하다 — 다만 "돌지 않아서"가 아니다.** plan ① Task 9 리뷰의 실측(`enabledPlugins`는 **불리언이든 배열이든 돌지 않는다**, 각각 3 failed / 5 failed)은 `hold` 인자도 `Adapter`의 정규화도 **없던 옛 하네스**의 것이다. 이 task가 그 둘을 들이면 장애물이 사라져 한 줄을 더해도 **돈다**(실측: 48 passed). 그러니 그 실측을 배제의 근거로 옮겨 적으면 안 된다. 진짜 근거는 이렇다 — 이 섹션 고유의 것은 정규화와 H3 둘인데, 정규화는 항등(`_identity`)이라 잴 것이 없고, 열 시나리오는 확장 값을 base와 로컬에만 두고 레포에는 한 번도 싣지 않아 **레포 값만 보는 H3가 한 번도 발화하지 않는다**(실측: 진짜 hold를 붙여도 48 passed 그대로고, hold 호출 33회 중 발화가 0회다). 그 H3는 보류 시나리오가 실제 hold로 맡는다.

**`Adapter`가 픽스처 값을 한 번 정규화해 싣는다.** `pluginConfigs` 값을 원본 그대로 실으면 판정표 서른 중 **여덟이 FAIL**한다(실측) — `merge`·`next_base`는 마스킹된 값을 돌려주는데 기존 단정은 원본을 기대하기 때문이다. 픽스처 값은 그대로 두고 `Adapter`에서 통과시키는 것이 `normalize`의 멱등 계약(5.2) 위에서 성립한다. (plan ①의 "`pluginConfigs`는 그대로 돈다"는 이 픽스처에 대해 사실이 아니다.)

**보류 훅은 테스트 더블이 아니라 실제 어댑터의 것을 쓴다.** 가짜 훅을 쓰면 `_make_hold`의 회귀를 이 파일이 하나도 잡지 못한다.

**Files:**
- Modify: `plugins/claude-sync/tests/test_mcp_state_machine.py`

- [ ] **Step 1: 실패하는 test 작성**

파일 상단의 docstring과 `Adapter`·`ADAPTERS`·`repeat_backup`을 교체하고 보류 시나리오를 더한다.

```python
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

    enabledPlugins가 없는 것은 의도다 — 다만 "돌지 않아서"가 아니다. 케이스 9는 세 값이
    서로 달라야 하는데 이 섹션의 불리언은 둘뿐이라 세 번째는 확장 포맷일 수밖에 없고,
    그 값 셋으로 여기 한 줄을 더하면 열 개가 그대로 **돈다**(실측: 48 passed).

    빼는 근거는 그 열 개가 이 섹션 **고유의 것을 하나도 재지 못한다**는 것이다. 고유한
    것은 정규화와 H3 둘인데, 정규화는 항등이라(_identity) 잴 것이 없고, H3는 레포 값만
    보는데 열 시나리오는 확장 값을 base와 로컬에만 두고 레포에는 한 번도 싣지 않는다
    (실측: 진짜 hold를 붙여도 48 passed 그대로다 — hold 호출 33회 중 H3 발화가 0회다).
    그 H3는 아래 보류 시나리오가 실제 hold를 붙여 맡는다.
    """
    assert {adapter.name for adapter in ADAPTERS} == {
        "mcp", "plugins:extraKnownMarketplaces", "plugins:pluginConfigs"}


@pytest.fixture(params=ADAPTERS, ids=lambda a: a.name)


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


def held_state(released=()):
    return {"pluginConfigs": {}, "release": {"enabledPlugins": sorted(released)}}


def live_hold(section, state):
    """**실제 어댑터의 hold**를 회차마다 현재 상태로 다시 만든다.

    테스트 더블을 쓰면 _make_hold의 회귀를 이 파일이 하나도 잡지 못한다.
    state는 before_round가 바꾼다 — 이 파일에서 그 변경은 전부 보류의 **이탈**이다
    (해제 셋, prune 하나, 해제 표식 정리 하나). 진입은 전이가 아니라 초기 base가
    표현한다 — 아래 test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3.

    섹션 하나짜리 문서를 넘기므로 held_context의 directory_names가 비고, 따라서 이
    시나리오들에서 발화하는 것은 **H1과 H3뿐이다** — H2는 소스가 없어 항상 거짓이고
    H4는 pluginConfigs 섹션에서만 본다.
    """
    def hold(local, repo):
        hooks = pc.build_hooks({section: local}, {section: repo},
                               auto_ids=state["auto_ids"], held_state=state["held"])
        return hooks[section]["hold"](local, repo)
    return hold


def enabled_adapter(state):
    """enabledPlugins 어댑터 — 실제 hold를 다는 것이 요점이다.

    값 튜플은 아래 어느 보류 시나리오도 읽지 않는다(전부 리터럴을 넘긴다).
    Adapter.__init__의 케이스 9 불변식(A·B·ORIG가 정규화 후에도 서로 다를 것)을
    통과시키기 위해서만 있고, 그 불변식이 지키는 판정표는 이 어댑터가 설계상 돌지
    않는다(위 test_adapters_cover_every_section_that_can_run_the_decision_table).
    """
    return plugin_adapter("enabledPlugins", (True, False, ["1.0.0"]),
                          hold=live_hold("enabledPlugins", state))


def test_h3_hold_preserves_the_repo_value_across_rounds():
    """보류 유지 — 레포의 버전 제약이 회차를 거쳐도 true로 덮이지 않는다.

    코어의 "보류 키는 레포 값을 그대로 싣는다"를 지우면 여기서 걸린다.

    두 빈 단정의 무게가 다르다(실측) — H3를 지우면 conflicts가 ["p@m"]으로 **채워진다**
    (케이스 9). deleted는 채워질 수 없다: 그 갈래는 `not in_l`을 요구하는데 로컬이
    p@m을 계속 쥐고 있다. 채워지는 배치는 아래
    test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3이다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)
    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {})
    for report, repo, base in snapshots:
        assert repo["p@m"] == ["1.0.0"]
        assert report["held"] == ["p@m"]
        # deleted는 여기서 채워질 수 없다(로컬이 p@m을 계속 쥔다) — 동반 기록이다.
        # conflicts는 다르다: H3를 지우면 ["p@m"]으로 채워진다(케이스 9).
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
        if index == 3:
            # next_held_state의 release 정리를 흉내낸다 — "레포 값이 불리언이 되었거나
            # 키가 사라진 항목을 정리한다". 표식을 남겨두면 마지막 held 단정이 **표식
            # 때문에도** 참이 되어, 그 아래 적은 "레포 값이 불리언 → 자연 해제"를
            # 확인하지 못한다(H3의 두 조건이 함께 거짓이라 어느 쪽이 이겼는지 모른다).
            state["held"] = held_state()
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

    (H1의 value.add를 지우면 local_stale이 ["z@m"]으로 **채워진다**(케이스 4, 실측).
    반면 deleted는 여기서 채워질 수 없다 — 로컬이 z@m을 계속 쥐고 있어 `not in_l`이
    성립하지 않는다. **케이스 3이 실제로 날 수 있는 배치**는 아래
    test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3이 맡는다.)
    """
    state = {"auto_ids": frozenset({"z@m"}), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 0:
            repo = {}                                   # 타 기기가 z를 지웠다
        if index == 2:
            state["auto_ids"] = frozenset()             # prune 이후 — 보류 이탈
        return local, repo, base

    # 가운데 인자(초기 레포)는 읽히지 않는다 — index 0의 before가 첫 backup_round
    # **전에** {}로 덮기 때문이다(실측: 다른 값으로 바꿔도 38 passed).
    snapshots = repeat_backup(adapter, {"z@m": True}, {"z@m": True}, {"z@m": True},
                              rounds=4, before_round=before)
    for report, repo, base in snapshots[:2]:
        # deleted는 여기서 채워질 수 없다(로컬이 z@m을 계속 쥔다) — 동반 기록이다.
        # local_stale은 다르다: H1의 value.add를 지우면 채워진다(케이스 4).
        assert report["deleted"] == [] and report["local_stale"] == []
        assert "z@m" not in repo                        # 보류 중에는 조용하다
        assert "z@m" not in base
    assert snapshots[2][1]["z@m"] is True               # 이탈 → 케이스 1로 push
    # 같은 이유로 공허하다 — 동반 기록이다. 채워지는 배치는 아래
    # test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3이다.
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


def test_restore_base_drops_the_held_key_instead_of_freezing_it():
    """restore 경로의 계약 — apply-base가 value_held를 **스스로 계산해** 넘긴다.

    plan_plugins.apply_base는 pc.value_held_for로 집합을 만들어 ks.next_base에 넘긴다.
    plugin_adapter.next_base가 그 형태를 그대로 흉내내는데, 위 다섯 시나리오는 전부
    merge 경로(backup_round)만 타므로 그 한 줄을 지나지 않는다 — 여기가 유일한 자리다.
    빼면 예외도 경고도 없이 보류 키가 **이전 base 값으로** 얼어붙는다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)
    local = {"mine@m": True}
    repo = {"mine@m": True, "p@m": ["1.0.0"]}
    frozen = {"mine@m": True, "p@m": True}      # 보류가 걸리기 전에 합의했던 값
    base = adapter.next_base(local, frozen, repo)
    assert "p@m" not in base                    # 값 보류 키는 base에서 제거된다 (5.3)
    assert base["mine@m"] is True               # 보류가 아닌 키는 그대로 전진한다


def test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3():
    """5.3이 지목한 손실 경로 — 보류 키가 base에 얼어붙으면 해제 순간 케이스 3이 난다.

    이 기기는 p@m을 켜지 않았고(로컬에 없다), 타 기기가 레포에 버전 제약을 올려 H3가
    보류한다. 보류 중 base에서 그 키가 빠지므로(5.3) 해제 시 in_s가 거짓이 되어
    **케이스 2**로 착지하고 레포 값이 살아남는다. base에 남으면 in_s가 참이 되어
    **케이스 3(deleted)** 이 나고 타 기기가 올린 값이 레포에서 지워진다 — 위 시나리오들의
    deleted 단정이 구조적으로 채워질 수 없는 것과 달리, 여기서는 실제로 채워진다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 2:
            state["held"] = held_state(["p@m"])         # 해제만 한다 — keep_local 없음
        return local, repo, base

    snapshots = repeat_backup(adapter, {"mine@m": True},
                              {"mine@m": True, "p@m": ["1.0.0"]},
                              {"mine@m": True, "p@m": True},
                              rounds=4, before_round=before)
    for report, repo, base in snapshots[:2]:
        assert report["held"] == ["p@m"]
        # conflicts는 여기서 채워질 수 없다(양 갈래 모두 `in_l`을 요구한다) — 동반 기록이다.
        assert report["deleted"] == [] and report["conflicts"] == []
        assert repo["p@m"] == ["1.0.0"]
        assert "p@m" not in base                        # 보류 중 base에서 빠진다 (5.3)
    report, repo, base = snapshots[2]
    # 실측: base 제거 규칙을 지우면 여기서 deleted == ["p@m"]이 되고 레포가
    # {"mine@m": True}로 줄어든다 — 타 기기가 올린 버전 제약이 사라진다.
    assert report["deleted"] == []                      # 케이스 3이 **아니다**
    assert report["repo_ahead"] == ["p@m"]              # 케이스 2로 착지
    assert repo["p@m"] == ["1.0.0"]
    assert snapshots[3] == snapshots[2]                 # 이후 불변
```

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_state_machine.py -v`
기대: 보류 시나리오 일곱이 FAIL 또는 ERROR(헬퍼 미정의). 판정표 열 개는 **세 어댑터로 30개**가 되어야 한다.

- [ ] **Step 3: 구현**

Step 1의 편집이 곧 구현이다. **소스 코드는 바꾸지 않는다** — 이 task는 기존 구현의 미검증 경로를 덮는 것이 목적이다. 보류 시나리오가 FAIL한다면 그것은 실제 결함이므로 `lib/plugin_config.py` 또는 `lib/keyed_sync.py`를 고치고 **왜 고쳤는지 커밋 메시지에 남긴다.**

- [ ] **Step 4: 개수와 단정이 약해지지 않았는지 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_mcp_state_machine.py -v`
기대: 판정표 시나리오 10개 × 어댑터 3 = **30개**, 어댑터 목록 가드 1개, 보류 시나리오 7개 — 이 파일에서 **38개**다.

실행: `git diff plugins/claude-sync/tests/test_mcp_state_machine.py | grep '^-' | grep -c assert`
실행: `git diff plugins/claude-sync/tests/test_mcp_state_machine.py | grep '^+' | grep -c assert`
기대: 뒤의 수가 앞의 수보다 크다. 작거나 같으면 단정이 사라진 것이므로 확인한다.

실행: `uv run --with pytest pytest plugins/claude-sync/tests -q`
기대: `0 failed`

- [ ] **Step 4b: 변조 확인 (필수)**

**이 task의 존재 이유가 변조 확인이다.** 아래는 전부 446개가 잡지 못했던 것들이다.

- `keyed_sync.merge`의 값 보류 갈래에서 `if name in repo: merged[name] = repo[name]`을 지우기 → **보류 유지 시나리오가 잡아야 한다.** 잡지 못하면 이 task는 실패다
- `_next_base_normalized`의 `if name in value_held: continue`를 지우기 → base 제거 단정이 잡아야 한다
- `plugin_adapter.next_base`에서 `value_held=`를 빼기 → **restore 경로를 지나는 시나리오만이 잡는다.** merge 경로만 타는 시나리오로는 SURVIVE한다(실측) — 보류 키의 base 제거를 재는 시나리오가 반드시 하나 있어야 한다
- `plugin_config._make_hold`의 H3에서 `key not in released` 검사를 지우기 → 해제 착지 시나리오가 잡아야 한다
- H1의 **`value.add`**를 지우기 → auto 시나리오가 잡아야 한다. **`action.add`는 이 파일이 구조적으로 잡을 수 없다** — 코어가 "action 축은 `restore_plan`만 소비한다, `diff`·`merge`·`next_base`는 value 축만 본다"를 명시하고 이 파일은 그 셋만 돈다. 그쪽 가드는 `test_plugin_config.py`·`test_plugin_scripts.py`가 진다
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

> **[2026-08-31 갱신 — spec 4차 개정 ④]** spec 14.3의 에뮬레이터 계약표가 2026-08-29
> 실환경 스모크에 맞춰 바뀌었다. **에뮬레이터가 곧 CLI 동작의 정의**이므로 이 task의
> 계약이 곧 그 표다.
>
> | 행 | 옛 계약 | 실측 | 에뮬레이터 상태 |
> |---|---|---|---|
> | `install` | *"키를 `true`로. 단 기존 값이 배열이면 보존"* | **배열이면 보존, 그 외에는 매니페스트의 `defaultEnabled`(기본 `true`)** (스모크 7장) | **미반영** — `install`이 여전히 `True`를 쓴다 |
> | `install` 재실행 | (에뮬레이터는 **처음부터 exit 0**이었다) | exit 0 | 고칠 것이 없었다. 틀렸던 것은 산문이다 |
> | `enable`/`disable`에 미설치 id | exit 1, 아무것도 안 씀 | **exit 0이고 키를 만든다**(유령 키) | **반영됨**(`61d7567` — `_set_value`) |
> | `marketplace add` | 언제나 github 모양 | **인자에서 출처를 판별한다** | **미반영**(의도적 단순화. docstring이 그렇게 자인한다) |
> | `marketplace remove`의 `pluginConfigs` 연쇄 | 추정 | **지운다**(스모크 8장 추정 1) | docstring이 아직 *"실측 없음 — 추정"* 이라 적는다 |
>
> **가장 무거운 것은 첫 행이다.** 에뮬레이터에 매니페스트 `defaultEnabled` 개념이 없으면
> spec 9.3.1이 순서를 바꾼 이유(**4단계가 3단계를 되돌린다**)를 **교대 테스트가 재현할 수
> 없다** — `install`이 언제나 `true`를 쓰면 `defaultEnabled: false` 갈래가 존재하지 않는다.
> 다음 라운드의 대상이다.

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
            if self._blocked(plan, plugin_id, blocked):
                continue
            self.cli.install(plugin_id)
        for plugin_id in plan["disable_after_install"]:             # 3단계
            if self._blocked(plan, plugin_id, blocked):
                continue
            self.cli.disable(plugin_id)
        for plugin_id, options in (secrets or {}).items():          # 4단계
            # 실제 흐름은 **계획이 지목한 키만** 되묻는다. 대조하지 않으면 계획이
            # 요구하지 않은 id에도 설정이 채워져 실제 흐름이 만들 수 없는 상태가 되고,
            # 이어지는 백업이 그 값을 레포로 민다(r2 리뷰 m12).
            assert plugin_id in plan["config_keys"], plugin_id
            if self._blocked(plan, plugin_id, blocked):
                continue
            self.cli.install(plugin_id, config=options)
        return self._apply_base(backup_path, plan, choices or {})

    @staticmethod
    def _blocked(plan, plugin_id, blocked):
        """1단계 등록이 실패한 마켓플레이스에 속하는가 (9.3.2)."""
        return plan["depends_on"].get(plugin_id) in blocked

    def _apply_base(self, backup_path, plan, choices):
        merged = {section: {"keep_stale": [], "keep_local": []} for section in pc.SECTIONS}
        for section, values in choices.items():
            # setdefault로 두면 섹션 이름 오타가 예외 없이 통과한다 — choice_list가
            # 모르는 섹션을 그냥 무시하므로 선택을 하나도 적용하지 않은 restore가
            # 초록으로 지나간다(9.3.4를 섹션별로 쓸 때 밟는다).
            assert section in pc.SECTIONS, section
            merged[section].update(values)
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
    """**실측 없음 — 추정.** 1.2와 브리프 C1이 재는 것은 객체/**미설치** 행이다."""
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
    assert cli.marketplace_remove("m") == 1      # 1-b #8 — 재실행은 exit 1


def test_dependency_install_marks_auto_and_explicit_install_clears_it(tmp_path):
    """N6 — 명시적 설치는 auto 표식을 **되돌릴 수 없게** 지운다."""
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset({"child@m"})
    cli.install("child@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_prune_removes_orphaned_auto_entries(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    cli.uninstall("parent@m")
    cli.prune()
    assert "child@m" not in cli.settings()["enabledPlugins"]
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


# --- 14.2 #1 부트스트랩 / #6 레포 쓰기 실패 ---

def test_backup_bootstraps_the_base_blob_with_three_sections(tmp_path):
    """7.4의 배선 결함을 잡는 유일한 테스트 — base가 영영 생성되지 않으면 삭제 전파가 죽는다.

    **단 `Device` 모형의 배선이지 SKILL.md의 배선이 아니다.** 실제 배선의 같은 계열
    오사용(`update_base.py "$BASE_STAGING"` → `"$SYNC_REPO"`)은 어떤 테스트도 잡지
    못한다 — Task 14 Step 4b가 그 자리를 다룬다.
    """
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


def test_a_skipped_backup_does_not_promote_stale_staging(tmp_path):
    """`Device.backup`의 rmtree를 지키는 단정 — 없으면 옛 staged 내용이 base로 올라간다.

    두 조건이 갈리려면 **base가 빈 채로 staged만 남은 시점**이 필요하다. 첫 백업을
    `push=False`로 돌려 그 시점을 만든 뒤 settings.json을 지우고 백업하면, rmtree가
    있으면 게이트가 끝내 닫혀 base가 생기지 않고 없으면 옛 파일이 base로 올라간다.
    """
    dev = make_device(tmp_path)
    dev.cli.install("p@m")
    dev.backup(push=False)
    assert os.path.exists(os.path.join(dev.staging, pc.BACKUP_RELPATH))
    os.remove(dev.cli.settings_path)
    report = dev.backup()
    assert report["status"] == "skipped"
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


# --- 9.3.2 등록 실패가 막는 단계 ---

BLOCKED_REPO = {
    "enabledPlugins": {"p@m": True, "q@m": True},
    "extraKnownMarketplaces": {"m": GH},
    "pluginConfigs": {"p@m": {"options": {"token": "s3cr3t"}}},
}


def _blocked_device(tmp_path, name):
    """p@m을 **미리 설치해 둔다** — 그래야 4단계만 남아 2단계 필터가 가리지 못한다."""
    dev = make_device(os.path.join(str(tmp_path), name), repo_init=BLOCKED_REPO)
    dev.cli.install("p@m")
    return dev


def test_a_blocked_marketplace_stops_the_install_and_config_steps(tmp_path):
    """9.3.2 — 1단계 등록 실패는 2단계뿐 아니라 **4단계도** 막는다."""
    dev = _blocked_device(tmp_path, "blocked")
    plan = dev.restore(secrets={"p@m": {"token": "s3cr3t"}}, fail_marketplaces={"m"})
    assert plan["install"] == ["q@m"]                       # 2단계 대상
    assert plan["skipped_already_installed"] == ["p@m"]     # 2단계 대상이 아니다
    assert plan["config_keys"] == {"p@m": ["token"]}        # 4단계 대상
    assert dev.cli.settings()["extraKnownMarketplaces"] == {}   # 등록이 실제로 실패했다
    assert "q@m" not in dev.cli.settings()["enabledPlugins"]    # 2단계가 막혔다
    assert dev.cli.settings()["pluginConfigs"] == {}            # 4단계가 막혔다

    ok = _blocked_device(tmp_path, "ok")                    # 단정을 공허하지 않게 하는 절반
    ok.restore(secrets={"p@m": {"token": "s3cr3t"}})
    assert ok.cli.settings()["enabledPlugins"]["q@m"] is True
    assert ok.cli.settings()["pluginConfigs"]["p@m"]["options"] == {"token": "s3cr3t"}


def test_a_blocked_marketplace_stops_the_disable_step(tmp_path):
    """9.3.2 — 등록 실패는 2·4단계뿐 아니라 **3단계도** 막는다.

    위 테스트는 3단계를 재지 못한다 — 그 픽스처의 disable_after_install이 비어 루프가
    돌지 않는다. 3단계를 관측하려면 **네 조건이 함께** 필요하다(실측 — 넷 다 하중을
    받는 것을 변조로 확인했다). ① 레포 값이 false ② pluginConfigs로 candidates에
    들어옴 ③ 이미 설치됨(로컬에 값이 있어야 disable이 exit 0으로 쓴다 — 없으면 추정
    4번의 갈래로 떨어진다) ④ **그 마켓플레이스의 1단계 등록이 실패함**(_blocked는
    depends_on이 blocked에 있을 때만 참이다).

    **④가 놓치기 쉽다.** 등록이 성공하면 blocked가 비어 필터가 애초에 동작하지 않고,
    그 id에 secret까지 주어지면 3단계의 disable을 4단계의 install --config가 곧바로
    되돌린다(값이 배열이 아니면 true). 어느 쪽이든 필터 유무가 값에 나타나지 않는다(실측).
    같은 이유로 두 번째 복원에는 secrets를 주지 않는다.
    """
    dev = make_device(tmp_path, repo_init={
        "enabledPlugins": {"p@m": False},                       # (1)
        "extraKnownMarketplaces": {"m": GH},
        "pluginConfigs": {"p@m": {"options": {"token": pc.SENTINEL}}}})   # (2)
    dev.cli.install("p@m")                                      # (3)
    plan = dev.restore(fail_marketplaces={"m"})                 # (4)
    assert plan["disable_after_install"] == ["p@m"]
    assert plan["skipped_already_installed"] == ["p@m"]
    assert plan["depends_on"] == {"p@m": "m"}
    assert dev.local()["enabledPlugins"]["p@m"] is True         # 3단계가 막혔다

    dev.restore()                                               # 원인 제거 (secrets 없이)
    assert dev.local()["enabledPlugins"]["p@m"] is False        # 3단계가 실제로 값을 바꾼다
```

**규정 정정 다섯째(P5) — 위 `Device.restore`의 4단계는 초판에서 `blocked` 필터를 타지 않았다.** spec 9.3.2가 *"1단계 등록 실패는 2단계뿐 아니라 4단계도 막는다. 근거는 단계 종속이 아니라 명령의 형태다"*를 못 박고 `plan_plugins._install_dependencies`가 그래서 `depends_on`에 **2단계 ∪ 4단계**를 싣는데, 초판은 그 필터를 2·3단계에만 넣었다. 에뮬레이터의 `install`은 언제나 exit 0이므로 그 공백은 **실제 CLI가 도달할 수 없는 상태**(등록에 실패한 마켓플레이스의 플러그인에 설정이 채워진 상태)를 만들고, 이어지는 백업이 그 값을 레포로 밀어 Task 13의 14.2 #7이 거짓 초록이 된다. 세 곳이 같은 술어를 쓰도록 `_blocked`로 뽑았다. (초판대로면 4단계 필터 제거 변조가 **758 passed로 살아남는다** — 실측. 위 테스트를 더한 뒤 CAUGHT.)

**규정 정정 여섯째(P6) — `test_install_flattens_an_existing_object_value`의 "실측"은 미측정 칸이었다.** 브리프 C1과 spec 1.2의 표는 **네 행뿐이고**(배열/미설치·배열/재실행·객체/미설치·건드리지 않음) **객체/재실행 행이 없다.** 그런데 같은 규정의 Step 3이 `set_enabled`에 `_mark_installed`를 함께 부르게 했으므로 이 픽스처가 만드는 것은 객체/**재실행**이다 — 규정 안에서 닫힌 모순이고, 실측된 객체 행(미설치)에는 도달할 수 없다. 결론(`true`가 된다)은 맞고 **근거가 추정**이므로 그렇게 적는다. 같은 이유로 C1 1행(배열/미설치)도 이 픽스처로는 표현할 수 없다.

**규정 정정 여덟째(P8) — 초판이 3단계에 붙인 "미측정" 사유가 실측으로 거짓이었다.** 초판은 *"에뮬레이터의 `disable`이 미설치 id에 아무것도 쓰지 않아(Step 3의 `_set_value`) 3단계 필터를 지워도 관측되지 않는다"*라고 적었다. **결론(미측정)은 맞고 사유가 두 겹으로 틀리다.** ㉠ 위 `_blocked_device`가 만드는 계획은 `disable_after_install`이 **비어 있다** — `BLOCKED_REPO`의 `enabledPlugins`가 둘 다 `true`라 `value_command`가 `"disable"`을 내지 않기 때문이다. 즉 3단계 루프가 **한 번도 돌지 않아서** 관측되지 않는 것이지 `disable`이 무력해서가 아니다(실측). ㉡ 그리고 그 사유는 일반적으로도 거짓이다 — `pluginConfigs` 경로로 candidates에 들어온 **이미 설치된** id는 로컬 `enabledPlugins`에 값이 있으므로 `disable`이 **exit 0으로 값을 쓴다**(`plan_plugins.py:208-212`가 같은 사실을 적는다). 실측: 레포를 `{"enabledPlugins": {"p@m": false}, "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {"p@m": {"options": {"token": …}}}}`로 두고 로컬에 `p@m`을 설치한 뒤 **`fail_marketplaces={"m"}`으로** 복원하면, 계획이 `disable_after_install: ["p@m"]`을 내고 3단계 필터가 있으면 `p@m`이 `true`로 남지만 **필터를 지우면 `false`로 바뀐다.** (**세 조각 중 하나라도 빠지면 재현되지 않는다 — 전부 실측했다.** `extraKnownMarketplaces`를 빠뜨리면 `pluginConfigs`가 `needs_secret`으로 라우팅되지 않아 `config_keys`가 비고 `disable_after_install`도 `[]`가 되어 아무것도 관측되지 않으며, 그 상태에서 `secrets`를 함께 주면 4단계 가드가 `AssertionError: p@m`으로 먼저 죽는다. `fail_marketplaces`를 빠뜨리면 아래 P10의 이유로 관측되지 않는다.)

**규정 정정 열째(P10) — P8이 적은 관측 조건이 불완전했고, 지목한 자리가 그 조건을 만족하지 않았다.** P8은 관측 조건을 *"레포 값이 `false`이면서 `pluginConfigs`로 candidates에 들어오는 **이미 설치된** id"* 셋으로 적고, 그것을 세우는 자리로 *"14.2 #7이 정확히 그 모양이다"*를 지목했다. **둘 다 틀렸다.**

㉠ **네 번째 조건이 빠졌다 — 그 마켓플레이스의 1단계 등록이 실패해야 한다.** `_blocked`는 `plan["depends_on"][id]`가 `blocked`에 있을 때만 참이므로, 등록이 성공하면 필터는 애초에 동작하지 않는다. 게다가 등록이 성공하면 3단계가 낸 `disable`을 **4단계의 `install --config`가 곧바로 되돌린다**(`PluginCLI.install` — 값이 배열이 아니면 `true`). 같은 레포·같은 로컬로 네 갈래를 실측한 결과(복원 후 로컬 `enabledPlugins["p@m"]`, 원본 트리 / 3단계 필터를 지운 트리):

| 등록 실패 | secret 제공 | 원본 | 필터 제거 | 관측? |
|---|---|---|---|---|
| 예 | 예 | `True` | `False` | **관측됨** |
| 예 | 아니오 | `True` | `False` | **관측됨** |
| 아니오 | 예 | `True` | `True` | 안 됨 |
| 아니오 | 아니오 | `False` | `False` | 안 됨 |

㉡ **규정이 이미 코드로 적어 둔 14.2 #7(`test_blocked_install_is_recovered_by_the_next_restore`)은 그 조건을 하나도 만족하지 않는다** — 레포 `enabledPlugins`가 둘 다 `true`이고 `pluginConfigs`가 비었고 `p@m`이 미설치다. 실측: 그 픽스처는 원본 트리와 3단계 필터를 지운 트리에서 출력이 **완전히 같다**(`disable_after_install`이 두 회차 모두 `[]`). 즉 Task 13이 규정대로 14.2 #7을 구현해도 3단계는 닫히지 않았을 것이다. P6과 같은, **규정 안에서 닫힌 모순**이다.

**닫는 방법으로 자매 시나리오를 골랐다 — 14.2 #7의 픽스처를 고치지 않는다.** 두 관심사가 **같은 id에 반대되는 설치 상태**를 요구하기 때문이다: 14.2 #7의 주인공은 *미설치*여야 "부분 실패로 설치되지 않았다가 재실행에서 설치된다"를 재고, 3단계 관측 대상은 *이미 설치*여야 `disable`이 값을 쓴다. 한 픽스처에 넣으면 마켓플레이스 둘·플러그인 셋·설치 상태 둘이 얽히고, 무엇보다 3단계 시나리오가 안고 있는 함정(**두 번째 복원에 `secrets`를 주면 4단계가 3단계를 되돌린다**)에 14.2 #7이 조용히 의존하게 된다. 자매에서는 그 함정이 곧 주제라 docstring에 적힌다. 그래서 위 Step 1에 `test_a_blocked_marketplace_stops_the_disable_step`을 더했고, **14.2 #7은 2단계 판으로 그대로 둔다.**

**결과(실측): 3단계 blocked 필터 제거 변조가 이제 CAUGHT다**(그 자매 테스트가 잡는다). 네 조건 각각을 지우는 변조 넷도 전부 CAUGHT라 조건 목록이 장식이 아님을 확인했다. 필터를 세 곳에 다 두는 근거는 여전히 9.3.2이고, 이제 세 곳 모두 관측된다.

**규정 정정 아홉째(P9) — Step 1 코드 블록이 `install`의 옛 시그니처를 남겨 두었다.** 위 P7이 `install(..., dependencies=())`를 `set_manifest`로 옮겼는데, 그 정정이 **산문에만 반영되고 Step 1 코드 블록은 동기화되지 않았다.** 실제 시그니처는 `install(self, plugin_id, config=None)`이므로 옛 블록을 그대로 옮기면 `TypeError`로 죽는다. Task 12의 두 자리(`test_dependency_install_marks_auto_and_explicit_install_clears_it`·`test_prune_removes_orphaned_auto_entries`)와 **Task 13 Step 1의 `test_auto_dependency_round_trip_keeps_the_entry_in_the_repo`** 한 자리를 `set_manifest` → `install` 두 줄로 고쳤다 — Task 13 절은 산문이 이미 `set_manifest`를 지시하고 있어 **한 규정 안에서 산문과 코드가 모순이었다.**

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
        self._manifests = {}        # 플러그인 id → plugin.json의 dependencies 배열

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

    def set_manifest(self, plugin_id, dependencies=()):
        """플러그인 매니페스트(plugin.json)의 dependencies. CLI 명령이 아니다."""
        self._manifests[plugin_id] = list(dependencies)

    def set_directory_marketplace(self, name, path):
        """로컬 디렉토리 출처를 심는다 (H2). CLI 명령이 아니라 픽스처다."""
        data = self.settings()
        data["extraKnownMarketplaces"][name] = {
            "source": {"source": "directory", "path": path}}
        self._write(self.settings_path, data)
        return 0

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
    def install(self, plugin_id, config=None):
        """키를 true로. **단 기존 값이 배열이면 보존**하고 객체는 평탄화한다 (1.2).

        이미 설치돼 있어도 exit 0(멱등). 명시적 설치는 auto 표식을 지운다(N6) —
        되돌릴 수 없다. config는 **부분 병합**이다(N2). 의존성은 **매니페스트에서
        읽는다** — 명령의 인자가 아니다(N1).
        """
        dependencies = self._manifests.get(plugin_id, ())
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

    def prune(self):
        """부모가 사라진 auto 항목을 제거한다."""
        data = self.settings()
        installed = self.installed()["plugins"]
        removed = []
        for plugin_id, entries in list(installed.items()):
            auto = any(e.get("scope") == "user" and e.get("auto") is True for e in entries)
            parents = [p for p, children in self._manifests.items()
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

**규정 정정 일곱째(P7) — 초판의 두 API 모양이 CLI 명령 경계와 어긋났다.**
① `install(..., dependencies=())`는 **명령의 인자가 아니라 매니페스트(`plugin.json`)의 내용**이다(N1). 인자로 받으면 같은 부모를 설치하는 모든 호출부가 그 배열을 기억해야 하고, 특히 `Device.restore`의 2단계는 `install(plugin_id)`로만 부르므로 **복원 경로에서 의존성 끌어오기가 영영 표현되지 않는다**(9.3.1). `set_manifest` 픽스처로 옮기고 `install`이 그것을 읽게 했다. `_parents`도 `if dependencies:`일 때만 갱신돼 옛 부모 관계가 남았는데, 매니페스트를 보면 그 자리가 사라진다.
② `marketplace_add`/`set_directory_marketplace`는 **한 CLI 명령의 두 갈래**다. 합치지 않고 후자를 픽스처 절로 옮겼다 — 복원 경로가 directory 갈래에 도달하지 않기 때문이다(`plugin_config.marketplace_arg`의 docstring이 *"directory 출처는 여기 오지 않는다"*로 못 박고, H2가 그 앞에서 보류한다). 즉 이 값은 계획이 만들어 주지 않고 테스트가 직접 심어야 하는 로컬 상태다. 대신 `marketplace_add`에 **경로를 넘기면 조용히 github 출처가 된다**는 것을 그 자리에 적는다.

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
- `Device.backup`의 게이트 `os.path.exists(staged)`를 `report["status"] == "ok"`로 바꾸기 → **등가 변이다(실측). 잡히지 않는 것이 정상이다.** 두 조건이 갈리는 상태는 둘뿐이고 둘 다 관측 불가다 — (i) `status "ok"` + staged 부재는 `update_base.py`가 경고만 내고 exit 0, base SHA 불변이며, (ii) `status "skipped"` + staged 잔존은 **존재 게이트 쪽이 오히려 위험한데**(옛 staged 내용이 base를 덮는다) `backup()`의 `rmtree`가 그 상태를 막는다. 존재 게이트를 쓰는 이유는 더 강해서가 아니라 **SKILL.md 배선이라서**이고, 같은 계약을 `update_base`가 한 번 더 진다. 그 근거를 `Device.backup` 주석에 남길 것
- `collect`의 rename을 레포 쓰기보다 **앞으로** 옮기기 → 잡혀야 한다. 다만 **이것은 무방비 지점이 아니다** — 이 task 이전부터 있던 `tests/test_plugin_scripts.py`의 `test_collect_does_not_stage_when_repo_write_fails`가 이미 스크립트 층에서 잡는다(실측). 여기서 고쳐야 하는 것은 무방비가 아니라 **하네스 층 단정의 공허함**이다: 규정의 `test_base_does_not_advance_when_the_repo_file_cannot_be_written`의 base 단정은 그 테스트가 `update_base`를 아예 부르지 않는 데다 `collect_plugins.py`가 base를 쓰지도 않아 **어떤 구현에서도 참이다**(실측). 스테이징 최종 파일이 직전 백업 내용 그대로인지를 재는 **대체 단정**이 함께 있어야 한다
- `Device.backup`의 `shutil.rmtree(self.staging, ignore_errors=True)`를 지우기 → **잡혀야 한다.** 바로 위 일곱째를 등가로 판정하는 근거 전체가 이 한 줄에 걸려 있다 — rmtree가 없으면 (ii)가 실재하는 상태가 되고, `status "skipped"`인데도 옛 staged 내용이 base를 덮는다. 관측하려면 **base가 빈 채로 staged만 남은 시점**을 만들어야 한다: `backup(push=False)` → `settings.json` 제거 → `backup()` → `base() is None`. 두 번째 백업이 skipped라 새 staged가 생기지 않으므로, rmtree가 있으면 게이트가 끝내 닫히고 없으면 `update_base`가 옛 파일을 올린다. (규정 초판은 이 변조를 지시하지 않았고, 그 결과 rmtree를 지워도 **757 passed**였다 — 실측)
- **실패 갈래가 다른 파일에 남기는 부작용** 둘 → **잡혀야 한다.** 위 아홉은 전부 **성공 갈래**만 건드린다. ① `uninstall`이 exit 1로 죽는 자리에서도 `_forget_installed`를 부르게 하기 ② `_set_value`가 미설치 id에 exit 1을 내면서 `_mark_installed`는 부르게 하기. 두 파일 중 한쪽만 갱신되면 갈린다는 것이 이 파일의 핵심 위험인데, 실패 갈래의 단정이 전부 `settings()`만 보면 둘 다 조용하다(초판대로면 **758 passed로 둘 다 살아남는다** — 실측). ①은 "설치 기록만 있고 `enabledPlugins`에는 없는 id"가 필요한데 공개 API로는 만들 수 없으므로 파일을 직접 심는다(스코프 테스트와 같은 방식). **[2026-08-29 갱신]** ②의 문면은 더 이상 적용되지 않는다 — 실환경 스모크가 *"미설치 id에 `enable`/`disable`은 exit 1"*을 뒤집어(exit 0이고 키를 만든다) `_set_value`에 그 갈래가 없어졌다. 같은 위험을 재는 대체 변조는 **"유령 키를 만들면서 `_mark_installed`도 부르게 하기"**이고, `test_enable_and_disable_on_an_unknown_plugin_create_a_ghost_key`가 잡는다(실측 CAUGHT).
- **`_apply_base`가 알 수 없는 선택지 섹션 이름을 삼키기**(`assert section in pc.SECTIONS`를 `setdefault`로 되돌리기) → **잡혀야 한다.** `plan_plugins`의 `choice_list`가 모르는 섹션을 그냥 무시하므로, 삼키면 **선택을 하나도 적용하지 않은 restore**가 초록으로 지나간다. 정상 이름이 통과하는 절반을 함께 두어 "언제나 죽는다"가 아님을 잰다(초판대로면 SURVIVED — 실측).
- **restore 3단계의 `blocked` 필터를 지우기** → **잡혀야 한다.** 관측에는 네 조건이 함께 필요하다(위 P10) — 그 조건을 세운 자매 시나리오가 Step 1에 있다. 그 시나리오가 없으면 이 변조는 살아남는다(초판·r2 트리 둘 다에서 SURVIVED였다 — 실측). 함께 재는 것: **네 조건을 하나씩 지우는 변조 넷**(레포 값을 `true`로 · `pluginConfigs`를 비우기 · 사전 설치를 빼기 · `fail_marketplaces`를 빼기) → 넷 다 잡혀야 한다. 넷 중 하나라도 살아남으면 그 조건은 docstring의 장식이다.
- **`Device.restore`의 4단계 가드**(`assert plugin_id in plan["config_keys"]`)를 지우기 → **잡혀야 한다.** 없으면 계획이 되묻지 않은 id에도 설정이 채워져 **실제 흐름이 만들 수 없는 상태**가 만들어지고, 이어지는 백업이 그 값을 레포로 민다 — Task 13이 여섯 시나리오에서 `secrets`를 쓰므로 그때 조용한 fail-open이 된다. 정상 id가 통과하는 절반을 함께 두어 "언제나 죽는다"가 아님을 잰다.

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests/plugin_cli.py plugins/claude-sync/tests/test_plugin_cycle.py
git commit -m "test: CLI 에뮬레이터와 교대 하네스, 부트스트랩·rename 계약"
```

---

### Task 13: 교대 시나리오 — 선택지 실행 후의 수렴

**근거:** spec 14.2 #2·#3·#4·#5·#7·#8, 6.4, 7.3, 9.3.4, 9.3.5

**판정표를 100% 덮은 테스트가 전부 통과하는데도 시스템이 데이터를 잃을 수 있다.** 아래 여섯은 단위 테스트로 잡히지 않는 것들이고, 특히 #4·#5·#8은 서로를 대체하지 못한다 — #2·#3은 보류가 **유지되는 동안만** 보고, #2는 "사라지지 않음"만 보므로 **영원히 다시 묻는** 실패를 통과시킨다.

**에뮬레이터의 `marketplace add`는 언제나 github 모양의 값을 만든다(Task 12의 6번 — 에뮬레이터의 단순화다. 2026-08-29 스모크가 **실제 CLI는 인자에서 출처 종류를 판별한다**를 실측했고, url·git 두 출처의 값 모양은 여전히 미측정이다).** url·git 출처 시나리오를 쓰려면 **그 자리를 먼저 고쳐야 한다.** 고치지 않고 쓰면 시나리오가 조용히 github를 검증하고, `restorable`·`marketplace_arg`의 출처별 갈래는 하나도 타지 않는다. **결과는 "차이가 드러난다"보다 무겁다** — github는 왕복이 닫히지만(`marketplace_arg`가 `repo` 필드를 내고 에뮬레이터가 같은 필드에 되쓴다), url·git은 `marketplace_arg`가 URL 문자열을 내는데 에뮬레이터가 그것을 **github 값의 `repo` 필드**에 담는다(`_SOURCE_ARG_FIELDS = {"github": ("repo",), "url": ("url",), "git": ("url", "repo")}`). 복원 직후 로컬 값이 레포 값과 다르므로 `_next_base_sections`의 "로컬과 merged가 같은 값인 키만 전진"에 걸려 그 키는 base에 실리지 않고, 다음 백업이 같은 차이를 다시 보고한다 — **수렴 자체가 깨진다.** (코드를 따라간 귀결이고 끝까지 돌려 본 실측은 없다. 그런 시나리오가 아직 없기 때문이다.)

**`Device.restore`의 소비자는 Task 12가 넷 세워 두었다** — `test_a_blocked_marketplace_stops_the_install_and_config_steps`(9.3.2 blocked의 2·4단계), `test_a_blocked_marketplace_stops_the_disable_step`(같은 9.3.2의 3단계 — `fail_marketplaces`와 재실행 수렴을 함께 쓰는 유일한 자리다), `test_restore_rejects_a_secret_the_plan_did_not_ask_for`(4단계 `config_keys` 가드), `test_restore_rejects_an_unknown_choice_section`(선택지 섹션 이름). 첫·둘째가 `fail_marketplaces`를, 첫·셋째가 `secrets`를, 넷째가 `choices`를(값을 바꾸지 않는 형태로) 쓴다. **`choices`가 실제로 값을 바꾸는 갈래는 아직 아무도 타지 않는다** — `keep_stale`·`keep_local`에 실제 키를 넣고 그 효과를 재는 것은 이 task가 처음이다. 그때까지 그 갈래의 변조는 전부 살아남는 상태이므로, 여기서 도입하는 시나리오가 그 가드를 함께 세운다.

**Task 12 품질 리뷰가 남긴 나머지 지뢰(전부 실측·코드 확인).**
- **한 HOME에 `PluginCLI` 인스턴스를 둘 만들지 말 것.** 생성자가 `settings.json`·`installed_plugins.json`을 초기화하므로 이전 상태가 지워진다(클래스 docstring에 경고가 있다). **두 기기 시나리오는 HOME을 갈라야 한다** — `Device` 하나에 HOME 하나다.
- **`test_base_does_not_advance_when_the_repo_file_cannot_be_written`을 복제할 때 `Device.backup()`으로 바꾸지 말 것.** 그 테스트는 직전 백업이 남긴 스테이징 파일을 마지막 단정에서 읽으려고 `dev._run(COLLECT, ...)`를 직접 부른다. `Device.backup()`은 앞에서 `rmtree`를 돌리므로 그 파일이 사라져 단정이 `FileNotFoundError`로 죽는다(조용하지는 않다).
- **의존성은 `install`의 인자가 아니라 `set_manifest`로 심는다**(N1 — `dependencies`는 `plugin.json`의 배열이다). 그래서 `Device.restore`의 2단계 `install(plugin_id)`로도 자식이 따라온다(9.3.1). 14.2 #4의 H1 시나리오는 이 픽스처를 먼저 부를 것.
- **선택지 섹션 이름 오타는 `AssertionError`로 죽는다**(`Device._apply_base`). `plan_plugins`의 `choice_list`가 모르는 섹션을 무시하므로 그 가드가 없으면 "선택을 하나도 적용하지 않은 restore"가 초록으로 지나간다. 9.3.4의 세 선택지를 섹션별로 쓸 때 이 가드가 먼저 말한다.
- **4단계가 3단계를 되돌린다 — 미확인이고, 어느 쪽이든 이 task가 밟는다.** 한 id가 `disable_after_install`과 `config_keys`에 **함께** 실릴 수 있다(spec 9.3.1이 두 단계 모두 *"설치 여부로 좁히지 않는다"*로 못 박는다). 그때 3단계가 낸 `disable` 뒤에 4단계의 `install --config`가 오므로, 사용자가 그 id의 값을 입력하면 **복원이 끝난 로컬 값이 `true`가 된다** — 레포가 `false`인데도. 실측 확인했다(위 P10의 표 3행). 갈래가 둘이고 **지금은 어느 쪽인지 모른다.**
  - **(ㄱ) 실제 CLI도 `--config`와 함께 값을 `true`로 되돌린다면** — 이것은 하네스가 아니라 **spec 9.3.1의 순서 규정에서 나오는 설계상의 귀결**이다. 3단계가 무효화되므로 레포의 `false`가 그 기기에 영영 복원되지 않고, 다음 백업이 로컬 `true`를 도로 밀어 **수렴이 깨진다.** 순서를 바꾸거나(4단계 뒤에 3단계를 다시 낸다) 4단계를 값 보존형으로 만드는 **spec 결정이 필요하다 — plan ③ 후보로 표시한다.**
  - **(ㄴ) 실제 CLI가 `--config`만 쓰고 `enabledPlugins` 값을 건드리지 않는다면** — 틀린 것은 에뮬레이터의 **3번**(값이 `false`인 항목을 `install`하면 `true`가 된다)이고, `PluginCLI.install`을 고쳐야 한다.
  - 둘 중 무엇인지는 **실제 CLI를 재야 알 수 있다.** 재기 전까지는 어느 쪽도 단정하지 말 것. 그때까지 3단계를 관측하는 시나리오는 **그 id에 `secrets`를 주지 않는 것**으로 우회한다(`test_a_blocked_marketplace_stops_the_disable_step`이 그렇게 한다).
  - **[2026-08-29 갱신 — 닫혔다. 갈래 (ㄱ)이다.]** 실환경 스모크가 `disable`된 id에 `install --config token=…`를 내어 `enabledPlugins`가 `false` → `true`로 바뀌는 것을 실측했다(`docs/superpowers/2026-08-29-plugin-cli-smoke.md` 4장). 에뮬레이터의 3번이 옳았고, 따라서 **spec 9.3.1의 순서를 고쳐야 하는 plan ③ 항목이다.** 우회(secrets를 주지 않는다)는 그대로 유효하다.
- **14.2 #7의 픽스처로는 3단계가 관측되지 않는다(실측).** 레포 `enabledPlugins`가 둘 다 `true`이고 `pluginConfigs`가 비어 `disable_after_install`이 두 회차 모두 `[]`이므로, 원본 트리와 3단계 필터를 지운 트리의 출력이 완전히 같다. 3단계는 Task 12의 자매 시나리오가 이미 잰다(위 P10) — **14.2 #7의 픽스처를 그쪽에 맞추려 하지 말 것.** 두 시나리오는 같은 id에 **반대되는 설치 상태**를 요구한다.
- **`set_directory_marketplace`에는 호출자가 하나도 없다**(Task 12 종료 시점, 스위트 전체 grep 0건 — 실측). 그래서 그 값의 모양(Task 12 7번 — 당시 추정이었고 2026-08-29 스모크가 **가정과 정확히 같음**을 실측했다)을 **지금 어떤 테스트도 고정하지 않고**, 그 자리를 github 모양으로 바꾸는 변조가 **SURVIVED**다(실측). H2 시나리오 `test_local_directory_marketplace_never_reaches_the_repo`가 **첫 소비자**다. url·git 갈래에는 "그 자리를 먼저 고칠 것"이 세 곳에 적혀 있으나 directory 갈래에는 그 안내가 없었다.
- **`test_plugin_cycle.py`는 이미 책임이 둘이다** — (A) 14.3 에뮬레이터 계약(`PluginCLI`만 쓴다, 서브프로세스를 부르지 않는다)과 (B) `Device` 하네스 시나리오. 이 task가 여섯 시나리오를 얹어 (B)가 크게 늘면 (A)를 `test_plugin_cli.py`로 떼는 것을 권한다.

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
    """9.3.4 케이스 4의 "유지" — 레포로 되돌아간 뒤 부활·소멸이 반복되지 않는다.

    복원 뒤 두 backup을 한 회차로 줄여도 아래 단정은 참이다(실측 777 passed).
    전방 카나리아이고, 이 파일의 다른 2회차들과 같은 지위다. 하중을 지는 것은
    `set_repo` 앞의 최초 백업이다 — 그것을 지우면 CAUGHT다(실측).
    """
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

# 아래 두 시나리오가 **문자 그대로 같은** 픽스처를 쓴다. 같은 파일의 BLOCKED_REPO와 같은
# 규율이다 — 한 쌍이 공유하는 리터럴은 상수로 올린다(P3).
DECLINED_REPO = {"enabledPlugins": {"delta@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}


def test_declined_config_silences_status_until_the_repo_value_changes(tmp_path):
    """6.4 — 보류를 고른 뒤 status가 조용해야 하고, 레포 값이 바뀌면 다시 보고해야 한다."""
    dev = make_device(tmp_path, repo_init=DECLINED_REPO)
    dev.restore(choices={"pluginConfigs": {"declined": ["delta@m"]}})
    assert dev.held()["pluginConfigs"]["delta@m"]
    section = dev.status()["sections"]["pluginConfigs"]
    assert section["only_repo"] == [] and section["changed"] == []
    assert section["held"]["declined"] == ["delta@m"]

    changed = json.loads(json.dumps(DECLINED_REPO))
    changed["pluginConfigs"]["delta@m"]["options"]["extra"] = pc.SENTINEL
    set_repo(dev.repo, changed)
    assert dev.status()["sections"]["pluginConfigs"]["only_repo"] == ["delta@m"]


def test_declined_config_keeps_the_repo_entry_across_two_backups(tmp_path):
    """6.4 — 초판의 "base에 레포 값 기록"이 케이스 3으로 착지시켰던 자리다.

    기기 B가 "이 기기에서는 안 쓴다"고 말했을 뿐인데 기기 A가 백업해 둔 설정 키 목록이
    레포에서 사라지면 안 된다.

    **base 단정은 오늘 두 겹으로 참이라 단일 변조로는 잡히지 않는다** — 값 보류 skip과
    next_base의 "로컬이 동의한 키만 전진". 그런데도 거는 이유는 6.4가 지목하는 초판의
    형태(apply-base가 레포 값을 base에 기록)가 그 두 겹을 **함께** 우회하기 때문이다.
    """
    dev = make_device(tmp_path, repo_init=DECLINED_REPO)
    dev.restore(choices={"pluginConfigs": {"declined": ["delta@m"]}})
    assert "delta@m" not in dev.base()["pluginConfigs"]
    dev.backup()
    dev.backup()
    assert repo_doc(dev.repo)["pluginConfigs"]["delta@m"]["options"] == {
        "apiKey": pc.SENTINEL}


def test_partially_entered_config_does_not_drop_the_other_keys(tmp_path):
    """14.1 — 세 키 중 두 개만 입력해도 레포의 세 번째 키가 사라지지 않는다 (6.3).

    **"사라지지 않음"만 재면 두 입력 중 어느 것도 단정을 좌우하지 않는다**(실측 — 초판이
    그랬다: `declined`만 빼도, `secrets`만 빼도 스위트가 통과했다). 보류가 없으면 그
    항목은 `conflicts.repo_kept`로 떨어지는데 **그때도 레포 값은 보존되기** 때문이다.
    두 경로가 갈리는 곳은 다음 실행의 침묵이다 —

      [declined 있음] status: changed == []
      [declined 없음] status: changed == ["p@m"]  ← 영원히 다시 묻는다

    spec 6.3이 부분 입력에 보류를 요구하는 **이유 자체**가 그것이고, 이 plan이 14.2 #5에서
    경고한 형태("사라지지 않음만 보므로 영원히 다시 묻는 실패를 통과시킨다")의
    pluginConfigs 판이다. enabledPlugins와 달리 대신 잡는 형제 시나리오가 없다.
    """
    repo_init = {"enabledPlugins": {"p@m": True},
                 "extraKnownMarketplaces": {"m": GH},
                 "pluginConfigs": {"p@m": {"options": {k: pc.SENTINEL
                                                       for k in ("a", "b", "c")}}}}
    dev = make_device(tmp_path, repo_init=repo_init)
    dev.restore(secrets={"p@m": {"a": "1", "b": "2"}},
                choices={"pluginConfigs": {"declined": ["p@m"]}})
    # 입력한 두 키만 로컬에 들어간다 (N2). secrets를 단정에 싣는 유일한 자리다.
    assert dev.local()["pluginConfigs"]["p@m"]["options"] == {"a": "1", "b": "2"}
    assert dev.held()["pluginConfigs"]["p@m"]                       # 6.3 → 보류로 기록된다
    dev.backup()
    dev.backup()
    assert sorted(repo_doc(dev.repo)["pluginConfigs"]["p@m"]["options"]) == ["a", "b", "c"]
    # **위 줄만으로는 두 경로가 갈리지 않는다.** 갈리는 곳이 여기다.
    assert dev.status()["sections"]["pluginConfigs"]["changed"] == []


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
    dev.cli.set_manifest("p@m", ["z@m"])
    dev.cli.install("p@m")                              # z가 auto로 다시 들어온다
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

# 아래 두 시나리오도 **문자 그대로 같은** 픽스처를 쓴다(P3). 레포 값이 확장 포맷이라는
# 것이 H3의 술어이므로, 이 값이 불리언으로 미끄러지면 둘이 **동시에** 주제를 잃는다.
EXTENDED_REPO = {"enabledPlugins": {"p@m": ["1.0.0"]},
                 "extraKnownMarketplaces": {"m": GH}, "pluginConfigs": {}}


def test_extended_value_escape_hatch_round_trip(tmp_path):
    """7.3 — 탈출구 실행 → backup 2회 → 레포 값이 true → 그 뒤 uninstall이 케이스 3으로 전파.

    #4·#5 어느 것도 이 경로를 덮지 않는다. "지우려면 먼저 불리언화"가 실제로 성립하는지가
    여기서 판정된다.
    """
    dev = make_device(tmp_path, repo_init=EXTENDED_REPO)
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
    # **정리하는 것은 backup이 아니라 apply-base다**(실측 — 초판은 여기서 곧바로 []를
    # 기대했으나 ['p@m']이었다). plugins-held.json의 소유자는 apply-base 하나뿐이고
    # (write_held_state), collect_plugins는 읽기만 한다.
    assert dev.held()["release"]["enabledPlugins"] == ["p@m"]        # backup은 손대지 않는다
    dev.restore()
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
    dev = make_device(tmp_path, repo_init=EXTENDED_REPO)
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

**프로덕션 가드 축.**

- `plan_plugins.apply_base`의 release + `keep_local` 동시 적용을 지우기 → H3 왕복이 잡아야 한다
- `pc.next_held_state`의 release 정리를 지우기 → 왕복의 `release` 단정이 잡아야 한다
- `collect_plugins`의 H2 보류를 마켓플레이스 섹션에만 적용하기 → directory 시나리오가 잡아야 한다
- `Device.restore`의 `blocked` 검사를 지우기 → **CAUGHT다(실측).** 초판은 여기에 *"부분 실패 시나리오가 통과해 버린다 — 에뮬레이터는 실패하지 않으므로"*라고 적었으나 반증됐다: 실패를 흉내낼 수단이 없다는 것과 **잘못된 성공**을 잴 수 없다는 것은 다른 말이고, 등록이 실패했는데도 플러그인이 설치돼 버리는 것이 단정에 걸린다. 그래도 `depends_on`이 비면 잡히는 단정을 함께 걸 것 — 실패 메시지가 증상이 아니라 원인을 가리킨다
- `keyed_sync.next_base`의 "로컬이 동의한 키만 전진"을 지우기 → 부분 실패의 base 단정(10.4)이 잡아야 한다

**입력 축(위 표의 다섯째 축).** 이 축을 돌려야만 드러나는 SURVIVE가 초판에 다섯 있었다. 아래 항목 수와 그 다섯은 대응하지 않는다 — 한 항목이 여럿을 내기도 하고, 초판에서 이미 CAUGHT였던 변조도 항목 안에 섞여 있다.

- **선택 인자를 하나씩 뺀다** — 각 시나리오의 `choices`(`keep_stale`·`release`·`declined`)와 `secrets`. **각각이 자기 시나리오 하나를 죽여야 한다.** 죽지 않으면 그 시나리오는 사용자의 선택이 결과를 가른다는 것을 재지 않는 것이다
- **픽스처 값을 미끄러뜨린다** — 레포의 확장 포맷 값을 불리언으로, `pluginConfigs`의 options를 비움 → 그 픽스처를 쓰는 시나리오 중 **그 값이 술어인** 쪽이 잡아야 한다. **"전부"가 아니다** — Task 13에서 반증됐다(실측): 확장 포맷 값은 두 소비자가 **둘 다** 잡지만, options를 비우는 변조는 **하나만** 잡고 **그 통과가 정당하다**(다른 쪽의 주제는 "보류 후 침묵 → 레포 값이 바뀌면 재보고"라 옵션이 비어도 성립한다). 잡지 않는 시나리오가 있으면 그 값이 그 시나리오의 **술어가 아니라는 뜻**이므로, 그 사실이 맞는지 한 번 묻고 넘어간다
- **회차를 줄인다** — backup 2회를 1회로. 여기서 SURVIVE는 정당할 수 있다(전방 카나리아). **단 그 사실을 docstring에 적을 것** — 적지 않으면 다음 사람이 그것을 관측되는 회차로 읽는다
- **에뮬레이터가 만드는 상태를 지운다** — `install`이 매니페스트의 의존성 자식을 `enabledPlugins`에 넣지 않게 → auto 왕복 시나리오와 **계약 파일**이 함께 잡아야 한다(N1의 실측 행)
- **에뮬레이터 명령의 규약을 뒤집는다** — `marketplace add`를 비멱등으로, exit code를 1로, 값의 모양을 github→url로, `enable`/`disable`이 값 대신 키를 지우게 → **계약 파일이** 잡아야 한다(spec 14.3 표의 여섯 행이 전부 계약 파일에 있어야 하고, **한 행의 요구가 둘이면 둘 다** 잡아야 한다 — 3행은 exit code 규약과 "키를 유지한 채 값만 바꾼다" 둘이다). **계약 파일이 잡지 못하고 시나리오만 잡으면** 계약이 잘못된 파일에 있는 것이다. 단 **둘 다 잡는 것은 정상이다** — 시나리오가 공유 상수를 통해 같은 사실에 걸리는 경우이고, 그것을 결함으로 읽지 말 것

- [ ] **Step 5: Commit**

```bash
git add plugins/claude-sync/tests/test_plugin_cycle.py
git commit -m "test: 선택지 실행 후의 교대 시나리오 여섯"
```

---

### Task 14: 세 스킬 배선 — **사용자 가치가 여기서 처음 나온다**

**근거:** spec 7.4, 9.1·9.2·9.3, 12장, 부록 A / 13장 표의 9·10행

> **[2026-08-31 갱신 — spec 4차 개정 ①②③]** `sync-restore/SKILL.md`의 5절 배선이
> 바뀐다. **이 라운드는 SKILL.md를 고치지 않는다** — 규정만 갱신한다(spec 12.1).
>
> 1. **실행 순서가 `5-1 → 5-2 → 5-4 → 5-3`이다.** 절 번호는 그대로 두고 **실행만**
>    바꾼다(spec 9.3.1이 번호를 유지한 것과 같은 이유 — `depends_on`이 "2단계 ∪ 4단계"로
>    번호를 참조한다). 이유: `install --config`(5-4)도 `enabledPlugins` 값을 쓰므로
>    **5-3을 되돌린다**(실측, 스모크 4장). 값 보존형 5-4는 **CLI에 `configure`
>    서브커맨드가 없어** 존재하지 않는 선택지다(스모크 10장).
> 2. **5-3 직전에 로컬 `settings.json`을 다시 읽는다.** `disable_after_install`은
>    **계획 시점의 후보 목록**이고, "현재 상태와 다를 때만"의 *현재* 는 **실행 시점**이다.
> 3. **레포 문서의 구문이 깨졌으면 계획이 `status: "skipped"`로 온다**(9.3.6). 아래
>    5절 머리의 skipped 분기가 그대로 처리하지만, **`local_stale` 제안이 나오지 않는
>    것이 요점이다** — 지금은 최상위 `ok`와 함께 "전부 지웁시다"가 나간다.

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
# 두 수집 단계의 실행줄은 **상수로 묶는다.** 아래 스테이징 순서 가드가 이 표의
# **인덱스**를 딛으면, 표에서 항목 하나가 빠지거나 순서가 바뀌는 것만으로 그 가드가
# 엉뚱한 줄을 보고 그러고도 초록이 된다.
COLLECT_PLUGINS_CALL = 'python3 "$SYNC_SCRIPTS/collect_plugins.py" "$SYNC_REPO" "$BASE_STAGING"'
COLLECT_MCP_CALL = 'python3 "$SYNC_SCRIPTS/collect_mcp.py" "$SYNC_REPO" "$BASE_STAGING"'

COMPAT_WIRING = {
    "sync-backup": {
        "section": "2.5 호환성 검사",
        "after_section": "### 2. 레포 준비",
        "before_section": "### 3. Git User 설정",
        "before_calls": (
            'python3 $SYNC_SCRIPTS/reconcile_backup.py "$SYNC_REPO"',
            # extract_plugins.py를 지우면서 **앵커를 지우지 않는다** — 이 항목은
            # "호환성 검사가 이 실행줄보다 앞에 있어야 한다"를 거는 자리다.
            COLLECT_PLUGINS_CALL,
            'python3 "$SYNC_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"',
            COLLECT_MCP_CALL,
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
    "sync-backup": COLLECT_PLUGINS_CALL,
    "sync-restore": 'python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json"',
}
```

**아래 목록은 최소치다.** Task 14 실행의 두 리뷰가 실측으로 여섯을 더 요구했고 전부
받아들여졌다 — restore 쪽 base 게이트의 두 relpath, 그 게이트에 **도달하는지**(절이
skip 가능한 단계 안에 있으면 안 된다), backup 10단계 게이트의 `REPO_HAS_CONTENT` 축,
스킬이 스크립트의 **어느 키를 읽는지** 적은 산문 앵커 넷, status의 용어집이 두 벌이
되지 않는지, 그리고 이 표들이 스스로 줄어드는 것을 막는 완전성 메타가드 셋.
**Step 4b에서 SURVIVE가 나오면 여기에 더한다** — 이 목록은 그 출발점이다.

파일 끝에 가드를 더한다.

```python
STAGING_CLEAR = 'rm -rf "$BASE_STAGING"'


def test_backup_clears_the_shared_staging_once_before_both_collectors():
    """7.4 — 각 단계가 제 앞에서 rm -rf하면 앞 단계의 산출물이 지워진다."""
    text = read_skill("sync-backup")
    assert text.count(STAGING_CLEAR) == 1
    clear = index_of(text, STAGING_CLEAR, "sync-backup")
    for call in (COLLECT_PLUGINS_CALL, COLLECT_MCP_CALL):
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


# spec 12장이 **보존을 지시한** 자기 업데이트 두 줄이 같은 절의 bash 블록에 있고
# --scope user를 갖지 않는다. 그래서 "claude plugin으로 시작하는 모든 줄"을 훑는 형태는
# **성립 불가**다(Task 14 실행에서 실측). 그 둘만 **명령 전문**으로 제외한다 —
# 동사(`update `)로 제외하면 5-2의 install을 `claude plugin update <id>`로 바꾼 줄까지
# 함께 빠져나가고(실측), 허용 목록(설치·활성화 동사)으로 적으면 목록에서 동사 하나를
# 빼는 것만으로 그 명령이 검사를 조용히 빠져나간다.
RESTORE_SELF_UPDATE_COMMANDS = (
    "claude plugin marketplace update claude-sync",
    "claude plugin update claude-sync",
)


def test_restore_plugin_commands_carry_scope_user_and_never_dash_y():
    """14.1 — --scope user가 없으면 복원된 플러그인이 settings.json에 나타나지 않아
    backup이 못 보고 status가 only_repo를 영구 보고한다(I6). -y는 D2 위반이다."""
    prefix = "claude plugin "
    commands = [line.strip() for block in bash_blocks(plugin_restore_section())
                for line in block.splitlines()
                if line.strip().startswith(prefix)
                and line.strip() not in RESTORE_SELF_UPDATE_COMMANDS]
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
- `absent_locally` — 보류 키 중 **로컬 섹션 문서에 값이 없는** 것. 여기 있는 항목에 "레포 값을 보존합니다"만 말하면 거짓이다(보존할 로컬 값이 없다). **이 목록 자체는 "미설치"가 아니다** — auto 의존성은 `installed_plugins.json`에 있으므로 **설치되어 있으면서** `settings.json`에는 값이 없고, `enabledPlugins`의 키 부재는 매니페스트 기본값 위임이지 미설치가 아니다
- `not_installed` — **9.2의 "설치됨/미설치"를 이 필드로 말한다**(이 task에서 정한 결론). `compare_plugins.py`가 이미 싣고 있다 — `absent_locally`의 부분집합이며 `enabledPlugins`·`pluginConfigs` 두 섹션에만 실린다(마켓플레이스 이름은 설치 집합과 이름 공간이 다르다). *"compare는 설치 여부를 알 수 없다"* 는 앞 판의 서술은 **거짓이었다** — 그 스크립트는 `installed_ids`를 읽는다

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

#### 5-3. 값 맞추기 — **마지막에 실행한다** (5-4 뒤)

> **[2026-08-31 갱신 — spec 9.3.1]** 아래 *"설치 직후 값은 `true`"* 는 두 군데가 틀렸다.
> ㉠ `install`은 **매니페스트의 `defaultEnabled`** 를 쓴다(기본 `true`이므로 대다수는
> 같지만 `false`인 플러그인에서는 `false`다 — 스모크 7장). ㉡ 5-4의 `install --config`가
> **같은 값을 다시 쓰므로 이 절이 5-4보다 먼저 돌면 되돌려진다**(스모크 4장 — 수렴이
> 깨진다). → **실행 순서를 `5-4 → 5-3`으로 바꾸고, 이 절 직전에 로컬 `settings.json`을
> 다시 읽어 그 값으로 판정한다.** `disable_after_install`은 계획 시점의 **후보 목록**이다.
> 재읽기 뒤에도 로컬 키가 없어 추정이 남는 id에서 나오는 exit 1은
> **"이미 그 상태"** 이므로 실패로 렌더링하지 않는다(spec 10.2).

`disable_after_install`의 항목만 끈다. 설치 직후 값은 `true`이므로 그 외에는 부를 것이 없다 — **`enable`/`disable`은 멱등이 아니라** 현재 상태와 같으면 exit 1로 거짓 실패를 낸다.

```bash
claude plugin disable <id> --scope user
```

#### 5-4. 설정 채우기 — **5-3보다 먼저 실행한다**

`config_keys`에 실린 키를 사용자에게 묻는다. **레포에는 마스킹된 값만 있으므로 그대로 등록하면 동작하지 않는 항목이 설치된다.**

> **[2026-08-31 갱신 — spec 9.3.1]** 이 명령은 `pluginConfigs`만 쓰는 것이 아니라
> **`enabledPlugins` 값도 함께 쓴다**(실측: `false` → `true`, 스모크 4장). 그래서
> **5-3보다 먼저** 돈다 — 뒤에 돌면 5-3이 맞춰 놓은 값을 되돌린다.

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

> **[2026-08-31 갱신 — spec 1.2 · 13장]** 실측이 이 문구에 한 줄을 더하게 만들었다.
> **CLI는 비불리언 값을 「꺼짐」으로 읽는다**(스모크 3장 — `disable`이 배열·객체 값에
> `already disabled`로 exit 1을 낸다). 즉 레포의 확장 값을 그대로 받은 기기에서 그
> 플러그인은 **꺼진 상태**이지 "버전을 고정한 켜짐"이 아니다. 위 문구만 읽으면 사용자는
> 그 플러그인이 켜져 있다고 믿는다 — **탈출구를 고를 이유가 바로 여기 있는데** 그것이
> 문구에 없다. 같은 실측이 `value_command`가 비불리언 레포 값에 언제나 `None`을
> 돌려주는 것을 **옳다고 뒷받침한다**(명령을 내면 값이 사라진다).

**로컬에 값이 없는 보류 항목은 이 버킷에 오지 않는다.** `restore_plan`이 값 보류 키를 `value_held`에 넣는 조건이 `name in local`이라, 로컬에 값이 없는 보류 키는 `add`/`needs_secret`(복원 불가면 `unrestorable`)으로 빠진다 — 그쪽 항목에 "레포의 값을 보존합니다"라고 말하면 **보존할 로컬 값이 없어 거짓**이다. **`absent_locally`를 여기서 가리키면 안 된다** — 그것은 `compare_plugins.py`(status)만 내는 필드이고 계획 JSON에는 없다(앞 판의 결함. 결론은 맞고 근거가 틀렸던 (b) 양식이다).

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

**(g) `sync-restore/SKILL.md` 6-6과 새 6.5절.** MCP의 base 갱신 블록에서 `rm -rf`를 지우고(5절로 옮겼다) `BASE_STAGING`을 쓴다. 6-6에는 **MCP의 `apply-base`까지만** 남긴다.

```bash
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"
python3 "$SYNC_SCRIPTS/plan_mcp.py" apply-base "$SYNC_REPO/mcp-servers.json" "$BASE_STAGING" /tmp/claude-sync-mcp-choices.json
rm -f /tmp/claude-sync-mcp-choices.json
```

**스테이징 → `base/` 이동은 `### 6` 밖으로 꺼내 독립 절로 올린다**(예: `### 6.5 base 갱신 (스테이징 → base)`, 6절과 7절 사이). **`#### 6-6` 안에 두면 안 된다** — 6절 머리가 *"`status`가 `"skipped"`면 MCP 단계 전체를 건너뛴다"*고 지시하므로, `plan_mcp.py plan`이 skipped인 실행(레포의 `mcp-servers.json`이 상위 버전 형식일 때가 1급 경로다)에서 그 절이 통째로 돌지 않고, **5절이 이미 계산해 스테이징에 써 둔 플러그인 base가 영영 옮겨지지 않는다.** 옮기는 경로가 이것 하나뿐이라 `keep_stale`·`keep_local`·`release` 선택이 조용히 무효가 되고 H3 탈출구가 완전히 죽는다 — 9.3.7이 막으려던 바로 그 상태다. 5절 5-7의 인계 문장도 그 새 절을 가리키게 적는다.

```bash
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging"

RELS=()
for rel in plugins.json mcp-servers.json; do
  [ -f "$BASE_STAGING/$rel" ] && RELS+=("$rel")
done
if [ ${#RELS[@]} -gt 0 ]; then
  python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"
  echo "base 갱신됨: ${RELS[*]}"
fi
```

**루프의 모양만 잠그면 부족하다** — 그 루프에 **도달하는지**를 재는 단정을 함께 건다. 도달성은 축이 **둘**이다: ⑴ 어느 단계에도 속하지 않는가(5절·6절이 각각 "단계 전체를 건너뛴다"고 적은 절 안에 루프가 없어야 한다) ⑵ **두 생산자보다 뒤인가**(두 `apply-base`가 스테이징에 쓰기 전에 옮기기가 끝나면 그 파일의 base가 전진하지 않는다 — ⑴만 걸면 절을 6-6보다 앞에 두는 배치가 무가드로 남는다). 앞쪽 `rm -rf`에 이미 같은 꼴의 짝이 있다.

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
- `update_base.py "$BASE_STAGING"`을 `"$SYNC_REPO"`로 바꾸기 → **잡힌다(실측으로 앞 판의 예측이 반증됐다).** backup 쪽은 `test_backup_base_gate_covers_both_relpaths`의 `'"$BASE_STAGING" "${RELS[@]}"' in block`이, restore 쪽은 `before_calls` 앵커의 `index_of`가 부재를 실패로 만든다. 하네스 모형의 같은 오사용(`Device.backup`의 source_root)도 기존 시나리오 둘이 잡는다 — **따라서 `test_plugin_cycle.py`에 단정을 더하지 않는다.** 이 plan에서 "어떤 테스트도 잡지 못한다"류의 예측이 실측에 반증된 **일곱 번째**다
- **restore 6-6의 두 relpath 루프도 함께 뒤집을 것** — backup 판만 지목했던 앞 판에서 그쪽이 무가드로 남았다(실측 SURVIVED). 그렇게 되면 restore 경로의 `base/plugins.json`이 전진하지 않아 `keep_stale`·`keep_local`·`release` 선택이 조용히 무효가 된다(9.3.7)
- 10단계 게이트에서 `[ "$REPO_HAS_CONTENT" = "1" ]` 축을 빼기 → 파일 존재 축만으로는 **푸시 실패 실행의 base 전진**을 막지 못한다. 두 축을 다 걸 것
- 5절의 자기 업데이트 bash 블록을 통째로 지우기 → 절 전체에서 문자열을 찾는 가드는 **같은 문구를 쓴 산문**으로 충족된다. `bash_blocks(...)` 안에서 찾을 것
- restore 5-2의 `--scope user`를 지우기 / `-y`를 붙이기 → 명령 가드가 잡아야 한다
- 5-5의 `marketplace remove`를 bash 블록 안으로 옮기기 → 실행 금지 가드가 잡아야 한다
- `check_status.py`의 플러그인 블록을 되살리기 → status 가드가 잡아야 한다
- 4.5단계를 다시 5.5로 되돌리기 → 탐지 순서 가드가 잡아야 한다
- **입력 축.** 이 task에는 에뮬레이터 픽스처가 없지만 축은 적용된다 — 위에서 단정을 더하기로 했다면, 그 단정이 딛고 선 **테스트 쪽 입력**(`COMPAT_WIRING`의 앵커, `test_plugin_cycle.py`의 픽스처)을 하나씩 빼고 그 단정이 죽는지 확인한다. 죽지 않으면 그 단정은 자기 이름이 약속한 것을 재지 않는다

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
- Create: `plugins/claude-sync/tests/test_user_docs.py` — **실행 시 추가됨.** 아래 Step 1의 초안은
  사용자 문서 가드를 `test_script_root.py` 끝에 두라고 적었으나, 그 파일은 스스로
  *"관심사를 둘 담는다"*(0단계 bash 실행 / 세 SKILL.md 계약)라고 적고 있고 `README.md`는
  스킬도 스크립트도 아니다. 셋째 관심사를 얹으면 Task 14 품질 리뷰의 I4(간판이 내용을
  설명하지 못한다)가 그대로 재발하므로 갈랐다. SKILL.md의 서술 정정 가드는 둘째 관심사에
  속하므로 `test_script_root.py`에 남겼다

**규정 결함 — 13장 표가 놓친 자리 하나(실행 중 발견).** `backup-readme.md:35` /
`backup-readme.ko.md:35`가 `sync-metadata.json`을 이렇게 설명하고 있었다.

> - `sync-metadata.json` — Per-file modification timestamps (for conflict detection)
> - `sync-metadata.json` — 파일별 수정 시각 (충돌 감지용)

**둘 다 거짓이다.** `generate_metadata.py:1`이 *"백업 시점의 파일별 내용 해시(sha256)와
버전 표식을 기록한다. **mtime 미사용.**"* 이라고 적고, `README.md:87`·`README.ko.md:87`도
*"수정 시각(mtime)은 일절 사용하지 않습니다"* 라며 같은 저장소 안에서 정면으로 부정한다.
13장 표에 없어 **어느 task에도 배정되지 않았는데**, 그 줄은 이 task가 고친 `:34` 바로
아래 같은 불릿 목록 안에 있다. `backup-readme*.md`는 **사용자의 백업 레포에 그대로
복사되는 파일**이라 레포를 클론한 사람이 처음 읽는 문서가 동작 모델을 틀리게 말한다.
이 task에서 함께 고치고 `CORRECTIONS`에 쌍으로 넣었다(quality review I3).

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

**위 코드는 초안이고 실행에서 다음을 고쳤다.**

- `STALE_CLAIMS`의 `not in` 형태는 **바늘이 틀려도 초록이다.** 옛 문구를 혼자 걸지 않고
  **(옛 문구, 정정 문안) 쌍**으로 바꿔 positive 절반을 함께 걸었다(`CORRECTIONS`).
- `assert "key by key" in text`는 **공허하다** — 같은 문서의 `mcp-servers.json` 문단이
  이미 그 문구를 갖고 있어 플러그인 쪽 문장이 통째로 없어도 통과한다. `plugins.json`을
  **같은 줄에서** 지목하도록 좁혔다.
- 세 토큰 존재 단정은 어댑터에서 뽑는다 — `pc.SECTIONS`·`pc.MARKETPLACE_ALIASES`·
  `pc.DEFAULT_INSTALLED`. 손으로 적은 상수는 값만 바꾸면 통째로 공허해진다.
- 새 한계의 항목 수는 **spec 13장 "새로 적어야 할 한계"의 불릿 수에서 뽑는다.** 문서마다
  손으로 센 숫자를 두면 한 항목이 빠져도 아무도 알아채지 못한다.
- `USER_DOCS`는 디스크 목록과 대조한다(다섯째 축).

- [ ] **Step 2: test를 실행하여 실패를 확인**

실행: `uv run --with pytest pytest plugins/claude-sync/tests/test_user_docs.py plugins/claude-sync/tests/test_script_root.py -q`
기대: 문서 가드 FAIL (실측 23건)

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

**이 grep은 정정 대상이 아닌 문장 둘과 충돌한다(실측).** `README.ko.md:93`과
`sync-backup/SKILL.md:40`은 MCP에 대해 *"파일 통째로 덮어쓰지 않고"* 라고 **참을** 말하는데
부분 문자열이 같아 함께 걸린다. 대비 문구였으므로(`plugins.json`이 예외라는 전제)
`plugins.json`도 키 단위 병합이 된 지금은 필요 없다 — 뜻을 유지한 채 그 표현을 지웠다
(`서버마다 따로 판정되므로` / `**서버 이름 키 단위 3-way 병합** 대상이다`).

- [ ] **Step 4b: 변조 확인 (필수)**

- `CORRECTIONS`에서 쌍을 하나씩 지우기 → 그 문구를 되살렸을 때 가드가 통과해 버리는지 확인한다(목록이 실제로 전수인지 검증)
- 정정한 문장 하나를 옛 문장으로 되돌리기 → 대응 가드가 FAIL해야 한다
- **영어 README만 되돌리기** → 파라미터화된 가드가 그 파일에서 FAIL해야 한다. 한국어판만 보는 가드였다면 여기서 드러난다

**하네스를 먼저 고쳐야 한다(실측).** `mutate.py`는 `plugins/`만 임시 복사본에 옮기므로
레포 루트의 `README.md`·`README.ko.md`와 `docs/`를 읽는 테스트가 있으면 **대조군부터
깨지고** 그 파일을 대상으로 한 변조는 아예 적용되지 않는다. `.git`·캐시를 제외하고
레포 전체를 복사하도록 고쳤다(저장소 밖 파일이라 이 plan의 커밋에는 들어가지 않는다).

**1라운드 — 19종 중 18 CAUGHT, 1 SURVIVED. 대조군 CONTROL_OK(844 passed).**
다섯째 축(테스트가 준 목록을 뺀다)을 다섯 자리에 돌렸다 — `CORRECTIONS`의 쌍 하나,
`CORRECTIONS`의 문서 하나, `USER_DOCS`의 문서 하나, `LIMITS_ANCHOR`의 문서 하나,
spec 불릿 추출기가 빈 목록을 내는 경우. 전부 CAUGHT다.

**2라운드(spec 준수 review 뒤) — 14종 중 13 CAUGHT, 1 SURVIVED. CONTROL_OK(845 passed).**
review가 **1라운드가 놓친 SURVIVE 둘**을 찾았고 둘 다 닫았다.

- `pc.SENTINEL in sec`가 **공허했다.** 같은 절의 MCP 문단이 `<REDACTED>`를 이미 갖고 있어
  플러그인 쪽이 `<MASKED>`로 거짓이 돼도 초록이었다(실측). **같은 줄 지목**으로 좁혔다 —
  `key by key`에 적용한 것과 같은 처방인데 여기에만 적용하지 않았던 것이다.
- `"두 필드만" not in sec`에 **positive 대응이 없었다.** *"세 필드를 추출"* → *"두 필드를
  추출"* 이 SURVIVED였다 — 조사 하나로 13장 7행이 지운 거짓이 되살아난다. 수사를
  `len(pc.SECTIONS)`에서 뽑아 짝지었다(`KOREAN_COUNT`). 겸사겸사 `:33` 표 행도 걸었다.

**"바늘의 값을 잠글 원천이 없다"는 1라운드의 결론은 과장이었다.** 열한 바늘 중 **열이**
`plans/2026-08-20-mcp-integration.md`(커밋 하나뿐인 완결 문서)와 spec 13장에 축자로 남아
있다. 그 둘을 `NEEDLE_SOURCES`로 삼아
`test_every_stale_needle_is_quoted_by_a_source_document`가 대응을 건다 — 바늘을 무의미한
값으로 바꾸면 CAUGHT다(1라운드에 SURVIVED였던 그 변조를 축자로 재현해 확인했다).
두 원천은 **둘 다 실어야 한다**: 넷은 plan 쪽에만, 셋은 spec 쪽에만 있어 하나를 빼면
대조가 깨진다(실측 — 둘 다 CAUGHT).

**3라운드(quality review 뒤) — "닫을 수 없다"가 또 과장이었다. 다섯 번째다.**
2라운드가 *"`민감 정보 미포함`은 어느 원천에도 없다"* 고 적었는데 **거짓이었다** —
이 plan 본문의 Task 15 Step 1 초안(`STALE_CLAIMS`)이 그 문구를 축자로 담고 있다.
원천을 셋으로 늘려(`plans/2026-08-25-plugins-sync-body.md` 추가) 바늘 **열셋 전부**를
묶었고 `UNSOURCED_NEEDLES`는 빈 집합이 됐다 — 손으로 고른 목록이 하나 줄었다.
그 자리에서 예외를 인정하기 전에 **저장소 안 원천을 전수로 훑는 습관**이 아직
붙지 않았다는 것이 이 라운드의 교훈이다.

세 원천 중 이 plan 본문만 **여전히 편집된다**(나머지 둘 중 하나는 커밋 하나뿐인 완결
문서, 하나는 plan ③이 고칠 spec이다). 다만 인용을 담은 Step 1 초안 블록과 위 규정 결함
기록은 이제 이력이라 바뀌지 않는다.

**새 한계 일곱은 개수만 잠겨 있었다(quality review I1).** 실측으로, 한 불릿을 다른
불릿의 **복제**로 바꾸거나 *"평문으로 동기화되므로 복원 시 다시 입력할 필요가 없다"* 는
**보안 서술의 정반대**로 바꿔도 스위트 전체가 통과했다 — 정정 여덟 곳에는 `CORRECTIONS`가
그 명제를 잠갔는데 새로 쓴 일곱 곳에는 같은 처방이 없었다. 같은 언어의 두 문서를
**목록째 비교**하고(`test_the_two_language_pairs_carry_the_same_limits`), 한↔영은
**백틱 토큰 서명**으로 비교한다. 후자는 서명이 비면 공허해지므로 코드가 이름을 소유한
둘(`autoUpdate`·`plugins-held.json`)을 함께 요구한다.

**디스크 대조 선택자가 루트의 모든 `.md`를 징집하고 있었다(I2).** `CHANGELOG.md` 하나가
생기면 "새 한계 일곱을 적어야 하는 사용자 문서"로 규정돼, 다음 사람이 그것을 풀려고
`USER_DOCS`에 아무거나 넣는다 — 그 가드가 막으려던 바로 그 결함이다. `README` 계열로
좁혔고 실패 메시지에 고쳐야 할 세 자리를 적었다. 다섯째 축은 유지된다(실측).

**3라운드 변조 — 14종 전부 CAUGHT, SURVIVED 0. 대조군 CONTROL_OK(849 passed).**
review가 SURVIVED로 신고한 셋(Q1·Q2·Q5)을 축자로 재현해 전부 뒤집혔다. 다섯째 축을
여섯 자리에 돌렸다(`NEEDLE_SOURCES` 셋 각각, `USER_DOCS`, 디스크 선택자, `limit_tokens`의
정규식) — 전부 CAUGHT.

**대조군이 실제로 일했다.** 3라운드 첫 실행이 `CONTROL_BROKEN`으로 멈췄는데, M3 검증
중에 돌린 `git checkout README.md`가 **아직 커밋하지 않은 편집을 되돌린 것**이었다.
로컬 스위트는 그 편집 **전에** 마지막으로 돌아 초록이었으므로, 대조군이 없었으면
그 상태로 커밋됐다.

**남은 구멍 하나(신고).** 같은 언어의 **두 문서를 똑같이** 고치는 산문 편집은 지금
잡히지 않는다 — 짝 비교는 두 문서가 같아지므로 통과하고, 한↔영 토큰 서명은 백틱이 없는
문장을 보지 못한다(영어 둘·한국어 둘·네 문서 전부 SURVIVED — 실측).

**단 "잡을 방법이 없다"는 아니다.** 한국어 절반은 **spec 13장의 한국어 불릿 일곱**이라는
저장소 안 원천에 같은 순번으로 묶으면 닫힌다 — 같은 순번 불릿의 최장 공통 구간이 clean에서
최소 9자, 보안 뒤집기에서 7자, 복제에서 2자로 갈린다(리뷰가 약 40줄 프로토타입으로
clean 통과 / KO·EN·네 문서 변조 전부 CAUGHT를 실측했다). 한국어 쪽은 **손으로 고른 진실이
하나도 늘지 않는다** — 값이 전부 spec에서 나오고, 이 파일이 `NEEDLE_SOURCES`로 이미 쓰는
idiom이다. 영어 절반은 저장소 안에 원천이 없어 `CORRECTIONS`와 같은 개수-잠금 핀 문구가
따로 필요하다. **닫는 것은 plan ③의 몫이고, 시도할 값이 있다** — 이 구멍의 대표 사례가
*"플러그인 설정 값이 평문으로 동기화된다"* 는 **보안 서술의 정반대**이고 그것이 사용자의
백업 레포로 복사되는 파일에 들어간다.

**이 문단 자체가 교훈이다.** 초판은 *"산문을 언어를 가로질러 비교할 방법이 없다"* 로 끝났고,
그것이 이 plan에서 **여섯 번째** *"닫을 수 없다"* 과장이었다 — 바로 위 문단이 *"예외를
인정하기 전에 원천을 전수로 훑는다"* 를 교훈으로 적은 **같은 커밋**에서.

- [ ] **Step 5: Commit**

```bash
git add README.md README.ko.md plugins/claude-sync/skills plugins/claude-sync/tests/test_script_root.py plugins/claude-sync/tests/test_user_docs.py
git commit -m "docs: plugins.json이 키 단위로 병합된다는 사실을 여덟 곳에 반영한다"
```

---

## 완료 정의

- [ ] `uv run --with pytest pytest plugins/claude-sync/tests -q` → **0 failed.** 개수는 게이트가 아니다 — 리뷰 후속 커밋이 테스트를 더한다
- [ ] **`PLAN_SHA`를 정한다** — 이 plan 문서를 커밋한 지점의 sha다. `git log --oneline -1 -- docs/superpowers/plans/2026-08-25-plugins-sync-body.md`로 확인한다. `main..HEAD`를 쓰면 안 된다 — 이 테스트 파일들이 `main`에 없어 전부 신규 추가로 잡힌다
- [ ] `git diff --stat $PLAN_SHA..HEAD -- plugins/claude-sync/tests/test_mcp_cycle.py` → **출력 없음.** MCP 교대 시나리오는 이 plan이 건드리지 않는다
- [ ] `git diff --stat $PLAN_SHA..HEAD -- plugins/claude-sync/tests/test_mcp_config.py` → Task 1의 원자성 테스트 **하나만** 추가돼 있다. 그 외 변경이 있으면 어댑터 계약이 바뀐 것이다
- [ ] `grep -rn "extract_plugins" plugins/claude-sync/skills/` → **출력 없음**
- [ ] `grep -rn "MCP_STAGING" plugins/claude-sync/skills/` → **출력 없음** (`BASE_STAGING`으로 통일됐다)
- [ ] 위 둘의 범위가 `skills/`인 것은 실수가 아니다 — `tests/`에는 **부재를 거는 가드**(`test_extract_plugins_is_gone_everywhere`, `'[ -f "$MCP_STAGING/mcp-servers.json" ]' not in ...`)가 그 이름을 적어야 하므로, 저장소 전체를 범위로 삼으면 Task 14 Step 1이 지시한 테스트와 **논리적으로 양립 불가**다
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
| ~~실환경 스모크 — 확장 포맷의 의도된 형태, 객체 평탄화의 성격, `install`의 기본 스코프~~ **측정 완료**(2026-08-29, `docs/superpowers/2026-08-29-plugin-cli-smoke.md`) | spec 14.5 |
| **spec 4차 개정 ①~⑤를 코드에 반영** — 구문 깨짐의 restore 전체 skip(`plan_plugins.py`·**`plan_mcp.py`**), 복원 실행 순서 `1 → 2 → 4 → 3`과 3단계의 실행 시점 재읽기(`sync-restore/SKILL.md`), 에뮬레이터의 `install`에 `defaultEnabled` 규칙 | spec **12.1** (그 표가 파일별 목록이다) |
| **`url`·`git` 마켓플레이스 출처의 왕복** — github은 닫혔고(스모크 9장) 이 둘은 **여전히 미측정**이다. https github URL이 github으로 정규화되므로 raw `.json` URL이나 비-github 호스트 픽스처가 필요하다. 에뮬레이터의 `marketplace_add`가 **언제나 github 모양**을 쓰는 것도 함께 고쳐야 한다 | spec 8.6 · 14.5 #1·#2 / 감사 ② 권고 1·2 |
| **`marketplace remove`의 소속 판정 규칙**(`endswith` false-positive)과 **설치된 플러그인의 `defaultEnabled`를 되읽는 파일** | spec 14.5 #3·#4 |
| **backup 방향의 `{}` degrade를 그대로 둘 것인가** — 유지가 사용자 결정이지만, 그 근거(*"다음 백업이 되돌린다"*)는 **base가 없을 때만 참이다**(실측). base가 있으면 레포의 모든 키가 케이스 4로 떨어져 레포 문서가 `{}`가 되고 `status`는 `"ok"`다 | spec 15장 오픈이슈 6 |
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
