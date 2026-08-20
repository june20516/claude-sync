#!/usr/bin/env python3
"""로컬 user 스코프 MCP 설정과 레포 백업의 차이를 보고한다 (읽기 전용).

사용: compare_mcp.py <레포의 mcp-servers.json 경로>

정규식도 `claude mcp list` 파이프도 쓰지 않는다. 판정은 mcp_config.diff 하나만
쓴다 — status와 backup이 서로 다른 파서를 갖는 것이 Bug #2의 원인이었다.
base는 읽지도 갱신하지도 않는다(읽기 전용 스킬).
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import mcp_config as mc  # noqa: E402


def compare(backup_path, claude_json_path=None):
    """{"status": "ok", "only_local": [...], "only_repo": [...], "changed": [...]}

    diff가 양쪽에 redact를 적용하므로 로컬 평문과 레포 마스킹이 in_sync로 수렴한다.
    """
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    out = {"status": "ok"}
    out.update(mc.diff(local, repo))
    return out


def main():
    if len(sys.argv) != 2:
        print("사용: compare_mcp.py <레포의 mcp-servers.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = compare(sys.argv[1])
    except (mc.LocalConfigUnavailable, OSError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("MCP 비교 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
