#!/usr/bin/env python3
"""복원 계획 수립과 base 계산. 로컬 상태를 직접 바꾸지 않는다.

사용:
  plan_mcp.py plan <레포의 mcp-servers.json 경로>
    복원 계획 JSON을 stdout에 낸다 (버킷 9개 + configs + secret_keys).

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
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402

# 등록·채택 대상 버킷. SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이 되살아나므로
# 등록에 쓸 config를 계획에 함께 실어 준다. 값은 redact를 거쳐 비밀이 없다.
NEEDS_CONFIG = ("add", "needs_secret", "repo_ahead", "both_changed")


def build_plan(backup_path, claude_json_path=None, base_dir=ss.BASE_DIR):
    """restore_plan 결과에 등록용 레포 config(마스킹됨)를 덧붙여 반환한다."""
    local = mc.read_local_servers(claude_json_path)
    repo = mc.load_backup(backup_path)
    base = mc.parse_base(ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir))
    plan = mc.restore_plan(local, repo, base)
    masked = mc.redact(repo)
    names = sorted({n for bucket in NEEDS_CONFIG for n in plan[bucket]})
    out = {"status": "ok"}
    out.update(plan)
    out["configs"] = {n: masked[n] for n in names}
    out["secret_keys"] = {
        n: mc.secret_keys(masked[n]) for n in names if mc.secret_keys(masked[n])
    }
    return out


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    else:
        print("사용: plan_mcp.py plan <레포의 mcp-servers.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = runner()
    except (mc.LocalConfigUnavailable, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("MCP 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
