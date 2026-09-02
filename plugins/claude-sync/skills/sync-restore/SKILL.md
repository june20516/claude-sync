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

**기준선(base)이 없는 첫 실행은 판정이 아니라 degrade다.** 이 기기가 그 문서를 한 번도 reconcile하지 않았으면 `~/.claude/.sync-state/base/<rel>`이 없고, 그러면 삭제 후보(케이스 4·5)로 가는 경로가 **닫히며** 케이스 7·8도 전부 `both_changed`로 뭉친다(`lib/keyed_sync.py`의 `restore_plan`). **v2에서 올라온 뒤의 첫 `/sync-restore`가 정확히 그 상태다** — 양쪽에 있는 항목이 한꺼번에 "양쪽이 모두 바뀌었습니다"로 나온다.

그러므로 5·6절에서 항목마다 묻기 **전에** 한 번만 알린다. 건수를 함께 적는다.

> "이 기기에는 아직 비교 기준선이 없어, 양쪽에 있는 항목이 모두 「양쪽이 모두 바뀌었습니다」로 나옵니다(N건). 실제로 둘 다 바뀌었다는 뜻이 아니라 **어느 쪽이 앞선 것인지 판단할 근거가 없다**는 뜻입니다. 한 번 답하면 기준선이 생겨 다음 실행부터는 조용해집니다."

**"질문을 줄이려면 `/sync-backup`을 먼저 돌려라"고 안내하지 않는다.** 기준선 없는 백업은 합집합으로 degrade하면서 **양쪽에 있는 항목을 이 기기 값으로 덮고 그것을 충돌로 보고하지 않는다**(실측 — `/sync-backup` 4.6단계가 같은 사실을 막는다). 질문이 많은 것은 결함이 아니라 그 덮어쓰기를 막는 장치다.

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

**출력은 파일별 맵이다.** 최상위에 있는 것은 `status`·`reason`·`files` 셋뿐이고 판정은 전부 `files[<relpath>]` 아래에 있다. `files`의 키는 `mcp-servers.json`과 `plugins.json`이다. **항목마다 한 번씩, 둘 다 본다** — 첫 항목에서 멈추면 다른 문서의 사고가 뒤 단계에서 거짓 문구로 그대로 나간다.

최상위 `status`가 `"skipped"`면 **git 히스토리를 훑지 못했다**는 뜻이다. 최상위 `reason`을 알린다. 그리고 계속한다. **그것을 "다운그레이드를 확인하지 못했다"로 옮겨 적지 않는다** — 이때도 `files` 맵은 채워져 나오고 형태 비교는 git 없이 완결되므로 파일별 판정은 여전히 사실이다. 못 한 것은 후보 커밋 탐색이다.

`files`의 항목마다 — 그 항목의 키를 `<relpath>`라 하자:

`status`가 `"skipped"`면 **그 문서에 대해 `reason`을 알리고** 계속한다 — "사고가 없다"가 아니라 "확인하지 못했다"이다. `repo_shape`·`base_shape`를 함께 보여준다.

`downgrade_suspected`가 `false`면 그 문서는 조용히 넘어간다.

`downgrade_suspected`가 `true`면 **레포의 `<relpath>`가 그 문서의 옛 형식인데 이 기기의 base는 v2였다**는 뜻이다. 옛 버전 기기가 레포를 되돌렸다. **막지 않는다 — 경고하고 계속한다.** restore는 레포를 훼손하지 않고, 사용자가 복구 안내를 받을 경로가 여기다.

> "백업 레포의 `<relpath>`가 옛 형식으로 되돌아가 있습니다. 이 기기가 마지막으로 본 것은 새 형식이었습니다 — 낮은 버전 기기가 백업을 실행해 되돌린 것으로 보입니다.
>
> **되돌아가면서 일부 항목이 레포에서 누락됐을 수 있습니다.** 그 항목들은 **이 기기의 로컬에 아직 남아 있을 수 있고, 그렇다면 지금 로컬이 마지막 사본입니다.**"

**무엇이 누락되고 어디서 거짓 문구가 나오는지는 문서마다 다르다.** 그 문서의 행만 말한다.

| `<relpath>` | 2.x가 흘리는 것 | 뒤에서 거짓 문구가 나오는 자리 |
|---|---|---|
| `mcp-servers.json` | 타 기기에만 등록된 서버, 그리고 명령에 공백이 든 서버 — 2.x는 그 기기의 `claude mcp list` 출력만으로 이 파일을 통째로 다시 만들므로 **이 기기 것까지** 흘린다(실측) | **6-5** — "다른 기기가 이 서버를 삭제했습니다" |
| `plugins.json` | 타 기기의 플러그인·마켓플레이스, 그리고 **설정 키 전부** — 2.x는 이 파일을 통째로 다시 만들면서 `enabledPlugins`·`extraKnownMarketplaces` **둘만** 옮기므로, `pluginConfigs`와 `additionalMarketplaces`는 **이 기기 것까지** 사라진다(실측) | **5-5** — "다른 기기가 삭제했습니다" |

이때 반드시 함께 알린다.

- **위 표에서 그 문서에 해당하는 자리의 문구가 나와도 제거나 삭제를 선택하지 마세요.** 삭제가 아니라 유실입니다.
- 복구는 **레포에 쓸 수 있는 경로**에서 한다. 모든 기기를 3.0.0 이상으로 올린 뒤 `/sync-backup`을 실행하면 4.5단계가 문서마다 마지막 정상 커밋을 찾아 복구를 제안한다. **restore는 리모트에 push하지 않으므로 여기서 레포를 고칠 수 없다.**
- `candidate`가 있으면 그 커밋의 `sha`·`date`·`subject`와 `entries`의 **버킷별 항목 수**를 참고용으로 보여준다. 버킷 이름은 문서마다 다르므로 **나온 키를 그대로 쓴다.** 복구를 실행하지는 않는다.
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

### 5. 플러그인 복원

**2.5단계에서 버전 경고가 있었다면 이 안내를 가장 먼저 보여준다.** 사용자에게 지금 필요한 것은 다른 플러그인 설치가 아니라 claude-sync 자신의 업데이트다.

```bash
claude plugin marketplace update claude-sync
claude plugin update claude-sync
```

그다음 Claude Code를 재시작하거나 `/reload-plugins`를 실행해야 적용된다. 업데이트 후 `/sync-restore`를 다시 실행하면 보류됐던 항목이 복원된다.

레포 `plugins.json`과 로컬 상태를 비교해 계획을 세운다. `claude plugin list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging-restore"
rm -rf "$BASE_STAGING"
python3 "$SYNC_SCRIPTS/plan_plugins.py" plan "$SYNC_REPO/plugins.json" > /tmp/claude-sync-plugins-plan.json
cat /tmp/claude-sync-plugins-plan.json
```

`BASE_STAGING`은 여기서 딱 한 번 비운다. 6-6의 MCP `apply-base`가 같은 디렉토리를 쓰므로, 각 단계가 제 앞에서 `rm -rf`하면 앞 단계의 산출물이 지워지고 그 파일의 base가 전진하지 않는다.

**경로는 이 스킬 전용이다**(`…-base-staging-restore`). `/sync-backup`은 `…-base-staging-backup`을 쓴다. 두 스킬이 한 디렉토리를 공유하면 같은 두 relpath를 같은 존재 게이트로 승격하게 되어, 이 `rm -rf` 줄이 실행되지 않은 실행에서 **다른 스킬이 남긴** 산출물이 이 기기의 base로 실린다 — 결합을 산문이 아니라 경로로 끊는다.

`status`가 `"skipped"`면 `reason`을 알리고 플러그인 단계 전체를 건너뛴다(파일 복원과 6절의 MCP 단계는 그대로 진행한다). 갈래는 셋이다 — `settings.json`을 읽지 못했거나, 레포 파일의 형식을 알아볼 수 없거나, **레포 파일의 JSON 구문이 깨졌다.** 어느 갈래든 **제안을 하나도 내지 않는다**: 못 읽은 문서를 "항목 0개"로 읽으면 이 기기의 플러그인이 전부 `local_stale`로 떨어져 **"전부 지웁시다"가 나가는데**, 그 근거("다른 기기가 삭제했다")는 거짓이다(실측). `reason_kind`가 `unknown_schema`이면 `claude plugin marketplace update claude-sync && claude plugin update claude-sync` 후 다시 시도하도록 안내한다.

`reason_kind`가 **`broken_syntax`**이면 레포 파일 자체가 손상된 것이다 — **플러그인 업데이트는 소용이 없다.** 그 파일을 정상 JSON으로 되돌린 뒤 다시 실행하도록 안내한다(레포 git 이력에 정상 판본이 있으면 그것으로 복구한다). **그냥 지우라고 안내하지 않는다** — 그 문서에만 있던 다른 기기의 항목은 **이 기기의 로컬에 없어서 다음 백업이 되밀 수 없다** — 지우면 그 항목이 레포에서 사라진다.

**분기는 `reason_kind`로 한다 — `reason` 문장으로 하지 않는다.** 그 문장은 사람이 읽는 표시용이고, 문구를 다듬는 편집이 스킬의 경로를 **조용히** 바꾼다(예외도 빈 결과도 나지 않는다). 갈래는 `broken_syntax` · `unknown_schema` · `local_unreadable` · `io_error` · `contract_violation` 다섯이고, 표에 없는 값이면 처방을 지어내지 말고 `reason`만 보여준다.

**최상위 `status`는 섹션 skip을 반영하지 않는다.** 그 값은 "계획 수립을 수행했는가"이므로, 섹션 둘이 접힌 실행에서도 `"ok"`이고 `install`·`config_keys`는 비어 있다. 최상위만 읽으면 "복원할 것이 없습니다"로 보고하고 **조용히 아무것도 복원하지 않는다.** 섹션 단위 사실은 `sections[<섹션>]["status"]`에만 있으니 **그것을 반드시 따로 읽고**, `"skipped"`인 섹션의 복원만 건너뛴다.

**`status`가 `"ok"`인 섹션에 `degraded_reason`이 있으면 그 문장도 함께 알린다.** 그 섹션은 접히지 않았지만 판정의 입력 하나를 잃은 상태다 — 보류 파일을 읽지 못하면 `pluginConfigs`만 접히는데 `enabledPlugins`는 H3의 해제 기록(`release`)을 함께 잃어, **이미 "이 기기 값으로 통일"을 고른 항목이 그 실행에서 다시 보류된다.** `reason`과 다른 키인 것은 그래서다 — 이것을 skip으로 렌더링하면 정상 처리된 섹션이 건너뛴 것으로 보고된다. 보류 파일을 고치고 다시 실행하도록 안내한다.

**섹션 버킷의 처방 — 열한 개 전부** (9.3.8). 아래 이름은 `sections[<섹션>]` 안의 버킷이고 **최상위 키가 아니다.** 세 섹션이 각각 자기 몫을 낸다. 처리하는 절이 있는 행은 그 절 번호를 가리키고, 없는 행은 처방을 여기서 준다. 바로 뒤 6절의 MCP 표와 **층은 같고 처방이 다르다** — 그 표를 이 절에 옮겨 쓰지 않는다.

| 버킷 | 처방 |
|---|---|
| `add` | 계획이 최상위 `install`로 실어 준다 — 설치한다 (5-2) |
| `needs_secret` | 최상위 `config_keys`가 물어야 할 키 이름을 싣는다 — 값을 받아 채운 뒤 설치한다 (5-3) |
| `unrestorable` | 설치를 **시도하지 않는다.** 사유는 최상위 `unrestorable_reasons`에 있고 7절이 한 번만 보고한다. 실패 건수로 세지 않는다 |
| `in_sync` | 아무것도 하지 않는다 — 이 섹션의 그 항목은 이미 레포와 같다 |
| `local_only` | 보고만 — "이 항목은 이 기기에만 있습니다. 다음 `/sync-backup`이 레포로 올립니다" |
| `local_ahead` | 보고만 — "이 기기에서 바꾼 값이 아직 레포에 없습니다. `/sync-backup`을 실행해 올리세요". **선택지를 주지 않는다** — 레포 값은 이 기기가 마지막으로 본 그대로다 |
| `repo_ahead` | 세 선택지 (5-5) |
| `both_changed` | 세 선택지 + "양쪽이 모두 바뀌었습니다" 안내 (5-5) |
| `local_stale` | 세 선택지 (5-5). 마켓플레이스는 제거를 실행하지 않고 명령만 안내한다 |
| `value_held` | 설치는 하고 값은 레포를 보존한다 (5-6) |
| `action_held` | 어떤 CLI 명령의 대상도 되지 않는다. 섹션이 좁혀 주는 만큼만 말한다 (5-6) |

**`local_ahead`에 "레포 따르기"를 제시하지 않는다.** 레포 값은 이 기기가 마지막으로 reconcile한 값 그대로이므로, 채택은 곧 **아직 백업되지 않은 이 기기의 변경을 버리는 것**이다. 세 선택지를 주는 버킷(5-5)과 갈리는 자리가 여기다.

**`pluginConfigs`의 이 판정은 마스킹된 값 기준이다.** 비밀 값만 바꾼 항목은 양쪽이 같아져 `in_sync`로 떨어지므로 위 문구가 뜨지 않는다 — 그것이 "이 기기의 비밀이 레포에 올라갔다"는 뜻은 아니다. 레포에는 애초에 마스킹된 값만 올라간다.

#### 5-1. 마켓플레이스 등록

`marketplace_add`의 각 항목을 등록한다. `skipped_always_known`은 **등록하지 않는다** — 내장이거나 의사 출처라 시도하면 반드시 실패한다.

```bash
claude plugin marketplace add <arg> --scope user
```

`arg`는 계획이 실어 준 문자열을 그대로 쓴다. `reserved`가 `true`인 항목은 실패할 수 있다. 실패하면 "이 이름은 공식 마켓플레이스용으로 예약되어 있습니다"로 갈래를 구별해 보고한다.

#### 5-2. 플러그인 설치

`install` 목록을 설치한다. `skipped_already_installed`는 **부르지 않는다** — 이미 설치된 id에 bare install은 exit 0이지만(실측) **무해한 재실행이 아니다.** 그 명령이 쓰는 값은 매니페스트의 `defaultEnabled`이고 그 필드는 **선택 필드이며 기본이 `true`**다(실측 — 2026-08-29 스모크 2차 7장). 그래서 대다수 플러그인에서 로컬의 `false`를 말없이 켜고, 객체 값은 `true`로 평탄화한다(배열만 보존된다). 5-4가 마지막에 값을 되돌리지만 **평탄화된 객체 값은 되돌아오지 않는다** — 그것을 쓸 CLI가 없다(5-6).

**`depends_on`이 가리키는 마켓플레이스의 등록이 실패했다면 그 항목은 시도하지 않는다** — 등록되지 않은 상태로 install하면 CLI가 "플러그인이 없다"와 **똑같은 문구**로 실패해 사용자가 원인을 알 수 없다. `blocked`로 모아 "마켓플레이스 등록이 실패해 건너뛰었습니다"로 보고한다. 같은 규칙이 5-3·5-4에도 적용된다 — 4단계도 `install <id@marketplace> --config k=v` 형태라 등록되지 않은 마켓플레이스로는 똑같이 죽는다.

```bash
claude plugin install <id> --scope user
```

**`-y`를 붙이지 않는다.** 마켓플레이스가 명령으로 설치를 선언한 플러그인은 세션 안에서 설치할 수 없다 — 우회할 대상이 아니라 그대로 존중할 경계다. 실패하면 CLI가 출력한 문구를 **그대로** 전달한다. CLI가 이미 실행할 명령 전문과 승인 방법을 알려준다.

**설치가 실패한 id는 5-3·5-4의 대상에서 뺀다**(9.3.2 — 2단계가 실패한 id는 3·4단계를 건너뛴다). `blocked` 필터는 **1단계 등록 실패**만 걸러 내므로 이 갈래를 대신하지 못한다. 특히 5-4가 위험하다: 설치되지 않은 id에 `disable`을 내면 CLI가 exit 1이 아니라 **exit 0으로 `{id: false}` 키를 만든다**(실측 — 2026-08-29 스모크 2장). 설치 기록이 없는 그 **유령 키**는 레포 값과 같으므로 다음 백업이 in_sync로 읽어 base를 전진시키고, 그 뒤로 그 id는 `add` 버킷에 오지 않아 **영영 설치되지 않는다.** 잃는 것은 값이 아니라 **실패의 흔적**이다 — 실패한 항목의 base가 전진하지 않는 것은 다음 회차에 그 항목이 다시 보이게 하려는 것인데, 유령 키가 로컬을 레포에 **우연히** 동의시켜 그 규칙을 우회한다.

#### 5-3. 설정 채우기

**값 맞추기(5-4)보다 먼저 돈다.** 실행 순서는 `1 → 2 → 4 → 3`이고 절 번호는 그 순서를 따른다 — 단계 번호는 그대로다. 이 명령도 `install`이라 **`enabledPlugins` 값을 함께 쓴다**(5-2와 같은 규칙). 값 맞추기를 먼저 하면 이 명령이 그것을 곧바로 되돌리고, 다음 백업이 되돌려진 값을 레포로 밀어 **수렴이 깨진다.** 실측(2026-08-29 스모크 4장): `enabledPlugins={"demo@mkt": false}`인 기기에 `install demo@mkt --config token=…`을 내면 값이 `true`가 된다. 한 id가 `disable_after_install`과 `config_keys`에 **함께** 실릴 수 있으므로(둘 다 설치 여부로 좁히지 않는다) 가정이 아니라 실제로 나오는 갈래다.

**값 보존형 4단계는 선택지가 아니다** — CLI에 `configure` 서브커맨드가 없고(`claude plugin --help`에 `enable`·`disable`뿐이다), `/plugin configure`는 세션 안 슬래시 명령이라 이 스킬이 부를 수 없다. 남는 처방이 순서다.

**`config_keys`에 실린 키만** 사용자에게 묻는다. 계획이 지목하지 않은 id의 설정을 채우면 실제 흐름이 만들 수 없는 상태가 되고, 이어지는 백업이 그 값을 레포로 민다. **레포에는 마스킹된 값만 있으므로 그대로 등록하면 동작하지 않는 항목이 설치된다.**

**`config_skipped_local_extended`에 실린 id는 이 단계의 대상이 아니다.** 그 id의 로컬 `enabledPlugins` 값이 객체나 배열이고, 위 명령이 그것을 매니페스트 기본값으로 **평탄화**한다(객체가 그렇다 — 배열은 보존되지만 계획은 두 종류를 한 규칙으로 다룬다). 사용자가 요청하지 않은, 되돌릴 수 없는 로컬 상태 변경이므로 건너뛴다. **"복원 실패"로 렌더링하지 않는다** — 건너뛴 것이지 실패한 것이 아니다(10.2의 갈래 구분과 같은 종류다). 각 id와 **그 로컬 값**을 함께 보여 준다. 무엇을 지키려고 건너뛰었는지 봐야 사용자가 "이 기기 값을 포기하겠다"를 고를 수 있기 때문이다. 그렇게 고르면 같은 명령을 그 id에 직접 실행하면 된다는 것을 함께 알린다. **이 스킬이 대신 실행하지는 않는다.**

**지킬 값이 있을 때만 실린다.** 5-4가 그 키에 `enable`/`disable`을 낼 예정이면 그 명령이 확장 값을 어차피 지우므로(5-6의 표) 건너뛸 이유가 없다 — 그때는 설정 채우기를 그대로 진행한다. 그 갈래의 5-4는 부수 효과가 아니라 레포와 갈린 값을 맞추는 **요청된 수렴**이다.

그 id가 5-2의 `install` 목록에도 있고 로컬 값이 **객체**면 이 보류가 지키는 것은 없다. bare install이 같은 값을 먼저 덮기 때문이다(배열은 보존된다). 그 갈래에서 로컬 값은 **설치되지 않은 플러그인의 유령 키**이므로, 보고할 때 그 사실을 함께 적는다.

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

#### 5-4. 값 맞추기

**마지막 단계다.** 앞의 두 단계가 둘 다 `install`이라 `enabledPlugins` 값을 쓰므로, 레포 값과의 일치를 여기서 확정한다.

**계획의 `disable_after_install`을 그대로 실행하지 않는다.** 그 목록은 **계획 시점의** 로컬 값으로 정해졌는데 그 사이에 5-2와 5-3이 같은 키를 썼다. 실행 직전에 로컬을 다시 읽어 명령을 확정한다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/plan_plugins.py" recheck-values "$SYNC_REPO/plugins.json" /tmp/claude-sync-plugins-plan.json > /tmp/claude-sync-plugins-values.json
cat /tmp/claude-sync-plugins-values.json
```

`status`가 `"skipped"`면 `reason`을 알리고 **이 단계만** 건너뛴다 — 앞 단계가 이미 한 일은 그대로 둔다.

`commands`의 각 항목에 대해 그 항목의 `command`(`enable` 또는 `disable`)를 실행한다. 목록이 비어 있으면 **부를 것이 없다** — 앞 단계가 이미 레포와 같은 상태를 만들었다는 뜻이지 무언가 빠진 것이 아니다.

```bash
claude plugin disable <id> --scope user
claude plugin enable <id> --scope user
```

**`enable`/`disable`은 멱등이 아니다** — 현재 상태와 같은데 부르면 exit 1로 거짓 실패를 낸다. 그래서 "현재 상태와 다를 때만" 부르고, 그 **현재 상태**를 위의 재읽기가 정한다. 확장 포맷 값(5-6)에는 어느 쪽도 나가지 않는다.

**5-2의 `blocked` 필터가 여기에도 걸린다** — 등록이 실패한 마켓플레이스의 플러그인에는 어떤 명령도 내지 않는다.

**여기서 나가는 exit 1은 전부 진짜 실패다** — stderr 전문과 함께 보고한다. 앞 판에는 예외 갈래가 하나 있었다(`assumed`): 실행 직전에도 로컬에 키가 없으면 "켜져 있다"고 **추정**했고, 그 추정이 틀렸을 때의 exit 1을 실패로 렌더링하지 않았다. **그 추정이 사라졌다** — 로컬 키의 **부재는 「꺼짐」**이라는 것이 실측이기 때문이다(2026-09-01 스모크 4차). 그래서 재읽기가 부재를 `false`로 **읽고**, 레포가 `true`이면 `enable`이 나가고 `false`이면 아무 명령도 나가지 않는다. 어느 쪽도 "추정이 틀려서 나는 exit 1"을 만들지 않는다.

#### 5-5. 세 선택지 — 케이스 4·5·8·9

**이 표의 버킷은 `sections[<섹션>]` 안에 있다.** 계획 JSON은 두 층이고 이 절이 그 둘을 함께 부른다 — 버킷은 섹션별이고, `repo_values`·`local_values`·`install`·`config_keys`·`unrestorable_reasons`는 **최상위**다. 바로 뒤 6단계의 MCP 계획(`plan_mcp`)도 같은 두 층이다 — 버킷은 `sections["servers"]` 안, `configs`·`secret_keys`는 최상위. 최상위에서 `local_stale`을 찾으면 없고, 그러면 **케이스 4·5·8·9가 하나도 보고되지 않는다** — 넷 다 안정 상태라 사용자가 고를 기회 자체가 사라지고 다음 실행도 같다.

> **먼저 2.5단계가 낸 `files["plugins.json"]`의 `downgrade_suspected`를 본다. 참이면 `local_stale`(케이스 4·5)에 아래 표의 문구를 쓰지 않는다.**

**그 문서 하나만 본다.** `mcp-servers.json` 쪽 판정으로 이 안내를 억제하면, 플러그인은 멀쩡한데 참인 안내가 사라진다(반대도 같다 — MCP 쪽 억제는 6-5에 있다).

**`files["plugins.json"]`의 `downgrade_suspected`가 거짓일 때**(정상) — 아래 표의 문구를 그대로 쓴다.

**`files["plugins.json"]`의 `downgrade_suspected`가 참일 때** — 케이스 4·5의 "다른 기기가 삭제했습니다"는 **거짓이다.** 아무도 삭제하지 않았고, 낮은 버전 기기가 `plugins.json`을 통째로 다시 만들면서 **이 기기에 없는 타 기기의 항목을 흘린 것**이다. 그 문구는 사용자를 제거로 이끄는데, **이 항목의 마지막 사본이 지금 로컬에 있는 그것일 수 있다.** 대신 이렇게 쓴다.

> "이 항목은 다른 기기가 삭제한 것이 아니라, **낮은 버전 기기가 백업을 되돌리면서 레포에서 유실된 것으로 보입니다**(2.5단계 참조). 로컬에 남아 있는 이 값이 마지막 사본일 수 있습니다."

그리고 **아래 「삭제 전파」의 `uninstall --scope user`를 권하지 않는다. 기본 선택은 "로컬 유지"다** — 다음 백업이 그 항목을 레포로 되돌리므로 복구 경로이기도 하다. 이 억제는 `local_stale`(케이스 4·5)에만 적용된다. 케이스 8·9는 레포에 키가 살아 있으므로 유실이 아니다.

| 버킷 (`sections[<섹션>]` 안) | 상황 | 문구 |
|---|---|---|
| `local_stale`(케이스 4) | 다른 기기가 삭제했고 이 기기는 base와 같다 | "다른 기기가 삭제했습니다" |
| `local_stale`(케이스 5) | 다른 기기가 삭제했는데 이 기기에서 변경했다 | "다른 기기가 삭제했는데 이 기기에서 변경했습니다" |
| `repo_ahead`(케이스 8) | 다른 기기가 바꿨고 이 기기는 옛 값이다 | "다른 기기가 변경했습니다" |
| `both_changed`(케이스 9) | 양쪽이 다르게 바꿨다 | "양쪽이 모두 바뀌었습니다. 채택하면 이 기기의 변경이 사라집니다" |

세 선택지: **레포 따르기 / 로컬 유지(다음 백업에 올리기) / 이번엔 넘어가기.** 넷 다 **안정 상태**이므로 사용자가 고르지 않으면 영원히 유지된다.

- 레포 따르기 — `repo_values`의 값에 맞춰 `enable`/`disable`을 실행한다(값이 같으면 부르지 않는다. 현재 값은 `local_values`에 있다). **그 둘은 최상위 키다** — 섹션 안에서 찾으면 없다. base override는 없다.
- 로컬 유지 — 케이스 4·5는 `keep_stale`, 케이스 8·9는 `keep_local`에 넣는다. **한 조작이 아니다**(5-7).
- 이번엔 넘어가기 — 아무것도 하지 않는다.

**삭제 전파.** 레포에 키가 있고 값이 `false`면 다른 기기가 **껐다**는 뜻이므로 `disable`을 제안한다. 레포에 키가 **없고** base에 있었으면 다른 기기가 **삭제했다**는 뜻이므로 `uninstall --scope user`를 제안한다. 둘 다 사용자 확인을 받고 실행한다. **부재는 `false`가 아니다** — 레포에 키가 아예 없는 항목을 `disable` 대상으로 삼지 않는다.

**마켓플레이스의 `local_stale`은 삭제를 자동 실행하지 않는다.** `claude plugin marketplace remove`가 **소속 플러그인 키를 연쇄 삭제**하기 때문이다. 선택지는 **유지**(`keep_stale` — 다음 백업이 레포로 되돌린다)와 **이번엔 넘어가기** 둘이다. 제거를 원하면 명령만 안내하고, 함께 적는다: `--scope`를 생략하면 **모든 스코프**에서 제거되고, 그 마켓플레이스 소속 플러그인 키가 **전부 사라지며**, 손으로 실행하면 다음 백업이 그 삭제를 레포로 전파한다.

#### 5-6. 확장 포맷 값 — `value_held`

`sections[<섹션>]["value_held"]`에 있는 항목은 **설치돼 있고 값만 레포를 따르는 상태**다(5-5의 버킷과 같은 층이다). "양쪽이 모두 바뀌었습니다"라고 말하지 않는다 — 사실이 아니고, 배열 값을 쓸 CLI도 없다. **실측**(2026-08-29 스모크 3장): CLI는 확장 값을 「꺼짐」으로 읽어 `disable`은 `already disabled`로 죽고 `enable`은 그 값을 `true`로 **지운다.** 그래서 이 항목에는 어느 쪽도 내지 않는다.

> "설치했습니다. 다만 이 기기는 버전 제약을 표현할 수 없어 레포의 값을 보존합니다."

**로컬에 값이 없는 보류 항목은 이 버킷에 오지 않는다.** 계획은 그런 키를 `add`/`needs_secret`으로 (복원할 수 없으면 `unrestorable`로) 보낸다 — 그쪽 항목에 "레포의 값을 보존합니다"라고 말하면 거짓이다. 보존할 로컬 값이 없기 때문이다. 그 항목들에는 "설치했습니다"까지만 말한다. (`absent_locally`는 `/sync-status`의 필드이고 이 계획 JSON에는 없다.)

**탈출구**: "버전 제약을 포기하고 이 기기 값으로 통일한다"를 고르면 그 id를 `release`에 넣는다. 다음 백업이 이 기기의 값을 push해 레포 값이 불리언이 되고 보류가 자연 해제된다.

**지우고 싶을 때도 이 탈출구를 먼저 써야 한다.** H3의 조건은 **레포 값**이므로 로컬에서 `uninstall`해도 보류가 유지되어 삭제가 전파되지 않고, 다음 restore가 **다시 설치한다.** 순서는 ① 탈출구로 값을 불리언화 → ② 백업 → ③ `uninstall` → ④ 백업이다.

`sections[<섹션>]["action_held"]`에 있는 항목에는 **어떤 명령도 실행하지 않는다.**

**이 계획에는 보류 사유의 종류가 없다.** `plan_plugins`는 `held_kinds`를 부르지 않는다(의도 — 그 함수는 분류 불가에 `ValueError`를 던져 **플러그인 단계 전체를 접으므로**, 레포를 쓰지 않는 복원 경로에 그 실패 모드를 들이지 않는다). 그러니 **없는 종류를 지어내지 않는다.** 말할 수 있는 것은 이만큼이다.

| 버킷 · 섹션 | 확정되는 사유 |
|---|---|
| `value_held` (모든 섹션) | **버전 제약(확장 값) 하나로 확정.** 코어가 행동 보류를 먼저 걸러 내므로 이 버킷에는 그것만 남는다 |
| `action_held` · `extraKnownMarketplaces` | **로컬 디렉토리 마켓플레이스 하나로 확정** — 이 섹션에는 다른 보류 축이 걸리지 않는다 |
| `action_held` · `enabledPlugins` | 의존성 자동 설치 **또는** 로컬 디렉토리 마켓플레이스. 둘을 가르지 않는다 |
| `action_held` · `pluginConfigs` | 위 둘 **또는** 설정 입력을 건너뛴 항목. 셋을 가르지 않는다 |

확정되지 않는 두 줄은 **"이 명령으로는 사유를 가르지 못합니다"라고 그대로 말하고**, 종류별 내역이 필요하면 `/sync-status`를 안내한다 — 그쪽의 `held.auto`·`held.local_marketplace`·`held.extended_value`·`held.declined`가 사유를 실제로 낸다.

#### 5-7. base 갱신

**사용자가 아무 선택도 하지 않았어도 실행한다.** 무선택은 "이전 base 유지"로 계산되므로 결과가 달라지지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging-restore"

# 5-5에서 "로컬 유지"를, 5-3에서 "건너뜀"을, 5-6에서 "이 기기 값으로 통일"을 고른
# 항목만 적는다. 나머지 선택(레포 따르기·이번엔 넘어가기)에는 override가 필요 없다.
# **섹션 키를 정확히 쓴다** — 모르는 섹션 이름은 조용히 무시되어, 선택을 하나도
# 적용하지 않은 복원이 성공한 것처럼 보인다.
# **이 파일에는 이름과 선택만 들어간다 — 비밀 값은 절대 담지 않는다.**
cat > /tmp/claude-sync-plugins-choices.json << 'EOF'
{"enabledPlugins": {"keep_stale": [], "keep_local": [], "release": []},
 "extraKnownMarketplaces": {"keep_stale": [], "keep_local": []},
 "pluginConfigs": {"keep_stale": [], "keep_local": [], "declined": [], "configured": []}}
EOF

python3 "$SYNC_SCRIPTS/plan_plugins.py" apply-base "$SYNC_REPO/plugins.json" "$BASE_STAGING" /tmp/claude-sync-plugins-choices.json
rm -f /tmp/claude-sync-plugins-choices.json
```

`configured`에는 **5-3에서 값을 입력한** 항목을 적는다 — 적지 않으면 이전에 건너뛴 항목의 보류가 풀리지 않아 영영 조용한 상태로 남는다.

`apply-base`는 `settings.json`을 **다시 읽어** 계산하므로 5-1~5-6의 CLI 실행이 **모두 끝난 뒤**에 호출해야 한다. 실패했거나 건너뛴 항목은 로컬에 없으므로 base가 자동으로 전진하지 않는다.

스테이징에서 `base/`로 옮기는 것은 **6절 밖의 6.5절**이 두 파일을 함께 처리한다. 6절 안에 두면 MCP 계획이 `skipped`인 실행에서 이 절이 계산해 둔 플러그인 base가 영영 옮겨지지 않는다.

### 6. MCP 서버 복원

`~/.claude.json`의 user 스코프 `mcpServers`와 레포 `mcp-servers.json`을 비교해 계획을 세운다. `claude mcp list`는 호출하지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_SCRIPTS/plan_mcp.py" plan "$SYNC_REPO/mcp-servers.json" > /tmp/claude-sync-mcp-plan.json
cat /tmp/claude-sync-mcp-plan.json
```

**계획 JSON은 두 층이다 — 5절의 플러그인 계획과 같은 구조다.** 버킷은 `sections["servers"]` 안에 있고(섹션이 플러그인은 셋, MCP는 하나 — 이름은 `mcp_config.SECTIONS`), 실행 재료인 `configs`·`secret_keys`는 **최상위**다. 최상위에서 `add`나 `local_stale`을 찾으면 없고, 그러면 아래 표의 어느 버킷도 처리되지 않는다.

`status`가 `"skipped"`면 `reason`을 알리고 MCP 단계 전체를 건너뛴다(파일 복원과 5절의 플러그인 단계는 그대로 진행한다). `reason_kind`가 `unknown_schema`이면 레포가 **이 기기보다 상위 버전으로 백업된 것**이므로 `claude plugin marketplace update claude-sync && claude plugin update claude-sync` 후 다시 시도하도록 안내한다. `reason_kind`가 **`broken_syntax`**이면 레포 파일이 손상된 것이므로 **정상 JSON으로 되돌린 뒤 다시 실행하도록** 안내한다 — 이 갈래도 **제안을 하나도 내지 않는다.** 못 읽은 문서를 "서버 0개"로 읽으면 이 기기의 서버가 전부 `local_stale`로 떨어져 거짓 근거의 제거 제안이 나가기 때문이다(실측). `"ok"`면 버킷별로 처리한다.

| 버킷 (`sections["servers"]` 안) | 처방 |
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

이름이 CLI 규칙(영숫자·하이픈·언더스코어)을 어겼거나, config에 `command`도 `url`+`type`(http/sse)도 없는 항목이다. 옛 v1 형식에서 승격된 항목이 정확히 이 형태다. 목록을 한 번만 보여주고 "이 항목들은 옛 형식이거나 이름 규칙에 맞지 않아 복원할 수 없습니다"라고 안내한다. **실패 건수로 세지 않는다.** 사유는 `sections["servers"]["unrestorable_reasons"]`에 있다 — 항목마다 그 문장을 그대로 보여준다. **레포에서 정리하려면 `/sync-backup`이 6.5단계에서 제안한다** — restore는 레포에 쓰지 않는다.

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
1. 그 이름이 `sections["servers"]["unrestorable"]`에 있으면 채택 선택지를 제시하지 않는다.
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

> **먼저 2.5단계가 낸 `files["mcp-servers.json"]`의 `downgrade_suspected`를 본다. 참이면 아래 기본 문구를 쓰지 않는다.**

**그 문서 하나만 본다.** `plugins.json` 쪽 판정으로 이 안내를 억제하면, MCP는 멀쩡한데 참인 안내가 사라진다(반대도 같다 — 플러그인 쪽 억제는 5-5에 있다).

**`files["mcp-servers.json"]`의 `downgrade_suspected`가 거짓일 때**(정상) — 안내 문구를 둘로 가른다.

- 케이스 4(로컬 값이 base와 같음): "다른 기기가 이 서버를 삭제했습니다."
- 케이스 5(로컬에서 변경도 했음): "다른 기기가 삭제했는데 이 기기에서 변경했습니다."

**`files["mcp-servers.json"]`의 `downgrade_suspected`가 참일 때** — 위 두 문장은 **거짓이다.** 아무도 삭제하지 않았고, 낮은 버전 기기가 레포를 옛 형식으로 되돌리면서 흘린 것이다. 그 문장은 사용자를 "제거"로 이끄는데, **이 서버의 마지막 사본이 지금 로컬에 있는 그것일 수 있다.** 대신 이렇게 쓴다.

> "이 서버는 다른 기기가 삭제한 것이 아니라, **낮은 버전 기기가 백업을 되돌리면서 레포에서 유실된 것으로 보입니다**(2.5단계 참조). 로컬에 남아 있는 이 값이 마지막 사본일 수 있습니다."

그리고 **"제거"를 권하지 않는다. 기본 선택은 "유지"다.**

| 선택 | 동작 | 도달 상태 | 다운그레이드 의심 시 |
|---|---|---|---|
| **제거** | `claude mcp remove <name> -s user` | 레포·로컬 모두 없음 | **권하지 않는다** — 마지막 사본이 사라진다 |
| **유지** | 로컬 그대로 두고 이름을 `keep_stale`에 넣는다 | 다음 backup이 레포로 되돌린다 | **권장.** 레포 복구 경로이기도 하다 |
| **나중에** | 아무것도 하지 않는다 | 변화 없음, 다시 보고 | 안전하다 |

"유지"가 base에서 이름을 지우는 것은 **"그 이력은 잊는다"는 명시적 선언**이다. 이 동작이 없으면 케이스 4가 영원히 유지되어 사용자가 그 서버를 레포에 되돌릴 방법이 없다.

다운그레이드가 의심될 때 "유지"가 권장인 이유가 하나 더 있다. 이 기기를 3.0.0 이상으로 올린 뒤 `/sync-backup`을 실행하면 **"유지"한 서버가 레포로 되돌아간다** — 유실된 것을 되살리는 경로다. "제거"를 고르면 그 경로가 닫힌다.

#### 6-6. MCP base 계산

**사용자가 아무 선택도 하지 않았어도 실행한다.** 무선택은 "이전 base 유지"로 계산되므로 결과가 달라지지 않는다.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging-restore"

# 6-4에서 "로컬 유지"를, 6-5에서 "유지"를 고른 이름만 적는다.
# 나머지 선택(제거·채택·나중에)에는 base override가 필요 없다.
# 이 파일에는 이름과 선택만 들어간다 — 비밀 값은 절대 담지 않는다.
cat > /tmp/claude-sync-mcp-choices.json << 'EOF'
{"keep_stale": [], "keep_local": []}
EOF

python3 "$SYNC_SCRIPTS/plan_mcp.py" apply-base "$SYNC_REPO/mcp-servers.json" "$BASE_STAGING" /tmp/claude-sync-mcp-choices.json
rm -f /tmp/claude-sync-mcp-choices.json
```

`apply-base`는 `~/.claude.json`을 **다시 읽어** 계산하므로, 위 6-1~6-5의 CLI 실행이 **모두 끝난 뒤**에 호출해야 한다. 이 단계는 스테이징까지만 쓴다 — `base/`로 옮기는 것은 6.5절이다.

### 6.5 base 갱신 (스테이징 → base)

**5절과 6절 중 어느 쪽이 건너뛰어졌더라도 이 절은 실행한다.** 두 apply-base가 같은 스테이징 디렉토리에 쓰고 여기가 그것을 `base/`로 옮기는 **유일한 경로**이므로, 이 절이 어느 한쪽 단계 **안에** 있으면 그 단계가 `skipped`인 실행에서 다른 파일의 base까지 함께 영영 전진하지 않는다. 그러면 `keep_stale`·`keep_local`·`release` 선택이 조용히 무효가 되고, 사용자는 같은 질문을 매번 다시 받는다(9.3.7).

```bash
BASE_STAGING="${TMPDIR:-/tmp}/claude-sync-base-staging-restore"

# **두 relpath를 함께 훑는다** — 한 파일에만 걸면 다른 파일의 base가 전진하지 않아
# 그 파일의 삭제 전파가 조용히 죽는다. 계산되지 않은 파일은 스테이징에 없으므로
# 자동으로 빠진다.
# apply-base에는 레포 쓰기가 없으므로 여기서는 **파일 존재가 곧 "계산 성공"**이다.
RELS=()
for rel in plugins.json mcp-servers.json; do
  [ -f "$BASE_STAGING/$rel" ] && RELS+=("$rel")
done
if [ ${#RELS[@]} -gt 0 ]; then
  python3 "$SYNC_BACKUP_SCRIPTS/update_base.py" "$BASE_STAGING" "${RELS[@]}"
  echo "base 갱신됨: ${RELS[*]}"
fi
```

`update_base.py`에 `"$SYNC_REPO"`를 넘기면 안 된다 — `base ← 레포 파일 바이트`가 되어 타 기기의 서버와 플러그인을 다음 백업이 삭제한다.

### 7. 결과 보고

복원 완료 후 다음을 요약해서 보여준다:

- **적용 건수**: add / overwrite / auto_merge / skip 각각의 파일 수
- **해소한 충돌**: 파일명과 선택 방식 (나중에는 미해소로 표시)
- **local_ahead 파일** → "올리려면 /sync-backup을 실행하세요" 안내 (restore는 push하지 않음)
- **설치한 플러그인**: 5-2에서 설치한 것, 5-4에서 값을 맞춘 것
- **건너뛴 플러그인 설정**: 5-3에서 값을 입력하지 않아 보류(`declined`)로 만든 항목. 나중에 채우는 방법을 함께 적는다
- **보류한 항목**: 계획에 있는 두 버킷 그대로 — `value_held`(버전 제약)와 `action_held`(섹션별로 5-6의 표만큼만 좁혀 말한다). **`held`의 종류별 내역을 여기서 요구하지 않는다** — 복원 흐름의 어떤 스크립트도 그 필드를 내지 않으므로, 요구하면 지어내게 된다(`orphaned`와 같은 자리다). 종류별 내역은 `/sync-status`가 낸다. **"버전 때문에 보류한 항목"(이 기기의 플러그인이 낮아 알아보지 못한 것)과 섞지 않는다** — 앞의 것은 이 릴리즈의 정상 동작이고 뒤의 것은 업데이트로 풀린다
- **복원하지 못한 플러그인**: `blocked`(마켓플레이스 등록 실패로 시도하지 않음)와 `unrestorable`. 뒤의 것은 목록도 사유도 **섹션 안에** 있다 — `sections[<섹션>].unrestorable`과 같은 자리의 `unrestorable_reasons`를 그대로 쓴다(`/sync-status`의 `compare_plugins`와 같은 층위다). **둘 다 실패 건수로 세지 않는다** — 시도하지 않았기 때문이다
- **`orphaned`는 이 스킬이 보고하지 않는다.** 마켓플레이스가 등록되지 않은 채 레포에 남은 플러그인 목록은 `collect_plugins`(백업 5단계)만 낸다 — 복원 흐름의 어떤 스크립트도 그 필드를 내보내지 않으므로 **여기서 요구하면 목록을 레포 파일에서 지어내게 된다**(두 번째 파서 = 결함 B). 안내는 `/sync-backup` 쪽에 있다
- **등록한 MCP 서버** (`add` / `needs_secret`에서 값을 받아 등록한 것)
- **건너뛴 MCP 서버**: 비밀 값 입력을 건너뛴 것, `unrestorable`(옛 형식·이름 규칙 위반 — 실패로 세지 않는다)
- **버전 때문에 보류한 항목**: 이 기기의 플러그인이 낮아 알아보지 못한 것. **"실패"가 아니라 "보류"로 보고한다** — 데이터는 레포에 그대로 있고 업데이트 후 다시 실행하면 복원된다
- **해소한 MCP 충돌**: 서버명과 선택(채택 / 로컬 유지 / 유지 / 제거 / 나중에)
- **`local_ahead` MCP 서버** → "올리려면 `/sync-backup`을 실행하세요"
- **등록 실패한 MCP 서버**: `add-json`이 실패한 것. "레포 값 채택"의 `remove` **이후** 실패는 서버가 로컬에서 사라진 상태이므로 넣으려던 JSON과 함께 크게 경고한다

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

**실패는 항목 단위로 독립이고 종료 코드는 0이다.** 하나가 실패해도 나머지는 계속 진행한다 — 그래야 안내가 보인다.
