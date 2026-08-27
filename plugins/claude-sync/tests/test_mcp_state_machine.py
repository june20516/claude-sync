"""backup을 반복 적용했을 때 고정점에 도달하는지 검증한다.

단발 호출 테스트는 상태 기계 결함을 잡지 못한다. 이전 설계의 Critical 결함
("base ← 레포 파일 전체")은 판정표를 100% 덮은 테스트를 전부 통과했지만,
2회차 백업에서 타 기기의 서버를 전멸시켰다.

**어댑터와 값 픽스처를 주입받는다.** 열 개의 판정표 시나리오는 세 어댑터가 공유한다 —
MCP, 그리고 플러그인의 두 섹션이다.

**enabledPlugins는 이 시나리오 집합을 쓸 수 없다.** 케이스 9가 서로 다른 값 셋을
요구하는데 불리언은 값이 둘뿐이고, 값을 확장 포맷으로 늘리면 H3가 전부 보류해 판정표를
타지 않는다. 그 섹션은 아래 **보류 시나리오**가 맡는다 — 보류의 진입·유지·이탈은
회차 사이에 상태가 변해야 표현되므로 애초에 다른 하네스가 필요하다.

(파일 이름이 여전히 test_mcp_state_machine.py인 것은 앵커를 늘리지 않기 위해서다.
내용은 더 이상 MCP 전용이 아니다.)
"""
import pytest

import keyed_sync as ks
import mcp_config as mc
import plugin_config as pc


class Adapter:
    """상태 기계 테스트가 어댑터에 요구하는 최소 표면.

    merge(local, repo, base)와 next_base(local, base, merged)를 **위치 인자 셋**으로
    부른다 — normalize·hold는 어댑터가 클로저로 닫아 넣는다(spec 5.5의 위치 인자 순서).
    merge는 병합 결과를 merged_key에, 다음 base를 "next_base"에 담아 돌려줘야 한다.

    values는 (A, B, ORIG)이고 **정규화 후에도 셋이 서로 달라야 한다.** 케이스 9가
    local·repo·base 세 값이 모두 다를 것을 요구하기 때문이다. 마스킹이 값을 뭉개는
    섹션(pluginConfigs)에서는 **키 이름으로** 값을 갈라야 한다 — 값만 다르게 두면
    정규화 후 셋이 같아져 케이스 9가 조용히 케이스 6이 된다.

    싣는 값은 **정규화를 한 번 통과시킨 것**이다. merge·next_base가 돌려주는 값은 전부
    정규화된 것이라, 원본을 그대로 기대값으로 쓰면 마스킹하는 섹션에서 `repo[k] == B`
    류의 단정이 전부 어긋난다(실측: pluginConfigs에서 열 중 여덟이 FAIL). normalize가
    멱등이라는 계약(spec 5.2) 위에서만 성립한다 — 두 번째 적용이 값을 또 바꾸면 이
    기대값이 틀린다. 두 섹션의 훅은 멱등이고 그 성질은 test_plugin_config.py가 지킨다.
    """

    def __init__(self, name, merge, next_base, values, merged_key="servers", normalize=None):
        self.name, self.merge, self.next_base = name, merge, next_base
        self.merged_key = merged_key
        self.normalize = normalize or (lambda mapping: mapping)
        one = lambda value: self.normalize({"k": value})["k"]  # noqa: E731
        self.A, self.B, self.ORIG = (one(value) for value in values)
        pairs = ((self.A, self.B), (self.B, self.ORIG), (self.A, self.ORIG))
        assert not any(ks.same(x, y) for x, y in pairs), (
            "%s: A·B·ORIG가 정규화 후에도 서로 달라야 한다 — 케이스 9를 표현할 수 없다"
            % name)


def plugin_adapter(section, values, hold=None):
    """플러그인 한 섹션을 상태 기계 하네스에 맞춘다.

    hold를 주면 그것을 쓰고, 주지 않으면 보류 없음이다 — 판정표 시나리오는 보류가 없는
    상태를 전제한다(보류 키는 판정표를 타지 않는다).
    next_base가 value_held를 **스스로 계산해 넘기는 것**이 restore 경로의 계약이다
    (plan_plugins.apply_base와 같은 형태). 넘기지 않으면 보류 키가 base에 얼어붙는다.
    """
    normalize = pc.SECTION_NORMALIZE[section]
    held = hold if hold is not None else ks.no_hold

    def merge(local, repo, base):
        return ks.merge(local, repo, base, normalize=normalize, hold=held)

    def next_base(local, base, merged):
        value_held = set(held(normalize(local), normalize(merged))["value"])
        return ks.next_base(local, base, merged, normalize=normalize,
                            value_held=value_held)

    return Adapter("plugins:%s" % section, merge, next_base, values,
                   merged_key="merged", normalize=normalize)


ADAPTERS = [
    Adapter("mcp", mc.merge, mc.next_base,
            ({"command": "a"}, {"command": "b"}, {"command": "o"})),
    plugin_adapter("extraKnownMarketplaces",
                   ({"source": {"source": "github", "repo": "o/a"}},
                    {"source": {"source": "github", "repo": "o/b"}},
                    {"source": {"source": "github", "repo": "o/orig"}})),
    # 값이 아니라 **키 이름**으로 셋을 가른다 — redact가 값을 전부 SENTINEL로 만들므로
    # 값만 다르게 두면 정규화 후 셋이 같아진다.
    plugin_adapter("pluginConfigs",
                   ({"options": {"ka": "x"}}, {"options": {"kb": "x"}},
                    {"options": {"ko": "x"}})),
]


def test_adapters_cover_every_section_that_can_run_the_decision_table():
    """어느 하나가 빠지면 그 섹션에서 판정표가 검증되지 않는다.

    enabledPlugins가 없는 것은 의도다 — 값이 둘뿐이라 케이스 9를 표현할 수 없다.
    그 섹션은 아래 보류 시나리오가 맡는다.
    """
    assert {adapter.name for adapter in ADAPTERS} == {
        "mcp", "plugins:extraKnownMarketplaces", "plugins:pluginConfigs"}


@pytest.fixture(params=ADAPTERS, ids=lambda a: a.name)
def adapter(request):
    return request.param


def backup_round(adapter, local, repo, base):
    """푸시에 성공한 backup 1회를 흉내낸다: 레포 ← 병합 결과, base ← next_base."""
    result = adapter.merge(local, repo, base)
    merged = result[adapter.merged_key]
    return result, merged, result["next_base"]


def repeat_backup(adapter, local, repo, base, rounds=3, before_round=None):
    """같은 로컬로 backup을 rounds회 반복하고 매 회차의 (보고, 레포, base)를 모은다.

    before_round(index, local, repo, base) -> (local, repo, base) 를 주면 그 회차 **직전에**
    셋을 갈아끼운다. 보류 상태(hold 클로저가 읽는 dict)도 여기서 바꾼다.

    이 훅이 없으면 보류의 **이탈**을 표현할 수 없다 — 회차마다 같은 local과 같은 hold를
    넘기게 되므로, 7.3이 경고한 "해제 후 착지"(케이스 9가 아니라 케이스 7이어야 한다)가
    정의상 표현 불가능하다.
    """
    snapshots = []
    exclude = (adapter.merged_key, "next_base")
    for index in range(rounds):
        if before_round is not None:
            local, repo, base = before_round(index, local, repo, base)
        result, repo, base = backup_round(adapter, local, repo, base)
        report = {k: v for k, v in result.items() if k not in exclude}
        snapshots.append((report, repo, base))
    return snapshots


def assert_fixed_point_from_second_round(snapshots):
    """2회차부터 레포 내용과 보고가 변하지 않아야 한다."""
    assert snapshots[1] == snapshots[2], "2회차와 3회차가 다르다 — 고정점이 아니다"


def test_repeated_backup_without_cleanup_keeps_reporting_local_stale(adapter):
    """케이스 4를 정리하지 않고 반복해도 항목이 되살아나지 않고 base[X]가 전진하지 않는다."""
    A = adapter.A
    local = {"X": A, "y": A}
    snapshots = repeat_backup(adapter, local, {"y": A}, {"X": A})
    for report, repo, base in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo
        assert base["X"] == A
        assert base["y"] == A
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_removed_backup_converges_without_stale(adapter):
    """restore '제거' 경로: X가 L·R·S 어디에도 없는 상태로 안정된다."""
    A = adapter.A
    local = {"y": A}
    base = adapter.next_base(local, {"X": A, "y": A}, {"y": A})   # restore의 base 갱신(①)
    assert "X" not in base
    snapshots = repeat_backup(adapter, local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == [] and report["deleted"] == []
        assert sorted(repo) == ["y"]
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_kept_backup_pushes_entry_back(adapter):
    """restore '유지' 경로: base에서 X를 지웠으므로 케이스 1로 push되고 이후 불변."""
    A = adapter.A
    local = {"X": A, "y": A}
    base = adapter.next_base(local, {"X": A}, {"y": A})
    base.pop("X", None)                                     # override ② (7.4)
    snapshots = repeat_backup(adapter, local, {"y": A}, base)
    assert sorted(snapshots[0][1]) == ["X", "y"]
    for report, _, _ in snapshots:
        assert report["local_stale"] == []
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_deferred_backup_keeps_case4(adapter):
    """restore '나중에' 경로: 아무것도 바뀌지 않고 케이스 4가 반복된다."""
    A = adapter.A
    local = {"X": A, "y": A}
    base = adapter.next_base(local, {"X": A}, {"y": A})           # override 없음
    assert base["X"] == A
    snapshots = repeat_backup(adapter, local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case9_conflict_freezes_base(adapter):
    """케이스 9: 매회 conflicts=[Z], 레포는 R 유지, base[Z] 고정."""
    A, B, ORIG = adapter.A, adapter.B, adapter.ORIG
    snapshots = repeat_backup(adapter, {"Z": A}, {"Z": B}, {"Z": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert repo["Z"] == B
        assert base["Z"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case5_conflict_freezes_base(adapter):
    """케이스 5: 매회 conflicts=[X], 레포에 X 없음, base[X] 고정."""
    A, ORIG = adapter.A, adapter.ORIG
    snapshots = repeat_backup(adapter, {"X": A}, {}, {"X": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["X"]
        assert "X" not in repo
        assert base["X"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_conflicted_name_freezes_only_its_own_base(adapter):
    """전역 게이트를 되살리면 안 되는 이유 — 충돌 하나가 전체 base를 동결하지 않는다."""
    A, B, ORIG = adapter.A, adapter.B, adapter.ORIG
    snapshots = repeat_backup(adapter, {"Z": A, "n": B}, {"Z": B}, {"Z": ORIG})
    for report, _, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert base["Z"] == ORIG
        assert base["n"] == B
    assert_fixed_point_from_second_round(snapshots)


def test_case2_remote_added_survives_repeated_backup(adapter):
    """타 기기가 추가한 항목이 2회차에도 레포에 남는다 — 옛 설계가 여기서 데이터를 잃었다."""
    A, B = adapter.A, adapter.B
    snapshots = repeat_backup(adapter, {"x": A}, {"x": A, "z": B}, {"x": A})
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["z"] == B
        assert report["repo_ahead"] == ["z"]
    assert_fixed_point_from_second_round(snapshots)


def test_case8_remote_change_survives_repeated_backup(adapter):
    """타 기기의 변경이 로컬 값으로 되돌아가지 않는다."""
    B, ORIG = adapter.B, adapter.ORIG
    snapshots = repeat_backup(adapter, {"x": ORIG}, {"x": B}, {"x": ORIG})
    for report, repo, base in snapshots:
        assert repo["x"] == B
        assert base["x"] == ORIG
        assert report["repo_ahead"] == ["x"]
    assert_fixed_point_from_second_round(snapshots)


def test_new_machine_without_base_does_not_delete_others_on_second_round(adapter):
    """base=None으로 시작한 새 기기가 2회차에 남의 항목을 삭제하지 않는다."""
    A, B = adapter.A, adapter.B
    snapshots = repeat_backup(adapter, {"mine": A}, {"theirs": B}, None)
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["theirs"] == B
    assert_fixed_point_from_second_round(snapshots)


# ---------------------------------------------------------------- 보류 시나리오
#
# 위 열 개는 보류가 **없는** 상태의 판정표다. 아래는 보류가 걸린 키가 회차를 넘어
# 어떻게 움직이는지를 본다 — 진입해서 유지될 때, 이탈할 때, 보류 중에 레포에서
# 사라졌을 때, 그리고 이탈이 **삭제로 착지할 수 있는** 배치일 때. 다회차가 아니면
# 넷 다 표현되지 않는다. 일곱 중 하나(restore 경로의 base 갱신,
# test_restore_base_drops_the_held_key_instead_of_freezing_it)만 단발이다 —
# merge 경로가 그 코드를 지나지 않기 때문이다.

def held_state(released=()):
    return {"pluginConfigs": {}, "release": {"enabledPlugins": sorted(released)}}


def live_hold(section, state):
    """**실제 어댑터의 hold**를 회차마다 현재 상태로 다시 만든다.

    테스트 더블을 쓰면 _make_hold의 회귀를 이 파일이 하나도 잡지 못한다.
    state는 before_round가 바꾼다 — 그것이 보류의 진입·이탈이다.

    섹션 하나짜리 문서를 넘기므로 held_context의 directory_names가 비고, 따라서 이
    시나리오들에서 발화하는 것은 **H1과 H3뿐이다** — H2는 소스가 없어 항상 거짓이고
    H4는 pluginConfigs 섹션에서만 본다.
    """
    def hold(local, repo):
        hooks = pc.build_hooks({section: local}, {section: repo},
                               auto_ids=state["auto_ids"], held_state=state["held"])
        return hooks[section]["hold"](local, repo)
    return hold


def enabled_adapter(state):
    """enabledPlugins 전용 값 도메인 — 불리언 둘과 확장 포맷 하나."""
    return plugin_adapter("enabledPlugins", (True, False, ["1.0.0"]),
                          hold=live_hold("enabledPlugins", state))


def test_h3_hold_preserves_the_repo_value_across_rounds():
    """보류 유지 — 레포의 버전 제약이 회차를 거쳐도 true로 덮이지 않는다.

    코어의 "보류 키는 레포 값을 그대로 싣는다"를 지우면 여기서 걸린다.

    두 빈 단정의 무게가 다르다(실측) — H3를 지우면 conflicts가 ["p@m"]으로 **채워진다**
    (케이스 9). deleted는 채워질 수 없다: 그 갈래는 `not in_l`을 요구하는데 로컬이
    p@m을 계속 쥐고 있다. 채워지는 배치는 아래
    test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3이다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)
    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {})
    for report, repo, base in snapshots:
        assert repo["p@m"] == ["1.0.0"]
        assert report["held"] == ["p@m"]
        assert report["deleted"] == [] and report["conflicts"] == []
        assert "p@m" not in base            # 값 보류 키는 base에서 제거된다 (5.3)
    assert_fixed_point_from_second_round(snapshots)


def test_h3_release_lands_on_case7_not_case9():
    """보류 해제 후 착지 — 7.3이 스스로 경고한 자리다.

    해제만 하면 base에 그 키가 없어 케이스 9로 떨어지고 레포 값이 그대로 남는다.
    apply-base가 해제와 **동시에** keep_local(base[k] ← 레포 값)을 걸어야 케이스 7이 되고,
    그때서야 로컬 값이 push되어 레포 값이 불리언이 되고 H3가 자연 해제된다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 2:                                  # restore의 "이 기기 값으로 통일"
            state["held"] = held_state(["p@m"])         # 해제 표식
            base = dict(base, **{"p@m": repo["p@m"]})   # 동시에 keep_local
        if index == 3:
            # next_held_state의 release 정리를 흉내낸다 — "레포 값이 불리언이 되었거나
            # 키가 사라진 항목을 정리한다". 표식을 남겨두면 마지막 held 단정이 **표식
            # 때문에도** 참이 되어, 그 아래 적은 "레포 값이 불리언 → 자연 해제"를
            # 확인하지 못한다(H3의 두 조건이 함께 거짓이라 어느 쪽이 이겼는지 모른다).
            state["held"] = held_state()
        return local, repo, base

    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {},
                              rounds=4, before_round=before)
    assert snapshots[1][1]["p@m"] == ["1.0.0"]          # 해제 전에는 보존
    report, repo, base = snapshots[2]
    assert repo["p@m"] is True                          # 케이스 7 → 로컬 값 push
    assert report["conflicts"] == []                    # 케이스 9가 **아니다**
    assert base["p@m"] is True
    assert snapshots[3][1]["p@m"] is True               # 이후 불변
    assert snapshots[3][0]["held"] == []                # 레포 값이 불리언 → 자연 해제


def test_h3_release_without_keep_local_would_land_on_case9():
    """왜 두 조각이 함께여야 하는지를 고정한다 — 해제만 하면 반대 결과가 난다.

    이 테스트가 실패하면 keep_local 동시 적용이 불필요해진 것이므로 apply-base와
    spec 7.3을 함께 고쳐야 한다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 2:
            state["held"] = held_state(["p@m"])         # 해제만 한다
        return local, repo, base

    snapshots = repeat_backup(adapter, {"p@m": True}, {"p@m": ["1.0.0"]}, {},
                              rounds=3, before_round=before)
    report, repo, _ = snapshots[2]
    assert report["conflicts"] == ["p@m"]
    assert repo["p@m"] == ["1.0.0"]


def test_held_key_missing_from_the_repo_does_not_become_a_deletion():
    """보류 키가 레포에서 사라졌을 때 — 이탈이 케이스 3·4·5로 착지하지 않는다.

    보류 중에는 판정표를 타지 않으므로 조용하고, 이탈하면 base에 그 키가 없으므로
    케이스 1(로컬 신규)로 착지해 **레포로 되돌아간다.** 이것이 base 제거 규칙(5.3)이
    보장하는 성질이고, 14.2 #4가 테스트로 강제하라고 지목한 것이다.

    (H1의 value.add를 지우면 local_stale이 ["z@m"]으로 **채워진다**(케이스 4, 실측).
    반면 deleted는 여기서 채워질 수 없다 — 로컬이 z@m을 계속 쥐고 있어 `not in_l`이
    성립하지 않는다. **케이스 3이 실제로 날 수 있는 배치**는 아래
    test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3이 맡는다.)
    """
    state = {"auto_ids": frozenset({"z@m"}), "held": held_state()}
    adapter = plugin_adapter("enabledPlugins", (True, False, ["1.0.0"]),
                             hold=live_hold("enabledPlugins", state))

    def before(index, local, repo, base):
        if index == 0:
            repo = {}                                   # 타 기기가 z를 지웠다
        if index == 2:
            state["auto_ids"] = frozenset()             # prune 이후 — 보류 이탈
        return local, repo, base

    snapshots = repeat_backup(adapter, {"z@m": True}, {"z@m": True}, {"z@m": True},
                              rounds=4, before_round=before)
    for report, repo, base in snapshots[:2]:
        assert report["deleted"] == [] and report["local_stale"] == []
        assert "z@m" not in repo                        # 보류 중에는 조용하다
        assert "z@m" not in base
    assert snapshots[2][1]["z@m"] is True               # 이탈 → 케이스 1로 push
    assert snapshots[2][0]["deleted"] == []
    assert snapshots[3][1]["z@m"] is True               # 이후 불변


def test_auto_hold_keeps_the_entry_out_of_the_repo_across_rounds():
    """H1 — 의존성 플러그인이 반복 백업에서도 레포로 승격되지 않는다 (N6)."""
    state = {"auto_ids": frozenset({"dep@m"}), "held": held_state()}
    adapter = enabled_adapter(state)
    snapshots = repeat_backup(adapter, {"dep@m": True, "mine@m": True}, {}, {})
    for report, repo, base in snapshots:
        assert "dep@m" not in repo and "dep@m" not in base
        assert repo["mine@m"] is True
        assert report["held"] == ["dep@m"]
    assert_fixed_point_from_second_round(snapshots)


def test_restore_base_drops_the_held_key_instead_of_freezing_it():
    """restore 경로의 계약 — apply-base가 value_held를 **스스로 계산해** 넘긴다.

    plan_plugins.apply_base는 pc.value_held_for로 집합을 만들어 ks.next_base에 넘긴다.
    plugin_adapter.next_base가 그 형태를 그대로 흉내내는데, 위 다섯 시나리오는 전부
    merge 경로(backup_round)만 타므로 그 한 줄을 지나지 않는다 — 여기가 유일한 자리다.
    빼면 예외도 경고도 없이 보류 키가 **이전 base 값으로** 얼어붙는다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)
    local = {"mine@m": True}
    repo = {"mine@m": True, "p@m": ["1.0.0"]}
    frozen = {"mine@m": True, "p@m": True}      # 보류가 걸리기 전에 합의했던 값
    base = adapter.next_base(local, frozen, repo)
    assert "p@m" not in base                    # 값 보류 키는 base에서 제거된다 (5.3)
    assert base["mine@m"] is True               # 보류가 아닌 키는 그대로 전진한다


def test_release_of_a_key_missing_from_the_local_lands_on_case2_not_case3():
    """5.3이 지목한 손실 경로 — 보류 키가 base에 얼어붙으면 해제 순간 케이스 3이 난다.

    이 기기는 p@m을 켜지 않았고(로컬에 없다), 타 기기가 레포에 버전 제약을 올려 H3가
    보류한다. 보류 중 base에서 그 키가 빠지므로(5.3) 해제 시 in_s가 거짓이 되어
    **케이스 2**로 착지하고 레포 값이 살아남는다. base에 남으면 in_s가 참이 되어
    **케이스 3(deleted)** 이 나고 타 기기가 올린 값이 레포에서 지워진다 — 위 시나리오들의
    deleted 단정이 구조적으로 채워질 수 없는 것과 달리, 여기서는 실제로 채워진다.
    """
    state = {"auto_ids": frozenset(), "held": held_state()}
    adapter = enabled_adapter(state)

    def before(index, local, repo, base):
        if index == 2:
            state["held"] = held_state(["p@m"])         # 해제만 한다 — keep_local 없음
        return local, repo, base

    snapshots = repeat_backup(adapter, {"mine@m": True},
                              {"mine@m": True, "p@m": ["1.0.0"]},
                              {"mine@m": True, "p@m": True},
                              rounds=4, before_round=before)
    for report, repo, base in snapshots[:2]:
        assert report["held"] == ["p@m"]
        # conflicts는 여기서 채워질 수 없다(양 갈래 모두 `in_l`을 요구한다) — 동반 기록이다.
        assert report["deleted"] == [] and report["conflicts"] == []
        assert repo["p@m"] == ["1.0.0"]
        assert "p@m" not in base                        # 보류 중 base에서 빠진다 (5.3)
    report, repo, base = snapshots[2]
    # 실측: base 제거 규칙을 지우면 여기서 deleted == ["p@m"]이 되고 레포가
    # {"mine@m": True}로 줄어든다 — 타 기기가 올린 버전 제약이 사라진다.
    assert report["deleted"] == []                      # 케이스 3이 **아니다**
    assert report["repo_ahead"] == ["p@m"]              # 케이스 2로 착지
    assert repo["p@m"] == ["1.0.0"]
    assert snapshots[3] == snapshots[2]                 # 이후 불변
