#!/usr/bin/env python3
"""플러그인 복원 계획 수립과 base 계산. 로컬 상태를 직접 바꾸지 않는다.

사용:
  plan_plugins.py plan <레포의 plugins.json 경로>
    복원 계획 JSON을 stdout에 낸다 (섹션별 버킷 11개 + 실행 보조).

  plan_plugins.py apply-base <레포의 plugins.json 경로> <스테이징 디렉토리>
                             <선택 결과 JSON 경로>
    복원 후 로컬을 기준으로 다음 base를 계산해 스테이징에 쓰고, 이 기기의 보류
    선택(plugins-held.json)을 갱신한다.

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
# 이 버킷들이 내는 것은 "레포가 원하는 상태에 도달하려면 손대야 할 id" 전체다.
# 그것을 2단계와 4단계로 가르는 것은 아래 build_plan의 설치 집합 하나다(9.3.1).
INSTALL_BUCKETS = ("add", "needs_secret")

# 등록 후보가 되는 버킷. to_register와 skipped_always_known이 **같은 집합**을 훑어야
# 한다 — 후자는 전자가 always-known으로 걸러 낸 나머지를 보고하는 자리라, 두 열거가
# 갈리면 등록도 보고도 되지 않는 항목이 생긴다. needs_secret을 넣는 것은 **방어다**:
# route_new는 secret_keys(value)가 비지 않을 때만 그 버킷에 넣는데 이 섹션의 훅은
# _no_secrets(SECTION_SECRET_KEYS)라 오늘은 **항상** 빈다. 그래서 지금은 어느 쪽을
# 써도 결과가 같고, 증상이 없는 채로 그 섹션에 되물을 키가 생기는 날 조용히 갈린다.
REGISTER_BUCKETS = ("add", "needs_secret")


def _plan_sections(local, repo, base, hooks, skipped, degraded):
    """섹션별 restore_plan. skipped 섹션은 계획을 내지 않는다.

    degraded는 **접지 않은** 섹션에 얹는 "판정 불가" 사유다(with_degraded).
    """
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
        out[section] = pc.with_degraded(plan, degraded.get(section))
    return out


def _install_dependencies(candidates):
    """손댈 id → 먼저 등록해야 할 마켓플레이스 이름 (9.3.2).

    **2단계와 4단계를 모두 받는다.** 근거는 명령의 **형태**다 — 두 단계가 내는 것이
    둘 다 `plugin install <id@marketplace>` 형태라 1단계 등록에 똑같이 의존한다.
    (9.3.2가 규정하는 것은 "2단계가 실패한 id는 3·4단계를 건너뛴다"이고, 그것은 2단계
    자체가 없는 skipped_already_installed에는 도달하지 않는다 — 여기 근거가 아니다.)
    2단계로 좁히면 등록에 실패한 마켓플레이스로 4단계 명령이 나가 거짓 실패를 양산한다 —
    이 함수가 막으려는 바로 그 실패다.

    등록이 실패한 마켓플레이스의 플러그인은 설치를 시도하지 않는다 — 시도하면 CLI가
    모호한 문구로 실패해 거짓 실패를 양산한다. always-known 다섯은 등록 단계가 애초에
    없으므로 의존을 걸지 않는다(걸면 설치가 영영 차단된다).

    **marketplace_of가 None인 갈래는 오늘 도달할 수 없다** — candidates ⊆ restorable이고
    _plugin_restorable은 marketplace_of(key)가 None이면 거짓을 돌려주므로 그런 키는
    unrestorable로 빠져 candidates에 들어오지 않는다. 그래도 거르는 이유는 빠졌을 때의
    실패 모양이다: None은 ALWAYS_KNOWN에 없으므로 그대로 통과해 {"키": null}이 실리고,
    SKILL.md는 존재하지 않는 등록 단계를 기다리며 그 플러그인을 영영 차단한다 —
    조용하다. **도달 가능한 경로가 있다는 뜻으로 읽지 말 것.**
    """
    out = {}
    for key in candidates:
        marketplace = pc.marketplace_of(key)
        if marketplace is not None and marketplace not in pc.ALWAYS_KNOWN:
            out[key] = marketplace
    return out


def build_plan(backup_path, settings_path=None, installed_path=None, held_path=None,
               base_dir=ss.BASE_DIR):
    """복원 계획.

    **평문 비밀이 실리지 않는 근거는 "값이 전부 정규화된다"가 아니다.** sections는 코어가
    키 목록만 담아 돌려주므로(restore_plan) 값이 실리는 자리는 **넷**이다 —
    marketplace_add[].arg(마스킹된 레포 값에서 뽑은 source 문자열), config_keys(값이
    아니라 물어야 할 option 키 **이름**), repo_values/local_values(enabledPlugins 전용 —
    도메인상 비밀이 없는 섹션이다), 그리고 unrestorable_reasons(아래). 그 넷을 전부
    마스킹 훅에 통과시키는 것은 근거를 구조로 바꾸기 위해서다: enabledPlugins의 정규화가
    오늘 항등(_identity)이라는 사실에 기대면, 그 섹션에 마스킹이 도입되는 순간 훅을
    우회하는 자리 하나만 조용히 남는다.

    **넷째는 값이 문자열 안에 들어가 있어 세는 눈에 걸리지 않는다.** unrestorable_reasons의
    마켓플레이스 갈래는 레포 값의 source.source를 사유 문장에 **보간한다**
    (plugin_config.unrestorable_reason의 (a)·(b) 갈래). 레포에
    {"m": {"source": {"source": "X"}}}가 있으면 사유가 "'X' 출처로는 …"이 된다. 오늘
    안전한 근거는 둘이다 — 그 값도 masked[section]을 거치고(위와 같은 훅), 그리고
    extraKnownMarketplaces에는 도메인상 비밀이 없다. 나머지 두 섹션의 갈래는 값이 아니라
    **키**에서 뽑은 마켓플레이스 이름만 넣으므로 값이 실리지 않는다.
    **10.2의 사유 갈래를 늘릴 때 이 자리를 다시 셀 것** — pluginConfigs는 마스킹 대상
    섹션이라(_redact_configs) 그 갈래가 값을 보간하기 시작하면 성질이 달라진다.

    **최상위 status는 섹션 skip을 반영하지 않는다(의도).** 그 값은 "계획 수립을
    수행했는가"다 — 접힌 섹션이 있어도 나머지 섹션의 계획은 유효하고, 최상위를 skipped로
    접으면 마켓플레이스 등록처럼 멀쩡히 낼 수 있는 단계까지 함께 버려진다(9.3.6의 부분
    skip이 전체 skip으로 바뀐다). 그 대가로 **restore에서는 반대 방향이 위험하다**:
    installed_plugins.json 판정 불가로 두 섹션이 접힌 실행의 출력은
    {"status": "ok", "install": [], "skipped_already_installed": [],
     "disable_after_install": [], "config_keys": {}}이라
    소비자가 최상위만 읽으면 "복원할 것이 없습니다"로 보고하고 **조용히 아무것도
    복원하지 않는다.** 섹션 단위 사실은 sections[<섹션>]["status"]에만 있고, 소비자는
    그것을 **반드시 따로 읽어야 한다.**

    **2단계와 4단계가 갈리는 자리가 여기다**(9.3.1). 두 단계는 다른 명령이고 대상도
    다르다 — 2단계는 `plugin install <id>`, 4단계는 `install --config k=v`다. 이미 설치된
    플러그인에 2단계를 내면 **exit 0이지만**(브리프 1-b #2 · 2026-08-29 스모크 2장 —
    실측) **그 id의 값이 `true`로 덮인다.** 로컬이 `false`인 id를 말없이 켜고, 객체 값이면
    평탄화해 없앤다. 3단계가 되돌려 주지도 않는다 — 그 목록은 **계획 시점의** 로컬 값으로
    정해지는데, 그때 이미 레포와 같았던 id는 애초에 거기 실리지 않기 때문이다.
    (*초판은 이 자리에 "exit 1로 죽어 거짓 실패가 된다"라고 적었다. 결론은 같고 사유가
    틀렸다 — 그 문장은 브리프 1-b #2가 저장소 안에서 이미 반증하고 있었다.*)
    가르는 기준은 **설치 집합 하나**이고 로컬 섹션 문서가 아니다 —
    enabledPlugins의 키 부재는 미설치가 아니라 매니페스트 defaultEnabled에 위임하는
    상태이므로(value_command가 같은 사실을 반대편에서 쓴다) 그것으로 가르면 이미 설치된
    플러그인이 2단계로 간다.
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    auto_ids, installed_ids, held_state, skipped, degraded = pc.read_hold_inputs(
        installed_path, held_path)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=held_state)
    sections = _plan_sections(local, repo, base, hooks, skipped, degraded)

    masked = {section: hooks[section]["normalize"](repo[section])
              for section in pc.SECTIONS}
    # 로컬 값도 **같은 훅**을 통과시킨다. compare_plugins.changed_detail이 양쪽을 둘 다
    # 정규화하는 것과 같은 규약이다 — 원본을 실으면 그 섹션에 마스킹이 도입될 때
    # 로컬 값만 마스킹 계층 전체를 우회하고, 예외도 빈 결과도 나지 않는다(6.1).
    # **싣는 자리와 비교하는 자리가 같은 값을 봐야 한다.** local_values의 페이로드만
    # 훅에 통과시키고 disable 판정은 원본으로 비교하면, 한쪽만 마스킹된 두 값이
    # value_command에 들어가 없어야 할 enable/disable이 **CLI 명령으로** 나간다.
    # 그래서 이 파일에는 **정규화를 거치지 않은 로컬 값을 꺼내 쓰는 자리가 없다** —
    # local을 그대로 넘기는 곳은 코어와 훅뿐이고, 그쪽은 스스로 정규화한다.
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

    # 손대야 할 id 전체. 부재는 여기 오지 않는다(레포에 있는 키만 본다).
    # **이 목록을 한 번만 조립한다** — 아래 다섯 필드가 전부 여기서 파생된다. 두 곳에서
    # 만들면 갈리고, 갈려도 증상이 없다.
    candidates = [k for bucket in INSTALL_BUCKETS for k in plugins.get(bucket, [])]
    candidates += [k for bucket in INSTALL_BUCKETS for k in configs.get(bucket, [])
                   if k not in candidates]
    candidates = sorted(candidates)
    # 2단계 — `plugin install <id>`. 4단계 — `install --config k=v`(설정 값은 config_keys).
    # **가르는 기준은 설치 집합 하나다**(위 docstring). 이미 설치된 id에 2단계를 내면
    # exit 0으로 조용히 그 id의 값이 `true`로 덮인다.
    install = [k for k in candidates if k not in installed_ids]
    # 1단계의 skipped_always_known과 같은 결의 **제외 목록**이다 — 어느 단계에서 왜
    # 빠졌는지를 보고에 남겨야 SKILL.md가 "아무 일도 일어나지 않았다"와 구별할 수 있다.
    # 이 id들에 남은 것은 3단계(disable_after_install)와 4단계(config_keys)뿐이다.
    # **둘 다에 없으면 낼 명령이 없다. 그런데 그 이유가 세 갈래고, 사용자 문구가 서로
    # 다르다** — "이미 같은 상태"로 뭉뚱그리면 (b)에서 실측으로 거짓이 된다:
    #   (a) enabledPlugins 기여이고 레포 값이 **불리언**인데 현재 상태와 같다
    #       (value_command가 None을 냈다). 여기서 "현재 상태"는 로컬 키가 없을 때
    #       아래 local_masked.get(k, True)로 **가정한** 값이다 — 매니페스트
    #       defaultEnabled가 true라는 가정이고, false인 플러그인에서는 참이 아니다.
    #   (b) enabledPlugins 기여인데 레포 값이 **확장 포맷**이라 밀 CLI가 없다(H3).
    #       value_command는 레포 값이 불리언이 아니면 무조건 None이므로 여기도 명령이
    #       없지만, **상태가 같다는 뜻이 아니다** — 현재 상태는 알려진 바가 없다.
    #       H3 보류 키는 add 버킷으로 들어오므로(위 INSTALL_BUCKETS) 도달 가능하다.
    #       문구는 8.4의 "레포 값을 보존합니다"다.
    #   (c) pluginConfigs 기여인데 되물을 option 키가 없다(_config_secret_keys는 options만
    #       본다). 이쪽도 레포와 완전히 같아졌다는 보장은 없다.
    # **갈래는 repo_values로 판별한다** — 값이 불리언이면 (a), 비불리언이면 (b), 키가
    # 아예 없으면 (c)다(repo_values는 레포 enabledPlugins에 있는 키만 싣는다). 한 id가
    # 두 섹션에 함께 기여하면 갈래도 겹친다. 여기서 미리 갈라 싣지 않는 것은 같은
    # 분할을 두 곳에서 만들지 않기 위해서다.
    # **"키 부재"는 (c)의 충분조건일 뿐 필요조건이 아니다** — enabledPlugins가 in_sync라
    # 기여하지 않고 pluginConfigs만 기여하는 id는 불리언으로 실려 (a)로 보인다. 그래도
    # 문구는 갈리지 않는다: _config_secret_keys가 option 키 전부를 되물을 목록으로
    # 돌려주므로, add 버킷에 남는 pluginConfigs 항목은 정의상 options가 비어 실질이 없다.
    # 세 갈래 모두 **bare install은 대안이 아니다.** exit 0이라 죽지는 않지만(실측) 값을
    # `true`로 덮어써 (a)에서 방금 "현재 상태와 같다"고 판정한 그 상태를 깨고 (b)의 확장
    # 값을 평탄화한다 — 조용한 상태 파괴다.
    skipped_already_installed = [k for k in candidates if k in installed_ids]
    # **3단계의 기준은 두 목록 전부(candidates)다.** 이미 설치된 id도 값 맞추기 대상이다 —
    # 로컬 enabledPlugins에 값이 없고(매니페스트 기본값에 위임) 레포가 false이면 그
    # 플러그인은 켜진 채 남으므로 disable이 필요하다. 2단계로 좁히면 그 명령이 사라진다.
    # **candidates의 절반은 "설치 직후"가 아니다.** enabledPlugins 경로의 키는 정의상
    # 로컬 섹션 문서에 없지만, pluginConfigs 경로의 키는 이미 로컬에 값이 있을 수 있다 —
    # 그 섹션의 route_new는 "그 섹션에" 레포 전용인 키를 훑을 뿐 플러그인 자체의 설치
    # 여부와 무관하기 때문이다.
    # 그래서 로컬에 값이 있으면 **그 값**을 쓰고, 없을 때만 설치 직후의 true로 떨어진다. 상수
    # true를 넣으면 value_command가 지키라고 받는 규칙("현재 상태와 다를 때만 낸다")을
    # 유일한 호출부가 우회하고, 이미 꺼진 플러그인에 disable이 나가 exit 1의 거짓 실패가
    # 된다(enable/disable은 멱등이 아니다).
    disable_after_install = [
        k for k in candidates
        if k in masked["enabledPlugins"]
        and pc.value_command(local_masked.get(k, True),
                             masked["enabledPlugins"][k]) == "disable"]

    # 값을 맞춰야 하는 세 갈래에 양쪽 값을 실어 준다 — 케이스 8·9(repo_ahead·
    # both_changed)의 선택 뒤, 8.4의 값 보류 문구("레포 값을 보존합니다"), 그리고 설치
    # 직후의 3단계. SKILL.md가 value_command와 같은 규칙을 손으로 재구현하지 않게 하려는
    # 것이다 — 재구현하면 멱등이 아닌 명령을 같은 상태에 내어 거짓 실패를 양산한다.
    decided = sorted({k for bucket in ("repo_ahead", "both_changed", "value_held")
                      for k in plugins.get(bucket, [])} | set(candidates))

    return {
        "status": "ok",
        "sections": sections,
        "marketplace_add": marketplace_add,
        "skipped_always_known": sorted(
            name for bucket in REGISTER_BUCKETS for name in markets.get(bucket, [])
            if name in pc.ALWAYS_KNOWN),
        # 2단계 (9.3.1)
        "install": install,
        # 2단계에서 제외된 id — 이미 이 기기에 설치되어 있다.
        "skipped_already_installed": skipped_already_installed,
        # 3단계 (9.3.1)
        "disable_after_install": disable_after_install,
        # **4단계 (9.3.1)** — `install --config k=v`의 대상과 물어야 할 키 이름이다.
        # 코어가 needs_secret으로 라우팅할 때 부른 것과 **같은 훅**으로 키 목록을 만든다.
        # 자유 함수(SECTION_SECRET_KEYS)를 따로 부르면 라우팅과 보고가 갈릴 수 있고,
        # 갈려도 증상이 없다 — 사용자는 되물어야 할 키를 하나 덜 받을 뿐이다.
        # **설치 집합으로 좁히지 않는다.** 2단계로 새로 깔린 id도, 이미 설치돼 있어
        # 4단계만 남은 id도 똑같이 설정을 채워야 한다 — 한쪽으로 좁히면 다른 쪽 id의
        # 설정이 어디에서도 채워지지 않는다.
        "config_keys": {k: hooks["pluginConfigs"]["secret_keys"](
            masked["pluginConfigs"][k])
            for k in configs.get("needs_secret", [])},
        "repo_values": {k: masked["enabledPlugins"][k] for k in decided
                        if k in masked["enabledPlugins"]},
        "local_values": {k: local_masked[k] for k in decided if k in local_masked},
        "depends_on": _install_dependencies(candidates),
        # 훅 묶음의 reason을 쓴다 — 자유 함수 unrestorable_reason에 repo를 따로 넘기면
        # 판정(restorable)과 사유가 **다른 repo**를 볼 수 있고 양쪽 다 무증상이다
        # (Task 6 quality review I2). build_hooks가 둘에 같은 repo를 닫아 준다.
        "unrestorable_reasons": {
            k: hooks[section]["reason"](k, masked[section].get(k))
            for section in pc.SECTIONS
            for k in sections[section].get("unrestorable", [])},
    }


def _next_base_sections(local, repo, base, hooks, skipped, degraded, choices,
                        next_held):
    """섹션별 다음 base와 그 보고. _plan_sections와 **같은 층위의 짝**이다.

    앞의 여섯 인자는 _plan_sections와 같고, 뒤의 둘만 base 경로에만 있는 입력이다 —
    사용자의 선택(choices)과 **이번 실행의** 보류 상태(next_held).

    **value_held를 스스로 계산해 next_base에 넘긴다.** merge 경로와 달리 여기서는
    아무도 대신 계산해 주지 않는다. 넘기지 않으면 보류 키가 base에 얼어붙어, 보류가
    풀리는 순간 케이스 3(삭제)이 난다.

    **레포 매핑 전체를 세 번째 인자로 넘긴다.** next_base의 계약은 "local과 merged가
    같은 값을 갖는 키만 전진"이므로, 그 교집합이 곧 "실제로 복원에 성공한 항목"이 된다 —
    실패했거나 사용자가 건너뛴 항목은 로컬에 없으니 자동으로 빠진다(10.4).
    여기에 "복원을 시도한 목록"을 넘기면 그 안전장치가 사라진다.

    **④의 keep_local 동시 적용은 enabledPlugins 한 섹션에만 건다.** 두 섹션은 키가 같은
    문자열이라 이 목록이 섹션을 넘어 새면 사용자가 고르지도 않은 pluginConfigs 항목까지
    base가 레포 값으로 전진한다 — 실제 설정 차이가 케이스 8·9 대신 케이스 7로 착지해
    다음 백업에서 로컬 값이 레포를 덮는다. 9.3.7의 섹션 중첩이 막으려는 위험의 다른
    입구이고, 선택 JSON의 중첩만으로는 막히지 않는다(release는 그 JSON이 아니라 보류
    파일에서도 온다). **불필요한 특수 케이스로 읽고 지우지 말 것.**

    **②와 ③이 같은 키에 겹치면 ③이 이긴다** — ③이 뒤에 돌기 때문이다. 임의의 순서가
    아니라 ③이 `key in masked` 가드를 갖는 데서 나온다: ③은 레포에 값이 있을 때만
    적용되고, 그때 ②(케이스 4·5 = "레포가 그 키를 잃었다")는 이미 모순 입력이다.
    순서를 뒤집으면 그 모순 입력이 정당한 선택을 조용히 덮는다.

    **kept_stale은 요청을, kept_local은 적용한 것을 보고한다.** 비대칭으로 보이지만 둘
    다 "이 실행이 만든 base 상태"를 말한다 — keep_stale은 그 키가 base에 있었든 없었든
    결과가 "없음"이라 요청이 곧 결과이고, keep_local은 레포에 값이 없으면 얹을 값 자체가
    없다. 그때도 요청을 그대로 보고하면 SKILL.md가 반영되지 않은 선택을 반영됐다고
    안내한다. **예외는 바로 위의 모순 입력 하나다** — 같은 키가 ②③에 함께 오면 ③이
    이겨 그 키가 nb에 남는데도 kept_stale에 실린다. 같은 보고의 base_keys가 그 키를
    담으므로 소비자가 대조할 수는 있다.

    **base_keys는 형제 plan_mcp의 base_names와 이름이 다르다(의도).** 두 필드의 모양은
    같다(정렬된 문자열 리스트). 다른 것은 층위다 — 그쪽은 **문서 최상위**의 서버 이름
    목록이고 이쪽은 **sections[<섹션>] 아래**의 plugin@marketplace 키 목록이다. 같은
    restore 흐름이 두 출력을 함께 읽으므로, 이름이 같으면 층위가 다른 두 목록을 한
    종류로 렌더링하게 된다.
    """
    previous_base = base or {}
    doc, report = {}, {}
    for section in pc.SECTIONS:
        if section in skipped:
            # 판정하지 못한 섹션은 이전 base를 그대로 통과시킨다 — {}로 덮으면 다음
            # 백업이 그 섹션 전체를 "로컬 신규"로 읽는다(collect_plugins와 같은 처방).
            doc[section] = previous_base.get(section, {})
            report[section] = pc.skipped_section(skipped[section])
            continue
        normalize = hooks[section]["normalize"]
        masked = normalize(repo[section])
        # 손으로 조립하지 않는다 — hold는 정규화된 입력을 받고 (local, repo) 순서가
        # 뒤집히면 예외도 빈 결과도 없이 판정이 반대로 선다(Task 6 quality review I1).
        value_held = pc.value_held_for(section, hooks, local[section], repo[section])
        nb = ks.next_base(local[section],
                          None if base is None else base.get(section, {}),
                          repo[section],
                          normalize=normalize, value_held=value_held)
        stale = pc.choice_list(choices, section, "keep_stale")
        for key in stale:
            nb.pop(key, None)
        keep_local = list(pc.choice_list(choices, section, "keep_local"))
        if section == "enabledPlugins":
            # ④ — H3 탈출구의 동시 적용. **이 섹션에만 건다**(위 docstring).
            keep_local += [key for key in next_held["release"]["enabledPlugins"]
                           if key not in keep_local]
        kept_local = []
        for key in keep_local:
            if key in masked:
                nb[key] = masked[key]
                kept_local.append(key)
        doc[section] = nb
        report[section] = pc.with_degraded(
            {"status": "ok", "kept_stale": stale, "kept_local": kept_local,
             "base_keys": sorted(nb)}, degraded.get(section))
    return doc, report


def apply_base(backup_path, staging_dir, choices, settings_path=None, installed_path=None,
               held_path=None, base_dir=ss.BASE_DIR):
    """복원 후 로컬 기준으로 다음 base를 계산하고 override 셋을 적용해 스테이징에 쓴다.

    ① next_base(복원 후 로컬, 이전 base, 레포 값)  — 정규화는 코어가 한다
    ② keep_stale(케이스 4·5의 "유지")   → base에서 키 삭제  (그 이력은 잊는다)
    ③ keep_local(케이스 8·9의 "로컬 유지") → base[k] ← 레포 값 (그 이력은 잊는다)
    ④ release(H3 탈출구) → ②③과 별개로 보류를 풀고 **동시에 ③을 적용한다**
       (**enabledPlugins 한 섹션에만 건다** — 근거는 _next_base_sections)

    ④가 ③을 함께 걸지 않으면 base에 그 키가 없어(5.3) 다음 백업이 케이스 9로 떨어지고
    레포 값이 그대로 남는다 — 약속과 반대다. ③을 함께 걸면 same(repo, base)이므로
    케이스 7(로컬만 변경) → 로컬 값 push → 레포 값이 불리언 → H3 자연 해제로 이어진다.

    **섹션 루프와 그 보고는 _next_base_sections가 맡는다** — build_plan이 _plan_sections에
    위임하는 것과 같은 층위다. 이 몸통에 남는 것은 읽기 → 계산 → 쓰기 세 국면뿐이다.

    **이 함수는 .tmp+rename 규칙에서 제외된다.** 그 규칙은 "레포 쓰기가 성공한 뒤에
    rename"인데 apply-base에는 **레포 쓰기가 없다** — 그대로 적용하면 rename 트리거가
    영영 오지 않아 게이트가 언제나 거짓이 되고 restore 경로의 base가 전혀 전진하지
    않는다. 여기서는 **파일 존재가 곧 "계산 성공"**이다(9.3.7).

    **최상위 status는 섹션 skip을 반영하지 않는다** — build_plan·collect_plugins·
    compare_plugins와 같은 계약이다. 접힌 섹션이 있어도 나머지 섹션의 base는 유효하고,
    최상위를 skipped로 접으면 소비자가 "반영할 것이 없다"로 읽어 정상 처리된 섹션까지
    함께 버린다. 섹션 사실은 sections[<섹션>]["status"]에만 있다.

    **파일 두 개를 쓰는 순서가 계약이다.** 스테이징(base) 먼저, 보류 파일 나중.
    반대로 하면 release가 기록된 뒤 base 쓰기가 실패했을 때 H3가 풀린 채로 base에 키가
    없어 다음 백업이 케이스 9로 떨어진다. 이 순서에서는 보류 파일 쓰기가 실패해도
    "다시 묻는다"에 그친다. **이 순서를 재는 fixture는 스테이징 디렉토리 자리에 일반
    파일을 두는 것이다** — os.makedirs가 그 자리에서 OSError로 죽으므로, 순서가 뒤집혀
    있으면 그 시점에 보류 파일이 이미 쓰여 있다.
    """
    local = pc.read_local_sections(settings_path)
    repo = pc.load_backup(backup_path)
    base = pc.parse_base(ss.read_base(pc.BACKUP_RELPATH, base_dir=base_dir))
    # installed_ids는 쓰지 않는다 — base 계산은 "이 기기에 설치돼 있는가"를 묻지 않는다.
    # 다음 base는 복원 후 로컬 값과 레포 값의 일치로만 전진한다(_next_base_sections).
    auto_ids, _installed_ids, held_state, skipped, degraded = pc.read_hold_inputs(
        installed_path, held_path)

    # **이번 실행의** 보류 상태로 훅을 만든다. 이것이 실제로 결과를 가르는 곳은 H4다 —
    # 이번에 declined된 pluginConfigs 키가 곧바로 value_held가 되어 base에서 빠진다.
    # 이전 상태를 넘기면 그 키가 base로 전진했다가 다음 실행에서야 보류로 판정되어
    # 얼어붙은 base가 남는다(5.3).
    # release 쪽은 이 선택으로 결과가 갈리지 않는다 — 아래 ③이 그 키에 레포 값을 다시
    # 얹으므로 H3가 걸렸든 풀렸든 nb의 최종 값이 같다. 그래도 같은 상태를 넘기는 것은
    # 훅과 아래 루프가 **한 보류 상태**를 보게 하기 위해서다.
    next_held = pc.next_held_state(held_state, pc.normalized_sections(repo), choices)
    hooks = pc.build_hooks(local, repo, auto_ids=auto_ids, held_state=next_held)

    doc, report = _next_base_sections(local, repo, base, hooks, skipped, degraded,
                                      choices, next_held)

    os.makedirs(staging_dir, exist_ok=True)
    pc.dump_backup(doc, os.path.join(staging_dir, pc.BACKUP_RELPATH))
    # 보류 파일을 읽지 못했다면 쓰지 않는다 — 빈 상태로 덮으면 사용자의 선택이 조용히
    # 사라진다. 그 경우 SKILL.md가 파일을 지울 경로를 안내한다(6.4).
    # **게이트는 한 섹션에 걸리는데 파일은 두 섹션의 상태를 담는다.** pluginConfigs만
    # 접힌 실행에서는 enabledPlugins가 정상 처리되므로 release 선택이 base에는 반영되고
    # (④) 파일에는 남지 않아, 다음 백업에서 H3가 다시 걸려 **그 해제가 1회용이 된다.**
    # 그래도 이 게이트가 옳다 — 빈 상태로 덮으면 declined 전부가 조용히 사라진다.
    if "pluginConfigs" not in skipped:
        pc.write_held_state(next_held, held_path)
    return {"status": "ok", "sections": report}


def read_choices(path):
    """섹션으로 중첩된 선택 결과. **비밀 값은 담기지 않는다.**

    사용자가 입력한 pluginConfigs 값은 여기 실리지 않고 `install --config`로 곧바로
    전달된다 — 담으면 임시 파일에 평문 비밀이 남는다(9.3.7).
    """
    with open(path, "rb") as f:
        data = json.loads(f.read())
    if not isinstance(data, dict):
        raise ValueError("선택 결과 JSON의 최상위가 객체가 아님: %s" % path)
    return data


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "plan":
        runner = lambda: build_plan(args[1])  # noqa: E731
    elif len(args) == 4 and args[0] == "apply-base":
        runner = lambda: apply_base(args[1], args[2], read_choices(args[3]))  # noqa: E731
    else:
        print("사용: plan_plugins.py plan <레포의 plugins.json 경로>", file=sys.stderr)
        print("      plan_plugins.py apply-base <레포의 plugins.json 경로>"
              " <스테이징 디렉토리> <선택 결과 JSON 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = runner()
    # collect_plugins·compare_plugins와 같은 튜플을 쓴다. 갈리면 한쪽만 traceback으로 죽는다.
    # ValueError를 잡는 이유 둘: 코어(keyed_sync)의 normalize 계약 위반 — 훅이 키 집합을
    # 바꾼 경우 — 과, 선택 결과 JSON이 객체가 아니거나 깨진 경우(read_choices,
    # json.JSONDecodeError도 ValueError의 하위다). 어느 쪽도 restore 흐름 전체를
    # traceback으로 세우지 않는다(10.3).
    # BrokenBackupSyntax = 레포 문서의 구문 깨짐 → **플러그인 단계 전체 skip**(9.3.6).
    # 접지 않고 "항목 0개"로 읽으면 로컬의 모든 항목이 local_stale로 떨어져, 파일 하나가
    # 깨졌을 뿐인데 "이 기기의 플러그인을 전부 지웁시다"가 최상위 ok와 함께 나간다.
    except (pc.LocalConfigUnavailable, pc.UnknownBackupSchema,
            pc.BrokenBackupSyntax, OSError, ValueError) as e:
        out = {"status": "skipped", "reason": str(e)}
        print("플러그인 복원 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
