#!/usr/bin/env python3
"""로컬 user 스코프 MCP 설정을 레포와 키 단위 3-way 병합한다.

사용: collect_mcp.py <레포 경로> <스테이징 디렉토리>

`claude mcp list`를 호출하지 않고 stdin도 받지 않는다 — 데이터 소스는
~/.claude.json의 top-level mcpServers뿐이다(spec 3장).

base는 이 스크립트가 쓰지 않는다. 커밋 전에 실행되기 때문이다(7.5).
next_base를 스테이징 디렉토리에 mcp-servers.json이라는 이름으로 써 두고,
레포가 실제로 그 내용을 갖게 된 뒤 SKILL.md가
update_base.py <스테이징 디렉토리> mcp-servers.json 으로 옮긴다.
레포를 source_root로 넘기면 base ← 레포 파일 바이트가 되어 7.3을 위반한다.
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


def collect(repo_path, staging_dir, claude_json_path=None, base_dir=ss.BASE_DIR):
    """merge 결과를 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    스테이징은 <rel>.tmp로 먼저 쓰고 **레포 쓰기가 성공한 뒤에** <rel>로 rename한다.
    스테이징 최종 파일의 존재가 곧 "레포까지 반영됨"을 뜻해야 하기 때문이다 —
    SKILL.md의 base 갱신 게이트가 그 파일의 존재만 보고 판단한다.
    먼저 최종 이름으로 쓰면 레포 쓰기가 실패해도 게이트가 통과해 base가 전진하고,
    다음 백업이 이 기기 자신의 서버를 케이스 4로 오독한다.

    **레포 문서의 구문이 깨졌으면 load_backup이 BrokenBackupSyntax를 던진다** — 쓰기
    앞이므로 레포도 스테이징도 손대지 않은 채 main()이 문서 단위 skipped로 접는다.
    "서버 0개"로 읽고 병합을 계속하면 레포에만 있던 다른 기기의 서버가 케이스 4로
    지워지고 그 결과가 status "ok"로 보고된다(spec 9.1.2, 실측).

    **전제: 호출부가 실행마다 스테이징 디렉토리를 한 번 비운다**(SKILL.md의 rm -rf).
    os.replace가 실패하면 <rel>.tmp가 남는데, 그것이 무해한 이유가 이 전제다.
    spec 7.4의 배선이 스테이징 디렉토리를 플러그인 수집과 공유하므로 이 성질이
    유지되려면 rm -rf가 **수집 단계들보다 앞에서 딱 한 번** 실행되어야 한다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo_file = os.path.join(repo_path, mc.BACKUP_RELPATH)
    repo = mc.load_backup(repo_file)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    result = mc.merge(local, repo, base)
    servers = result["servers"]

    os.makedirs(staging_dir, exist_ok=True)
    staged = os.path.join(staging_dir, mc.BACKUP_RELPATH)
    tmp = staged + ".tmp"
    mc.dump_backup(result["next_base"], tmp)
    mc.dump_backup(servers, repo_file)

    # 이 블록이 **쓰기 뒤에** 있어도 되는 이유는 예외를 던질 수 없는 순수 계산이기
    # 때문이다. collect_plugins는 반대로 쓰기 **앞에** 둔다 — 거기 보고 블록은
    # held_kinds를 부르고 그것이 분류 불가에 ValueError를 던지기 때문이다.
    # 던질 수 있는 계산이 여기 들어오면 그때 앞으로 옮긴다: 레포를 이미 고친 뒤에
    # 던지면 그 예외가 부르는 skipped의 문구("레포 파일은 손대지 않았다")가 거짓이 된다.
    out = {
        "status": "ok",
        # 분할은 보고 층 한 벌이다(lib/report.py) — collect_plugins가 같은 모양을
        # 축자로 복제하고 있었고, 한쪽만 고쳐지는 자리였다.
        "conflicts": report.split_conflicts(result["conflicts"], servers),
        "deleted": result["deleted"],
        "local_stale": result["local_stale"],
        "repo_ahead": report.split_repo_ahead(result["repo_ahead"], local),
    }
    try:
        os.replace(tmp, staged)
    except OSError as e:
        # 레포는 이미 갱신됐다. skipped로 접으면 "레포를 손대지 않았다"가 거짓이 된다.
        # 키 이름을 reason과 가른다 — reason은 SKILL.md "6단계 skipped 분기"의 필드다.
        out["base_staging"] = "failed"
        out["base_staging_reason"] = (
            "레포는 갱신됐으나 base 스테이징에 실패했다: %s (다음 백업이 복구한다)" % e)
    return out


def main():
    if len(sys.argv) != 3:
        print("사용: collect_mcp.py <레포 경로> <스테이징 디렉토리>", file=sys.stderr)
        sys.exit(1)
    try:
        out = collect(sys.argv[1], sys.argv[2])
    # 세 스크립트(collect_mcp·compare_mcp·plan_mcp)가 같은 튜플을 쓴다. 갈리면
    # 한쪽만 traceback으로 죽는다.
    # ValueError를 잡는 이유: 코어(keyed_sync)가 normalize 계약 위반 — 훅이 키 집합을
    # 바꾼 경우 — 을 ValueError로 던진다. 어댑터 훅의 결함 하나로 backup 흐름 전체가
    # traceback으로 서는 것을 막는다. (이 스크립트에서 살아서 도달하는 ValueError는
    # 그 계약 위반 하나뿐이다 — JSON 파싱 실패는 read_local_servers와 load_backup이
    # 각각 LocalConfigUnavailable·BrokenBackupSyntax로 이미 흡수한다.)
    # BrokenBackupSyntax = 레포 문서의 구문 깨짐. **레포 쓰기 앞에서** 던지므로 이
    # 갈래의 skipped는 "레포 파일은 손대지 않았다"가 참이다. 접지 않고 "서버 0개"로
    # 읽으면 레포에만 있던 다른 기기의 서버가 케이스 4로 지워진다(spec 9.1.2).
    except (mc.LocalConfigUnavailable, mc.UnknownBackupSchema,
            mc.BrokenBackupSyntax, OSError, ValueError) as e:
        out = report.skipped(e)
        print("MCP 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
