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

### 비목표 (이번 범위 밖)
- `plugins.json`의 덮어쓰기 문제. 같은 구조적 결함이 있으나 이번엔 고치지 않고 **문서에 사실대로 명시**한다.
- project 스코프(`.mcp.json`) 및 local 스코프 서버 동기화. 프로젝트 레포에 속하므로 user 설정 동기화 대상이 아니다.
- `claude.ai *` 커넥터 동기화. 계정 레벨이라 기기 설정으로 재현할 수 없다.
- 비밀 값 자체의 동기화(볼트 연동 등).
- **파일**의 삭제 전파. 선행 설계의 비목표를 그대로 유지한다.
  MCP 서버는 이번에 삭제 전파를 도입하되, 로컬 제거는 restore에서 사용자 확인을 거쳐야 완결된다(7.3, 8.3).

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

## 5. 공용 모듈 `lib/mcp_config.py`

`lib/sync_state.py`와 같은 위치·같은 임포트 방식(`sys.path.insert`로 `../../../lib`)을 쓴다.
세 스킬이 MCP를 만지는 **유일한 경로**이며, 파서가 두 벌 존재할 수 없게 만드는 것이 이 모듈의 존재 이유다.

```python
SENTINEL = "<REDACTED>"
SECRET_FIELDS = ("headers", "env")

def read_local_servers(claude_json_path=None) -> dict[str, dict]
    """~/.claude.json의 top-level mcpServers를 반환한다.
    mcpServers 키가 없으면 {} (서버 0개라는 정상 상태).
    파일이 없거나 JSON 파싱에 실패하면 LocalConfigUnavailable을 던진다."""

def redact(servers: dict) -> dict
    """headers/env의 값만 SENTINEL로 치환한다. 키 이름과 나머지 필드는 보존한다."""

def secret_keys(cfg: dict) -> list[tuple[str, str]]
    """[("headers", "CONTEXT7_API_KEY"), ...] — 복원 시 사용자에게 물어볼 항목."""

def load_backup(path) -> dict[str, dict]
    """mcp-servers.json을 읽어 servers 매핑을 반환한다. v2 객체와 v1 배열을 모두 지원한다.
    파일이 없으면 {}."""

def dump_backup(servers: dict, path) -> None
    """v2 형식으로 저장한다."""

def diff(local: dict, backed: dict) -> dict
    """{"only_local": [...], "only_repo": [...], "changed": [...]}.
    비교 직전 양쪽에 redact를 적용한다."""

def merge(local: dict, repo: dict, base: dict | None) -> dict
    """키 단위 3-way 병합.
    {"servers": {...}, "conflicts": [...], "deleted": [...], "local_stale": [...]}.
    local_stale이 비어 있지 않으면 호출부는 base를 갱신하지 않는다(7.3).
    base가 None이면 삭제 없이 합집합으로 degrade한다."""

def restore_plan(local: dict, backed: dict, base: dict | None) -> dict
    """{"add": [...], "needs_secret": [...], "in_sync": [...],
        "differs": [...], "local_stale": [...]}.
    local_stale은 로컬에 있고 레포에 없으며 base에 있는 서버 — 타 기기의 삭제(7.3)."""
```

`diff()`가 **비교 직전 양쪽에 `redact()`를 적용**하는 것이 핵심이다.
이것이 없으면 로컬(평문) vs 레포(마스킹)가 영원히 달라 보여, 지금 Bug #2와 똑같은 미수렴 증상이 재발한다.

## 6. 비밀 처리

`headers`와 `env`의 **값만** `"<REDACTED>"`로 치환하고 키 이름은 남긴다.
`settings.json`에서 `enabledPlugins`/`extraKnownMarketplaces`만 화이트리스트로 뽑는 기존 철학과 같은 선택이다.

- 레포에는 `{ "CONTEXT7_API_KEY": "<REDACTED>" }`가 남는다 → 어떤 키가 필요한지는 전달되고 값은 유출되지 않는다.
- 복원 시 `needs_secret`으로 분류하여 사용자에게 값을 묻는다.
- **사용자가 입력을 건너뛰면 그 서버는 등록하지 않는다.** 인증이 깨진 서버를 만들지 않는 편이 낫다.
- 마스킹 대상은 값이 문자열인 경우로 한정하고, 중첩 구조가 오면 통째로 SENTINEL로 치환한다.

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

"레포에 있는데 로컬에 없다"(2 vs 3)를 *타 기기 추가* 와 *내 삭제* 로 가르려면 **base가 반드시 필요하다.**
base가 없으면 판별 불가이므로 삭제 없이 합집합으로 degrade한다(첫 도입 시점, 새 기기가 여기 해당).

### 7.3 삭제 수렴 — 케이스 4가 필요한 이유

restore는 non-destructive이므로 로컬 서버를 지우지 않는다. 그래서 삭제를 레포에만 반영하면 되살아난다.

> 기기 A·B가 동기화된 상태(레포 `{X, Y}`, A.S = B.S = `{X, Y}`)에서 A가 X를 지우고 백업한다(케이스 3).
> 레포는 `{Y}`가 된다. 이제 B가 백업하면 B의 로컬에는 X가 남아 있다.
> 이때 X를 "로컬 신규"로 취급해 레포에 다시 올리면 A의 삭제가 즉시 취소되고,
> 반대로 레포에서 지운 채 base를 `{Y}`로 갱신하면 **다음 백업에서 S에 X가 없어져 결국 되살아난다.**

그래서 케이스 4는 다음 두 규칙을 함께 적용한다.

1. **레포에 재추가하지 않는다.** X는 레포에서 빠진 채로 유지되고 `local_stale`로 보고된다.
2. **`local_stale`가 하나라도 있으면 이번 백업에서 base를 갱신하지 않는다.**
   S에 X가 남으므로 다음 백업도 같은 판정(케이스 4)을 내린다 — 되살아나지 않고 안정 상태에 머문다.

base를 갱신하지 않아도 나머지 서버는 푸시 직후 L==R이라 케이스 6(in_sync)으로 떨어지므로 부작용이 없다.

수렴은 restore에서 일어난다. 사용자가 로컬 제거를 선택하면(8.3) L에서 X가 사라져
케이스 3이 되고, base가 `{Y}`로 갱신되며 완결된다. 사용자가 거부하면 케이스 4가 유지되는데,
이는 "이 기기는 이 서버를 계속 쓴다"는 선택이므로 안정 상태로 남는 것이 옳다.

### 7.4 base 관리

- 위치: `~/.claude/.sync-state/base/mcp-servers.json`. 레포 상대경로 기준이므로
  `sync_state.write_base`/`read_base`를 그대로 재사용한다.
- 저장 내용: 레포 파일 바이트. 비교 시 `load_backup`으로 파싱해 servers 매핑을 얻는다
  (들여쓰기 등 포맷 차이에 영향받지 않는다).
- 갱신 시점:
  - backup — 커밋·푸시 **성공 이후에만**, 그리고 **`local_stale`이 비어 있을 때만** 갱신한다
    (기존 `update_base.py`의 "푸시 성공 시에만" 계약에 7.3의 게이트를 더한 것이다).
  - restore — MCP 단계 이후 레포 내용으로 갱신한다.
  - status — 읽기 전용이므로 갱신하지 않는다.

### 7.5 충돌 처리

별도 해소 UX를 만들지 않는다. 파일 쪽 `reject`와 같은 철학으로 처리한다.

- backup: 충돌 서버만 건너뛰고 "`/sync-restore` 먼저 실행" 안내. 백업 전체를 막지 않는다.
- restore: additive이므로 이미 등록된 서버는 건드리지 않는다. 차이를 사용자에게 보여준 뒤
  base를 레포 내용으로 갱신한다.
- 그 결과 다음 backup에서 R==S가 되어 로컬이 push된다.
  이는 파일 쪽 "로컬 유지(ours)" 해소와 정확히 같은 의미이므로 모델이 일관된다.

## 8. 스킬별 동작

### 8.1 backup

```
~/.claude.json → read_local_servers → redact → L
레포 mcp-servers.json → load_backup → R
base → load_backup → S
merge(L, R, S) → dump_backup → 레포
푸시 성공 && local_stale 없음 → write_base("mcp-servers.json", 레포 파일 바이트)
```

`conflicts`와 `local_stale`은 결과 보고에 포함하고 각각 다음 행동을 안내한다
— `conflicts`는 "`/sync-restore` 먼저", `local_stale`은 "`/sync-restore`에서 로컬 정리".

`claude mcp list` 호출은 완전히 제거한다. 스크립트는 `collect_mcp.py`로 이름을 바꾸며 stdin을 받지 않는다.

### 8.2 status

```
read_local_servers → L,  load_backup(레포) → R
diff(L, R) → only_local / only_repo / changed 출력
```

`changed`는 이름만이 아니라 config 차이까지 잡는다(예: `command` 변경). base는 갱신하지 않는다.

### 8.3 restore

```
load_backup(레포) → R,  read_local_servers → L,  base → S
restore_plan(L, R, S) → add / needs_secret / differs / in_sync / local_stale
add:          claude mcp add-json <name> '<json>' --scope user
needs_secret: 사용자에게 값을 물어 채운 뒤 add-json, 건너뛰면 미등록
differs:      건드리지 않고 안내만
local_stale:  "다른 기기에서 삭제된 서버가 로컬에 남아 있습니다. 제거할까요?"
              예 → claude mcp remove <name> -s user
              아니오 → 유지 (다음 backup에서 케이스 4로 남는다)
이후 base ← 레포 내용
```

`local_stale`은 L에 있고 R에 없으며 S에 있는 서버다(7.2 케이스 4).
이 확인 절차가 삭제를 수렴시키는 유일한 지점이므로 생략할 수 없다.
제거 명령은 `claude mcp get`이 안내하는 형식(`claude mcp remove <name> -s user`)을 그대로 쓴다.

`claude mcp add-json <name> <json> --scope user`를 쓴다. stdio·http를 모두 받고
`command`/`args`/`env`/`headers`를 그대로 전달하며, 공백이 든 이름도 인용만 하면 안전하다.
기존 SKILL.md의 `claude mcp add <name> <url> --transport ...`는 stdio 복원이 불가능하고 이름 인용도 빠져 있다.

## 9. 에러 처리 & 안전장치

가장 위험한 지점은 7.2의 삭제 판정이다. `~/.claude.json`을 일시적으로 읽지 못해 L이 빈 값이 되면
레포의 서버가 전부 삭제될 수 있다. 따라서 두 경우를 **엄격히 구분한다**.

| 상황 | 처리 |
|---|---|
| `mcpServers` 키 없음 | `{}` 반환 — 정상적인 "서버 0개". 삭제 판정 수행 |
| `~/.claude.json` 없음 / JSON 파싱 실패 | `LocalConfigUnavailable` 예외 → **MCP 단계 전체를 건너뜀.** 삭제 판정을 하지 않음 |
| 레포 `mcp-servers.json` 없음 | `{}` — 첫 백업으로 간주 |
| base 없음 | 삭제 없이 합집합 degrade |
| `add-json` 실패 | 해당 서버만 실패로 기록하고 나머지를 계속 진행 |

MCP 단계 실패가 backup·restore 전체를 실패시키지 않는다. 파일 동기화는 그대로 진행한다.

## 10. 마이그레이션 & 하위호환

- `load_backup`은 v1 배열(`[{name, url, type}, ...]`)을 읽어 `{name: {...}}`로 승격한다.
  v1에는 복원용 필드가 없으므로 이름 비교까지만 유효하다.
- 첫 백업에서 v2로 승격된다. v1 항목 중 로컬 user 스코프에 없는 이름(`claude.ai *` 등)은
  base가 없으므로 삭제되지 않고 그대로 보존된다. 사용자가 원하면 수동으로 정리한다.
- **역호환은 없다.** 구버전 `compare_mcp.py`는 `[s["name"] for s in backed]`로 배열을 가정하므로
  v2 객체를 만나면 `TypeError`로 죽는다. 따라서 MAJOR 버전 상승(2.0.0 → 3.0.0)이 필요하다.

## 11. 영향 파일 요약

| 파일 | 변경 |
|---|---|
| `plugins/claude-sync/lib/mcp_config.py` | **신설** — 5장 API |
| `plugins/claude-sync/skills/sync-backup/scripts/parse_mcp.py` | **삭제** |
| `plugins/claude-sync/skills/sync-backup/scripts/collect_mcp.py` | **신설** — 8.1 |
| `plugins/claude-sync/skills/sync-status/scripts/compare_mcp.py` | 정규식 제거, `mcp_config.diff()` 호출로 축소 |
| `plugins/claude-sync/skills/sync-restore/scripts/plan_mcp.py` | **신설** — 복원 계획 JSON |
| `plugins/claude-sync/skills/sync-backup/SKILL.md` | 6단계 재작성, 동기화 대상 표 정정, base 갱신 반영 |
| `plugins/claude-sync/skills/sync-status/SKILL.md` | `claude mcp list` 파이프 제거 |
| `plugins/claude-sync/skills/sync-restore/SKILL.md` | 6단계를 `add-json` 기반으로 재작성, 비밀 입력 흐름 추가 |
| `plugins/claude-sync/skills/sync-backup/scripts/backup-readme.md` / `.ko.md` | `mcp-servers.json` 설명 갱신 |
| `plugins/claude-sync/tests/test_mcp_config.py` | **신설** |
| `README.md` / `README.ko.md` | 12장 |
| `.claude-plugin/marketplace.json`, `plugins/claude-sync/.claude-plugin/plugin.json` | 2.0.0 → 3.0.0 |

## 12. 문서 정정

1. 동기화 대상 표의 `claude mcp list → mcp-servers.json | MCP 서버 이름과 URL`을
   `~/.claude.json (user 스코프) → mcp-servers.json | MCP 서버 설정 (비밀 값은 마스킹)`으로 바꾼다.
2. 백업 대상에서 제외되는 것(계정 커넥터·플러그인 제공·project/local 스코프)과 그 이유를 명시한다.
3. `mcp-servers.json`이 3-way 병합 대상이 되었음을 명시한다.
4. **`plugins.json`은 여전히 매 백업마다 통째로 덮어쓰이며 reconcile 대상이 아님을 명시한다.**
   이번에 고치지 않으므로 사실대로 남긴다. `README.ko.md`의 "로컬 파일은 절대 자동으로 덮어쓰지 않습니다"에
   이 예외를 붙인다.
5. 비밀 마스킹 정책과, 복원 시 값 입력이 필요하다는 점을 백업 레포 README에 적는다.

## 13. 검증 방법

pytest가 현재 환경에 설치되어 있지 않아 기존 `tests/`도 실행 불가 상태다.
`uv`가 있으므로 `uv run --with pytest pytest plugins/claude-sync/tests`로 실행한다.

**단위 테스트 (`test_mcp_config.py`)**
- 공백이 포함된 `command`(safari)가 온전히 보존된다 — Bug #1 회귀.
- http 서버의 `type`/`url`/`headers`가 보존되고, 값은 마스킹되며 키 이름은 남는다 — Bug #3·#4 회귀.
- `diff`: 로컬 평문과 레포 마스킹이 `in_sync`로 수렴한다 — Bug #2 및 마스킹 함정 회귀.
- `diff`: `command` 변경이 `changed`로 잡힌다.
- `merge`: 7.2 판정표 9줄 각각.
- `merge`: base가 없으면 삭제하지 않고 합집합이 된다.
- `merge`: 케이스 4에서 서버가 레포에 재추가되지 않고 `local_stale`로 보고된다.
- **순환 정합성**: 케이스 4 상태에서 base를 갱신하지 않은 채 `merge`를 두 번 연속 적용해도
  서버가 되살아나지 않고 같은 판정에 머문다 — 7.3 회귀.
- `restore_plan`: `local_stale` 분류, 그리고 로컬 제거 후 `merge`가 케이스 3으로 넘어가 수렴한다.
- `read_local_servers`: `mcpServers` 없음 → `{}`, 파일 없음/깨짐 → 예외.
- **안전장치**: `LocalConfigUnavailable` 발생 시 레포 servers가 보존된다.
- `load_backup`: v1 배열 하위호환.
- `restore_plan`: `needs_secret` 분류.

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

- `merge`의 config 동등 비교 방식: 정규화 후 딕셔너리 비교 vs 정렬 JSON 직렬화 해시.
  (현 안: `json.dumps(sort_keys=True)` 문자열 비교 — 단순하고 재현 가능.)
- `needs_secret` 값 입력을 SKILL.md의 대화 흐름으로 둘지, 스크립트 인자로 받을지.
  (현 안: SKILL.md 대화 — 스크립트에 비밀이 argv로 남지 않는다.)
- `plugins.json`의 동일 결함을 후속 과제로 등록할지.
- `local_stale`이 오래 방치될 때의 처리. (현 안: 백업할 때마다 보고만 하고 강제하지 않는다.
  base가 갱신되지 않는 상태가 지속되지만, 나머지 서버는 in_sync이므로 실질적 손해가 없다.)
