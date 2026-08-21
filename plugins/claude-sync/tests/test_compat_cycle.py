"""반복 적용·교대 적용 — 상태 기계가 발산하거나 흔적을 남기지 않는지 본다.

실제 ~/.claude는 건드리지 않는다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts")
)

import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import collect_mcp  # noqa: E402
import generate_metadata as gm  # noqa: E402

COMPAT_CLI = os.path.join(os.path.dirname(__file__), "..", "lib", "compat.py")


def fake_claude_dir(tmp_path):
    d = tmp_path / "claude"
    (d / "agents").mkdir(parents=True)
    (d / "agents" / "a.md").write_text("a", encoding="utf-8")
    (d / "CLAUDE.md").write_text("c", encoding="utf-8")
    return str(d)


def plugin_json(tmp_path, version="3.0.0"):
    path = tmp_path / "plugin.json"
    path.write_text(json.dumps({"version": version}), encoding="utf-8")
    return str(path)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def dir_snapshot(path):
    out = {}
    for root, _, files in os.walk(path):
        for f in files:
            full = os.path.join(root, f)
            out[os.path.relpath(full, path)] = read_bytes(full)
    return out


def test_metadata_stable_across_three_runs(tmp_path):
    """세 번 돌려도 바이트가 같아야 한다. 매번 diff가 나면 표식이 소음이 된다."""
    claude_dir, pj = fake_claude_dir(tmp_path), plugin_json(tmp_path)
    outs = []
    for i in range(3):
        p = str(tmp_path / ("m%d.json" % i))
        gm.write_metadata(p, gm.build_metadata(claude_dir, pj))
        outs.append(read_bytes(p))
    assert outs[0] == outs[1] == outs[2]


def test_repeated_backup_does_not_diverge(tmp_path):
    """같은 로컬로 collect를 두 번 돌리면 레포 파일과 base가 그대로여야 한다."""
    local = tmp_path / "claude.json"
    local.write_text(json.dumps({"mcpServers": {"a": {"command": "a"}}}), encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    staging = str(tmp_path / "staging")
    base_dir = str(tmp_path / "base")

    collect_mcp.collect(str(repo), staging, claude_json_path=str(local), base_dir=base_dir)
    # 1회차 결과를 base로 올린다 (SKILL.md 11단계가 하는 일)
    os.makedirs(base_dir, exist_ok=True)
    with open(os.path.join(base_dir, mc.BACKUP_RELPATH), "wb") as f:
        f.write(read_bytes(os.path.join(staging, mc.BACKUP_RELPATH)))
    first = read_bytes(os.path.join(str(repo), mc.BACKUP_RELPATH))

    collect_mcp.collect(str(repo), staging, claude_json_path=str(local), base_dir=base_dir)
    second = read_bytes(os.path.join(str(repo), mc.BACKUP_RELPATH))
    assert first == second


def test_block_then_unblock_leaves_no_state(tmp_path):
    """교대 적용: 차단됐다가 해제되면 흔적 없이 통과한다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    meta_path = repo / compat.METADATA_RELPATH
    pj = plugin_json(tmp_path, "3.0.0")

    meta_path.write_text(json.dumps({"min_reader_version": "4.0.0"}), encoding="utf-8")
    blocked_before = dir_snapshot(str(repo))
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is True
    assert dir_snapshot(str(repo)) == blocked_before   # 차단이 레포를 건드리지 않았다

    meta_path.write_text(json.dumps({"min_reader_version": "3.0.0"}), encoding="utf-8")
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is False

    meta_path.write_text(json.dumps({"min_reader_version": "4.0.0"}), encoding="utf-8")
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is True


def test_cli_usage_error_is_clean(tmp_path):
    """가짜 안전망 방지 — sys.exit(1)이 없어도 IndexError가 exit 1을 대신 만든다.

    종료 코드만 보면 변이를 못 잡는다. 트레이스백이 없고 stdout이 비어 있어야
    "의도된 사용법 오류"이며, 인자를 두 개 준 경우도 함께 본다(그 경로는 변이 시 exit 0이 된다).
    """
    for argv in ([], [str(tmp_path), "extra"]):
        proc = subprocess.run([sys.executable, COMPAT_CLI] + argv,
                              capture_output=True, text=True)
        assert proc.returncode == 1, argv
        assert "사용:" in proc.stderr
        assert "Traceback" not in proc.stderr, argv
        assert proc.stdout == "", argv


def test_gate_keeps_boolean_version_readable(tmp_path):
    """{"version": true}가 통과함을 고정한다 — bool 제외가 의도임을 문서화한다."""
    path = tmp_path / "mcp-servers.json"
    path.write_text(json.dumps({"version": True, "servers": {"a": {"command": "a"}}}),
                    encoding="utf-8")
    assert mc.load_backup(str(path)) == {"a": {"command": "a"}}


def test_check_is_idempotent(tmp_path):
    """같은 입력이면 몇 번을 불러도 같은 판정이다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / compat.METADATA_RELPATH).write_text(
        json.dumps({"min_reader_version": "4.0.0", "written_by_version": "4.0.0"}),
        encoding="utf-8",
    )
    pj = plugin_json(tmp_path)
    results = [compat.check(str(repo), plugin_json_path=pj) for _ in range(5)]
    assert all(r == results[0] for r in results)


def test_upgrade_then_write_marker_unblocks_older_repo(tmp_path):
    """3.0.0이 쓴 레포는 3.0.0이 다시 읽을 수 있다 — 자기가 자기를 막지 않는다."""
    claude_dir, pj = fake_claude_dir(tmp_path), plugin_json(tmp_path, "3.0.0")
    repo = tmp_path / "repo"
    repo.mkdir()
    gm.write_metadata(
        str(repo / compat.METADATA_RELPATH), gm.build_metadata(claude_dir, pj)
    )
    assert compat.check(str(repo), plugin_json_path=pj)["blocked"] is False
