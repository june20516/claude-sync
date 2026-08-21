# claude-sync: 버전 호환성 대처

- 작성일: 2026-08-21
- 상태: 설계 확정 (구현 계획 대기)
- 대상 레포: `june20516/claude-sync` (플러그인)
- 릴리즈: **3.0.0** — 버전을 올리지 않는다. PR target은 `release/3.0.0`
- 선행 설계: `2026-08-20-mcp-config-source-design.md` (같은 릴리즈의 작업 1)
- 근거 문서: `2026-08-21-version-compat-BRIEF.md` (조사·결정), `2026-08-21-release-3.0.0-PLAN.md`

## 1. 배경 & 문제

3.0.0은 역호환이 없다. `mcp-servers.json`이 v1 배열에서 v2 객체로 바뀌었고, v2.0.0 기기가
v3 백업을 만나면 `/sync-status`는 `TypeError`로 죽고 `/sync-backup`은 **레포 파일을 v1 배열로
덮어쓰면서 명령에 공백이 든 서버를 누락시킨다.**

작업 1에서 "모르면 안 쓴다" 가드(`UnknownBackupSchema`)를 넣었으므로 **3.0.0 이후 버전에서는
이 파괴가 구조적으로 불가능하다.** 그러나 이미 배포된 2.0.0에는 소급 적용할 수 없다.
안내·차단·복구는 전부 *낮은 버전 기기에서* 실행되어야 하는데 그 코드를 우리가 못 바꾼다.

**그래서 이 작업의 목표는 2.0.0을 구하는 것이 아니라, 3.0.0 이후 버전들이 서로를 알아보고
스스로 멈추게 만드는 것이다.** 다음 major 전환에서 사용자가 영문 모를 파괴를 겪지 않게 한다.

지금 3.0.0이 알 수 있는 것은 *모른다는 사실*뿐이다. *상대가 몇 버전인지*는 모른다.
남은 것은 **표식**과 **능동적 판정**이다.

### 1.1 `autoUpdate`는 이 문제를 해결하지 못한다

브리프 2.1의 실측 결론이다. 자세한 것은 그 문서를 볼 것. 요약:

`extraKnownMarketplaces.<name>.autoUpdate: true`는 **마켓플레이스와 설치된 플러그인을 모두**
세션 시작 시 갱신한다(실측: 사용자 조작 없이 `figma` 2.2.95 → 2.2.96). 그런데도 불일치 창은
닫히지 않는다.

| 이유 | 근거 |
|---|---|
| 서드파티 마켓플레이스의 **기본값은 꺼짐** | 기본 켜짐은 Anthropic 예약 이름 집합뿐. `june20516/claude-sync`는 없다 |
| 켜짐 상태가 **기기 간에 전파되지 않는다** | `settings.json`은 이 프로젝트의 동기화 대상이 아니다 |
| 세션 시작 후 **0~10분 랜덤 지연** | 지연 구간에 실행한 명령은 옛 코드다 |
| 갱신돼도 **그 세션은 옛 코드를 쓴다** | 버전별 디렉토리가 병존하고 실행 중 세션은 옛 것에 고정. 알림은 low priority, 10초 후 소멸 |
| 기기를 켜지 않으면 갱신도 없다 | 온라인 + Claude Code 실행이 전제 |

**결론: "자동으로 따라잡을 것"을 전제한 설계는 세울 수 없다.** (b) 가드는 그대로 필요하고,
오히려 첫 번째 이유 때문에 가치가 높다.

### 1.2 조사 중 드러난 결함 — `$SYNC_SCRIPTS` 버전 드리프트

세 SKILL.md의 0단계가 모두 같은 패턴이다.

```bash
SYNC_SCRIPTS=$(find ~/.claude -path "*/sync-backup/scripts" -type d 2>/dev/null | head -1)
```

**개발 기기에서 이미 두 개가 매칭되고, `head -1`이 고르는 것은 `cache/.../2.0.0/...`이다.**

```
~/.claude/plugins/marketplaces/claude-sync/plugins/claude-sync/skills/sync-backup/scripts
~/.claude/plugins/cache/claude-sync/claude-sync/2.0.0/skills/sync-backup/scripts
```

- 첫 번째는 **마켓플레이스 클론**이다. 레포의 default 브랜치를 그대로 받은 것이라 설치본이 아니다.
- 두 번째가 실제 설치본이다. 3.0.0이 설치되면 옛 버전 디렉토리가 지워지지 않으므로 **셋이 된다**
  (실측: `figma/2.2.90`, `2.2.91`, `2.2.95`, `2.2.96`이 모두 잔존).
- `find`의 출력 순서는 파일시스템 순서이므로 `head -1`은 **임의 선택**이다.

결과가 나쁘다. 3.0.0 세션이 2.0.0의 `generate_metadata.py`를 실행하면 **표식이 조용히 안 써진다.**
(a)가 무력화되고, 표식이 없으니 (b)는 판정할 근거를 잃는다. `reconcile_backup.py`·`update_base.py`는
양쪽에 다 있으므로 옛 의미로 동작한다. 이 결함 하나가 이 설계 전체를 무력화한다.

`CLAUDE_PLUGIN_ROOT`는 훅·모니터의 `command` 필드에 치환되는 변수일 뿐 **Bash 환경변수가 아니다**
(실측: 세션 환경에 없음). `find`가 쓰인 이유이고, 고치려면 `find`를 정확하게 만들어야 한다.

## 2. 목표 / 비목표

### 목표

1. 백업 레포가 **자기를 쓴 버전과 읽는 데 필요한 최소 버전을 스스로 밝힌다.**
2. 낮은 버전 기기가 그 표식을 읽고 **`/sync-backup`을 스스로 멈춘다.**
3. `/sync-status`는 아무것도 막지 않고 **경고만** 한다. `/sync-restore`는 **경고 후 묻는다.**
4. 판정은 **`lib/compat.py` 한 곳**을 통한다. 세 SKILL.md가 각자 버전을 비교하지 않는다.
5. 다운그레이드 사고를 **탐지**하고 마지막 정상 백업을 **제안**한다(자동 복구는 하지 않는다).
6. 실행 중인 플러그인 버전과 **같은 버전의 스크립트**를 실행한다.

### 비목표

- **2.0.0 기기를 구하는 것.** 불가능하다. 그쪽 코드를 바꿀 수 없다.
- `plugins.json`의 스키마 버전 도입. 후속 브리프의 범위다.
- `mcp-servers-v2.json` 같은 **파일 추가형 마이그레이션.** 브리프 1.2에서 기각됐다.
- 버전 번호 상승. `plugin.json`·`marketplace.json`은 `3.0.0`이고 이 작업도 같은 릴리즈다.
- 백업마다 git 태그를 옮기는 것.

## 3. 결정 사항

브리프 3장의 여섯 가지 + 조사 중 추가된 하나. **여기 적힌 것이 확정이다.**

| # | 결정 | 근거 |
|---|---|---|
| 1 | **semver 정책**: 레포에 쓰는 문서의 스키마가 하위 호환 없이 바뀌면 **major**. 읽는 쪽 확장은 minor, 버그 수정은 patch. **major는 장식이 아니라 호환 경계이며 `min_reader_version`에 테스트로 묶인다**(5.2) | Claude Code에 semver 비교·제약 해석이 전혀 없다(브리프 2.2). 툴이 강제하지 않으므로, **우리가 스스로 강제하지 않으면 이 숫자는 아무 일도 하지 않는다** |
| 2 | **판정 근거**: `min_reader_version`은 backup 전체를 막는 **단일 게이트**. 항목별 보류는 **각 파일 자체의 `version` 필드**로 판정한다. `sync-metadata.json`의 `schema` 맵은 사람이 읽는 요약일 뿐 판정 근거가 아니다 | metadata는 파생 산출물이라 유실·불일치가 가능하다. 파일 자체의 `version`이 권위 있다. 지금 뚫려 있는 구멍(형태는 알아보지만 상위 버전인 문서)도 닫힌다 |
| 3 | **차단 대상**: `/sync-backup`만. status는 경고만, restore는 경고 후 확인 | status를 막으면 진단 수단이 사라지고, restore를 막으면 업데이트 안내를 받을 경로가 사라진다 |
| 4 | **표식 없는 백업**: 표식 없음 = 2.x가 쓴 것 = 우리보다 앞설 수 없음 → **차단하지 않는다.** 3.0.0부터는 항상 표식을 쓴다 | 표식은 3.0.0에서 신설된다. 없다는 것은 그 이전 버전이 썼다는 뜻이다 |
| 5 | **복구 UX**: 확인 후에만 | 자동 복구는 옛 기기가 *의도적으로* 지운 서버까지 되살린다 |
| 6 | **git 태그**: 남기지 않는다 | 백업 레포는 사용자 데이터 레포다. 우리 코드가 태그를 관리하면 상태가 하나 더 생긴다. (c)는 커밋 내용을 직접 검사하므로 태그 없이 동작한다. `plugin tag`는 플러그인 소스 레포용으로만 쓴다 |
| 7 | **`$SYNC_SCRIPTS` 드리프트 수정을 이 작업에 포함한다** | 1.2 참조. 이것 없이는 (a)가 조용히 무력화된다 |

## 4. 스크립트 경로 해석 (결정 7)

세 SKILL.md의 0단계를 **플러그인 루트 기준**으로 바꾼다.

```bash
# 설치된 플러그인 루트를 고른다.
#  - plugins/cache 아래만 본다. plugins/marketplaces는 레포 클론이지 설치본이 아니다.
#  - 여러 버전이 남아 있으므로 sort -V로 가장 높은 것을 고른다. head -1은 임의 선택이다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' | sort -V | tail -1)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"    # 스킬마다 이 부분만 다르다
SYNC_LIB="$SYNC_ROOT/lib"

# 어느 버전을 쓰는지 눈에 보이게 한다. 불일치는 조용하면 안 된다.
echo "Plugin root: $SYNC_ROOT"
python3 -c 'import json,sys; print("Version:", json.load(open(sys.argv[1])).get("version","unknown"))' \
  "$SYNC_ROOT/.claude-plugin/plugin.json"
```

`SYNC_ROOT`를 찾지 못하면 플러그인이 제대로 설치되지 않은 것이므로 중단하고 안내한다.

`sort -V`는 macOS BSD sort에서 동작한다(실측 확인: `2.0.0 < 3.9.0 < 3.10.0`).

**restore의 `SYNC_BACKUP_SCRIPTS`도 같은 `SYNC_ROOT`에서 유도한다.** 지금은 두 번째 `find`로
따로 찾고 있어 두 스킬의 스크립트가 서로 다른 버전에서 올 수 있다.

## 5. (a) 레포 수준 표식

### 5.1 `sync-metadata.json`

`generate_metadata.py`가 생성하는 파일에 세 필드를 추가한다.

```json
{
  "files": {
    "agents/code-reviewer.md": "a3f2c1d4e5b6...",
    "CLAUDE.md": "1c2d3e4f5a6b..."
  },
  "written_by_version": "3.0.0",
  "min_reader_version": "3.0.0",
  "schema": { "mcp-servers.json": 2 }
}
```

| 필드 | 출처 | 성격 |
|---|---|---|
| `written_by_version` | `$SYNC_ROOT/.claude-plugin/plugin.json`의 `version` | 정보. 판정에 쓰지 않는다 |
| `min_reader_version` | **`compat.MIN_READER_VERSION` 코드 상수** | **판정 근거.** 이것 하나가 backup 게이트다 |
| `schema` | `{"mcp-servers.json": mcp_config.SCHEMA_VERSION}` | 사람이 읽는 요약. 판정에 쓰지 않는다(결정 2) |

### 5.2 `min_reader_version`은 왜 상수이고, 그래서 semver의 의의는 무엇인가

**현재 플러그인 버전을 그대로 쓰면 안 된다.** 그러면 3.0.1을 내는 순간 3.0.0 기기가 전부
막힌다. 스키마는 하나도 안 바뀌었는데도.

**그렇다고 아무 데도 묶이지 않은 자유로운 상수여도 안 된다.** 두 가지 이유다.

첫째, **버전 숫자가 하는 일이 없어진다.** Claude Code는 semver를 읽지 않는다(브리프 2.2).
우리 코드마저 안 읽으면 major·minor·patch는 사람에게 주는 인상일 뿐이고, 실제로 쓰이는 것은
"두 숫자의 순서" 하나다. 그것은 단조 증가하는 정수 하나로도 똑같이 된다.

둘째, 그리고 더 나쁜 것은 **실패 양상**이다. 스키마를 깨면서 상수 올리는 것을 잊으면
**가드가 조용히 발동하지 않는다.** 옛 기기가 통과해 레포를 파괴한다 — 이 작업이 막으려는
바로 그 사고다. 잊기도 쉽다. 버전을 올리는 것은 릴리즈에 필수이고 `plugin tag`가 검증까지
하지만, `lib/compat.py` 안의 상수는 안 고쳐도 릴리즈가 된다.

그래서 **major를 호환 경계로 못 박고, 상수를 거기에 묶는다.**

- `MIN_READER_VERSION`은 `lib/compat.py`의 상수다. 스키마 호환성을 결정하는 것은 **코드**이지
  `plugin.json`의 문자열이 아니므로 코드 옆에 두는 것이 정직하고, `plugin.json`을 못 읽는
  상황에서도 표식이 정상적으로 기록된다(5.5).
- **불변식: `MIN_READER_VERSION`의 major는 `plugin.json`의 major와 같아야 한다.**
  **테스트가 강제한다**(12.3). major를 올리면서 상수를 손대지 않으면 개발 시점에 시끄럽게
  깨진다. 조용한 실패를 시끄러운 실패로 바꾸는 것이 이 테스트의 전부다.
- 결정 1에 따라 같은 major 안에서는 스키마가 깨지지 않으므로, 실제 값은 항상 **`{major}.0.0`**이다.
  3.0.0에서는 `"3.0.0"`이다.

#### 이 프로젝트에서 semver가 갖는 의의

| 자리 | 코드가 읽는가 | 하는 일 |
|---|---|---|
| **major** | **읽는다** | **호환 경계.** `min_reader_version`의 값이자 차단 판정의 실질적 기준 |
| minor | 비교의 하위 자릿수로만 | 읽는 쪽 확장. `min_reader`가 항상 `X.0.0`이므로 판정 결과를 바꾸지 못한다 |
| patch | 비교의 하위 자릿수로만 | 버그 수정. 위와 같다 |

**minor·patch에 코드가 의미를 부여하지 않는다는 것을 숨기지 않는다.** 판정만 놓고 보면
단조 증가하는 정수 하나로도 6.4가 그대로 돌아간다. semver를 쓰는 값어치는 **사람이 숫자만
보고 "이 업그레이드가 내 백업을 깨뜨릴 수 있는가"를 알 수 있다**는 것이고, 조용한 데이터
손실이 실패 양상인 도구에서는 그것이 값을 한다.

> **한 번 올려 푸시하면 되돌릴 수 없다.** 그 미만 기기는 전부 막힌다.
> 그래서 major는 스키마가 실제로 깨질 때만 올린다. **"큰 리팩터링"은 major가 아니다.**
> major를 올리는 커밋은 무엇이 깨졌는지를 커밋 메시지에 적는다.

#### minor·patch 판정 체크리스트 — "기능 추가면 minor"가 아니다

**같은 major 안에서는 아무도 서로를 차단하지 않는다.** 그래서 minor·patch의 안전 조건은
하나로 압축된다.

> **같은 major의 옛 기기가 새 데이터를 만나 되쓰기해도 그 데이터가 살아남는가.**

3.0.0 코드로 확인한 판정표다. 새 정보를 **어디에** 넣느냐가 전부를 가른다.

| 변경 | 옛 3.x가 되쓰면 | 판정 |
|---|---|---|
| `mcp-servers.json`의 **서버별** 키 추가 | `merge` 케이스 8·9가 `servers[name] = repo[name]`로 레포 값을 유지한다 | **minor 가능** |
| `mcp-servers.json`의 **최상위** 키 추가 | `dump_backup`이 `{version, scope, servers}`만 쓴다 → **소멸** | **major** |
| 동기화 대상 추가 (`SYNCED_DIRS`에 새 디렉토리) | `reconcile_backup`은 로컬 목록만 순회하며 레포 파일을 지우지 않는다 | **minor 가능** |
| `plugins.json`에 무엇이든 추가 | `extract_plugins.py`가 로컬 `settings.json`으로 통째 재생성 → **소멸** | **불가** (아래) |
| `sync-metadata.json`에 필드 추가 | 매 백업 재생성이라 옛 기기가 지운다 | 파생 정보만 넣는 한 무해 |

**예외 — base가 없으면 서버별 키도 소멸한다.** `merge`는 `base is None`일 때 합집합으로
degrade하며 `if in_l: servers[name] = local[name]`로 로컬이 통째로 이긴다. 새 기기의 첫
백업(restore 전)이 이 경우다. "새 기기는 restore 먼저"라는 기존 원칙이 여기서도 근거를 갖는다.

**`plugins.json`은 지금 어떤 버전 조합에서도 안전하지 않다.** 레포를 읽지 않고 재생성하므로
major·minor·patch와 무관하게 다른 기기가 넣은 것을 파괴한다. 후속 브리프의 첫 task가
"스키마 설계가 아니라 `extract_plugins.py`가 파괴하지 않게 만드는 것"인 이유다.
**그 작업 전에는 `plugins.json`에 새 정보를 넣지 않는다.**

실무 규칙으로 줄이면: **새 정보가 서버별 dict 안에 들어가면 minor, 최상위나 `plugins.json`에
들어가면 major.**

### 5.3 `schema`에 `plugins.json`을 넣지 않는 이유

`plugins.json`에는 아직 자체 `version` 필드가 없다. 결정 2에 따라 판정은 파일 자체의 필드로
하므로, metadata에 `"plugins.json": 1`을 적으면 **없는 사실을 쓰는 것**이 된다.
후속 작업이 `plugins.json`에 스키마 버전을 도입할 때 함께 추가한다.

### 5.4 충돌 대상이 아니다

`sync-metadata.json`은 매 백업마다 재생성되는 파생 산출물이며 reconcile 대상이 아니다.
`sync_state.SYNCED_DIRS`(`agents`, `skills`)와 `SYNCED_FILES`(`CLAUDE.md`) 어디에도 없다 — 확인 완료.

**시각·기기명은 넣지 않는다.** 2026-06-10 설계가 시간 의존을 제거했고, 매 백업마다 diff가
생겨 소음이 된다. 언제·누가는 git commit이 이미 기록한다.

### 5.5 자기 버전을 못 읽을 때

`plugin.json`이 없거나 깨졌거나 `version`이 없으면 `written_by_version`을 **생략하고** 경고한다.
metadata 생성 자체는 계속한다 — 자기 버전을 모르는 것이 파일 해시를 못 쓸 이유는 아니다.
`min_reader_version`은 상수이므로 이 경우에도 정상적으로 기록된다.

## 6. (b) `lib/compat.py`

### 6.1 책임

**순수 판정.** git도 네트워크도 부르지 않는다. 파일 I/O는 얇은 `main()`에만 있다 —
`mcp_config.py`가 순수 함수 + `load_backup`/`dump_backup`으로 나뉜 것과 같은 구조다.

세 SKILL.md는 이 파일 하나만 부른다. **각자 버전을 비교하지 않는다.** 그렇게 하면 이
프로젝트가 없애려고 만든 파서 드리프트가 그대로 재현된다.

### 6.2 상수

```python
MIN_READER_VERSION = "3.0.0"      # 5.2 참조. 손으로만 올린다
METADATA_RELPATH = "sync-metadata.json"
```

### 6.3 API

```python
def parse_version(text):
    """'3.10.0' -> (3, 10, 0). 파싱 못 하면 None.

    문자열 비교를 쓰면 '3.10.0' > '3.9.0'이 거짓이 된다. 반드시 정수 튜플로 비교한다.
    'v3.0.0'의 선행 v와 '3.0.0-rc1'의 접미사는 허용하고 코어 3자리만 읽는다.
    'unknown'(plugin list가 실제로 내는 값)은 None이다.
    """

def read_plugin_version(plugin_json_path):
    """plugin.json의 version 문자열. 읽지 못하면 None(예외 아님).

    '자기 버전을 모른다'는 정상적으로 표현 가능한 상태여야 한다. 예외로 만들면
    호출부마다 try가 생기고 그 처리가 갈린다.
    """

UNREADABLE = object()   # 파일은 있는데 읽지 못했다 — "없다"와 반드시 구별한다

def load_metadata(path):
    """sync-metadata.json을 읽는다. 세 상태를 구별한다.

    - 없음 / JSON 깨짐 / dict 아님 -> None
    - 파일은 있는데 열지 못함(PermissionError, EIO, IsADirectoryError 등) -> UNREADABLE

    **"못 읽음"을 "없음"과 같은 값으로 표현하면 안 된다.** 표식 없음은 "2.x가 썼다"는
    의미 있는 결론이고 통과로 이어지는데(결정 4), 못 읽은 파일이 그 결론을 참칭하면
    상위 버전이 쓴 레포를 통과시켜 이 기능이 막으려는 파괴가 그대로 일어난다.
    깨진 JSON만 None으로 degrade한다 — 그것은 내용의 문제이고 다음 백업이 되돌린다.
    못 읽음은 환경의 문제라 다음 백업이 고쳐주지 않으므로 데드락 논거가 닿지 않는다.
    """

def evaluate(meta, my_version):
    """판정. 아래 표 그대로. 반환은 6.5의 dict."""

def shape_of(data):
    """백업 문서의 형태. 'absent' | 'broken' | 'v1_array' | 'v2_object' | 'unknown'

    다운그레이드 판정에 필요하다. mcp_config는 파싱해서 매핑만 주므로 원본 형태가 사라진다.
    """

def downgrade_suspected(repo_shape, base_shape):
    """레포는 v1 배열인데 내 base는 v2 객체였다 -> 옛 버전 기기가 덮어썼다."""
```

### 6.4 판정표

`evaluate(meta, my_version)`의 전수다. 이 표 밖의 경우는 없다.

| # | metadata 상태 | 내 버전 | 판정 | `reason` |
|---|---|---|---|---|
| 0 | **못 읽음 (`UNREADABLE`)** | 무관 | **차단** | `metadata_unreadable` |
| 1 | 없음 (`None`) | 무관 | 통과 | `None` |
| 2 | dict인데 `min_reader_version` 없음 | 무관 | 통과 | `None` |
| 3 | `min_reader_version`이 문자열 아님 / 파싱 불가 | 무관 | **차단** | `min_reader_unparsable` |
| 4 | 파싱 가능 | 미상 (`None`) | **차단** | `my_version_unknown` |
| 5 | 파싱 가능 | 최소치 미만 | **차단** | `older_than_min_reader` |
| 6 | 파싱 가능 | 최소치 이상 | 통과 | `None` |

- **0이 차단인 이유**: 표식이 *없다*는 것은 "2.x가 썼다"는 결론이지만, *못 읽었다*는
  아무 결론도 아니다. 둘을 같은 값으로 접으면 상위 버전이 쓴 레포를 통과시킨다.
  이때의 해법은 플러그인 업데이트가 아니라 권한·경로 확인이므로 **안내 문구도 다르다**(6.6).
- **1·2가 통과인 이유**(결정 4): 표식이 없다는 것은 3.0.0 이전이 썼다는 뜻이고, 그것은 우리보다
  앞설 수 없다. 깨진 metadata도 `load_metadata`가 `None`으로 degrade하므로 1에 합류한다.
- **3이 차단인 이유**: 필드가 *있는데* 못 읽는다는 것은 상위 버전이 우리가 모르는 형식으로
  썼을 가능성이다. "모르면 안 쓴다."
- **4가 차단인 이유**: 레포가 최소치를 요구하는데 우리가 그것을 충족하는지 증명할 수 없다.
  요구가 없으면(1·2) 자기 버전을 몰라도 통과다 — 증명할 것이 없기 때문이다.

### 6.5 반환 형태

```python
{
  "blocked": False,               # "차단"이지 "업그레이드하면 풀린다"가 아니다
  "reason": None,                 # 6.4의 reason
  "my_version": "3.0.0",          # 모르면 None
  "repo_min_reader": "3.0.0",     # 없으면 None
  "repo_written_by": "3.0.0",     # 없으면 None
  "message": "..."                # 사용자에게 보일 문구. 여기서만 만든다
}
```

> **`blocked`는 "차단"이라는 뜻이고 그 이상이 아니다.** `metadata_unreadable`은 차단이지만
> 업그레이드로 풀리지 않는다. 세 SKILL.md가 문장을 덧붙일 때는 `blocked`가 아니라
> **`reason`으로 분기한다** — "업데이트하세요"를 모든 차단에 붙이면 권한 문제를 겪는
> 사용자에게 틀린 해법을 준다. 이전 이름 `needs_upgrade`가 정확히 그 오류를 유도했다.

### 6.6 안내 문구

**한 곳에서만 만든다.** 세 SKILL.md가 각자 쓰면 드리프트한다.

차단일 때:

```
이 백업은 claude-sync 3.1.0 이상이 필요합니다 (이 기기: 3.0.0).
백업을 계속하면 레포가 손상될 수 있어 중단했습니다.

  claude plugin marketplace update claude-sync
  claude plugin update claude-sync

그다음 Claude Code를 재시작하거나 /reload-plugins 를 실행하세요.
업데이트는 재시작 전까지 적용되지 않습니다.
```

- **명령은 항상 두 줄이다.** 마켓플레이스 갱신 없이 `plugin update`만 하면 새 버전을 못 본다.
- **재시작 안내는 반드시 넣는다.** `plugin update`가 "restart required to apply"라고 명시하고,
  자동 갱신 경로에서도 `Run /reload-plugins to apply`가 뜬다(브리프 2.1.1).
- 내 버전이 미상이면 `(이 기기: 버전 미상)`으로 적고, 플러그인 설치 상태 확인을 함께 안내한다.
- **`metadata_unreadable`은 문구가 다르다.** 플러그인을 올려도 해결되지 않으므로 업그레이드
  명령을 내밀지 않는다. 대신 못 읽은 사실과 확인할 곳을 알린다:

```
백업 레포의 sync-metadata.json을 읽지 못했습니다 (권한 또는 입출력 문제).
표식을 확인할 수 없어, 이 레포가 더 높은 버전을 요구하는지 알 수 없습니다.

  ls -l <레포>/sync-metadata.json 으로 권한을 확인하거나, 레포를 다시 클론하세요.
```

> **"멈춥니다"라고 쓰지 않는다.** 이 문구는 세 스킬이 공유하는데 backup만 멈추고
> status는 계속하며 restore는 묻는다. 행동을 문구에 넣으면 나머지 둘에서 거짓이 된다.

### 6.7 CLI 진입점

```bash
python3 "$SYNC_LIB/compat.py" <레포 경로>
```

기존 스크립트 관례대로 JSON을 stdout에 낸다.

```json
{
  "status": "ok",
  "blocked": false,
  "reason": null,
  "my_version": "3.0.0",
  "repo_min_reader": "3.0.0",
  "repo_written_by": "3.0.0",
  "message": ""
}
```

- `plugin.json` 경로는 스크립트 위치에서 유도한다(`lib/../.claude-plugin/plugin.json`).
- 읽기 전용이다. 어떤 파일도 쓰지 않는다.
- **레포 디렉토리가 없으면 `blocked: true`, `reason: "repo_not_found"`다.** "표식 없음"으로
  접으면 안 된다 — 표식 없음은 "2.x가 썼다"는 *결론*이고, 레포가 없는 것은 결론이 아니라
  호출자의 입력 오류다. 특히 빈 문자열은 `os.path.join("", ...)`이 상대 경로가 되어
  **현재 디렉토리의 파일을 읽고 통과 판정을 낸다.**
- **`main()`은 마지막 방어선으로 모든 예외를 잡아 `blocked: true`, `reason: "check_failed"`로
  떨어뜨린다.** 형제 스크립트(`collect_mcp.py` 등)의 `status: "skipped"`를 베끼면 안 된다 —
  거기서 skipped는 "이 단계만 건너뛰고 진행"이지만 호환성 검사에서 그것은 "가드 없이 백업 진행"이다.
  **compat은 fail-closed다.**
- **다운그레이드 판정은 여기서 하지 않는다.** git이 필요하므로 `detect_downgrade.py`의 몫이다
  (9장). `compat.py`는 순수 판정 함수 `shape_of`·`downgrade_suspected`를 **제공만** 하고,
  그것을 부르는 것은 스크립트다. 두 진입점이 같은 플래그를 각자 계산하면 드리프트한다.

## 7. 파일 자체의 `version` 게이트 (결정 2)

### 7.1 지금 뚫려 있는 구멍

`_recognized_servers`는 **형태만** 본다. `version` 필드를 보지 않는다.

```python
if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
    return _servers_from_obj(obj)
```

그래서 미래의 v3 문서가 `{"version": 3, "servers": {...}}` 형태를 유지하면 **알아보는 것으로
판정되어 그대로 병합된다.** v3가 `servers` 값의 의미를 바꿨다면 조용히 파괴된다.
`UnknownBackupSchema`는 이 경우 발동하지 않는다.

### 7.2 수정

`_recognized_servers` **한 곳**에 게이트를 넣는다.

```python
def _recognized_servers(obj):
    if isinstance(obj, list):
        return _servers_from_obj(obj)            # v1 배열에는 version 개념이 없다
    if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
        version = obj.get("version")
        if _claims_newer_schema(version):
            return None                          # 상위 스키마 — 알아보지 못한 것으로 취급
        return _servers_from_obj(obj)
    return None


def _claims_newer_schema(version):
    """version이 SCHEMA_VERSION보다 높다고 주장하는가."""
    if isinstance(version, bool):
        return False                             # True는 int의 인스턴스다. 버전 주장이 아니다
    return isinstance(version, (int, float)) and version > SCHEMA_VERSION
```

**float까지 막는다.** `{"version": 3.0}`은 파이썬이 아닌 도구(jq, YAML 변환기, 다른 언어의
v3 writer)가 실제로 만드는 형태다. int만 막고 float를 통과시키는 것은 설계된 구분이 아니라
`isinstance` 선택의 우연이며, **게이트의 존재 이유 자체를 무력화하는 경로**다.

문자열(`"3"`)은 통과시킨다 — 손으로 고친 문서를 막지 않기 위해서다. 이 결정은
테스트로 고정한다(12.4).

**`parse_base`·`parse_backup`·`load_backup`이 모두 이 함수를 통하므로 세 곳이 자동으로
같은 기준을 갖는다.** 한 곳에만 넣으면 "이력은 못 믿는데 레포는 믿는" 비대칭이 생기고,
그 비대칭이 상위 버전 백업을 파괴한다 — 기존 주석이 경고하는 바로 그것이다.

`version`이 없거나 int가 아니면 통과시킨다(기존 동작 유지). `dump_backup`은 항상 쓰지만,
손으로 만든 문서를 막을 이유는 없다.

## 8. 세 스킬의 동작

### 8.0 검사가 성립하지 않으면 통과로 읽지 않는다 (불변식 6의 스킬 층위)

세 SKILL.md는 `compat.py`가 낸 JSON을 읽고 행동합니다. **그 JSON이 없거나 읽을 수 없는 경우가
곧 "문제 없음"이 되어서는 안 됩니다.**

> **호환성 검사 명령이 비-0으로 끝났거나, 출력이 JSON이 아니거나, `blocked` 키가 없으면
> — `blocked: true`와 같이 다룬다.**

근거: `compat.py`는 **차단일 때도 종료 코드 0으로 JSON을 내도록** 만들어져 있다(6.7).
그러므로 그렇지 않다는 것은 판정 결과가 아니라 **검사 자체가 성립하지 않았다**는 뜻이다.
`python3`이 없거나, `SYNC_ROOT`가 잘못 잡혔거나, 파일이 없는 경우가 여기 해당한다.

이때 사용자에게 보일 문구는 `compat.py`가 만들지 못하므로 SKILL.md가 직접 쓴다.
**이것이 SKILL.md가 문구를 직접 쓰는 유일한 경우다.**

```
호환성 검사를 실행하지 못했습니다 (<명령>이 실패했습니다).
이 레포를 안전하게 다룰 수 있는지 판단할 수 없어 중단했습니다.

  0단계에서 찾은 플러그인 루트가 올바른지, python3이 있는지 확인하세요.
```

`/sync-status`는 이 경우에도 멈추지 않는다 — 경고만 하고 나머지 분석을 계속한다(8.2).
`/sync-restore`는 경고 후 묻는다(8.3).



호환성 검사는 세 스킬 모두 **레포를 가져온 직후, 아무것도 쓰기 전에** 한다.

### 8.1 `/sync-backup` — 유일하게 차단한다

| 단계 | 추가/변경 |
|---|---|
| 0. 스크립트 경로 | **`SYNC_ROOT` 기준으로 교체** (4장) |
| 2. 레포 준비 (clone/pull) | — |
| **2.5 호환성 검사 (신설)** | `compat.py` 호출. `blocked`면 **파일 복사·plugins·MCP 수집 전에 중단**하고 6.6 문구를 보여준다. `pull_only` 가드가 1단계에서 하는 것과 같은 형태다 |
| **5.5 다운그레이드 탐지 (신설)** | `downgrade_suspected`면 경고 + 복구 후보 제시 + 계속할지 질문 |
| 6. MCP 수집 | 변경 없음 (`skipped` + 사유 안내는 이미 반영됨) |
| 7. `sync-metadata.json` 생성 | `written_by_version`·`min_reader_version`·`schema` 기록 (5장) |
| 10. 커밋 & 푸시 | 변경 없음. 5.5에서 복구를 택했다면 그 결과가 커밋에 포함된다 |
| 12. 결과 보고 | "이 백업은 claude-sync 3.0.0 이상을 요구하도록 기록되었습니다"를 처음 한 번 알린다 |

> **브리프 정정 — 다운그레이드 탐지는 6.5단계가 아니라 5.5단계다.**
> 브리프 5장은 MCP 수집(6단계) *다음*에 두라고 하지만, 그 시점에는 `collect_mcp.py`가 이미
> `mcp-servers.json`을 v2로 덮어쓴 뒤다. **"레포가 v1 배열"이라는 증거가 사라져 탐지 자체가
> 불가능하다.** 반드시 수집 앞에 와야 한다.

**차단은 backup에만 건다.**

### 8.2 `/sync-status` — 경고만, 아무것도 막지 않는다

| 단계 | 추가/변경 |
|---|---|
| 0. 스크립트 경로 | `SYNC_ROOT` 기준으로 교체 |
| 1. 레포 준비 직후 | `compat.py` 호출. `blocked`면 **맨 위에 크게 경고**하되 분석은 계속한다 |
| 2. MCP 비교 | 변경 없음 |
| 3. 결과 요약 | 버전 불일치를 **첫 줄에** 넣는다. `downgrade_suspected`면 그것도 보고한다 |

status가 차단하면 안 되는 이유: 버전이 안 맞을 때 사용자가 가장 먼저 실행할 명령이 status다.
그것마저 막으면 진단 수단이 사라진다. 읽기 전용이므로 위험도 없다.

### 8.3 `/sync-restore` — 경고 후 진행 여부를 묻는다

| 단계 | 추가/변경 |
|---|---|
| 0. 스크립트 경로 | `SYNC_ROOT` 기준으로 교체. `SYNC_BACKUP_SCRIPTS`도 같은 루트에서 유도 |
| 2. 레포에서 가져오기 직후 | `compat.py` 호출. `blocked`면 경고하고 **계속할지 묻는다.** pull-only라 레포는 훼손되지 않지만 **모르는 스키마의 항목을 건너뛴 부분 복원**이 된다는 점을 명시한다 |
| 3. 파일 reconcile | 변경 없음. 파일 동기화는 스키마와 무관하다 |
| 5. 플러그인 복원 | **여기가 탈출구다.** 버전이 낮아 막혔다면 필요한 것은 `plugin update`다. 복원 절차 안에서 6.6의 안내를 우선 노출한다 |
| 6. MCP 복원 | 변경 없음 |
| 6-6. base 갱신 | 변경 없음. `apply_base`가 이미 `UnknownBackupSchema`로 막는다. SKILL.md에 이유를 적어 둔다 |
| 7. 결과 보고 | 버전 때문에 건너뛴 항목을 **"실패"가 아니라 "보류"로** 보고한다 |

## 9. (c) 다운그레이드 탐지·복구

### 9.1 탐지 조건

옛 버전 기기가 레포를 덮어썼다는 **확정적 신호**다.

```
레포의 mcp-servers.json이 v1 배열   AND   내 base는 v2 객체였다
```

- 레포가 v1인 것만으로는 부족하다 — 정말 오래된 레포일 수 있다.
- base가 v2였다는 것은 **내가 v2를 본 적이 있다**는 뜻이다. 그 뒤 v1이 되었다면 누군가 되돌린 것이다.
- base를 못 읽으면(`None`) 판정하지 않는다. **신뢰할 수 없는 이력은 근거가 될 수 없다**(불변식 2).

판정은 `compat.downgrade_suspected(repo_shape, base_shape)` 순수 함수다.

### 9.2 복구 후보 탐색

`skills/sync-backup/scripts/detect_downgrade.py <레포 경로>` — git 히스토리를 훑는 것은
스크립트의 일이다. `compat.py`는 git을 부르지 않는다.

이 스크립트는 backup(쓰기 경로)과 status(읽기 경로)가 **같이** 쓴다. 4장에서 `SYNC_ROOT`를
잡으므로 status에서도 `$SYNC_ROOT/skills/sync-backup/scripts/detect_downgrade.py`로 명시적으로
부른다 — 복사본을 만들지 않는다. 읽기 전용이므로 status가 불러도 안전하다.

`mcp-servers.json`을 건드린 커밋을 최신순으로 훑어 **`version`이 2인 마지막 커밋**을 찾는다.

```bash
git log --format=%H -- mcp-servers.json
git show "<sha>:mcp-servers.json"
```

출력(JSON):

```json
{
  "status": "ok",
  "downgrade_suspected": true,
  "candidate": {
    "sha": "a1b2c3d",
    "date": "2026-08-20",
    "subject": "backup: 2026-08-20",
    "server_count": 11,
    "server_names": ["context7", "playwright", "..."]
  }
}
```

- 후보를 못 찾으면 `"candidate": null`. 그때는 사고를 알리되 복구는 제안하지 않는다.
- git 명령이 실패하면 `{"status": "skipped", "reason": ...}`. **탐지 실패가 백업을 막지 않는다.**

### 9.3 복구 UX (결정 5)

**자동으로 복구하지 않는다.** 옛 기기가 *의도적으로* 지운 서버까지 되살리기 때문이다.

SKILL.md는 다음을 보여주고 사용자에게 고르게 한다.

1. 사고 사실과 근거 (레포는 v1, 내 base는 v2였다)
2. 후보 커밋의 날짜·서버 수·서버 이름
3. 선택지
   - **복구한다** — 후보 커밋의 `mcp-servers.json`을 레포 작업본에 되돌려 놓고 백업을 계속한다.
     이후 6단계의 3-way 병합이 로컬과 정상적으로 합친다.
   - **복구하지 않고 계속한다** — 현재 레포 상태를 그대로 두고 백업한다.
   - **중단한다** — 다른 기기의 상태를 확인한 뒤 다시 온다.

## 10. 에러 처리 & 불변식

### 10.0 불변식 6 — 판정 불가를 통과로 접지 않는다

> **`compat.py`에서 "판정할 수 없다"는 반드시 표현 가능한 별도 상태여야 하고,
> 그것을 소비하는 쪽은 명시적으로 다뤄야 한다. 모르는 입력의 기본 갈래는 통과가 아니라
> 차단이거나 예외다.**

이 불변식은 사후에 추가된 것이 아니라 **여섯 번의 code review가 같은 결함을 반복해서
찾아낸 결과** 승격된 것이다. 잡힌 사례는 전부 한 형태였다.

| 사례 | 접힌 것 | 결과 |
|---|---|---|
| `parse_version` 접두 매치 | `'3.0.0.5'` → `(3,0,0)` | 통과 |
| `_load_json` | 못 읽음 → 없음 | 통과 |
| `check()` | 없는 레포 → 표식 없음 | 통과 |
| 스키마 게이트 | `3.0`(float) → 버전 주장 아님 | 통과 |
| `main()` | 예외 → 트레이스백 + 비-0 | 안내 소실 |
| `shape_of` | 타입 오류 → `"broken"` | 탐지 꺼짐 |
| `downgrade_suspected` | 모르는 shape → `False` | 탐지 꺼짐 |

**근본 원인은 개별 함수의 부주의가 아니다.** 교리가 한 함수의 주석으로만 존재했기 때문에,
새 함수를 쓸 때마다 "판정 불가"의 표현을 다시 결정하게 되고 가장 손이 덜 가는 기본값이
매번 fail-open 쪽이었다. 그래서 개별 수정으로는 수렴하지 않는다 — 다음 함수도 같은 선택을 한다.

**지켜야 할 세 가지:**

1. **판정 불가는 값으로 표현한다.** `UNREADABLE` 센티널과 `shape_of`의 `"unreadable"`이 그
   예다. "없음"이나 "정상"과 같은 값으로 접지 않는다.
2. **문자열 열거형을 받는 판정 함수는 총(total)이어야 한다.** 모르는 값을 받으면 `ValueError`를
   던진다. `_upgrade_message`가 이미 그렇게 한다 — 같은 파일 안에서 관례가 갈리면 안 된다.
3. **호출자 오류는 값이 아니라 예외로 드러낸다.** `shape_of`에 파싱된 객체를 넘기는 것은
   "깨진 문서"가 아니라 프로그래밍 실수다. fail-open 방향의 반환값으로 삼키면
   그 실수가 "사고 없음"이라는 결론이 된다.

**새 판정 함수를 추가할 때마다 이 셋을 확인한다.** 확인을 강제하는 테스트를 함께 붙인다
(12.8).

### 10.1 상황별 처리



기존 다섯 불변식(`2026-08-20-mcp-redesign-STATUS.md` 5장)을 그대로 지킨다. 이 설계가 추가로
지켜야 하는 것:

| 상황 | 처리 | 이유 |
|---|---|---|
| `sync-metadata.json` 없음 | 통과 | 결정 4 |
| `sync-metadata.json` JSON 깨짐 | 통과 + 경고 | 막으면 데드락이다(6.3). 다음 백업이 고친다 |
| `sync-metadata.json`을 **열지 못함** (권한·IO) | **차단** | 내용이 아니라 환경의 문제라 다음 백업이 고쳐주지 않는다. 못 읽음을 없음으로 접으면 fail-open이다 |
| `min_reader_version` 있는데 파싱 불가 | **차단** | 모르면 안 쓴다 |
| `plugin.json` 없음/깨짐 | 내 버전 미상 → 레포가 요구하면 차단, 아니면 통과 | 증명할 것이 없으면 막지 않는다 |
| 레포 디렉토리가 없음 / 경로가 빈 문자열 | **차단** (`repo_not_found`) | 빈 문자열은 cwd의 파일을 읽어 거짓 통과를 낸다 |
| `check()`가 예상 못 한 예외 | **차단** (`check_failed`) | 마지막 방어선. skipped로 떨어뜨리면 가드 없이 백업이 진행된다 |
| `SYNC_ROOT` 못 찾음 | 즉시 중단 + 안내 | 어떤 버전을 실행할지 모르는 상태로 진행하면 안 된다 |
| base 읽기 실패 | 다운그레이드 판정 안 함 | 불변식 2 |
| `detect_downgrade.py`의 git 실패 | `skipped` + 백업 계속 | 탐지는 부가 기능이다 |
| 레포 문서의 `version`이 `SCHEMA_VERSION`보다 큼 | `UnknownBackupSchema` → 해당 항목 `skipped` | 7장 |

## 11. 영향 파일 요약

| 파일 | 변경 |
|---|---|
| `lib/compat.py` | **신설**. 판정 + 문구 + CLI |
| `lib/mcp_config.py` | `_recognized_servers`에 `version` 게이트 (7장) |
| `skills/sync-backup/scripts/generate_metadata.py` | 세 필드 추가 (5장) |
| `skills/sync-backup/scripts/detect_downgrade.py` | **신설** (9장) |
| `skills/sync-backup/SKILL.md` | 0단계 교체, 2.5·5.5단계 신설, 7·12단계 보강 |
| `skills/sync-status/SKILL.md` | 0단계 교체, 1단계 검사, 3단계 요약 |
| `skills/sync-restore/SKILL.md` | 0단계 교체, 2단계 검사·질문, 5·7단계 보강 |
| `tests/test_compat.py` | **신설** |
| `tests/test_downgrade.py` | **신설** (실제 git 픽스처) |
| `tests/test_mcp_config.py` | `version` 게이트 케이스 추가 |
| `tests/test_mcp_scripts.py` | `generate_metadata` 케이스 추가 |

**`plugin.json`·`marketplace.json`의 버전은 건드리지 않는다.** 둘 다 `3.0.0`이다.

## 12. 검증 방법

기존 166개는 전부 통과해야 한다. 추가 목표 **30개 이상**.

### 12.1 semver 비교

- `parse_version`: `"3.0.0"` → `(3,0,0)`, `"v3.0.0"` → `(3,0,0)`, `"3.0.0-rc1"` → `(3,0,0)`
- **`"3.10.0" > "3.9.0"`이 참인지** — 문자열 비교였다면 거짓이다. 이 프로젝트의 명시된 함정이다
- `"unknown"`, `""`, `None`, `"3.0"`, `"a.b.c"` → `None`

### 12.2 판정 (6.4의 표 전수)

여섯 행 각각에 테스트 하나씩. 특히:
- 표식 없는 레포 + 낮은 버전 기기 → **통과** (결정 4)
- 표식 있는 레포 + 버전 미상 기기 → **차단**
- 표식 **없는** 레포 + 버전 미상 기기 → **통과**
- 깨진 metadata → **통과** (데드락 방지)

### 12.3 표식 생성과 semver 불변식

- 세 필드가 모두 있고 값이 맞는다
- `min_reader_version`이 **`plugin.json`의 버전이 아니라 상수**다 — `plugin.json`을 `3.9.9`로
  바꾼 픽스처에서도 `min_reader_version`이 `"3.0.0"`이어야 한다. 같은 major 안의 상승이
  옛 기기를 막아서는 안 된다(5.2의 첫 번째 이유)
- **`MIN_READER_VERSION`의 major == `plugin.json`의 major** — 픽스처가 아니라 **레포의 실제
  `plugin.json`**을 읽어 단언한다. 이 테스트 하나가 5.2의 불변식을 강제한다.
  major를 올리면서 상수를 안 건드리면 여기서 깨진다. **조용한 실패를 시끄러운 실패로 바꾸는
  것이 이 테스트의 존재 이유이며, 이것이 이 프로젝트에서 semver를 의미 있게 만드는 유일한 장치다**
- `min_reader_version`의 minor·patch가 `0`이다 — 결정 1에 따라 호환 경계는 항상 `{major}.0.0`이다
- `plugin.json`이 없으면 `written_by_version`이 생략되고 **`min_reader_version`은 정상 기록된다**
  (상수를 쓰는 두 번째 이유)
- `schema`에 `plugins.json`이 **없다**

### 12.4 `version` 게이트

- `{"version": 3, "servers": {...}}` → `load_backup`이 `UnknownBackupSchema`
- 같은 문서 → `parse_base`가 `None` (비대칭 없음)
- `{"version": 2, ...}` → 정상
- v1 배열 → 정상
- `version` 필드 없는 `{"servers": {...}}` → 정상

### 12.5 반복 적용·교대 적용

> 단발 호출 테스트가 전부 통과하는데도 시스템이 데이터를 잃은 전례가 이 프로젝트에 있다.

- **반복**: 같은 레포에 backup을 2회, 3회 → `sync-metadata.json`이 안정적이고(파일 해시 외
  diff 없음) base가 발산하지 않는다
- **교대**: 레포의 `min_reader_version`을 높였다가 되돌린다 → 차단됐다가 다시 통과한다.
  **차단이 어떤 상태도 남기지 않는다**(base 전진 없음, 레포 파일 변경 없음)
- **차단 후 레포 무결성**: 차단된 backup이 레포 작업본을 전혀 건드리지 않았는지 해시로 확인

### 12.6 다운그레이드 (실제 git 레포 픽스처)

- v2 커밋 → v1로 덮어쓴 커밋 → 탐지되고 **v2 커밋을 찾아낸다**
- base가 v1이면 탐지 안 함 (정말 오래된 레포)
- base가 `None`이면 탐지 안 함 (불변식 2)
- 히스토리에 v2가 없으면 `candidate: null`
- git 실패 → `skipped`, 백업은 계속

### 12.8 판정 함수가 총(total)인가 — 불변식 6의 강제 장치

문자열 열거형을 받는 판정 함수마다 **모르는 값에 `ValueError`를 던지는지** 단언한다.
이 테스트가 없으면 불변식 6은 다시 주석으로만 남고, 다음 함수가 같은 실수를 반복한다.

- `_upgrade_message("some_future_reason", ...)` → `ValueError`
- `downgrade_suspected("v1array", "v2_object")` → `ValueError` (오타)
- `shape_of(이미_파싱된_객체)` → `TypeError` (호출자 오류)

그리고 **판정 불가 상태가 통과로 접히지 않는지**를 갈래마다 단언한다.

- `check()`에서 `UNREADABLE` → 차단
- `downgrade_suspected`에서 `"unreadable"` → 탐지하지 않되, 그 사실이 호출부에 드러난다

### 12.7 스크립트 경로 해석

셸 파이프라인이므로 파이썬 테스트에서 `bash -c`로 직접 실행하고, `HOME`을 픽스처 트리로
바꿔 검증한다.

- 여러 버전 디렉토리(`2.0.0`, `3.0.0`, `3.10.0`)를 만들어 두고 **`3.10.0`을 고르는지**
  — `head -1`이었다면 임의 선택이 된다
- `plugins/marketplaces/` 아래에도 같은 구조를 만들어 두고 **제외하는지**
- 하나도 없으면 빈 문자열을 내어 SKILL.md가 중단할 수 있게 하는지

**드리프트 가드**: 세 SKILL.md를 읽어 다음을 단언한다.

- 셋 다 `plugins/cache` 한정 + `sort -V` 파이프라인을 포함한다
- 셋 다 옛 패턴(`find ~/.claude -path "*/sync-*/scripts" ... | head -1`)을 **포함하지 않는다**

같은 스니펫이 세 곳에 복제되므로, 한 곳만 고치고 나머지를 잊는 것을 이 테스트가 막는다.

## 13. 배포 순서

이 작업이 끝나도 **3.0.0 배포 순서는 그대로다.**

> 모든 기기를 3.0.0으로 올린 뒤에 어느 기기에서든 `/sync-backup`을 실행한다.

이 설계의 차단 장치는 3.0.0 이후 버전에서만 동작한다. 2.0.0 기기의 backup은 여전히
레포 파일을 통째로 재생성하며, 그것을 막을 코드는 2.0.0 안에 없다.
`autoUpdate`도 도움이 되지 않는다(1.1).

**현재 이 개발 기기의 캐시는 `claude-sync/2.0.0`이다.** 플러그인을 업데이트하기 전에는
`/sync-backup`을 실행하지 않는다.
