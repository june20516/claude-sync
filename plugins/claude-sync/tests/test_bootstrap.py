"""백업 레포의 `.gitignore` — `bootstrap.sh`가 만든다.

**이 파일이 따로 있는 이유.** `bootstrap.sh`는 SKILL.md가 아니라 **레포에 복사되는 셸
스크립트**다(sync-backup SKILL.md 8단계). 실행해서 재므로 읽어서 재는
`test_skill_wiring.py`에 속하지 않고, 스크립트라서 사용자 문서를 재는
`test_user_docs.py`에도 속하지 않으며, `test_script_root.py`는 그 파일의 docstring대로
SKILL.md 0단계 전용이다.

**무엇을 막는가(실측).** `plugin_config.dump_backup` → `ks.dump_json` → `ks.dump_bytes`가
레포 파일을 쓰면서 `<레포>/plugins.json.tmp`를 잠깐 만든다. 정상 실패 경로는 그것을 스스로
지우지만 `os.replace` 전에 SIGKILL로 죽으면 남고, 그러면 sync-backup 10단계의
`git add -A`가 그것을 커밋해 **잘린 문서가 모든 기기로 퍼진다.** `/*.tmp` 한 줄이 그 보험이다.

**패턴은 루트에 고정한다.** 맨 `*.tmp`는 git이 모든 깊이에 적용해, 사용자의
`skills/notes/draft.tmp`가 표식에는 이름과 해시로 실리고 `/sync-status`는 push를
약속하는데 `git add -A`만 조용히 건너뛰는 **보고 경로 없는 두 번째 제외 축**이 된다.
레포 쪽 문서 셋은 전부 루트에 있으므로 고정해도 보험은 그대로다.

**한계.** 소급되지 않는다 — `bootstrap.sh`는 새 기기가 처음 복원할 때만 돈다. 그 한계는
스크립트 주석에도 적혀 있다.
"""
import os
import shutil
import subprocess

BOOTSTRAP = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts", "bootstrap.sh"))


def run_bootstrap(tmp_path, repo):
    """레포에 복사한 뒤 거기서 실행한다 — 원본 트리에서 실행하면 소스 디렉토리에 쓴다."""
    shutil.copy(BOOTSTRAP, str(repo / "bootstrap.sh"))
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    r = subprocess.run(
        ["bash", str(repo / "bootstrap.sh")],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)),
    )
    assert r.returncode == 0, r.stderr
    return r


def test_bootstrap_creates_a_gitignore_that_ignores_temp_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_bootstrap(tmp_path, repo)
    assert (repo / ".gitignore").read_text() == "/*.tmp\n"


def test_running_bootstrap_twice_does_not_duplicate_the_line(tmp_path):
    """새 기기 복원은 한 번으로 끝나지 않는다 — 두 번 돌아도 파일이 자라면 안 된다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_bootstrap(tmp_path, repo)
    run_bootstrap(tmp_path, repo)
    assert (repo / ".gitignore").read_text() == "/*.tmp\n"


def test_an_existing_gitignore_is_appended_to_not_overwritten(tmp_path):
    """사용자가 자기 레포에 적은 줄을 덮으면 그것이 곧 이 task가 막으려는 손실이다."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("secrets/\n")
    run_bootstrap(tmp_path, repo)
    assert (repo / ".gitignore").read_text() == "secrets/\n/*.tmp\n"


def test_appending_to_a_file_without_a_trailing_newline_does_not_glue_the_lines(tmp_path):
    """`echo >>`는 마지막 줄에 개행이 없으면 그 줄에 이어 붙인다 — `secrets//*.tmp`가 된다.

    그 한 줄은 사용자의 패턴과 이 스크립트의 패턴을 **동시에** 망가뜨린다.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text("secrets/")
    run_bootstrap(tmp_path, repo)
    assert (repo / ".gitignore").read_text() == "secrets/\n/*.tmp\n"


def test_the_pattern_ignores_the_temp_file_but_not_a_users_nested_tmp(tmp_path):
    """실제 git에게 물어 두 성질을 함께 잰다 — 맨 `*.tmp`로는 둘째가 죽는다.

    보험은 그대로여야 하고(레포 루트의 `plugins.json.tmp`), 사용자의 파일은 커밋
    가능해야 한다(`skills/notes/draft.tmp`). 후자가 제외되면 표식은 그 이름과 sha256을
    광고하고 `/sync-status`는 매 실행마다 push를 약속하는데 파일은 영영 도달하지 않는다.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    run_bootstrap(tmp_path, repo)
    (repo / "plugins.json.tmp").write_text("{")
    (repo / "skills" / "notes").mkdir(parents=True)
    (repo / "skills" / "notes" / "draft.tmp").write_text("메모")

    def ignored(rel):
        return subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", rel]).returncode == 0

    assert ignored("plugins.json.tmp")
    assert not ignored("skills/notes/draft.tmp")
