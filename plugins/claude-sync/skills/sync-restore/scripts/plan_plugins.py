#!/usr/bin/env python3
"""플러그인 복원 계획 수립과 base 계산. 로컬 상태를 직접 바꾸지 않는다.

사용:
  plan_plugins.py plan <레포의 plugins.json 경로>
    복원 계획 JSON을 stdout에 낸다 (섹션별 버킷 11개 + 실행 보조).

CLI 실행과 비밀 값 입력은 SKILL.md의 대화 흐름이 맡는다 — 비밀이 스크립트 인자에
남지 않게 하려는 것과, 9.3.4의 세 선택지가 대화형 확인이어야 하는 것이 같은 이유다.

**계획이 판정의 단일 진입점이다.** SKILL.md가 레포 파일을 직접 파싱하면 "파서 두 벌"이
되살아나므로 등록 인자·설정 키 목록·의존 관계·복원 불가 사유를 전부 여기 싣는다.
"""
import json
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import keyed_sync as ks  # noqa: E402
import plugin_config as pc  # noqa: E402
import sync_state as ss  # noqa: E402

# 설치 대상이 되는 버킷. 값 보류만인 키(H3)는 add로 들어오므로 여기 포함된다 —
# **설치는 한다.** 행동 보류 키는 코어가 action_held 버킷에만 넣으므로 자동으로 빠진다.
INSTALL_BUCKETS = ("add", "needs_secret")

# 등록 후보가 되는 버킷. to_register와 skipped_always_known이 **같은 집합**을 훑어야
# 한다 — 후자는 전자가 always-known으로 걸러 낸 나머지를 보고하는 자리라, 두 열거가
# 갈리면 등록도 보고도 되지 않는 항목이 생긴다. needs_secret을 넣는 것은 **방어다**:
# route_new는 secret_keys(value)가 비지 않을 때만 그 버킷에 넣는데 이 섹션의 훅은
# _no_secrets(SECTION_SECRET_KEYS)라 오늘은 **항상** 빈다. 그래서 지금은 어느 쪽을
# 써도 결과가 같고, 증상이 없는 채로 그 섹션에 되물을 키가 생기는 날 조용히 갈린다.
REGISTER_BUCKETS = ("add", "needs_secret")


def _plan_sections(local, repo, base, hooks, skipped):
    """섹션별 restore_plan. skipped 섹션은 계획을 내지 않는다."""
    out = {}
    for section in pc.SECTIONS:
        if section in skipped:
            out[section] = pc.skipped_section(skipped[section])
            continue
        plan = ks.restore_plan(
            local[section], repo[section],
            None if base is None else base.get(section, {}),
            normalize=hooks[section]["normalize"], hold=hooks[section]["hold"],
            restorable=hooks[section]["restorable"],
            secret_keys=hooks[section]["secret_keys"])
        plan["status"] = "ok"
        out[section] = plan
    return out


def _install_dependencies(install):
    """설치 키 → 먼저 등록해야 할 마켓플레이스 이름 (9.3.2).

    등록이 실패한 마켓플레이스의 플러그인은 설치를 시도하지 않는다 — 시도하면 CLI가
    모호한 문구로 실패해 거짓 실패를 양산한다. always-known 다섯은 등록 단계가 애초에
    없으므로 의존을 걸지 않는다(걸면 설치가 영영 차단된다).

    **marketplace_of가 None인 갈래는 오늘 도달할 수 없다** — install ⊆ restorable이고
    _plugin_restorable은 marketplace_of(key)가 None이면 거짓을 돌려주므로 그런 키는
    unrestorable로 빠져 install에 들어오지 않는다. 그래도 거르는 이유는 빠졌을 때의
    실패 모양이다: None은 ALWAYS_KNOWN에 없으므로 그대로 통과해 {"키": null}이 실리고,
    SKILL.md는 존재하지 않는 등록 단계를 기다리며 그 플러그인을 영영 차단한다 —
    조용하다. **도달 가능한 경로가 있다는 뜻으로 읽지 말 것.**
    """
    out = {}
    for key in install:
        marketplace = pc.marketplace_of(key)
        if marketplace is not None and marketplace not in pc.ALWAYS_KNOWN:
            out[key] = marketplace
    return out


def build_plan(backup_path, settings_path=None, installed_path=None, held_path=None,
               base_dir=ss.BASE_DIR):
    """복원 계획.

    **평문 비밀이 실리지 않는 근거는 "값이 전부 정규화된다"가 아니다.** sections는 코어가
    키 목록만 담아 돌려주므로(restore_plan) 값이 실리는 자리는 셋뿐이다 —
    marketplace_add[].arg(마스킹된 레포 값에서 뽑은 source 문자열), config_keys(값이
    아니라 물어야 할 option 키 **이름**), repo_values/local_values(enabledPlugins 전용 —
    도메인상 비밀이 없는 섹션이다). 그 셋을 전부 마스킹 훅에 통과시키는 것은 근거를
    구조로 바꾸기 위해서다: enabledPlugins의 정규화가 오늘 항등(_identity)이라는 사실에
    기대면, 그 섹션에 마스킹이 도입되는 순간 훅을 우회하는 자리 하나만 조용히 남는다.

    **최상위 status는 섹션 skip을 반영하지 않는다(의도).** 그 값은 "계획 수립을
    수행했는가"다 — 접힌 섹션이 있어도 나머지 섹션의 계획은 유효하고, 최상위를 skipped로
    접으면 마켓플레이스 등록처럼 멀쩡히 낼 수 있는 단계까지 함께 버려진다(9.3.6의 부분
    skip이 전체 skip으로 바뀐다). 그 대가로 **restore에서는 반대 방향이 위험하다**:
    installed_plugins.json 판정 불가로 두 섹션이 접힌 실행의 출력은
    {"status": "ok", "install": [], "disable_after_install": [], "config_keys": {}}이라
    소비자가 최상위만 읽으면 "복원할 것이 없습니다"로 보고하고 **조용히 아무것도
    복원하지 않는다.** 섹션 단위 사실은 sections[<섹션>]["status"]에만 있고, 소비자는
    그것을 **반드시 따로 읽어야 한다.**
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=held_state)
    sections = _plan_sections(local, repo, base, hooks, skipped)

    masked = {section: hooks[section]["normalize"](repo[section])
              for section in pc.SECTIONS}
    # 로컬 값도 **같은 훅**을 통과시킨다. compare_plugins.changed_detail이 양쪽을 둘 다
    # 정규화하는 것과 같은 규약이다 — 원본을 실으면 그 섹션에 마스킹이 도입될 때
    # 로컬 값만 마스킹 계층 전체를 우회하고, 예외도 빈 결과도 나지 않는다(6.1).
    local_masked = hooks["enabledPlugins"]["normalize"](local["enabledPlugins"])
    plugins = sections["enabledPlugins"]
    markets = sections["extraKnownMarketplaces"]
    configs = sections["pluginConfigs"]

    # 1단계 — 등록. always-known 다섯은 건너뛴다(등록이 무의미하거나 반드시 실패한다).
    to_register = [name for bucket in REGISTER_BUCKETS
                   for name in markets.get(bucket, [])
                   if name not in pc.ALWAYS_KNOWN]
    marketplace_add = [
        {"name": name,
         "arg": pc.marketplace_arg(masked["extraKnownMarketplaces"][name]),
         "reserved": name in pc.RESERVED_MARKETPLACE_NAMES}
        for name in to_register]

    # 2단계 — 설치. 3단계 — 값 맞추기. 부재는 여기 오지 않는다(레포에 있는 키만 본다).
    install = [k for bucket in INSTALL_BUCKETS for k in plugins.get(bucket, [])]
    install += [k for bucket in INSTALL_BUCKETS for k in configs.get(bucket, [])
                if k not in install]
    install = sorted(install)
    # **install의 절반은 "설치 직후"가 아니다.** enabledPlugins 경로의 키는 정의상 로컬에
    # 없으므로 설치 직후의 값 true가 맞지만, pluginConfigs 경로의 키는 이미 로컬에 설치돼
    # 있을 수 있다 — 그 섹션의 route_new는 "그 섹션에" 레포 전용인 키를 훑을 뿐 플러그인
    # 자체의 설치 여부와 무관하기 때문이다. 그래서 로컬에 값이 있으면 **그 값**을 쓰고,
    # 없을 때만 설치 직후의 true로 떨어진다. 상수 true를 넣으면 value_command가 지키라고
    # 받는 규칙("현재 상태와 다를 때만 낸다")을 유일한 호출부가 우회하고, 이미 꺼진
    # 플러그인에 disable이 나가 exit 1의 거짓 실패가 된다(enable/disable은 멱등이 아니다).
    disable_after_install = [
        k for k in install
        if k in masked["enabledPlugins"]
        and pc.value_command(local["enabledPlugins"].get(k, True),
                             masked["enabledPlugins"][k]) == "disable"]

    # 값을 맞춰야 하는 세 갈래에 양쪽 값을 실어 준다 — 케이스 8·9(repo_ahead·
    # both_changed)의 선택 뒤, 8.4의 값 보류 문구("레포 값을 보존합니다"), 그리고 설치
    # 직후의 3단계. SKILL.md가 value_command와 같은 규칙을 손으로 재구현하지 않게 하려는
    # 것이다 — 재구현하면 멱등이 아닌 명령을 같은 상태에 내어 거짓 실패를 양산한다.
    decided = sorted({k for bucket in ("repo_ahead", "both_changed", "value_held")
                      for k in plugins.get(bucket, [])} | set(install))

    return {
        "status": "ok",
        "sections": sections,
        "marketplace_add": marketplace_add,
        "skipped_always_known": sorted(
            name for bucket in REGISTER_BUCKETS for name in markets.get(bucket, [])
            if name in pc.ALWAYS_KNOWN),
        "install": install,
        "disable_after_install": disable_after_install,
        # 코어가 needs_secret으로 라우팅할 때 부른 것과 **같은 훅**으로 키 목록을 만든다.
        # 자유 함수(SECTION_SECRET_KEYS)를 따로 부르면 라우팅과 보고가 갈릴 수 있고,
        # 갈려도 증상이 없다 — 사용자는 되물어야 할 키를 하나 덜 받을 뿐이다.
        "config_keys": {k: hooks["pluginConfigs"]["secret_keys"](
            masked["pluginConfigs"][k])
            for k in configs.get("needs_secret", [])},
        "repo_values": {k: masked["enabledPlugins"][k] for k in decided
                        if k in masked["enabledPlugins"]},
        "local_values": {k: local_masked[k] for k in decided if k in local_masked},
        "depends_on": _install_dependencies(install),
        # 훅 묶음의 reason을 쓴다 — 자유 함수 unrestorable_reason에 repo를 따로 넘기면
        # 판정(restorable)과 사유가 **다른 repo**를 볼 수 있고 양쪽 다 무증상이다
        # (Task 6 quality review I2). build_hooks가 둘에 같은 repo를 닫아 준다.
        "unrestorable_reasons": {
            k: hooks[section]["reason"](k, masked[section].get(k))
            for section in pc.SECTIONS
            for k in sections[section].get("unrestorable", [])},
    }


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    else:
        print("사용: plan_plugins.py plan <레포의 plugins.json 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = runner()
    # collect_plugins·compare_plugins와 같은 튜플을 쓴다. 갈리면 한쪽만 traceback으로 죽는다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 복원 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
