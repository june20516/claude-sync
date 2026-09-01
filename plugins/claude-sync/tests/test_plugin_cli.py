"""`claude plugin` CLI 에뮬레이터의 계약 (spec 14.3).

**이것이 틀리면 test_plugin_cycle.py의 시나리오가 전부 무의미하다.** 그 파일은 실제
스크립트를 서브프로세스로 부르는 `Device` 하네스의 교대 시나리오를 담고, 이 파일은
그 하네스가 딛고 선 에뮬레이터만 잰다 — 여기서는 `PluginCLI`만 쓰고 스크립트를
서브프로세스로 부르지 않는다.

근거는 plugin_cli.py 모듈 docstring이 가리키는 두 출처다 — 브리프 1-b·1-c의 실측표와
`docs/superpowers/2026-08-29-plugin-cli-smoke.md`(spec 14.5 실환경 스모크).
"""
import json
import os
import sys

import pytest

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


def test_install_writes_the_manifest_default_enabled(tmp_path):
    """**실측**(plugin_cli 모듈 docstring 12번 — 2026-08-29 스모크 2차 7장).

    `install`은 "언제나 `true`"가 아니다. 1차 스모크가 그렇게 읽은 것은 픽스처의
    `defaultEnabled`가 전부 기본값(true)이었기 때문이고, 2차가 그 필드를 `false`로 둔
    플러그인을 세워 갈랐다.

    **이 테스트가 없으면 그 규칙이 공허하다** — 에뮬레이터를 "언제나 true"로 되돌려도
    스위트 전체가 통과했다(실측: 이 파일을 쓰기 전에 규칙만 먼저 넣었더니
    **깨진 테스트가 하나도 없었다**). `defaultEnabled`를 심는 입력이 저장소 어디에도
    없었기 때문이다.

    **표의 세 번째 행(`defaultEnabled: false` + 기존 `true`)이 그 문서의 요약 문장과
    어긋난다.** 요약은 *"배열이면 보존하고 그 외에는 defaultEnabled를 쓴다"*인데 그
    행의 실측은 `false`가 아니라 **`true` 유지**다. 여기서는 표를 따른다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("off@m", default_enabled=False)
    cli.set_manifest("on@m")                      # defaultEnabled는 선택 필드 — 기본 true
    # (키 없음) 행 둘.
    cli.install("off@m")
    cli.install("on@m")
    assert cli.settings()["enabledPlugins"] == {"off@m": False, "on@m": True}
    # `false` 행 둘 — defaultEnabled가 true인 쪽만 **뒤집힌다.**
    cli.install("off@m")
    cli.install("on@m")
    assert cli.settings()["enabledPlugins"] == {"off@m": False, "on@m": True}
    # `true` 행 — defaultEnabled가 false여도 **유지된다.** 표의 세 번째 행이다.
    assert cli.enable("off@m") == 0
    cli.install("off@m")
    assert cli.settings()["enabledPlugins"]["off@m"] is True
    # 배열 행 — defaultEnabled와 무관하게 보존된다.
    cli.set_enabled("arr@m", ["1.0.0"])
    cli.set_manifest("arr@m", default_enabled=False)
    cli.install("arr@m")
    assert cli.settings()["enabledPlugins"]["arr@m"] == ["1.0.0"]


def test_a_failed_install_touches_neither_file(tmp_path):
    """**실측**(plugin_cli 모듈 docstring 13번 — 1-b #3·#4).

    1-b #3은 미등록 마켓플레이스로 install하면 `settings.json`을 **만들지도 않는다**고
    기록한다. 그 갈래를 재현하는 것이 유령 키 시나리오의 전제다 — 이 픽스처가 없으면
    "2단계가 실패한 id"라는 상태 자체를 저장소 안에서 만들 수 없다.

    **의존성도 끌어오지 않는다.** 실패한 install이 자식만 남기면 그 자식이 auto로 남아
    `prune`의 입력이 되고, 실패한 복원이 로컬 상태를 바꾼 것이 된다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_manifest("p@m", ["child@m"])
    cli.set_install_failure("p@m")
    before_settings = cli.settings()
    before_installed = cli.installed()
    assert cli.install("p@m", config={"k": "v"}) == 1
    assert cli.settings() == before_settings
    assert cli.installed() == before_installed
    # 다른 id는 영향받지 않는다 — 실패는 심은 id 하나에만 걸린다.
    assert cli.install("q@m") == 0
    assert cli.settings()["enabledPlugins"] == {"q@m": True}


def test_install_flattens_an_existing_object_value(tmp_path):
    """**실측**(plugin_cli 모듈 docstring 9번 — 2026-08-29 스모크 2장).

    1.2와 브리프 C1이 재는 것은 **객체/미설치** 행이었다. `set_enabled`가 설치 기록을 함께
    남기므로(그 자리 docstring 참조) 여기서 만드는 상태는 **객체/이미 설치 → 재실행**이고,
    그 행은 두 표 어디에도 없었다 — 결론은 맞고 **근거만 추정이던 자리**였다. 스모크가
    그 행을 직접 재어 `true`로 평탄화됨을 확인했고, 그래서 여기 표식이 승격됐다.

    평탄화가 객체 한 갈래뿐이라는 것(배열은 살아남는다)은 브리프 C1의 실측이고, 그쪽은
    test_install_writes_true_but_preserves_an_existing_array가 잰다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("o@m", {"version": "1.0.0"})
    cli.install("o@m")
    assert cli.settings()["enabledPlugins"]["o@m"] is True


def test_enable_and_disable_are_not_idempotent(tmp_path):
    """이미 그 상태면 exit 1 — 이 성질이 없으면 "현재 상태와 다를 때만"이 무의미해진다.

    **14.3 3행의 요구는 둘이다** — exit code 규약과 *"키를 유지한 채 값만 true↔false로
    바꾼다"*(1-b #5). 초판은 exit code만 쟀고, 그래서 `_set_value`가 값을 바꾸는 대신
    **키를 지우도록** 만드는 변조가 이 파일을 통과했다(실측 — 그때 잡은 것은 교대
    시나리오 하나뿐이었다). 키가 사라지면 그 항목은 로컬에 "없는" 상태가 되어 다음
    백업이 케이스 3(삭제)이나 케이스 2로 오독한다 — 값이 `false`인 것과 의미가 반대다
    (`value_command`의 *"로컬의 부재는 false가 아니다"*가 같은 사실을 반대편에서 쓴다).
    """
    cli = PluginCLI(str(tmp_path))
    cli.install("p@m")
    assert cli.enable("p@m") == 1
    assert cli.disable("p@m") == 0
    # **값만 바뀌고 키는 남는다.** exit code만 재면 이 절반이 빠진다.
    assert cli.settings()["enabledPlugins"]["p@m"] is False
    assert cli.disable("p@m") == 1
    assert cli.enable("p@m") == 0
    assert cli.settings()["enabledPlugins"]["p@m"] is True


def test_enable_and_disable_on_an_unknown_plugin_create_a_ghost_key(tmp_path):
    """**실측**(2026-08-29 스모크 2장 — 옛 추정 4번을 뒤집은 자리).

    초판은 *"exit 1이고 값을 만들어 내지 않는다"*를 에뮬레이터의 규약으로 고정했다.
    실제 CLI는 **exit 0이고 키를 만든다**(`{"ghost@smoke-mkt": false}`). 그래서 이
    테스트가 재는 것은 안전 성질이 아니라 **위험**이다 — 이름이 `reject`에서
    `create_a_ghost_key`로 바뀐 것이 그 뜻이다.

    **왜 위험인가.** 복원 2단계(`install`)가 실패한 id에 3단계가 `disable`을 내면
    설치되지 않은 플러그인에 로컬 값 `false`가 생기고, 레포도 `false`이므로 다음 백업이
    그 키를 in_sync로 읽어 **next_base를 전진시킨다** — 복원 실패가 성공처럼 보이고,
    그 뒤로는 그 id가 add 버킷에 오지 않아 **영영 설치되지 않는다.** spec 10.4의
    *"실패한 항목은 로컬에 없으니 자동으로 빠진다"*가 이 갈래에서는 참이 아니다.

    **그 갈래는 이제 막혀 있다** — 2단계가 실패한 id는 3·4단계를 건너뛴다(9.3.2,
    sync-restore/SKILL.md 5-2). `test_plugin_cycle`의
    `test_a_failed_install_does_not_leave_a_ghost_key`가 그 방어를 잰다. 이 파일이 고정하는
    것은 방어가 아니라 **CLI가 무엇을 하는가**이고, 하네스가 그 위험을 무해한 no-op으로
    흉내 내지 못하게 막는 것이다.
    """
    cli = PluginCLI(str(tmp_path))
    assert cli.disable("ghost@m") == 0
    # 값이 생긴다. **부재는 「꺼짐」과 같지 않다** — 같았다면 exit 1이었을 것이다.
    assert cli.settings()["enabledPlugins"] == {"ghost@m": False}
    # 재실행은 이제 「이미 그 상태」라 exit 1이다.
    assert cli.disable("ghost@m") == 1
    # **두 파일 중 다른 쪽도 함께 잰다.** 설치 기록은 만들지 않는다 — 그래서 이 키는
    # `read_installed`의 installed_ids에 없는 **유령**이고, 다음 복원의 2단계는
    # 그것을 `install` 목록에 넣으려 하지만 로컬 값이 레포와 같아져 add 버킷 자체에
    # 오지 않는다. 설치 기록이 함께 생기면 위험의 모양이 달라지므로 여기서 고정한다.
    assert cli.installed()["plugins"] == {}
    # enable 방향은 스모크가 재지 않았다 — 한 메서드(`_set_value`)의 대칭으로 둔다.
    assert cli.enable("other@m") == 0
    assert cli.settings()["enabledPlugins"]["other@m"] is True


def test_a_non_boolean_value_reads_as_off(tmp_path):
    """**실측**(2026-08-29 스모크 3장). CLI는 비불리언 값을 「꺼짐」으로 읽는다.

    이 표가 spec 7.3의 H3(값 보류)와 `plugin_config.value_command`가 **비불리언 레포
    값에 언제나 `None`**을 돌려주는 것의 근거다 — 확장 값에 낼 수 있는 명령은
    `enable` 하나뿐이고 그것은 값을 `true`로 **파괴한다.** `disable`은 exit 1로 죽고
    값이 보존된다. 즉 어느 쪽도 "레포의 확장 값을 이 기기에 재현"하지 못한다.

    초판 에뮬레이터는 `현재값 == 요청값`으로 판정해 배열·객체에 `disable`을 내면
    **exit 0으로 값을 `false`로 갈아엎었다** — 실측과 반대다.

    **두 값을 한 기기에 함께 심고 dict 동등으로 잰다.** 루프로 한 키를 돌려 쓰면 행
    하나를 빼는 변조가 살아남는다(실측: `for value in (배열, 객체)`에서 객체 행을 뺀
    변조가 SURVIVED). 스모크가 잰 것은 **두 행**이므로 둘 다 실려 있어야 한다.
    """
    cli = PluginCLI(str(tmp_path))
    cli.set_enabled("arr@m", ["1.0.0"])
    cli.set_enabled("obj@m", {"version": "1.0.0"})
    # 「이미 꺼짐」 — 명령이 죽고 확장 값이 그대로 남는다.
    assert cli.disable("arr@m") == 1
    assert cli.disable("obj@m") == 1
    assert cli.settings()["enabledPlugins"] == {
        "arr@m": ["1.0.0"], "obj@m": {"version": "1.0.0"}}
    # 반대 방향은 통과하고 **값을 파괴한다.**
    assert cli.enable("arr@m") == 0
    assert cli.enable("obj@m") == 0
    assert cli.settings()["enabledPlugins"] == {"arr@m": True, "obj@m": True}


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


def test_marketplace_add_is_idempotent_and_writes_a_github_source(tmp_path):
    """1-b #7 — 재실행도 exit 0. 그리고 **그 명령이 만드는 값의 모양**(6번).

    14.3 표의 `marketplace add` 행이 이 파일에 없었다(실측 — 이 명령을 비멱등으로
    만드는 변조도, exit code를 언제나 1로 만드는 변조도 스위트 전체에서 살아남았다).
    다른 테스트들이 이 명령을 **셋업으로 부르기만** 하고 반환값도 재실행도 재지 않았기
    때문이다.

    `o/r` 인자가 github 모양을 만드는 것은 **실측**이다(plugin_cli 모듈 docstring 6번 —
    2026-08-29 스모크 2차 9장). 판별의 나머지 두 모양은
    `test_marketplace_add_detects_the_source_from_the_argument`가 잰다. 이전에는 이 모양이
    교대 시나리오 하나(H2)에 묻혀 있어서, 자기 주제가 directory 보류인 그 시나리오를
    손대는 순간 두 자리가 함께 풀렸다.

    1-b #10 — `autoUpdate`를 설정하는 옵션이 CLI에 **없으므로** 값에도 넣지 않는다.
    그 필드의 부재를 dict 동등으로 함께 고정한다.
    """
    cli = PluginCLI(str(tmp_path))
    assert cli.marketplace_add("m", "o/r") == 0
    assert cli.settings()["extraKnownMarketplaces"] == {
        "m": {"source": {"source": "github", "repo": "o/r"}}}
    # 멱등 — 재실행도 exit 0이고 값이 그대로다(`Marketplace 'x' already on disk`).
    # marketplace remove·uninstall·enable/disable의 "재실행은 exit 1"과 **반대편**이다.
    assert cli.marketplace_add("m", "o/r") == 0
    assert cli.settings()["extraKnownMarketplaces"] == {
        "m": {"source": {"source": "github", "repo": "o/r"}}}


# ── `marketplace add`의 출처 분류 (3차 스모크 14장의 표 전부) ──────────────────
#
# 표를 **여기 한 벌** 두고 아래 셋이 함께 쓴다 — 판별, 왕복, 완전성. 세 곳에 손으로
# 나열하면 한 곳에서 행이 빠져도 나머지가 초록이다.
#
# **순서가 규칙이다.** github 정규화가 `.git` 규칙보다 먼저다. 그래서
# `https://github.com/o/r.git`는 이 에뮬레이터에서 github이 되는데, 그 모양은
# **여전히 미측정이다**(네트워크가 필요하다). 프로덕션에는 도달 경로가 없다 —
# `marketplace_arg`가 github 출처에 내는 것은 `repo` 필드이지 URL이 아니다.
SOURCE_ARG_TABLE = [
    ("/tmp/mkt", {"source": "directory", "path": "/tmp/mkt"}),
    ("o/r", {"source": "github", "repo": "o/r"}),
    # 정규화 — 인자 모양이 달라도 값이 같다.
    ("https://github.com/o/r", {"source": "github", "repo": "o/r"}),
    ("http://127.0.0.1:8733/gitmkt.git",
     {"source": "git", "url": "http://127.0.0.1:8733/gitmkt.git"}),
    ("http://127.0.0.1:8731/marketplace.json",
     {"source": "url", "url": "http://127.0.0.1:8731/marketplace.json"}),
]

# 표 밖의 모양. **값을 지어내지 않고 죽는다** — 조용히 github으로 쓰면 그 시나리오를
# 쓰는 사람이 왕복이 깨지는 것을 볼 자리가 없다(이 하네스가 이미 한 번 그렇게 틀렸다).
UNCLASSIFIED_ARGS = [
    "file:///tmp/mkt",          # 실측으로는 CLI가 exit 1로 거부한다 — 아래 테스트 참조
    "./relative/path",
    "just-a-word",
    "ftp://example.com/mkt.json",
]


@pytest.mark.parametrize("arg,source", SOURCE_ARG_TABLE, ids=[a for a, _ in SOURCE_ARG_TABLE])
def test_marketplace_add_detects_the_source_from_the_argument(tmp_path, arg, source):
    """**실측**(plugin_cli 모듈 docstring 6번 — 2026-08-29 스모크 2차 9장 · 3차 14장).

    초판 에뮬레이터는 **언제나 github 모양**으로 썼다. 실제 CLI는 인자 하나에서 출처
    종류를 판별한다. 2차가 앞의 셋을, 3차가 뒤의 둘(`git`·`url`)을 쟀다 — 로컬에
    http 서버를 세워야 나오는 갈래라 2차 픽스처로는 만들 수 없었다.
    """
    cli = PluginCLI(str(tmp_path))
    assert cli.marketplace_add("m", arg) == 0
    assert cli.settings()["extraKnownMarketplaces"]["m"] == {"source": source}


@pytest.mark.parametrize("arg", UNCLASSIFIED_ARGS)
def test_marketplace_add_refuses_to_invent_a_source_for_an_unmeasured_shape(tmp_path, arg):
    """표 밖의 인자에는 `NotImplementedError`다 — fail-closed를 유지한다.

    `file://`는 3차 스모크 14장이 **거부(exit 1)** 로 쟀지만 이 에뮬레이터는 그 갈래를
    재현하지 않는다. `marketplace_add`의 계약이 "멱등, exit 0"이고 거부 갈래를 넣으면
    그 계약이 갈리는데, **프로덕션에는 그 인자를 만들 경로가 사실상 없다**(사용자가
    settings에 손으로 `{"source":"url","url":"file://…"}`를 적은 경우뿐이다).
    모르는 모양과 같은 자리에서 죽는 편이 좁고, 죽으면 그 시나리오를 쓰는 사람이 본다.
    """
    cli = PluginCLI(str(tmp_path))
    with pytest.raises(NotImplementedError):
        cli.marketplace_add("m", arg)


def test_the_emulator_writes_every_source_kind_production_can_build_an_argument_for():
    """**완전성 단정.** 위 표에서 행이 빠지면 그 출처가 아무 데서도 재지지 않는다.

    기준을 손으로 적지 않고 **프로덕션의 `_SOURCE_ARG_FIELDS`에서 뽑는다** — 그 맵이
    인자를 만들 수 있는 출처의 정본이고, 거기 있는 종류를 에뮬레이터가 못 쓰면 왕복을
    검증할 자리가 없다. `directory`는 그 맵에 없다(H2로 보류되어 인자를 만들지 않는다)
    — 그래도 값의 모양은 이 에뮬레이터가 쓰므로 함께 센다.
    """
    produced = {PluginCLI._marketplace_source(arg)["source"] for arg, _ in SOURCE_ARG_TABLE}
    assert produced == set(pc._SOURCE_ARG_FIELDS) | {"directory"}


# 3차 스모크 13장의 **두 행**이 이 픽스처의 근거다. 값도 인자도 그 표에서 그대로 옮겼다.
ROUND_TRIP = [
    ({"source": {"source": "url", "url": "http://127.0.0.1:8731/marketplace.json"}},
     "http://127.0.0.1:8731/marketplace.json"),
    ({"source": {"source": "git", "url": "http://127.0.0.1:8733/gitmkt.git"}},
     "http://127.0.0.1:8733/gitmkt.git"),
    # github 행도 함께 둔다 — 왕복이 닫힌 것이 셋임을 한 자리에서 말한다(2차 9장).
    ({"source": {"source": "github", "repo": "o/r"}}, "o/r"),
]


def test_the_round_trip_table_covers_every_source_kind_that_gets_an_argument():
    """**완전성 단정.** 아래 표에서 행이 빠지면 그 출처의 왕복이 아무 데서도 재지지 않는다.

    기준을 손으로 적지 않고 `_SOURCE_ARG_FIELDS`에서 뽑는다 — 인자를 만들 수 있는 출처의
    정본이 그 맵이고, 거기 있는 종류의 왕복이 비면 8.6이 "복원 가능"이라고 적는 근거가
    사라진다. 위 판별 표(`SOURCE_ARG_TABLE`)와는 **다른 것을 잰다**: 저쪽은 인자 → 값,
    이쪽은 값 → 인자 → 값이다. 한쪽만 있으면 `marketplace_arg` 쪽 결함이 새어 나간다.
    """
    assert {v["source"]["source"] for v, _ in ROUND_TRIP} == set(pc._SOURCE_ARG_FIELDS)


@pytest.mark.parametrize("value,arg", ROUND_TRIP,
                         ids=[v["source"]["source"] for v, _ in ROUND_TRIP])
def test_a_marketplace_value_round_trips_through_the_registration_argument(tmp_path, value, arg):
    """레포 값 → `marketplace_arg` → 에뮬레이터 `marketplace add` → **같은 값**.

    왕복이 깨지면 복원이 등록한 마켓플레이스가 다음 백업에서 **다른 값**으로 보여
    그 항목이 영원히 `changed`로 남는다. 8.6이 "복원 가능"이라고 적는 근거가 이 왕복이고,
    `url`·`git` 두 행은 3차 스모크(13장)가 실측으로 닫았다 — 그전에는 필드 이름조차
    확인되지 않아 spec이 그 둘을 14.5의 미측정 목록으로 이월하고 있었다.
    """
    assert pc.marketplace_arg(value) == arg
    cli = PluginCLI(str(tmp_path))
    assert cli.marketplace_add("m", arg) == 0
    assert cli.settings()["extraKnownMarketplaces"]["m"] == value


def test_set_directory_marketplace_writes_a_directory_source(tmp_path):
    """directory 출처 값의 모양 — **실측**(모듈 docstring 7번 — 2026-08-29 스모크 2장).

    CLI 명령이 아니라 픽스처다(`marketplace add <경로>`의 결과이지만 복원 경로가 이
    갈래에 도달하지 않는다 — H2로 보류된다). 그래도 계약 파일이 지는 것은, 이 모양이
    `plugin_config._source_kind`가 읽는 형태와 어긋나면 H2가 통째로 죽고 로컬 디렉토리
    마켓플레이스가 레포로 올라가기 때문이다. 그 결과는 기기 B의 restore가 등록할 소스도
    없는 항목을 매번 요구하는 것이다.

    이 모양 역시 교대 시나리오 하나(H2)에만 걸려 있었다 — 그 시나리오는 **결과**(레포에
    올라가지 않는다)를 재고, 여기서는 **입력**(그 결과를 만드는 값의 모양)을 잰다.

    초판에는 이 모양이 추정이었다. 스모크가 실제 CLI에 디렉토리 경로를 주고 읽은 값이
    **가정과 정확히 같아서** 표식만 승격됐고 값은 그대로다.
    """
    cli = PluginCLI(str(tmp_path))
    assert cli.set_directory_marketplace("mylocal", "/tmp/x") == 0
    assert cli.settings()["extraKnownMarketplaces"] == {
        "mylocal": {"source": {"source": "directory", "path": "/tmp/x"}}}
    assert pc.directory_marketplaces(cli.settings()["extraKnownMarketplaces"],
                                     {}) == frozenset({"mylocal"})


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
    # **N1의 핵심 축이다(실측 행).** 자식이 직접 설치와 **똑같은 모양**으로
    # enabledPlugins에 들어가고, 구별 수단은 auto 플래그 하나뿐이다. 이것을 재지 않으면
    # 자식을 아예 넣지 않는 에뮬레이터로 바뀌어도 저장소가 조용하고(실측), 그러면
    # H1("직접 설치한 플러그인이 의존성으로 재편입됐다" — 조용히 사라지는 경로)의
    # 커버리지가 무증상으로 사라진다.
    assert cli.settings()["enabledPlugins"]["child@m"] is True
    assert pc.read_auto_ids(cli.installed_path) == frozenset({"child@m"})
    cli.install("child@m")
    assert cli.settings()["enabledPlugins"]["child@m"] is True
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
    **실측**(plugin_cli 모듈 docstring 8번 — 2026-08-29 스모크 2차 8장): N4는 배열의
    존재와 항목의 필드를 쟀을 뿐이고 1차 스모크는 **스코프 하나만** 세워 닫지 못했는데,
    2차가 `--scope project`로 한 벌 더 설치한 뒤 `--scope user`로 재설치해
    `["project", "user"]` 둘 다 남는 것을 읽었다.
    (이 문단은 모듈 docstring 8번이 승격될 때 함께 고쳐지지 않아 **한쪽만 낡아 있었다** —
    표시 규약이 요구하는 양방향 갱신을 Task 7의 전수 grep이 잡았다.)
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
