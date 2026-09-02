#!/usr/bin/env python3
"""레포 백업 문서 진단 — 다운그레이드 사고와 구문 손상 (읽기 전용).

마지막 정상(v2) 백업 커밋을 찾아 복구 후보로 제시한다.

사용: detect_downgrade.py <레포 경로>

레포의 백업 문서가 **그 문서의 옛 형식**인데 이 기기의 base는 v2 객체였다면, 옛 버전
기기가 덮어쓴 것이다. 옛 형식은 relpath마다 다르다 — `mcp-servers.json`은 최상위 배열,
`plugins.json`은 `version` 키가 없는 객체다(compat._OLD_SHAPE). 그래서 판정은 백업 문서
**둘 각각**에 돌리고, 결과는 `{"files": {relpath: {...}}}` 맵으로 낸다.

git 히스토리를 훑어 그 문서가 마지막으로 v2였던 커밋을 후보로 제시한다.

**구문 손상도 같은 루프에서 진단한다**(spec 5.1). `repo_shape == broken`이면 `broken_syntax`가
참이고, 그때도 마지막 v2 커밋을 후보로 낸다 — 깨진 문서에 필요한 것이 정확히 그것이다.
두 갈래는 배타다: SHAPE_BROKEN은 어느 문서의 옛 형식과도 다르므로 downgrade_suspected가
거짓이다. 구문 손상은 base 없이도 사실이다. 스크립트 이름은 바꾸지 않는다 — 가드 수십 개가
이름을 부른다(spec 11장).

**자동으로 복구하지 않는다** — 옛 기기가 의도적으로 지운 항목까지 되살리기 때문이다.
탐지 실패가 백업을 막아서도 안 된다. 부가 기능이므로 status=skipped로 물러난다.

**공개 단위는 셋이다** — `detect`·`detect_file`·`find_last_v2_commit`. spec 9.2가 이름으로
부르며 각각의 계약을 서술하는 것들이다. 나머지(`_git`·`_adapter`·`_shape_of_file`·
`_base_shape`·`_git_unusable_reason`·`_skipped_*`)는 구현 세부이므로 비공개다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib")
)
import compat  # noqa: E402
import mcp_config as mc  # noqa: E402
import plugin_config as pc  # noqa: E402
import sync_state as ss  # noqa: E402


def _mcp_buckets(servers):
    """mcp-servers.json의 후보 요약. {섹션: [이름…]}

    parse_base가 평탄한 {이름: 설정}을 주므로 여기서 버킷 하나로 감싼다. 버킷 이름을
    손으로 적지 않고 mcp_config.SECTIONS에서 뽑는다 — 리터럴이면 문서 키가 바뀌어도
    어긋난 이름이 조용히 사용자에게 나간다.
    언패킹으로 "섹션이 하나"라는 전제를 함께 건다. 섹션이 늘면 여기서 ValueError로
    즉시 드러난다 — 그때는 감싸는 규칙 자체를 다시 정해야 한다.
    """
    (section,) = mc.SECTIONS
    return {section: sorted(servers)}


def _plugins_buckets(sections):
    """plugins.json의 후보 요약. 버킷 이름은 parse_base가 낸 매핑의 키 그대로다.

    그 매핑은 부재 섹션도 {}로 채워 돌려주므로(plugin_config._recognized_sections)
    키 집합은 항상 pc.SECTIONS 전부다. 여기서 다시 목록을 적지 않는 이유이기도 하다.
    """
    return {name: sorted(mapping) for name, mapping in sections.items()}


# relpath -> (base 파서, 후보 요약기).
#
# **파서는 parse_backup이 아니라 parse_base다.** parse_backup은 알아볼 수 없는 문서를
# 빈 값으로 degrade하므로 상위 버전 백업이 "항목 0개인 정상 백업"으로 제시된다 —
# 두 어댑터가 명시적으로 금지하는 접기다(불변식 6).
#
# **이 표가 v2 판정을 겸하지 않는다.** v2인가는 compat.shape_of가, 항목을 셀 수 있는가는
# 여기의 parse_base가 답한다. 자세한 이유는 find_last_v2_commit의 docstring에 있다.
_ADAPTERS = {
    mc.BACKUP_RELPATH: (mc.parse_base, _mcp_buckets),
    pc.BACKUP_RELPATH: (pc.parse_base, _plugins_buckets),
}

# 판정 대상 문서. **손으로 적지 않고 어댑터 표에서 뽑는다** — 두 벌이면 어댑터를
# 더하고 목록을 안 늘렸을 때 그 문서가 조용히 판정에서 빠진다.
# 정렬은 출력 순서를 결정론적으로 만들기 위한 것이다.
RELPATHS = tuple(sorted(_ADAPTERS))


def _adapter(relpath):
    """relpath의 (parse_base, 요약기). 모르는 relpath는 조용한 fail-open 대신 ValueError.

    compat._for_relpath와 같은 관례다 — 모르는 입력에 빈 결과를 돌려주면
    "판정할 수 없었다"가 "사고가 없다"로 접힌다(불변식 6).
    """
    if relpath not in _ADAPTERS:
        raise ValueError("어댑터를 모르는 relpath: %r" % relpath)
    return _ADAPTERS[relpath]


def _git(repo_path, args):
    """git 표준 출력(bytes). 실패하면 RuntimeError."""
    proc = subprocess.run(["git", "-C", repo_path] + args, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip() or "git 실패")
    return proc.stdout


def _git_unusable_reason(repo_path):
    """이 레포에서 git 자체를 쓸 수 없으면 그 사유(문자열), 쓸 수 있으면 None.

    **전역 status와 파일별 status는 다른 것을 말한다.** 전역은 git이 없거나 레포가 git이
    아닌 경우(어느 문서의 히스토리도 훑을 수 없다), 파일별은 그 문서의 히스토리 훑기가
    실패한 경우다. 한쪽으로 합치면 "탐지할 수 없었다"와 "사고가 없다"의 구별(불변식 6)이
    파일 단위에서 무너진다 — 두 문서 중 하나만 못 봤는데 전체가 skipped로 읽히거나,
    레포가 아예 git이 아닌데 그 사실이 어디에도 안 나온다.
    """
    try:
        _git(repo_path, ["rev-parse", "--git-dir"])
    except (RuntimeError, OSError) as e:
        return str(e)
    return None


def find_last_v2_commit(repo_path, relpath):
    """그 문서가 v2 객체였던 마지막 커밋과, 알아보지 못한 문서를 건너뛰었는지.

    반환: (candidate_dict_or_None, newer_seen)

    **v2 판정은 compat.shape_of이지 parse_base가 아니다.** 두 어댑터의 인식 조건이 답하는
    질문은 *"이 문서를 읽을 수 있는가"* 이지 *"v2인가"* 가 아니고, **둘 다 v1 문서를 그대로
    인식한다** — 실측으로 mc.parse_base(b'[{"name":"a","command":"a"}]')는
    {'a': {'command': 'a'}}를, pc.parse_base(b'{"enabledPlugins":{"a@m":true}}')는 세 섹션
    매핑을 돌려준다(어느 쪽도 None이 아니다). plugins.json 쪽 근거는 인식 조건 2
    (*"version이 없거나 SCHEMA_VERSION 이하"*)이고, mcp 쪽 근거는 인식 함수가 v1 배열을
    명시적으로 받는다는 것이다.

    그래서 parse_base로 v2를 판정하면 **2.x가 쓴 v1 커밋이 "마지막 정상 판본"으로 제시**되고,
    대화가 그 sha를 되돌리라고 안내한다 — 탐지가 사고를 복구하는 대신 **고착시킨다.**

    역할을 나눈다: shape_of가 **v2인가**를, parse_base가 **항목을 셀 수 있는가**를
    답한다(None이면 newer_seen).

    --diff-filter=d로 **삭제 커밋을 목록에서 애초에 뺀다.** 그러면 남은 커밋에는 파일이
    반드시 존재하므로 git show 실패는 곧 "레포가 손상됐다"는 뜻이 되어 그대로 전파해도
    된다. try/except로 감싸 continue하면 레포 손상이 "v2가 없음"으로 접혀, 사용자에게
    "되돌릴 지점이 없다"는 사실이 아닐 수 있는 결론이 전달된다(불변식 6).
    """
    parse_base, buckets_of = _adapter(relpath)
    out = _git(
        repo_path,
        ["log", "--diff-filter=d", "--format=%H%x09%ad%x09%s", "--date=short",
         "--", relpath],
    )
    newer_seen = False
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        blob = _git(repo_path, ["show", "%s:%s" % (sha, relpath)])
        if compat.shape_of(blob, relpath) != compat.SHAPE_V2_OBJECT:
            continue
        entries = parse_base(blob)
        if entries is None:
            newer_seen = True
            continue          # 알아보지 못하는 문서다. 0개라고 단언하지 않는다
        return {
            "sha": sha,
            "date": date,
            "subject": subject,
            # relpath 중립이다. 버킷 이름은 어댑터가 정한다 — 여기서 mcp 전용 키
            # (서버 개수·서버 이름)를 내면 plugins.json 쪽 대화가 쓸 이름이 없다.
            "entries": buckets_of(entries),
        }, newer_seen
    return None, newer_seen


def _shape_of_file(path, relpath):
    """파일을 읽어 그 relpath의 규칙으로 형태를 판정한다.

    **못 읽음을 absent로 접지 않는다(불변식 6).** absent는 "파일이 없다"는 결론이지만
    권한·IO 실패는 아무 결론도 아니다. 접으면 다운그레이드 탐지가 조용히 꺼진다.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return compat.SHAPE_ABSENT
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw, relpath)


def _base_shape(relpath, base_dir):
    """그 문서의 base 블롭 형태. read_base는 없으면 None, 그 외 OSError는 전파한다.

    **base는 문서마다 따로 읽는다.** 한 번 읽어 두 판정에 돌려 쓰면 plugins.json의 base
    부재가 mcp-servers.json의 base로 가려져, 근거 없는 판정이 근거 있는 것처럼 나간다.
    """
    try:
        raw = ss.read_base(relpath, base_dir=base_dir)
    except OSError:
        return compat.SHAPE_UNREADABLE
    return compat.shape_of(raw, relpath)


def detect(repo_path, base_dir=ss.BASE_DIR):
    """{"status", "reason", "files": {relpath: {…}}}

    파일별 항목은 detect_file이 낸다. 전역 status는 git 자체를 쓸 수 없을 때만 skipped다
    (_git_unusable_reason 참조).

    **전역이 skipped여도 files 맵은 채워서 낸다.** 비우면 그 맵을 도는 SKILL.md의 루프가
    0회 돌아 아무것도 보고되지 않고, "탐지할 수 없었다"가 "사고가 없다"로 조용히
    읽힌다(불변식 6). 형태 판정은 git 없이도 되므로 그 결과는 여전히 사실이다.
    """
    unusable = _git_unusable_reason(repo_path)
    files = {relpath: detect_file(repo_path, relpath, base_dir)
             for relpath in RELPATHS}
    if unusable is not None:
        return {"status": "skipped", "reason": unusable, "files": files}
    return {"status": "ok", "reason": None, "files": files}


def detect_file(repo_path, relpath, base_dir):
    """문서 하나의 판정. {"status", "reason", "downgrade_suspected", "broken_syntax",
    "repo_shape", "base_shape", "candidate", "newer_schema_seen"}

    repo_shape·base_shape를 항상 싣는다 — 탐지하지 못한 경우에도 왜 못 했는지가 호출부에
    드러나야 한다(불변식 6). SKILL.md가 "탐지할 수 없었다"와 "사고가 없다"를 구별해
    보고할 수 있는 근거가 이것이다.
    """
    repo_shape = _shape_of_file(os.path.join(repo_path, relpath), relpath)
    base_shape = _base_shape(relpath, base_dir)
    suspected = compat.downgrade_suspected(repo_shape, base_shape, relpath)
    broken = repo_shape == compat.SHAPE_BROKEN
    out = {
        "status": "ok",
        "reason": None,
        "downgrade_suspected": suspected,
        # 구문 손상. base 없이도 사실이므로 base_shape를 보지 않는다(spec 5.1).
        "broken_syntax": broken,
        "repo_shape": repo_shape,
        "base_shape": base_shape,
        "candidate": None,
        # 히스토리에 이 버전이 알아보지 못하는 백업이 있었는가.
        # "후보 없음"과 "알아보지 못해 건너뜀"은 다른 말이다.
        "newer_schema_seen": False,
    }
    if suspected or broken:
        try:
            out["candidate"], out["newer_schema_seen"] = find_last_v2_commit(
                repo_path, relpath)
        except (RuntimeError, OSError) as e:
            # **ValueError를 여기서 잡지 않는다(의도).** 파일별로 접는 것은 *환경 실패*
            # 뿐이다 — 그것은 이 문서에만 해당하고 다른 문서의 판정은 여전히 사실이다.
            # 판정 함수가 던지는 ValueError(알 수 없는 shape·relpath·섹션 수)는
            # 프로그래밍 오류이고 오늘은 구성상 도달할 수 없다. 그것을 한 문서의
            # skipped로 접으면 코드 결함이 "그 파일만 환경 문제였다"로 묻히므로,
            # main()의 마지막 방어선이 받아 **전체를** skipped로 알린다(키 모양은 유지).
            # 이 선택은 test_a_judgment_error_is_not_folded_into_one_file이 잠근다.
            return _skipped_file(str(e), suspected, repo_shape, base_shape, broken)
    return out


def _skipped_file(reason, suspected=False, repo_shape=None, base_shape=None,
                  broken=False):
    """문서 하나의 탐지를 못 한 경우. **키 모양을 detect_file의 정상 경로와 같게 둔다.**

    소비하는 쪽이 entry.get("downgrade_suspected")를 볼 때 키가 없으면 None(falsy)이 되어
    또 한 번 "사고 없음"처럼 읽힌다(불변식 6).
    """
    return {
        "status": "skipped",
        "reason": reason,
        "downgrade_suspected": suspected,
        "broken_syntax": broken,
        "repo_shape": repo_shape,
        "base_shape": base_shape,
        "candidate": None,
        "newer_schema_seen": False,
    }


def _skipped_all(reason):
    """탐지 자체가 실패한 경우. files 맵도 같은 키 모양으로 채운다.

    여기서는 형태조차 알 수 없으므로 shape는 None이다. 그래도 **맵은 비우지 않는다** —
    비면 소비하는 루프가 0회 돌아 보고가 통째로 사라진다(detect의 docstring 참조).
    """
    return {
        "status": "skipped",
        "reason": reason,
        "files": {relpath: _skipped_file(reason) for relpath in RELPATHS},
    }


def main():
    if len(sys.argv) != 2:
        print("사용: detect_downgrade.py <레포 경로>", file=sys.stderr)
        sys.exit(1)
    try:
        out = detect(sys.argv[1])
    except Exception as e:  # noqa: BLE001 — 마지막 방어선
        # OSError만 잡으면 downgrade_suspected가 던지는 ValueError를 놓쳐 트레이스백으로
        # 죽고, "탐지 실패가 백업을 막으면 안 된다"는 이 스크립트의 원칙이 무너진다.
        out = _skipped_all("%s: %s" % (type(e).__name__, e))
        print("다운그레이드 탐지 건너뜀: %s" % e, file=sys.stderr)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
