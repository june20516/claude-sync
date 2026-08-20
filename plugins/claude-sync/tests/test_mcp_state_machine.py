"""backup을 반복 적용했을 때 고정점에 도달하는지 검증한다 (spec 13장 멱등성 표).

단발 호출 테스트는 상태 기계 결함을 잡지 못한다. 이전 설계의 Critical 결함
("base ← 레포 파일 전체")은 판정표를 100% 덮은 테스트를 전부 통과했지만,
2회차 백업에서 타 기기의 서버를 전멸시켰다.
"""
import mcp_config as mc

A = {"command": "a"}
B = {"command": "b"}
ORIG = {"command": "o"}


def backup_round(local, repo, base):
    """푸시에 성공한 backup 1회를 흉내낸다: 레포 ← servers, base ← next_base.

    반환 (보고, 다음 레포, 다음 base).
    """
    result = mc.merge(local, repo, base)
    return result, result["servers"], result["next_base"]


def repeat_backup(local, repo, base, rounds=3):
    """같은 로컬로 backup을 rounds회 반복하고 매 회차의 (보고, 레포, base)를 모은다."""
    snapshots = []
    for _ in range(rounds):
        result, repo, base = backup_round(local, repo, base)
        report = {k: v for k, v in result.items() if k not in ("servers", "next_base")}
        snapshots.append((report, repo, base))
    return snapshots


def assert_fixed_point_from_second_round(snapshots):
    """2회차부터 레포 내용과 보고가 변하지 않아야 한다."""
    assert snapshots[1] == snapshots[2], "2회차와 3회차가 다르다 — 고정점이 아니다"


def test_repeated_backup_without_cleanup_keeps_reporting_local_stale():
    """케이스 4를 정리하지 않고 반복해도 서버가 되살아나지 않고 base[X]가 전진하지 않는다."""
    local = {"X": A, "y": A}
    snapshots = repeat_backup(local, {"y": A}, {"X": A})
    for report, repo, base in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo                 # 되살아나지 않는다
        assert base["X"] == A                  # base[X] 고정
        assert base["y"] == A                  # 다른 이름의 base는 정상 전진
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_removed_backup_converges_without_stale():
    """restore '제거' 경로: X가 L·R·S 어디에도 없는 상태로 안정된다."""
    local = {"y": A}
    base = mc.next_base(local, {"X": A, "y": A}, {"y": A})   # restore의 base 갱신(①)
    assert "X" not in base
    snapshots = repeat_backup(local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == [] and report["deleted"] == []
        assert sorted(repo) == ["y"]
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_kept_backup_pushes_server_back():
    """restore '유지' 경로: base에서 X를 지웠으므로 케이스 1로 push되고 이후 불변."""
    local = {"X": A, "y": A}
    base = mc.next_base(local, {"X": A}, {"y": A})
    base.pop("X", None)                                     # override ② (7.4)
    snapshots = repeat_backup(local, {"y": A}, base)
    assert sorted(snapshots[0][1]) == ["X", "y"]            # 1회차에 복귀
    for report, _, _ in snapshots:
        assert report["local_stale"] == []
    assert_fixed_point_from_second_round(snapshots)


def test_after_restore_deferred_backup_keeps_case4():
    """restore '나중에' 경로: 아무것도 바뀌지 않고 케이스 4가 반복된다."""
    local = {"X": A, "y": A}
    base = mc.next_base(local, {"X": A}, {"y": A})           # override 없음
    assert base["X"] == A
    snapshots = repeat_backup(local, {"y": A}, base)
    for report, repo, _ in snapshots:
        assert report["local_stale"] == ["X"]
        assert "X" not in repo
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case9_conflict_freezes_base():
    """케이스 9: 매회 conflicts=[Z], 레포는 R 유지, base[Z] 고정."""
    snapshots = repeat_backup({"Z": A}, {"Z": B}, {"Z": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert repo["Z"] == B
        assert base["Z"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_repeated_backup_with_case5_conflict_freezes_base():
    """케이스 5: 매회 conflicts=[X], 레포에 X 없음, base[X] 고정."""
    snapshots = repeat_backup({"X": A}, {}, {"X": ORIG})
    for report, repo, base in snapshots:
        assert report["conflicts"] == ["X"]
        assert "X" not in repo
        assert base["X"] == ORIG
    assert_fixed_point_from_second_round(snapshots)


def test_conflicted_name_freezes_only_its_own_base():
    """전역 게이트를 되살리면 안 되는 이유 — 충돌 하나가 전체 base를 동결하지 않는다."""
    snapshots = repeat_backup({"Z": A, "n": B}, {"Z": B}, {"Z": ORIG})
    for report, _, base in snapshots:
        assert report["conflicts"] == ["Z"]
        assert base["Z"] == ORIG      # 충돌 이름의 base는 고정
        assert base["n"] == B         # 정상 서버의 base는 전진
    assert_fixed_point_from_second_round(snapshots)


def test_case2_remote_added_survives_repeated_backup():
    """타 기기가 추가한 서버가 2회차에도 레포에 남는다 — 옛 설계가 여기서 데이터를 잃었다."""
    snapshots = repeat_backup({"x": A}, {"x": A, "z": B}, {"x": A})
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["z"] == B
        assert report["repo_ahead"] == ["z"]
    assert_fixed_point_from_second_round(snapshots)


def test_case8_remote_change_survives_repeated_backup():
    """타 기기의 변경이 로컬 값으로 되돌아가지 않는다."""
    snapshots = repeat_backup({"x": ORIG}, {"x": B}, {"x": ORIG})
    for report, repo, base in snapshots:
        assert repo["x"] == B
        assert base["x"] == ORIG
        assert report["repo_ahead"] == ["x"]
    assert_fixed_point_from_second_round(snapshots)


def test_new_machine_without_base_does_not_delete_others_on_second_round():
    """base=None으로 시작한 새 기기가 2회차에 남의 서버를 삭제하지 않는다."""
    snapshots = repeat_backup({"mine": A}, {"theirs": B}, None)
    for report, repo, _ in snapshots:
        assert report["deleted"] == []
        assert repo["theirs"] == B
    assert_fixed_point_from_second_round(snapshots)
