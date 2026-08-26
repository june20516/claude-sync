#!/usr/bin/env python3
"""로컬 플러그인 상태와 레포 백업의 차이를 섹션별로 보고한다 (읽기 전용).

사용: compare_plugins.py <레포의 plugins.json 경로>

판정은 keyed_sync.diff 하나만 쓴다 — status와 backup이 서로 다른 파서를 갖는 것이
결함 B의 원인이었다(check_status.py는 enabledPlugins의 **키 집합만** 비교했다).

**base는 읽지도 갱신하지도 않는다.** 그래도 보류는 안다 — hold는 plugins-held.json·
installed_plugins.json·로컬/레포 값만 있으면 계산되기 때문이다(spec 6.5). base를 읽지
않으면서 보류를 아는 이 성질이 없으면 6.4의 탈출구가 restore만 조용하게 만들고
/sync-status는 매번 보고한다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import keyed_sync as ks  # noqa: E402
import plugin_config as pc  # noqa: E402


def compare(backup_path, settings_path=None, installed_path=None, held_path=None):
    """{"status": "ok", "sections": {섹션: {...}}}

    diff가 양쪽에 정규화를 적용하므로 로컬 평문과 레포 마스킹이 in_sync로 수렴한다.
    값 보류 키는 세 버킷 어디에도 넣지 않고 종류별 held로만 보고한다 — "backup 시
    추가"는 거짓이고 사용자가 해소할 수도 없다(spec 9.2).

    섹션 skip의 범위는 read_hold_inputs가 정한다. 여기서 다시 정하지 않는 것이
    collect_plugins와 같은 범위를 보장하는 유일한 근거다 — 갈리면 사용자가 backup과
    status에서 서로 다른 상태를 본다.
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    # 훅과 보고 컨텍스트를 **한 번의 (local, repo)** 로 만든다. 따로 부르면 두 입력이
    # 어긋날 수 있고, 그러면 hold가 보류한 키를 held_kinds가 분류하지 못해 섹션이
    # 통째로 skipped가 된다 — 아무것도 잘못되지 않았는데 상태가 사라진다.
    hooks, context = pc.hooks_and_context(local, repo, auto_ids=auto_ids,
                                          held_state=held_state)

    sections = {}
    for section in pc.SECTIONS:
        if section in skipped:
            sections[section] = pc.skipped_section(skipped[section])
            continue
        normalize = hooks[section]["normalize"]
        restorable = hooks[section]["restorable"]
        # 정규화된 레포 값이다. held_kinds의 H4 지문과 restorable의 판정이 둘 다
        # 코어가 본 값과 같아야 한다 — 원본을 넘기면 지문이 어긋나 분류가 실패한다.
        repo_norm = normalize(repo[section])
        out = ks.diff(local[section], repo[section],
                      normalize=normalize, hold=hooks[section]["hold"])
        sections[section] = {
            "status": "ok",
            "only_local": out["only_local"],
            "only_repo": out["only_repo"],
            "changed": out["changed"],
            # "restore 시 설치"가 거짓인 항목을 갈라 낸다 — 이 기기에서는 복원할 수 없다.
            "unrestorable": [k for k in out["only_repo"]
                             if not restorable(k, repo_norm[k])],
            "held": pc.held_kinds(section, out["held"], repo_norm=repo_norm, **context),
            # H3는 행동 보류가 아니라 설치 대상이다. "설치됨"과 "미설치"를 문구가
            # 구별해야 한다 — 아직 설치되지 않은 항목에 "레포 값을 보존합니다"만
            # 말하면 거짓이 된다(spec 8.4).
            "not_installed": [k for k in out["held"] if k not in local[section]],
        }
    return {"status": "ok", "sections": sections}


def main():
    if len(sys.argv) != 2:
        print("사용: compare_plugins.py <레포의 plugins.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = compare(sys.argv[1])
    # collect_plugins·compare_mcp와 같은 튜플을 쓴다. 갈리면 한쪽만 traceback으로 죽는다.
    # ValueError의 출처는 둘이다 — 코어의 normalize 계약 위반(훅이 키 집합을 바꿈)과
    # held_kinds의 분류 불가. 어느 쪽도 status 흐름 전체를 세울 이유가 없다.
    # AutoFlagsUnavailable·HeldStateUnavailable은 여기 없다 — 섹션 단위로 이미 흡수됐다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 비교 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
