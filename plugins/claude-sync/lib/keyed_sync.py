#!/usr/bin/env python3
"""claude-sync의 값 무관 키 단위 3-way 동기화 코어.

MCP 서버와 플러그인이 같은 판정표·인식 계층·예외 클래스를 공유한다.
도메인 지식(인식·마스킹·판정 보류·복원 가능성)은 전부 훅으로 주입된다 — 이 모듈은 값을 모른다.

이 모듈을 복사하지 말 것. 과거 Critical 세 건이 전부 상태 기계에서 나왔고,
복사하면 위험도 복사된다.
"""
import copy
import json

BROKEN = object()   # JSON 구문 오류 센티널. None·0·false와 구별해야 한다


class LocalConfigUnavailable(Exception):
    """로컬 설정을 읽지 못했다.

    "항목 0개"와 반드시 구별해야 한다. 이 예외가 발생하면 삭제 판정을 해서는 안 된다.
    어댑터가 re-export하므로 `except adapter.LocalConfigUnavailable`이 이 클래스를 잡는다.
    """


class UnknownBackupSchema(Exception):
    """레포의 백업 파일이 이 버전이 아는 형식이 아니다.

    상위 버전이 쓴 문서일 수 있으므로 "항목 0개"로 읽어서는 안 된다. 그렇게 읽으면
    merge가 레포를 빈 것으로 보고 이 기기의 로컬만 남긴 결과를 덮어써 상위 버전의
    백업을 파괴한다. 옛 버전이 v2 문서에 저지른 사고와 같은 형태다.
    LocalConfigUnavailable이 로컬 쪽에서 하는 역할을 레포 쪽에서 한다(불변식 2).
    """


def claims_newer_schema(version, schema_version):
    """version이 schema_version보다 높다고 주장하는가.

    float까지 본다. {"version": 3.0}은 파이썬이 아닌 도구(jq, YAML 변환기, 다른 언어의
    v3 writer)가 실제로 만드는 형태다. int만 막고 float를 통과시키면 게이트의 존재
    이유 자체가 무력화된다.
    bool은 제외한다 — True는 int의 인스턴스지만 버전 주장이 아니다.
    문자열("3")은 통과시킨다. 손으로 고친 문서를 막지 않기 위해서다.
    """
    if isinstance(version, bool):
        return False
    return isinstance(version, (int, float)) and version > schema_version


def decode(data):
    """JSON 디코드. 구문이 깨졌으면 BROKEN 센티널."""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return BROKEN


def fingerprint(value):
    """값을 키 정렬 JSON 문자열로 만들어 비교 가능한 형태로 바꾼다.

    어댑터의 디스크 직렬화와 같은 옵션(sort_keys, ensure_ascii=False)을 쓴다 —
    디스크 표현이 같으면 same()도 같다고 판정하도록 맞춘 것이다.
    (들여쓰기·봉투 구조는 공유하지 않으므로 결과 문자열이 파일 내용과 같지는 않다.)
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def same(a, b):
    """값 동등 비교. 키 순서에 무관하다."""
    return fingerprint(a) == fingerprint(b)


# recognize(obj) -> mapping | None
#   parse_base·load_backup·parse_backup 세 함수가 공유하는 훅의 계약이다.
#   알아볼 수 있는 문서면 매핑(비어 있으면 {}), 알아볼 수 없으면 None을 돌려줘야 한다.
#   "유효한데 항목 0개"에 None을 돌려주면 load_backup이 정상 문서를 UnknownBackupSchema로
#   막는다. "알아볼 수 없음"에 {}를 돌려주면 상위 버전이 쓴 백업이 파괴된다.
#   세 함수가 반드시 같은 훅 인스턴스를 받아야 한다 — 갈리면 "이력은 못 믿는데 레포는
#   믿는" 비대칭이 생긴다(spec 4.4).
def parse_base(data, recognize):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None을 반환한다.

    "이력이 비어 있었다"({})와 "이력을 읽을 수 없다"(None)를 반드시 구별해야 한다.
    전자는 삭제·충돌 판정의 근거가 되지만, 후자는 근거가 될 수 없다.
    """
    if data is None:
        return None
    obj = decode(data)
    if obj is BROKEN:
        return None
    return recognize(obj)


def load_backup(path, recognize):
    """레포의 백업 파일을 안전하게 읽는다. 파일이 없으면 {}.

    구문이 깨진 파일은 {}로 degrade한다 — 레포 파일 하나가 깨졌다고 백업 전체를 막지
    않으며, 다음 백업이 그 파일을 정상 내용으로 되돌린다.
    구문은 유효한데 형식을 알아볼 수 없으면 UnknownBackupSchema를 던진다.
    (PermissionError 등 그 외 OSError는 전파한다.)
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}
    obj = decode(raw)
    if obj is BROKEN:
        return {}
    recognized = recognize(obj)
    if recognized is None:
        raise UnknownBackupSchema(
            "%s의 형식을 알아볼 수 없다 — 상위 버전이 쓴 백업일 수 있다" % path
        )
    return recognized


def parse_backup(data, recognize):
    """바이트/문자열에서 매핑을 읽는다(관대한 해석). 디코드·인식 실패는 전부 {}.

    **레포 파일을 읽을 때는 이 함수가 아니라 load_backup을 쓴다** — 알아볼 수 없는
    문서를 "0개"로 읽으면 그 파일을 덮어써 파괴하기 때문이다.
    """
    obj = decode(data)
    if obj is BROKEN:
        return {}
    recognized = recognize(obj)
    return {} if recognized is None else recognized


# hold(local, repo) -> {"value": set[str], "action": set[str]}
#   diff·merge·restore_plan이 공유하는 훅의 계약이다.
#   **정규화된 입력을 받는다** — 코어가 normalize를 적용한 뒤에 부르므로, 훅이 원본
#   값(예: 비밀 평문)을 볼 것이라고 가정하면 안 된다.
#   **좌우 비대칭이다** — 보류 판정이 레포 값을 보는지 로컬 쪽 사실을 보는지가 훅마다
#   다르다(spec 7.3: H3는 레포 값을, H1·H2는 로컬 쪽 사실을 본다). (local, repo) 순서가
#   뒤집히면 예외도 빈 결과도 나지 않고 판정이 조용히 반대로 선다.
#   두 축은 다른 연산이다: value = 레포에 push하지 않는다, action = CLI 명령을 실행하지 않는다.
#   **action 축은 restore_plan만 소비한다** — diff·merge·next_base는 value 축만 본다.
#   행동 보류는 "복원할 때 명령을 실행하지 않는다"는 뜻이라, 레포 내용을 정하는
#   diff·merge·next_base에는 바꿀 판정이 없기 때문이다(의도적 무시, 누락 아님).
def no_hold(local, repo):
    """보류가 없는 도메인을 위한 기본 훅. MCP 어댑터가 쓴다."""
    return {"value": frozenset(), "action": frozenset()}


# normalize(mapping) -> mapping
#   diff·next_base·merge·restore_plan이 공유하는 훅의 계약이다. 값 층위 변환만 허용된다 —
#   키를 추가·제거해서는 안 된다(키 층위 제외는 hold의 몫, spec 5.2).
#   멱등이어야 한다 — next_base는 merge 경로에서 이미 정규화된 local·base를 다시
#   정규화하므로, 비멱등 훅은 호출될 때마다 값이 계속 바뀌어 base가 수렴하지 않는다.
#   **코어는 키 보존만 집행한다**(아래 _normalized가 어긋나면 ValueError). 멱등성은
#   집행하지 않는다 — 코어는 값을 모르므로 두 번 적용해 비교하는 것 외에 확인할 방법이
#   없고, 그 비용을 매 호출에 물릴 이유가 없다. 멱등성은 어댑터 테스트가 책임진다.
def _normalized(mapping, normalize):
    """normalize를 적용하되 키 집합이 보존됐는지 확인한다.

    키 층위 제외는 전부 hold의 몫이다(spec 5.2). normalize가 키를 빼면
    merge가 그것을 "로컬에서 삭제됨"(케이스 3)으로 읽어 레포에서 지운다.
    조용히 통과시키면 이 개정이 없애려던 손실 경로가 그대로 부활한다.
    """
    out = normalize(mapping)
    if set(out) != set(mapping):
        raise ValueError("normalize가 키 집합을 바꿨다 — 키 층위 제외는 hold가 맡는다")
    return out


def diff(local, repo, *, normalize, hold):
    """상태 비교. 비교 직전 양쪽에 normalize를 적용한다.

    비밀 값은 로컬에 평문, 레포에 마스킹된 형태로 저장되므로 원본끼리 비교하면
    비밀을 가진 항목이 영구히 "변경됨"으로 보고된다(미수렴).
    값 보류 키는 세 버킷 어디에도 넣지 않고 held에만 넣는다.
    **hold의 value 축만 쓴다** — 행동 보류(action)는 restore_plan 전용이다(의도적 무시).
    normalize는 값 층위 변환만 허용된다 — 키를 지우면 _normalized가 ValueError를
    던진다. 키 층위 제외(동기화하지 않을 키를 고르는 일)는 hold의 몫이다(spec 5.2).
    """
    local, repo = _normalized(local, normalize), _normalized(repo, normalize)
    value_held = set(hold(local, repo)["value"])
    return {
        "only_local": sorted(set(local) - set(repo) - value_held),
        "only_repo": sorted(set(repo) - set(local) - value_held),
        "changed": sorted(
            name for name in (set(local) & set(repo)) - value_held
            if not same(local[name], repo[name])
        ),
        "held": sorted(value_held),
    }


def _next_base_normalized(local, old, merged, value_held):
    """이미 정규화된 세 매핑으로 다음 base를 만든다. next_base의 본체다.

    merge는 세 인자를 모두 정규화해 넘기므로 공개 next_base를 부르면 정규화가 두 번
    적용된다. 코어는 멱등성을 집행하지 않으므로(spec 5.2) 비멱등 훅에서는 그 이중 적용이
    base를 과전진시킬 수 있다. merge가 이 함수를 직접 불러 그 의존을 없앤다.
    단독 호출자(restore)는 공개 next_base를 쓴다.
    """
    out = {}
    for name in sorted(set(old) | set(merged)):
        if name in value_held:
            continue                                    # 값 보류 → base에서 제거
        if name in merged and name in local and same(merged[name], local[name]):
            out[name] = copy.deepcopy(merged[name])     # 로컬이 동의 → 전진
        elif name not in merged and name not in local:
            continue                                    # 양쪽에서 사라짐 → 제거
        elif name in old:
            out[name] = copy.deepcopy(old[name])        # 동의 안 함 → 이전 base 유지
    return out


def next_base(local, base, merged, *, normalize, value_held=frozenset()):
    """다음 base 매핑. base[key]는 로컬이 그 값에 동의할 때만 전진한다.

    로컬이 동의하지 않은 값(타 기기가 추가·변경한 항목, 충돌 중인 항목)을 base에 기록하면
    다음 백업이 그 차이를 "로컬이 바뀌었다"로 오독해, 타 기기의 항목을 삭제하거나
    타 기기의 변경을 되돌린다.

    **값 보류 키는 base에서 제거한다.** base의 의미는 "이 기기가 마지막으로 동의한 값"인데
    보류 키는 정의상 이 기기가 동의하지 않기로 한 키다. 남기면 보류가 풀리는 순간
    얼어붙은 base로 케이스 3(삭제)이 난다.

    **세 번째 인자(merged)가 무엇인지는 호출 경로마다 다르다.** merge 경로는 병합
    결과를 넘기고, restore 경로(plan_mcp.apply_base)는 레포 매핑 전체를 넘긴다 —
    그때 첫 인자 local은 "복원을 실행한 뒤 다시 읽은 로컬"이다. 이름이 merged인 것은
    merge 경로를 기준으로 붙은 것이고, 계약은 "local과 merged가 같은 값을 갖는 키만
    전진"이므로 두 경로 모두 성립한다 — restore 경로에서는 그 교집합이 곧 "실제로
    복원에 성공한 항목"이 되어, 실패했거나 사용자가 건너뛴 항목은 로컬에 없으니
    자동으로 빠진다. 여기에 "복원을 시도한 목록"을 넘기면 그 안전장치가 사라진다.

    hold 콜러블이 아니라 이미 계산된 집합을 받는다 — hold는 (local, repo)가 필요한데
    이 함수의 인자에는 repo가 없기 때문이다. merge가 한 번 계산해 넘기고,
    단독 호출자(restore)는 스스로 계산해 넘긴다.

    입력(local·base·merged)에 normalize를 내부 적용한다 — restore는 원본 로컬(비밀
    평문)을 그대로 넘기게 되므로, 호출부가 아니라 이 함수가 정규화를 책임져야
    same() 비교가 성립한다. merge 경로에서는 local·base가 이미 정규화된 채로 들어와
    normalize가 두 번 적용되므로, normalize는 반드시 멱등이어야 한다(spec 5.2 계약 —
    코어는 키 보존만 집행하고 멱등성은 집행하지 않는다).

    반환값은 입력의 어떤 nested 객체도 공유하지 않는다(deepcopy).
    """
    return _next_base_normalized(
        _normalized(local, normalize),
        _normalized(base, normalize) if base else {},
        _normalized(merged, normalize),
        value_held,
    )


def merge(local, repo, base, *, normalize, hold):
    """키 단위 3-way 병합 (판정표 케이스 1~10).

    base가 None이면 삭제 없이 합집합으로 degrade한다 — "타 기기 추가"와 "내 삭제"를
    구별할 수 없기 때문이다. 단 **양쪽에 있는 키는 로컬 값이 레포를 덮는다.**

    반환하는 next_base는 키 단위로 전진한다. 그래서 호출부가 conflicts 유무로 base 갱신을
    전역으로 게이트할 필요가 없다 — 항목 하나가 충돌 중이어도 나머지 base는 계속 전진한다.
    **전역 게이트를 되살리지 말 것.**

    conflicts에는 케이스 5(로컬 수정 vs 리모트 삭제)와 케이스 9(양쪽 변경)가 함께
    들어가는데 결과가 다르다 — 9는 merged에 레포 값이 남고 5는 merged에서 아예 빠진다.
    "name in result['merged']"로 둘을 구분할 수 있다.

    **hold의 value 축만 쓴다** — 행동 보류(action)는 restore_plan 전용이다(의도적 무시).
    """
    local, repo = _normalized(local, normalize), _normalized(repo, normalize)
    base = None if base is None else _normalized(base, normalize)
    held = hold(local, repo)
    value_held = set(held["value"])

    merged, conflicts, deleted, local_stale, repo_ahead = {}, [], [], [], []
    for name in sorted(set(local) | set(repo) | set(base or {})):
        if name in value_held:
            if name in repo:
                merged[name] = repo[name]      # 레포 값 보존. 판정표를 타지 않는다
            continue
        in_l, in_r = name in local, name in repo
        if base is None:
            if in_l:
                merged[name] = local[name]
            elif in_r:
                merged[name] = repo[name]
            continue
        in_s = name in base
        if in_l and not in_r and not in_s:                  # 1 로컬 신규
            merged[name] = local[name]
        elif not in_l and in_r and not in_s:                # 2 타 기기 추가
            merged[name] = repo[name]
            repo_ahead.append(name)
        elif not in_l and in_r and in_s:                    # 3 로컬에서 삭제
            deleted.append(name)
        elif in_l and not in_r and in_s:                    # 4·5
            if same(local[name], base[name]):               # 4 타 기기 삭제, 로컬 잔존
                local_stale.append(name)
            else:                                           # 5 로컬 수정 vs 리모트 삭제
                conflicts.append(name)
        elif in_l and in_r:
            if same(local[name], repo[name]):               # 6 in_sync
                merged[name] = local[name]
            elif in_s and same(repo[name], base[name]):     # 7 로컬만 변경
                merged[name] = local[name]
            elif in_s and same(local[name], base[name]):    # 8 타 기기 변경
                merged[name] = repo[name]
                repo_ahead.append(name)
            else:                                           # 9 충돌
                conflicts.append(name)
                merged[name] = repo[name]
        # (암묵) 케이스 10: base에만 존재 → 어느 리스트에도 넣지 않는다
    return {
        "merged": merged,
        "conflicts": conflicts,
        "deleted": deleted,
        "local_stale": local_stale,
        "repo_ahead": repo_ahead,
        "held": sorted(value_held),
        # 공개 next_base가 아니라 내부 함수를 부른다 — local·base·merged가 이미
        # 정규화돼 있으므로 다시 정규화하면 멱등성에 의존하게 된다(Task 5 리뷰 I2).
        "next_base": _next_base_normalized(local, base or {}, merged, value_held),
    }


BUCKETS = (
    "add", "needs_secret", "unrestorable", "in_sync", "local_ahead",
    "repo_ahead", "both_changed", "local_stale", "local_only",
    "value_held", "action_held",
)


# restorable(key, value) -> bool
#   restore_plan만 쓰는 훅이다. 레포에만 있는 항목을 이 도구가 재현할 수 있는가를 묻는다 —
#   거짓이면 unrestorable 버킷으로 가고 어떤 복원 명령의 대상도 되지 않는다.
#   값뿐 아니라 키 이름도 받는 것은, 값은 멀쩡한데 이름이 CLI 규칙을 어겨 재현할 수 없는
#   경우가 있기 때문이다.
#
# secret_keys(value) -> list
#   restore_plan만 쓰는 훅이다. 복원하려면 사용자에게 값을 되물어야 하는 항목의 목록을
#   돌려준다(없으면 빈 리스트). 비어 있지 않으면 needs_secret 버킷으로 간다 — 레포에는
#   마스킹된 값만 있으므로 그대로 등록하면 동작하지 않는 항목이 설치된다.
#   **route_new가 restorable → secret_keys 순으로 부르는 것이 계약이다** — 애초에 재현할
#   수 없는 항목의 비밀을 사용자에게 묻지 않기 위해서다. 따라서 secret_keys는
#   restorable이 참인 값만 받는다.
def restore_plan(local, repo, base, *, normalize, hold, restorable, secret_keys):
    """복원 계획. diff·merge와 마찬가지로 비교 직전 양쪽에 normalize를 적용한다.

    케이스 7·8·9를 한 버킷으로 뭉치지 않는다 — 처방이 서로 다르고, 특히 케이스 7에
    "레포 값 채택"을 제시하면 아직 백업되지 않은 로컬 변경이 파괴된다.
    조건식은 merge가 판정표의 7·8·9행에서 쓰는 것과 같다.
    local_stale은 케이스 4와 5를 모두 담는다(merge.local_stale ⊆ restore_plan.local_stale) —
    담지 않으면 케이스 5가 탈출구 없는 상태가 된다.

    보류 키는 두 축으로 갈린다(spec 5.3):
      행동 보류        → action_held 버킷에만. 어떤 CLI 명령의 대상도 되지 않는다
      값 보류(행동 아님) → 로컬에 없으면 add(설치 대상), 있으면 value_held 전용 버킷
    value_held를 판정표에 태우면 케이스 9로 분류되어 "양쪽이 모두 바뀌었습니다"가 뜨는데,
    그것은 사실이 아니고 "레포 따르기"를 실행할 수단도 없다.
    """
    local, repo = _normalized(local, normalize), _normalized(repo, normalize)
    known = _normalized(base, normalize) if base else {}
    held = hold(local, repo)
    value_held, action_held = set(held["value"]), set(held["action"])

    plan = {key: [] for key in BUCKETS}

    def route_new(name, value):
        """레포에만 있는 항목을 add/needs_secret/unrestorable로 보낸다."""
        if not restorable(name, value):
            plan["unrestorable"].append(name)
        elif secret_keys(value):
            plan["needs_secret"].append(name)
        else:
            plan["add"].append(name)

    for name in sorted(set(local) | set(repo)):
        if name in action_held:
            plan["action_held"].append(name)
            continue
        if name in value_held:
            if name in local:
                plan["value_held"].append(name)
            elif name in repo:
                route_new(name, repo[name])
            continue
        in_local, in_repo = name in local, name in repo
        if in_repo and not in_local:
            route_new(name, repo[name])
        elif in_local and in_repo:
            if same(local[name], repo[name]):                        # 6
                plan["in_sync"].append(name)
            elif name in known and same(repo[name], known[name]):    # 7
                plan["local_ahead"].append(name)
            elif name in known and same(local[name], known[name]):   # 8
                plan["repo_ahead"].append(name)
            else:                                                    # 9
                plan["both_changed"].append(name)
        elif name in known:                                          # 4·5
            plan["local_stale"].append(name)
        else:                                                        # 1
            plan["local_only"].append(name)
    return plan
