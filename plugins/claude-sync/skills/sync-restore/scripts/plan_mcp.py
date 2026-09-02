#!/usr/bin/env python3
"""복원 계획 수립과 base 계산. 로컬 상태를 직접 바꾸지 않는다.

사용:
  plan_mcp.py plan <레포의 mcp-servers.json 경로>
    복원 계획 JSON을 stdout에 낸다 (`sections[<섹션>]`의 버킷 9개 + 최상위 configs·secret_keys).

  plan_mcp.py apply-base <레포의 mcp-servers.json 경로> <스테이징 디렉토리> <선택 결과 JSON 경로>
    복원 후 로컬을 다시 읽어 next_base를 계산하고, 선택 override 두 개를 적용해
    스테이징 디렉토리에 기록한다. base 블롭 기록은 update_base.py가 한다(7.5).

CLI 실행과 비밀 값 입력은 SKILL.md의 대화 흐름이 맡는다(8.3) — 비밀이 스크립트
인자에 남지 않게 하려는 것과, 7.4·7.7의 세 선택지가 대화형 확인이어야 하는 것이
같은 이유다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import report  # noqa: E402
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402

# 등록·채택 대상 버킷. SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이 되살아나므로
# 등록에 쓸 config를 계획에 함께 실어 준다. 값은 redact를 거쳐 비밀이 없다.
NEEDS_CONFIG = ("add", "needs_secret", "repo_ahead", "both_changed")


def build_plan(backup_path, claude_json_path=None, base_dir=ss.BASE_DIR):
    """restore_plan 결과를 `sections` 층으로 감싸고 등록용 레포 config(마스킹됨)를 덧붙인다.

    **두 층이다 — plan_plugins와 같은 구조**(spec 7). 버킷은 `sections[<섹션>]` 안(판정),
    `configs`·`secret_keys`는 최상위(실행 재료). 섹션 이름은 `mc.SECTIONS`에서 뽑고
    언패킹으로 "섹션이 하나"라는 전제를 함께 건다 — detect_downgrade._mcp_buckets와 같다.
    앞 판은 버킷을 최상위에 두어 sync-restore/SKILL.md가 두 표의 층 차이를 세 군데서
    경고해야 했다. 휘발성 JSON이라 마이그레이션은 없다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    plan = mc.restore_plan(local, repo, base)
    masked = mc.redact(repo)
    names = sorted({n for bucket in NEEDS_CONFIG for n in plan[bucket]})
    (section,) = mc.SECTIONS
    return {
        "status": "ok",
        "sections": {section: dict(plan)},
        "configs": {n: masked[n] for n in names},
        "secret_keys": {
            n: mc.secret_keys(masked[n]) for n in names if mc.secret_keys(masked[n])
        },
    }


def apply_base(backup_path, staging_dir, choices, claude_json_path=None, base_dir=ss.BASE_DIR):
    """복원 후 로컬 기준으로 다음 base를 계산하고 override 두 개를 적용해 스테이징에 쓴다.

    ① next_base(복원 후 로컬, 이전 base, 레포)  — 입력의 redact는 next_base가 한다
    ② keep_stale(케이스 4·5의 "유지")   → base에서 이름 삭제  (그 이력은 잊는다)
    ③ keep_local(케이스 8·9의 "로컬 유지") → base[x] ← 레포 값 (그 이력은 잊는다)

    override가 없으면 두 종류의 "유지"가 "나중에"와 구별되지 않아 고정점에 도달하지
    못한다(7.4·7.7). 반대로 "레포 값 채택"과 "제거"에는 override가 없다 —
    next_base가 이미 하는 일을 중복하지 않는 것이 규칙이다.

    **이 함수는 .tmp+rename 규칙에서 제외된다.** 그 규칙은 "레포 쓰기가 성공한 뒤에
    rename"인데 apply-base에는 **레포 쓰기가 없다.** 그대로 적용하면 rename 트리거가
    영영 오지 않아 SKILL.md의 게이트가 언제나 거짓이 되고, restore 경로의 base가
    전혀 전진하지 않는다 — keep_stale/keep_local 선택이 전부 무효가 된다.
    여기서는 **파일 존재가 곧 "계산 성공"**이다(spec 9.3.7).
    """
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    nb = mc.next_base(local, base, repo)
    keep_stale = [n for n in choices.get("keep_stale", []) if isinstance(n, str)]
    keep_local = [n for n in choices.get("keep_local", []) if isinstance(n, str)]
    for name in keep_stale:
        nb.pop(name, None)
    masked = mc.redact(repo)
    kept_local = []
    for name in keep_local:
        if name in masked:
            nb[name] = masked[name]
            kept_local.append(name)
    os.makedirs(staging_dir, exist_ok=True)
    mc.dump_backup(nb, os.path.join(staging_dir, mc.BACKUP_RELPATH))
    return {
        "status": "ok",
        "kept_stale": keep_stale,
        "kept_local": kept_local,
        "base_names": sorted(nb),
    }


def read_choices(path):
    """{"keep_stale": [...], "keep_local": [...]} — 이름과 선택만 담긴다. 비밀은 없다."""
    with open(path, "rb") as f:
        data = json.loads(f.read())
    if not isinstance(data, dict):
        raise ValueError("선택 결과 JSON의 최상위가 객체가 아님: %s" % path)
    return data


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    elif len(args) == 4 and args[0] == "apply-base":
        runner = lambda: apply_base(args[1], args[2], read_choices(args[3]))  # noqa: E731
    else:
        print("사용: plan_mcp.py plan <레포의 mcp-servers.json 경로>", file=sys.stderr)
        print("      plan_mcp.py apply-base <레포의 mcp-servers.json 경로>"
              " <스테이징 디렉토리> <선택 결과 JSON 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = runner()
    # 세 스크립트(collect_mcp·compare_mcp·plan_mcp)가 같은 튜플을 쓴다. 갈리면
    # 한쪽만 traceback으로 죽는다.
    # ValueError를 잡는 이유 둘: 선택 결과 JSON이 깨졌을 때(read_choices,
    # json.JSONDecodeError도 ValueError의 하위다)와, 코어(keyed_sync)가 normalize 계약
    # 위반 — 훅이 키 집합을 바꾼 경우 — 을 ValueError로 던질 때다. 어느 쪽도 restore
    # 흐름 전체를 traceback으로 세우지 않는다.
    # BrokenBackupSyntax = 레포 문서의 구문 깨짐 → **MCP 단계 전체 skip**(spec 9.3.6).
    # 접지 않고 "서버 0개"로 읽으면 레포의 모든 서버가 케이스 4로 떨어져, 파일 하나가
    # 깨졌을 뿐인데 "다른 기기가 지웠으니 이 기기에서도 지웁시다"가 status ok로 나간다.
    except (mc.LocalConfigUnavailable, mc.UnknownBackupSchema,
            mc.BrokenBackupSyntax, OSError, ValueError) as e:
        out = report.skipped(e)
        print("MCP 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
