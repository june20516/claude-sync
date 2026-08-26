"""세 스크립트(collect_plugins / compare_plugins / plan_plugins)의 계약 테스트.

실제 ~/.claude와 ~/.claude/.sync-state는 절대 건드리지 않는다 —
인프로세스 호출은 경로 인자로, CLI 호출은 env HOME= 으로 격리한다.
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

from marks import requires_permission_bits  # noqa: E402
import plugin_config as pc  # noqa: E402
import collect_plugins  # noqa: E402

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
