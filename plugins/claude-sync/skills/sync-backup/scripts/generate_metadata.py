#!/usr/bin/env python3
"""백업 시점의 파일별 내용 해시(sha256)와 버전 표식을 기록한다. mtime 미사용.

**레포 작업 트리를 걷는다 — `~/.claude`가 아니다.** 7단계 시점의 레포 트리가 정의상
"이 백업이 담는 내용"이다: 4단계가 push 복사와 `.syncignore` 삭제를 마쳤고, reject 파일은
옛 레포 판본 그대로이며, 다른 기기가 올린 파일은 거기 있다. 앞 판은 `~/.claude`를 걸어
**이 기기의 로컬**을 적었고, 그래서 표식이 레포에 없는 내용(reject 파일의 로컬 해시)을
레포 것이라 말하고 다른 기기의 파일은 통째로 빠뜨렸다(실측 — 2026-09-01, spec 3.3).

그래서 `.syncignore`를 읽지 않는다. 제외 파일은 4단계가 레포 트리에서 이미 지웠으므로
여기서 다시 거를 것이 없다 — 제외의 근거가 필터에서 구조로 옮겨 갔다. 매칭 규칙의
소비자는 `~/.claude`를 걷는 둘(check_status.py·reconcile_backup.py)이다.

표식 세 필드의 성격이 다르다:
- written_by_version: 정보. 판정에 쓰지 않는다.
- min_reader_version: **판정 근거.** 이것 하나가 backup 게이트다.
- schema: 사람이 읽는 요약. 판정 근거가 아니다 — 항목별 보류는 각 파일 자체의
  version 필드로 한다(spec 결정 2). 이 맵을 읽는 코드도 산문도 없다. 세 SKILL.md가
  읽는 것은 detect_downgrade의 출력(`newer_schema_seen`·`broken_syntax`)이지 이 맵이
  아니다. 백업 문서 **둘 다** 싣는다.
"""
import hashlib
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import compat  # noqa: E402
import keyed_sync as ks  # noqa: E402
import mcp_config as mc  # noqa: E402
import plugin_config as pc  # noqa: E402
import sync_state as ss  # noqa: E402


def file_sha256(path):
    """파일의 sha256 hex. 파일이 없으면(끊어진 심볼릭 링크 포함) None.

    (PermissionError 등 그 외 OSError는 전파한다 — sync_state.file_hash와 같은 관례.)
    표식 생성 전체가 죽는 것보다 파일 하나가 빠지는 것이 싸다. 죽으면 표식 없는
    백업이 푸시된다.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read())
    except FileNotFoundError:
        return None
    return h.hexdigest()


def build_metadata(tree_root, plugin_json_path):
    """표식이 붙은 메타데이터 dict. `files`는 tree_root의 동기화 대상 전부다.

    **tree_root는 기본값 없는 필수 인자다.** 기본값을 `~/.claude`로 두면 갱신되지 않은
    호출자가 조용히 옛 동작(로컬을 적는다)으로 돌아간다 — compat.shape_of의 relpath와
    같은 이유다. 걷는 집합은 sync_state.iter_synced_relpaths가 정한다(agents/·skills/·
    CLAUDE.md) — 세 소비자와 같은 정의라야 표식의 키 집합이 판정의 집합과 같다.
    끊어진 심볼릭 링크는 건너뛴다 — os.walk가 그것을 파일로 열거하고 file_sha256이 None을
    돌려준다. 표식 생성 전체가 죽는 것보다 파일 하나가 빠지는 것이 싸다.

    plugin.json을 못 읽으면 written_by_version을 생략한다 — 자기 버전을 모르는 것이
    파일 해시를 못 쓸 이유는 아니다. min_reader_version은 상수이므로 이 경우에도
    정상 기록된다.
    """
    files = {}
    for rel in sorted(ss.iter_synced_relpaths(tree_root)):
        digest = file_sha256(os.path.join(tree_root, rel))
        if digest is None:
            print("건너뜀(읽을 수 없음): %s" % rel, file=sys.stderr)
            continue
        files[rel] = digest
    metadata = {"files": files}
    written_by = compat.read_plugin_version(plugin_json_path)
    if written_by is not None:
        metadata["written_by_version"] = written_by
    metadata["min_reader_version"] = compat.MIN_READER_VERSION
    # **백업 문서 둘 다 싣는다**(version-compat spec 5.3의 약속). 상수를 각 모듈에서
    # 뽑는다 — 리터럴을 적으면 SCHEMA_VERSION이 올라가도 표식만 조용히 옛 값을 말한다.
    metadata["schema"] = {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION,
                          pc.BACKUP_RELPATH: pc.SCHEMA_VERSION}
    return metadata


def write_metadata(output_path, metadata):
    """sort_keys로 바이트를 안정화한다 — os.walk 순서 때문에 매 백업마다 diff가 생기면
    표식 파일 자체가 소음이 된다.

    **`ks.dump_json`으로 원자적으로 쓴다.** 7단계는 이 파일을 레포 작업 트리에 직접
    쓰고 10단계의 `git add -A`가 그것을 커밋·푸시한다. 평범한 `open(path, "w")`는
    선-truncate라 쓰기 도중 실패(ENOSPC/EIO/SIGKILL)가 **잘린 JSON을 남기고 그대로
    푸시된다.** 그러면 모든 기기에서 `compat.load_metadata`가 None이 되고
    `_block_reason`이 `raw_min is None`을 보고 차단하지 않는다 — 이 파일 하나가
    `min_reader_version` 게이트의 유일한 입력이라, 어느 기기든 정상 백업으로 덮을
    때까지 **전 기기에서 게이트가 조용히 꺼진다.**"""
    ks.dump_json(metadata, output_path)


def main():
    if len(sys.argv) != 3:
        # 파일명을 리터럴로 다시 쓰지 않는다 — 쓰는 쪽과 읽는 쪽이 다른 파일을 보면
        # 표식이 있는데도 없는 것으로 판정되는 무증상 고장이 된다.
        print("사용: generate_metadata.py <출력 경로 (예: $SYNC_REPO/%s)> <레포 작업 트리>"
              % compat.METADATA_RELPATH, file=sys.stderr)
        sys.exit(1)
    output_path, tree_root = sys.argv[1], sys.argv[2]
    metadata = build_metadata(tree_root, compat.default_plugin_json_path())
    if "written_by_version" not in metadata:
        print(
            "경고: plugin.json에서 버전을 읽지 못해 written_by_version을 생략했습니다.",
            file=sys.stderr,
        )
    write_metadata(output_path, metadata)


if __name__ == "__main__":
    main()
