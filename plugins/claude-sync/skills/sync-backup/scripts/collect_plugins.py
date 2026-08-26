#!/usr/bin/env python3
"""로컬 플러그인 상태를 레포와 **섹션별** 키 단위 3-way 병합한다.

사용: collect_plugins.py <레포 경로> <스테이징 디렉토리>

`claude plugin list --json`을 호출하지 않고 stdin도 받지 않는다 — 값의 원천은
settings.json(세 섹션의 값)과 installed_plugins.json(auto 플래그) 둘뿐이다(spec 3장).
세 번째로 읽는 로컬 파일이 하나 더 있다: ~/.claude/.sync-state/plugins-held.json.
그것은 값의 원천이 아니라 **이 기기의 보류 선택**이고, 부재가 정상 상태다(6.4).

base는 이 스크립트가 쓰지 않는다. 커밋 전에 실행되기 때문이다. next_base를 스테이징
디렉토리에 plugins.json으로 써 두고, 레포가 실제로 그 내용을 갖게 된 뒤 SKILL.md가
update_base.py로 옮긴다. **레포를 source_root로 넘기면** base ← 레포 파일 바이트가 되어
타 기기가 추가·변경한 항목이 base에 실리고, 다음 백업이 그것을 "이 기기가 삭제했다"로
오독해 다른 기기의 플러그인을 경고 없이 지운다.

**전제: 호출부가 실행마다 스테이징 디렉토리를 한 번 비운다**(SKILL.md의 rm -rf).
collect_mcp.py와 같은 디렉토리를 공유하므로 그 rm -rf는 두 수집 단계보다 앞에서
딱 한 번 실행되어야 한다(spec 7.4).
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


def collect(repo_path, staging_dir, settings_path=None, installed_path=None,
            held_path=None, base_dir=ss.BASE_DIR):
    """세 섹션을 병합해 레포 파일과 스테이징 파일에 쓰고 보고 dict를 반환한다.

    순서가 곧 안전 성질이다(spec 9.1.1):
      1 로컬 읽기 → 2 레포 읽기 → 3 이력 읽기 → 4 **hold 계산** → 5 섹션별 merge
      → 6 정합성 → 보고 생성 → 7 스테이징(.tmp) → 8 레포 → rename

    4단계가 2단계보다 뒤인 것이 중요하다. **실측으로 걸리는 것은 H2의 레포 쪽 방어다** —
    build_hooks·held_context가 닫는 directory_marketplaces가 레포에 이미 실린 directory
    출처를 보는데, 레포를 읽기 전에 부르면 그 집합이 비어 이 기기에 등록할 소스가 없는
    항목이 케이스 3(삭제)으로 레포에서 지워진다. restorable·reason도 여기서 레포를
    닫으므로 같은 이유로 뒤에 있어야 한다(collect가 그 둘을 쓰지 않을 뿐 계약은 같다).

    H1·H3·H4는 **코어가 호출 시점에 레포를 넘기므로** 순서를 뒤집어도 살아남는다 —
    그래서 이 뒤집기가 조용하다. 네 종류 중 셋이 멀쩡히 동작하고 H2 하나만 무증상으로
    죽으므로, 순서를 지키는 것 말고는 드러날 자리가 없다.

    **보고를 쓰기보다 먼저 만든다.** held_kinds가 분류 불가에 ValueError를 던지는데,
    레포를 이미 고친 뒤라면 그 예외가 부르는 skipped의 표준 문구("레포 파일은 손대지
    않았다")가 거짓이 된다.

    스테이징은 <rel>.tmp로 쓰고 **레포 쓰기가 성공한 뒤에** rename한다 — 최종 파일의
    존재가 곧 "레포까지 반영됨"을 뜻해야 SKILL.md의 base 갱신 게이트가 참이 된다.

    **최상위 status는 섹션 skip을 반영하지 않는다(의도).** 그 값은 "이 스크립트가 레포를
    갱신했는가"이고, 섹션 하나가 접혀도 나머지 둘은 갱신됐으므로 ok다. 섹션 단위 사실은
    sections[<섹션>]["status"]에만 있다 — SKILL.md는 그 둘을 다른 분기로 읽어야 한다.
    최상위를 섹션 skip에 따라 바꾸면 전체 skip(레포를 손대지 않았다)과 부분 skip(레포를
    갱신했다)이 같은 값으로 접혀, 정반대의 두 상태에 같은 안내가 나간다.
    """
    local = pc.read_local_sections(settings_path)
    repo_file = os.path.join(repo_path, pc.BACKUP_RELPATH)
    repo = pc.load_backup(repo_file)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))

    auto_ids, held_state, skipped = pc.read_hold_inputs(installed_path, held_path)
    # 훅과 보고 컨텍스트를 **한 번의 (local, repo)** 로 만든다. 따로 부르면 두 입력이
    # 같다는 보장이 이 줄의 규율뿐이고, 어긋나면 held_kinds가 분류에 실패해 섹션이
    # 통째로 skipped가 된다.
    hooks, context = pc.hooks_and_context(local, repo, auto_ids=auto_ids,
                                          held_state=held_state)

    previous_base = base or {}
    merged_doc, base_doc, sections = {}, {}, {}
    for section in pc.SECTIONS:
        if section in skipped:
            # 7.5 — base도 레포도 pass-through. 레포 쪽을 빠뜨리면 4.3을 문언대로 읽어
            # {}를 쓰게 되고, 타 기기의 항목이 status:"ok"인 채로 전량 소실된다.
            merged_doc[section] = repo[section]
            base_doc[section] = previous_base.get(section, {})
            sections[section] = pc.skipped_section(skipped[section])
            continue
        normalize = hooks[section]["normalize"]
        result = ks.merge(local[section], repo[section],
                          None if base is None else base.get(section, {}),
                          normalize=normalize, hold=hooks[section]["hold"])
        merged = result["merged"]
        merged_doc[section] = merged
        base_doc[section] = result["next_base"]
        sections[section] = {
            "status": "ok",
            # 케이스 9는 레포 값이 남고 케이스 5는 아예 빠진다 — 처방이 다르므로 가른다.
            "conflicts": {
                "repo_kept": [k for k in result["conflicts"] if k in merged],
                "repo_absent": [k for k in result["conflicts"] if k not in merged],
            },
            "deleted": result["deleted"],
            "local_stale": result["local_stale"],
            # 케이스 2(타 기기 추가)와 케이스 8(타 기기 변경)은 안내 문구가 다르다.
            # 가르는 축은 **로컬에 그 키가 있는가**다 — present는 이 기기에도 있어
            # 사용자가 값을 고르지만, absent는 restore가 그냥 설치한다.
            "repo_ahead": {
                "present": [k for k in result["repo_ahead"] if k in local[section]],
                "absent": [k for k in result["repo_ahead"] if k not in local[section]],
            },
            "held": pc.held_kinds(section, result["held"],
                                  repo_norm=normalize(repo[section]), **context),
        }

    out = {
        "status": "ok",
        "orphaned": pc.orphaned(merged_doc["enabledPlugins"],
                                merged_doc["extraKnownMarketplaces"]),
        "sections": sections,
    }

    os.makedirs(staging_dir, exist_ok=True)
    staged = os.path.join(staging_dir, pc.BACKUP_RELPATH)
    tmp = staged + ".tmp"
    pc.dump_backup(base_doc, tmp)
    pc.dump_backup(merged_doc, repo_file)
    try:
        os.replace(tmp, staged)
    except OSError as e:
        # 레포는 이미 갱신됐다. skipped로 접으면 "레포를 손대지 않았다"가 거짓이 된다.
        # 키 이름을 reason과 가른다 — reason은 SKILL.md "6단계 skipped 분기"의 필드다.
        out["base_staging"] = "failed"
        out["base_staging_reason"] = (
            "레포는 갱신됐으나 base 스테이징에 실패했다: %s (다음 백업이 복구한다)" % e)
    return out


def main():
    if len(sys.argv) != 3:
        print("사용: collect_plugins.py <레포 경로> <스테이징 디렉토리>", file=sys.stderr)
        sys.exit(1)
    try:
        out = collect(sys.argv[1], sys.argv[2])
    # collect_mcp·compare_plugins·plan_plugins와 같은 튜플을 쓴다. 갈리면 한쪽만
    # traceback으로 죽는다. ValueError의 출처는 셋이다 — 코어의 normalize 계약 위반(훅이
    # 키 집합을 바꿈), held_kinds의 분류 불가, dump_backup의 "섹션이 객체가 아님"(쓰기 전에
    # 던지므로 손상 파일이 레포에 들어가지 않는다). 셋 다 backup 흐름 전체를 세우지 않는다.
    # AutoFlagsUnavailable·HeldStateUnavailable은 여기 없다 — 섹션 단위로 이미 흡수됐다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema, OSError, ValueError) as e:
        # 모양이 pc.skipped_section과 같지만 그것을 쓰지 않는다 — 층위가 다르다. 이쪽은
        # sections 자체가 없는 **문서 전체**의 갈래이고, 같은 리터럴이 plugin_config를
        # import하지 않는 mcp 계열 셋에도 있다. 소비자가 읽는 자리도 다르다.
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 단계 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
