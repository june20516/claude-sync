---
name: sync-status
description: 로컬 Claude 설정과 Git 레포 백업 간의 차이를 보여주는 dry-run 도구. 아무것도 변경하지 않고 상태만 확인한다. 사용자가 /sync-status 를 실행했을 때만 동작한다. 자동 호출하지 않는다.
disable-model-invocation: true
---

# sync-status

로컬 Claude 설정과 Git 레포 백업 간의 차이를 보여준다. 아무것도 변경하지 않는 읽기 전용 명령이다.

backup이나 restore 전에 "지금 상태가 어떤지" 확인하고 싶을 때 사용한다.

## 설정 파일

동기화 설정은 `~/.claude/sync-config.json`에 저장된다. 파일이 없으면 사용자에게 Git 레포 URL을 물어보고 저장한다 (이것만 유일하게 쓰기 동작이 발생할 수 있다).

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
SYNC_SCRIPTS="$SYNC_ROOT/skills/sync-status/scripts"
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

`SYNC_BACKUP_SCRIPTS`는 다운그레이드 탐지(`detect_downgrade.py`)를 부르기 위해 필요하다. 읽기 전용 스크립트이므로 status가 불러도 안전하며, 복사본을 만들지 않는다.

`SYNC_ROOT`가 비어 있으면 플러그인이 제대로 설치되지 않은 것이므로 즉시 중단하고 사용자에게 안내한다.

### 1. 설정 확인 및 레포 준비

```bash
cat ~/.claude/sync-config.json
```

레포를 최신 상태로 가져온다 (clone 또는 pull):

```bash
if [ -d ${TMPDIR:-/tmp}/claude-sync-repo/.git ]; then
  cd ${TMPDIR:-/tmp}/claude-sync-repo && git pull --rebase
else
  rm -rf ${TMPDIR:-/tmp}/claude-sync-repo
  git clone <repo_url> ${TMPDIR:-/tmp}/claude-sync-repo
fi
```

### 1.5 호환성 검사 (경고만)

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 "$SYNC_LIB/compat.py" "$SYNC_REPO"
python3 "$SYNC_BACKUP_SCRIPTS/detect_downgrade.py" "$SYNC_REPO"
```

**검사가 성립하지 않았으면**(비-0 종료, JSON 아님, `blocked` 키 없음) 그 사실을 맨 위에 알린다 — "호환성을 확인하지 못했습니다"이지 "문제 없습니다"가 아니다. 그래도 **분석은 계속한다.**

`blocked`가 `true`면 **분석 결과 맨 위에 크게 경고한다.** `message`를 그대로 보여주고 다음을 덧붙인다:

> "이 상태에서는 `/sync-backup`이 차단됩니다. 아래 분석은 계속 진행합니다."

**이 명령은 아무것도 막지 않는다.** 버전이 안 맞을 때 사용자가 가장 먼저 실행할 명령이 status이고, 그것마저 막으면 진단 수단이 사라진다. 읽기 전용이라 위험도 없다.

탐지 출력의 `status`가 `"skipped"`면 **`reason`을 알린다** — "사고가 없다"가 아니라 "확인하지 못했다"이다. `repo_shape`·`base_shape`를 함께 보여준다. 그래도 분석은 계속한다.

`newer_schema_seen`이 `true`면 히스토리에 **이 버전이 알아보지 못하는 백업**이 있다는 뜻이다. 그 사실도 알린다.

`downgrade_suspected`가 `true`면 함께 알린다:

> "백업 레포의 MCP 파일이 옛 형식으로 되돌아가 있습니다 — 낮은 버전 기기가 덮어쓴 것으로 보입니다. `/sync-backup`을 실행하면 복구 후보를 제시합니다."

`candidate`가 있으면 그 커밋의 날짜와 서버 수도 함께 보여준다. status는 복구하지 않는다.

### 2. 메타데이터 기반 상태 분석

로컬 `~/.claude`와 레포를 **파일 내용의 sha256으로** 비교한다. mtime은 쓰지 않는다. 판정의 기준선(merge base)은 이 기기의 `~/.claude/.sync-state/base`다.

**여기서 `sync-metadata.json`은 읽지 않는다** — 이 절의 "메타데이터"는 그 파일이 아니라 base 스냅샷을 가리킨다. 표식 파일을 보는 곳은 1.5단계의 호환성 검사 하나이고 거기서 읽는 것은 버전 표식이다. `check_status.py`에는 표식 유무로 갈리는 **분기가 없다** — 언제나 같은 base 해시 경로를 탄다.

아직 base가 없는 파일은 로컬과 레포가 다르면 `conflict`로 분류된다. 어느 쪽이 앞선 것인지 판단할 근거가 없기 때문이며, 이것도 분기가 아니라 같은 3-way 분류의 결과다.

**`~/.claude/.syncignore`에 걸린 로컬 파일은 이 보고에 나오지 않는다.** 이 스크립트는 레포가 아니라 `~/.claude`를 직접 걷기 때문에 필터가 없으면 제외한 파일이 "backup 시 push"로 보고된다 — 백업은 그것을 실제로 push하지 않으므로 **보고만 어긋나는** 자리다. 매칭 규칙은 백업 4단계·`sync-metadata.json`과 같은 한 벌(`lib/syncignore.py`)이고, `.syncignore`가 무엇을 뜻하는지의 정본은 그 파일의 모듈 docstring이다 — **"올리지 않는다"(backup 방향 전용)**.

**레포에도 있는 제외 파일은 여전히 보고된다.** 다만 `local_ahead`("backup 시 push")가 아니라 **`⊘ .syncignore 제외인데 레포에 남아 있음 (backup 시 레포에서 삭제)`**로 따로 묶인다. 셋 중 참인 문구가 없어서다: push는 거짓이고(4단계가 지운다), 침묵도 거짓이며(레포에 있으니 restore가 건드린다), "restore 시 내려옴"도 거짓이다(`in_sync`는 skip, `local_ahead`는 keep). 스크립트는 그 묶음 아래에 두 줄을 덧붙인다 — 다음 백업이 레포 사본을 지우고 **다른 기기가 올려 둔 같은 경로 파일도 함께 사라진다**는 것, 그리고 restore는 `.syncignore`를 보지 않으므로 지워지기 전에 복원하면 그 파일도 평소의 3-way 판정을 받는다는 것.

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
python3 $SYNC_SCRIPTS/check_status.py "$SYNC_REPO"
```

파일 분석 이후, 플러그인과 MCP 서버 비교를 각각 수행한다:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -f "$SYNC_REPO/plugins.json" ]; then
  python3 "$SYNC_SCRIPTS/compare_plugins.py" "$SYNC_REPO/plugins.json"
fi
```

출력 JSON의 `status`가 `"skipped"`면 `settings.json`을 읽지 못했거나, 레포 파일의 형식을 알아볼 수 없거나, **레포 파일의 JSON 구문이 깨진 것이다.** `reason`을 알리고 플러그인 비교만 생략한다 — 읽기 실패를 "0개"로 오인하지 않기 위해서다. 그렇게 오인하면 레포에만 있는 항목이 `only_repo`에서 통째로 사라지고 이 기기의 항목이 전부 `only_local`로 뒤집힌다(실측). **"동일합니다"로 보고하지 않는다.** `reason`이 형식 문제이면 **이 기기의 플러그인이 낡은 것**이므로 `claude plugin marketplace update claude-sync && claude plugin update claude-sync`를 안내한다.

`reason`이 **"구문이 깨졌다"**이면 레포 파일 자체가 손상된 것이다 — **플러그인 업데이트는 소용이 없다.** 그 파일을 정상 JSON으로 되돌린 뒤 다시 실행하도록 안내한다(레포 git 이력에 정상 판본이 있으면 그것으로 복구한다). **그냥 지우라고 안내하지 않는다** — 그 문서에만 있던 다른 기기의 항목은 **이 기기의 로컬에 없어서 다음 백업이 되밀 수 없다** — 지우면 그 항목이 레포에서 사라진다. 이 상태에서는 `/sync-backup`도 같은 문서를 건너뛴다.

**최상위 `status`는 섹션 skip을 반영하지 않는다.** 그 값은 "비교를 수행했는가"이므로 섹션 둘이 접힌 실행에서도 `"ok"`다. 섹션 단위 사실은 `sections[<섹션>]["status"]`에만 있으니 **그것을 반드시 따로 읽고**, 최상위만 보고 "동일"이라고 말하지 않는다. 섹션 하나만 `"skipped"`인 경우가 있다(`auto` 판정 불가 → `enabledPlugins`·`pluginConfigs`, 보류 파일 손상 → `pluginConfigs`).

**`status`가 `"ok"`인 섹션에 `degraded_reason`이 있으면 그 문장도 함께 알린다.** 그 섹션은 접히지 않았지만 판정의 입력 하나를 잃은 상태다 — 보류 파일을 읽지 못하면 `pluginConfigs`만 접히는데 `enabledPlugins`는 H3의 해제 기록(`release`)을 함께 잃어, **이미 "이 기기 값으로 통일"을 고른 항목이 그 실행에서 다시 보류된다.** `reason`과 다른 키인 것은 그래서다 — 이것을 skip으로 렌더링하면 정상 처리된 섹션이 건너뛴 것으로 보고된다. 보류 파일을 고치고 다시 실행하도록 안내한다.

섹션별로 보고한다.

- `only_local` — 로컬에만 있음. `/sync-backup`이 판정합니다
- `only_repo` — 레포에만 있음. `/sync-restore`가 이 기기에 설치합니다. **다만 `unrestorable`에 있는 항목은 "이 기기에서는 복원할 수 없습니다"로 말한다**(정의는 아래 `unrestorable` 항목)
- `changed` — 양쪽에 있으나 값이 다름. **켬/끔 변경이 여기 포함된다.** 값이 확장 포맷이면 "버전 제약"으로 말한다. **방향과 값은 `changed_detail[<키>]["local"]`·`["repo"]`에서 읽는다** — 레포 파일을 다시 파싱하면 status 경로에 파서가 두 벌이 되어 결함 B가 되살아난다. 값은 이미 정규화돼 있어 비밀은 마스킹된 채로 온다
- `held.auto` / `held.local_marketplace` / `held.extended_value` / `held.declined` — 종류별 문구로 보고하거나 침묵한다. **`only_local`·`changed`로 말하지 않는다** — 백업하지 않는 항목을 "backup 시 추가"라고 하면 거짓이고 사용자가 해소할 수도 없다
- `absent_locally` — 보류 키 중 **로컬 섹션 문서에 값이 없는** 것. 여기 있는 항목에 "레포 값을 보존합니다"만 말하면 거짓이다(보존할 로컬 값이 없다). **이 목록 자체는 "미설치"가 아니다** — 의존성으로 설치된 플러그인은 설치되어 있으면서 `settings.json`에는 값이 없고, `enabledPlugins`의 키 부재는 매니페스트 기본값 위임이지 미설치가 아니다
- `not_installed` — `absent_locally` 중 **이 기기에 설치되지 않은** 것. 여기에만 "미설치"라고 말한다. `enabledPlugins`·`pluginConfigs` 두 섹션에만 실린다 — 마켓플레이스 이름은 설치 집합과 이름 공간이 달라 실으면 디렉토리 마켓플레이스가 "미설치 플러그인"으로 보고된다
- `unrestorable` — 이 기기에서 복원할 수 없는 항목. **`only_repo`의 부분집합이 아니다** — `/sync-restore`가 새 항목으로 훑는 집합에서 뽑으므로 값 보류(확장 값) 중 로컬에 값이 없는 키도 여기 들어온다. 그런 키는 `only_repo`에 없고 `held.extended_value`·`absent_locally`·`not_installed`에만 뜨는데, **어느 목록에 실렸든 이 목록에 있으면 "이 기기에서는 복원할 수 없습니다"가 우선한다.** `only_repo`만 보고 이 문구를 붙이면 그 항목에 "restore가 설치합니다"가 그대로 나간다(spec 9.2가 금지한 문구)

status는 아무것도 바꾸지 않는다. base를 읽지도 갱신하지도 않는다.

MCP 서버 비교:

```bash
SYNC_REPO="${TMPDIR:-/tmp}/claude-sync-repo"
if [ -f "$SYNC_REPO/mcp-servers.json" ]; then
  python3 "$SYNC_SCRIPTS/compare_mcp.py" "$SYNC_REPO/mcp-servers.json"
fi
```

출력 JSON의 `status`가 `"skipped"`면 `~/.claude.json`을 읽지 못했거나, 레포 파일의 형식을 알아볼 수 없거나, **레포 파일의 JSON 구문이 깨진 것이다.** `reason`을 알리고 MCP 비교만 생략한다 — 읽기 실패를 "서버 0개"로 오인하지 않기 위해서다. `reason`이 "구문이 깨졌다"이면 레포 파일이 손상된 것이므로 **정상 JSON으로 되돌린 뒤 다시 실행하도록** 안내한다(플러그인 업데이트는 소용이 없다). `reason`이 형식 문제이면 **이 기기의 플러그인이 낡은 것**이므로 `claude plugin marketplace update claude-sync && claude plugin update claude-sync`를 안내한다. 세 목록이 모두 비어 있으면 "MCP 서버: 동일"이라고 보고한다.

### 3. 결과 요약

**`blocked`가 `true`면 요약의 첫 줄에 넣는다.** `my_version`과 `repo_min_reader`를 그대로 쓴다. 예: "이 기기 3.0.0 / 이 백업이 요구하는 최소 버전 4.0.0 — `/sync-backup`이 차단됩니다."

`blocked`가 `false`인데 `repo_written_by`가 더 높으면 그것은 **차단 사유가 아니다.** 알리더라도 "차단됩니다"라고 쓰지 않는다 — `min_reader_version`은 항상 `{major}.0.0`이므로 같은 major의 상위 버전이 쓴 백업은 막히지 않는다.

상태 분류 (내용 해시 3-way, mtime 미사용):
- **in_sync**: 로컬과 레포 내용 동일
- **fast_forward**: 레포가 앞섬 → restore 시 자동 업데이트
- **repo_only**: 레포에만 있는 새 파일 → restore 시 추가
- **local_ahead / local_only**: 로컬이 앞섬 → backup 시 push
- **conflict**: 양쪽 모두 base 이후 변경 → restore 시 해소 필요

**플러그인과 MCP 서버의 어휘는 파일과 다르다.** 위의 "local_ahead / local_only: 로컬이 앞섬 → backup 시 push"는 그 둘에 적용되지 않는다. **버킷별 문구는 2단계를 따른다 — 여기에 정의를 다시 적지 않는다.** 두 벌이 되면 요약을 만드는 이 자리의 옛 정의가 2단계의 지시를 덮어써, `unrestorable` 항목에 "restore가 설치합니다"라고 말하거나 보류 항목을 `only_local`·`changed`로 내보내게 된다 — 둘 다 spec 9.2가 금지한 문구다.

status는 base를 읽지 않으므로 케이스를 확정하지 않는다. 판정의 단일 진입점은 backup의 `merge` 하나다.

이 명령은 아무것도 바꾸지 않는다. MCP 서버 비교 대상은 `~/.claude.json`의 user 스코프뿐이다. 계정 커넥터(`claude.ai *`), 플러그인 제공 서버(`plugin:*`), project·local 스코프 서버는 그 객체에 없으므로 자동으로 제외된다.

분석 결과를 사용자에게 보여준다. 이 스킬은 아무것도 변경하지 않으므로, 필요한 다음 단계를 안내한다:

- 로컬 변경사항을 레포에 반영하려면 → `/sync-backup`
- 레포 내용을 로컬에 적용하려면 → `/sync-restore`
