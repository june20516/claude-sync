# claude-sync: MCP 서버 백업 데이터 소스 재설계

- 작성일: 2026-08-20
- 상태: 설계 확정 (구현 계획 대기)
- 대상 레포: `june20516/claude-sync` (플러그인)
- 선행 설계: `2026-06-10-git-like-sync-design.md` (v2.0.0)

## 1. 배경 & 문제

v2.0.0의 MCP 백업은 `claude mcp list`의 **사람이 읽는 텍스트 출력**을 정규식으로 파싱한다.
실환경(macOS, Claude Code, 서버 11개)에서 재현한 결과는 다음과 같다.

### 1.1 측정된 실패

`claude mcp list` 출력 11줄을 v2.0.0 `parse_mcp.py`에 그대로 입력했을 때:

| 서버 | 백업 결과 | 저장된 type | 실제 |
|---|---|---|---|
| `claude.ai *` 7개 | 저장됨 | `stdio` | HTTP · 계정 레벨이라 복원 불가 |
| `plugin:figma:figma` | 제외됨(의도대로) | — | 플러그인이 제공 |
| `context7` | 저장됨 | `HTTP` | `headers` 누락 → 인증 불가 |
| `playwright` | **누락** | — | stdio |
| `safari-mcp-stp` | **누락** | — | stdio |

`~/.claude.json`의 user 스코프 서버는 `playwright`, `context7`, `safari-mcp-stp` 3개다.
**복원 가능한 형태로 백업된 서버는 0개다.** MCP 백업은 부분 고장이 아니라 사실상 동작하지 않는다.

### 1.2 개별 결함

- **Bug #1 — stdio 서버 누락.** 정규식 `^(.+?):\s+(\S+)\s+(?:\((\w+)\)\s+)?-\s+.+$`의 `(\S+)`는
  공백 없는 단일 토큰만 잡는다. `npx @playwright/mcp@latest`,
  `/Applications/Safari Technology Preview.app/Contents/MacOS/safaridriver --mcp`처럼 명령에 공백이 있으면
  매칭이 실패하고 **경고 없이 조용히 누락**된다.
- **Bug #2 — status와 backup의 파서 불일치.** `compare_mcp.py`는 `^(.+?):\s+`라는 훨씬 느슨한 패턴을 쓴다.
  status는 11개를 인식하고 backup은 8개만 기록하므로, 백업 직후에도 `/sync-status`가 영구적으로 차이를 보고한다.
- **Bug #3 — type 오분류.** CLI가 `(HTTP)` 표기를 붙이지 않는 줄은 전부 `stdio`로 저장된다.
  원격 HTTP 커넥터 7개가 stdio로 기록된다.
- **Bug #4 — 스키마가 복원을 지원하지 않음.** `name`/`url`/`type`만 저장한다.
  stdio 복원에는 `command`/`args`가, HTTP 인증에는 `headers`가 필요한데 텍스트 출력에는 그 정보가 애초에 없다.
- **Bug #5 — cwd 의존 (신규 발견).** `claude mcp list`는 실행 디렉토리의 local 스코프 서버를 함께 출력한다.
  `/Users/bran/repositories/pnpt-types`에서 실행하면 그 프로젝트 전용 서버 `atlassian`이 목록에 추가된다.
  즉 **어느 디렉토리에서 `/sync-backup`을 실행했는지에 따라 프로젝트 전용 서버가 user 백업에 섞인다.**
- **Bug #6 — 복원 불가 항목 백업 (신규 발견).** `claude.ai *` 커넥터는 계정 레벨이라 `~/.claude.json`에 없고
  `claude mcp add`로 재현할 수 없다. v2.0.0은 `plugin:`만 제외하고 이들은 그대로 백업한다.

### 1.3 근본 원인

여섯 결함은 서로 다른 버그가 아니라 하나의 원인에서 파생된 증상이다.
**사람이 읽으라고 만든 CLI 텍스트 출력을 기계 파싱의 데이터 소스로 삼았다.**
그 출력은 (a) 손실 압축이고(`command`/`args`/`env`/`headers`/scope를 버린다),
(b) 값 안에 구분자가 등장하는 비정형이며, (c) cwd에 의존하고, (d) 호환성 계약이 없다.
`claude mcp list`에 `--json` 옵션은 존재하지 않는다(확인함).

파서가 두 벌 존재한다는 사실(#2)도 이 원인의 결과다.
비정형 텍스트는 파싱 규칙을 코드마다 새로 정의하게 만들고, 정의가 둘이면 드리프트는 시간 문제다.

### 1.4 별개로 드러난 문제 — `mcp-servers.json`은 reconcile 대상이 아니다

`sync_state.iter_synced_relpaths`가 다루는 것은 `agents/`, `skills/`, `CLAUDE.md`뿐이다.
`mcp-servers.json`은 백업 6단계에서 매번 새로 생성되고 10단계 `git add -A`로 통째로 덮어씌워진다.
따라서 기기 A가 백업하면 기기 B에만 있던 서버가 레포에서 사라진다(git 히스토리에는 남고,
restore는 additive이므로 B의 로컬은 삭제되지 않는다).

그런데 `README.ko.md`는 "**로컬 파일은 절대 자동으로 덮어쓰지 않습니다**"라는 파일 단위 보장을 내걸고 있고,
`mcp-servers.json`은 레포 파일 목록에 다른 파일들과 나란히 실려 있다.
**이 예외는 README에도, SKILL.md에도, 백업 레포 README에도 적혀 있지 않다.**

## 2. 목표 / 비목표

### 목표
1. MCP 백업의 데이터 소스를 CLI 텍스트에서 **`~/.claude.json`의 user 스코프 `mcpServers` 객체**로 전환한다.
2. backup·status·restore가 **단일 공용 모듈**만 통해 MCP를 다루게 하여 파서 드리프트를 구조적으로 차단한다.
3. `command`/`args`/`env`/`headers`/`type`/`url`을 보존하여 **실제로 복원 가능한** 백업을 만든다.
4. `headers`/`env`의 비밀 값을 마스킹하되 **키 이름은 보존**한다.
5. `mcp-servers.json`을 **서버 이름 키 단위 3-way 병합** 대상으로 만들어 기기 간 덮어쓰기 손실을 없앤다.
6. 문서가 실제 동작과 어긋난 부분을 정정한다.
7. **base는 레포의 사본이 아니라 "로컬이 동의한 부분"만 담는 파생 문서로 유지한다**(7.3).
   이 불변식은 목표가 아니라 제약이다 — 깨는 순간(예: `base ← 레포 파일 바이트`) 다음 백업이
   타 기기의 서버를 경고 없이 삭제한다. base를 만지는 모든 코드는 7.3을 읽고 써야 한다.

### 비목표 (이번 범위 밖)
- `plugins.json`의 덮어쓰기 문제. 같은 구조적 결함이 있으나 이번엔 고치지 않고 **문서에 사실대로 명시**한다.
- project 스코프(`.mcp.json`) 및 local 스코프 서버 동기화. 프로젝트 레포에 속하므로 user 설정 동기화 대상이 아니다.
- `claude.ai *` 커넥터 동기화. 계정 레벨이라 기기 설정으로 재현할 수 없다.
- 비밀 값 자체의 동기화(볼트 연동 등).
- **파일**의 삭제 전파. 선행 설계의 비목표를 그대로 유지한다.
  MCP 서버는 이번에 삭제 전파를 도입하되, 로컬 제거는 restore에서 사용자 확인을 거쳐야 완결된다(7.4, 8.3).

## 3. 데이터 소스

### 3.1 스코프와 저장 위치

| 스코프 | 저장 위치 | 동기화 대상 |
|---|---|---|
| user | `~/.claude.json` top-level `mcpServers` | **대상** |
| local | `~/.claude.json` `projects[<cwd>].mcpServers` | 제외 |
| project | 프로젝트의 `.mcp.json` | 제외 |
| 계정 커넥터 | `~/.claude.json`에 없음 (`claude.ai *`) | 제외 |
| 플러그인 제공 | 플러그인이 소유 (`plugin:*`) | 제외 |

user와 local의 구분은 실측으로 확인했다. `playwright`/`context7`/`safari-mcp-stp`는 top-level에 있어
모든 디렉토리에서 보이고, `atlassian`은 `projects["/Users/bran/repositories/pnpt-types"].mcpServers`에 있어
해당 디렉토리에서만 보인다. project 스코프의 `.mcp.json` 위치는 `claude mcp add --scope` 도움말 기준이다.

### 3.2 이 선택이 자동으로 해결하는 것

top-level `mcpServers`만 읽으면 `claude.ai *`(#6), `plugin:*`(#6), local·project 스코프(#5)는
**애초에 그 객체에 존재하지 않으므로** 필터 코드 없이 제외된다.
`command`/`args`/`env`/`headers`가 그대로 들어 있으므로 #3·#4가 사라지고,
정규식이 없으므로 #1이 사라진다. 헬스체크를 유발하지 않으므로 백업·상태확인이 빨라지고 네트워크에 의존하지 않는다.

### 3.3 감수하는 리스크

`~/.claude.json`은 Claude Code의 비공개 내부 상태 파일이며 호환성 계약이 없다.
포맷이 바뀌면 백업이 깨질 수 있다. 완화책:
- 서버 config를 **통째로 보존**한다(모르는 필드도 그대로). 필드가 추가돼도 백업은 살아남는다.
- 읽기 실패를 정상 상태와 엄격히 구분하고(9장), 실패 시 MCP 단계만 건너뛴다.

## 4. 스키마 v2

```json
{
  "version": 2,
  "scope": "user",
  "servers": {
    "playwright": { "command": "npx", "args": ["@playwright/mcp@latest"] },
    "safari-mcp-stp": {
      "command": "/Applications/Safari Technology Preview.app/Contents/MacOS/safaridriver",
      "args": ["--mcp"]
    },
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp",
      "headers": { "CONTEXT7_API_KEY": "<REDACTED>" }
    }
  }
}
```

- `servers`는 **이름 → config 객체** 매핑이다. 배열에서 객체로 바뀐 것이 키 단위 병합(7장)을 가능하게 한다.
- config는 `~/.claude.json`의 값을 그대로 보존하며, 비밀 필드의 **값만** 치환한다.
- `json.dump(..., indent=2, sort_keys=True)`로 저장해 git diff를 안정화한다.
- `scope`는 문서 목적의 상수(`"user"`)다.
- **config가 객체가 아닌 항목**(`"x": null` 같은 수동 편집 실수)은 값을 해석하지 않고 **그대로 보존한다.**
  `read_local_servers`는 `mcpServers` 자체가 dict인지만 검사하고 개별 값은 검사하지 않는다(9장).
  걸러내면 그 이름이 "로컬에서 사라졌다"로 읽혀 레포에서 삭제되는데, 쓰레기 한 줄이 레포에 실리는 것보다
  그 오판이 더 비싸다. 복원 단계에서는 `add-json`으로 재현할 수 없으므로 `unrestorable`로 분류된다(5장).

## 5. 공용 모듈 `lib/mcp_config.py`

`lib/sync_state.py`와 같은 위치·같은 임포트 방식(`sys.path.insert`로 `../../../lib`)을 쓴다.
세 스킬이 MCP를 만지는 **유일한 경로**이며, 파서가 두 벌 존재할 수 없게 만드는 것이 이 모듈의 존재 이유다.

```python
SENTINEL = "<REDACTED>"
SECRET_FIELDS = ("headers", "env")
SCHEMA_VERSION = 2                      # 4장 스키마 v2
BACKUP_RELPATH = "mcp-servers.json"     # 레포 상대경로이자 base 블롭 키
DEFAULT_CLAUDE_JSON = os.path.expanduser("~/.claude.json")

class LocalConfigUnavailable(Exception):
    """~/.claude.json을 읽지 못했다. "서버 0개"와 반드시 구별한다 — 9장."""

def read_local_servers(claude_json_path=None) -> dict[str, dict]
    """~/.claude.json의 top-level mcpServers를 반환한다.
    mcpServers 키가 없으면 {} (서버 0개라는 정상 상태).
    파일이 없거나 JSON 파싱에 실패하면, 그리고 top-level이 객체가 아니거나
    mcpServers 값이 dict가 아니면(null 포함) LocalConfigUnavailable을 던진다.
    PermissionError 등 그 밖의 OSError는 전파한다 — 잡는 주체는 스크립트다(9장)."""

def redact(servers: dict) -> dict
    """headers/env의 값만 SENTINEL로 치환한다. 키 이름과 나머지 필드는 보존한다.
    멱등이며 입력을 변경하지 않는다(deepcopy)."""

def secret_keys(cfg: dict) -> list[tuple[str, str]]
    """[("headers", "CONTEXT7_API_KEY"), ...] — 복원 시 사용자에게 물어볼 항목."""

def parse_backup(data) -> dict[str, dict]
    """바이트/문자열에서 servers 매핑을 읽는다. 깨진 입력은 {}로 degrade한다."""

def parse_base(data) -> dict[str, dict] | None
    """base 블롭 전용. 이력을 신뢰할 수 없으면 None(이력 없음)을 반환한다.
    "이력이 비어 있었다"({})와 "이력을 읽을 수 없다"(None)를 반드시 구별한다 — 9장.
    백업 문서로 알아볼 수 있는 형태(v1 배열, 또는 servers가 dict인 v2 객체)일 때만
    매핑을 돌려준다. data가 None, JSON 파싱 실패, 그리고 구문은 유효하지만 스키마가 아닌
    JSON(null·문자열·숫자·servers가 없거나 dict가 아닌 객체)은 모두 None이다."""

def load_backup(path) -> dict[str, dict]
    """mcp-servers.json을 읽어 servers 매핑을 반환한다. v2 객체와 v1 배열을 모두 지원한다.
    파일이 없으면 {}. (PermissionError 등 그 밖의 OSError는 전파한다.)"""

def dump_backup(servers: dict, path) -> None
    """v2 형식으로 저장한다. indent=2, sort_keys=True로 git diff를 안정화한다."""

def same(a: dict, b: dict) -> bool
    """config 동등 비교. dump_backup과 같은 직렬화 옵션(sort_keys, ensure_ascii=False)으로
    만든 JSON 문자열을 비교하므로 키 순서에 무관하고, 디스크 표현이 같으면 same도 참이다.
    **동등 비교의 유일한 진입점이다.** diff·merge·next_base·restore_plan은 물론 세 스크립트도
    이 함수만 쓴다. 호출부가 == 나 자체 정규화를 다시 만들면 판정이 갈라지는데, 그것이
    이 spec이 애초에 없애려던 "파서 두 벌"과 같은 종류의 드리프트다."""

def diff(local: dict, backed: dict) -> dict
    """{"only_local": [...], "only_repo": [...], "changed": [...]}.
    비교 직전 양쪽에 redact를 적용한다."""

def merge(local: dict, repo: dict, base: dict | None) -> dict
    """키 단위 3-way 병합. 입력에 redact를 내부에서 적용한다(diff와 같은 계약).
    {"servers": {...}, "conflicts": [...], "deleted": [...], "local_stale": [...],
     "repo_ahead": [...], "next_base": {...}}.
    next_base는 7.3의 전진 규칙을 적용한 다음 base다 — 호출부는 판정을 재구현하지 않고
    레포가 그 내용을 갖게 된 뒤 이것을 그대로 기록한다(7.5).
    repo_ahead는 타 기기가 추가·변경한 서버(케이스 2·8) — 보고용이며 `name in local`로 둘을 가른다.
    conflicts에서 케이스 5와 9는 `name in servers`로 구분한다.
    base가 None이면 삭제 없이 합집합으로 degrade한다."""

def next_base(local: dict, base: dict | None, servers: dict) -> dict
    """7.3의 전진 규칙을 적용한 다음 base. merge가 내부에서 쓰고 결과에 담아 반환하지만,
    restore도 같은 규칙으로 base를 갱신해야 하므로 공개 함수다(8.3).
    **입력에 redact를 내부 적용한다 — merge·diff와 같은 계약이다.**
    restore는 read_local_servers()의 원본(비밀 평문)을 넘기게 되는데, 내부 적용이 없으면
    same(레포의 <REDACTED>, 로컬 평문)이 거짓이 되어 비밀을 가진 서버의 base가 전진하지 않고
    (7.3의 불변식이 한 라운드 깨진다), 평문 키가 base 블롭에 새 사본으로 기록된다.
    redact는 멱등이므로 이미 마스킹된 merge 경로에는 영향이 없다."""

def restore_plan(local: dict, backed: dict, base: dict | None) -> dict
    """복원 계획. diff·merge와 마찬가지로 비교 직전 양쪽에 redact를 적용한다.
    {"add": [...], "needs_secret": [...], "unrestorable": [...], "in_sync": [...],
     "local_ahead": [...], "repo_ahead": [...], "both_changed": [...],
     "local_stale": [...], "local_only": [...]}

    R에만 있는 이름(로컬 미설치) — 셋으로 가른다:
      unrestorable  add-json으로 재현할 수 없는 항목. 둘 중 하나면 여기다 —
                    (a) 이름이 CLI 규칙 `^[A-Za-z0-9_-]+$`(영숫자·하이픈·언더스코어)을 어김,
                    (b) config에 command도 없고 url+type(http/sse)도 없음.
                    v1 배열에서 승격된 항목이 정확히 이 형태다(10장).
      needs_secret  복원 가능하지만 secret_keys(cfg)가 비어 있지 않음 → 값을 물어야 한다.
      add           그 밖 — 그대로 등록한다.
    L·R 양쪽에 있는 이름 — same과 base로 넷으로 가른다:
      in_sync       same(L[x], R[x])
      local_ahead   케이스 7. base에 있고 same(R[x], S[x]) — 아직 백업되지 않은 로컬 변경
      repo_ahead    케이스 8. base에 있고 same(L[x], S[x]) — 타 기기가 변경
      both_changed  케이스 9. 그 밖(양쪽 다 S와 다름 / base가 None이거나 그 이름이 base에 없음)
    L에만 있는 이름:
      local_stale   base에 있음 — 케이스 4와 5를 **모두** 담는다.
      local_only    base에 없음 — 케이스 1(로컬 신규). restore는 아무것도 하지 않는다.

    **케이스 7·8·9를 differs 한 버킷으로 뭉치지 않는 이유는 7.7에 있다.** 처방이 서로 다르고,
    특히 케이스 7에 "레포 값 채택"을 제시하면 아직 백업되지 않은 로컬 변경이 파괴된다.
    merge가 7.2 판정표의 7·8·9행에서 이미 같은 조건식을 쓰고 있으므로 그것을 재사용한다 —
    restore_plan이 판정을 새로 만들면 두 곳의 케이스 구분이 갈라진다.

    local_stale이 케이스 5까지 담는 이유: 담지 않으면 backup은 매번 "충돌 — /sync-restore 먼저"라고
    안내하는데 restore가 아무것도 보여주지 않는 탈출구 없는 상태가 된다.
    merge.local_stale(케이스 4만) ⊆ restore_plan.local_stale(케이스 4+5)이다.

    merge와 이름이 겹치는 버킷의 대응 관계:
      merge.repo_ahead 중 `name in local`인 것(케이스 8) == restore_plan.repo_ahead
      merge.repo_ahead 중 그 밖(케이스 2)          == restore_plan의 add / needs_secret / unrestorable
      merge.conflicts 중 `name in servers`인 것(케이스 9) == restore_plan.both_changed
      merge.conflicts 중 그 밖(케이스 5)          ⊆ restore_plan.local_stale"""
```

`diff()`가 **비교 직전 양쪽에 `redact()`를 적용**하는 것이 핵심이다.
이것이 없으면 로컬(평문) vs 레포(마스킹)가 영원히 달라 보여, 지금 Bug #2와 똑같은 미수렴 증상이 재발한다.
`merge`·`next_base`·`restore_plan`도 같은 계약을 따른다 — 네 함수 중 하나만 빠져도 그 함수를 지나는
경로에서만 미수렴이 되살아나므로, "입력을 마스킹해서 넘기라"는 호출부 규약이 아니라 **함수의 계약**으로 둔다.

**config 동등 비교 방식은 `same`으로 확정했다**(구현·테스트 완료). 정규화 후 딕셔너리 비교가 아니라
`json.dumps(sort_keys=True, ensure_ascii=False)` 문자열 비교를 쓴다 — 단순하고 재현 가능하며,
`dump_backup`의 직렬화와 같은 옵션이라 "레포 파일이 같으면 판정도 같다"가 성립한다.

`unrestorable` 판정은 `add`에만 쓰이는 것이 아니다. 케이스 8·9의 "레포 값 채택"도 `add-json`을 거치므로,
레포 값이 `unrestorable`이면 그 서버에는 **채택 선택지를 제시하지 않는다**(8.3).

## 6. 비밀 처리

`headers`와 `env`의 **값만** `"<REDACTED>"`로 치환하고 키 이름은 남긴다.
`settings.json`에서 `enabledPlugins`/`extraKnownMarketplaces`만 화이트리스트로 뽑는 기존 철학과 같은 선택이다.

- 레포에는 `{ "CONTEXT7_API_KEY": "<REDACTED>" }`가 남는다 → 어떤 키가 필요한지는 전달되고 값은 유출되지 않는다.
- 복원 시 `needs_secret`으로 분류하여 사용자에게 값을 묻는다.
- **사용자가 입력을 건너뛰면 그 서버는 등록하지 않는다.** 인증이 깨진 서버를 만들지 않는 편이 낫다.
- 마스킹 대상은 값이 문자열인 경우로 한정하고, 중첩 구조가 오면 통째로 SENTINEL로 치환한다.

**마스킹 범위의 한계**: `headers`와 `env`만 마스킹한다. 일부 서드파티 MCP 서버는
API 키를 `args`(`--api-key=sk-...`)나 `url`의 쿼리스트링으로 전달하는데, 이 경로는 마스킹되지 않는다.
`args`/`url`을 휴리스틱으로 마스킹하면 정상 설정을 망가뜨릴 위험이 더 크므로 범위를 넓히지 않는다.
대신 **백업 레포는 private 권장**이라는 기존 안내를 유지하고, 이 한계를 백업 레포 README에 명시한다(12장).

**결과로 따라오는 성질**: 마스킹 후 비교하므로 **비밀 값만 바뀐 변경은 동기화되지 않는다.**
로컬에서 API 키를 교체해도 backup은 변화를 감지하지 않고 status도 차이를 보고하지 않는다.
비밀은 애초에 동기화 대상이 아니므로 의도된 동작이며, 이 규칙이 없으면 키를 가진 서버가
영구히 "변경됨"으로 보고된다(Bug #2와 같은 미수렴). 이 성질은 `diff`·`merge`·`restore_plan`에
일관되게 적용한다.

## 7. 키 단위 3-way 병합

### 7.1 왜 텍스트 머지가 아닌가

`git merge-file`을 JSON에 적용하면 충돌 마커가 파일 안에 삽입되어 JSON 자체가 깨진다.
따라서 파일 단위가 아니라 **서버 이름 키마다** `sync_state.classify`와 같은 판단을 내린다.

### 7.2 판정표

L = 로컬 user 스코프(redact 적용), R = 레포 `servers`, S = base.

| # | L | R | S | 판정 |
|---|---|---|---|---|
| 1 | 있음 | 없음 | 없음 | 로컬 신규 → 레포에 추가 |
| 2 | 없음 | 있음 | **없음** | 타 기기가 추가 → 보존 |
| 3 | 없음 | 있음 | **있음** | 로컬에서 삭제됨 → 레포에서 제거 |
| 4 | 있음 | 없음 | **있음** (L==S) | 타 기기가 삭제, 로컬은 잔존 → 레포에 재추가하지 않고 `local_stale`로 보고 |
| 5 | 있음 | 없음 | **있음** (L≠S) | 로컬 수정 vs 리모트 삭제 → 충돌 |
| 6 | 있음 | 있음 | — (L==R) | in_sync |
| 7 | 있음 | 있음 | R==S, L≠R | 로컬만 변경 → push |
| 8 | 있음 | 있음 | L==S, R≠S | 타 기기가 변경 → 레포 값 유지 |
| 9 | 있음 | 있음 | 양쪽 ≠ S (S 없음 포함), L≠R | 충돌 → 해당 서버만 건너뜀 |
| 10 | 없음 | 없음 | 있음 | 이미 양쪽에서 사라짐 → 결과에서 제외 (no-op) |

구현은 `set(L) | set(R) | set(S)`를 순회한다. 케이스 10은 사용자가 restore를 거치지 않고
`claude mcp remove`를 직접 실행했을 때 발생하며, base가 다음 갱신에서 자연히 정리된다.

"레포에 있는데 로컬에 없다"(2 vs 3)를 *타 기기 추가* 와 *내 삭제* 로 가르려면 **base가 반드시 필요하다.**
base가 없으면 판별 불가이므로 삭제 없이 합집합으로 degrade한다(첫 도입 시점, 새 기기가 여기 해당).

### 7.3 base 전진 규칙 — 이 설계의 핵심 불변식

> **base[name]은 로컬이 그 값에 동의할 때만 전진한다. 동의하지 않으면 이전 base를 유지한다.**

새로운 발명이 아니다. `update_base.py`가 파일 단위로 이미 지키는 규칙
("push된 파일의 base ← 로컬 내용")을 키 단위로 옮긴 것이다.

**왜 필요한가.** 초기 설계는 "푸시 성공 && `conflicts`·`local_stale` 없음 → base ← 레포 파일 전체"였다.
그런데 케이스 2(타 기기 추가)와 케이스 8(타 기기 변경)의 결과값은 **이 기기의 로컬이 동의한 값이 아니다.**
그걸 base에 기록하면 base가 더 이상 "로컬의 조상"이 아니게 되고,
다음 백업이 `L≠S`를 "로컬이 바뀌었다"로 오독한다.

```
기기 B: L={x}, R={x,z}, S={x}      # z는 다른 기기가 추가한 서버
1회차: z 보존, base ← {x,z}
2회차: L에 z 없음 + S에 z 있음 → 케이스 3 → z가 레포에서 삭제됨
```

새 기기에서 `/sync-restore` 없이 `/sync-backup`을 두 번 실행하면 다른 모든 기기의 서버가
경고 없이 사라진다 — **1.4가 지적한 바로 그 버그가 한 라운드 늦게 재현된다.**
케이스 8도 같은 경로로 타 기기의 변경이 되돌려진다.

| 상황 | base[name] |
|---|---|
| 로컬이 결과값에 동의 (케이스 1·6·7) | 결과값으로 전진 |
| 양쪽에서 사라짐 (케이스 3·10) | base에서 제거 |
| 로컬이 동의하지 않음 (케이스 2·4·5·8·9) | 이전 base 유지 |

`merge`가 `next_base`로 이 매핑을 계산해 반환하므로 호출부는 판정 로직을 재구현하지 않는다.

**부수 효과: 전역 게이트가 불필요해진다.** 케이스 4·5·9는 이름 단위 보존만으로 base가 고정되므로
`conflicts`/`local_stale`이 비었는지와 무관하게 안정적이다. 전역 게이트보다 정밀하다 —
서버 하나가 충돌 중이어도 나머지 서버의 base는 계속 전진한다.

### 7.4 삭제 수렴 — 케이스 4가 안정 상태인 이유

restore는 non-destructive이므로 로컬 서버를 지우지 않는다. 그래서 타 기기가 삭제한 서버가
로컬에 남는다(케이스 4).

> 기기 A·B가 동기화된 상태(레포 `{X, Y}`)에서 A가 X를 지우고 백업한다(케이스 3). 레포는 `{Y}`가 된다.
> 이제 B가 백업하면 B의 로컬에는 X가 남아 있다. 이때 X를 "로컬 신규"로 취급해 레포에 다시 올리면
> A의 삭제가 즉시 취소된다.

7.3의 규칙 아래에서 이 상태는 **안정적이다.** base[X]가 전진하지 않으므로 백업을 몇 번 반복해도
계속 케이스 4로 판정되어 `local_stale`로 보고되고, 되살아나지 않는다.

수렴은 restore에서 사용자가 선택할 때 일어난다. 이때 **"제거하지 않음"에는 서로 다른 두 의미가
있으므로 한 동작으로 뭉치면 안 된다.** "이 기기는 X를 계속 쓴다"(→ 레포에 되돌려야 한다)와
"지금은 판단을 미룬다"(→ 아무것도 바뀌면 안 된다)는 정반대의 결과를 요구한다.
그래서 8.3은 선택지를 셋으로 나누며, 이는 파일 쪽 충돌 해소 UX(백업 채택 / 로컬 유지 / 나중에)와
같은 구조다.

| 선택 | 동작 | 다음 backup | 도달 상태 |
|---|---|---|---|
| **제거** | `claude mcp remove X -s user` | X가 L·R·S 어디에도 없음 | 레포·로컬 모두 X 없음 |
| **유지** | 로컬 그대로 두고 **base에서 X를 제거** | 케이스 1 → X를 레포에 push | 레포·로컬 모두 X 있음 (A의 삭제 취소) |
| **나중에** | 아무것도 하지 않음 | 케이스 4 반복 | 변화 없음, 다시 보고 |

"유지"가 base에서 X를 지우는 것은 **"그 이력은 잊는다"는 명시적 선언**이다.
이 동작이 없으면 케이스 4가 영원히 유지되어 사용자가 X를 레포에 되돌릴 방법이 없다.

세 경로 모두 고정점에 도달하므로 재실행해도 결과가 달라지지 않는다(13장 검증).

### 7.5 base 저장과 갱신 시점

- 위치: `~/.claude/.sync-state/base/mcp-servers.json`. 레포 상대경로 기준이므로
  `sync_state.write_base`/`read_base`를 그대로 재사용한다.
- 저장 내용: **`next_base` 매핑을 스키마 v2로 직렬화한 문서.** 레포 파일 바이트가 아니다 —
  7.3 때문에 base는 레포의 사본이 아니라 "로컬이 동의한 부분"의 파생 문서다.
  읽을 때는 **`parse_base`**를 쓴다. `load_backup`이 아니라 `parse_base`인 이유는 9장에 있다 —
  신뢰할 수 없는 base를 `{}`로 읽으면 "이력이 비어 있었다"로 오인된다.
- **기록 주체는 기존 `update_base.py` 하나뿐이다. 새 스크립트를 만들지 않는다.**
  backup·restore 모두 파생 문서를 **스테이징 디렉토리**에 `mcp-servers.json`이라는 이름으로 쓴 뒤
  `update_base.py <스테이징 디렉토리> mcp-servers.json`을 호출한다.
  `update_base.py`는 `source_root/<rel>`을 읽어 base 블롭에 기록하는 구조이므로 스크립트를 고치지 않고
  계약이 맞고, base를 쓰는 코드 경로가 둘로 갈라지지 않는다(파일 쪽과 같은 규칙을 공유한다).
  - 스테이징 경로는 기존 흐름의 `/tmp/claude-sync-*` 관례를 따라
    `${TMPDIR:-/tmp}/claude-sync-mcp-base/`를 쓴다. 파일 하나가 아니라 디렉토리인 이유는
    `update_base.py`의 첫 인자가 `source_root`이기 때문이고, 그 안의 **파일 이름은 `<rel>` 인자와
    같아야 하므로 반드시 `mcp-servers.json`이다.**
  - `update_base.py "$SYNC_REPO" mcp-servers.json`처럼 **레포를 `source_root`로 넘기면 안 된다.**
    그러면 `base ← 레포 파일 바이트`가 되어 7.3을 정면으로 위반한다 — 케이스 2·8의 값이 base에 실려
    다음 백업이 타 기기의 서버를 삭제하거나 변경을 되돌린다.
- 갱신 시점:
  - backup — `collect_mcp.py`는 커밋 **전에** 실행되므로 직접 base를 쓰지 않는다.
    `merge`가 돌려준 `next_base`를 스테이징 파일로 써 두고, **레포가 실제로 그 내용을 갖게 된 뒤**
    `update_base.py`를 호출한다. "갖게 된 뒤"는 두 경우다 —
    ① 커밋·푸시 성공, ② **커밋할 변경이 없음**(레포가 이미 `next_base`와 정합하다는 뜻이다).
    ②를 빠뜨리면 restore 없이 backup만 하는 기기에서 base가 영원히 부트스트랩되지 않는다.
    그 기기는 `merge(base=None)`의 합집합 degrade에 머물러 **로컬 삭제가 영영 전파되지 않는데**,
    1.4와 7.3이 걱정하는 기기가 정확히 그 기기다.
    푸시가 **실패하면 기록하지 않는다** — 레포가 그 내용을 갖지 않으므로(`update_base.py`와 같은 계약).
  - restore — MCP 단계에서 로컬을 실제로 바꾼 뒤 `~/.claude.json`을 **다시 읽어**
    `next_base(복원 후 로컬, 이전 base, 레포)`를 계산하고, 여기에 두 종류의 override를 적용한 결과를
    같은 방식으로 기록한다(8.3). 사용자가 아무 선택도 하지 않았어도 기록한다 — 무선택은
    "이전 base 유지"로 계산되므로 결과가 달라지지 않는다.
  - status — 읽기 전용이므로 갱신하지 않는다.

### 7.6 충돌과 타 기기 선행의 보고

- **충돌**(케이스 5·9): 해당 서버만 건너뛰고 "`/sync-restore` 먼저 실행"을 안내한다.
  백업 전체를 막지 않는다. 케이스 9는 레포에 이전 값이 남고 케이스 5는 레포에 없으므로,
  호출부는 `name in result["servers"]`로 둘을 구분해 안내한다.
- **케이스 9의 해소 경로는 7.7의 세 선택지다.** restore에서 `both_changed`로 분류되어
  케이스 8과 같은 선택지를 받되, 안내 문구에 "양쪽이 모두 바뀌었다"는 사실을 드러낸다.
  이 문장을 명시하는 이유는 초안에 케이스 9의 처방이 아예 없었기 때문이다 —
  `restore_plan`이 케이스 7·8·9를 `differs` 한 버킷에 뭉쳐 놓은 덕분에 케이스 9가 **우연히**
  선택지를 받고 있었다. 버킷을 나누는 순간(5장) 그 우연이 사라지므로 설계로 못 박는다.
- **타 기기 선행**(케이스 2·8): `repo_ahead`로 보고한다. 파일 단위 `reconcile_backup.py`는
  같은 상황을 `reject`로 막지만 MCP는 레포 값을 유지하고 넘어가므로, 사용자에게 알릴 통로가 필요하다.
  두 케이스는 안내 문구가 다르다(7.7, 8.1) — 케이스 2만 "`/sync-restore`를 실행하면 로컬에 반영됩니다"이고,
  케이스 8은 restore에서 **선택**이 필요하다.
- restore: additive이므로 이미 등록된 서버는 **추가**하지 않지만, 케이스 8·9는 7.7의 선택지를 제시한다.
  케이스 7은 선택지를 제시하지 않는다(7.7).

### 7.7 케이스 7·8·9의 해소 — 한 버킷으로 뭉치면 안 된다

케이스 8(타 기기가 변경, 로컬은 옛 값)은 케이스 4와 대칭인데 초기 설계는 처방을 빠뜨렸다.
`repo_ahead`는 "`/sync-restore`를 실행하면 로컬에 반영됩니다"라고 안내하지만,
restore의 `differs` 버킷은 "건드리지 않고 안내만"이므로 **아무것도 반영되지 않는다.**
사용자는 매 백업마다 같은 안내를 듣고, restore를 실행하면 아무 일도 일어나지 않는다 —
**빠져나갈 수 없는 루프이고 안내문이 사실이 아니다.**

기기 A에서 `args` 버전 핀이나 `url`을 한 줄 고치는 것만으로 기기 B가 이 상태에 빠진다.

7.4와 같은 구조로 세 선택지를 제시한다. 세 경로 모두 고정점에 도달한다.

| 선택 | 동작 | 다음 backup | 도달 상태 |
|---|---|---|---|
| **레포 값 채택** | 레포 값으로 로컬을 교체한다. 비밀이 있으면 **먼저** 값을 받아 채운다. `claude mcp remove` → `claude mcp add-json` 2단계(8.3) | 케이스 6 | 양쪽 레포 값 |
| **로컬 유지** | 로컬 그대로, **`base[x] ← 레포 값`**(그 이력은 잊는다) | R==S, L≠S → 케이스 7 → push | 양쪽 로컬 값 |
| **나중에** | 아무것도 하지 않음 | 케이스 8 반복 | 변화 없음 |

"로컬 유지"에서 base를 **레포 값으로** 옮기는 것이 핵심이다. 케이스 4의 "유지"가 base에서 이름을
*제거*하는 것과 방향은 다르지만, "이력을 잊어 다음 백업이 push하게 만든다"는 의도는 같다.
**이 base 조작이 없으면 "로컬 유지"는 "나중에"와 완전히 같은 결과가 된다** — `next_base`는 로컬이
레포 값에 동의하지 않으므로 이전 base(=로컬 값)를 유지하고, 다음 백업은 다시 `L==S, R≠S`로 케이스 8이다.
표가 약속한 "양쪽 로컬 값"에 영원히 도달하지 못한다. 그래서 8.3은 이것을 **명시적 override**로 적는다.

반대로 **"레포 값 채택"에는 override가 필요 없다.** 채택 후에는 로컬이 레포 값에 동의하므로
`next_base`가 스스로 전진시킨다(단 `next_base`가 입력에 `redact`를 적용해야 성립한다 — 5장).

**"레포 값 채택"은 마스킹된 값을 그대로 쓰면 안 된다.** 레포의 `headers`/`env`는 항상 `<REDACTED>`이므로
그대로 로컬에 쓰면 `headers.K == "<REDACTED>"`인, **인증이 깨진 서버**가 남는다.
6장이 "값 입력을 건너뛰면 그 서버는 등록하지 않는다"로 금지한 바로 그 상태다. 따라서 —

- 채택 대상에 `secret_keys`가 있으면 `needs_secret`과 **같은 흐름으로 사용자에게 값을 받아 채운 뒤** 적용한다.
- 사용자가 입력을 건너뛰면 **채택하지 않고 "나중에"와 동일하게 처리한다**(로컬 불변, base 불변).
- 기존 로컬 비밀을 조용히 이월하지 않는다. 레포 값이 바뀐 이유가 키 교체일 수 있고, 그때 이월은
  "동작하는 것처럼 보이다가 인증에서 실패하는" 더 나쁜 상태를 만든다. 물어보는 편이 정직하다.

**케이스 9(양쪽 변경)도 같은 세 선택지를 쓴다.** 도달 상태와 base 조작이 케이스 8과 동일하다
(채택 → 케이스 6 / 로컬 유지 → 케이스 7 → push / 나중에 → 케이스 9 유지).
다만 안내 문구는 갈라야 한다 — 케이스 8은 "다른 기기가 변경했습니다"이고,
케이스 9는 "**양쪽이 모두 바뀌었습니다. 채택하면 이 기기의 변경이 사라집니다**"라고 밝힌다.

**케이스 7(로컬 앞섬)에는 선택지를 주지 않는다.** `L≠R`이지만 `same(R, S)`이므로 그 차이의 정체는
"아직 백업되지 않은 이 기기의 변경"이다. 여기에 "레포 값 채택"을 제시하면 **사용자의 미백업 변경이
파괴된다.** restore는 `local_ahead`로 보고만 하고 "`/sync-backup`을 실행해 올리세요"를 안내한다.
케이스 7·8·9를 `differs` 한 버킷으로 뭉치면 이 구분이 사라지고 세 케이스가 같은 처방을 받으므로,
`restore_plan`은 셋을 나눈다(5장).

`repo_ahead`의 케이스 2와 8은 **`name in local`로 구분한다**(2는 로컬에 없고, 8은 있다).
케이스 5와 9를 `name in servers`로 구분하는 것과 같은 방식이다. 안내 문구도 갈라야 한다 —
케이스 2는 "restore가 설치합니다", 케이스 8은 "restore에서 선택이 필요합니다".

## 8. 스킬별 동작

### 8.1 backup

`collect_mcp.py`가 담당한다. `claude mcp list` 호출은 완전히 제거하고 stdin도 받지 않는다.

```
사용: collect_mcp.py <레포 경로> <스테이징 디렉토리>

~/.claude.json         → read_local_servers → L      (merge가 내부에서 redact)
<레포>/mcp-servers.json → load_backup       → R
base 블롭               → parse_base         → S
merge(L, R, S)
  → servers   를 dump_backup → <레포>/mcp-servers.json
  → next_base 를 dump_backup → <스테이징 디렉토리>/mcp-servers.json   (아직 base가 아니다)
stdout: {"status": "ok", "conflicts": {"repo_kept": [...], "repo_absent": [...]},
         "deleted": [...], "local_stale": [...],
         "repo_ahead": {"present": [...], "absent": [...]}}
```

`conflicts`를 `repo_kept`(케이스 9, `name in servers`)와 `repo_absent`(케이스 5)로,
`repo_ahead`를 `present`(케이스 8, `name in local`)와 `absent`(케이스 2)로 갈라서 내보내는 이유는,
그 구분이 이미 스크립트 안에 있기 때문이다. 뭉쳐서 내보내면 SKILL.md가 판정을 재구현해야 하고,
그것이 이 spec이 없애려는 드리프트의 형태다.

`collect_mcp.py`는 base를 쓰지 않는다 — 커밋 **전에** 실행되기 때문이다(7.5).
스테이징 파일에 써 두고, 커밋·푸시 단계가 끝난 뒤 SKILL.md가
`update_base.py <스테이징 디렉토리> mcp-servers.json`을 호출해 base로 옮긴다.
그 호출은 **푸시 성공 경로와 "커밋할 변경 없음" 경로 양쪽**에 있어야 한다(7.5).
현재 `sync-backup/SKILL.md`의 base 갱신은 `git commit && git push` 성공 블록 **안에만** 있으므로
그 자리에 그대로 끼워 넣으면 안 된다.

`LocalConfigUnavailable`(또는 `PermissionError` 등 그 밖의 OSError)이면 레포 파일도 스테이징 파일도
건드리지 않고 `{"status": "skipped", "reason": "..."}`를 stdout에 내고 **종료 코드 0**으로 끝낸다(9장).
스테이징 파일을 쓰지 않으므로 `update_base.py`도 호출하지 않는다 — base가 전진하지 않아야 한다.

base 갱신에 별도 게이트는 없다 — 7.3의 이름 단위 전진 규칙이 `next_base` 안에 이미 반영되어 있다.
`conflicts`/`local_stale`이 비었는지로 전역 게이트를 걸지 않는다(7.3의 부수 효과).
기록을 건너뛰는 경우는 **푸시 실패와 MCP 단계 skip 둘뿐이다.**

결과 보고에 포함하고 각각 다음 행동을 안내한다:
- `conflicts.repo_kept`(케이스 9) → "양쪽이 바뀌었습니다. 레포 값을 그대로 두었습니다. `/sync-restore`에서 해소하세요"
- `conflicts.repo_absent`(케이스 5) → "다른 기기가 삭제했는데 이 기기에서 수정했습니다. `/sync-restore` 먼저 실행하세요"
- `local_stale` → "`/sync-restore`에서 로컬을 정리하세요"
- `repo_ahead.absent`(케이스 2) → "다른 기기가 추가했습니다. `/sync-restore`가 이 기기에 설치합니다"
- `repo_ahead.present`(케이스 8) → "다른 기기가 이 서버를 **변경**했습니다. `/sync-restore`에서 채택할지 선택이 필요합니다"
- `deleted` → 이 기기에서 지운 서버가 레포에서도 제거되었음을 알린다

케이스 8에 케이스 2와 같은 문구("restore를 실행하면 반영됩니다")를 쓰면 안 된다.
restore는 케이스 8을 자동 반영하지 않으므로 그 안내는 사실이 아니고, 7.7이 지목한
"빠져나갈 수 없는 루프"의 안내문이 그대로 재현된다. 실제로 필요한 것은 사용자의 선택이다.

### 8.2 status

`compare_mcp.py`가 담당한다. 정규식과 `claude mcp list` 파이프를 모두 제거하고 stdin도 받지 않는다.

```
사용: compare_mcp.py <레포의 mcp-servers.json 경로>

read_local_servers → L,  load_backup(레포) → R
diff(L, R) → {"status": "ok", "only_local": [...], "only_repo": [...], "changed": [...]}
```

`changed`는 이름만이 아니라 config 차이까지 잡는다(예: `command` 변경). base는 갱신하지 않는다.
`LocalConfigUnavailable`이면 `{"status": "skipped", "reason": "..."}`를 내고 종료 코드 0으로 끝낸다 —
읽기 실패를 "서버 0개"로 오인해 레포의 서버를 전부 `only_repo`로 보고하지 않기 위해서다(9장).

**status의 어휘는 파일과 갈라야 한다.** `sync-status/SKILL.md`의 상태 설명
"local_ahead / local_only: 로컬이 앞섬 → backup 시 push"는 파일에는 맞지만 MCP에는 틀리다.
케이스 4(타 기기가 삭제, 로컬 잔존)의 서버도 `only_local`로 나오는데, 그 서버는 backup에서
push되지 않고 `local_stale`로 보고된다(7.4). status는 base를 읽지 않으므로 둘을 구분할 수 없다.
따라서 MCP의 `only_local`은 **"로컬에만 있음 — 신규이거나, 다른 기기가 삭제한 뒤 남은 것일 수 있습니다.
`/sync-backup`이 판정합니다"**로 안내한다. status가 base까지 읽어 케이스를 확정하게 만들지는 않는다 —
읽기 전용 요약이라는 이 스킬의 성격을 유지하는 편이 낫고, 판정의 단일 진입점은 `merge` 하나로 족하다.

### 8.3 restore

`plan_mcp.py`가 계획을 만들고, **선택지를 사용자에게 묻고 CLI를 실행하는 주체는 SKILL.md의 대화 흐름**이다.
비밀 값이 스크립트 인자로 남지 않게 하려는 것과, 7.4·7.7의 세 선택지가 대화형 확인이어야 하는 것이
같은 이유다. 스크립트는 판정과 base 계산만 맡고 로컬 상태를 직접 바꾸지 않는다.

```
사용: plan_mcp.py plan <레포의 mcp-servers.json 경로>

load_backup(레포) → R,  read_local_servers → L,  base 블롭 → parse_base → S
restore_plan(L, R, S) → stdout에 {"status": "ok", ...5장의 버킷 9개}
                        (restore_plan이 내부에서 redact를 적용한다)
```

버킷별 처방:

| 버킷 | 처방 |
|---|---|
| `add` | `claude mcp add-json <name> '<json>' --scope user` |
| `needs_secret` | 사용자에게 값을 물어 채운 뒤 `add-json`. 건너뛰면 등록하지 않는다(6장) |
| `unrestorable` | 등록을 **시도하지 않고** 한 번만 안내한다(10장). 실패 건수로 세지 않는다 |
| `in_sync` | 아무것도 하지 않는다 |
| `local_only`(케이스 1) | 보고만 — "다음 `/sync-backup`에서 레포로 올라갑니다" |
| `local_ahead`(케이스 7) | 보고만 — "이 기기의 변경이 아직 백업되지 않았습니다. `/sync-backup`을 실행해 올리세요". **선택지를 주지 않는다**(7.7) |
| `repo_ahead`(케이스 8) | 7.7의 세 선택지 |
| `both_changed`(케이스 9) | 7.7의 세 선택지 + "양쪽이 모두 바뀌었습니다" 안내 |
| `local_stale`(케이스 4·5) | 7.4의 세 선택지. 제거는 `claude mcp remove <name> -s user` |

`local_stale`은 L에 있고 R에 없으며 S에 있는 서버로, **케이스 4와 5를 모두 담는다.**
`merge.local_stale`(케이스 4만)보다 넓다 — 케이스 5까지 담지 않으면 backup은 매번
"충돌 — `/sync-restore` 먼저"라고 안내하는데 restore가 아무것도 보여주지 않는
**탈출구 없는 상태**가 된다. 두 경우는 안내 문구로 구분한다
(4 = "타 기기가 삭제함", 5 = "타 기기가 삭제했고 이 기기에서 수정함").
세 선택지의 의미와 도달 상태는 7.4의 표를 따른다.
제거 명령은 `claude mcp get`이 안내하는 형식(`claude mcp remove <name> -s user`)을 그대로 쓴다.

**"유지"가 base에서 이름을 제거하는 것이 핵심이다.** 7.3의 전진 규칙 아래에서 케이스 4는
안정 상태이므로, base를 건드리지 않으면 사용자가 그 서버를 레포에 되돌릴 방법이 없다.

**케이스 8·9의 "레포 값 채택" 절차** — 레포 값은 항상 마스킹돼 있고 `add-json`은 기존 이름을
덮어쓰지 못하므로, 한 줄 명령이 아니라 순서가 정해진 다섯 단계다.

```
1. 레포 값이 unrestorable이면 채택 선택지를 제시하지 않는다(5장).
2. 레포 값에 secret_keys가 있으면 **먼저** 사용자에게 값을 물어 넣을 JSON을 완성한다.
   건너뛰면 여기서 중단하고 "나중에"와 동일하게 처리한다(로컬 불변, base 불변).
3. claude mcp remove <name> -s user
4. claude mcp add-json <name> '<완성된 JSON>' --scope user
5. 4가 실패하면 **서버가 로컬에서 사라진 상태로 남는다.**
```

3·4의 순서는 실측에서 나온 것이다 — `add-json`은 이미 있는 이름에 대해
`MCP server <name> already exists in local config`로 exit 1이며 덮어쓰지 않는다.
JSON 완성을 3보다 **앞에** 두는 이유도 같다. remove 뒤에 값을 묻다가 사용자가 중단하면
아무것도 채택되지 않은 채 서버만 사라진다. 5의 실패는 크게 경고하고, **넣으려던 JSON을 그대로
보여주어** 사용자가 직접 다시 등록할 수 있게 한다. 이때 base는 건드리지 않는다.

**base 갱신** — 로컬을 실제로 바꾼 뒤 `~/.claude.json`을 다시 읽어 계산한다. 한 줄이 아니라 다섯 단계다.

```
사용: plan_mcp.py apply-base <레포의 mcp-servers.json 경로> <스테이징 디렉토리> <선택 결과 JSON 경로>

① B ← next_base(복원 후 로컬, 이전 base, 레포)      # next_base가 입력에 redact를 적용한다(5장)
② 케이스 4·5에서 "유지"를 고른 이름 x  →  B에서 x를 **삭제**      (7.4 — 그 이력은 잊는다)
③ 케이스 8·9에서 "로컬 유지"를 고른 이름 x  →  B[x] ← 레포 값     (7.7 — 그 이력은 잊는다)
④ B를 <스테이징 디렉토리>/mcp-servers.json 으로 dump_backup
⑤ SKILL.md가 update_base.py <스테이징 디렉토리> mcp-servers.json 호출  (7.5)
```

선택 결과 JSON은 SKILL.md가 대화에서 받은 답을 그대로 옮긴 파일이며, 필요한 것은 **이름과 선택뿐**이다:

```json
{"keep_stale": ["X", ...], "keep_local": ["Y", ...]}
```

`keep_stale`은 케이스 4·5에서 "유지"를 고른 이름, `keep_local`은 케이스 8·9에서 "로컬 유지"를 고른
이름이다. 나머지 선택(제거·채택·나중에)은 여기에 적지 않는다 — base override가 필요 없기 때문이다.
비밀 값은 이 파일에 **절대 담기지 않는다.** 그래서 스크립트 인자로 안전하게 넘길 수 있다.

**override 두 개를 빠뜨리면 두 종류의 "유지"가 모두 고정점에 도달하지 못한다.**
`next_base`는 로컬이 동의하지 않은 이름의 base를 **이전 값으로 유지**하므로, ②가 없으면 케이스 4가,
③이 없으면 케이스 8이 다음 백업에서 그대로 반복된다 — "유지"와 "나중에"가 구별되지 않고,
7.4·7.7이 없애려던 "빠져나갈 수 없는 루프"가 절차 단계에서 되살아난다.
반대로 **"레포 값 채택"과 "제거"에는 override가 없다.** 채택 후에는 로컬이 레포 값에 동의하므로 ①이
스스로 전진시키고, 제거 후에는 이름이 L·R 어디에도 없으므로 ①이 스스로 base에서 지운다.
`next_base`가 이미 하는 일을 override로 중복하지 않는 것이 규칙이다 —
**override는 "사용자가 이력을 잊기로 선언한" 두 경우에만 쓴다.**

**L에 `redact`를 적용한 뒤 비교하는 것이 필수다.** 로컬에는 실제 API 키가, 레포에는
`"<REDACTED>"`가 들어 있으므로 원본끼리 비교하면 비밀을 가진 서버가 **매번 차이로 보고된다**
— Bug #2와 같은 종류의 영구 미수렴이다. `restore_plan`과 `next_base`가 `diff`·`merge`와 같은 계약으로
내부에서 적용하므로(5장) 호출부는 원본을 그대로 넘겨도 된다.

`claude mcp add-json <name> <json> --scope user`를 쓴다. stdio·http를 모두 받고
`command`/`args`/`env`/`headers`를 그대로 전달한다. 스코프 기본값이 `local`이므로
`--scope user`(또는 `-s user`)를 **반드시** 붙인다. 기존 SKILL.md의
`claude mcp add <name> <url> --transport ...`는 stdio 복원이 불가능하다.

**실측으로 확인한 두 가지 제약이 위 절차를 규정한다.**
- **이름은 영숫자·하이픈·언더스코어만 허용된다.**
  어기면 `Invalid name ... Names can only contain letters, numbers, hyphens, and underscores.`로 exit 1이다.
  공백이나 점이 든 이름은 **인용해도 등록되지 않는다.** v1 배열에서 승격된 `claude.ai Notion` 같은 항목이
  정확히 이 형태이므로, 그런 이름을 만나면 **오류로 중단하지 말고 건너뛰고 보고한다**(`unrestorable`, 10장).
  마이그레이션 직후 restore가 매번 여러 건의 "실패"를 뱉지 않게 하는 것이 목적이다.
- **기존 이름을 덮어쓸 수 없다.** `MCP server <name> already exists in local config`로 exit 1이다.
  값을 바꾸려면 `remove` → `add-json` 2단계이며, 그 사이가 위험 구간이라 JSON을 미리 완성해 둔다.

`add-json` 하나가 실패해도 나머지 서버는 계속 진행한다(9장). 마지막에 실패 목록을 모아 보고한다.

## 9. 에러 처리 & 안전장치

가장 위험한 지점은 7.2의 삭제 판정이다. `~/.claude.json`을 일시적으로 읽지 못해 L이 빈 값이 되면
레포의 서버가 전부 삭제될 수 있다. 따라서 두 경우를 **엄격히 구분한다**.

| 상황 | 처리 |
|---|---|
| `mcpServers` 키 없음 | `{}` 반환 — 정상적인 "서버 0개". 삭제 판정 수행 |
| `~/.claude.json` 없음 / JSON 파싱 실패 | `LocalConfigUnavailable` 예외 → **MCP 단계 전체를 건너뜀.** 삭제 판정을 하지 않음 |
| **top-level이 객체가 아님 / `mcpServers` 값이 dict가 아님(`null` 포함)** | `LocalConfigUnavailable` → MCP 단계 건너뜀. **삭제 오판을 막는 핵심 안전장치다** — `null`을 "서버 0개"로 읽으면 레포의 서버가 전부 케이스 3으로 판정되어 사라진다 |
| **`PermissionError` 등 그 밖의 `OSError`** | 모듈은 **전파한다**(의도적). 잡는 주체는 **스크립트**다 — `collect_mcp.py`/`compare_mcp.py`/`plan_mcp.py`가 잡아 skip으로 보고한다. 스크립트가 traceback으로 죽으면 SKILL.md 흐름 전체가 중단된다 |
| 레포 `mcp-servers.json` 없음 | `{}` — 첫 백업으로 간주 |
| base 없음 | 삭제 없이 합집합 degrade |
| 푸시 실패 | base를 전진시키지 않는다. 레포가 실제로 그 내용을 갖지 않으므로 |
| **base 블롭을 신뢰할 수 없음** | `parse_base`가 `None` 반환 → base 없음과 동일하게 합집합 degrade. JSON 파싱 실패뿐 아니라 **구문은 유효하지만 백업 문서가 아닌 경우**(`null`, 문자열, 숫자, `servers`가 없거나 dict가 아닌 객체)도 포함한다. `{}`로 읽어 "이력이 비어 있었다"로 오인하지 않는다 |
| `add-json` 실패 | 해당 서버만 실패로 기록하고 나머지를 계속 진행. 단 "레포 값 채택"의 `remove` **이후** 실패는 서버가 로컬에서 사라진 상태이므로 크게 경고하고 JSON을 보여준다(8.3) |
| **이름 규칙 위반 / 재현 불가 config** | `unrestorable` — 시도하지 않고 한 번만 안내한다. 실패 건수로 세지 않는다(10장) |

**세 스크립트의 출력·종료 코드 계약을 하나로 맞춘다.**
결과는 stdout에 JSON 한 덩이로 내고 `"status"`는 `"ok"` 또는 `"skipped"`(+ `"reason"`)이며,
사람이 읽을 메시지는 stderr로 낸다. **MCP 단계의 실패로는 종료 코드 0을 유지한다.**
0이 아닌 코드는 인자 개수가 틀린 경우처럼 호출부가 잘못한 때만 쓴다.
"MCP 단계 실패가 backup·restore 전체를 실패시키지 않는다"는 원칙을 종료 코드로 표현한 것이며,
SKILL.md는 `status` 필드 하나만 보고 분기하면 된다. 파일 동기화는 그대로 진행한다.
`skipped`일 때 backup은 레포의 `mcp-servers.json`을 **손대지 않고** base도 전진시키지 않는다(8.1).

## 10. 마이그레이션 & 하위호환

- `load_backup`은 v1 배열(`[{name, url, type}, ...]`)을 읽어 `{name: {...}}`로 승격한다.
  v1에는 복원용 필드가 없으므로 이름 비교까지만 유효하다.
- **v1 승격 항목은 복원에서 제외한다.** `restore_plan`이 `unrestorable`로 분류해 `add-json`을
  시도조차 하지 않는다(5장). 두 가지 이유가 겹친다 — v1 config는 `command`도 `url`+`type`(http/sse)도
  아니라서 `add-json '{"url":"npx ...","type":"stdio"}'`가 스키마 불일치로 exit 1이고,
  `claude.ai *` 7개는 이름 규칙(영숫자·하이픈·언더스코어)까지 어긴다.
  제외하지 않으면 **마이그레이션 직후 restore가 매번 최대 10건의 실패를 보고한다** — v2로 승격된
  백업이 올라가기 전까지 계속. 안내는 "이 항목들은 옛 형식이라 복원할 수 없습니다"로 **한 번만** 낸다.
- 첫 백업에서 v2로 승격된다. v1 항목 중 로컬 user 스코프에 없는 이름(`claude.ai *` 등)은
  base가 없으므로 삭제되지 않고 그대로 보존된다. 사용자가 원하면 수동으로 정리한다.
- **역호환은 없다.** 구버전 `compare_mcp.py`는 `[s["name"] for s in backed]`로 배열을 가정하므로
  v2 객체를 만나면 `TypeError`로 죽는다. 따라서 MAJOR 버전 상승(2.0.0 → 3.0.0)이 필요하다.

## 11. 영향 파일 요약

| 파일 | 변경 |
|---|---|
| `plugins/claude-sync/lib/mcp_config.py` | 5장 API 중 `restore_plan`을 뺀 전부가 구현·테스트 완료. 남은 것 ① **`restore_plan` 신설**(5장 버킷 9개), ② **`next_base`에 `redact` 내부 적용**(5장 계약 — `merge`·`diff`와 대칭. 현 코드는 적용하지 않아 restore가 원본 로컬을 넘기면 base가 전진하지 않는다) |
| `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py` | **삭제** (다른 참조 없음) |
| `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py` | **신설** — 8.1. 레포 경로와 스테이징 디렉토리를 인자로 받고 stdin을 받지 않는다 |
| `plugins/claude-sync/skills/sync-backup/scripts/update_base.py` | **변경 없음** — 스테이징 디렉토리를 `source_root`로 받아 그대로 재사용한다(7.5). base를 기록하는 **유일한 주체**이며, 이 일을 위한 새 스크립트를 만들지 않는다 |
| `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py` | 정규식·stdin 제거, 레포 경로 인자 + `mcp_config.diff()` 호출로 축소 (8.2) |
| `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py` | **신설** — `plan`(계획 JSON)과 `apply-base`(override 적용 후 스테이징 기록) 두 모드 (8.3) |
| `plugins/claude-sync/skills/sync-backup/SKILL.md` | 6단계 재작성, 동기화 대상 표 정정(12장), 10·11단계에 MCP base 스테이징 → `update_base.py` 호출 추가. **"커밋할 변경 없음" 경로에도 호출이 있어야 하므로** 현재의 `git commit && git push` 성공 블록 안에만 넣으면 안 된다(7.5) |
| `plugins/claude-sync/skills/sync-status/SKILL.md` | `claude mcp list` 파이프 제거, 상태 어휘 설명 정정(8.2, 12장) |
| `plugins/claude-sync/skills/sync-restore/SKILL.md` | 6단계를 `add-json` 기반으로 재작성. 7.4·7.7의 세 선택지 대화, 비밀 입력, `remove`→`add-json` 2단계와 실패 경고, `apply-base` + `update_base.py` 호출 |
| `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md` / `.ko.md` | `mcp-servers.json` 설명 갱신 (12장) |
| `plugins/claude-sync/tests/test_mcp_config.py` | 현재 99개 통과. `restore_plan` 버킷 9개와 `next_base`의 redact 계약 회귀를 추가한다 |
| `README.md` / `README.ko.md` | 12장 |
| `.claude-plugin/marketplace.json`, `plugins/claude-sync/.claude-plugin/plugin.json` | 2.0.0 → 3.0.0 |

## 12. 문서 정정

동기화 대상 표는 **다섯 곳**에 흩어져 있다 — `README.md`, `README.ko.md`,
`skills/sync-backup/scripts/backup-readme.md`, `backup-readme.ko.md`,
`skills/sync-backup/SKILL.md`. 한 곳만 고치면 나머지 넷이 계속 옛 서술을 말한다.

1. 동기화 대상 표의 `claude mcp list → mcp-servers.json | MCP 서버 이름과 URL`을
   `~/.claude.json (user 스코프) → mcp-servers.json | MCP 서버 설정 (비밀 값은 마스킹)`으로 바꾼다.
   백업 레포 README 두 곳의 `mcp-servers.json — MCP 서버 목록 (이름, URL, 타입)`도 함께 고친다.
2. 백업 대상에서 제외되는 것(계정 커넥터·플러그인 제공·project/local 스코프)과 그 이유를 명시한다.
3. `mcp-servers.json`이 3-way 병합 대상이 되었음을 명시한다.
4. **`plugins.json`은 여전히 매 백업마다 통째로 덮어쓰이며 reconcile 대상이 아님을 명시한다.**
   이번에 고치지 않으므로 사실대로 남긴다. `README.ko.md`의 "로컬 파일은 절대 자동으로 덮어쓰지 않습니다"에
   이 예외를 붙인다.
5. 비밀 마스킹 정책과, 복원 시 값 입력이 필요하다는 점을 백업 레포 README에 적는다.
   `headers`/`env`만 마스킹하고 `args`/`url`에 든 키는 마스킹되지 않는다는 한계(6장)도 함께 적는다.
6. `sync-status/SKILL.md`의 상태 어휘 설명 "local_ahead / local_only: 로컬이 앞섬 → backup 시 push"는
   **MCP 서버에는 적용되지 않는다.** 케이스 4의 잔존 서버도 `only_local`로 보이지만 push되지 않는다.
   MCP 항목의 안내를 8.2의 문구로 따로 적는다.
7. 케이스 4·8은 restore에서 사용자가 실제로 마주치는 화면이므로, `README`의 `/sync-restore` 설명에
   "삭제·변경이 충돌하면 서버마다 물어봅니다(제거/유지/나중에, 레포 값 채택/로컬 유지/나중에)"를 한 줄 넣는다.
   물어본다는 사실을 미리 알려 두는 편이, 처음 보는 사용자가 임의로 고르는 것을 줄인다.

## 13. 검증 방법

이 장은 **완료 정의**다. 여기 적힌 시나리오가 전부 통과해야 구현이 끝난 것으로 본다.

pytest가 현재 환경에 설치되어 있지 않아 기존 `tests/`도 실행 불가 상태다.
`uv`가 있으므로 `uv run --with pytest pytest plugins/claude-sync/tests`로 실행한다.

**단위 테스트 (`test_mcp_config.py`)**
- 공백이 포함된 `command`(safari)가 온전히 보존된다 — Bug #1 회귀.
- http 서버의 `type`/`url`/`headers`가 보존되고, 값은 마스킹되며 키 이름은 남는다 — Bug #3·#4 회귀.
- `diff`: 로컬 평문과 레포 마스킹이 `in_sync`로 수렴한다 — Bug #2 및 마스킹 함정 회귀.
- `diff`: `command` 변경이 `changed`로 잡힌다.
- `merge`: 7.2 판정표 10줄 각각.
- `merge`: base가 없으면 삭제하지 않고 합집합이 된다.
- `merge`: 케이스 4에서 서버가 레포에 재추가되지 않고 `local_stale`로 보고된다.
- **순환 정합성**: 케이스 4 상태에서 `merge`의 `next_base`를 다음 라운드의 base로 삼아 다시 `merge`해도
  서버가 되살아나지 않고 같은 판정(`local_stale`)에 머문다 — 7.3 회귀.
  (base를 갱신하지 않는 것이 아니라, **갱신해도** 전진하지 않는다는 것이 7.3의 요지다.)
- `restore_plan`: `local_stale` 분류(케이스 4와 5를 모두 담는다).
- `restore_plan`: 로컬에 실제 비밀이 있고 레포가 `<REDACTED>`일 때 차이로 보고되지 않고 `in_sync`다
  — 영구 미수렴 회귀.
- `restore_plan`: `needs_secret` 분류.
- **`restore_plan`: 케이스 7·8·9가 각각 `local_ahead`/`repo_ahead`/`both_changed`로 갈린다** —
  한 버킷으로 뭉치면 케이스 7에 "레포 값 채택"이 제시되어 미백업 로컬 변경이 파괴된다.
- **`restore_plan`: v1 승격 항목과 이름 규칙 위반이 `unrestorable`로 빠지고 `add`에 들어가지 않는다.**
- **`next_base`: 비밀이 평문인 로컬을 그대로 넘겨도 마스킹된 레포와 동등으로 판정되어 base가 전진한다**
  — `redact` 내부 적용 계약 회귀.
- `read_local_servers`: `mcpServers` 없음 → `{}`, 파일 없음/깨짐/`mcpServers`가 dict 아님 → 예외.
- **안전장치**: `LocalConfigUnavailable` 발생 시 레포 servers가 보존된다.
- `load_backup`: v1 배열 하위호환.

**멱등성 / 수렴 (7.4 세 경로)** — `merge`를 반복 적용해 고정점을 확인한다.
각 경로마다 backup을 3회 연속 적용했을 때 2회차부터 레포 내용과 보고가 변하지 않아야 한다.

| 시나리오 | 기대 |
|---|---|
| 정리 없이 backup 반복 | 매회 `local_stale=[X]`, 레포 불변, **base[X]가 전진하지 않음**(다른 이름의 base는 정상 전진) |
| restore "제거" 후 backup | `local_stale` 비고 레포·로컬 모두 X 없음, 이후 불변 |
| restore "유지" 후 backup | 1회차에 X가 레포로 복귀, 이후 불변 |
| restore "나중에" 후 backup | 케이스 4 유지, 레포 불변, 되살아나지 않음 |
| 케이스 9 충돌 상태로 backup 반복 | 매회 `conflicts=[Z]`, 레포는 R 유지, **base[Z] 고정** |
| 케이스 5 충돌 상태로 backup 반복 | 매회 `conflicts=[X]`, 레포에 X 없음, **base[X] 고정** |
| 혼합(충돌 1 + 정상 1)으로 backup 반복 | 충돌 이름의 base만 고정되고 **정상 서버의 base는 전진한다** |
| 케이스 2(타 기기 추가) 상태로 backup 2회 | 2회차에도 그 서버가 레포에 남는다 |
| 케이스 8(타 기기 변경) 상태로 backup 2회 | 2회차에도 레포 값이 유지된다(로컬 값으로 되돌아가지 않는다) |
| base=None 새 기기가 backup 2회 | 2회차에 남의 서버가 `deleted`되지 않는다 |

이전 설계에서는 전역 게이트(`conflicts`/`local_stale`이 비었을 때만 base 갱신)가 앞의 두 회귀를
막았다. 7.3의 이름 단위 전진 규칙이 같은 방어를 **서버별로** 제공하므로 게이트는 제거했다 —
위 줄들은 그 대체가 실제로 작동하는지 검증한다. 마지막 네 줄은 게이트가 아예 막지 못했던
회귀(케이스 2·8·base=None)를 덮는다. **게이트를 되살리는 구현은 이 검증을 통과하더라도
정확도가 떨어지므로(충돌 하나가 전체 base를 동결한다) 받아들이지 않는다.**

**해소 경로 — backup과 restore를 교대로 적용한다**

위 표 열 줄은 전부 *backup 반복*이다. 사용자가 7.4·7.7의 선택지를 고른 뒤 무슨 일이 일어나는지는
backup만 반복해서는 드러나지 않는다. 실제로 **8.3의 base override 누락**(케이스 8의 "로컬 유지"가
"나중에"와 구별되지 않는 결함)은 위 표를 전부 통과했다. 표가 잡지 못한 이유가 교대 시나리오의
부재였으므로, 아래를 완료 정의에 포함한다.

| 시나리오 | 기대 |
|---|---|
| 케이스 8 → restore "레포 값 채택" → backup | 로컬·레포·base 모두 레포 값, 이후 `repo_ahead` 보고 없음 |
| 케이스 8 → restore "로컬 유지" → backup | 1회차에 로컬 값이 레포로 push(케이스 7 경유), 이후 불변. **"나중에"와 결과가 달라야 한다** |
| 케이스 8 → restore "나중에" → backup | 케이스 8 유지, 레포 값 불변, 다시 보고 |
| 케이스 9 → 세 선택지 각각 → backup | 채택 → in_sync / 로컬 유지 → 케이스 7 → push / 나중에 → 케이스 9 유지 |
| 케이스 7 상태에서 restore | 로컬이 바뀌지 않는다. 선택지가 제시되지 않고 `local_ahead`로만 보고된다 |
| 비밀 있는 서버의 케이스 8에서 "채택" 중 입력 건너뜀 | 로컬 불변, base 불변. `<REDACTED>`가 로컬 `headers`/`env`에 기록되지 않는다 |
| backup→restore→backup→restore **2주기**(무선택) | 2주기째의 레포·base·보고가 1주기째와 완전히 같다 |
| 기기 A·B 교대 2주기 (A가 삭제, B가 "유지") | X가 레포로 복귀한 뒤 안정. 이후 주기에서 부활·소멸이 반복되지 않는다 |
| **마이그레이션(v1 레포) 후 첫 restore** | v1 승격 항목이 `unrestorable`로 **한 번만** 안내되고 `add-json` 실패가 0건이다 |
| 커밋할 변경이 없는 backup | base가 기록된다(부트스트랩). 그 뒤 로컬에서 서버를 지우면 다음 backup이 `deleted`로 전파한다 |
| 푸시가 실패한 backup | base가 기록되지 않는다 |
| MCP 단계가 `skipped`인 backup | 레포 `mcp-servers.json`이 변하지 않고 base도 전진하지 않으며, **파일 동기화는 정상 완료된다** |

**통합 시나리오**
- 실제 `~/.claude.json`으로 백업 → user 스코프 3개가 전부 기록되고 `claude.ai *`는 없다.
- 백업 직후 `/sync-status`가 "MCP 서버: 동일"을 보고한다 — 미수렴 증상 해소 확인.
- 프로젝트 디렉토리에서 백업해도 local 스코프 서버가 섞이지 않는다 — Bug #5 확인.
- 레포에만 있는 서버가 `add-json`으로 등록된다(테스트용 임시 서버로 확인 후 `claude mcp remove`).
- 기기 A에서 서버를 지우고 백업 → 기기 B에서 백업 시 되살아나지 않고 `local_stale`로 보고된다.

## 14. 배포 & CC 인식 (완성 조건)

1. `/Users/bran/personal/claude-sync`에서 변경 적용.
2. 13장 검증 통과.
3. **사용자 승인 후** `origin`에 커밋·푸시. (외부 동작 — 푸시 직전 확인.)
4. `claude plugin marketplace update claude-sync` → `claude plugin update claude-sync`.
5. 캐시 디렉토리가 `3.0.0` 신코드로 교체됐는지 확인.

## 15. 오픈 이슈 (구현 계획에서 확정)

**구현을 막지 않는 항목만 남겼다.** base 기록의 주체·경로·시점(7.5), 케이스 7·8·9의 분리(5장·7.7),
채택 시 비밀 처리(7.7), 세 스크립트의 인자·출력·종료 코드(8장·9장), v1 항목의 복원 배제(10장)는
모두 본문에서 확정했다. 아래는 그 뒤에 남는 판단들이다.

- **비밀 값이 `add-json`의 argv에 실린다.** `claude mcp add-json [options] <name> <json>`은 JSON을
  위치 인자로만 받고 stdin·파일 입력 경로가 없다(`--client-secret`은 OAuth client secret 전용이다).
  프로세스 목록과 에이전트 트랜스크립트에 값이 남는 것을 **감수한다** — 현재 CLI에 대안이 없다.
  완화책은 두 가지다: 값을 묻기 전에 이 사실을 사용자에게 고지하고(8.3), CLI가 stdin/파일 입력을
  추가하면 즉시 그쪽으로 옮긴다. 값을 묻는 주체는 SKILL.md 대화로 확정했다(8.3) —
  스크립트 인자로 받으면 argv 노출이 한 겹 더 늘어난다.
- `plugins.json`의 동일 결함을 후속 과제로 등록할지.
- `SECRET_FIELDS` 범위 확대 여부. (현 안: `headers`/`env`만. `args`/`url`에 키를 넣는 서버는
  실사용 조사 후 판단하며, 그때까지는 문서화된 한계로 둔다.)
- `base=None`(첫 백업) 분기가 `repo_ahead`를 채우지 않고, 같은 이름의 값이 다르면 보고 없이
  로컬 승으로 확정된다. 첫 백업 한정이라 Minor로 두되, 8.1의 결과 보고에 "첫 백업이라
  이력이 없어 로컬 값을 채택했습니다"를 넣을지 검토한다.
- 케이스 2에 "이 기기에는 설치하지 않겠다"를 선언할 수단이 없다(현재는 매번 `repo_ahead`로 보고된다).
  `.syncignore`류의 제외 목록이 필요한지는 실사용 후 판단한다.
- `local_stale`이 오래 방치될 때의 처리. (현 안: 백업할 때마다 보고만 하고 강제하지 않는다.
  base가 갱신되지 않는 상태가 지속되지만, 나머지 서버는 in_sync이므로 실질적 손해가 없다.)
- 케이스 4에서 다른 기기가 "유지"를 고르면, 그 서버를 지웠던 기기에는 케이스 2(`add`)로 다시 나타난다.
  사용자 눈에는 "지운 서버가 돌아왔다"로 보이지만 **데이터만으로는 신규 서버와 구별할 수 없다** —
  그 기기의 base에서 이미 이름이 지워졌기 때문이다(케이스 3). 출처를 알리려면 레포 문서에 흔적을
  남기는 별도 장치가 필요하므로 이번 범위 밖으로 둔다.
