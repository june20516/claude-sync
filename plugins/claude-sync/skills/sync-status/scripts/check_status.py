#!/usr/bin/env python3
"""로컬 ~/.claude 와 레포 백업의 차이를 3-way(내용 해시)로 분석해 출력한다. mtime 미사용.

**플러그인은 여기서 비교하지 않는다.** 옛 판은 플러그인 섹션의 **키 집합만** 비교해
켬/끔 변경을 통째로 놓쳤고(결함 B), 그 자리에 두 번째 파서가 있었다. 판정의 단일
진입점은 sync-status/scripts/compare_plugins.py 하나다 — SKILL.md 2단계가 부른다.
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import sync_state as ss  # noqa: E402
import syncignore  # noqa: E402

repo_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "SYNC_REPO", "/tmp/claude-sync-repo"
)
HOME_CLAUDE = os.path.expanduser("~/.claude")

# **`.syncignore`에 걸린 로컬 파일은 열거하지 않는다.** backup 4단계가 그 파일을 레포에서
# 지우므로 실제로는 push되지 않는데, 필터가 없으면 이 스크립트가 그것을
# `local_only`("backup 시 push")로 보고한다 — 사용자가 제외했다고 믿은 파일을 두고
# "다음 백업이 올립니다"라고 말하는 자리다. 누수는 아니고 **보고만 어긋난다.**
# 매칭은 4단계 bash·generate_metadata.py와 같은 한 벌을 쓴다(lib/syncignore.py).
#
# **레포 쪽 열거는 거르지 않는다(결정).** reconcile_restore.py는 `.syncignore`를 보지
# 않으므로 레포에 있는 항목은 제외 대상이라도 **restore의 판정 대상이다** — 거르면 이
# 보고가 restore와 어긋난다. 그래서 이 필터가 없애는 것은 정확히 **"레포에 없는 제외
# 파일"** 하나뿐이다.
#
# 레포에도 있는 제외 파일은 **`excluded_in_repo`로 따로 보고한다.** 그 자리에 쓸 수 있는
# 참인 문구가 셋 중 어느 것도 아니기 때문이다: "backup 시 push"는 거짓이고(4단계가
# 레포에서 지운다), 침묵도 거짓이며(레포에 있으니 restore가 건드린다), "restore 시
# 내려옴"도 거짓이다(`in_sync`는 skip, `local_ahead`는 keep이라 안 내려온다).
# 남는 참은 **backup 방향 하나** — 다음 백업이 레포 사본을 지우고 그 삭제를 푸시한다.
# 그것을 머리말에 두고, restore 쪽은 "`.syncignore`를 보지 않는다"만 덧붙인다.
# 규정의 정본은 lib/syncignore.py 모듈 docstring이다.
#
# `.syncignore`를 못 읽으면 예외가 전파된다 — load_patterns의 규약이다. 여기서 삼키면
# 제외 목록이 통째로 빈 것으로 읽혀 위의 잘못된 보고가 조용히 돌아온다.
patterns = syncignore.load_patterns(syncignore.default_path(HOME_CLAUDE))
local_rels = syncignore.filter_relpaths(
    sorted(ss.iter_synced_relpaths(HOME_CLAUDE)), patterns)
rels = sorted(set(ss.iter_synced_relpaths(repo_path)) | set(local_rels))

buckets = {
    "in_sync": [],
    "repo_only": [],      # restore 시 추가
    "local_only": [],     # backup 시 push
    "local_ahead": [],    # backup 시 push
    "fast_forward": [],   # restore 시 업데이트
    "conflict": [],       # 양쪽 변경
    "excluded_in_repo": [],   # backup 시 레포에서 삭제
}

for rel in rels:
    # 여기 오는 제외 대상은 **반드시 레포에 있다** — `rels`의 로컬 쪽 절반은 이미
    # 걸러졌으므로 제외 패턴에 걸린 채 남은 경로는 레포 열거에서만 올 수 있다.
    # 3-way 분류를 하지 않는 이유: 그 결과(local_ahead/fast_forward/…)가 말하는 것은
    # "이 파일을 어느 쪽으로 옮기는가"인데, 이 파일들에 대해 backup이 하는 일은
    # 옮기는 것이 아니라 **레포에서 지우는 것**이라 어느 분류에도 해당하지 않는다.
    if syncignore.is_excluded(rel, patterns):
        buckets["excluded_in_repo"].append(rel)
        continue
    local = os.path.join(HOME_CLAUDE, rel)
    repo = os.path.join(repo_path, rel)
    L = ss.file_hash(local)
    R = ss.file_hash(repo)
    S = ss.base_hash(rel)
    cls = ss.classify(L, R, S, local_exists=L is not None, repo_exists=R is not None)
    buckets[cls].append(rel)

print("=" * 60)
print("git-like 동기화 상태 (내용 해시 기준, mtime 미사용)")
print("=" * 60)

labels = [
    ("conflict", "⚠ 충돌 — 양쪽 변경 (restore 시 해소 필요)"),
    ("fast_forward", "↓ 업데이트 가능 — 레포가 앞섬 (restore 시 적용)"),
    ("repo_only", "+ 새 파일 — 레포에만 있음 (restore 시 추가)"),
    ("local_ahead", "↑ 로컬 앞섬 (backup 시 push)"),
    ("local_only", "+ 로컬 전용 (backup 시 push)"),
    ("excluded_in_repo", "⊘ .syncignore 제외인데 레포에 남아 있음 (backup 시 레포에서 삭제)"),
    ("in_sync", "✓ 동일"),
]

# 머리말은 참인 절반만 말한다. 나머지 절반(restore가 무시한다)을 적지 않으면 사용자가
# "곧 사라지니 신경 쓸 것 없다"로 읽는데, 지워지기 전에 복원하면 그 파일이 로컬에
# 적용될 수 있다. 두 문장이 함께 있어야 규정("올리지 않는다")이 온전히 읽힌다.
EXCLUDED_NOTE = (
    "  ↳ push되지 않는다. 다음 backup이 레포 사본을 지우고 그 삭제를 푸시하므로,\n"
    "    다른 기기가 올려 둔 같은 경로 파일도 함께 사라진다.\n"
    "  ↳ restore는 `.syncignore`를 보지 않는다 — 지워지기 전에 복원하면 이 파일도\n"
    "    평소의 3-way 판정을 그대로 받는다(추가·덮어쓰기·머지·보존)."
)

for key, label in labels:
    items = buckets[key]
    if items:
        print("\n%s (%d개):" % (label, len(items)))
        for f in items:
            print("  " + f)
        if key == "excluded_in_repo":
            print(EXCLUDED_NOTE)

if not any(buckets[k] for k in buckets if k != "in_sync"):
    # **전칭으로 읽히면 안 된다.** iter_synced_relpaths가 열거하는 것은 agents·skills·
    # CLAUDE.md뿐이고 플러그인·MCP의 두 백업 파일은 여기 포함되지 않는다 — 그 둘은
    # 2단계의 compare_plugins·compare_mcp가 따로 판정한다. 범위를 적지 않으면 소비자가
    # 이 한 줄을 "전부 동일"로 요약해, 플러그인·MCP의 차이가 조용히 사라진다.
    print("\n파일(에이전트·스킬·CLAUDE.md)은 모두 동기화 상태입니다."
          " 플러그인·MCP 서버는 따로 보고합니다.")

print()
