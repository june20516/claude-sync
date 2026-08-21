#!/usr/bin/env python3
"""다운그레이드 사고를 탐지하고 마지막 정상(v2) 백업 커밋을 찾는다 (읽기 전용).

사용: detect_downgrade.py <레포 경로>

레포의 mcp-servers.json이 v1 배열인데 이 기기의 base는 v2 객체였다면, 옛 버전 기기가
덮어쓴 것이다. git 히스토리를 훑어 마지막 v2 커밋을 후보로 제시한다.

**자동으로 복구하지 않는다** — 옛 기기가 의도적으로 지운 서버까지 되살리기 때문이다.
탐지 실패가 백업을 막아서도 안 된다. 부가 기능이므로 status=skipped로 물러난다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import sync_state as ss  # noqa: E402


def _git(repo_path, args):
    """git 표준 출력(bytes). 실패하면 RuntimeError."""
    proc = subprocess.run(["git", "-C", repo_path] + args, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "git 실패")
    return proc.stdout


def find_last_v2_commit(repo_path):
    """mcp-servers.json이 v2 객체였던 마지막 커밋. 없으면 None."""
    out = _git(
        repo_path,
        ["log", "--format=%H%x09%ad%x09%s", "--date=short", "--", mc.BACKUP_RELPATH],
    )
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        try:
            blob = _git(repo_path, ["show", "%s:%s" % (sha, mc.BACKUP_RELPATH)])
        except RuntimeError:
            continue          # 그 커밋에는 파일이 없었다. 탐색은 계속한다
        if compat.shape_of(blob) != compat.SHAPE_V2_OBJECT:
            continue
        servers = mc.parse_backup(blob)
        return {
            "sha": sha,
            "date": date,
            "subject": subject,
            "server_count": len(servers),
            "server_names": sorted(servers),
        }
    return None


def _shape_of_file(path):
    """파일을 읽어 형태를 판정한다.

    **못 읽음을 absent로 접지 않는다(불변식 6).** absent는 "파일이 없다"는 결론이지만
    권한·IO 실패는 아무 결론도 아니다. 접으면 다운그레이드 탐지가 조용히 꺼진다.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return compat.SHAPE_ABSENT
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw)


def _base_shape(base_dir):
    """base 블롭의 형태. read_base는 없으면 None, 그 외 OSError는 전파한다."""
    try:
        raw = ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir)
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw)


def detect(repo_path, base_dir=ss.BASE_DIR):
    """{"status", "downgrade_suspected", "repo_shape", "base_shape", "candidate"}

    repo_shape·base_shape를 항상 출력에 싣는다 — 탐지하지 못한 경우에도 왜 못 했는지가
    호출부에 드러나야 한다(불변식 6). SKILL.md가 "탐지할 수 없었다"와 "사고가 없다"를
    구별해 보고할 수 있는 근거가 이것이다.
    """
    repo_shape = _shape_of_file(os.path.join(repo_path, mc.BACKUP_RELPATH))
    base_shape = _base_shape(base_dir)
    suspected = compat.downgrade_suspected(repo_shape, base_shape)
    out = {
        "status": "ok",
        "downgrade_suspected": suspected,
        "repo_shape": repo_shape,
        "base_shape": base_shape,
        "candidate": None,
    }
    if suspected:
        try:
            out["candidate"] = find_last_v2_commit(repo_path)
        except (RuntimeError, OSError) as e:
            return {"status": "skipped", "reason": str(e),
                    "downgrade_suspected": suspected,
                    "repo_shape": repo_shape, "base_shape": base_shape,
                    "candidate": None}
    return out


def main():
    if len(sys.argv) != 2:
        print("사용: detect_downgrade.py <레포 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = detect(sys.argv[1])
    except OSError as e:
        out = {"status": "skipped", "reason": str(e)}
        print("다운그레이드 탐지 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
