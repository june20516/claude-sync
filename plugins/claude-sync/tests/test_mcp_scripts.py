"""세 스크립트(collect_mcp / compare_mcp / plan_mcp)의 계약 테스트.

실제 ~/.claude.json과 ~/.claude/.sync-state는 절대 건드리지 않는다 —
인프로세스 호출은 claude_json_path=/base_dir= 로, CLI 호출은 env HOME= 으로 격리한다.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-status", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import mcp_config as mc  # noqa: E402
import collect_mcp  # noqa: E402
import compare_mcp  # noqa: E402
import plan_mcp  # noqa: E402

A = {"command": "a"}
B = {"command": "b"}
ORIG = {"command": "o"}
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")


def write_local(tmp_path, servers):
    """~/.claude.json 역할의 임시 파일."""
    path = tmp_path / "claude.json"
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    return str(path)


def write_repo(tmp_path, servers):
    """레포 디렉토리와 mcp-servers.json을 만든다. servers가 None이면 파일 없음."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if servers is not None:
        mc.dump_backup(servers, str(repo / mc.BACKUP_RELPATH))
    return str(repo)


def write_base_blob(tmp_path, servers):
    """base 블롭 디렉토리를 만든다. servers가 None이면 이력 없음."""
    base_dir = tmp_path / "base"
    base_dir.mkdir(exist_ok=True)
    if servers is not None:
        mc.dump_backup(servers, str(base_dir / mc.BACKUP_RELPATH))
    return str(base_dir)


def repo_servers(repo):
    return mc.load_backup(os.path.join(repo, mc.BACKUP_RELPATH))


def staged_servers(staging):
    return mc.load_backup(os.path.join(staging, mc.BACKUP_RELPATH))


def test_collect_writes_repo_and_staging(tmp_path):
    """merge 결과는 레포로, next_base는 스테이징으로 — base 블롭은 건드리지 않는다."""
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    staging = str(tmp_path / "staging")
    out = collect_mcp.collect(repo, staging, claude_json_path=local, base_dir=base_dir)
    assert out["status"] == "ok"
    assert repo_servers(repo) == {"x": A}
    assert staged_servers(staging) == {"x": A}
    assert not os.path.exists(os.path.join(base_dir, mc.BACKUP_RELPATH))


def test_collect_splits_conflicts_by_repo_presence(tmp_path):
    """케이스 9는 repo_kept, 케이스 5는 repo_absent — SKILL.md가 판정을 재구현하지 않게 한다."""
    local = write_local(tmp_path, {"nine": A, "five": B})
    repo = write_repo(tmp_path, {"nine": B})
    base_dir = write_base_blob(tmp_path, {"nine": ORIG, "five": ORIG})
    out = collect_mcp.collect(repo, str(tmp_path / "staging"),
                              claude_json_path=local, base_dir=base_dir)
    assert out["conflicts"] == {"repo_kept": ["nine"], "repo_absent": ["five"]}
    assert repo_servers(repo)["nine"] == B


def test_collect_splits_repo_ahead_by_local_presence(tmp_path):
    """케이스 8은 present(선택 필요), 케이스 2는 absent(restore가 설치) — 안내 문구가 다르다."""
    local = write_local(tmp_path, {"eight": ORIG})
    repo = write_repo(tmp_path, {"eight": B, "two": B})
    base_dir = write_base_blob(tmp_path, {"eight": ORIG})
    out = collect_mcp.collect(repo, str(tmp_path / "staging"),
                              claude_json_path=local, base_dir=base_dir)
    assert out["repo_ahead"] == {"present": ["eight"], "absent": ["two"]}


def test_collect_masks_secrets_in_repo_file(tmp_path):
    """레포 파일에 평문 비밀이 실려서는 안 된다."""
    local = write_local(tmp_path, {"c7": {"type": "http", "url": "u", "headers": {"K": "sk-real"}}})
    repo = write_repo(tmp_path, None)
    collect_mcp.collect(repo, str(tmp_path / "staging"),
                        claude_json_path=local, base_dir=write_base_blob(tmp_path, None))
    raw = open(os.path.join(repo, mc.BACKUP_RELPATH), encoding="utf-8").read()
    assert "sk-real" not in raw
    assert mc.SENTINEL in raw


def test_collect_raises_without_touching_repo_or_staging(tmp_path):
    """읽기 실패는 '서버 0개'가 아니다 — 레포도 스테이징도 그대로 둔다(9장 안전장치).

    예외를 잡아 skipped로 보고하는 주체는 main()이다(9장). 여기서는 삭제 판정을
    하지 않고 아무것도 쓰지 않는다는 것만 확인한다.
    """
    repo = write_repo(tmp_path, {"z": B})
    staging = str(tmp_path / "staging")
    with pytest.raises(mc.LocalConfigUnavailable):
        collect_mcp.collect(repo, staging,
                            claude_json_path=str(tmp_path / "missing.json"),
                            base_dir=write_base_blob(tmp_path, {"z": B}))
    assert repo_servers(repo) == {"z": B}
    assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))


# --- 레포 문서의 구문 깨짐 (spec 9.1.2 · 9.3.6, 5차 개정) ------------------
#
# **MCP는 코어를 공유하므로 플러그인과 같은 결함을 갖는다.** 한쪽만 고치면 같은 결함이
# 다른 파일에 남고, 코어를 공유한다는 사실 때문에 더 찾기 어렵다(spec 9.3.6).
# tests/test_plugin_scripts.py의 같은 이름 짝과 함께 읽을 것.

def write_broken_repo(tmp_path, servers):
    """정상 문서를 **잘린 채로** 둔 레포. ks.dump_bytes가 막으려는 그 상태다.

    깨진 내용에 theirs가 그대로 남아 있어야 "레포 파일을 손대지 않았다"가 곧 소실
    방지가 된다 — 내용을 통째로 버리면 무엇을 잃었는지 잴 수 없다.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    path = repo / mc.BACKUP_RELPATH
    mc.dump_backup(servers, str(path))
    text = path.read_text(encoding="utf-8")
    path.write_text(text[:text.rindex("}")], encoding="utf-8")   # 닫는 괄호를 잘라 낸다
    return str(repo)


def broken_or_valid_repo(tmp_path, repo_syntax, servers):
    return (write_repo(tmp_path, servers) if repo_syntax == "valid"
            else write_broken_repo(tmp_path, servers))


@pytest.mark.parametrize("repo_syntax", ["valid", "broken"])
def test_backup_never_drops_a_server_that_only_the_repo_has(tmp_path, repo_syntax):
    """9.1.2 — 레포 문서의 구문이 깨져도 레포에만 있던 서버가 사라지지 않는다.

    **실측(개정 전)**: 깨진 갈래에서 레포 파일이 {"servers": {}}로 덮이고 보고는
    status "ok" · local_stale ["mine"]이었다. mine은 이 기기에 있으니 다음 백업이
    되밀지만 **theirs는 레포에만 있던 서버라 영구 소실된다.**

    네 입력이 전부 판별력을 떠받친다(입력 축 변조로 확인) — 레포의 theirs(잃을 것),
    로컬·base의 dropped(**레포가 실제로 지운** 서버. 정상 갈래의 제안을 만든다),
    로컬의 mine(깨진 문서를 "서버 0개"로 읽으면 케이스 4로 떨어지는 것). base를 빼면
    합집합 degrade가 되어 local_stale이 비고, "못 읽어서 제안이 없다"와 "지울 것이
    없어서 제안이 없다"가 같아진다.
    """
    repo = broken_or_valid_repo(tmp_path, repo_syntax, {"mine": A, "theirs": B})
    path = os.path.join(repo, mc.BACKUP_RELPATH)
    before = open(path, encoding="utf-8").read()
    staging = str(tmp_path / "staging")
    run = lambda: collect_mcp.collect(                                  # noqa: E731
        repo, staging,
        claude_json_path=write_local(tmp_path, {"mine": A, "dropped": B}),
        base_dir=write_base_blob(tmp_path, {"mine": A, "dropped": B}))
    if repo_syntax == "valid":
        out = run()
        assert out["status"] == "ok"
        assert repo_servers(repo) == {"mine": A, "theirs": B}
        # 진짜 삭제(dropped)만 케이스 4다 — base를 빼면 이 줄이 죽는다(입력 축 변조).
        assert out["local_stale"] == ["dropped"]
    else:
        with pytest.raises(mc.BrokenBackupSyntax):
            run()
        assert open(path, encoding="utf-8").read() == before      # 바이트 그대로
        assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))
    assert "theirs" in open(path, encoding="utf-8").read()


@pytest.mark.parametrize("repo_syntax", ["valid", "broken"])
def test_restore_never_proposes_removing_on_a_broken_repo_document(tmp_path, repo_syntax):
    """9.3.6 — 깨진 레포 문서에서 "이 기기의 서버를 지웁시다"가 나가지 않는다.

    **실측(개정 전)**: 깨진 갈래의 계획이 status "ok" · local_stale ["mine"]이었다.
    그 근거("다른 기기가 지웠다")는 거짓이다 — 레포는 아무것도 지우지 않았다.
    """
    repo = broken_or_valid_repo(tmp_path, repo_syntax, {"mine": A, "theirs": B})
    path = os.path.join(repo, mc.BACKUP_RELPATH)
    run = lambda: plan_mcp.build_plan(                                  # noqa: E731
        path, claude_json_path=write_local(tmp_path, {"mine": A, "dropped": B}),
        base_dir=write_base_blob(tmp_path, {"mine": A, "dropped": B}))
    if repo_syntax == "valid":
        plan = run()
        # 대조군 — 정상 문서에서는 **레포가 실제로 지운 dropped만** 제안이 된다.
        # base를 빼면 이 줄이 []를 받아 죽는다(입력 축 변조 — 합집합 degrade).
        assert plan["local_stale"] == ["dropped"]
        assert plan["add"] == ["theirs"]
    else:
        with pytest.raises(mc.BrokenBackupSyntax):
            run()


@pytest.mark.parametrize("script,args", [
    ("sync-backup/scripts/collect_mcp.py", ["<repo>", "<staging>"]),
    ("sync-status/scripts/compare_mcp.py", ["<backup>"]),
    ("sync-restore/scripts/plan_mcp.py", ["plan", "<backup>"]),
])
def test_a_broken_repo_document_is_a_document_level_skip_from_the_cli(tmp_path, script, args):
    """세 스크립트가 같은 갈래를 낸다 — 종료 코드 0, status "skipped", 무엇을 할지.

    reason에 "구문이 깨졌다"가 있어야 SKILL.md가 형식 문제(플러그인 업데이트 안내)와
    구문 문제(레포 파일을 고치라는 안내)를 가른다 — 두 안내는 서로 쓸모가 없다.
    """
    repo = write_broken_repo(tmp_path, {"mine": A, "theirs": B})
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"mine": A}}),
                                       encoding="utf-8")   # 로컬 읽기는 성공해야 한다
    subst = {"<repo>": repo, "<staging>": str(tmp_path / "staging"),
             "<backup>": os.path.join(repo, mc.BACKUP_RELPATH)}
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, script)]
        + [subst.get(a, a) for a in args],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "skipped"
    assert "구문이 깨졌다" in out["reason"]
    assert mc.BACKUP_RELPATH in out["reason"]


def test_collect_cli_exits_zero_on_skip(tmp_path):
    """MCP 단계 실패로 backup 전체를 실패시키지 않는다 — 종료 코드 0."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"z": B})
    script = os.path.join(SCRIPTS_DIR, "sync-backup", "scripts", "collect_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), repo, str(tmp_path / "staging")],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_collect_cli_rejects_wrong_argument_count():
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다."""
    script = os.path.join(SCRIPTS_DIR, "sync-backup", "scripts", "collect_mcp.py")
    proc = subprocess.run([sys.executable, os.path.abspath(script)], capture_output=True, text=True)
    assert proc.returncode == 1


def test_compare_converges_when_local_secret_is_plaintext(tmp_path):
    """백업 직후 '동일'로 수렴한다 — Bug #2(영구 미수렴) 회귀."""
    repo_cfg = {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}
    local = write_local(tmp_path, {"c7": dict(repo_cfg, headers={"K": "sk-real"})})
    repo = write_repo(tmp_path, {"c7": repo_cfg})
    out = compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)
    assert out == {"status": "ok", "only_local": [], "only_repo": [], "changed": []}


def test_compare_reports_three_buckets(tmp_path):
    local = write_local(tmp_path, {"mine": A, "both": A})
    repo = write_repo(tmp_path, {"theirs": B, "both": B})
    out = compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)
    assert out["only_local"] == ["mine"]
    assert out["only_repo"] == ["theirs"]
    assert out["changed"] == ["both"]


def test_compare_preserves_command_with_spaces(tmp_path):
    """공백이 든 command도 온전히 비교된다 — Bug #1 회귀."""
    cfg = {"command": "/Applications/Safari Technology Preview.app/Contents/MacOS/safaridriver",
           "args": ["--mcp"]}
    local = write_local(tmp_path, {"safari-mcp-stp": cfg})
    repo = write_repo(tmp_path, {"safari-mcp-stp": cfg})
    out = compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)
    assert out["only_local"] == [] and out["changed"] == []


def test_compare_raises_instead_of_reporting_everything_as_only_repo(tmp_path):
    """읽기 실패를 '서버 0개'로 오인하면 레포의 서버가 전부 only_repo가 된다.

    main()이 이 예외를 잡아 skipped로 바꾼다 — 아래 CLI 테스트에서 확인한다.
    """
    repo = write_repo(tmp_path, {"z": B})
    with pytest.raises(mc.LocalConfigUnavailable):
        compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH),
                            claude_json_path=str(tmp_path / "missing.json"))


def test_compare_cli_exits_zero_on_skip(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"z": B})
    script = os.path.join(SCRIPTS_DIR, "sync-status", "scripts", "compare_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), os.path.join(repo, mc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_plan_emits_buckets_and_configs(tmp_path):
    """SKILL.md가 레포 파일을 직접 파싱하지 않도록 등록용 config를 함께 낸다."""
    repo_cfg = {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}
    local = write_local(tmp_path, {})
    repo = write_repo(tmp_path, {"c7": repo_cfg, "pw": {"command": "npx"}})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["status"] == "ok"
    assert out["add"] == ["pw"] and out["needs_secret"] == ["c7"]
    assert out["configs"]["pw"] == {"command": "npx"}
    assert out["secret_keys"]["c7"] == [("headers", "K")]   # JSON으로 나가면 배열이 된다


def test_plan_config_values_are_masked(tmp_path):
    """configs는 레포 값(마스킹됨)이다 — 계획 출력에 비밀이 실리지 않는다."""
    local = write_local(tmp_path, {})
    repo = write_repo(tmp_path, {"c7": {"type": "http", "url": "u", "headers": {"K": "sk-real"}}})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["configs"]["c7"]["headers"]["K"] == mc.SENTINEL


def test_plan_omits_configs_for_unrestorable(tmp_path):
    """등록을 시도하지 않는 항목에는 등록용 config를 주지 않는다."""
    local = write_local(tmp_path, {})
    repo = write_repo(tmp_path, {"claude.ai Notion": {"url": "u", "type": "stdio"}})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["unrestorable"] == ["claude.ai Notion"]
    assert out["configs"] == {}


def test_plan_uses_base_to_split_cases_7_8_9(tmp_path):
    local = write_local(tmp_path, {"seven": A, "eight": ORIG, "nine": A})
    repo = write_repo(tmp_path, {"seven": ORIG, "eight": B, "nine": B})
    base_dir = write_base_blob(tmp_path, {"seven": ORIG, "eight": ORIG, "nine": ORIG})
    out = plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH),
                              claude_json_path=local, base_dir=base_dir)
    assert out["local_ahead"] == ["seven"]
    assert out["repo_ahead"] == ["eight"]
    assert out["both_changed"] == ["nine"]


def test_plan_cli_exits_zero_on_skip(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"z": B})
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), "plan", os.path.join(repo, mc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_plan_cli_rejects_unknown_mode():
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run([sys.executable, os.path.abspath(script), "bogus"],
                          capture_output=True, text=True)
    assert proc.returncode == 1


def write_choices(tmp_path, payload):
    path = tmp_path / "choices.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_apply_base_advances_where_local_agrees(tmp_path):
    """① 기본 전진 — 로컬이 동의한 이름만 base로 간다."""
    local = write_local(tmp_path, {"x": A, "mine": A})
    repo = write_repo(tmp_path, {"x": A, "theirs": B})
    staging = str(tmp_path / "staging")
    out = plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging,
                              {"keep_stale": [], "keep_local": []},
                              claude_json_path=local,
                              base_dir=write_base_blob(tmp_path, None))
    assert out["status"] == "ok"
    staged = staged_servers(staging)
    assert staged == {"x": A}          # theirs는 로컬이 동의하지 않았고 이전 base에도 없다


def test_apply_base_keep_stale_forgets_the_name(tmp_path):
    """② 케이스 4 '유지' — base에서 이름을 지워 다음 backup이 push하게 만든다."""
    local = write_local(tmp_path, {"X": A, "y": A})
    repo = write_repo(tmp_path, {"y": A})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging,
                        {"keep_stale": ["X"]},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, {"X": A, "y": A}))
    assert "X" not in staged_servers(staging)


def test_apply_base_keep_local_moves_base_to_repo_value(tmp_path):
    """③ 케이스 8 '로컬 유지' — base ← 레포 값. 없으면 '나중에'와 구별되지 않는다."""
    local = write_local(tmp_path, {"x": ORIG})
    repo = write_repo(tmp_path, {"x": B})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging,
                        {"keep_local": ["x"]},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, {"x": ORIG}))
    assert staged_servers(staging)["x"] == B


def test_apply_base_without_choices_is_defer(tmp_path):
    """'나중에' — override 없음. 케이스 8의 base가 이전 값(로컬 값)에 머문다."""
    local = write_local(tmp_path, {"x": ORIG})
    repo = write_repo(tmp_path, {"x": B})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging, {},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, {"x": ORIG}))
    assert staged_servers(staging)["x"] == ORIG


def test_apply_base_never_writes_plaintext_secret(tmp_path):
    """복원 후 로컬은 평문이지만 base에는 SENTINEL만 들어간다 — next_base의 redact 계약."""
    cfg_plain = {"type": "http", "url": "u", "headers": {"K": "sk-real"}}
    cfg_masked = {"type": "http", "url": "u", "headers": {"K": mc.SENTINEL}}
    local = write_local(tmp_path, {"c7": cfg_plain})
    repo = write_repo(tmp_path, {"c7": cfg_masked})
    staging = str(tmp_path / "staging")
    plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging, {},
                        claude_json_path=local,
                        base_dir=write_base_blob(tmp_path, None))
    raw = open(os.path.join(staging, mc.BACKUP_RELPATH), encoding="utf-8").read()
    assert "sk-real" not in raw
    assert staged_servers(staging)["c7"] == cfg_masked   # base가 전진했다


def test_apply_base_cli_writes_staging_file(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"x": A}}), encoding="utf-8")
    repo = write_repo(tmp_path, {"x": A})
    staging = str(tmp_path / "staging")
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), "apply-base",
         os.path.join(repo, mc.BACKUP_RELPATH), staging,
         write_choices(tmp_path, {"keep_stale": [], "keep_local": []})],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "ok"
    assert staged_servers(staging) == {"x": A}


def test_apply_base_cli_skips_on_broken_choices(tmp_path):
    """선택 결과 JSON이 깨져도 restore 전체를 중단시키지 않는다 — 종료 코드 0."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    repo = write_repo(tmp_path, {"x": A})
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    script = os.path.join(SCRIPTS_DIR, "sync-restore", "scripts", "plan_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), "apply-base",
         os.path.join(repo, mc.BACKUP_RELPATH), str(tmp_path / "staging"), str(bad)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


FUTURE_V3 = '{"version": 3, "scope": "user", "entries": {"x": {"command": "a"}}}'


def write_repo_raw(tmp_path, text):
    """레포에 임의 바이트의 mcp-servers.json을 둔다(미래 스키마 흉내)."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / mc.BACKUP_RELPATH).write_text(text, encoding="utf-8")
    return str(repo)


def test_collect_refuses_to_overwrite_unknown_schema(tmp_path):
    """미래 버전이 쓴 레포 파일을 이 버전이 비워 버리면 안 된다."""
    local = write_local(tmp_path, {"mine": A})
    repo = write_repo_raw(tmp_path, FUTURE_V3)
    staging = str(tmp_path / "staging")
    with pytest.raises(mc.UnknownBackupSchema):
        collect_mcp.collect(repo, staging, claude_json_path=local,
                            base_dir=write_base_blob(tmp_path, {"mine": A}))
    assert open(os.path.join(repo, mc.BACKUP_RELPATH), encoding="utf-8").read() == FUTURE_V3
    assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))


def test_collect_cli_skips_on_unknown_schema(tmp_path):
    """MCP 단계만 건너뛰고 종료 코드 0 — backup 흐름 전체를 실패시키지 않는다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"mine": A}}), encoding="utf-8")
    repo = write_repo_raw(tmp_path, FUTURE_V3)
    script = os.path.join(SCRIPTS_DIR, "sync-backup", "scripts", "collect_mcp.py")
    proc = subprocess.run(
        [sys.executable, os.path.abspath(script), repo, str(tmp_path / "staging")],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
    assert open(os.path.join(repo, mc.BACKUP_RELPATH), encoding="utf-8").read() == FUTURE_V3


def test_compare_refuses_unknown_schema(tmp_path):
    """읽기 전용이지만 '레포에 아무것도 없다'는 오보를 내지 않는다."""
    local = write_local(tmp_path, {"mine": A})
    repo = write_repo_raw(tmp_path, FUTURE_V3)
    with pytest.raises(mc.UnknownBackupSchema):
        compare_mcp.compare(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local)


def test_plan_refuses_unknown_schema(tmp_path):
    """복원 계획이 로컬 서버를 전부 local_only로 오보하지 않는다."""
    local = write_local(tmp_path, {"mine": A})
    repo = write_repo_raw(tmp_path, FUTURE_V3)
    with pytest.raises(mc.UnknownBackupSchema):
        plan_mcp.build_plan(os.path.join(repo, mc.BACKUP_RELPATH), claude_json_path=local,
                            base_dir=write_base_blob(tmp_path, None))


def test_apply_base_refuses_unknown_schema(tmp_path):
    """모르는 레포를 근거로 base를 전진시키지 않는다."""
    local = write_local(tmp_path, {"mine": A})
    repo = write_repo_raw(tmp_path, FUTURE_V3)
    staging = str(tmp_path / "staging")
    with pytest.raises(mc.UnknownBackupSchema):
        plan_mcp.apply_base(os.path.join(repo, mc.BACKUP_RELPATH), staging, {},
                            claude_json_path=local, base_dir=write_base_blob(tmp_path, None))
    assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))


def test_collect_does_not_stage_when_repo_write_fails(tmp_path, monkeypatch):
    """레포 쓰기가 실패하면 스테이징 최종 파일이 남지 않아야 base가 전진하지 않는다.

    남으면 SKILL.md의 게이트 `[ -f ... ]`가 통과해 base가 전진하고,
    다음 백업이 이 기기 자신의 서버를 케이스 4로 오독한다.
    """
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    staging = str(tmp_path / "staging")
    real_dump = mc.dump_backup

    def fail_on_repo(servers, path):
        if path == os.path.join(repo, mc.BACKUP_RELPATH):
            raise OSError("disk full")
        return real_dump(servers, path)

    monkeypatch.setattr(mc, "dump_backup", fail_on_repo)
    with pytest.raises(OSError):
        collect_mcp.collect(repo, staging, claude_json_path=local, base_dir=base_dir)
    assert not os.path.exists(os.path.join(staging, mc.BACKUP_RELPATH))


def test_collect_keeps_repo_write_when_staging_rename_fails(tmp_path, monkeypatch):
    """rename 자체가 실패해도 레포는 이미 갱신돼 있다 — skipped로 접으면 거짓말이 된다(spec 7.4).

    status는 ok를 유지하고 base_staging에 failed를 남긴다. 스테이징 최종 파일은
    존재하지 않아야 SKILL.md의 게이트가 막혀 base가 전진하지 않는다.
    """
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    staging = str(tmp_path / "staging")
    staged = os.path.join(staging, mc.BACKUP_RELPATH)
    real_replace = collect_mcp.os.replace

    def fail_on_rename(src, dst):
        if dst == staged:
            raise OSError("rename failed")
        return real_replace(src, dst)

    monkeypatch.setattr(collect_mcp.os, "replace", fail_on_rename)
    out = collect_mcp.collect(repo, staging, claude_json_path=local, base_dir=base_dir)
    assert out["status"] == "ok"
    assert out["base_staging"] == "failed"
    assert repo_servers(repo) == {"x": A}
    assert not os.path.exists(staged)


def drops_a_key(servers):
    """키를 하나 지우는 normalize 훅. 코어의 키 보존 계약(spec 5.2)을 어긴다.

    실제 redact는 키를 지우지 않으므로 MCP에서는 이 상황이 오지 않는다. 두 번째
    어댑터(plugin_config)의 normalize가 키 하나를 떨어뜨리는 순간이 첫 발현이다.
    """
    return {name: cfg for name, cfg in servers.items() if name != "x"}


def test_collect_cli_skips_when_normalize_drops_a_key(tmp_path, monkeypatch, capsys):
    """normalize 계약 위반(ValueError)도 traceback이 아니라 skipped로 접힌다.

    코어가 이 위반을 ValueError로 던지는데 main()의 except 튜플에서 빠지면,
    어댑터 훅의 결함 하나가 backup 흐름 전체를 세운다(9장 안전장치 회귀).
    """
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, {"x": B})
    monkeypatch.setattr(mc, "redact", drops_a_key)
    monkeypatch.setattr(mc, "DEFAULT_CLAUDE_JSON", local)
    # base 이력은 이 회귀와 무관하다. 실제 ~/.claude/.sync-state를 읽지 않도록 없는 것으로 둔다.
    monkeypatch.setattr(collect_mcp.ss, "read_base", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["collect_mcp.py", repo, str(tmp_path / "staging")])
    collect_mcp.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped"
    assert out["reason"]


def test_compare_cli_skips_when_normalize_drops_a_key(tmp_path, monkeypatch, capsys):
    """status도 같은 계약 위반에서 접힌다 — 세 스크립트의 except 튜플이 갈리지 않게 한다."""
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, {"x": B})
    monkeypatch.setattr(mc, "redact", drops_a_key)
    monkeypatch.setattr(mc, "DEFAULT_CLAUDE_JSON", local)
    monkeypatch.setattr(sys, "argv",
                        ["compare_mcp.py", os.path.join(repo, mc.BACKUP_RELPATH)])
    compare_mcp.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped"
    assert out["reason"]


def test_collect_names_the_staging_failure_reason_apart_from_skipped(tmp_path, monkeypatch):
    """status=ok payload에 `reason`을 실으면 skipped 경로의 필드 이름과 충돌한다.

    SKILL.md:292가 `reason`을 "레포 파일은 손대지 않았다"의 사유로 문서화했다.
    같은 이름을 ok 경로에 쓰면 스킬이 두 상태를 한 이름으로 읽는다.
    """
    local = write_local(tmp_path, {"x": A})
    repo = write_repo(tmp_path, None)
    base_dir = write_base_blob(tmp_path, None)
    staging = str(tmp_path / "staging")
    staged = os.path.join(staging, mc.BACKUP_RELPATH)
    real_replace = os.replace

    def fail_on_staging(src, dst):
        # repo_file도 mc.BACKUP_RELPATH로 끝나므로 endswith가 아니라 정확히
        # staged 경로만 매치한다 — 아니면 레포 쓰기 자체가 먼저 걸려
        # collect()가 이 함수의 try/except에 닿기도 전에 예외로 죽는다.
        if str(dst) == staged:
            raise OSError("rename failed")
        return real_replace(src, dst)

    monkeypatch.setattr(collect_mcp.os, "replace", fail_on_staging)
    out = collect_mcp.collect(repo, staging,
                              claude_json_path=local, base_dir=base_dir)
    assert out["status"] == "ok"
    assert out["base_staging"] == "failed"
    assert "reason" not in out
    assert "다음 백업이 복구한다" in out["base_staging_reason"]
