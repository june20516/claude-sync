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
    """6.4 — 없음은 정상이고 깨짐은 한 섹션만 skip이다."""
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    out = collect(tmp_path, local={"enabledPlugins": {"p@m": True}}, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["enabledPlugins"]["status"] == "ok"


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

    installed_plugins.json에 있다는 것 자체가 이 기기에 설치되어 있다는 뜻인데(3.4),
    그 파일에서 auto 플래그만 읽는 이 스크립트는 설치 여부를 알 수 없다. 아래가 그
    반례다 — dep@m은 **설치되어 있으면서** settings.json에는 없다. 이 조합에
    "미설치"라는 이름을 붙이면 보고가 실측으로 거짓이 된다.
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
    """6.4 — 없음은 정상이고 깨짐은 한 섹션만 skip이다."""
    held = tmp_path / "plugins-held.json"
    held.write_text("{not json", encoding="utf-8")
    out = compare(tmp_path, local={"enabledPlugins": {"p@m": True}}, held=str(held))
    assert out["sections"]["pluginConfigs"]["status"] == "skipped"
    assert out["sections"]["pluginConfigs"]["reason"]
    assert out["sections"]["enabledPlugins"]["status"] == "ok"


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
    """
    base = {"enabledPlugins": {"ahead@m": True, "both@m": True, "mine@m": True}}
    local = {"enabledPlugins": {"ahead@m": True, "both@m": ["2.0.0"], "mine@m": False,
                                "held@m": True, "solo@m": True}}
    repo = {"enabledPlugins": {"ahead@m": False, "both@m": False, "mine@m": True,
                               "held@m": ["1.0.0"], "new@m": True},
            "extraKnownMarketplaces": {"m": GH}}
    out = build_plan(tmp_path, local=local, repo=repo, base=base)
    section = out["sections"]["enabledPlugins"]
    assert section["repo_ahead"] == ["ahead@m"]        # 케이스 8
    assert section["both_changed"] == ["both@m"]       # 케이스 9
    assert section["value_held"] == ["held@m"]         # H3
    assert section["local_ahead"] == ["mine@m"]        # 케이스 7 — 판정 대상이 아니다
    assert section["local_only"] == ["solo@m"]         # 케이스 1 — 판정 대상이 아니다
    assert out["install"] == ["new@m"]
    assert out["repo_values"] == {"ahead@m": False, "both@m": False,
                                  "held@m": ["1.0.0"], "new@m": True}
    # new@m은 로컬에 없다 — 없는 키를 넣으면 SKILL.md가 "값이 바뀐다"고 잘못 말한다.
    assert out["local_values"] == {"ahead@m": True, "both@m": ["2.0.0"], "held@m": True}


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
    """14.1 — 부재는 꺼짐이 아니다 (1-c C4)."""
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
    # 레포에 마켓플레이스 m이 **있어야** 이 단정이 skip을 잰다. 없으면 p@m이 skip과
    # 무관하게 unrestorable로 떨어져 install이 어차피 빈다.
    assert out["install"] == []
    # 부분 skip이 전체 skip으로 조용히 바뀌지 않았음을 함께 본다 (9.3.6).
    assert [m["name"] for m in out["marketplace_add"]] == ["m"]


def plan_script():
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                        "skills", "sync-restore", "scripts",
                                        "plan_plugins.py"))


def test_plan_cli_rejects_unknown_mode():
    """호출부가 잘못한 경우에만 0이 아닌 종료 코드를 쓴다."""
    proc = subprocess.run([sys.executable, plan_script(), "bogus"],
                          capture_output=True, text=True)
    assert proc.returncode == 1


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
