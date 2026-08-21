#!/usr/bin/env python3
"""백업 시점의 파일별 내용 해시(sha256)와 버전 표식을 기록한다. mtime 미사용.

표식 세 필드의 성격이 다르다:
- written_by_version: 정보. 판정에 쓰지 않는다.
- min_reader_version: **판정 근거.** 이것 하나가 backup 게이트다.
- schema: 사람이 읽는 요약. 판정 근거가 아니다 — 항목별 보류는 각 파일 자체의
  version 필드로 한다(spec 결정 2).
"""
import hashlib
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import compat  # noqa: E402
import mcp_config as mc  # noqa: E402


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
    """
    metadata = {"files": {}}
    metadata["files"].update(collect(os.path.join(claude_dir, "agents"), "agents"))
    metadata["files"].update(collect(os.path.join(claude_dir, "skills"), "skills"))
    metadata["files"].update(collect(os.path.join(claude_dir, "CLAUDE.md"), "CLAUDE.md"))
    written_by = compat.read_plugin_version(plugin_json_path)
    if written_by is not None:
        metadata["written_by_version"] = written_by
    metadata["min_reader_version"] = compat.MIN_READER_VERSION
    metadata["schema"] = {mc.BACKUP_RELPATH: mc.SCHEMA_VERSION}
    return metadata


def write_metadata(output_path, metadata):
    """sort_keys로 바이트를 안정화한다 — os.walk 순서 때문에 매 백업마다 diff가 생기면
    표식 파일 자체가 소음이 된다."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


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
