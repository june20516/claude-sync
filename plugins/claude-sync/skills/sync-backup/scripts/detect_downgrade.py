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
    """v2 객체였던 마지막 커밋과, 상위 스키마 문서를 건너뛰었는지.

    반환: (candidate_dict_or_None, newer_seen)

    --diff-filter=d로 **삭제 커밋을 목록에서 애초에 뺀다.** 그러면 남은 커밋에는 파일이
    반드시 존재하므로 git show 실패는 곧 "레포가 손상됐다"는 뜻이 되어 그대로 전파해도
    된다. try/except로 감싸 continue하면 레포 손상이 "v2가 없음"으로 접혀, 사용자에게
    "되돌릴 지점이 없다"는 사실이 아닐 수 있는 결론이 전달된다(불변식 6).
    """
    out = _git(
        repo_path,
        ["log", "--diff-filter=d", "--format=%H%x09%ad%x09%s", "--date=short",
         "--", mc.BACKUP_RELPATH],
    )
    newer_seen = False
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        blob = _git(repo_path, ["show", "%s:%s" % (sha, mc.BACKUP_RELPATH)])
        if compat.shape_of(blob, mc.BACKUP_RELPATH) != compat.SHAPE_V2_OBJECT:
            continue
        # parse_backup이 아니라 parse_base를 쓴다. parse_backup은 알아볼 수 없는 문서를
        # {}로 degrade하므로 상위 버전 백업이 "서버 0개인 정상 백업"으로 제시된다.
        # mcp_config가 명시적으로 금지하는 접기다(불변식 6).
        servers = mc.parse_base(blob)
        if servers is None:
            newer_seen = True
            continue          # 상위 버전이 쓴 문서다. 0개라고 단언하지 않는다
        return {
            "sha": sha,
            "date": date,
            "subject": subject,
            "server_count": len(servers),
            "server_names": sorted(servers),
        }, newer_seen
    return None, newer_seen


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
    return compat.shape_of(raw, mc.BACKUP_RELPATH)


def _base_shape(base_dir):
    """base 블롭의 형태. read_base는 없으면 None, 그 외 OSError는 전파한다."""
    try:
        raw = ss.read_base(mc.BACKUP_RELPATH, base_dir=base_dir)
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw, mc.BACKUP_RELPATH)


def detect(repo_path, base_dir=ss.BASE_DIR):
    """{"status", "downgrade_suspected", "repo_shape", "base_shape", "candidate"}

    repo_shape·base_shape를 항상 출력에 싣는다 — 탐지하지 못한 경우에도 왜 못 했는지가
    호출부에 드러나야 한다(불변식 6). SKILL.md가 "탐지할 수 없었다"와 "사고가 없다"를
    구별해 보고할 수 있는 근거가 이것이다.
    """
    repo_shape = _shape_of_file(os.path.join(repo_path, mc.BACKUP_RELPATH))
    base_shape = _base_shape(base_dir)
    suspected = compat.downgrade_suspected(repo_shape, base_shape, mc.BACKUP_RELPATH)
    out = {
        "status": "ok",
        "downgrade_suspected": suspected,
        "repo_shape": repo_shape,
        "base_shape": base_shape,
        "candidate": None,
        # 히스토리에 이 버전이 알아보지 못하는 백업이 있었는가.
        # "후보 없음"과 "상위 버전 문서라 건너뜀"은 다른 말이다.
        "newer_schema_seen": False,
    }
    if suspected:
        try:
            out["candidate"], out["newer_schema_seen"] = find_last_v2_commit(repo_path)
        except (RuntimeError, OSError) as e:
            return _skipped(str(e), suspected, repo_shape, base_shape)
    return out


def _skipped(reason, suspected=False, repo_shape=None, base_shape=None):
    """탐지를 못 한 경우의 보고. **키 모양을 detect의 정상 경로와 같게 유지한다.**

    소비하는 쪽이 out.get("downgrade_suspected")를 볼 때 키가 없으면 None(falsy)이 되어
    또 한 번 "사고 없음"처럼 읽힌다(불변식 6).
    """
    return {
        "status": "skipped",
        "reason": reason,
        "downgrade_suspected": suspected,
        "repo_shape": repo_shape,
        "base_shape": base_shape,
        "candidate": None,
        "newer_schema_seen": False,
    }


def main():
    if len(sys.argv) != 2:
        print("사용: detect_downgrade.py <레포 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = detect(sys.argv[1])
    except Exception as e:  # noqa: BLE001 — 마지막 방어선
        # OSError만 잡으면 downgrade_suspected가 던지는 ValueError를 놓쳐 트레이스백으로
        # 죽고, "탐지 실패가 백업을 막으면 안 된다"는 이 스크립트의 원칙이 무너진다.
        out = _skipped("%s: %s" % (type(e).__name__, e))
        print("다운그레이드 탐지 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
