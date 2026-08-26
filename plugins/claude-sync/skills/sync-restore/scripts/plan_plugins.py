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


def build_plan(backup_path, settings_path=None, installed_path=None, held_path=None,
               base_dir=ss.BASE_DIR):
    """복원 계획. 값은 전부 정규화(마스킹)를 거치므로 비밀이 실리지 않는다."""
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=held_state)
    sections = _plan_sections(local, repo, base, hooks, skipped)

    masked = {section: hooks[section]["normalize"](repo[section])
              for section in pc.SECTIONS}
    plugins = sections["enabledPlugins"]
    markets = sections["extraKnownMarketplaces"]
    configs = sections["pluginConfigs"]

    # 1단계 — 등록. always-known 다섯은 건너뛴다(등록이 무의미하거나 반드시 실패한다).
    to_register = [name for name in markets.get("add", []) + markets.get("needs_secret", [])
                   if name not in pc.ALWAYS_KNOWN]
    marketplace_add = [
        {"name": name,
         "arg": pc.marketplace_arg(masked["extraKnownMarketplaces"][name]),
         "reserved": name in pc.RESERVED_MARKETPLACE_NAMES}
        for name in to_register]

    # 2단계 — 설치. 3단계 — 값 맞추기. 설치 직후 값은 true이므로 레포가 false인
    # 항목만 disable 대상이다. 부재는 여기 오지 않는다(레포에 있는 키만 본다).
    install = [k for bucket in INSTALL_BUCKETS for k in plugins.get(bucket, [])]
    install += [k for bucket in INSTALL_BUCKETS for k in configs.get(bucket, [])
                if k not in install]
    install = sorted(install)
    disable_after_install = [
        k for k in install
        if k in masked["enabledPlugins"]
        and pc.value_command(True, masked["enabledPlugins"][k]) == "disable"]

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
            name for name in markets.get("add", []) if name in pc.ALWAYS_KNOWN),
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
        "local_values": {k: local["enabledPlugins"][k] for k in decided
                         if k in local["enabledPlugins"]},
        # 9.3.2 — 등록이 실패한 마켓플레이스의 플러그인은 설치를 시도하지 않는다.
        # 시도하면 CLI가 모호한 문구로 실패해 거짓 실패를 양산한다.
        "depends_on": {k: pc.marketplace_of(k) for k in install
                       if pc.marketplace_of(k) not in pc.ALWAYS_KNOWN
                       and pc.marketplace_of(k) is not None},
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
