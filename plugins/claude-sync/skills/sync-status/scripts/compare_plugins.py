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

# 설치 구별(not_installed)을 실을 수 있는 섹션 — **키가 플러그인 id인 둘뿐이다.**
# extraKnownMarketplaces의 키는 마켓플레이스 이름이라 installed_ids와 이름 공간이 달라,
# 실으면 등록만 안 된 마켓플레이스가 전부 "미설치 플러그인"으로 보고된다.
# 이 둘이 AutoFlagsUnavailable의 skip 범위와 **같은 짝**인 것은 우연이 아니다(3.4):
# 설치 집합을 못 읽은 실행에서는 이 둘이 함께 접히므로, 이 필드가 실리는 곳에서는
# installed_ids가 언제나 실제로 읽힌 값이다.
INSTALL_KEYED_SECTIONS = ("enabledPlugins", "pluginConfigs")


def compare(backup_path, settings_path=None, installed_path=None, held_path=None):
    """{"status": "ok", "sections": {섹션: {...}}}

    diff가 양쪽에 정규화를 적용하므로 로컬 평문과 레포 마스킹이 in_sync로 수렴한다.
    값 보류 키는 세 버킷 어디에도 넣지 않고 종류별 held로만 보고한다 — "backup 시
    추가"는 거짓이고 사용자가 해소할 수도 없다(spec 9.2).

    섹션 skip의 범위는 read_hold_inputs가 정한다. 여기서 다시 정하지 않는 것이
    collect_plugins와 같은 범위를 보장하는 유일한 근거다 — 갈리면 사용자가 backup과
    status에서 서로 다른 상태를 본다.

    **최상위 status는 섹션 skip을 반영하지 않는다(의도).** 그 값은 "비교를 수행했는가"다
    — 읽기 전용이므로 collect의 근거("이 스크립트가 레포를 갱신했는가")는 여기 적용되지
    않고, 같은 결론에 다른 근거가 선다. 두 섹션이 접힌 실행에서도 ok가 나오므로
    소비자는 최상위만 보고 "동일"이라고 말하면 안 된다 — 섹션 단위 사실은
    sections[<섹션>]["status"]에만 있고, 그것을 **반드시 따로 읽어야 한다.**

    **"세 섹션이 전부"는 도달할 수 없다.** skipped를 만드는 곳은 read_hold_inputs
    하나뿐이고 거기 들어갈 수 있는 키는 enabledPlugins·pluginConfigs 둘뿐이다 —
    extraKnownMarketplaces는 auto와도 보류 파일과도 무관해 어느 실패 경로로도 접히지
    않는다(spec 3.4). 이 전제를 틀리게 읽으면 소비자 쪽에 **절대 실행되지 않는**
    "모든 섹션이 접혔습니다" 분기가 생긴다.
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    auto_ids, installed_ids, held_state, skipped = pc.read_hold_inputs(
        installed_path, held_path)
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
        local_norm = normalize(local[section])
        out = ks.diff(local[section], repo[section],
                      normalize=normalize, hold=hooks[section]["hold"])
        entry = {
            "status": "ok",
            "only_local": out["only_local"],
            "only_repo": out["only_repo"],
            "changed": out["changed"],
            # 키 목록만으로는 켬→끔인지 그 반대인지, 레포 값이 확장 포맷인지를 말할 수
            # 없다. 소비자가 그 문구를 만들려고 settings.json·plugins.json을 다시 읽으면
            # status 경로에 두 번째 파서가 생긴다 — 그것이 결함 B의 형태다(spec 9.2).
            # **out["changed"] 하나에서 파생시킨다** — 두 곳에서 만들면 갈리고 무증상이다.
            # 값은 반드시 **정규화된** 쪽이다. 원본을 실으면 로컬 평문 option 값이 그대로
            # 보고에 올라 마스킹 계층 전체를 우회한다(6.1).
            "changed_detail": {k: {"local": local_norm[k], "repo": repo_norm[k]}
                               for k in out["changed"]},
            # "restore 시 설치"가 거짓인 항목을 갈라 낸다 — 이 기기에서는 복원할 수 없다.
            "unrestorable": [k for k in out["only_repo"]
                             if not restorable(k, repo_norm[k])],
            "held": pc.held_kinds(section, out["held"], repo_norm=repo_norm, **context),
            # **값 보류 키 중 로컬 섹션 문서에 값이 없는 것.** H3만이 아니라 out["held"]
            # 전부를 훑는다 — "레포 값을 보존합니다"가 거짓이 되는 조건이 종류와
            # 무관하게 정확히 이것이기 때문이다(spec 8.4).
            # **이 필드는 "미설치"가 아니다.** 두 사실이 갈리기 때문이다 — auto 의존성은
            # installed_plugins.json에 있으므로 **설치되어 있으면서** settings.json에는
            # 없다(3.4). 설치 여부는 아래 not_installed가 따로 말한다.
            "absent_locally": [k for k in out["held"] if k not in local[section]],
        }
        # **"설치됨"과 "미설치"를 갈라 말한다**(9.2). absent_locally의 부분집합이며,
        # 나머지(= 설치되어 있는데 로컬 섹션 문서에 값이 없는 항목)가 "레포 값을
        # 보존합니다"를 참으로 말할 수 있는 쪽이다. 두 목록을 따로 싣지 않는 것은 같은
        # 분할을 두 곳에서 만들지 않기 위해서다 — 갈리면 증상이 없다.
        # **보류 키 전체가 아니라 absent_locally에서 뽑는다.** 로컬 섹션 문서에 값이 있는
        # 보류 키의 문구는 설치 여부가 아니라 값 차이를 말하고(8.4의 셋째 행), "값은
        # 있는데 설치는 안 된" 상태는 CLI가 만들지 않는다 — uninstall이 키를 지우기
        # 때문이다(9.3.3). 넓히면 그 문구가 "미설치"로 뒤집힌다.
        if section in INSTALL_KEYED_SECTIONS:
            entry["not_installed"] = [k for k in entry["absent_locally"]
                                      if k not in installed_ids]
        sections[section] = entry
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
        # 모양이 pc.skipped_section과 같지만 그것을 쓰지 않는다 — 층위가 다르다. 이쪽은
        # sections 자체가 없는 **문서 전체**의 갈래이고, 같은 리터럴이 plugin_config를
        # import하지 않는 mcp 계열 셋에도 있다. 소비자가 읽는 자리도 다르다.
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 비교 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
