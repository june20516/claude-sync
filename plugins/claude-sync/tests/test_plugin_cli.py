"""`claude plugin` CLI 에뮬레이터의 계약 (spec 14.3).

**이것이 틀리면 test_plugin_cycle.py의 시나리오가 전부 무의미하다.** 그 파일은 실제
스크립트를 서브프로세스로 부르는 `Device` 하네스의 교대 시나리오를 담고, 이 파일은
그 하네스가 딛고 선 에뮬레이터만 잰다 — 여기서는 `PluginCLI`만 쓰고 스크립트를
서브프로세스로 부르지 않는다.

근거는 plugin_cli.py 모듈 docstring이 가리키는 브리프 1-b·1-c의 실측표다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import plugin_config as pc  # noqa: E402
from plugin_cli import PluginCLI  # noqa: E402


def test_install_writes_true_but_preserves_an_existing_array(tmp_path):
    cli = PluginCLI(str(tmp_path))
    assert cli.install("p@m") == 0
    assert cli.settings()["enabledPlugins"]["p@m"] is True
    cli.set_enabled("q@m", ["1.0.0"])
    assert cli.install("q@m") == 0
    assert cli.settings()["enabledPlugins"]["q@m"] == ["1.0.0"]


def test_install_flattens_an_existing_object_value(tmp_path):
    """**실측 없음 — 추정**(plugin_cli 모듈 docstring 9번).

    1.2와 브리프 C1이 재는 것은 **객체/미설치** 행이다. `set_enabled`가 설치 기록을 함께
    남기므로(그 자리 docstring 참조) 여기서 만드는 상태는 **객체/이미 설치 → 재실행**이고,
    그 행은 두 표 어디에도 없다. 이 에뮬레이터는 설치 여부로 분기하지 않으므로 측정된
    행과 같은 결과를 낸다 — **결론이 아니라 근거가 추정이다.**

    평탄화가 객체 한 갈래뿐이라는 것(배열은 살아남는다)은 실측이고, 그쪽은
    test_install_writes_true_but_preserves_an_existing_array가 잰다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("o@m", {"version": "1.0.0"})
    cli.install("o@m")
    assert cli.settings()["enabledPlugins"]["o@m"] is True


def test_enable_and_disable_are_not_idempotent(tmp_path):
    """이미 그 상태면 exit 1 — 이 성질이 없으면 "현재 상태와 다를 때만"이 무의미해진다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m")
    assert cli.enable("p@m") == 1
    assert cli.disable("p@m") == 0
    assert cli.disable("p@m") == 1


def test_enable_and_disable_reject_an_unknown_plugin(tmp_path):
    """**에뮬레이터의 규약이지 실측이 아니다** (plugin_cli 모듈 docstring 4번).

    브리프 1-b는 설치되지 않은 id에 enable/disable을 낸 갈래를 재지 않았다. 여기서
    고정하는 것은 둘이다 — exit 1이라는 것, 그리고 **값을 만들어 내지 않는다**는 것.
    후자가 실질이다: 설치에 실패한 플러그인에 3단계(disable_after_install)가 로컬 값을
    심으면 다음 백업의 next_base가 그 키를 전진시켜 **복원 실패가 성공처럼 보인다**
    (10.4가 "실패한 항목은 로컬에 없으니 자동으로 빠진다"로 막으려는 것이 그것이다).
    """
    cli = PluginCLI(str(tmp_path))
    assert cli.enable("ghost@m") == 1
    assert cli.disable("ghost@m") == 1
    assert cli.settings()["enabledPlugins"] == {}
    # **두 파일 중 다른 쪽도 함께 잰다.** settings.json만 보면 실패 갈래가
    # installed_plugins.json에 항목을 남겨도 조용하다 — 그러면 read_installed의
    # installed_ids에 유령 id가 들어가 restore의 2단계가 그것을
    # skipped_already_installed로 접는다.
    assert cli.installed()["plugins"] == {}


def test_uninstall_removes_the_config_too_and_fails_when_absent(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m", config={"k": "v"})
    assert "p@m" in cli.installed()["plugins"]
    assert cli.uninstall("p@m") == 0
    assert cli.settings()["enabledPlugins"] == {}
    assert cli.settings()["pluginConfigs"] == {}
    # 설치 기록도 함께 지운다 — 남기면 restore의 2단계가 그 id를
    # skipped_already_installed로 접어 영영 설치하지 않는다.
    assert cli.installed()["plugins"] == {}
    assert cli.uninstall("p@m") == 1


def test_a_failed_uninstall_leaves_the_installed_record_alone(tmp_path):
    """**에뮬레이터의 규약이지 실측이 아니다.** 실패 갈래의 두 파일 일관성을 잰다.

    성공 갈래는 명령마다 두 파일의 절반이 따로 단정돼 있지만, 실패 갈래는 exit code와
    settings.json만 보면 `installed_plugins.json` 쪽 부작용이 조용히 지나간다.
    갈리면 `read_installed`의 installed_ids가 로컬 값과 어긋나 restore의 2단계/4단계
    분리가 틀린 쪽으로 떨어진다.

    "설치 기록만 있고 enabledPlugins에는 없는 id"는 공개 API로 만들 수 없으므로
    파일을 직접 심는다(스코프 테스트와 같은 방식). 그 상태 자체는 실측이 아니라
    이 단정을 공허하지 않게 만드는 픽스처다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.install("q@m")
    data = cli.installed()
    data["plugins"]["orphan@m"] = [{"scope": "user", "auto": False}]
    with open(cli.installed_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    assert cli.uninstall("orphan@m") == 1
    assert set(cli.installed()["plugins"]) == {"q@m", "orphan@m"}
    # 실패한 명령은 다른 항목의 기록도 건드리지 않는다.
    assert cli.settings()["enabledPlugins"] == {"q@m": True}


def test_install_config_merges_partially(tmp_path):
    """N2 — 지정하지 않은 키는 보존된다. 6.3의 부분 입력이 여기 걸려 있다."""
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m", config={"a": "1", "b": "2"})
    cli.install("p@m", config={"b": "3"})
    assert cli.settings()["pluginConfigs"]["p@m"]["options"] == {"a": "1", "b": "3"}


def test_marketplace_remove_cascades_to_member_plugins(tmp_path):
    """실측 — 연쇄 삭제. restore가 이 명령을 실행하지 않는 이유다 (9.3.5)."""
    cli = PluginCLI(str(tmp_path))
    cli.marketplace_add("m", "o/r")
    cli.install("p@m", config={"k": "v"})
    cli.install("q@other")
    assert cli.marketplace_remove("m") == 0
    assert cli.settings()["enabledPlugins"] == {"q@other": True}
    assert cli.settings()["pluginConfigs"] == {}
    # 설치 기록도 소속 플러그인만 사라진다.
    assert set(cli.installed()["plugins"]) == {"q@other"}
    # 재실행은 exit 1 (1-b #8). uninstall(#6)·enable/disable(#5)의 같은 갈래와 짝이다 —
    # restore가 이 명령을 실행하지 않더라도 세 형제의 규약은 함께 고정해 둔다.
    assert cli.marketplace_remove("m") == 1


def test_dependency_install_marks_auto_and_explicit_install_clears_it(tmp_path):
    """N6 — 명시적 설치는 auto 표식을 **되돌릴 수 없게** 지운다."""
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset({"child@m"})
    cli.install("child@m")
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_dependency_install_leaves_an_already_installed_child_alone(tmp_path):
    """C1 표의 마지막 행 — 건드리지 않은 값은 형태 무관 보존된다.

    자식이 이미 수동 설치돼 있으면 부모 설치가 그 값을 덮지도, auto로 되돌리지도
    않는다. 되돌아가면 H1이 사용자가 직접 고른 플러그인을 보류에 넣는다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("child@m", ["1.0.0"])
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    assert cli.settings()["enabledPlugins"]["child@m"] == ["1.0.0"]
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_installing_at_user_scope_keeps_other_scope_entries(tmp_path):
    """N4 — plugins[<id>]는 스코프별 배열이다. user 스코프 항목만 갈아 끼운다.

    이 동기화는 전부 user 스코프로 동작하므로(9.3.1), project 항목을 함께 지우면
    read_installed의 스코프 필터가 필터로 동작하는 입력 자체를 만들 수 없게 된다.
    **실측 없음 — 추정**(plugin_cli 모듈 docstring 8번): N4가 배열의 존재와 항목의 필드를
    쟀을 뿐, `install --scope user`가 다른 스코프 항목을 건드리지 않는다는 것은 재지 않았다.
    """
    cli = PluginCLI(str(tmp_path))
    with open(cli.installed_path, "w", encoding="utf-8") as f:
        json.dump({"version": 2,
                   "plugins": {"p@m": [{"scope": "project", "auto": True}]}}, f)
    cli.install("p@m")
    entries = cli.installed()["plugins"]["p@m"]
    assert {"scope": "project", "auto": True} in entries
    assert {"scope": "user", "auto": False} in entries
    # project 스코프의 auto는 auto 집합에 들어가지 않는다 (spec 3.4).
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_prune_removes_orphaned_auto_entries(tmp_path):
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    cli.uninstall("parent@m")
    cli.prune()
    assert "child@m" not in cli.settings()["enabledPlugins"]
    assert pc.read_auto_ids(cli.installed_path) == frozenset()


def test_prune_keeps_a_manually_promoted_child(tmp_path):
    """N6 — auto가 지워진 항목은 부모가 사라져도 prune 대상이 아니다."""
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("parent@m", ["child@m"])
    cli.install("parent@m")
    cli.install("child@m")
    cli.uninstall("parent@m")
    cli.prune()
    assert cli.settings()["enabledPlugins"]["child@m"] is True
