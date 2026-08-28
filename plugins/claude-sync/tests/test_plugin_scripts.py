"""세 스크립트(collect_plugins / compare_plugins / plan_plugins)의 계약 테스트.

실제 ~/.claude와 ~/.claude/.sync-state는 절대 건드리지 않는다 —
인프로세스 호출은 경로 인자로, CLI 호출은 env HOME= 으로 격리한다.
"""
import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-backup", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-status", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "sync-restore", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from marks import requires_permission_bits  # noqa: E402
import keyed_sync as ks  # noqa: E402
import plugin_config as pc  # noqa: E402
import collect_plugins  # noqa: E402
import compare_plugins  # noqa: E402
import plan_plugins  # noqa: E402

GH = {"source": {"source": "github", "repo": "june20516/suberpower"}}
DIR_SOURCE = {"source": {"source": "directory", "path": "/x"}}


def drops_a_key(mapping):
    """normalize 계약 위반 — 키 층위 제외는 hold의 몫이다(5.2). 코어가 ValueError를 던진다."""
    return {k: v for k, v in mapping.items() if k != "gone@m"}


def write_settings(tmp_path, **sections):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(sections), encoding="utf-8")
    return str(path)


def write_installed(tmp_path, plugins=None):
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps({"version": 2, "plugins": plugins or {}}), encoding="utf-8")
    return str(path)


def write_repo(tmp_path, sections=None):
    """레포 디렉토리. sections가 None이면 plugins.json이 없다."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    if sections is not None:
        pc.dump_backup(sections, str(repo / pc.BACKUP_RELPATH))
    return str(repo)


def write_base_blob(tmp_path, sections=None):
    base_dir = tmp_path / "base"
    base_dir.mkdir(exist_ok=True)
    if sections is not None:
        pc.dump_backup(sections, str(base_dir / pc.BACKUP_RELPATH))
    return str(base_dir)


def repo_doc(repo):
    return pc.load_backup(os.path.join(repo, pc.BACKUP_RELPATH))


def staged_doc(staging):
    return pc.load_backup(os.path.join(staging, pc.BACKUP_RELPATH))


def staged_text(staging):
    """스테이징 파일의 **원문**. dict 동등성으로는 새 필드에 실린 평문을 보지 못한다."""
    with open(os.path.join(staging, pc.BACKUP_RELPATH), encoding="utf-8") as f:
        return f.read()


def collect(tmp_path, local=None, repo=None, base=None, installed=None, held=None):
    """기본값이 정상 경로다 — 각 테스트는 어긋나게 만들 것 하나만 지정한다."""
    return collect_plugins.collect(
        write_repo(tmp_path, repo),
        str(tmp_path / "staging"),
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path, base),
    )


def test_collect_writes_repo_and_staging_without_touching_base(tmp_path):
    out = collect(tmp_path, local={"enabledPlugins": {"p@m": True}})
    assert out["status"] == "ok"
    repo = write_repo(tmp_path)
    assert repo_doc(repo)["enabledPlugins"] == {"p@m": True}
    assert staged_doc(str(tmp_path / "staging"))["enabledPlugins"] == {"p@m": True}
    assert not os.path.exists(os.path.join(str(tmp_path / "base"), pc.BACKUP_RELPATH))


def test_collect_keeps_other_devices_entries(tmp_path):
    """결함 A — 한 기기의 백업이 다른 기기의 플러그인을 지우지 않는다 (G1).

    레포에 mine@m이 함께 있어야 이 단정이 판별력을 갖는다. 레포에서 빼면 mine@m이
    케이스 4(타 기기 삭제, 로컬 잔존)로 떨어져 **정상 구현에서도** merged에서 빠지고,
    그러면 이 테스트는 결함 A가 아니라 케이스 4를 재는 것이 된다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {"mine@m": True}},
                  repo={"enabledPlugins": {"mine@m": True, "theirs@m": True}},
                  base={"enabledPlugins": {"mine@m": True}})
    assert out["sections"]["enabledPlugins"]["deleted"] == []
    assert sorted(repo_doc(write_repo(tmp_path))["enabledPlugins"]) == ["mine@m", "theirs@m"]


def test_collect_reports_value_change_not_just_key_set(tmp_path):
    """결함 B — true→false가 보고되어야 한다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"p@m": False}},
                  repo={"enabledPlugins": {"p@m": True}},
                  base={"enabledPlugins": {"p@m": True}})
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"p@m": False}


def test_collect_skips_everything_when_settings_is_unreadable(tmp_path):
    """결함 C — 종료 코드 0으로 계속하고, 레포·스테이징 둘 다 손대지 않는다."""
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    with pytest.raises(pc.LocalConfigUnavailable):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=str(tmp_path / "none.json"),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}
    assert not os.path.exists(os.path.join(str(tmp_path / "staging"), pc.BACKUP_RELPATH))


def test_collect_skips_everything_when_enabled_plugins_is_null(tmp_path):
    """14.1 — {"enabledPlugins": null}을 "0개"로 읽으면 레포에서 전멸한다."""
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"enabledPlugins": None}), encoding="utf-8")
    with pytest.raises(pc.LocalConfigUnavailable):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=str(settings),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}


def test_collect_skips_everything_when_the_repo_document_is_unrecognized(tmp_path):
    """14.1 — version: 3을 주장하는 문서를 만나면 레포 파일을 건드리지 않는다.

    "0개"로 읽어 덮어쓰면 상위 버전의 백업이 파괴된다. 조건 3(아는 섹션 없음)과
    조건 4(섹션이 객체가 아님)도 같은 갈래로 떨어진다.
    """
    repo = write_repo(tmp_path)
    repo_file = os.path.join(repo, pc.BACKUP_RELPATH)
    for raw in ('{"version": 3, "enabledPlugins": {}}',
                '{"foo": 1}',
                '{"enabledPlugins": {"p@m": true}, "extraKnownMarketplaces": "손상"}'):
        with open(repo_file, "w", encoding="utf-8") as f:
            f.write(raw)
        with pytest.raises(pc.UnknownBackupSchema):
            collect_plugins.collect(repo, str(tmp_path / "staging"),
                                    settings_path=write_settings(tmp_path),
                                    installed_path=write_installed(tmp_path),
                                    held_path=str(tmp_path / "none-held.json"),
                                    base_dir=write_base_blob(tmp_path))
        with open(repo_file, encoding="utf-8") as f:
            assert f.read() == raw
        assert not os.path.exists(os.path.join(str(tmp_path / "staging"),
                                               pc.BACKUP_RELPATH))


def test_collect_skips_two_sections_when_auto_flags_are_unavailable(tmp_path):
    """3.4 — 판정 불가를 통과로 접으면 되돌릴 수 없는 승격이 타 기기에서 일어난다.

    14.1: 레포가 그대로여야 한다. 마켓플레이스는 auto와 무관하므로 계속 진행한다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {"mine@m": True},
                         "extraKnownMarketplaces": {"m": GH}},
                  repo={"enabledPlugins": {"theirs@m": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["status"] == "ok"
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["extraKnownMarketplaces"]["status"] == "ok"
    doc = repo_doc(write_repo(tmp_path))
    assert doc["enabledPlugins"] == {"theirs@m": True}      # 레포 pass-through (7.5)
    assert doc["extraKnownMarketplaces"] == {"m": GH}


def test_skipped_section_passes_the_previous_base_through(tmp_path):
    """base 쪽 pass-through — 이전 base를 잃으면 다음 회차가 케이스 3을 낸다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"mine@m": True}},
                  base={"enabledPlugins": {"mine@m": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert staged_doc(str(tmp_path / "staging"))["enabledPlugins"] == {"mine@m": True}


def test_collect_skips_only_plugin_configs_when_held_file_is_broken(tmp_path):
    """6.4 — 없음은 정상이고 깨짐은 한 섹션만 skip이다.

    **범위만 재면 절반이다.** 접히지 않은 enabledPlugins도 그 파일의 release를 함께
    잃으므로, 그 섹션이 실제로 판정을 냈는지(내용)와 무엇을 잃었는지(사유)를 함께 잰다 —
    범위만 재던 판에서는 release 손실이 무증상이었다.
    """
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    out = collect(tmp_path, local={"enabledPlugins": {"p@m": True}}, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    plugins = out["sections"]["enabledPlugins"]
    assert plugins["status"] == "ok"
    # 접히지 않았다는 것을 **내용으로** 확인한다 — 병합이 실제로 돌아 레포에 실렸다.
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"p@m": True}
    assert pc.DEGRADED_RELEASE in plugins["degraded_reason"]


def test_auto_failure_reason_is_not_overwritten_by_the_held_failure(tmp_path):
    """두 실패가 겹치면 pluginConfigs의 사유는 **더 넓은 원인**(auto 판정 불가)이다.

    보류 파일 사유로 덮으면 보고에 "보류 파일이 깨졌다"만 남는데, 그 문장은 함께 접힌
    enabledPlugins를 설명하지 못한다 — 사용자는 두 섹션이 왜 빠졌는지 알 수 없다.
    read_hold_inputs의 setdefault가 이 성질을 지킨다.
    """
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    out = collect(tmp_path,
                  local={"enabledPlugins": {"p@m": True}},
                  installed=str(tmp_path / "none-installed.json"),
                  held=str(held))
    auto_reason = out["sections"]["enabledPlugins"]["reason"]
    assert "auto 판정 불가" in auto_reason
    assert out["sections"]["pluginConfigs"]["reason"] == auto_reason


@requires_permission_bits
def test_unreadable_installed_file_is_not_read_as_no_auto(tmp_path):
    """PermissionError를 "auto 없음"으로 접으면 auto 항목이 조용히 승격된다 (N6).

    부재·형식 이상은 AutoFlagsUnavailable(두 섹션 skip)이지만 권한 오류는 그 갈래가
    아니다 — 어댑터의 네 읽기 함수와 같은 규칙으로 전파하고, main()이 전체 skip으로
    접는다. read_hold_inputs가 OSError까지 삼키면 그 구별이 사라진다.
    """
    installed = tmp_path / "installed_plugins.json"
    installed.write_text(json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
    os.chmod(str(installed), 0)
    try:
        with pytest.raises(PermissionError):
            collect_plugins.collect(
                write_repo(tmp_path), str(tmp_path / "staging"),
                settings_path=write_settings(tmp_path),
                installed_path=str(installed),
                held_path=str(tmp_path / "none-held.json"),
                base_dir=write_base_blob(tmp_path))
    finally:
        os.chmod(str(installed), 0o600)


def test_auto_plugin_is_neither_backed_up_nor_deleted(tmp_path):
    """14.1 — H1 위반 + C2형 삭제 전파를 함께 막는다.

    dep@m은 레포에도 base에도 없어야 이 단정이 판별력을 갖는다 —
      * 레포에 있으면 값 보류가 레포 값을 **보존**하므로 정상 구현에서도 merged에 남고,
      * base에만 있으면 케이스 4로 떨어져 H1이 죽어 있어도 merged에서 빠진다.
    둘 다 없을 때만 "H1이 없으면 케이스 1(로컬 신규)로 레포에 실린다"가 성립한다.
    mine@m을 레포에 함께 두는 것은 그것이 케이스 4로 새지 않게 하기 위해서다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {"dep@m": True, "mine@m": True}},
                  repo={"enabledPlugins": {"mine@m": True}},
                  base={"enabledPlugins": {"mine@m": True}},
                  installed=write_installed(tmp_path, {"dep@m": [{"scope": "user",
                                                                  "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    assert section["deleted"] == []
    assert section["held"]["auto"] == ["dep@m"]
    assert sorted(repo_doc(write_repo(tmp_path))["enabledPlugins"]) == ["mine@m"]


def test_auto_plugin_already_in_the_repo_is_preserved_not_dropped(tmp_path):
    """H1의 반쪽 — 이미 레포에 실린 auto 항목은 보류가 **보존**한다(삭제가 아니다).

    값 보류가 "레포에서 뺀다"였다면 이 항목이 타 기기에서 경고 없이 사라진다.
    코어의 값 보류 갈래는 판정표를 타지 않고 레포 값을 그대로 남긴다 —
    "백업하지 않는다"와 "레포에서 지운다"는 다른 연산이다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {"dep@m": True}},
                  repo={"enabledPlugins": {"dep@m": True}},
                  base={"enabledPlugins": {"dep@m": True}},
                  installed=write_installed(tmp_path, {"dep@m": [{"scope": "user",
                                                                  "auto": True}]}))
    assert out["sections"]["enabledPlugins"]["deleted"] == []
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"dep@m": True}


def test_repo_directory_marketplace_entries_are_held_not_deleted(tmp_path):
    """H2의 **레포 쪽** 방어 — 이미 실린 directory 출처 항목을 보류한다.

    이것이 "hold 계산은 레포 읽기보다 뒤"를 실제로 재는 단정이다. build_hooks·
    held_context에 레포를 읽기 전 값을 넘기면 directory_names가 비어 이 보류가 통째로
    죽고, 이 기기에 등록할 소스가 없는 항목이 케이스 3(삭제)으로 레포에서 지워진다.
    H1·H3·H4는 코어가 호출 시점에 레포를 넘기므로 그 뒤집기에서도 살아남는다 —
    그래서 H2 말고는 이 순서를 잡을 수 있는 종류가 없다.
    """
    doc = {"enabledPlugins": {"p@d": True},
           "extraKnownMarketplaces": {"d": DIR_SOURCE}}
    out = collect(tmp_path, local={}, repo=doc, base=doc)
    assert out["sections"]["enabledPlugins"]["deleted"] == []
    assert out["sections"]["extraKnownMarketplaces"]["deleted"] == []
    assert out["sections"]["enabledPlugins"]["held"]["local_marketplace"] == ["p@d"]
    assert out["sections"]["extraKnownMarketplaces"]["held"]["local_marketplace"] == ["d"]
    written = repo_doc(write_repo(tmp_path))
    assert written["enabledPlugins"] == {"p@d": True}
    assert written["extraKnownMarketplaces"] == {"d": DIR_SOURCE}


def test_new_device_without_base_lets_local_win_instead_of_conflicting(tmp_path):
    """이력 없음(None)과 이력이 비었음({})은 다른 사실이다 (불변식 2).

    base가 None이면 삭제 없는 합집합 degrade이고 **양쪽에 있는 키는 로컬 값이 레포를
    덮는다.** {}로 접으면 같은 키가 케이스 9(충돌)로 떨어져 레포 값이 남고, 새 기기의
    첫 백업이 자기 설정을 못 올린 채 충돌만 보고한다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {"p@m": False}},
                  repo={"enabledPlugins": {"p@m": True}})
    assert out["sections"]["enabledPlugins"]["conflicts"] == {"repo_kept": [],
                                                              "repo_absent": []}
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"p@m": False}


def test_declined_config_is_classified_from_the_normalized_repo_value(tmp_path):
    """held_kinds에 넘기는 repo_norm은 **정규화된** 레포 값이어야 한다 (H4).

    H4의 지문은 코어가 마스킹한 레포 값으로 계산된다. 보고 쪽에 원본을 넘기면 평문이
    남아 있는 레포 파일에서 지문이 어긋나 "보류로 판정했는데 종류를 못 찾는" 상태가
    되고, held_kinds가 ValueError를 던져 섹션이 통째로 skipped가 된다 —
    held_context가 막으려는 것과 같은 갈래의 어긋남이다.
    """
    plain = {"options": {"k": "plain"}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"]({"p@m": plain})["p@m"]
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({"pluginConfigs": {"p@m": pc.value_fingerprint(masked)}}),
                    encoding="utf-8")
    out = collect(tmp_path,
                  local={"pluginConfigs": {"p@m": plain}},
                  repo={"pluginConfigs": {"p@m": plain}},
                  held=str(held))
    section = out["sections"]["pluginConfigs"]
    assert section["status"] == "ok"
    assert section["held"]["declined"] == ["p@m"]


def test_repo_extended_value_survives_when_local_lacks_the_key(tmp_path):
    """14.1의 첫 줄 — 출발점이 "로컬에 키가 없다"여야 복원 구간 파괴를 잡는다 (H3)."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {}},
                  repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {"p@m": ["1.0.0"]}
    assert out["sections"]["enabledPlugins"]["held"]["extended_value"] == ["p@m"]


def test_extended_value_key_is_removed_from_next_base(tmp_path):
    """5.3 — 값 보류 키의 base를 남기면 해제되는 순간 케이스 3이 난다."""
    collect(tmp_path,
            local={"enabledPlugins": {"p@m": True}},
            repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
            base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in staged_doc(str(tmp_path / "staging"))["enabledPlugins"]


def test_plugin_config_secrets_never_reach_the_repo_file(tmp_path):
    """14.1 — 비밀 유출."""
    collect(tmp_path, local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}})
    with open(os.path.join(write_repo(tmp_path), pc.BACKUP_RELPATH), encoding="utf-8") as f:
        raw = f.read()
    assert "sk-real" not in raw
    assert pc.SENTINEL in raw


def test_absent_base_section_does_not_delete_anything(tmp_path):
    """14.1 — base에 pluginConfigs가 없으면 어떤 항목도 deleted로 판정되지 않는다.

    부재 섹션은 "이력이 비어 있었다"({})이므로 in_s가 거짓이고 케이스 3이 성립하지
    않는다. 레포에만 있는 항목은 케이스 2(타 기기 추가)로 보존된다.
    """
    out = collect(tmp_path,
                  local={"pluginConfigs": {}},
                  repo={"pluginConfigs": {"p@m": {"options": {"k": pc.SENTINEL}}}},
                  base={"enabledPlugins": {}})
    assert out["sections"]["pluginConfigs"]["deleted"] == []
    assert "p@m" in repo_doc(write_repo(tmp_path))["pluginConfigs"]


def test_second_backup_of_an_empty_device_is_not_skipped(tmp_path):
    """14.1 — 빈 섹션을 생략하면 다음 백업의 인식 규칙에 걸려 영구 skip된다 (4.3)."""
    first = collect(tmp_path, local={})
    assert first["status"] == "ok"
    repo = write_repo(tmp_path)
    second = collect_plugins.collect(
        repo, str(tmp_path / "staging2"),
        settings_path=write_settings(tmp_path),
        installed_path=write_installed(tmp_path),
        held_path=str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path))
    assert second["status"] == "ok"


def test_collect_splits_the_decision_table_into_report_buckets(tmp_path):
    """판정표 여섯 케이스를 한 fixture에 심어 보고 배선을 통째로 잠근다.

    SKILL.md는 이 네 필드만 보고 안내 문구를 고르므로, 배선이 어긋나면 판정 자체는
    옳은데 **사용자가 정반대의 처방을 받는다** — 케이스 9(레포 값이 남았다)와
    케이스 5(아예 빠졌다), 케이스 8(값을 고르라)과 케이스 2(restore가 설치한다)가
    각각 뒤바뀐다. deleted·local_stale은 그 사실이 사용자에게 도달하는 **유일한 통로**라
    비면 백업이 레포에서 항목을 지운 것이 어디에도 나오지 않는다.
    레포 값을 전부 불리언으로 두는 것은 H3(비불리언 레포 값 보류)를 피해 이 여섯이
    판정표를 타게 하기 위해서다.
    """
    out = collect(
        tmp_path,
        local={"enabledPlugins": {"c9@m": False, "c5@m": True,
                                  "c8@m": False, "c4@m": True}},
        repo={"enabledPlugins": {"c9@m": True, "c2@m": True,
                                 "c8@m": True, "c3@m": True}},
        base={"enabledPlugins": {"c9@m": {"v": 1}, "c5@m": False, "c8@m": False,
                                 "c3@m": True, "c4@m": True}})
    section = out["sections"]["enabledPlugins"]
    assert section["conflicts"] == {"repo_kept": ["c9@m"], "repo_absent": ["c5@m"]}
    assert section["repo_ahead"] == {"present": ["c8@m"], "absent": ["c2@m"]}
    assert section["deleted"] == ["c3@m"]
    assert section["local_stale"] == ["c4@m"]
    assert repo_doc(write_repo(tmp_path))["enabledPlugins"] == {
        "c9@m": True, "c2@m": True, "c8@m": True}


def test_collect_reports_base_staging_failure_without_claiming_skip(tmp_path,
                                                                    monkeypatch):
    """rename만 실패하면 레포는 **이미 갱신돼 있다** — status는 ok이고 사유는 별도 키다.

    사유를 reason에 담으면 SKILL.md의 skipped 분기가 그 키 하나로 갈리므로, 레포를
    고쳐 놓고 사용자에게 "레포 파일은 손대지 않았다"를 보여 준다. 갈래를 통째로 지우면
    실패가 아무 데도 보고되지 않는다. 스테이징 최종 파일이 없어야 base 갱신 게이트가
    막혀 base가 전진하지 않는다.
    """
    repo = write_repo(tmp_path)
    staging = str(tmp_path / "staging")
    staged = os.path.join(staging, pc.BACKUP_RELPATH)
    real_replace = os.replace

    def fail_on_rename(src, dst):
        # 레포 파일도 basename이 같으므로 endswith가 아니라 staged 경로를 정확히 맞춘다 —
        # 아니면 레포 쓰기가 먼저 걸려 collect가 try/except에 닿기도 전에 죽는다.
        if str(dst) == staged:
            raise OSError("rename failed")
        return real_replace(src, dst)

    monkeypatch.setattr(collect_plugins.os, "replace", fail_on_rename)
    out = collect_plugins.collect(
        repo, staging,
        settings_path=write_settings(tmp_path, enabledPlugins={"mine@m": True}),
        installed_path=write_installed(tmp_path),
        held_path=str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path))
    assert out["status"] == "ok"
    assert out["base_staging"] == "failed"
    assert "reason" not in out
    assert "다음 백업이 복구한다" in out["base_staging_reason"]
    assert repo_doc(repo)["enabledPlugins"] == {"mine@m": True}
    assert not os.path.exists(staged)


def test_orphaned_is_computed_from_the_merged_document_not_the_local_one(tmp_path):
    """7.6 — 고아 판정의 대상은 **레포에 실릴 문서**다.

    섹션이 skip된 실행에서 둘이 갈린다: 로컬에는 없고 레포에만 있는 고아가 그대로
    남는데, 로컬에서 계산하면 그것이 보고에서 사라진다.
    """
    out = collect(tmp_path,
                  local={"enabledPlugins": {}},
                  repo={"enabledPlugins": {"alpha@bar": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert out["orphaned"] == ["alpha@bar"]


def test_collect_cli_rejects_wrong_argument_count():
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다.

    데이터 문제의 skip(종료 코드 0)과 배선 실수(1)를 가르는 유일한 신호다 —
    0으로 접으면 SKILL.md가 인자를 잘못 넘겨도 성공으로 보인다.
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills",
                          "sync-backup", "scripts", "collect_plugins.py")
    proc = subprocess.run([sys.executable, os.path.abspath(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 1


def test_collect_reports_orphaned_without_blocking(tmp_path):
    """7.6 — 차단하지 않는다. 최상위 orphaned로 보고만 한다."""
    out = collect(tmp_path,
                  local={"enabledPlugins": {"alpha@bar": True}},
                  repo={"extraKnownMarketplaces": {}})
    assert out["status"] == "ok"
    assert out["orphaned"] == ["alpha@bar"]


def test_collect_does_not_stage_when_repo_write_fails(tmp_path, monkeypatch):
    """레포 쓰기가 실패하면 스테이징 최종 파일이 남지 않아야 base가 전진하지 않는다."""
    repo = write_repo(tmp_path)
    real_dump = pc.dump_backup

    def fail_on_repo(sections, path):
        if os.path.dirname(path).endswith("repo"):
            raise OSError("disk full")
        return real_dump(sections, path)

    monkeypatch.setattr(collect_plugins.pc, "dump_backup", fail_on_repo)
    with pytest.raises(OSError):
        collect_plugins.collect(repo, str(tmp_path / "staging"),
                                settings_path=write_settings(tmp_path),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"),
                                base_dir=write_base_blob(tmp_path))
    assert not os.path.exists(os.path.join(str(tmp_path / "staging"), pc.BACKUP_RELPATH))


def test_repo_is_untouched_when_the_staging_write_fails(tmp_path, monkeypatch):
    """스테이징(.tmp)이 레포보다 **먼저**여야 한다.

    순서를 맞바꾸면 .tmp 쓰기 실패가 레포를 이미 고친 뒤에 일어나고, 그 OSError가
    부르는 skipped의 표준 문구("레포 파일은 손대지 않았다")가 거짓이 된다.
    로컬 항목을 하나 두는 것은 병합 결과가 레포 원본과 **달라야** 이 단정이 판별력을
    갖기 때문이다 — 같으면 레포를 다시 써도 내용이 그대로라 아무것도 재지 못한다.
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    real_dump = pc.dump_backup

    def fail_on_staging(sections, path):
        if os.path.basename(path).endswith(".tmp"):
            raise OSError("disk full")
        return real_dump(sections, path)

    monkeypatch.setattr(collect_plugins.pc, "dump_backup", fail_on_staging)
    with pytest.raises(OSError):
        collect_plugins.collect(
            repo, str(tmp_path / "staging"),
            settings_path=write_settings(tmp_path,
                                         enabledPlugins={"mine@m": True}),
            installed_path=write_installed(tmp_path),
            held_path=str(tmp_path / "none-held.json"),
            base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}


def test_collect_builds_the_report_before_touching_the_repo(tmp_path, monkeypatch):
    """보고 생성이 실패하면 레포가 이미 바뀐 뒤여서는 안 된다.

    held_kinds는 분류할 수 없는 보류 키에 ValueError를 던진다. 그 예외는 섹션을
    skipped로 접는데, 레포를 먼저 고쳤다면 "레포 파일은 손대지 않았다"가 거짓이 된다.
    로컬 항목을 하나 두어 병합 결과가 레포 원본과 다르게 만든다 — 같으면 레포를 먼저
    써도 내용이 그대로라 이 단정이 공허해진다(실측으로 변조가 살아남았다).
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})

    def boom(*args, **kwargs):
        raise ValueError("분류 불가")

    monkeypatch.setattr(collect_plugins.pc, "held_kinds", boom)
    with pytest.raises(ValueError):
        collect_plugins.collect(
            repo, str(tmp_path / "staging"),
            settings_path=write_settings(tmp_path,
                                         enabledPlugins={"mine@m": True}),
            installed_path=write_installed(tmp_path),
            held_path=str(tmp_path / "none-held.json"),
            base_dir=write_base_blob(tmp_path))
    assert repo_doc(repo)["enabledPlugins"] == {"theirs@m": True}


def test_collect_exits_zero_and_reports_skip_from_the_cli(tmp_path):
    """10.3 — 종료 코드는 0이다. 그래야 안내가 보인다."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills",
                          "sync-backup", "scripts", "collect_plugins.py")
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    proc = subprocess.run([sys.executable, script, write_repo(tmp_path),
                           str(tmp_path / "staging")],
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_collect_cli_skips_when_normalize_drops_a_key(tmp_path, monkeypatch, capsys):
    """normalize 계약 위반(ValueError)도 traceback이 아니라 skipped로 접힌다.

    main()의 except 튜플에서 ValueError가 빠지면 어댑터 훅의 결함 하나가 backup 흐름
    전체를 세운다 — 이 프로젝트가 이미 고친 결함 C의 회귀다. 위의 종료 코드 테스트는
    이 갈래를 재지 못한다(거기서 도달하는 것은 LocalConfigUnavailable뿐이다).
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"gone@m": True}})
    monkeypatch.setitem(pc.SECTION_NORMALIZE, "enabledPlugins", drops_a_key)
    monkeypatch.setattr(pc, "DEFAULT_SETTINGS",
                        write_settings(tmp_path, enabledPlugins={"gone@m": True}))
    monkeypatch.setattr(pc, "DEFAULT_INSTALLED", write_installed(tmp_path))
    monkeypatch.setattr(pc, "DEFAULT_HELD", str(tmp_path / "none-held.json"))
    # 실제 ~/.claude/.sync-state를 읽지 않게 한다. base 이력은 이 회귀와 무관하다.
    monkeypatch.setattr(collect_plugins.ss, "read_base", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv",
                        ["collect_plugins.py", repo, str(tmp_path / "staging")])
    collect_plugins.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped"
    assert out["reason"]
    assert repo_doc(repo)["enabledPlugins"] == {"gone@m": True}


# --------------------------------------------------------------- compare_plugins

def compare(tmp_path, local=None, repo=None, installed=None, held=None):
    """기본값이 정상 경로다. 레포는 항상 파일이 있는 상태로 둔다(부재는 별도 갈래다)."""
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    return compare_plugins.compare(
        os.path.join(repo_dir, pc.BACKUP_RELPATH),
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "none-held.json"))


def compare_script():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                        "skills", "sync-status", "scripts",
                                        "compare_plugins.py"))


def test_compare_reports_value_changes_not_just_key_sets(tmp_path):
    """결함 B — check_status.py의 키 집합 비교는 켬/끔 변경을 못 봤다."""
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": False}},
                  repo={"enabledPlugins": {"p@m": True}})
    section = out["sections"]["enabledPlugins"]
    assert section["changed"] == ["p@m"]
    assert section["only_local"] == [] and section["only_repo"] == []


def test_compare_converges_masked_secrets_to_in_sync(tmp_path):
    """로컬 평문과 레포 마스킹을 원본끼리 비교하면 영구히 "변경됨"이 된다."""
    out = compare(tmp_path,
                  local={"pluginConfigs": {"p@m": {"options": {"k": "sk-real"}}}},
                  repo={"pluginConfigs": {"p@m": {"options": {"k": pc.SENTINEL}}}})
    assert out["sections"]["pluginConfigs"]["changed"] == []


def test_compare_keeps_held_keys_out_of_the_three_buckets(tmp_path):
    """9.2 — "backup 시 추가"는 거짓이고 사용자가 해소할 수도 없다."""
    out = compare(tmp_path, local={"enabledPlugins": {"dep@m": True}},
                  installed=write_installed(tmp_path,
                                            {"dep@m": [{"scope": "user", "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    assert section["only_local"] == []
    assert section["held"]["auto"] == ["dep@m"]


def test_compare_stays_silent_after_the_user_declined_a_config(tmp_path):
    """6.5 — base를 읽지 않고도 보류를 알아야 status가 조용해진다."""
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({
        "version": 1,
        "pluginConfigs": {"delta@m": pc.value_fingerprint(masked["delta@m"])},
        "release": {"enabledPlugins": []}}), encoding="utf-8")
    out = compare(tmp_path, local={}, repo=repo, held=str(held))
    section = out["sections"]["pluginConfigs"]
    assert section["only_repo"] == []
    assert section["held"]["declined"] == ["delta@m"]


def test_compare_reports_again_when_the_repo_value_changes(tmp_path):
    """지문이 달라지면 자동으로 해제된다 — 6.4가 약속한 동작이다."""
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({"pluginConfigs": {"delta@m": "0" * 64},
                                "release": {"enabledPlugins": []}}), encoding="utf-8")
    out = compare(tmp_path, local={},
                  repo={"pluginConfigs": {"delta@m": {"options": {"apiKey": pc.SENTINEL}}}},
                  held=str(held))
    assert out["sections"]["pluginConfigs"]["only_repo"] == ["delta@m"]


def test_compare_classifies_declined_configs_from_the_normalized_repo_value(tmp_path):
    """held_kinds에 넘기는 repo_norm은 **정규화된** 레포 값이어야 한다 (H4).

    H4의 지문은 코어가 마스킹한 레포 값으로 계산된다. 보고 쪽에 원본을 넘기면 평문이
    남아 있는 레포 파일에서 지문이 어긋나 "보류로 판정했는데 종류를 못 찾는" 상태가 되고,
    held_kinds가 ValueError를 던져 섹션이 통째로 skipped가 된다. 위의 declined 테스트는
    레포 값이 이미 마스킹돼 있어 이 어긋남을 재지 못한다(정규화가 멱등이라 결과가 같다).
    """
    plain = {"options": {"k": "plain"}}
    masked = pc.SECTION_NORMALIZE["pluginConfigs"]({"p@m": plain})["p@m"]
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({"pluginConfigs": {"p@m": pc.value_fingerprint(masked)}}),
                    encoding="utf-8")
    out = compare(tmp_path, local={"pluginConfigs": {"p@m": plain}},
                  repo={"pluginConfigs": {"p@m": plain}}, held=str(held))
    section = out["sections"]["pluginConfigs"]
    assert section["status"] == "ok"
    assert section["held"]["declined"] == ["p@m"]
    assert section["changed"] == [] and section["only_local"] == []


def test_compare_marks_unrestorable_repo_only_entries(tmp_path):
    """9.2 — "restore 시 설치"가 아니라 "이 기기에서는 복원할 수 없습니다"로 말해야 한다."""
    out = compare(tmp_path, local={}, repo={"enabledPlugins": {"p@nowhere": True}})
    assert out["sections"]["enabledPlugins"]["unrestorable"] == ["p@nowhere"]


def test_compare_leaves_restorable_repo_only_entries_out_of_unrestorable(tmp_path):
    """복원 가능한 항목까지 unrestorable로 접으면 사용자에게 되돌릴 수단이 없다 (8.1).

    restorable에 넘기는 값이 **그 섹션의 레포 값**이어야 이 단정이 성립한다. 문서 전체나
    로컬 매핑을 넘기면 마켓플레이스 쪽에서 marketplace_arg가 None을 돌려주어 정상 항목이
    전부 unrestorable이 된다 — enabledPlugins는 값을 보지 않으므로 무증상이다.
    """
    out = compare(tmp_path, local={},
                  repo={"enabledPlugins": {"p@m": True},
                        "extraKnownMarketplaces": {"m": GH}})
    plugins = out["sections"]["enabledPlugins"]
    markets = out["sections"]["extraKnownMarketplaces"]
    assert plugins["only_repo"] == ["p@m"] and plugins["unrestorable"] == []
    assert markets["only_repo"] == ["m"] and markets["unrestorable"] == []


def test_compare_distinguishes_installed_extended_values(tmp_path):
    """9.2·8.4 — H3는 행동 보류가 아니므로 "설치됨"과 "미설치"를 문구가 갈라야 한다."""
    installed = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert installed["sections"]["enabledPlugins"]["held"]["extended_value"] == ["p@m"]
    assert installed["sections"]["enabledPlugins"]["absent_locally"] == []
    missing = compare(tmp_path, local={}, repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert missing["sections"]["enabledPlugins"]["absent_locally"] == ["p@m"]


def test_absent_locally_is_not_a_claim_that_the_plugin_is_not_installed(tmp_path):
    """이름이 뜻하는 것은 "로컬 섹션 문서에 값이 없다"이지 "미설치"가 아니다.

    installed_plugins.json에 있다는 것 자체가 이 기기에 설치되어 있다는 뜻이다(3.4).
    아래가 그 반례다 — dep@m은 **설치되어 있으면서** settings.json에는 없다. 이 조합에
    "미설치"라는 이름을 붙이면 보고가 실측으로 거짓이 된다.

    설치 여부는 **not_installed가 따로 말한다**(9.2). 두 필드가 같은 fixture에서 서로
    다른 답을 내는 것이 이 이름을 유지한 이유다.
    """
    out = compare(tmp_path, local={}, repo={"enabledPlugins": {"dep@m": True}},
                  installed=write_installed(tmp_path,
                                            {"dep@m": [{"scope": "user", "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    assert section["status"] == "ok"
    # 설치되어 있다 — auto로 분류된 근거가 installed_plugins.json에 있다는 사실이다.
    assert section["held"]["auto"] == ["dep@m"]
    # 그런데도 여기 들어온다 — "레포 값을 보존합니다"가 거짓이 되는 조건이 이것이다.
    assert section["absent_locally"] == ["dep@m"]
    # Task 8이 이름을 바꾼 계기가 된 조합이다. 여기 들어가면 보고가 거짓이 된다.
    assert section["not_installed"] == []


def test_compare_splits_absent_locally_by_actual_installation(tmp_path):
    """9.2 — H3 항목은 "설치됨"과 "미설치"를 구별해 말한다.

    dep@m은 **설치되어 있으면서** settings.json에 없다(auto 의존성). ghost@m은 어디에도
    없다. 한 fixture에서 두 갈래가 **둘 다 비지 않아야** 이 배선이 "absent_locally를
    그대로 복사한 것"이나 하드코딩과 구별된다.

    absent_locally는 그대로 둔다 — "레포 값을 보존합니다"가 거짓이 되는 조건은 설치
    여부와 별개의 사실이고 spec 8.4가 그것을 요구한다.

    stale@m은 이 필드가 **absent_locally의 부분집합**임을 못박는다 — 로컬 문서에 값이
    있으면서 설치되지 않은 상태다. CLI는 그런 상태를 만들지 않는다(9.3.3: uninstall이
    키를 지운다). 보류 키 전체에서 뽑으면 이 키가 들어와, 문구가 값 차이를 말해야 할
    항목(8.4의 셋째 행)까지 "미설치"로 보고된다.
    """
    out = compare(tmp_path, local={"enabledPlugins": {"stale@m": True}},
                  repo={"enabledPlugins": {"dep@m": True, "ghost@m": ["1.0.0"],
                                           "stale@m": ["2.0.0"]}},
                  installed=write_installed(
                      tmp_path, {"dep@m": [{"scope": "user", "auto": True}]}))
    section = out["sections"]["enabledPlugins"]
    # 세 키가 전부 보류다 — 하나라도 빠지면 아래 두 목록이 저절로 좁아진다.
    assert section["held"] == {"auto": ["dep@m"], "local_marketplace": [],
                               "extended_value": ["ghost@m", "stale@m"]}
    assert section["absent_locally"] == ["dep@m", "ghost@m"]
    assert section["not_installed"] == ["ghost@m"]


def test_compare_splits_plugin_configs_by_installation_too(tmp_path):
    """설치 구별은 **두 섹션 모두**에 실린다 — 위의 enabledPlugins만 재면 절반이 미측정이다.

    INSTALL_KEYED_SECTIONS를 enabledPlugins 하나로 좁히는 회귀는 그 섹션을 재는 단정에
    걸리지 않는다 — 거기서는 필드가 그대로 남기 때문이다. 좁히면 pluginConfigs의
    "미설치" 문구가 통째로 사라지고, read_hold_inputs가 installed_ids를 접어도 되는
    근거("그 값을 읽는 자리가 전부 함께 접힌 **두** 섹션 안에 있다")의 절반이 검증되지
    않은 채 남는다.

    here@d는 **설치돼 있으면서 auto가 아니다.** auto 집합과 설치 집합이 같은 fixture에서는
    이 필드를 auto 집합으로 판정하는 회귀가 무증상이라, 그 변조가 compare 쪽에서 오래
    미측정으로 남아 있었다(Task 10.5 quality review Q9). 실제 증상은 수동 설치한
    플러그인을 전부 "미설치"로 보고하는 것이다.

    보류는 H2(레포의 directory 마켓플레이스)로 만든다. 다섯 키가 전부 보류여야 아래 두
    목록이 저절로 좁아진 것과 구별된다.

    **not_installed을 원소 넷으로 두는 것은 순서를 재기 위해서다** — 이 목록을 집합
    순회로 만드는 회귀는 정렬 순서를 깬다. 다만 그 가드는 **확률적이다**: 집합 순회
    순서가 우연히 정렬 순서와 같으면 통과한다(실측 — 원소 셋에서 PYTHONHASHSEED에 따라
    통과하는 시드가 있었다). 원소를 늘리는 것이 그 확률을 낮추는 유일한 수단이다.
    """
    out = compare(tmp_path, local={},
                  repo={"extraKnownMarketplaces": {"d": DIR_SOURCE},
                        "pluginConfigs": {"here@d": {"options": {}},
                                          "gone@d": {"options": {}},
                                          "also@d": {"options": {}},
                                          "mid@d": {"options": {}},
                                          "zap@d": {"options": {}},
                                          "brio@d": {"options": {}},
                                          "quix@d": {"options": {}}}},
                  installed=write_installed(tmp_path, {"here@d": [{"scope": "user"}]}))
    section = out["sections"]["pluginConfigs"]
    expected = ["also@d", "brio@d", "gone@d", "here@d", "mid@d", "quix@d", "zap@d"]
    assert section["status"] == "ok"
    assert section["held"] == {"auto": [], "declined": [],
                               "local_marketplace": expected}
    assert section["absent_locally"] == expected
    # here@d만 빠진다 — 설치돼 있기 때문이다(auto는 아니다).
    assert section["not_installed"] == [k for k in expected if k != "here@d"]


def test_compare_does_not_call_a_marketplace_uninstalled(tmp_path):
    """설치 구별은 **키가 플러그인 id인 두 섹션에만** 싣는다.

    extraKnownMarketplaces의 키는 마켓플레이스 이름이라 installed_ids와 이름 공간이
    다르다 — 실으면 등록만 안 된 마켓플레이스가 전부 "미설치 플러그인"으로 보고된다.
    같은 실행의 enabledPlugins가 그 필드를 **갖는** 것을 함께 재어, 필드가 어디에도
    없는 회귀와 구별한다.
    """
    doc = {"enabledPlugins": {"p@d": True}, "extraKnownMarketplaces": {"d": DIR_SOURCE}}
    out = compare(tmp_path, local={}, repo=doc)
    markets = out["sections"]["extraKnownMarketplaces"]
    # 비지 않았다 — 실을 값이 있었는데도 싣지 않은 것이다.
    assert markets["absent_locally"] == ["d"]
    assert "not_installed" not in markets
    assert out["sections"]["enabledPlugins"]["not_installed"] == ["p@d"]


def test_compare_does_not_claim_everything_is_uninstalled_when_a_section_is_skipped(
        tmp_path):
    """설치 집합을 못 읽었는데 "전부 미설치"로 접히면 restore가 전부 재설치를 시도한다.

    같은 fixture를 정상 installed 파일로 한 번 더 돌려 not_installed가 **비지 않게**
    나오는 것을 함께 잰다 — 없으면 "필드가 없다"가 설치 판정과 무관하게 참이 된다.
    """
    repo = {"enabledPlugins": {"ghost@m": ["1.0.0"]}}
    ok = compare(tmp_path, local={}, repo=repo)
    assert ok["sections"]["enabledPlugins"]["not_installed"] == ["ghost@m"]
    out = compare(tmp_path, local={}, repo=repo,
                  installed=str(tmp_path / "missing.json"))
    section = out["sections"]["enabledPlugins"]
    assert section == pc.skipped_section(section["reason"])
    assert "not_installed" not in section


def test_compare_splits_the_three_buckets_without_swapping_them(tmp_path):
    """네 갈래를 한 fixture에 심어 보고 배선을 잠근다.

    버킷이 맞바뀌면 판정은 옳은데 사용자가 정반대의 처방을 받는다 — only_local("backup
    시 레포에 추가")과 only_repo("restore 시 이 기기에 추가")는 방향이 반대다. 각 버킷에
    **비지 않은 값**이 나오는 것이 하드코딩과 구별하는 유일한 방법이다.
    레포 값을 불리언으로 두는 것은 H3(비불리언 레포 값 보류)를 피해 네 키가 전부
    판정표를 타게 하기 위해서다.
    """
    out = compare(tmp_path,
                  local={"enabledPlugins": {"mine@m": True, "both@m": True,
                                            "same@m": True}},
                  repo={"enabledPlugins": {"theirs@m": True, "both@m": False,
                                           "same@m": True}})
    section = out["sections"]["enabledPlugins"]
    assert section["only_local"] == ["mine@m"]
    assert section["only_repo"] == ["theirs@m"]
    assert section["changed"] == ["both@m"]
    assert section["unrestorable"] == ["theirs@m"]      # 레포에 'm'의 소스가 없다
    assert section["absent_locally"] == []
    assert section["held"] == {"auto": [], "local_marketplace": [],
                               "extended_value": []}


def test_compare_reports_directory_marketplace_holds_by_kind(tmp_path):
    """H2 — 이 기기에 등록할 소스가 없는 항목은 보류이고, 종류가 local_marketplace다.

    이 종류에 비지 않은 값이 나오는 fixture가 없으면 held의 배선이 하드코딩과
    구별되지 않는다. 두 섹션이 **각각** 자기 종류로 분류되는지도 함께 잠근다.
    """
    doc = {"enabledPlugins": {"p@d": True},
           "extraKnownMarketplaces": {"d": DIR_SOURCE}}
    out = compare(tmp_path, local={}, repo=doc)
    plugins = out["sections"]["enabledPlugins"]
    markets = out["sections"]["extraKnownMarketplaces"]
    assert plugins["held"]["local_marketplace"] == ["p@d"]
    assert markets["held"]["local_marketplace"] == ["d"]
    assert plugins["only_repo"] == [] and markets["only_repo"] == []
    # 보류 키 중 로컬에 없는 것 — "레포 값을 보존합니다"만 말하면 거짓이 되는 항목이다.
    assert plugins["absent_locally"] == ["p@d"]
    assert markets["absent_locally"] == ["d"]


def test_compare_never_reads_or_writes_base(tmp_path, monkeypatch):
    """읽기 전용 스킬이다 — base를 읽으면 status와 backup의 판정이 갈린다."""
    def boom(*args, **kwargs):
        raise AssertionError("compare_plugins가 base를 읽었다")

    monkeypatch.setattr(compare_plugins.pc, "parse_base", boom)
    assert compare(tmp_path, local={"enabledPlugins": {"p@m": True}})["status"] == "ok"


def test_compare_does_not_reach_the_base_history_at_all():
    """위 테스트는 pc.parse_base 경로만 막는다 — 이력 모듈 자체를 들이지 않는 것이 성질이다.

    sync_state를 import하면 read_base의 바이트를 직접 파싱하는 우회가 한 줄로 가능해지고,
    그러면 읽기 전용이라는 이 스크립트의 계약이 monkeypatch로 확인되지 않는다.

    **import 문만 본다.** 단순 부분 문자열 검사는 주석·docstring이 그 모듈명을 언급하기만
    해도 실패해서, "왜 base를 읽지 않는가"를 적는 것 자체가 무관한 실패를 낳는다.
    ^import로만 좁히지 않는 것은 함수 본문 안의 **들여쓴** import를 놓치기 때문이다.
    """
    with open(compare_plugins.__file__, encoding="utf-8") as f:
        src = f.read()
    assert re.search(r"^\s*(import|from)\s+sync_state\b", src, re.M) is None


def test_compare_skips_sections_the_same_way_backup_does(tmp_path):
    """스킬마다 다른 범위로 접으면 사용자가 두 명령에서 다른 상태를 본다.

    **최상위 status는 섹션 skip을 반영하지 않는다.** 반영하게 만들면 세 섹션 중 둘만
    접힌 이 실행이 통째로 "플러그인 비교 건너뜀"으로 읽혀, 멀쩡히 계산된
    extraKnownMarketplaces 비교가 사용자에게 도달하지 않는다. collect 쪽 대칭 단정은
    test_collect_skips_two_sections_when_auto_flags_are_unavailable에 있다 — 한쪽만
    잠가 두면 같은 규칙을 공유한다는 말이 한쪽에서만 참이 된다.
    """
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                  installed=str(tmp_path / "none-installed.json"))
    assert out["status"] == "ok"
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["extraKnownMarketplaces"]["status"] == "ok"
    assert "auto 판정 불가" in out["sections"]["enabledPlugins"]["reason"]
    # 세 스크립트가 **같은 키**로 skip을 보고해야 SKILL.md가 같은 코드로 읽는다.
    assert out["sections"]["enabledPlugins"] == pc.skipped_section(
        out["sections"]["enabledPlugins"]["reason"])


def test_compare_skips_only_plugin_configs_when_the_held_file_is_broken(tmp_path):
    """6.4 — 없음은 정상이고 깨짐은 한 섹션만 skip이다.

    collect 쪽과 같은 이유로 **내용과 사유를 함께 잰다**(범위만 재면 절반이다).
    """
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}}, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["pluginConfigs"]["reason"]
    plugins = out["sections"]["enabledPlugins"]
    assert plugins["status"] == "ok"
    assert plugins["only_local"] == ["p@m"]        # 비교가 실제로 수행됐다
    assert pc.DEGRADED_RELEASE in plugins["degraded_reason"]
    # 접힌 섹션의 사유와 **같은 사건**을 가리킨다.
    assert str(held) in plugins["degraded_reason"]


@pytest.mark.parametrize("runner", ["collect", "compare"])
def test_a_broken_held_file_reholds_released_keys_and_says_why(tmp_path, runner):
    """**접히지 않는 섹션이 조용히 되돌아가는 것을 막는다.**

    보류 파일에는 H3의 탈출구(`release`)가 들어 있는데 그 파일을 읽지 못하면
    `EMPTY_HELD`로 접힌다. 그런데 release를 읽는 자리(build_hooks → H3)는 **접히지 않는**
    enabledPlugins에 있어, 이미 해제한 확장 값 항목이 그 실행에서 다시 보류된다 —
    push되어야 할 로컬 값이 push되지 않고 base에서도 그 키가 빠진다(실측).

    방향은 보수적이라 값이 파괴되지는 않지만, **왜 그렇게 됐는지**가 pluginConfigs의
    reason에만 붙어 이 섹션에서는 읽을 수 없었다. 정상 held와 깨진 held를 나란히 재어
    ⑴ 판정이 실제로 뒤집히고 ⑵ 그 사유가 이 섹션에 실리는 것을 함께 건다.
    """
    run = {"collect": collect, "compare": compare}[runner]
    fixture = dict(local={"enabledPlugins": {"foo@m": True}},
                   repo={"enabledPlugins": {"foo@m": {"version": "1.0"}},
                         "extraKnownMarketplaces": {"m": GH}})
    good = tmp_path / "plugins-held.json"
    good.write_text(json.dumps({"version": 1, "pluginConfigs": {},
                                "release": {"enabledPlugins": ["foo@m"]}}),
                    encoding="utf-8")
    released = run(tmp_path, held=str(good), **fixture)["sections"]["enabledPlugins"]
    assert released["held"]["extended_value"] == []       # 탈출구가 살아 있다
    assert "degraded_reason" not in released

    broken = tmp_path / "broken-held.json"
    broken.write_text("{not json", encoding="utf-8")
    reheld = run(tmp_path, held=str(broken), **fixture)["sections"]["enabledPlugins"]
    assert reheld["status"] == "ok"
    assert reheld["held"]["extended_value"] == ["foo@m"]   # 해제가 되돌아갔다
    assert pc.DEGRADED_RELEASE in reheld["degraded_reason"]


@pytest.mark.parametrize("broken", ["installed", "held"])
def test_compare_and_collect_fold_the_same_sections(tmp_path, broken):
    """두 스킬의 skip 범위가 갈리면 사용자가 같은 기기에서 다른 상태를 본다.

    범위는 read_hold_inputs 하나가 정한다 — 스크립트가 각자 접으면 backup은 두 섹션을
    접는데 status는 안 접는 비대칭이 생기고, 예외 종류가 같아 보여 흔적을 남기지 않는다.
    """
    def folded(out):
        return sorted(k for k, v in out["sections"].items() if v["status"] == "skipped")

    if broken == "installed":
        kwargs = {"installed": str(tmp_path / "none-installed.json")}
    else:
        held = tmp_path / "plugins-held.json"
        held.write_text("{not json", encoding="utf-8")
        kwargs = {"held": str(held)}
    kwargs["local"] = {"enabledPlugins": {"p@m": True}}
    from_status = folded(compare(tmp_path, **kwargs))
    assert from_status == folded(collect(tmp_path, **kwargs))
    assert from_status != []


def test_compare_cli_rejects_wrong_argument_count():
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다."""
    proc = subprocess.run([sys.executable, compare_script()],
                          capture_output=True, text=True)
    assert proc.returncode == 1


def test_compare_cli_exits_zero_and_reports_skip(tmp_path):
    """10.3 — 종료 코드는 0이다. 그래야 안내가 보인다."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    proc = subprocess.run(
        [sys.executable, compare_script(), os.path.join(repo, pc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"


def test_compare_cli_skips_when_normalize_drops_a_key(tmp_path, monkeypatch, capsys):
    """normalize 계약 위반(ValueError)도 traceback이 아니라 skipped로 접힌다.

    세 스크립트의 except 튜플이 갈리면 같은 어댑터 결함에서 한쪽만 죽는다.
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"gone@m": True}})
    monkeypatch.setitem(pc.SECTION_NORMALIZE, "enabledPlugins", drops_a_key)
    monkeypatch.setattr(pc, "DEFAULT_SETTINGS",
                        write_settings(tmp_path, enabledPlugins={"gone@m": True}))
    monkeypatch.setattr(pc, "DEFAULT_INSTALLED", write_installed(tmp_path))
    monkeypatch.setattr(pc, "DEFAULT_HELD", str(tmp_path / "none-held.json"))
    monkeypatch.setattr(sys, "argv",
                        ["compare_plugins.py", os.path.join(repo, pc.BACKUP_RELPATH)])
    compare_plugins.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped"
    assert out["reason"]


def test_compare_refuses_an_unknown_repo_schema(tmp_path):
    """읽기 전용이지만 "레포에 아무것도 없다"는 오보를 내지 않는다 (14.1)."""
    repo = write_repo(tmp_path, {})
    with open(os.path.join(repo, pc.BACKUP_RELPATH), "w", encoding="utf-8") as f:
        f.write('{"version": 3, "enabledPlugins": {}}')
    with pytest.raises(pc.UnknownBackupSchema):
        compare_plugins.compare(os.path.join(repo, pc.BACKUP_RELPATH),
                                settings_path=write_settings(tmp_path),
                                installed_path=write_installed(tmp_path),
                                held_path=str(tmp_path / "none-held.json"))


def test_compare_output_never_carries_plaintext_secrets(tmp_path):
    """보고는 사용자 눈앞과 로그로 나간다 — 평문 옵션 값이 실리면 6.1이 무너진다.

    레포 파일과 달리 이쪽은 디스크에 남지 않아 유출이 눈에 띄지 않는다. 보고 dict에
    로컬 값을 그대로 실으면(디버깅 목적이 흔한 동기다) 마스킹 계층 전체를 우회한다.

    섹션이 접힌 실행에서도 "평문이 없다"는 저절로 참이 되므로, 그 단정 **앞에** 섹션이
    ok임을 확인한다 — 확인이 없으면 이 테스트는 하드코딩과 구별되지 않는다.
    """
    out = compare(tmp_path,
                  local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}},
                  repo={"pluginConfigs": {"p@m": {"options": {"apiKey": pc.SENTINEL}}}})
    assert out["sections"]["pluginConfigs"]["status"] == "ok"
    assert "sk-real" not in json.dumps(out, ensure_ascii=False)


def test_compare_says_which_way_an_on_off_change_went(tmp_path):
    """9.2 — changed가 키 목록뿐이면 켬→끔인지 그 반대인지가 출력 어디에도 없다.

    소비자가 그 문구를 만들려면 settings.json과 plugins.json을 **직접 다시 읽어야** 하고,
    그 순간 status 경로에 두 번째 파서가 생긴다 — 그것이 정확히 결함 B의 형태다.
    """
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                  repo={"enabledPlugins": {"p@m": False}})
    section = out["sections"]["enabledPlugins"]
    assert section["changed"] == ["p@m"]
    assert section["changed_detail"] == {"p@m": {"local": True, "repo": False}}


def test_released_extended_value_still_shows_it_is_a_version_constraint(tmp_path):
    """6.4의 탈출구를 쓴 키는 보류가 풀려 changed로 떨어진다 — 종류가 held에서 사라진다.

    보류된 동안에는 held["extended_value"]가 "버전 제약"이라는 사실을 말해 주지만,
    release 뒤에는 그 자리가 비므로 changed_detail만이 남는 근거다. 값이 없으면
    소비자가 켬/끔 변경과 버전 제약을 구별할 수 없다(9.2).
    """
    held = tmp_path / "plugins-held.json"
    held.write_text(json.dumps({"version": 1, "pluginConfigs": {},
                                "release": {"enabledPlugins": ["p@m"]}}),
                    encoding="utf-8")
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}},
                  repo={"enabledPlugins": {"p@m": ["1.0.0"]}}, held=str(held))
    section = out["sections"]["enabledPlugins"]
    assert section["held"]["extended_value"] == []      # 보류가 풀렸다
    assert section["changed"] == ["p@m"]
    assert section["changed_detail"]["p@m"] == {"local": True, "repo": ["1.0.0"]}


def test_changed_detail_is_derived_from_changed_and_cannot_drift(tmp_path):
    """같은 값을 두 곳에서 만들면 갈리고, 갈려도 증상이 없다 — 한 곳에서 파생시킨다.

    비지 않은 changed와 **두 개 이상의 키**가 있어야 이 단정이 공허해지지 않는다.
    """
    out = compare(tmp_path,
                  local={"enabledPlugins": {"a@m": True, "b@m": False, "same@m": True}},
                  repo={"enabledPlugins": {"a@m": False, "b@m": True, "same@m": True}})
    section = out["sections"]["enabledPlugins"]
    assert section["changed"] == ["a@m", "b@m"]
    assert sorted(section["changed_detail"]) == section["changed"]


def test_changed_detail_carries_normalized_values_not_plaintext(tmp_path):
    """changed_detail에 원본을 실으면 마스킹 계층 전체를 우회한다 (6.1).

    단정이 공허해지지 않도록 섹션이 접히지 않았다는 것과 changed가 비지 않았다는 것을
    **먼저** 확인한다 — 둘 중 하나라도 무너지면 "평문이 없다"는 저절로 참이 된다.
    """
    out = compare(tmp_path,
                  local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}},
                  repo={"pluginConfigs": {"p@m": {"options": {"apiKey": pc.SENTINEL,
                                                             "region": pc.SENTINEL}}}})
    section = out["sections"]["pluginConfigs"]
    assert section["status"] == "ok"
    assert section["changed"] == ["p@m"]
    assert section["changed_detail"]["p@m"]["local"] == {"options": {"apiKey": pc.SENTINEL}}
    assert "sk-real" not in json.dumps(out, ensure_ascii=False)


def build_plan(tmp_path, local=None, repo=None, base=None, installed=None, held=None):
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    return plan_plugins.build_plan(
        os.path.join(repo_dir, pc.BACKUP_RELPATH),
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "none-held.json"),
        base_dir=write_base_blob(tmp_path, base))


def test_plan_exposes_exactly_eleven_buckets_per_section(tmp_path):
    """코어가 버킷을 늘리면 여기서 걸린다 — 화이트리스트는 조용히 빠뜨린다.

    MCP는 아홉이지만 플러그인은 두 축을 **노출한다** — H3의 value_held는 사용자에게
    별도 문구로 말해야 하고, action_held는 어떤 명령의 대상도 아님을 알려야 한다.
    """
    out = build_plan(tmp_path)
    for section in pc.SECTIONS:
        assert set(out["sections"][section]) == set(ks.BUCKETS) | {"status"}


def test_plan_routes_new_repo_entries_by_secret_need(tmp_path):
    repo = {"enabledPlugins": {"plain@m": True, "conf@m": True},
            "extraKnownMarketplaces": {"m": GH},
            "pluginConfigs": {"conf@m": {"options": {"apiKey": pc.SENTINEL}}}}
    out = build_plan(tmp_path, local={}, repo=repo)
    assert out["sections"]["enabledPlugins"]["add"] == ["conf@m", "plain@m"]
    assert out["sections"]["pluginConfigs"]["needs_secret"] == ["conf@m"]
    assert out["config_keys"] == {"conf@m": ["apiKey"]}
    # conf@m은 두 섹션의 설치 버킷에 **동시에** 있다. 목록에 두 번 실리면 설치 명령이
    # 두 번 나가고, 두 번째는 이미 설치된 상태에서 실패해 거짓 실패로 보고된다.
    assert out["install"] == ["conf@m", "plain@m"]


def test_plan_installs_a_plugin_that_only_plugin_configs_names(tmp_path):
    """9.3.1의 4단계(설정 채우기)도 `install --config`다 — 설치 목록에서 빠지면
    그 플러그인의 설정을 채울 명령이 어디에서도 나오지 않는다.

    enabledPlugins의 add가 **비어 있는** 것을 함께 못박는다 — 그 섹션이 install을
    대신 채우면 이 단정이 pluginConfigs 기여를 재지 못한다.

    같은 fixture로 "부재는 false가 아니다"를 계획 층위에서 못박는다 (1-c C4) —
    conf@m은 **설치 대상이면서** 레포 enabledPlugins에 없다(= 매니페스트 기본값에
    위임). disable 가드가 부재를 false로 접으면 이 플러그인이 설치 직후 꺼진다.
    **여기가 그 가드를 재는 유일한 자리다** — 아래
    test_plan_never_disables_a_key_absent_from_the_repo의 키는 레포에 없어
    install에 애초에 들어오지 않으므로 그쪽 단정은 가드와 무관하게 참이다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"extraKnownMarketplaces": {"m": GH},
                           "pluginConfigs": {"conf@m": {"options":
                                                        {"apiKey": pc.SENTINEL}}}})
    assert out["sections"]["enabledPlugins"]["add"] == []
    assert out["install"] == ["conf@m"]
    assert out["depends_on"] == {"conf@m": "m"}
    assert out["disable_after_install"] == []


def test_plan_gives_marketplace_add_arguments(tmp_path):
    """SKILL.md가 레포 파일을 직접 파싱하면 파서 두 벌이 되살아난다 (8.6)."""
    out = build_plan(tmp_path, local={}, repo={"extraKnownMarketplaces": {"m": GH}})
    assert out["marketplace_add"] == [
        {"name": "m", "arg": "june20516/suberpower", "reserved": False}]


def test_plan_skips_always_known_marketplaces(tmp_path):
    """14.1 — 실패할 등록 시도를 애초에 만들지 않는다 (8.2)."""
    repo = {"extraKnownMarketplaces": {name: GH for name in sorted(pc.ALWAYS_KNOWN)}}
    out = build_plan(tmp_path, local={}, repo=repo)
    assert out["marketplace_add"] == []
    assert out["skipped_always_known"] == sorted(pc.ALWAYS_KNOWN)


def test_plan_flags_reserved_names_without_filtering_them(tmp_path):
    """8.3 — 정당한 소유자일 수 있으므로 시도한다. 다만 갈래를 미리 알려 준다."""
    out = build_plan(tmp_path, local={},
                     repo={"extraKnownMarketplaces": {"healthcare": GH}})
    assert out["marketplace_add"] == [
        {"name": "healthcare", "arg": "june20516/suberpower", "reserved": True}]


def test_plan_reports_dependency_of_each_install_on_its_marketplace(tmp_path):
    """9.3.2 — 1단계가 실패한 마켓플레이스의 플러그인은 2단계를 시도하지 않는다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@m": True},
                           "extraKnownMarketplaces": {"m": GH}})
    assert out["depends_on"] == {"p@m": "m"}


def test_plan_omits_dependency_for_always_known_marketplaces(tmp_path):
    """등록 단계가 없는 마켓플레이스에 blocked를 걸면 설치가 영영 차단된다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@claude-plugins-official": True}})
    # 설치 대상이 되었는데도 의존이 없다는 것이 요지다. install이 비면 저절로 참이 된다.
    assert out["install"] == ["p@claude-plugins-official"]
    assert out["depends_on"] == {}


def test_plan_disables_only_what_install_would_leave_wrong(tmp_path):
    """설치 직후 값은 true다. 레포가 false인 것만 disable 대상이다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"on@m": True, "off@m": False},
                           "extraKnownMarketplaces": {"m": GH}})
    assert out["disable_after_install"] == ["off@m"]


def test_plan_disables_nothing_outside_the_install_list(tmp_path):
    """disable은 **설치 직후**의 값 맞추기다 — 그 범위를 install 밖으로 넓히면 이미
    로컬에 있는 항목까지 대상이 된다.

    wait@m은 케이스 9로 사용자 선택을 기다리는 중인데 레포 값이 false다. 범위가
    넓어지면 선택을 묻기도 전에 disable 명령이 나간다. 같은 fixture에서 install에
    **있는** off@m은 대상이 되는 것을 함께 못박는다 — 안 그러면 "아무것도 disable하지
    않는다"로 저절로 참이 된다.
    """
    out = build_plan(tmp_path, local={"enabledPlugins": {"wait@m": True}},
                     repo={"enabledPlugins": {"wait@m": False, "off@m": False},
                           "extraKnownMarketplaces": {"m": GH}})
    section = out["sections"]["enabledPlugins"]
    assert section["both_changed"] == ["wait@m"]     # 레포 값이 false인 미설치 대상
    assert out["install"] == ["off@m"]
    assert out["disable_after_install"] == ["off@m"]


def test_plan_does_not_disable_a_plugin_that_is_already_off_locally(tmp_path):
    """install의 항목이 전부 "설치 직후 = true"인 것은 아니다.

    Task 10.5 이후 install은 installed_plugins.json에 없는 id만 담는다. 그래도 이
    fixture의 already@m은 그 파일에 없으면서 settings.json에는 값이 있는 **불일치
    상태**라 install에 들고, 그 값이 false다. 상수 true를 쓰면 이미 꺼진 것에
    disable이 나간다. (같은 취지의 넓은 문장은 candidates 쪽에 있다.)

    already@m은 로컬 enabledPlugins에 이미 false로 있고 레포도 false다(= in_sync).
    disable 판정이 로컬 값 자리에 상수 true를 넣으면 "true → false이니 disable"로 읽혀
    이미 꺼진 플러그인에 명령이 나가고, enable/disable은 멱등이 아니라 exit 1이다.

    같은 fixture에 진짜 신규 설치인 off@m을 함께 둔다 — 없으면 "아무것도 disable하지
    않는다"로 저절로 참이 되어 판별력을 잃는다.
    """
    out = build_plan(
        tmp_path,
        local={"enabledPlugins": {"already@m": False}},
        repo={"enabledPlugins": {"already@m": False, "off@m": False},
              "extraKnownMarketplaces": {"m": GH},
              "pluginConfigs": {"already@m": {"note": "x"}}})
    section = out["sections"]["enabledPlugins"]
    # 로컬 값이 이미 레포와 같다 — 이 단정이 없으면 아래가 "레포에 없어서"로도 참이 된다.
    assert section["in_sync"] == ["already@m"]
    assert out["install"] == ["already@m", "off@m"]
    assert out["disable_after_install"] == ["off@m"]


def test_plan_sorts_install_across_both_contributing_sections(tmp_path):
    """install은 두 섹션의 기여를 이어 붙인다 — 정렬하지 않으면 순서가 섹션 순서에
    끌려가 비결정적으로 보인다.

    **삽입 순서와 정렬 순서가 다른** 이름을 쓴다: enabledPlugins가 zeta@m을,
    pluginConfigs가 alpha@m을 낸다. 이어 붙인 그대로면 [zeta@m, alpha@m]이다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"zeta@m": True},
                           "extraKnownMarketplaces": {"m": GH},
                           "pluginConfigs": {"alpha@m": {"options":
                                                         {"apiKey": pc.SENTINEL}}}})
    section = out["sections"]
    assert section["enabledPlugins"]["add"] == ["zeta@m"]
    assert section["pluginConfigs"]["needs_secret"] == ["alpha@m"]
    assert out["install"] == ["alpha@m", "zeta@m"]


def test_plan_carries_both_values_for_every_decided_key(tmp_path):
    """8.6 — SKILL.md가 케이스 8·9의 값을 알아야 한다. 없으면 레포 파일을 다시 파싱해야
    하고 그것이 "파서 두 벌"이다.

    세 갈래(repo_ahead·both_changed·value_held)와 install을 **동시에** 채우고, 같은 키의
    레포 값과 로컬 값이 **서로 다르게** 만든다 — 한쪽을 비우거나 두 출처를 뒤바꾸는
    회귀가 각각 따로 드러나야 하기 때문이다. 판정 대상이 아닌 두 키(local_ahead의
    mine@m, local_only의 solo@m)를 함께 두어 목록이 decided로 좁혀지는 것도 잰다.

    **decided는 set이므로 정렬 전 순서를 이름으로 통제할 수 없다**(plan_plugins의 set
    comprehension). 그 순서는 버킷 순회 순서가 아니라 **문자열 해시 순서**이고 실행마다
    PYTHONHASHSEED에 끌려간다. 그래서 아래 정렬 단정은 정상 코드에서 **항상** 참이고,
    sorted를 없앤 회귀는 원소 수가 n일 때 약 1 - 1/n! 확률로 잡힌다 — 결정적이지 않다.
    **원소를 줄이면 그 확률이 떨어진다**(2원소면 절반을 놓친다). 그래서 decided를 여섯으로
    채운다 — repo_ahead 둘 + both_changed 하나 + value_held 하나 + install 둘 → 1/720.
    """
    base = {"enabledPlugins": {"zeta@m": True, "bravo@m": True, "both@m": True,
                               "mine@m": True}}
    local = {"enabledPlugins": {"zeta@m": True, "bravo@m": True, "both@m": ["2.0.0"],
                                "mine@m": False, "alpha@m": True, "solo@m": True}}
    repo = {"enabledPlugins": {"zeta@m": False, "bravo@m": False, "both@m": False,
                               "mine@m": True, "alpha@m": ["1.0.0"], "new@m": True,
                               "delta@m": True},
            "extraKnownMarketplaces": {"m": GH}}
    out = build_plan(tmp_path, local=local, repo=repo, base=base)
    section = out["sections"]["enabledPlugins"]
    assert section["repo_ahead"] == ["bravo@m", "zeta@m"]  # 케이스 8
    assert section["both_changed"] == ["both@m"]           # 케이스 9
    assert section["value_held"] == ["alpha@m"]            # H3
    assert section["local_ahead"] == ["mine@m"]            # 케이스 7 — 판정 대상이 아니다
    assert section["local_only"] == ["solo@m"]             # 케이스 1 — 판정 대상이 아니다
    assert out["install"] == ["delta@m", "new@m"]
    assert out["repo_values"] == {"zeta@m": False, "bravo@m": False, "both@m": False,
                                  "alpha@m": ["1.0.0"], "new@m": True, "delta@m": True}
    # new@m·delta@m은 로컬에 없다 — 없는 키를 넣으면 SKILL.md가 "값이 바뀐다"고 잘못 말한다.
    assert out["local_values"] == {"zeta@m": True, "bravo@m": True,
                                   "both@m": ["2.0.0"], "alpha@m": True}
    # decided를 정렬하지 않으면 집합 순회가 문자열 해시에 끌려가 **JSON 출력의 키 순서가
    # 실행마다 바뀐다.** dict를 ==로 비교하는 위의 두 단정은 순서를 보지 못하므로, install만
    # 정렬이 고정되고 같은 파일의 다른 출력은 아닌 비대칭이 남는다. 그것을 여기서 닫는다.
    assert list(out["repo_values"]) == sorted(out["repo_values"])
    assert list(out["local_values"]) == sorted(out["local_values"])


def test_plan_splits_bare_install_from_the_config_step_by_the_installed_set(tmp_path):
    """9.3.1 — 2단계(`plugin install <id>`)와 4단계(`install --config k=v`)는 다른 단계다.

    Task 9 quality review가 실측한 재현이 이것이다: 이미 설치된 플러그인에 bare install이
    나가면 CLI가 exit 1로 죽어 **거짓 실패**가 된다. old@m은 이 기기에 **설치돼 있고**
    레포에만 pluginConfigs가 있으므로 2단계가 아니라 4단계다.

    두 목록이 **서로 다른 비지 않은 값**을 갖는다 — 한쪽이 비면 분리 자체가 측정되지 않고
    "합쳐도 같은 결과"와 구별할 수 없다.
    """
    out = build_plan(
        tmp_path, local={},
        repo={"enabledPlugins": {"new@m": True},
              "extraKnownMarketplaces": {"m": GH},
              "pluginConfigs": {"old@m": {"options": {"apiKey": pc.SENTINEL}}}},
        installed=write_installed(tmp_path, {"old@m": [{"scope": "user"}]}))
    # 두 섹션이 각각 후보를 하나씩 냈다 — 한 섹션만 기여하면 분리가 절반만 측정된다.
    assert out["sections"]["enabledPlugins"]["add"] == ["new@m"]
    assert out["sections"]["pluginConfigs"]["needs_secret"] == ["old@m"]
    assert out["install"] == ["new@m"]
    assert out["skipped_already_installed"] == ["old@m"]
    assert out["config_keys"] == {"old@m": ["apiKey"]}


def test_plan_does_not_reinstall_what_only_the_manifest_default_enables(tmp_path):
    """**enabledPlugins의 키 부재는 미설치가 아니다** — 매니페스트 기본값(defaultEnabled)에
    위임하는 상태다. 이 task의 존재 이유가 그 구별이다.

    default@m은 settings.json의 enabledPlugins에 **없지만** 설치돼 있다. 2단계/4단계
    판정을 설치 집합 대신 **로컬 섹션 문서**로 하면 이 키가 2단계로 가서 bare install이
    나가고, 이미 설치된 플러그인이라 exit 1로 실패한다.

    miss@m은 어디에도 없다 — 2단계가 비지 않아야 위 단정이 "install이 늘 빈다"로 저절로
    참이 되지 않는다.
    """
    out = build_plan(
        tmp_path, local={},
        repo={"enabledPlugins": {"default@m": True, "miss@m": True},
              "extraKnownMarketplaces": {"m": GH}},
        installed=write_installed(tmp_path, {"default@m": [{"scope": "user"}]}))
    # 둘 다 add 버킷이다 — 로컬 섹션 문서만 보면 구별할 수 없다는 사실을 못박는다.
    assert out["sections"]["enabledPlugins"]["add"] == ["default@m", "miss@m"]
    assert out["install"] == ["miss@m"]
    assert out["skipped_already_installed"] == ["default@m"]


def test_a_broken_held_file_does_not_empty_the_installed_set(tmp_path):
    """부분 실패 — 보류 파일만 깨진 실행에서 설치 집합은 **살아 있어야 한다**.

    read_hold_inputs가 installed_ids를 빈 frozenset으로 접는 갈래는 AutoFlagsUnavailable
    **하나뿐**이고, 그 갈래는 enabledPlugins·pluginConfigs를 함께 skip한다. 그 대응이 이
    접힘이 fail-open이 아닌 유일한 근거다. 보류 파일 갈래(HeldStateUnavailable)는
    pluginConfigs 하나만 skip하므로, 여기서도 설치 집합을 접으면 enabledPlugins가 살아
    있는 채로 그 집합만 비어 정확히 근거가 경고한 재앙이 일어난다 — compare는 설치된
    플러그인 전부를 "미설치"로 보고하고, build_plan은 그 전부를 2단계에 실어
    bare install → exit 1의 거짓 실패를 양산한다(9.3.1).

    **한 fixture를 두 스크립트에 함께 건다.** 설치 집합의 소비자가 그 둘뿐이라, 한쪽만
    재면 다른 쪽에서 조용히 갈릴 수 있다.

    ghost@m은 정말로 설치돼 있지 않다 — 없으면 "미설치가 비었다"와 "2단계가 비었다"가
    설치 판정과 무관하게 저절로 참이 된다.

    **설치된 넷은 skipped_already_installed의 순서를 재기 위한 개수다** — 이 목록을 설치
    집합 순회로 만드는 회귀는 정렬 순서를 깬다. 그 가드도 위와 같은 이유로 확률적이다.
    """
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    # 값이 확장 포맷이라 다섯 다 H3 보류다 — 보류여야 absent_locally에 들어온다.
    repo = {"enabledPlugins": {"one@m": ["1.0.0"], "two@m": ["2.0.0"],
                               "three@m": ["3.0.0"], "four@m": ["4.0.0"],
                               "five@m": ["5.0.0"], "six@m": ["6.0.0"],
                               "ghost@m": ["9.0.0"]},
            "extraKnownMarketplaces": {"m": GH}}
    installed = write_installed(tmp_path, {"one@m": [{"scope": "user"}],
                                           "two@m": [{"scope": "user"}],
                                           "three@m": [{"scope": "user"}],
                                           "four@m": [{"scope": "user"}],
                                           "five@m": [{"scope": "user"}],
                                           "six@m": [{"scope": "user"}]})
    out = compare(tmp_path, local={}, repo=repo, installed=installed, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    section = out["sections"]["enabledPlugins"]
    assert section["status"] == "ok"
    assert section["absent_locally"] == ["five@m", "four@m", "ghost@m", "one@m",
                                        "six@m", "three@m", "two@m"]
    assert section["not_installed"] == ["ghost@m"]

    plan = build_plan(tmp_path, local={}, repo=repo, installed=installed, held=str(held))
    assert plan["sections"]["pluginConfigs"]["status"] == "skipped"
    assert plan["install"] == ["ghost@m"]
    assert plan["skipped_already_installed"] == ["five@m", "four@m", "one@m",
                                                "six@m", "three@m", "two@m"]


def test_plan_keeps_the_value_and_dependency_steps_on_both_lists(tmp_path):
    """3·4단계의 기준은 2단계 목록이 아니라 **두 목록의 합집합**이다.

    disable_after_install — 이미 설치된 id도 값 맞추기(3단계) 대상이다. here@m은 설치돼
      있고 로컬 enabledPlugins에 값이 없으며(매니페스트 기본값에 위임 = 켜짐으로 가정)
      레포가 false다. 2단계 목록으로 좁히면 이 disable이 사라져 플러그인이 켜진 채 남는다.
    depends_on — 근거는 명령의 형태다. 두 단계 모두 `plugin install <id@marketplace>`
      형태라 1단계 등록에 의존한다(9.3.2의 단계 종속이 아니다 — 그쪽은 2단계 실패를
      다루고 skipped_already_installed에는 2단계가 없다). 좁히면 등록에 실패한
      마켓플레이스로 4단계 명령이 나가 거짓 실패를 양산한다.
    config_keys — 코어의 needs_secret 버킷에서 나오고 설치 여부와 무관하다. 어느 한쪽으로
      좁히면 다른 쪽 id의 설정이 어디에서도 채워지지 않는다.

    세 필드가 **두 목록의 항목을 모두** 담는지가 요지이므로, 각 목록에 항목이 하나씩
    들어가는 fixture를 쓴다.
    """
    out = build_plan(
        tmp_path, local={},
        repo={"enabledPlugins": {"here@m": False, "gone@m": False},
              "extraKnownMarketplaces": {"m": GH},
              "pluginConfigs": {"here@m": {"options": {"apiKey": pc.SENTINEL}},
                                "gone@m": {"options": {"token": pc.SENTINEL}}}},
        installed=write_installed(tmp_path, {"here@m": [{"scope": "user"}]}))
    assert out["install"] == ["gone@m"]
    assert out["skipped_already_installed"] == ["here@m"]
    assert out["disable_after_install"] == ["gone@m", "here@m"]
    assert out["depends_on"] == {"gone@m": "m", "here@m": "m"}
    assert out["config_keys"] == {"gone@m": ["token"], "here@m": ["apiKey"]}
    # 값 페이로드도 합집합을 따른다 — 좁히면 SKILL.md가 3·4단계 문구를 만들 값을 잃는다.
    assert sorted(out["repo_values"]) == ["gone@m", "here@m"]


def test_plan_reads_base_of_each_section_from_that_section(tmp_path):
    """base를 안 읽거나 엉뚱한 섹션에서 읽으면 삭제 후보(케이스 4·5)가 통째로 사라진다 —
    로컬 신규(케이스 1)로 보이므로 예외도 빈 결과도 나지 않는다.

    세 섹션의 base 키를 **모두 다르게** 둔다. 한 섹션의 base를 세 섹션에 돌려 쓰면
    나머지 둘의 키가 base에 없어 local_only로 새는 것이 드러난다.
    """
    local = {"enabledPlugins": {"gone@m": True},
             "extraKnownMarketplaces": {"m": GH},
             "pluginConfigs": {"conf@m": {"options": {"token": "t"}}}}
    base = {"enabledPlugins": {"gone@m": True},
            "extraKnownMarketplaces": {"m": GH},
            "pluginConfigs": {"conf@m": {"options": {"token": pc.SENTINEL}}}}
    out = build_plan(tmp_path, local=local, repo={}, base=base)
    for section, key in (("enabledPlugins", "gone@m"),
                         ("extraKnownMarketplaces", "m"),
                         ("pluginConfigs", "conf@m")):
        assert out["sections"][section]["local_stale"] == [key]
        # base를 못 읽었을 때 이 키가 흘러가는 곳이다. 비어 있어야 위 단정이 공허하지 않다.
        assert out["sections"][section]["local_only"] == []


def test_plan_never_disables_a_key_absent_from_the_repo(tmp_path):
    """14.1 — 부재는 꺼짐이 아니다 (1-c C4).

    **이 fixture는 disable 가드를 타지 않는다** — local@m은 레포에 없어 install에
    애초에 들어오지 않으므로 disable_after_install 단정은 가드와 무관하게 참이다.
    가드 자체는 test_plan_installs_a_plugin_that_only_plugin_configs_names가 잰다.
    여기서 재는 것은 repo_values의 범위다.
    """
    out = build_plan(tmp_path, local={"enabledPlugins": {"local@m": True}},
                     repo={"enabledPlugins": {}})
    # 케이스 1(로컬 신규)로 떨어진 것을 먼저 못박는다 — 이것이 없으면 두 단정이
    # "레포에 없으므로 어느 목록에도 없다"로 저절로 참이 되어 판별력을 잃는다.
    assert out["sections"]["enabledPlugins"]["local_only"] == ["local@m"]
    assert out["disable_after_install"] == []
    assert "local@m" not in out["repo_values"]


def test_plan_puts_installed_extended_values_in_their_own_bucket(tmp_path):
    """8.4 — both_changed로 부르면 "양쪽이 바뀌었습니다"라는 거짓 문구가 뜬다."""
    out = build_plan(tmp_path, local={"enabledPlugins": {"p@m": True}},
                     repo={"enabledPlugins": {"p@m": ["1.0.0"]},
                           "extraKnownMarketplaces": {"m": GH}})
    section = out["sections"]["enabledPlugins"]
    assert section["value_held"] == ["p@m"]
    assert section["both_changed"] == [] and section["repo_ahead"] == []
    # 이 버킷의 키는 **이미 로컬에 있다.** 설치 목록에 넣으면 SKILL.md가 설치를 다시
    # 시도한다 — 새 기기 갈래(add)와 값만 다른 갈래(value_held)를 가른 이유가 이것이다.
    assert out["install"] == []


def test_extended_value_is_installed_on_a_new_machine(tmp_path):
    """14.1 — 값 보류를 행동 보류로 잘못 구현하는 회귀를 막는다 (5.3).

    설치하지 않으면 어느 기기에도 설치되지 않고, 모두가 값 보류라 아무도 push하지
    않아 레포 값이 영원히 고정되며, 삭제 판정에서도 빠진다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@m": ["1.0.0"]},
                           "extraKnownMarketplaces": {"m": GH}})
    assert out["sections"]["enabledPlugins"]["add"] == ["p@m"]
    assert out["install"] == ["p@m"]


def test_action_held_entries_become_no_command_at_all(tmp_path):
    """5.3 — 행동 보류 키는 어떤 CLI 명령의 대상도 되지 않는다."""
    out = build_plan(tmp_path, local={}, repo={"enabledPlugins": {"dep@m": True},
                                               "extraKnownMarketplaces": {"m": GH}},
                     installed=write_installed(tmp_path,
                                               {"dep@m": [{"scope": "user",
                                                           "auto": True}]}))
    assert out["sections"]["enabledPlugins"]["action_held"] == ["dep@m"]
    assert out["install"] == []
    assert out["disable_after_install"] == []


def test_plan_gives_reasons_for_unrestorable_entries(tmp_path):
    out = build_plan(tmp_path, local={}, repo={"enabledPlugins": {"p@nowhere": True}})
    assert out["sections"]["enabledPlugins"]["unrestorable"] == ["p@nowhere"]
    assert "소스가 없" in out["unrestorable_reasons"]["p@nowhere"]


def test_unrestorable_reason_and_the_verdict_read_the_same_repo(tmp_path):
    """10.2 — 판정(restorable)은 레포를 보는데 사유가 다른 문서를 보면 사유가 None이 되고,
    그 항목은 "복원 불가"로만 남아 사용자가 무엇을 해야 하는지 알 수 없다.

    **로컬에만 있는 마켓플레이스**가 있어야 두 입력이 갈린다 — 레포와 같으면 어느 쪽을
    넘겨도 같은 문장이 나와 이 단정이 판별력을 잃는다.
    """
    out = build_plan(tmp_path, local={"extraKnownMarketplaces": {"m": GH}},
                     repo={"enabledPlugins": {"p@m": True}})
    assert out["sections"]["enabledPlugins"]["unrestorable"] == ["p@m"]
    assert "소스가 없" in out["unrestorable_reasons"]["p@m"]


def test_status_and_restore_agree_on_which_keys_are_unrestorable(tmp_path):
    """**같은 fixture에서 두 스크립트의 `unrestorable`이 섹션마다 같은 집합이어야 한다.**

    갈렸던 자리는 값 보류다 — `compare_plugins`가 `ks.diff`의 `only_repo`(값 보류 제외)를
    훑고 `plan_plugins`가 `ks.restore_plan`의 버킷(값 보류 포함)에서 뽑아, H3(확장 값)
    보류이면서 레포 전용인 키에서 status는 "미설치 → restore가 설치"로, restore는
    "복원 불가"로 보고했다. **예외도 빈 결과도 나지 않아 증상이 전혀 없었다.**

    이 fixture가 그 갈래에 실제로 닿는지를 함께 건다 — `held.extended_value`가 비면
    아래 등호는 H3를 한 번도 지나지 않고 참이 된다(다섯째 축).
    H1·H2는 행동 보류이기도 해 restore가 `action_held`로 보내므로 이 갈래에 오지 않는다.
    """
    fixture = dict(
        local={},
        # auto@nowhere는 **행동 보류**(H1)여야 하므로 설치 파일에 auto로 실어 둔다.
        installed=write_installed(
            tmp_path, {"auto@nowhere": [{"scope": "user", "auto": True}]}),
        # h3@nowhere    확장 값(H3 = 값 보류만) + 레포 전용 + 소스 없음 → 복원 불가
        # plain@nowhere 보류가 아닌 레포 전용 + 소스 없음 → 복원 불가(대조군)
        # auto@nowhere  H1(값·행동 양축) + 레포 전용 + 소스 없음 → **어느 쪽도 아니다**
        #               (restore가 action_held로 보내 훑지 않는다). 이 키가 없으면
        #               route_new_for가 hold 대신 no_hold를 넘겨도 결과가 같아진다 —
        #               행동 축을 실제로 재는 것이 이 키뿐이다(다섯째 축, 실측).
        # ok@known      소스가 있어 복원 가능 → 어느 목록에도 없어야 한다
        repo={"enabledPlugins": {"h3@nowhere": {"version": "1.2"},
                                 "plain@nowhere": True,
                                 "auto@nowhere": True,
                                 "ok@known": True},
              "extraKnownMarketplaces": {"known": GH}})
    status = compare(tmp_path, **fixture)["sections"]
    plan = build_plan(tmp_path, **fixture)["sections"]
    assert status["enabledPlugins"]["held"]["extended_value"] == ["h3@nowhere"]
    assert status["enabledPlugins"]["held"]["auto"] == ["auto@nowhere"]
    assert plan["enabledPlugins"]["action_held"] == ["auto@nowhere"]
    for section in pc.SECTIONS:
        assert status[section]["unrestorable"] == plan[section]["unrestorable"], section
    assert status["enabledPlugins"]["unrestorable"] == ["h3@nowhere", "plain@nowhere"]


def test_compare_marks_a_held_repo_only_entry_unrestorable(tmp_path):
    """값 보류 키가 `only_repo`에서 빠지는 것과 복원 가능성 판정은 **다른 질문**이다.

    이 항목은 `only_repo`에 없고 `held.extended_value`·`not_installed`에만 뜨는데,
    restore는 그것을 설치 대상으로 훑다가 `unrestorable`로 접는다. 그 사실이 status에
    없으면 사용자는 "restore가 설치합니다"만 듣는다(spec 9.2가 금지한 문구).
    """
    out = compare(tmp_path, local={},
                  repo={"enabledPlugins": {"h3@nowhere": {"version": "1.2"}}})
    section = out["sections"]["enabledPlugins"]
    assert section["only_repo"] == []                    # 값 보류라 세 버킷에 없다
    assert section["not_installed"] == ["h3@nowhere"]
    assert section["unrestorable"] == ["h3@nowhere"]


def test_plan_gives_reasons_for_unrestorable_marketplaces(tmp_path):
    """10.2 — 사유가 **value를 실제로 보는** 갈래는 마켓플레이스뿐이다.

    플러그인 갈래의 unrestorable_reason은 키만 보고 value를 보지 않으므로, 이 스크립트가
    reason에 넘기는 masked[section].get(k)가 옳은 섹션의 옳은 값인지 위의 두 테스트는
    재지 못한다. 마켓플레이스 갈래는 _source_kind(value)와 _SOURCE_ARG_FIELDS로 **세 개의
    서로 다른 사용자 안내**를 만들므로 배선이 어긋나면 여기서만 증상이 난다 — value가
    None으로 새면 "출처 종류를 읽을 수 없다"(c)가 나와 멀쩡한 github 출처를 범인으로
    지목하고, 사유 루프가 enabledPlugins 한 섹션으로 좁혀지면 사유 자체가 사라진다.

    복원 **가능한** good을 함께 둔다 — 없으면 "전부 복원 불가"로도 단정이 참이 된다.
    """
    out = build_plan(tmp_path, local={},
                     repo={"extraKnownMarketplaces": {
                         # github 출처인데 인자로 쓸 repo 필드가 없다 → 갈래 (a)
                         "m": {"source": {"source": "github"}},
                         "good": GH}})
    section = out["sections"]["extraKnownMarketplaces"]
    assert section["unrestorable"] == ["m"]
    assert [entry["name"] for entry in out["marketplace_add"]] == ["good"]
    assert "필드가 비어 있다" in out["unrestorable_reasons"]["m"]


def test_plan_carries_no_secret_values(tmp_path):
    """계획은 SKILL.md의 대화로 흘러가고 임시 파일에 남는다 — 평문이 있으면 안 된다."""
    out = build_plan(tmp_path,
                     local={"pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}},
                     repo={"pluginConfigs": {"p@m": {"options": {"apiKey": pc.SENTINEL}}}})
    # 섹션이 접히면 평문이 실릴 자리 자체가 없어 단정이 공허해진다 — 먼저 확인한다.
    assert out["sections"]["pluginConfigs"]["status"] == "ok"
    assert out["sections"]["pluginConfigs"]["in_sync"] == ["p@m"]
    assert "sk-real" not in json.dumps(out, ensure_ascii=False)


def test_plan_skips_plugin_sections_when_auto_flags_are_unavailable(tmp_path):
    """9.3.6 — backup과 같은 규율을 restore에도 적용한다."""
    out = build_plan(tmp_path, local={},
                     repo={"enabledPlugins": {"p@m": True},
                           "extraKnownMarketplaces": {"m": GH}},
                     installed=str(tmp_path / "none-installed.json"))
    assert out["sections"]["enabledPlugins"]["status"] == "skipped"
    # **최상위는 섹션 skip을 반영하지 않는다(계약).** 여기를 skipped로 접으면 아래
    # marketplace_add 단정이 지키는 "부분 skip은 전체 skip이 아니다"와 어긋나고,
    # 반대로 이 줄이 없으면 두 의미 중 어느 쪽이 계약인지 아무것도 정해지지 않는다 —
    # 소비자는 최상위 ok를 "복원할 것이 없다"로 읽으면 안 된다(build_plan docstring).
    assert out["status"] == "ok"
    # 레포에 마켓플레이스 m이 **있어야** 이 단정이 skip을 잰다. 없으면 p@m이 skip과
    # 무관하게 unrestorable로 떨어져 install이 어차피 빈다.
    assert out["install"] == []
    # 부분 skip이 전체 skip으로 조용히 바뀌지 않았음을 함께 본다 (9.3.6).
    assert [m["name"] for m in out["marketplace_add"]] == ["m"]


def plan_script():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                        "skills", "sync-restore", "scripts",
                                        "plan_plugins.py"))


@pytest.mark.parametrize("args",
                         [[], ["bogus"], ["bogus", "x"], ["plan"], ["plan", "a", "b"]])
def test_plan_cli_rejects_wrong_invocations(tmp_path, args):
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다.

    서브커맨드 검사와 **개수 검사가 둘 다** 필요하다. 개수 검사가 빠지면
    `plan_plugins.py plan`이 usage 대신 IndexError traceback이 되는데, **종료 코드만
    보면 그 회귀가 보이지 않는다** — 처리되지 않은 예외도 1로 끝나기 때문이다.
    사용자가 자기 호출의 잘못을 알 수 있는 유일한 신호가 stderr의 usage다.

    ["bogus", "x"]가 **이름 검사를 재는 유일한 케이스다.** 나머지 넷은 개수만으로도
    걸리므로, 이 항목이 없으면 관문에서 `args[0] == "plan"`을 지워도 아무 테스트도
    실패하지 않고 `plan_plugins.py bogus <경로>`가 usage 없이 계획을 낸다.

    HOME을 격리한다 — 지금은 인자 검증에서 먼저 나가 실제 ~/.claude를 읽지 않지만,
    갈래를 넓힌 뒤 검사가 느슨해지는 순간 진짜 홈을 읽는다(파일 상단 규율).
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    proc = subprocess.run([sys.executable, plan_script()] + args,
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 1
    assert "사용:" in proc.stderr


def test_plan_cli_skips_when_normalize_drops_a_key(tmp_path, monkeypatch, capsys):
    """normalize 계약 위반(ValueError)도 traceback이 아니라 skipped로 접힌다.

    restore_plan은 diff와 **같은** normalize 계약 검사를 통과한다 — 훅이 키 집합을
    바꾸면 코어가 ValueError를 던진다. main()의 except 튜플에서 ValueError가 빠지면
    어댑터 훅의 결함 하나가 restore 흐름 전체를 traceback으로 세우고, 10.3("종료 코드는
    0이다 — 그래야 안내가 보인다")이 깨진다. 형제 둘(collect·compare)에만 이 테스트가
    있으면 세 스크립트 중 restore만 이 성질이 무보증으로 남는다.
    """
    repo = write_repo(tmp_path, {"enabledPlugins": {"gone@m": True}})
    monkeypatch.setitem(pc.SECTION_NORMALIZE, "enabledPlugins", drops_a_key)
    monkeypatch.setattr(pc, "DEFAULT_SETTINGS",
                        write_settings(tmp_path, enabledPlugins={"gone@m": True}))
    monkeypatch.setattr(pc, "DEFAULT_INSTALLED", write_installed(tmp_path))
    monkeypatch.setattr(pc, "DEFAULT_HELD", str(tmp_path / "none-held.json"))
    # 실제 ~/.claude/.sync-state를 읽지 않게 한다. base 이력은 이 회귀와 무관하다.
    monkeypatch.setattr(plan_plugins.ss, "read_base", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["plan_plugins.py", "plan",
                                      os.path.join(repo, pc.BACKUP_RELPATH)])
    plan_plugins.main()
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped"
    assert out["reason"]


def test_plan_cli_exits_zero_and_reports_skip(tmp_path):
    """10.3 — 종료 코드는 0이다. 그래야 안내가 보인다.

    레포에 항목이 **있는** 상태로 건너뛴다 — 비어 있으면 "할 일이 없어서 조용한 것"과
    "읽기 실패로 접힌 것"을 출력이 구별하지 못한다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    repo = write_repo(tmp_path, {"enabledPlugins": {"theirs@m": True}})
    proc = subprocess.run(
        [sys.executable, plan_script(), "plan", os.path.join(repo, pc.BACKUP_RELPATH)],
        capture_output=True, text=True, env=dict(os.environ, HOME=str(home)))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
    assert json.loads(proc.stdout)["reason"]


EMPTY_CHOICES = {section: {"keep_stale": [], "keep_local": []} for section in pc.SECTIONS}


def run_script(tmp_path, script, *args):
    """스크립트를 격리된 HOME으로 실행한다 (파일 상단 규율).

    tmp_path를 받는 것은 HOME을 pytest가 정리하게 하기 위해서다 — 인자 검증이
    느슨해지는 순간 스크립트가 진짜 ~/.claude를 읽는다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    return subprocess.run([sys.executable, script] + list(args),
                          capture_output=True, text=True,
                          env=dict(os.environ, HOME=str(home)))


def apply_base(tmp_path, choices=None, local=None, repo=None, base=None,
               installed=None, held=None, staging="staging"):
    repo_dir = write_repo(tmp_path, repo if repo is not None else {})
    merged = json.loads(json.dumps(EMPTY_CHOICES))
    for section, values in (choices or {}).items():
        if isinstance(values, dict):
            merged.setdefault(section, {}).update(values)
        else:
            merged[section] = values    # 형태가 어긋난 섹션 값을 그대로 넘기는 갈래
    result = plan_plugins.apply_base(
        os.path.join(repo_dir, pc.BACKUP_RELPATH),
        str(tmp_path / staging), merged,
        settings_path=write_settings(tmp_path, **(local or {})),
        installed_path=installed if installed is not None else write_installed(tmp_path),
        held_path=held if held is not None else str(tmp_path / "plugins-held.json"),
        base_dir=write_base_blob(tmp_path, base))
    return result, staged_doc(str(tmp_path / staging))


def test_apply_base_writes_the_final_name_directly(tmp_path):
    """9.3.7 — .tmp+rename을 적용하면 rename 트리거가 없어 base가 영영 전진하지 않는다."""
    _, doc = apply_base(tmp_path, local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": True}})
    assert doc["enabledPlugins"] == {"p@m": True}
    assert not os.path.exists(os.path.join(str(tmp_path / "staging"),
                                           pc.BACKUP_RELPATH + ".tmp"))


def test_keep_stale_forgets_the_history_so_the_entry_returns(tmp_path):
    """9.3.4 케이스 4·5 — base에서 지워야 다음 백업이 케이스 1로 push한다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_stale": ["X@m"]}},
                        local={"enabledPlugins": {"X@m": True}},
                        repo={"enabledPlugins": {}},
                        base={"enabledPlugins": {"X@m": True}})
    assert "X@m" not in doc["enabledPlugins"]


def test_keep_local_records_the_repo_value_so_the_landing_is_case7(tmp_path):
    """9.3.4 케이스 8·9 — base[k] ← 레포 값. base에서 지우면 케이스 1이 되어 뜻이 달라진다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_local": ["p@m"]}},
                        local={"enabledPlugins": {"p@m": False}},
                        repo={"enabledPlugins": {"p@m": True}},
                        base={"enabledPlugins": {"p@m": True}})
    assert doc["enabledPlugins"]["p@m"] is True


def test_choices_are_nested_by_section(tmp_path):
    """9.3.7 — 평면 목록이면 한쪽 선택이 다른 섹션의 base를 조작한다."""
    _, doc = apply_base(tmp_path,
                        choices={"enabledPlugins": {"keep_stale": ["p@m"]}},
                        local={"enabledPlugins": {"p@m": True},
                               "pluginConfigs": {"p@m": {"options": {}}}},
                        repo={"enabledPlugins": {}, "pluginConfigs": {}},
                        base={"enabledPlugins": {"p@m": True},
                              "pluginConfigs": {"p@m": {"options": {}}}})
    assert "p@m" not in doc["enabledPlugins"]
    assert "p@m" in doc["pluginConfigs"]


def test_value_held_keys_are_removed_from_base_without_any_override(tmp_path):
    """5.3 — 보류가 있는 어댑터는 restore 경로에서 스스로 value_held를 넘겨야 한다.

    넘기지 않으면 보류 키가 base에 얼어붙고, 보류가 풀리는 순간 케이스 3(삭제)이 난다.
    """
    _, doc = apply_base(tmp_path,
                        local={"enabledPlugins": {"p@m": True}},
                        repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
                        base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in doc["enabledPlugins"]


def test_release_lifts_the_hold_and_lands_on_case7(tmp_path):
    """7.3 — 해제만 하면 base에 키가 없어 케이스 9로 떨어진다. 약속과 반대다."""
    held_path = str(tmp_path / "plugins-held.json")
    result, doc = apply_base(tmp_path,
                             choices={"enabledPlugins": {"release": ["p@m"]}},
                             local={"enabledPlugins": {"p@m": True}},
                             repo={"enabledPlugins": {"p@m": ["1.0.0"]}},
                             held=held_path)
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # keep_local이 동시에 걸렸다
    # ④의 강제분도 **보고에 실린다.** 싣지 않으면 SKILL.md가 "로컬 유지를 고르신 항목"
    # 목록에서 이 키를 빼고 안내해, 사용자는 base가 전진한 사실을 볼 길이 없다.
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["p@m"]
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == ["p@m"]


def test_release_and_keep_local_naming_the_same_key_report_it_once(tmp_path):
    """④의 합류에는 중복 제거가 걸린다 — 없으면 kept_local에 같은 키가 두 번 실린다.

    SKILL.md가 그 목록을 그대로 렌더링하므로 사용자가 같은 항목을 두 줄로 본다.
    ③과 ④가 같은 키를 가리키는 것은 모순 입력이 아니다: 사용자가 케이스 8·9에서
    "로컬 유지"를 고르면서 같은 키의 H3를 함께 푸는 갈래가 그것이다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_local": ["p@m"], "release": ["p@m"]}},
        local={"enabledPlugins": {"p@m": True}},
        repo={"enabledPlugins": {"p@m": ["1.0.0"]}})
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["p@m"]
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # 적용 자체는 됐다


def test_keep_local_wins_over_keep_stale_on_the_same_key(tmp_path):
    """②③이 겹치면 ③이 이긴다 — ③이 뒤에 돌기 때문이고, 그 순서에는 근거가 있다.

    ③은 `key in masked` 가드를 가지므로 **레포에 값이 있을 때만** 적용된다. 그런데
    ②(케이스 4·5)는 "레포가 그 키를 잃었다"는 뜻이라, 둘이 겹치는 입력은 이미 모순이다.
    순서를 뒤집으면 그 모순 입력이 정당한 선택을 조용히 덮어 base에서 키가 사라지고
    다음 백업이 케이스 1(로컬 신규)로 착지한다.

    **kept_stale은 그때도 요청을 그대로 보고한다** — 같은 보고의 base_keys가 그 키를
    담으므로 소비자가 대조할 수 있다는 것이 그 비대칭을 받아들이는 근거다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_stale": ["p@m"], "keep_local": ["p@m"]}},
        local={"enabledPlugins": {"p@m": False}},
        repo={"enabledPlugins": {"p@m": True}},
        base={"enabledPlugins": {"p@m": True}})
    assert doc["enabledPlugins"]["p@m"] is True
    section = result["sections"]["enabledPlugins"]
    assert section["kept_stale"] == ["p@m"]
    assert section["kept_local"] == ["p@m"]
    assert section["base_keys"] == ["p@m"]


def test_release_list_is_sorted_regardless_of_where_the_entries_came_from(tmp_path):
    """보고·기록의 순서가 실행마다 흔들리면 diff가 흔들린다.

    이 catch는 **결정적이다** — 정렬 대상 released는 set이 아니라 리스트이고(이전
    파일의 순서 + 이번 선택의 순서), 이 fixture는 그 결합 순서를 정렬의 역순
    ["z@m", "a@m"]으로 만든다. 해시 순서에 기대지 않는다.

    선택에 z@m을 함께 넣어 **중복 제거도 같이 잰다** — 빠지면 결과가
    ["a@m", "z@m", "z@m"]이 되어 같은 단정이 갈라낸다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {}, "release": {"enabledPlugins": ["z@m"]}}, f)
    apply_base(tmp_path,
               choices={"enabledPlugins": {"release": ["a@m", "z@m"]}},
               local={"enabledPlugins": {"a@m": True, "z@m": True}},
               repo={"enabledPlugins": {"a@m": ["1.0.0"], "z@m": ["2.0.0"]}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == ["a@m", "z@m"]


def test_release_entry_is_cleared_once_the_repo_value_is_boolean(tmp_path):
    """조건이 사라지면 항목도 사라진다 — H4의 지문 규칙과 같은 형태다.

    이전 파일과 이번 선택 **양쪽에** p@m을 넣는다 — 두 목록이 각자 조건을 재므로
    한쪽에만 넣으면 다른 쪽의 조건 검사를 지워도 이 단정이 통과한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {}, "release": {"enabledPlugins": ["p@m"]}}, f)
    apply_base(tmp_path, choices={"enabledPlugins": {"release": ["p@m"]}},
               local={"enabledPlugins": {"p@m": True}},
               repo={"enabledPlugins": {"p@m": True}}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["release"]["enabledPlugins"] == []


def test_declined_config_is_recorded_with_the_masked_repo_fingerprint(tmp_path):
    """6.4 — 로컬 값이나 사용자 입력값을 지문에 넣으면 영영 매치되지 않는다.

    레포 값에 **평문**을 넣는다. SENTINEL을 넣으면 마스킹이 항등이 되어 지문이 같아지고,
    지문 대상을 masked에서 원본으로 바꾸는 회귀를 단정이 구별하지 못한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}}
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    assert masked["delta@m"] != repo["pluginConfigs"]["delta@m"]   # 마스킹이 값을 바꿨다
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {
            "delta@m": pc.value_fingerprint(masked["delta@m"])}


def test_declining_again_refreshes_the_fingerprint_of_a_changed_repo_value(tmp_path):
    """6.4 — 레포 값이 바뀐 뒤 같은 키를 다시 거절하면 지문이 **갱신돼야** 한다.

    갱신이 죽으면 낡은 지문이 남아 H4가 다시 매치되지 않고, 사용자는 같은 항목을
    **매 restore마다 다시** 받는다. 예외도 빈 결과도 없이 조용하다.

    이전 파일에 실재하지 않는 지문을 두어 "이전 값을 그대로 옮긴 것"과 구별한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {"delta@m": "0" * 64},
                   "release": {"enabledPlugins": []}}, f)
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-new"}}}}
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    fresh = pc.value_fingerprint(masked["delta@m"])
    assert fresh != "0" * 64
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {"delta@m": fresh}


def test_held_file_directory_is_created_on_a_machine_that_never_backed_up(tmp_path):
    """~/.claude/.sync-state/를 아무도 먼저 만들지 않는다 — write_base가 만드는 것은
    그 안의 base뿐이고, 백업을 한 번도 하지 않은 기기에는 그 디렉토리가 없다.

    빠지면 FileNotFoundError가 스크립트의 except 튜플에 걸려 {"status": "skipped"}로
    접히고, 사용자의 decline이 **영영 기록되지 않는다.** 다른 테스트는 전부 이미 있는
    tmp 디렉토리를 주므로 이 줄이 일하는 자리를 재지 못한다.
    """
    held_path = str(tmp_path / "fresh-state" / "plugins-held.json")
    assert not os.path.exists(os.path.dirname(held_path))
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] != {}


def test_the_held_file_is_untouched_when_the_staging_write_fails(tmp_path):
    """스테이징(base) 먼저, 보류 파일 나중 — 그 순서를 지키는 fixture.

    스테이징 디렉토리 자리에 **일반 파일**을 두면 os.makedirs가 OSError로 죽는다.
    순서가 뒤바뀌면 그 시점에 보류 파일이 이미 쓰여 있고, 그러면 H3가 풀린 채로 base에
    키가 없어 다음 백업이 케이스 9로 떨어진다 — 약속과 반대다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    (tmp_path / "blocked").write_text("not a directory", encoding="utf-8")
    with pytest.raises(OSError):
        apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
                   local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
                   held=held_path, staging="blocked")
    assert not os.path.exists(held_path)


def test_apply_base_never_writes_a_plaintext_secret(tmp_path):
    """형제 plan_mcp의 같은 가드와 짝이다 — dict 동등성이 아니라 **원문**을 훑는다.

    "값이 실리는 자리가 구조적으로 없다"는 결론은 오늘 참이지만, 값을 담는 필드가
    나중에 하나라도 생기면 dict 대조 단정은 그것을 보지 못한다. 전진 갈래(ahead@m)와
    keep_local 갈래(kept@m)를 한 fixture에 함께 둔다 — 값이 base로 들어가는 자리가
    그 둘뿐이라서다.
    """
    _, doc = apply_base(
        tmp_path,
        choices={"pluginConfigs": {"keep_local": ["kept@m"]}},
        local={"pluginConfigs": {"ahead@m": {"options": {"apiKey": "sk-ahead"}},
                                 "kept@m": {"options": {"other": "x"}}}},
        repo={"pluginConfigs": {"ahead@m": {"options": {"apiKey": "sk-ahead"}},
                                "kept@m": {"options": {"apiKey": "sk-kept"}}}})
    raw = staged_text(str(tmp_path / "staging"))
    assert "sk-ahead" not in raw
    assert "sk-kept" not in raw
    # 두 갈래가 실제로 base에 들어갔다 — 아니면 위 두 단정이 공허하다.
    assert doc["pluginConfigs"]["ahead@m"] == {"options": {"apiKey": pc.SENTINEL}}
    assert doc["pluginConfigs"]["kept@m"] == {"options": {"apiKey": pc.SENTINEL}}


def test_configured_entry_is_dropped_from_the_held_file(tmp_path):
    """6.4 — 사용자가 마음을 바꿔 값을 입력하면 그 항목을 파일에서 지운다."""
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {"delta@m": "0" * 64},
                   "release": {"enabledPlugins": []}}, f)
    apply_base(tmp_path, choices={"pluginConfigs": {"configured": ["delta@m"]}},
               local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {}


def test_held_file_is_not_written_when_it_could_not_be_read(tmp_path):
    """깨진 파일을 빈 상태로 덮으면 사용자의 보류 선택이 조용히 사라진다."""
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        f.write("{not json")
    out, _ = apply_base(tmp_path, local={}, repo={}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert f.read() == "{not json"
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"


def test_apply_base_ignores_unknown_and_non_string_choice_entries(tmp_path):
    """선택 결과 JSON은 사용자 대화에서 만들어진다 — 형태가 어긋나도 죽지 않는다.

    **해시 불가능한 원소를 함께 넣는다.** None·3만 넣으면 필터를 지워도 nb.pop(None)과
    nb.pop(3)이 조용히 성공해 어떤 단정도 흔들리지 않는다 — 필터가 실제로 막는 것은
    리스트·객체가 dict 키 자리에 들어가 TypeError로 죽는 갈래다.
    그리고 보고에도 문자열만 실려야 한다 — SKILL.md가 그 목록을 사용자에게 보여 준다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_stale": [None, 3, ["x"], "p@m"],
                                    "keep_local": [{"k": 1}, "q@m"]},
                 "nonsense": {"keep_local": ["x"]}},
        local={"enabledPlugins": {"p@m": True}},
        repo={"enabledPlugins": {"q@m": True}},
        base={"enabledPlugins": {"p@m": True}})
    assert "p@m" not in doc["enabledPlugins"]
    assert result["sections"]["enabledPlugins"]["kept_stale"] == ["p@m"]
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["q@m"]


def test_failed_restore_does_not_advance_the_base(tmp_path):
    """10.4 — 로컬이 그 값에 동의하지 않았으므로 base가 전진하면 안 된다.

    "복원을 시도한 목록"이 아니라 **복원 후 다시 읽은 로컬**을 넘기는 것이 그 안전장치다.
    """
    _, doc = apply_base(tmp_path, local={"enabledPlugins": {}},
                        repo={"enabledPlugins": {"failed@m": True}})
    assert "failed@m" not in doc["enabledPlugins"]


def test_apply_base_status_stays_ok_when_a_section_is_skipped(tmp_path):
    """최상위 status는 "이 스크립트가 돌았는가"이고 섹션 skip을 반영하지 않는다.

    반영하게 만들면 두 섹션이 접힌 실행에서 SKILL.md가 "반영할 것이 없다"로 읽고
    **정상 처리된 마켓플레이스 섹션까지 조용히 버린다.** 섹션 사실은
    sections[<섹션>]["status"]에만 있고 소비자는 그것을 따로 읽어야 한다.
    collect_plugins·compare_plugins가 같은 계약을 쓴다.
    """
    result, _ = apply_base(tmp_path,
                           local={"enabledPlugins": {"p@m": True}},
                           repo={"enabledPlugins": {"p@m": True}},
                           installed=str(tmp_path / "none-installed.json"))
    assert result["status"] == "ok"
    assert result["sections"]["enabledPlugins"]["status"] == "skipped"
    assert result["sections"]["extraKnownMarketplaces"]["status"] == "ok"


def test_apply_base_report_matches_the_document_it_staged(tmp_path):
    """보고 세 필드가 비면 SKILL.md가 선택이 반영됐는지 확인할 길이 없다.

    base_keys를 **실제로 쓴 문서와 대조한다** — 따로 만들면 갈리고, 갈려도 증상이 없다.
    셋을 서로 다른 비지 않은 값으로 채워 하나만 하드코딩돼도 드러나게 한다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_stale": ["gone@m"], "keep_local": ["stay@m"]}},
        local={"enabledPlugins": {"gone@m": True, "stay@m": False, "plain@m": True}},
        repo={"enabledPlugins": {"stay@m": True, "plain@m": True}},
        base={"enabledPlugins": {"gone@m": True, "stay@m": True, "plain@m": True}})
    section = result["sections"]["enabledPlugins"]
    assert section["kept_stale"] == ["gone@m"]
    assert section["kept_local"] == ["stay@m"]
    assert section["base_keys"] == sorted(doc["enabledPlugins"])
    assert "gone@m" not in section["base_keys"]
    assert doc["enabledPlugins"]["stay@m"] is True


def test_keep_local_reports_only_what_it_could_apply(tmp_path):
    """kept_local은 **적용한 것**을 보고한다 — 레포에 없는 키에는 걸 값이 없다.

    kept_stale이 요청을 그대로 보고하는 것과 비대칭으로 보이지만 둘 다 "이 실행이
    만든 base 상태"를 말한다: keep_stale은 키가 base에 없든 있든 결과가 "없음"이라
    요청이 곧 결과이고, keep_local은 레포에 값이 없으면 만들 결과 자체가 없다.
    요청을 그대로 보고하면 SKILL.md가 반영되지 않은 선택을 반영됐다고 안내한다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_local": ["ghost@m", "stay@m"]}},
        local={"enabledPlugins": {"stay@m": False}},
        repo={"enabledPlugins": {"stay@m": True}},
        base={"enabledPlugins": {"stay@m": True}})
    assert result["sections"]["enabledPlugins"]["kept_local"] == ["stay@m"]
    assert "ghost@m" not in doc["enabledPlugins"]


def test_apply_base_applies_choices_in_the_marketplace_section_too(tmp_path):
    """세 섹션을 도는 루프인데 두 섹션만 재면 셋째가 조용히 빠져도 통과한다.

    마켓플레이스는 auto·보류 파일 어느 실패로도 skip되지 않는 유일한 섹션이라,
    루프가 좁아지면 **그 섹션만 아무 선택도 반영되지 않는다.**
    """
    result, doc = apply_base(
        tmp_path,
        choices={"extraKnownMarketplaces": {"keep_stale": ["gone"]}},
        local={"extraKnownMarketplaces": {"gone": GH, "stay": GH}},
        repo={"extraKnownMarketplaces": {"stay": GH}},
        base={"extraKnownMarketplaces": {"gone": GH, "stay": GH}})
    assert result["sections"]["extraKnownMarketplaces"]["kept_stale"] == ["gone"]
    assert "gone" not in doc["extraKnownMarketplaces"]
    # 섹션 전체가 죽으면 위 단정이 공허해진다 — 살아남은 키가 있어야 한다.
    assert "stay" in doc["extraKnownMarketplaces"]


def test_apply_base_sorts_the_reported_base_keys(tmp_path):
    """정렬을 잃으면 보고가 삽입 순서를 따라가 diff가 실행마다 흔들린다.

    keep_local이 nb **뒤에** 덧붙이므로 삽입 순서를 정렬 역순으로 만들 수 있다 —
    zzz@m은 next_base가 먼저 얹고(aaa@m은 로컬에 없어 전진하지 못한다) aaa@m은
    keep_local이 나중에 얹으므로 nb의 삽입 순서는 [zzz@m, aaa@m]이다. 이 fixture는
    해시에 의존하지 않으므로 회귀를 **결정적으로** 잡는다.

    **삽입 순서를 스테이징 파일에서 볼 수는 없다** — ks.dump_json이 sort_keys=True로
    쓰기 때문에 doc은 언제나 정렬돼 있다. 그래서 정렬 회귀가 드러나는 자리는 보고의
    base_keys 하나뿐이고, doc 쪽 단정은 "두 키가 실제로 있다"(fixture가 비지 않았다)를
    맡는다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"keep_local": ["aaa@m"]}},
        local={"enabledPlugins": {"zzz@m": True}},
        repo={"enabledPlugins": {"zzz@m": True, "aaa@m": True}},
        base={"enabledPlugins": {"zzz@m": True}})
    assert doc["enabledPlugins"] == {"zzz@m": True, "aaa@m": True}
    assert result["sections"]["enabledPlugins"]["base_keys"] == ["aaa@m", "zzz@m"]


@pytest.mark.parametrize("args", [[], ["apply-base"], ["apply-base", "a", "b"],
                                  ["apply-base", "a", "b", "c", "d"],
                                  ["bogus", "a", "b", "c"]])
def test_apply_base_cli_rejects_wrong_invocations(tmp_path, args):
    """서브커맨드 이름 검사와 개수 검사가 **둘 다** 필요하다.

    처리되지 않은 IndexError도 종료 코드 1이므로, usage 문구를 함께 확인하지 않으면
    개수 검사 제거를 잡지 못한다. plan 서브커맨드가 같은 모양의 테스트를 갖는다.
    """
    proc = run_script(tmp_path, plan_script(), *args)
    assert proc.returncode == 1
    assert "사용:" in proc.stderr


def test_apply_base_cli_skips_when_the_choices_json_is_not_an_object(tmp_path):
    """read_choices의 ValueError가 흡수되지 않으면 restore 흐름이 traceback으로 선다.

    "형제 셋과 같은 except 튜플"이라는 주석이 지키는 것이 이 항목이다 —
    10.3의 "종료 코드는 0이다, 그래야 안내가 보인다"가 여기서 깨진다.

    **격리된 HOME에 settings.json을 넣는다.** 없으면 read_local_sections가 먼저
    LocalConfigUnavailable로 접혀 status가 어차피 skipped가 되고, 그러면 이 단정은
    read_choices와 무관하게 참이 된다. 사유가 **선택 결과 파일을 가리키는지**까지
    확인해야 그 구별이 선다.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    choices_path = tmp_path / "choices.json"
    choices_path.write_text("[]", encoding="utf-8")
    repo_dir = write_repo(tmp_path, {})
    proc = run_script(tmp_path, plan_script(), "apply-base",
                      os.path.join(repo_dir, pc.BACKUP_RELPATH),
                      str(tmp_path / "staging"), str(choices_path))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "skipped"
    assert str(choices_path) in json.loads(proc.stdout)["reason"]


def test_apply_base_cli_writes_the_staging_file(tmp_path):
    """main()의 인자 배선을 **성공 경로로** 한 번 실행한다 (형제 plan_mcp와 같은 가드).

    거부 갈래만 재면 배선이 무가드로 남는다. backup_path와 staging_dir이 뒤바뀌면
    os.makedirs가 레포의 plugins.json 자리에 디렉토리를 만들려다 FileExistsError로
    접혀 {"status": "skipped"} + **종료 코드 0**이 된다 — SKILL.md는 그것을 정상으로
    읽고 base는 전혀 전진하지 않는다. 이 함수가 .tmp 규칙에서 스스로를 제외하면서까지
    막으려던 바로 그 실패 모양이다.

    격리 HOME에 settings.json과 installed_plugins.json을 함께 넣는다. 하나라도 빠지면
    이 테스트는 조용히 통과하는 것이 아니라 **즉시 실패한다** — settings.json이 없으면
    LocalConfigUnavailable로 최상위가 skipped가 되어 status 단정에서, installed_plugins.json이
    없으면 섹션이 접혀 스테이징 문서가 비어 문서 단정에서 걸린다(둘 다 실측). 위험한 것은
    그때 단정을 `== {}`로 약화하는 것이다 — **그 약화된 형태**가 배선과 무관하게 참이 된다.
    """
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"p@m": True}}), encoding="utf-8")
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {}}), encoding="utf-8")
    choices_path = tmp_path / "choices.json"
    choices_path.write_text(json.dumps(EMPTY_CHOICES), encoding="utf-8")
    repo_dir = write_repo(tmp_path, {"enabledPlugins": {"p@m": True}})
    staging = str(tmp_path / "staging")
    proc = run_script(tmp_path, plan_script(), "apply-base",
                      os.path.join(repo_dir, pc.BACKUP_RELPATH), staging,
                      str(choices_path))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "ok"
    assert staged_doc(staging)["enabledPlugins"] == {"p@m": True}


def test_skipped_section_keeps_the_previous_base_in_the_staged_document(tmp_path):
    """7.5 — 판정하지 못한 섹션을 {}로 덮으면 그 섹션의 이력이 통째로 사라진다.

    다음 백업이 그 섹션 전체를 "로컬 신규"로 읽어 타 기기 항목까지 되살리거나 지운다.
    collect_plugins가 같은 처방을 갖는다. 이전 base에 **비지 않은 값**을 넣어야
    "빈 base를 그대로 통과시킨 것"과 구별된다.
    """
    result, doc = apply_base(tmp_path,
                             local={"enabledPlugins": {"p@m": True}},
                             repo={"enabledPlugins": {"p@m": True}},
                             base={"enabledPlugins": {"kept@m": True}},
                             installed=str(tmp_path / "none-installed.json"))
    assert result["sections"]["enabledPlugins"]["status"] == "skipped"
    assert doc["enabledPlugins"] == {"kept@m": True}


def test_this_runs_decline_takes_effect_on_the_base_immediately(tmp_path):
    """6.4·5.3 — 훅에 **이번 실행의** 보류 상태를 넘겨야 declined 키가 base에서 빠진다.

    이전 상태를 넘기면 H4가 아직 걸리지 않아 그 키가 base로 전진하고, 다음 실행에서야
    보류로 판정되어 얼어붙은 base가 남는다. 로컬과 레포의 마스킹 결과가 **같아야**
    next_base가 전진을 시도하므로(그래야 이 단정이 공허하지 않다) 옵션 키 집합을 맞춘다.

    레포 값에 **평문**을 넣는다. SENTINEL을 넣으면 마스킹이 항등이 되어 원본과 마스킹된
    값의 지문이 같아지고, value_held를 **정규화 없이** 손으로 조립하는 회귀가 이 단정에
    드러나지 않는다 — H4의 지문은 마스킹된 레포 값으로 계산되므로, 평문을 그대로 hold에
    넘기면 지문이 어긋나 보류가 통째로 비고 이 키가 base로 전진한다.
    """
    _, doc = apply_base(
        tmp_path,
        choices={"pluginConfigs": {"declined": ["delta@m"]}},
        local={"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}},
        repo={"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-plain"}}}})
    assert "delta@m" not in doc["pluginConfigs"]


def test_keep_local_writes_the_masked_repo_value_into_the_base(tmp_path):
    """6.1 — keep_local이 얹는 값도 마스킹 훅을 거친다.

    거치지 않으면 base에 평문이 남고, 다음 비교가 **마스킹된 로컬과 평문 base**를
    견주게 되어 사라지지 않는 차이가 생긴다. enabledPlugins로 재면 그 섹션의 정규화가
    항등이라 이 회귀가 드러날 자리가 없으므로 pluginConfigs로 잰다.

    로컬의 option 키 집합을 레포와 어긋나게 두어 next_base가 스스로 전진하지 못하게
    한다 — 그래야 doc에 남은 값이 keep_local이 얹은 것임이 확실해진다.
    """
    _, doc = apply_base(
        tmp_path,
        choices={"pluginConfigs": {"keep_local": ["delta@m"]}},
        local={"pluginConfigs": {"delta@m": {"options": {"other": "x"}}}},
        repo={"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}})
    assert doc["pluginConfigs"]["delta@m"] == {"options": {"apiKey": pc.SENTINEL}}


def test_local_only_entries_do_not_enter_the_base(tmp_path):
    """10.4 — next_base의 세 번째 인자가 **레포**여야 하는 이유.

    로컬을 넘기면 모든 키가 자기 자신과 같아 base가 로컬 전체로 전진한다. 아직 레포에
    올라가지 않은 이 기기의 항목이 "합의된 이력"이 되고, 다음 백업이 그것을 케이스 4
    (타 기기 삭제)로 읽어 사용자에게 되묻는다.
    """
    _, doc = apply_base(tmp_path,
                        local={"enabledPlugins": {"mine@m": True, "shared@m": True}},
                        repo={"enabledPlugins": {"shared@m": True}})
    assert "mine@m" not in doc["enabledPlugins"]
    assert doc["enabledPlugins"]["shared@m"] is True     # 합의된 키는 전진한다


def test_held_file_carries_the_schema_version(tmp_path):
    """read_held_state의 버전 게이트(claims_newer_schema)가 읽는 필드다.

    빠져도 지금은 read_held_state가 통과하므로 **무증상이다** — 나중에 스키마를 올릴 때
    이 파일만 게이트를 타지 못하고 낡은 형태로 조용히 통과한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    apply_base(tmp_path, choices={"pluginConfigs": {"declined": ["delta@m"]}},
               local={}, repo={"pluginConfigs": {"delta@m": {"options": {}}}},
               held=held_path)
    with open(held_path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["pluginConfigs"] != {}        # 파일이 실제로 내용을 담았다
    assert payload["version"] == pc.HELD_SCHEMA_VERSION


@pytest.mark.parametrize("broken", [["p@m"], "p@m", 7, None])
def test_apply_base_ignores_a_section_whose_choices_are_not_an_object(tmp_path, broken):
    """choice_list가 약속한 "형태가 어긋나도 세우지 않는다"의 나머지 절반.

    원소 타입은 test_apply_base_ignores_unknown_and_non_string_choice_entries가 재지만
    **섹션 값** 자체가 dict가 아닌 갈래는 그 테스트가 닿지 않는다 — SKILL.md가
    {"enabledPlugins": ["p@m"]}처럼 평면 목록을 내보내면 section_choices.get이
    AttributeError로 restore를 세운다.

    정상 섹션의 선택을 함께 넣어 "선택을 통째로 무시한다"와 구별한다.
    **None 갈래만으로는 구별이 서지 않는다** — 검사를 `choices.get(section) or {}`로
    완화해도 None은 그대로 빈 선택이 된다. 리스트·문자열·정수 갈래가 그 회귀를 잡는다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": broken,
                 "extraKnownMarketplaces": {"keep_stale": ["gone"]}},
        local={"enabledPlugins": {"p@m": True},
               "extraKnownMarketplaces": {"gone": GH, "stay": GH}},
        repo={"enabledPlugins": {}, "extraKnownMarketplaces": {"stay": GH}},
        base={"enabledPlugins": {"p@m": True},
              "extraKnownMarketplaces": {"gone": GH, "stay": GH}})
    assert result["sections"]["enabledPlugins"]["kept_stale"] == []
    assert doc["enabledPlugins"] == {"p@m": True}        # 어긋난 섹션의 base는 그대로다
    assert result["sections"]["extraKnownMarketplaces"]["kept_stale"] == ["gone"]
    assert "gone" not in doc["extraKnownMarketplaces"]
    assert "stay" in doc["extraKnownMarketplaces"]


def test_declined_ids_absent_from_the_repo_are_ignored(tmp_path):
    """SKILL.md가 레포에 없는 id를 declined로 보내면 KeyError로 restore가 통째로 선다.

    레포에 있는 항목을 함께 넣어 "declined를 통째로 무시한다"와 구별한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    repo = {"pluginConfigs": {"delta@m": {"options": {"apiKey": "sk-real"}}}}
    apply_base(tmp_path,
               choices={"pluginConfigs": {"declined": ["ghost@m", "delta@m"]}},
               local={}, repo=repo, held=held_path)
    masked = pc.SECTION_NORMALIZE["pluginConfigs"](repo["pluginConfigs"])
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {
            "delta@m": pc.value_fingerprint(masked["delta@m"])}


def test_previous_declined_entries_are_dropped_when_the_repo_loses_the_key(tmp_path):
    """6.4 — 레포에 없는 항목은 정리한다.

    남겨 두면 같은 값이 레포에 되돌아왔을 때 사용자가 다시 고르지 않았는데도 지문이
    매치되어 **조용히 보류로 복귀한다.** 레포에 남아 있는 항목을 함께 두어 "전부
    지운다"와 구별한다 — 그쪽은 지문까지 그대로 옮겨져야 한다.
    """
    held_path = str(tmp_path / "plugins-held.json")
    with open(held_path, "w", encoding="utf-8") as f:
        json.dump({"pluginConfigs": {"gone@m": "0" * 64, "stay@m": "1" * 64},
                   "release": {"enabledPlugins": []}}, f)
    apply_base(tmp_path, local={},
               repo={"pluginConfigs": {"stay@m": {"options": {}}}}, held=held_path)
    with open(held_path, encoding="utf-8") as f:
        assert json.load(f)["pluginConfigs"] == {"stay@m": "1" * 64}


def test_release_does_not_advance_the_base_of_the_other_section(tmp_path):
    """release의 keep_local 동시 적용은 **enabledPlugins 한 섹션의 것이다.**

    두 섹션은 키가 같은 문자열이라, 이 목록이 섹션을 넘어 새면 사용자가 고르지도 않은
    pluginConfigs 항목까지 base가 레포 값으로 전진한다 — 실제 설정 차이가 케이스 8·9
    대신 케이스 7로 착지해 로컬 값이 다음 백업에서 레포를 덮는다. 9.3.7의 섹션 중첩이
    막으려는 위험의 다른 입구다.

    로컬의 option 키 집합을 레포와 어긋나게 두어 next_base가 스스로 전진하지 못하게
    한다 — 그래야 pluginConfigs에 값이 생기는 유일한 경로가 이 누수뿐이다.
    """
    result, doc = apply_base(
        tmp_path,
        choices={"enabledPlugins": {"release": ["p@m"]}},
        local={"enabledPlugins": {"p@m": True},
               "pluginConfigs": {"p@m": {"options": {"other": "x"}}}},
        repo={"enabledPlugins": {"p@m": ["1.0.0"]},
              "pluginConfigs": {"p@m": {"options": {"apiKey": "sk-real"}}}})
    assert doc["enabledPlugins"]["p@m"] == ["1.0.0"]     # 해제 섹션은 전진한다
    assert "p@m" not in doc["pluginConfigs"]             # 다른 섹션은 전진하지 않는다
    assert result["sections"]["pluginConfigs"]["kept_local"] == []
