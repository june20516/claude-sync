# 3.1.0 릴리즈 체크리스트 (사용자 실행용)

> ## ⚠ 먼저 읽을 것 — 이 기기가 스모크의 픽스처다
>
> 3.0.0을 올린 이 기기에는 **①②③④를 실기기에서 검증할 상태가 살아 있습니다**(2026-09-02 실측):
> 임시 클론 `${TMPDIR}/claude-sync-repo`의 `mcp-servers.json`에 `claude.ai *` 커넥터 7개가
> 그대로 있고, `~/.claude/.sync-state/base/`에는 `plugins.json`·`mcp-servers.json` 둘뿐
> **파일 기준선이 하나도 없습니다.**
>
> **3.1.0을 설치하기 전에 그 상태를 손으로 고치지 마세요.** 커넥터 7개를 지우면 ③의 검증
> 대상이 사라지고, 파일 기준선을 만들면 ①②의 검증 대상이 사라집니다. BACKLOG의
> "이 기기에서 지금 해야 할 것" 2번(커넥터를 손으로 지운다)은 **하지 않습니다** — 3.1.0이
> 그것을 없애야 할 대상입니다.
>
> **순서가 중요합니다.** ①②③④의 픽스처는 **한 번의 `/sync-backup`으로 소비됩니다.**

plan ④(`docs/superpowers/plans/2026-09-02-post-3.0.0-fixes.md`)의 Task 14가 만든 문서입니다.
**이 문서는 배포하지 않습니다** — 푸시·머지·태그·배포는 외부 동작이므로 전부 사용자가
실행합니다.

---

## 1. 이미 확인된 것

| spec의 결함 | 무엇이 닫았나 | 그것을 고정하는 테스트 |
|---|---|---|
| ① `reject`가 방향을 단정한다 | `reconcile_backup.reject_bucket`이 기준선 유무 하나로 갈래를 정한다 | `test_reconcile.py::test_backup_reconcile_splits_reject_by_base_presence` · `test_skill_wiring.py::test_backup_step4_never_calls_a_baseless_reject_remote_ahead` |
| ② 백업만 하는 기기에 파일 기준선이 없다 | 10단계가 `push ∪ in_sync`를 두 성공 경로 모두에서 `update_base.py`에 넘긴다 | `test_skill_wiring.py::test_backup_advances_file_bases_on_both_success_paths` |
| ③ 복원 불가 항목이 레포에 영구 잔류한다 | `prune_mcp.py` + backup 6.5단계 | `test_mcp_scripts.py`의 prune 계약 여섯 · `test_mcp_cycle.py::test_pruned_garbage_does_not_come_back` · `test_a_device_that_really_has_the_server_is_asked_and_brings_it_back` |
| ④ 표식이 레포에 없는 내용을 적는다 | `generate_metadata.build_metadata`가 레포 작업 트리를 걷는다(둘째 인자 필수) | `test_metadata.py::test_files_map_is_exactly_the_synced_files_of_the_tree` (양방향 완전성) |
| ⑤ 구문 손상 복구를 사용자에게 떠넘긴다 | `detect_downgrade`의 `broken_syntax` + backup 4.5단계의 세 선택지 | `test_downgrade.py`의 구문 손상 넷 · `test_skill_wiring.py::test_every_broken_syntax_branch_points_at_the_plugin_repair` |
| 언어 스위치 | 세 스킬 1단계의 `language` 규칙 문단 | `test_skill_wiring.py::test_step1_carries_the_language_rule_and_asks_on_first_run` · `test_the_do_not_translate_list_is_the_same_in_every_skill` |
| 복원 계획 층 통일 | `plan_mcp.build_plan`의 `sections` 층 | `test_mcp_scripts.py::test_plan_is_two_layered_like_the_plugin_plan` · `test_restore_prose.py::test_the_mcp_plan_prose_reads_buckets_from_the_section_layer` |

**버전 일치**: `plugins/claude-sync/.claude-plugin/plugin.json`과 루트
`.claude-plugin/marketplace.json`이 둘 다 `3.1.0`입니다. `MIN_READER_VERSION`은 **`3.0.0`
그대로**입니다 — 백업 문서의 형식이 바뀌지 않아 3.0.0 기기가 3.1.0의 백업을 읽지 못할
이유가 없습니다.

**검증**: `main` 기준선 1211 passed → 이 브랜치 **1265 passed**. 변조 명세 열셋 전부 재실행해
`APPLY_FAIL` 0건, SURVIVED는 등가 변조 셋뿐입니다(`docs/superpowers/mutations/README.md`).

---

## 2. 실행 절차

흐름은 3.0.0과 같습니다 — **`feat/post-3.0.0-fixes` → `release/3.1.0` → `main`**.

### 2-1. 최종 검증

```bash
uv run --with pytest pytest plugins/claude-sync/tests -q
grep -rn '"version"' .claude-plugin/marketplace.json plugins/claude-sync/.claude-plugin/plugin.json
```

0 failed이고 둘 다 `3.1.0`이어야 합니다.

### 2-2. PR 둘

```bash
git push -u origin feat/post-3.0.0-fixes
gh pr create --base release/3.1.0 --head feat/post-3.0.0-fixes \
  --title "3.0.0 이후 결함 일곱 — 3.1.0" --body-file docs/RELEASE-NOTES-3.1.0.md
# 머지 후
gh pr create --base main --head release/3.1.0 \
  --title "release: 3.1.0" --body-file docs/RELEASE-NOTES-3.1.0.md
```

(`release/3.1.0` 브랜치가 없으면 `git push origin main:release/3.1.0`으로 먼저 만듭니다.)

### 2-3. 태그와 GitHub Release

```bash
claude plugin tag plugins/claude-sync --push
```

Release 본문은 `docs/RELEASE-NOTES-3.1.0.md`(한국어)와 `docs/RELEASE-NOTES-3.1.0.en.md`(영어)
둘을 씁니다.

### 2-4. 기기별 업데이트

```bash
claude plugin marketplace update claude-sync && claude plugin update claude-sync
```

**순서 제약이 없습니다.** 3.0.0 기기와 섞여 있어도 됩니다 — 백업 문서의 형식이 바뀌지
않았습니다.

---

## 3. 실기기 스모크 — 이 기기가 픽스처다

**설치 전에 1번을 먼저 합니다.**

### 3-1. (설치 전) 대조군

```
/sync-status
```

출력을 통째로 남겨 둡니다. 3.0.0이 `agents/code-reviewer.md`를 어떻게 부르는지가 대조
기준입니다.

### 3-2. 3.1.0 설치·재시작 후 `/sync-backup` **한 번**

확인할 것 넷:

| 단계 | 무엇을 본다 | 기대 |
|---|---|---|
| 4단계 (①) | `reject`의 두 갈래 | `reject.no_base == ["agents/code-reviewer.md"]`. 새 문구("어느 쪽이 앞선 것인지 판단할 수 없습니다")가 나가고 **"리모트가 앞선"은 나가지 않는다** |
| 6.5단계 (③) | `unrestorable` 목록과 사유 | `claude.ai *` 7개가 사유와 함께 뜬다. 「레포에서 정리한다」를 고르면 `pruned`가 7개, `refused`가 비어 있다 |
| 10단계 (②) | 경로와 파일 기준선 | "변경사항이 없습니다"가 **아니라** 커밋 경로다(프룬이 트리를 바꿨다). `~/.claude/.sync-state/base/`에 `in_sync` 8개의 파일 기준선이 생기고, **`agents/code-reviewer.md`의 기준선은 없다** |
| 7단계 (④) | 레포의 `sync-metadata.json` | `agents/code-reviewer.md`의 해시가 **레포 판본**(`1be61088…`)이다. 이 기기에 없는 다른 기기 파일이 있으면 그것도 맵에 있다 |

```bash
# 10단계 확인
ls -R ~/.claude/.sync-state/base/
# 7단계 확인
python3 -c "import json;print(json.load(open('${TMPDIR:-/tmp}/claude-sync-repo/sync-metadata.json'))['files']['agents/code-reviewer.md'])"
```

### 3-3. `/sync-backup` 한 번 더 — 고정점

`unrestorable`·`repo_ahead`·`deleted`가 전부 비어 있고, 10단계가 "변경사항이 없습니다"
경로로 가며, 파일 기준선 8개가 그대로여야 합니다(③의 고정점, ②의 두 번째 경로).

### 3-4. `/sync-restore`

- 계획 JSON이 `sections["servers"]` 층인지 확인합니다 (설계 D-2).
- `agents/code-reviewer.md`가 충돌로 뜨면 **「로컬 유지」**를 고릅니다.
  **「백업 채택」은 로컬 41줄을 버립니다** — 이것이 ①이 막으려던 바로 그 선택입니다.
- 그 뒤 `/sync-backup`을 한 번 더 돌리면 그 파일이 `push`로 올라가고 기준선이 생깁니다.

### 3-5. 언어 스위치

```bash
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.claude/sync-config.json")
d = json.load(open(p)); d["language"] = "en"
json.dump(d, open(p, "w"), ensure_ascii=False, indent=2)
PY
```

이어서 `/sync-status`. **문장은 영어**, 명령·JSON 키·버킷 이름·파일 경로·서버 이름은
그대로여야 합니다. 확인 후 원하면 키를 지웁니다(부재가 곧 한국어입니다).

### 3-6. ⑤ — 버리는 레포에서만

**실기기 레포를 깨뜨리지 않습니다.** 임시 클론을 복제한 버리는 레포에서 확인합니다.

```bash
cp -R "${TMPDIR:-/tmp}/claude-sync-repo" /tmp/claude-sync-broken-test
cd /tmp/claude-sync-broken-test
python3 -c "
p='mcp-servers.json'
s=open(p).read()
open(p,'w').write(s[:len(s)//2])   # 잘린 쓰기를 흉내낸다
"
```

이 레포를 대상으로 4.5단계의 세 선택지(**복구한다** / **복구하지 않고 계속한다** /
**중단한다**)를 한 번씩 돕니다. 「복구한다」 뒤에 5·6단계가 정상 병합하는지, 「복구하지
않고 계속한다」에서 그 문서만 건너뛰는지를 봅니다. 끝나면 지웁니다.

---

## 4. 스모크에서 무엇이 어긋나면 릴리즈를 멈추나

- 4단계가 `reject.no_base`에 "리모트가 앞선"을 말한다 → **①이 닫히지 않았다.**
- 6.5단계의 `refused`가 비어 있지 않다 → 목록과 판정이 갈렸다. `prune_mcp` 출력을 그대로 남깁니다.
- 10단계 뒤에 `agents/code-reviewer.md`의 **기준선이 생겼다** → 방향 모르는 파일의 base가 전진했다. **되돌릴 수 없는 쪽**이므로 즉시 멈춥니다.
- 표식의 해시가 로컬 판본이다 → ④가 닫히지 않았다.

나머지(문구 다듬기, 영어 번역의 어색함)는 릴리즈 차단 사유가 아닙니다 — 다음 판에 고칩니다.
