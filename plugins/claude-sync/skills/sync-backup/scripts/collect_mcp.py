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
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402


def collect(repo_path, staging_dir, claude_json_path=None, base_dir=ss.BASE_DIR):
    """merge 결과를 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    스테이징을 먼저 쓴다 — 레포 쓰기가 실패하면 status가 skipped가 되고
    SKILL.md가 update_base.py를 호출하지 않으므로 base는 전진하지 않는다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo_file = os.path.join(repo_path, mc.BACKUP_RELPATH)
    repo = mc.load_backup(repo_file)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    result = mc.merge(local, repo, base)
    servers = result["servers"]
    os.makedirs(staging_dir, exist_ok=True)
    mc.dump_backup(result["next_base"], os.path.join(staging_dir, mc.BACKUP_RELPATH))
    mc.dump_backup(servers, repo_file)
    return {
        "status": "ok",
        "conflicts": {
            "repo_kept": [n for n in result["conflicts"] if n in servers],
            "repo_absent": [n for n in result["conflicts"] if n not in servers],
        },
        "deleted": result["deleted"],
        "local_stale": result["local_stale"],
        "repo_ahead": {
            "present": [n for n in result["repo_ahead"] if n in local],
            "absent": [n for n in result["repo_ahead"] if n not in local],
        },
    }


def main():
    if len(sys.argv) != 3:
        print("사용: collect_mcp.py <레포 경로> <스테이징 디렉토리>", file=sys.stderr)
        sys.exit(1)
    try:
        out = collect(sys.argv[1], sys.argv[2])
    except (mc.LocalConfigUnavailable, OSError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("MCP 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
