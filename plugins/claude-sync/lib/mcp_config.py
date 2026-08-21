#!/usr/bin/env python3
"""claude-sync의 MCP 서버 동기화 코어.

데이터 소스는 ~/.claude.json의 top-level mcpServers(user 스코프)다.
`claude mcp list`의 텍스트 출력은 쓰지 않는다 — 손실 압축이고 cwd에 의존한다.
backup/status/restore는 이 모듈만 통해 MCP를 다룬다(파서 드리프트 차단).
"""
import copy
import json
import os
import re

SENTINEL = "<REDACTED>"
SECRET_FIELDS = ("headers", "env")
SCHEMA_VERSION = 2
BACKUP_RELPATH = "mcp-servers.json"
DEFAULT_CLAUDE_JSON = os.path.expanduser("~/.claude.json")
VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")   # claude mcp add-json의 실측 제약
_BROKEN = object()                             # JSON 구문 오류 센티널


class LocalConfigUnavailable(Exception):
    """~/.claude.json을 읽지 못했다.

    "서버 0개"와 반드시 구별해야 한다. 이 예외가 발생하면 삭제 판정을 해서는 안 된다.
    """


class UnknownBackupSchema(Exception):
    """레포의 백업 파일이 이 버전이 아는 형식이 아니다.

    상위 버전이 쓴 문서일 수 있으므로 "서버 0개"로 읽어서는 안 된다. 그렇게 읽으면
    merge가 레포를 빈 것으로 보고 이 기기의 로컬만 남긴 결과를 덮어써, 상위 버전의
    백업을 파괴한다. 옛 버전이 v2 문서에 저지른 사고와 같은 형태다.
    LocalConfigUnavailable이 로컬 쪽에서 하는 역할을 레포 쪽에서 한다(불변식 2).
    """


def read_local_servers(claude_json_path=None):
    """user 스코프 mcpServers를 반환한다.

    mcpServers 키가 아예 없으면 {} (서버 0개라는 정상 상태).
    키가 있는데 값이 dict가 아니면(null 포함) 읽기 실패로 취급해 예외를 던진다 —
    잘못된 삭제 판정을 막기 위해서다.
    파일이 없거나 JSON 파싱에 실패해도 LocalConfigUnavailable을 던진다.
    projects[*].mcpServers(local 스코프)는 읽지 않는다.
    PermissionError 등 그 외 OSError는 전파한다(LocalConfigUnavailable로 감싸지 않는다).
    """
    path = DEFAULT_CLAUDE_JSON if claude_json_path is None else claude_json_path
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read())
    except FileNotFoundError as e:
        raise LocalConfigUnavailable("%s 없음" % path) from e
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LocalConfigUnavailable("%s 파싱 실패: %s" % (path, e)) from e
    if not isinstance(data, dict):
        raise LocalConfigUnavailable("%s 최상위가 객체가 아님" % path)
    if "mcpServers" not in data:
        return {}
    servers = data["mcpServers"]
    if not isinstance(servers, dict):
        raise LocalConfigUnavailable("mcpServers가 객체가 아님")
    return dict(servers)


def _redact_field(value):
    """headers/env 한 필드의 값을 마스킹한다. 중첩 구조는 통째로 SENTINEL이 된다.

    값이 dict가 아니면(None 포함) 필드 전체가 dict가 아닌 문자열 SENTINEL로 바뀐다 —
    타입이 dict에서 str로 바뀌므로 secret_keys는 이 필드에 대해 키를 하나도 묻지 않는다.
    """
    if isinstance(value, dict):
        return {k: SENTINEL for k in value}
    return SENTINEL


def redact(servers):
    """headers/env의 값만 SENTINEL로 치환한다. 키 이름과 나머지 필드는 보존한다.

    입력은 변경하지 않으며, 반환값은 입력과 어떤 중첩 객체도 공유하지 않는다
    (deepcopy) — 후속 가공이 반환값을 다듬어도 원본 로컬 설정이 오염되지 않는다.
    이미 마스킹된 입력에 다시 적용해도 결과가 같다(멱등) — diff/merge가 로컬(평문)과
    레포(마스킹됨) 양쪽에 이 함수를 적용해 수렴시키는 전제다.
    """
    out = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            out[name] = cfg
            continue
        new = copy.deepcopy(cfg)
        for field in SECRET_FIELDS:
            if field in new:
                new[field] = _redact_field(new[field])
        out[name] = new
    return out


def secret_keys(cfg):
    """복원 시 사용자에게 값을 물어야 하는 (field, key) 목록."""
    found = []
    if not isinstance(cfg, dict):
        return found
    for field in SECRET_FIELDS:
        value = cfg.get(field)
        if isinstance(value, dict):
            found.extend((field, k) for k in sorted(value))
    return found


def _servers_from_obj(obj):
    """이미 디코딩된 JSON 객체에서 servers 매핑을 뽑는다. v2 객체와 v1 배열을 지원한다."""
    if isinstance(obj, list):
        out = {}
        for item in obj:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                out[item["name"]] = {k: v for k, v in item.items() if k != "name"}
        return out
    if isinstance(obj, dict):
        servers = obj.get("servers")
        return dict(servers) if isinstance(servers, dict) else {}
    return {}


def _decode(data):
    """JSON 디코드. 구문이 깨졌으면 _BROKEN.

    None·false·0처럼 falsy한 유효 값과 "디코드 실패"를 구별해야 하므로 센티널을 쓴다.
    """
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _BROKEN


def _recognized_servers(obj):
    """알아볼 수 있는 백업 문서면 servers 매핑, 아니면 None.

    v1 배열과 servers가 dict인 v2 객체만 인정한다. 이 판정이 parse_base·parse_backup·
    load_backup의 공통 기준이다 — 세 곳이 갈리면 "이력은 못 믿는데 레포는 믿는" 비대칭이
    생기고, 그 비대칭이 상위 버전 백업을 파괴한다.
    """
    if isinstance(obj, list):
        return _servers_from_obj(obj)
    if isinstance(obj, dict) and isinstance(obj.get("servers"), dict):
        return _servers_from_obj(obj)
    return None


def parse_backup(data):
    """JSON 바이트/문자열에서 servers 매핑을 읽는다(관대한 해석).

    v2 객체({"version":2, "servers":{...}})와 v1 배열([{name,url,type}, ...])을 모두 지원한다.
    깨진 입력도 알아볼 수 없는 입력도 {}로 degrade한다.
    **레포 파일을 읽을 때는 이 함수가 아니라 load_backup을 쓴다** — 알아볼 수 없는 문서를
    "서버 0개"로 읽으면 그 파일을 덮어써 파괴하기 때문이다.
    """
    obj = _decode(data)
    if obj is _BROKEN:
        return {}
    servers = _recognized_servers(obj)
    return {} if servers is None else servers


def parse_base(data):
    """base 블롭 전용 파싱. 이력을 신뢰할 수 없으면 None을 반환한다.

    "이력이 비어 있었다"({})와 "이력을 읽을 수 없다"(None)를 반드시 구별해야 한다.
    전자는 삭제·충돌 판정의 근거가 되지만, 후자는 근거가 될 수 없다.

    백업 문서로 알아볼 수 있는 형태 — v1 배열, 또는 servers가 dict인 v2 객체 — 일 때만
    매핑을 돌려준다. 구문은 유효하지만 스키마가 아닌 JSON(null, 문자열, 숫자,
    servers가 없거나 dict가 아닌 객체)은 신뢰할 수 없는 이력이므로 None이다.
    """
    if data is None:
        return None
    obj = _decode(data)
    if obj is _BROKEN:
        return None
    return _recognized_servers(obj)


def load_backup(path):
    """레포의 mcp-servers.json을 안전하게 읽는다. 파일이 없으면 {}.

    구문이 깨진 파일은 {}로 degrade한다 — 레포 파일 하나가 깨졌다고 백업 전체를 막지
    않으며, 다음 백업이 그 파일을 정상 내용으로 되돌린다.
    구문은 유효한데 형식을 알아볼 수 없으면 UnknownBackupSchema를 던진다. 상위 버전이
    쓴 문서일 수 있고, 그것을 "서버 0개"로 읽으면 이 버전이 그 백업을 덮어써 파괴한다.
    (PermissionError 등 그 외 OSError는 전파한다.)
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}
    obj = _decode(raw)
    if obj is _BROKEN:
        return {}
    servers = _recognized_servers(obj)
    if servers is None:
        raise UnknownBackupSchema(
            "%s의 형식을 알아볼 수 없다 — 상위 버전이 쓴 백업일 수 있다" % path
        )
    return servers


def dump_backup(servers, path):
    """v2 형식으로 저장한다. sort_keys로 git diff를 안정화한다."""
    payload = {"version": SCHEMA_VERSION, "scope": "user", "servers": servers}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def _fingerprint(cfg):
    """cfg를 키 정렬된 JSON 문자열로 만들어 비교 가능한 형태로 바꾼다.

    dump_backup과 같은 직렬화 옵션(sort_keys, ensure_ascii=False)을 쓴다 —
    디스크 표현이 같으면 same()도 같다고 판정하도록 맞춘 것이다.
    """
    return json.dumps(cfg, sort_keys=True, ensure_ascii=False)


def same(a, b):
    """설정 동등 비교. 키 순서에 무관하다."""
    return _fingerprint(a) == _fingerprint(b)


def diff(local, backed):
    """상태 비교. 비교 직전 양쪽에 redact를 적용한다.

    비밀 값은 로컬에 평문, 레포에 SENTINEL로 저장되므로 원본끼리 비교하면
    비밀을 가진 서버가 영구히 "변경됨"으로 보고된다(Bug #2와 같은 미수렴).
    """
    local_masked, repo_masked = redact(local), redact(backed)
    return {
        "only_local": sorted(set(local_masked) - set(repo_masked)),
        "only_repo": sorted(set(repo_masked) - set(local_masked)),
        "changed": sorted(
            name for name in set(local_masked) & set(repo_masked)
            if not same(local_masked[name], repo_masked[name])
        ),
    }


def next_base(local, base, servers):
    """다음 base 매핑. base[name]은 로컬이 그 값에 동의할 때만 전진한다.

    로컬이 동의하지 않은 값(타 기기가 추가·변경한 서버, 충돌 중인 서버)을 base에 기록하면
    다음 백업이 그 차이를 "로컬이 바뀌었다"로 오독해, 타 기기의 서버를 삭제하거나
    타 기기의 변경을 되돌린다. update_base.py가 파일 단위로 지키는 불변식과 같다.
    merge가 내부에서 쓰고 결과에 담아 반환하지만, restore도 같은 규칙으로 base를 갱신해야
    하므로 공개 함수다.
    반환값은 local·base·servers의 어떤 nested 객체도 공유하지 않는다(deepcopy) — 호출부가
    반환된 servers를 가공한 뒤 base에 써도 next_base가 조용히 오염되지 않는다.

    입력에 redact를 내부 적용한다 — merge·diff와 같은 계약이다. restore는
    read_local_servers()의 원본(비밀 평문)을 넘기게 되는데, 내부 적용이 없으면
    same(레포의 <REDACTED>, 로컬 평문)이 거짓이 되어 비밀을 가진 서버의 base가
    전진하지 않고, 평문 키가 base 블롭에 새 사본으로 기록된다.
    redact는 멱등이므로 이미 마스킹된 merge 경로에는 영향이 없다.
    """
    local, servers = redact(local), redact(servers)
    old = redact(base) if base else {}
    out = {}
    for name in sorted(set(old) | set(servers)):
        if name in servers and name in local and same(servers[name], local[name]):
            out[name] = copy.deepcopy(servers[name])  # 로컬이 동의 → 전진 (케이스 1·6·7)
        elif name not in servers and name not in local:
            continue                    # 양쪽에서 사라짐 → base에서 제거 (케이스 3·10)
        elif name in old:
            out[name] = copy.deepcopy(old[name])       # 로컬이 동의 안 함 → 이전 base 유지 (케이스 2·4·5·8·9)
    return out


def merge(local, repo, base):
    """서버 이름 키 단위 3-way 병합 (spec 7.2 판정표).

    입력에 redact를 내부에서 적용한다 — diff와 같은 계약이다. 호출부가 원본(비밀 평문)을
    그대로 넘겨도 결과에는 비밀이 실리지 않는다.
    base가 None이면 삭제 없이 합집합으로 degrade한다 — "타 기기 추가"와
    "내 삭제"를 구별할 수 없기 때문이다.
    반환하는 next_base는 이름 단위로 전진한다: 로컬이 동의한 이름만 base에 기록하고,
    동의하지 않은 이름(타 기기가 추가·변경했거나 충돌·잔존 중인 이름)은 이전 base를 유지한다
    (next_base 함수 참고). 그래서 호출부가 conflicts/local_stale 유무로 base 갱신을 전역으로
    게이트할 필요가 없다 — 서버 하나가 충돌 중이어도 나머지 서버의 base는 계속 전진한다.
    conflicts에는 케이스 5(로컬 수정 vs 리모트 삭제)와 케이스 9(양쪽 변경)가 함께 들어가는데
    결과가 다르다 — 9는 servers에 레포 값이 남고 5는 servers에서 아예 빠진다.
    "name in result['servers']"로 둘을 구분할 수 있다.
    """
    local, repo = redact(local), redact(repo)
    base = None if base is None else redact(base)
    servers, conflicts, deleted, local_stale, repo_ahead = {}, [], [], [], []
    for name in sorted(set(local) | set(repo) | set(base or {})):
        in_l, in_r = name in local, name in repo
        if base is None:
            if in_l:
                servers[name] = local[name]
            elif in_r:
                servers[name] = repo[name]
            continue
        in_s = name in base
        if in_l and not in_r and not in_s:                  # 1 로컬 신규
            servers[name] = local[name]
        elif not in_l and in_r and not in_s:                # 2 타 기기 추가
            servers[name] = repo[name]
            repo_ahead.append(name)
        elif not in_l and in_r and in_s:                    # 3 로컬에서 삭제
            deleted.append(name)
        elif in_l and not in_r and in_s:                    # 4·5 로컬만 있고 base에도 있음
            if same(local[name], base[name]):               # 4 타 기기 삭제, 로컬 잔존
                local_stale.append(name)
            else:                                           # 5 로컬 수정 vs 리모트 삭제
                conflicts.append(name)
        elif in_l and in_r:
            if same(local[name], repo[name]):               # 6 in_sync
                servers[name] = local[name]
            elif in_s and same(repo[name], base[name]):     # 7 로컬만 변경
                servers[name] = local[name]
            elif in_s and same(local[name], base[name]):    # 8 타 기기 변경
                servers[name] = repo[name]
                repo_ahead.append(name)
            else:                                           # 9 충돌
                conflicts.append(name)
                servers[name] = repo[name]
        # (암묵) L·R 모두 없음(base에만 존재, 케이스 10) → 아무 리스트에도 넣지 않는다
    return {
        "servers": servers,
        "conflicts": conflicts,
        "deleted": deleted,
        "local_stale": local_stale,
        "repo_ahead": repo_ahead,
        "next_base": next_base(local, base, servers),
    }


def restorable(name, cfg):
    """claude mcp add-json으로 재현할 수 있는 항목인가.

    둘 중 하나만 어겨도 거짓이다 —
    (a) 이름이 CLI 규칙(영숫자·하이픈·언더스코어)을 어김,
    (b) config에 command도 없고 url+type(http/sse)도 없음.
    v1 배열에서 승격된 항목이 정확히 (b)의 형태다(10장). type은 소문자만 인정한다 —
    v1이 저장하던 "HTTP"는 add-json 스키마와 맞지 않는다.
    """
    if not VALID_NAME.match(name):
        return False
    if not isinstance(cfg, dict):
        return False
    if isinstance(cfg.get("command"), str) and cfg["command"]:
        return True
    return isinstance(cfg.get("url"), str) and cfg.get("type") in ("http", "sse")


def restore_plan(local, backed, base):
    """복원 계획. diff·merge와 마찬가지로 비교 직전 양쪽에 redact를 적용한다.

    버킷 9개: add / needs_secret / unrestorable / in_sync / local_ahead /
    repo_ahead / both_changed / local_stale / local_only.
    케이스 7·8·9를 한 버킷으로 뭉치지 않는 이유는 7.7에 있다 — 처방이 서로 다르고,
    특히 케이스 7에 "레포 값 채택"을 제시하면 아직 백업되지 않은 로컬 변경이 파괴된다.
    조건식은 merge가 7.2 판정표의 7·8·9행에서 쓰는 것과 같다.
    local_stale은 케이스 4와 5를 모두 담는다(merge.local_stale ⊆ restore_plan.local_stale) —
    담지 않으면 케이스 5가 탈출구 없는 상태가 된다.
    """
    local, backed = redact(local), redact(backed)
    known = redact(base) if base else {}
    plan = {key: [] for key in (
        "add", "needs_secret", "unrestorable", "in_sync", "local_ahead",
        "repo_ahead", "both_changed", "local_stale", "local_only",
    )}
    for name in sorted(set(local) | set(backed)):
        in_local, in_repo = name in local, name in backed
        if in_repo and not in_local:
            cfg = backed[name]
            if not restorable(name, cfg):
                plan["unrestorable"].append(name)
            elif secret_keys(cfg):
                plan["needs_secret"].append(name)
            else:
                plan["add"].append(name)
        elif in_local and in_repo:
            if same(local[name], backed[name]):                          # 6
                plan["in_sync"].append(name)
            elif name in known and same(backed[name], known[name]):      # 7
                plan["local_ahead"].append(name)
            elif name in known and same(local[name], known[name]):       # 8
                plan["repo_ahead"].append(name)
            else:                                                        # 9
                plan["both_changed"].append(name)
        elif name in known:                                              # 4·5
            plan["local_stale"].append(name)
        else:                                                            # 1
            plan["local_only"].append(name)
    return plan
