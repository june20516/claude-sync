---
name: sync-restore
description: Git 레포에서 Claude 설정 파일들(agents, skills, CLAUDE.md, 플러그인 목록)을 복원한다. 사용자가 /sync-restore 를 실행했을 때만 동작한다. 자동 호출하지 않는다.
disable-model-invocation: true
---

# sync-restore

Git 레포에서 Claude 설정 파일들을 복원하는 스킬이다.

## 모델 (git-like, pull-only)

restore는 `git pull`처럼 동작한다. **리모트에 자동 push하지 않는다.** 비교는 내용 해시 3-way(로컬 `L` / 레포 `R` / base `S` = 이 기기가 마지막으로 reconcile한 remote 내용, `~/.claude/.sync-state/base/<rel>`)로 한다. 파일 수정 시각은 비교에 사용하지 않는다.

파일별 판정:
- **skip** (in_sync): L=R — 이미 동일
- **add** (repo_only): 레포에만 있는 새 파일 — 로컬에 추가. **충돌과 무관하게 항상 적용된다.**
- **overwrite** (fast_forward): 레포만 변경 — R로 덮어씀
- **keep** (local_ahead / local_only): 로컬만 변경 또는 로컬 전용 — 그대로 유지
- **merge** (conflict): 양쪽 모두 base 이후 변경 — 3-way 시도 후 자동 병합 또는 충돌 격리

**MCP 서버는 파일이 아니라 서버 이름 키 단위로 판정한다.** 로컬 `~/.claude.json`(user 스코프) / 레포 `mcp-servers.json` / base의 3-way이며, 레포에만 있는 서버는 등록하고, 양쪽이 다르거나 한쪽에서 사라진 서버는 **서버마다 물어본다**(제거·유지·나중에 / 레포 값 채택·로컬 유지·나중에). restore는 로컬 서버를 임의로 지우거나 덮어쓰지 않는다.

## 설정 파일

동기화 설정은 `~/.claude/sync-config.json`에 저장된다:

```json
{
  "repo_url": "git@github.com:user/claude-settings.git"
}
```

최초 실행 시 이 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다.

## 실행 절차

### 0. 플러그인 루트 확인

**실행 중인 플러그인과 같은 버전의 스크립트를 써야 한다.** 옛 버전 디렉토리가 지워지지 않고 남으므로, 아무거나 고르면 이 세션이 다른 버전의 스크립트를 실행하게 된다.

```bash
# plugins/cache 아래만 본다 — plugins/marketplaces는 레포 클론이지 설치본이 아니다.
# semver 모양인 디렉토리만 본다 — 'unknown'이나 'latest'는 sort -V에서 릴리즈를 이긴다.
#   (이 기기에 실제로 cache/claude-plugins-official/skill-creator/unknown 이 있다.)
# 경로 전체가 아니라 버전 성분으로 정렬한다 — 그러지 않으면 마켓플레이스 이름이 정렬을
#   지배해, 이름이 뒤인 마켓플레이스의 낮은 버전이 선택된다.
# head -1은 임의 선택이므로 쓰지 않는다.
SYNC_ROOT=$(find ~/.claude/plugins/cache -path "*/claude-sync/*/.claude-plugin" -type d 2>/dev/null \
  | sed 's|/\.claude-plugin$||' \
  | grep -E '/[0-9]+\.[0-9]+\.[0-9]+$' \
  | awk -F/ '{print $NF"\t"$0}' | sort -V | tail -1 | cut -f2-)
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-restore/scripts"
SYNC_BACKUP_SCRIPTS="$SYNC_ROOT/skills/sync-backup/scripts"
SYNC_LIB="$SYNC_ROOT/lib"

# 못 찾았으면 비-0으로 끝낸다. echo만 하고 exit 0으로 끝나면 "판정 불가"가 "문제 없음"과
# 같은 모양이 되고, 뒤 단계의 rm -rf + clone + push가 어느 버전인지도 모른 채 먼저 돈다.
# exit이 아니라 false다 — 뒤 단계가 같은 셸 세션의 $SYNC_SCRIPTS를 쓰므로 세션을 끝내면 안 된다.
if [ -z "$SYNC_ROOT" ]; then
  echo "claude-sync 플러그인 설치 경로를 찾지 못했습니다. 진행하지 마세요." >&2
  false
else
  # 어느 버전을 쓰는지 눈에 보이게 한다. 불일치는 조용하면 안 된다.
  echo "Plugin root: $SYNC_ROOT"
  python3 -c 'import json,sys
try:
    print("Version:", json.load(open(sys.argv[1])).get("version", "unknown"))
except Exception as e:
    print("Version: 읽지 못함 (%s)" % e)' "$SYNC_ROOT/.claude-plugin/plugin.json"
fi
```

`SYNC_BACKUP_SCRIPTS`가 필요한 이유는 base 블롭을 기록하는 주체가 `sync-backup/scripts/update_base.py` **하나뿐**이기 때문이다(파일 쪽과 같은 규칙을 공유한다). 이제 두 경로 모두 같은 `SYNC_ROOT`에서 나오므로 서로 다른 버전이 섞일 수 없다.

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 즉시 중단하고 사용자에게 안내한다.

### 1. 설정 확인

```bash
cat ~/.claude/sync-config.json
```

파일이 없으면 사용자에게 Git 레포 URL을 물어본다. URL을 받으면 `~/.claude/sync-config.json`에 저장한다.

### 2. 레포에서 최신 상태 가져오기

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -d "$SYNC_REPO/.git" ]; then
  cd "$SYNC_REPO" && git pull --rebase
else
  rm -rf "$SYNC_REPO"
  git clone <repo_url> "$SYNC_REPO"
fi
```

### 2.5 호환성·다운그레이드 검사

두 방향을 다 본다. **상위 버전이 쓴 레포**는 `compat.py`가, **옛 버전이 되돌린 레포**는
`detect_downgrade.py`가 판정한다. 앞의 것은 경고 후 묻고, 뒤의 것은 경고만 한다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"
python3 "$SYNC_BACKUP_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"
```

**검사가 성립하지 않았으면**(비-0 종료, JSON 아님, `blocked` 키 없음) 확인하지 못한 것을 문제 없음으로 읽지 않는다. 다만 이때는 `message`도 `reason`도 없으므로 **이 경우에만 SKILL.md가 문구를 직접 쓴다:**

> "호환성 검사를 실행하지 못했습니다. 이 레포가 이 버전에 안전한지 확인하지 못했습니다. restore는 레포를 훼손하지 않으므로 계속할 수 있지만, 알아보지 못하는 항목은 건너뛴 부분 복원이 됩니다. 계속할까요?"

- **계속한다** — 파일 복원은 스키마와 무관하므로 정상 동작한다.
- **중단하고 원인을 확인한다** — 0단계의 플러그인 루트와 `python3` 설치 상태를 본다.

**아래의 `reason` 분기와 폴백은 JSON이 나온 경우에만 적용한다.**

`blocked`가 `true`면 `message`를 보여주고 다음을 덧붙인 뒤 **계속할지 묻는다.**

> "restore는 레포를 훼손하지 않지만, 이 버전이 알아보지 못하는 항목은 건너뛴 **부분 복원**이 됩니다. 파일 동기화는 스키마와 무관하므로 정상 동작합니다. 계속할까요?"

선택지는 `reason`에 따라 다르다. **`blocked`가 아니라 `reason`으로 분기한다** — `blocked`는 "차단"이라는 뜻일 뿐 "업그레이드하면 풀린다"는 뜻이 아니다.

`reason`이 `older_than_min_reader` / `my_version_unknown` / `min_reader_unparsable`이면:

- **계속한다** — 파일은 정상 복원되고, 알아보지 못하는 MCP 항목만 보류된다.
- **중단하고 업데이트한다** — 5단계의 안내대로 플러그인을 올린 뒤 다시 실행한다.

`reason`이 `metadata_unreadable` / `repo_not_found` / `check_failed`이면 **업데이트를 권하지 않는다.** 그 갈래의 `message`에 업그레이드 명령이 없는 것이 그래서다.

- **계속한다** — 다만 `repo_not_found`이면 복원할 레포 자체가 없으므로 권하지 않는다.
- **중단하고 원인을 확인한다** — 레포 경로와 권한, `python3` 설치 상태를 본다.

표에 없는 `reason`이면 중단하고 `message`만 그대로 보여준다 — 정의되지 않은 갈래를 임의로 해석하지 않는다.

**restore를 막지 않는 이유**: 버전이 낮아 backup이 막힌 사용자가 업데이트 안내를 받을 수 있는 경로가 restore다. 여기까지 막으면 탈출구가 사라진다.

#### 다운그레이드 탐지 결과

`status`가 `"skipped"`면 **`reason`을 알리고** 계속한다 — "사고가 없다"가 아니라 "확인하지 못했다"이다. `repo_shape`·`base_shape`를 함께 보여준다.

`downgrade_suspected`가 `false`면 조용히 다음 단계로 간다.

`downgrade_suspected`가 `true`면 **레포의 `mcp-servers.json`이 v1 배열인데 이 기기의 base는 v2였다**는 뜻이다. 옛 버전 기기가 레포를 되돌렸다. **막지 않는다 — 경고하고 계속한다.** restore는 레포를 훼손하지 않고, 사용자가 복구 안내를 받을 경로가 여기다.

> "백업 레포의 MCP 파일이 옛 형식으로 되돌아가 있습니다. 이 기기가 마지막으로 본 것은 새 형식이었습니다 — 낮은 버전 기기가 백업을 실행해 되돌린 것으로 보입니다.
>
> **되돌아가면서 일부 서버가 레포에서 누락됐을 수 있습니다**(2.x는 명령에 공백이 든 서버를 흘립니다). 그 서버들은 **이 기기의 로컬에 아직 남아 있을 수 있고, 그렇다면 지금 로컬이 마지막 사본입니다.**"

이때 반드시 함께 알린다.

- **6단계에서 "다른 기기가 삭제했습니다"가 나와도 제거를 선택하지 마세요.** 삭제가 아니라 유실입니다(6-5).
- 복구는 **레포에 쓸 수 있는 경로**에서 한다. 모든 기기를 3.0.0 이상으로 올린 뒤 `/sync-backup`을 실행하면 5.5단계가 마지막 정상 커밋을 찾아 복구를 제안한다. **restore는 리모트에 push하지 않으므로 여기서 레포를 고칠 수 없다.**
- `candidate`가 있으면 그 커밋의 `date`·`subject`·`server_count`·`server_names`를 참고용으로 보여준다. 복구를 실행하지는 않는다.
- `newer_schema_seen`이 `true`면 히스토리에 이 버전이 알아보지 못하는 백업이 있다는 뜻이므로, 후보가 그보다 오래된 것임을 명시한다.

### 3. 파일별 reconcile (비대화 적용)

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/reconcile_restore.py" "$SYNC_REPO" --apply
```

스크립트가 자동 처리하는 것 (사용자 개입 없음):
- **skip** (in_sync), **add** (레포에만 있는 새 파일), **overwrite** (fast-forward: 레포가 앞섬), **keep** (local_ahead/local_only: 로컬 유지), **auto_merge** (양쪽 변경이나 안 겹쳐 깨끗이 병합).
- 위 모두 base를 적절히 갱신한다.
- **additive(add)는 충돌과 무관하게 항상 적용된다.** 충돌이 있어도 새 파일 추가는 막히지 않는다.

출력 JSON의 `conflicts` (겹친 충돌 또는 base 없음)만 4단계로 넘어간다. `local_ahead` 목록은 "올리려면 /sync-backup" 안내용이다.

### 4. 충돌 해소 (스킬이 대신 수행 — 사용자는 선택만)

`conflicts`가 비어 있으면 이 단계를 건너뛴다.

`conflicts`의 각 파일에 대해:
1. 간결한 diff를 보여준다:
   ```bash
   diff <(cat $SYNC_REPO/<rel>) ~/.claude/<rel>
   ```
   `has_base: true`이면 base와의 차이도 함께 보여준다.
2. 사용자에게 선택지를 제시: **로컬 유지 / 백업 채택 / 병합 / 나중에**
3. 선택대로 스킬이 직접 적용한다 (사용자가 파일을 만지지 않는다):

   - **백업 채택** (theirs): 레포 파일을 로컬에 복사한 뒤 base를 레포 내용으로 갱신.
     ```bash
     cp "$SYNC_REPO/<rel>" "$HOME/.claude/<rel>"
     python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" <rel>
     ```

   - **로컬 유지** (ours): 로컬 파일은 그대로 두고 base를 레포 내용으로 갱신 (remote를 봤고 거부 → 재충돌 방지). 로컬은 local_ahead가 된다.
     ```bash
     python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" <rel>
     ```

   - **병합** (겹침 / base 없음): 에이전트가 로컬·레포(가능하면 base) 내용을 읽어 병합안을 만들어 사용자에게 보여주고 확인받은 뒤 `"$HOME/.claude/<rel>"`에 쓴다. 그 후 base를 레포 내용으로 갱신. 로컬은 local_ahead가 된다.
     ```bash
     python3 "$SYNC_SCRIPTS/reconcile_restore.py" --set-base-from "$SYNC_REPO" <rel>
     ```

   - **나중에** (defer): 아무것도 하지 않는다. base 불변 → 다음 restore에서 다시 표시된다.

모든 해소 방식(나중에 제외)은 base ← 레포 내용으로 갱신한다. `--set-base-from` 호출이 이를 담당한다.

### 5. 플러그인 복원 (additive)

**2.5단계에서 버전 경고가 있었다면 이 안내를 가장 먼저 보여준다.** 사용자에게 지금 필요한 것은 다른 플러그인 설치가 아니라 claude-sync 자신의 업데이트다.

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync
```

그다음 Claude Code를 재시작하거나 `/reload-plugins`를 실행해야 적용된다. 업데이트 후 `/sync-restore`를 다시 실행하면 보류됐던 항목이 복원된다.

레포 `plugins.json`의 `enabledPlugins` 중 로컬 `settings.json`에 없는 것만 설치한다. 기존 플러그인은 제거하지 않는다.

#### 5-1. 마켓플레이스 추가

`extraKnownMarketplaces`에 있지만 로컬에 없는 마켓플레이스를 추가한다:
```bash
claude plugin marketplace add <owner/repo>
```

#### 5-2. 플러그인 설치

```bash
claude plugin install <plugin-name@marketplace>
```

`claude plugin` 명령어가 없거나 실패하면 `plugins.json` 내용을 보여주고 수동 설치를 안내한다.

### 6. MCP 서버 복원

`~/.claude.json`의 user 스코프 `mcpServers`와 레포 `mcp-servers.json`을 비교해 계획을 세운다. `claude mcp list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
MCP_STAGING="${TMPDIR:-/tmp}/claude-sync-mcp-base"
python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json" > /tmp/claude-sync-mcp-plan.json
cat /tmp/claude-sync-mcp-plan.json
```

`status`가 `"skipped"`면 `reason`을 알리고 MCP 단계 전체를 건너뛴다(파일 복원은 그대로 진행한다). `reason`이 "형식을 알아볼 수 없다"이면 레포가 **이 기기보다 상위 버전으로 백업된 것**이므로 `claude plugin marketplace update claude-sync && claude plugin update claude-sync` 후 다시 시도하도록 안내한다. `"ok"`면 버킷별로 처리한다.

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

레포에서 사라졌지만 로컬에 남아 있는 서버다.

> **먼저 2.5단계의 `downgrade_suspected`를 본다. 참이면 아래 기본 문구를 쓰지 않는다.**

**`downgrade_suspected`가 거짓일 때**(정상) — 안내 문구를 둘로 가른다.

- 케이스 4(로컬 값이 base와 같음): "다른 기기가 이 서버를 삭제했습니다."
- 케이스 5(로컬에서 수정도 했음): "다른 기기가 삭제했는데 이 기기에서 수정했습니다."

**`downgrade_suspected`가 참일 때** — 위 두 문장은 **거짓이다.** 아무도 삭제하지 않았고, 낮은 버전 기기가 레포를 옛 형식으로 되돌리면서 흘린 것이다. 그 문장은 사용자를 "제거"로 이끄는데, **이 서버의 마지막 사본이 지금 로컬에 있는 그것일 수 있다.** 대신 이렇게 쓴다.

> "이 서버는 다른 기기가 삭제한 것이 아니라, **낮은 버전 기기가 백업을 되돌리면서 레포에서 유실된 것으로 보입니다**(2.5단계 참조). 로컬에 남아 있는 이 값이 마지막 사본일 수 있습니다."

그리고 **"제거"를 권하지 않는다. 기본 선택은 "유지"다.**

| 선택 | 동작 | 도달 상태 | 다운그레이드 의심 시 |
|---|---|---|---|
| **제거** | `claude mcp remove <name> -s user` | 레포·로컬 모두 없음 | **권하지 않는다** — 마지막 사본이 사라진다 |
| **유지** | 로컬 그대로 두고 이름을 `keep_stale`에 넣는다 | 다음 backup이 레포로 되돌린다 | **권장.** 레포 복구 경로이기도 하다 |
| **나중에** | 아무것도 하지 않는다 | 변화 없음, 다시 보고 | 안전하다 |

"유지"가 base에서 이름을 지우는 것은 **"그 이력은 잊는다"는 명시적 선언**이다. 이 동작이 없으면 케이스 4가 영원히 유지되어 사용자가 그 서버를 레포에 되돌릴 방법이 없다.

다운그레이드가 의심될 때 "유지"가 권장인 이유가 하나 더 있다. 이 기기를 3.0.0 이상으로 올린 뒤 `/sync-backup`을 실행하면 **"유지"한 서버가 레포로 되돌아간다** — 유실된 것을 되살리는 경로다. "제거"를 고르면 그 경로가 닫힌다.

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

### 7. 결과 보고

복원 완료 후 다음을 요약해서 보여준다:

- **적용 건수**: add / overwrite / auto_merge / skip 각각의 파일 수
- **해소한 충돌**: 파일명과 선택 방식 (나중에는 미해소로 표시)
- **local_ahead 파일** → "올리려면 /sync-backup을 실행하세요" 안내 (restore는 push하지 않음)
- **설치한 플러그인** (있으면)
- **등록한 MCP 서버** (`add` / `needs_secret`에서 값을 받아 등록한 것)
- **건너뛴 MCP 서버**: 비밀 값 입력을 건너뛴 것, `unrestorable`(옛 형식·이름 규칙 위반 — 실패로 세지 않는다)
- **버전 때문에 보류한 항목**: 이 기기의 플러그인이 낮아 알아보지 못한 것. **"실패"가 아니라 "보류"로 보고한다** — 데이터는 레포에 그대로 있고 업데이트 후 다시 실행하면 복원된다
- **해소한 MCP 충돌**: 서버명과 선택(채택 / 로컬 유지 / 유지 / 제거 / 나중에)
- **`local_ahead` MCP 서버** → "올리려면 `/sync-backup`을 실행하세요"
- **등록 실패한 MCP 서버**: `add-json`이 실패한 것. "레포 값 채택"의 `remove` **이후** 실패는 서버가 로컬에서 사라진 상태이므로 넣으려던 JSON과 함께 크게 경고한다
