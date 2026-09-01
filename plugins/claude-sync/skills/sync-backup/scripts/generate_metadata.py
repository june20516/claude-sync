#!/usr/bin/env python3
"""백업 시점의 파일별 내용 해시(sha256)와 버전 표식을 기록한다. mtime 미사용.

**`.syncignore`를 존중한다.** 이 스크립트는 레포가 아니라 `~/.claude`를 직접 걷기
때문에, 4단계가 레포 작업 트리에서 지운 파일도 여기서는 그대로 보인다. 필터가 없으면
사용자가 제외한 파일의 **이름과 sha256이 푸시되는 표식 파일에 남는다.** 매칭 규칙은
lib/syncignore.py 한 곳에 있다 — 4단계의 `find -path`와 같은 규칙이다.

표식은 **푸시되는 산출물**이므로 여기서 거르는 것이 곧 규정 그대로다 —
`.syncignore`의 뜻은 "올리지 않는다"이고 backup 방향 전용이다(정본: lib/syncignore.py
모듈 docstring). 복원 쪽은 이 필터와 무관하다 — reconcile_restore.py는 제외 목록을
보지 않는다.

표식 세 필드의 성격이 다르다:
- written_by_version: 정보. 판정에 쓰지 않는다.
- min_reader_version: **판정 근거.** 이것 하나가 backup 게이트다.
- schema: 사람이 읽는 요약. 판정 근거가 아니다 — 항목별 보류는 각 파일 자체의
  version 필드로 한다(spec 결정 2). **여전히 참이다**(plan ③ Task 4에서 전수 grep:
  이 맵을 읽는 코드도 산문도 없다. 세 SKILL.md는 `newer_schema_seen`만 읽는데 그것은
  detect_downgrade의 출력이지 이 맵이 아니다). 백업 문서 **둘 다** 싣는다.
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
import syncignore  # noqa: E402


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


def collect(base, prefix):
    result = {}
    if os.path.isfile(base):
        digest = file_sha256(base)
        if digest is not None:
            result[prefix] = digest
        return result
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            for f in files:
                full = os.path.join(root, f)
                digest = file_sha256(full)
                if digest is None:
                    print("건너뜀(읽을 수 없음): %s" % full, file=sys.stderr)
                    continue
                rel = os.path.relpath(full, base)
                result[prefix + "/" + rel] = digest
    return result


def build_metadata(claude_dir, plugin_json_path):
    """표식이 붙은 메타데이터 dict.

    plugin.json을 못 읽으면 written_by_version을 생략한다 — 자기 버전을 모르는 것이
    파일 해시를 못 쓸 이유는 아니다. min_reader_version은 상수이므로 이 경우에도
    정상 기록된다.

    `.syncignore`는 `claude_dir` 안에서 찾는다 — 이 함수가 걷는 트리와 제외 목록이
    같은 곳에서 와야 테스트가 실제 `~/.claude` 없이 이 경로를 잴 수 있다.
    """
    files = {}
    files.update(collect(os.path.join(claude_dir, "agents"), "agents"))
    files.update(collect(os.path.join(claude_dir, "skills"), "skills"))
    files.update(collect(os.path.join(claude_dir, "CLAUDE.md"), "CLAUDE.md"))
    patterns = syncignore.load_patterns(syncignore.default_path(claude_dir))
    kept = syncignore.filter_relpaths(sorted(files), patterns)
    excluded = len(files) - len(kept)
    if excluded:
        print(".syncignore로 표식에서 제외: %d개" % excluded, file=sys.stderr)
    metadata = {"files": {rel: files[rel] for rel in kept}}
    written_by = compat.read_plugin_version(plugin_json_path)
    if written_by is not None:
        metadata["written_by_version"] = written_by
    metadata["min_reader_version"] = compat.MIN_READER_VERSION
    # **백업 문서 둘 다 싣는다**(version-compat spec 5.3의 약속. plan ③ Task 4).
    # 상수를 각 모듈에서 뽑는다 — 리터럴 `"plugins.json": 2`를 적으면 SCHEMA_VERSION이
    # 올라가도 표식만 조용히 옛 값을 말한다. 문서가 셋이 되면 여기와
    # test_metadata의 완전성 단정을 함께 고쳐야 한다.
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
    # 파일명을 리터럴로 다시 쓰지 않는다 — 쓰는 쪽과 읽는 쪽이 다른 파일을 보면
    # 표식이 있는데도 없는 것으로 판정되는 무증상 고장이 된다.
    output_path = sys.argv[1] if len(sys.argv) > 1 else compat.METADATA_RELPATH
    metadata = build_metadata(
        os.path.expanduser("~/.claude"), compat.default_plugin_json_path()
    )
    if "written_by_version" not in metadata:
        print(
            "경고: plugin.json에서 버전을 읽지 못해 written_by_version을 생략했습니다.",
            file=sys.stderr,
        )
    write_metadata(output_path, metadata)


if __name__ == "__main__":
    main()
