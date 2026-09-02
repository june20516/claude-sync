#!/usr/bin/env python3
"""레포의 mcp-servers.json에서 복원 불가 항목을 지운다 — 백업 6.5단계의 「레포에서 정리한다」.

사용: prune_mcp.py <레포 경로> <이름> [<이름> ...]
출력: {"status": "ok", "pruned": [...], "not_found": [...], "refused": {이름: 사유}}

**레포에서 그 항목이 나갈 수 있는 유일한 경로다**(spec 4.3). 어느 기기의 로컬에도 없는
항목은 base에 실릴 수 없고, 삭제 전파는 "base에 있고 로컬에서 사라짐"이라야 일어나므로
병합으로는 영원히 남는다(실측 — 2026-09-01, 2.x가 긁어 넣은 계정 커넥터 7개).

**거부 둘** — 잘못 배선된 이름을 조용히 지우지 않는다. 거부는 예외가 아니라 출력이다.
로컬에 있는 이름(사용자의 실제 설정이다)과 복원 가능한 이름(정리 대상이 아니다)은 지우지
않고 `refused`에 사유와 함께 싣는다. 이름은 6.5단계가 6단계 출력의 `unrestorable`을 그대로
넘기므로 정상 흐름에서 거부는 비어 있다.

**base·스테이징은 건드리지 않는다.** 지워지는 이름은 로컬에 없어 next_base에 애초에 실리지
않는다(keyed_sync._next_base_normalized — merged에 있고 local에 없으면 이전 base에 있을
때만 유지되는데, 로컬이 동의한 적 없는 이름은 base에 없다). test_mcp_cycle의 고정점이
그것을 건다. 커밋·푸시는 10단계가 한다 — 별도 커밋을 만들지 않는다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import report  # noqa: E402
import mcp_config as mc  # noqa: E402


def prune(repo_path, names, claude_json_path=None):
    """names 중 레포에 있고·로컬에 없고·복원 불가인 것만 지운다. 지운 것이 없으면 쓰지 않는다.

    load_backup이 구문 깨짐·미지 스키마에 예외를 던지므로 **쓰기 앞에서** 멈춘다 — 그 갈래의
    skipped("레포 파일은 손대지 않았다")가 참이다. 쓰기는 dump_backup(원자적)이다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo_file = os.path.join(repo_path, mc.BACKUP_RELPATH)
    repo = mc.load_backup(repo_file)
    pruned, not_found, refused = [], [], {}
    for name in dict.fromkeys(names):            # 순서 유지, 중복 무시
        if name not in repo:
            not_found.append(name)
        elif name in local:
            refused[name] = "로컬에 있는 서버는 지우지 않는다 — 사용자의 실제 설정이다"
        elif mc.restorable(name, repo[name]):
            refused[name] = "복원 가능한 항목은 지우지 않는다 — 정리 대상이 아니다"
        else:
            pruned.append(name)
    if pruned:
        mc.dump_backup({n: cfg for n, cfg in repo.items() if n not in pruned}, repo_file)
    return {"status": "ok", "pruned": pruned, "not_found": not_found, "refused": refused}


def main():
    if len(sys.argv) < 3:
        print("사용: prune_mcp.py <레포 경로> <이름> [<이름> ...]", file=sys.stderr)
        sys.exit(1)
    try:
        out = prune(sys.argv[1], sys.argv[2:])
    # 다른 MCP 스크립트 셋과 같은 튜플. 갈리면 한쪽만 traceback으로 죽는다.
    except (mc.LocalConfigUnavailable, mc.UnknownBackupSchema,
            mc.BrokenBackupSyntax, OSError, ValueError) as e:
        out = report.skipped(e)
        print("정리 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
