#!/usr/bin/env python3
"""`.syncignore` 매칭 규칙 한 벌. sync-backup/SKILL.md 4단계의 `find -path`와 같다.

의미의 정본
-----------
**`.syncignore`의 뜻은 "올리지 않는다" 하나다 — backup 방향 전용이다.**
한 줄 요약: **"내 것을 남에게 주지 않는다."** 세 스킬의 행동은 전부 여기서 유도된다.

- **backup — 제외한다.** 4단계가 레포 작업 트리에서 매치를 `rm -rf`하고, 10단계의
  `git add -A`가 그 삭제를 커밋·푸시한다. **이 기기가 이번에 복사한 것만 지우는 것이
  아니다** — 다른 기기가 올려 두어 이미 레포에 있던 같은 경로도 함께 지워져 푸시된다
  (실측: 4단계 bash를 커밋된 레포에 돌리면 그 파일이 사라지고 `git add -A`가
  `1 deletion`으로 스테이징한다). 7단계의 `sync-metadata.json`에도 이름·sha256을 남기지
  않는다.
- **restore — 무시한다(결정).** reconcile_restore.py는 이 모듈을 부르지 않는다.
  존중하게 만들면 **다른 기기가 올린 같은 경로 파일을 영영 받지 못한다** — 그것을 피하는
  선택이다. "올리지 않는다"는 내보내는 방향의 규정이지 받는 방향의 규정이 아니다.
- **status — 제외된 로컬 파일은 보고하지 않는다.** 그리고 제외됐는데 **레포에 남아 있는**
  파일은 "backup 시 push"가 아니라 **"backup이 레포에서 지운다"**로 보고한다
  (check_status.py의 `excluded_in_repo`). 위 두 줄에서 그대로 유도되는 문구다 —
  push도 아니고 침묵도 아니다.

**README 두 벌이 말해야 하는 것**(이 목록이 정본이다 — `test_user_docs.py`가 개수를
여기서 뽑는다. 손으로 적으면 한 문장을 지우면서 개수도 함께 줄이는 편집이 통과한다):

1. 뜻은 "올리지 않는다" 하나이고 **backup 방향 전용**이다
2. **restore는 무시한다** — 제외한 경로도 레포에 있으면 내려온다
3. **제외해도 로컬 파일이 덮어쓰이지 않게 보호되지는 않는다** — 2에서 곧바로 나온다

하나만 적으면 사용자가 "복원도 막힌다"로 읽고, 제외한 경로의 로컬 파일이 레포 내용으로
덮어쓰일 수 있다는 것을 모른 채 `/sync-restore`를 돌린다.

**왜 여기 있는가.** 4단계는 레포 작업 트리에서 `find … | rm -rf`로 파일을 지우는데,
`~/.claude`를 직접 걷는 스크립트 둘(check_status.py·reconcile_backup.py)은 그 삭제를
보지 못하므로 제외 목록을 스스로 적용해야 한다. 두 곳이 각자 매칭을 만들면 그 어긋남이
조용해지므로 규칙을 이 파일 하나에 둔다. 7단계의 generate_metadata.py는 **소비자가
아니다** — 레포 작업 트리를 걷으므로 4단계의 삭제가 곧 표식의 제외다(spec 3.3. 앞 판은
`~/.claude`를 걸어 이 필터에 기댔다).

**bash 쪽은 이 함수를 부를 수 없다**(`find`다). 그래서 대응이 깨지는 것을 잡는 것은
test_skill_wiring.py의 `test_python_syncignore_matches_the_skill_bash`다 — 같은 픽스처에
SKILL.md의 bash 블록과 아래 `is_excluded`를 **둘 다 돌려** 결과 집합이 같은지 잰다.
규칙을 한쪽만 고치면 거기서 죽는다.

`find "$SYNC_REPO" -path "$SYNC_REPO/$pattern" -print`의 성질(실측):
- `-path`는 FNM_PATHNAME 없이 매칭하므로 `*`가 `/`를 넘는다 → `fnmatchcase`가 같다.
- find는 디렉토리를 **후행 슬래시 없이** 출력하므로 `skills/x/`는 매치 0건이다.
- 매치된 디렉토리는 `rm -rf`로 통째로 사라진다 → **조상 디렉토리가 매치되면 그 아래
  파일도 제외**다. 파일 경로만 대조하면 디렉토리 패턴이 메타데이터에서만 새어 나간다.
- `-path "$SYNC_REPO/.git" -prune`은 레포 루트에만 있는 가지치기다. `~/.claude`를
  걷는 쪽에는 대응물이 필요 없다 — 표식 대상은 agents/·skills/·CLAUDE.md뿐이다.

**이 필터가 덮지 못하는 것**: `plugins.json`·`mcp-servers.json`은 4단계보다 **뒤인**
5·6단계가 다시 생성하므로 `.syncignore`로 제외할 수 없다. **위 정본의 "올리지 않는다"가
그 두 파일에는 적용되지 않는다는 뜻이다** — 민감 값은 제외가 아니라 어댑터의 마스킹이
담당한다(sync-backup/SKILL.md 「보안」절에 적혀 있다). 마스킹은 값만 가리고 키 이름은
남긴다.
"""
import fnmatch
import os

DEFAULT_RELPATH = ".syncignore"


def default_path(claude_dir):
    """`~/.claude` 역할 디렉토리 안의 `.syncignore` 경로."""
    return os.path.join(claude_dir, DEFAULT_RELPATH)


def load_patterns(path):
    """`.syncignore`의 패턴 목록. 파일이 없으면 빈 목록.

    4단계 bash와 같은 규칙이다 — **앞뒤의 공백·탭·CR을 다듬는다.** bash 쪽은
    `IFS=$' \\t\\r' read -r`이 같은 세 글자를 앞뒤에서만 떼고(안쪽 공백은 남는다),
    그 뒤 `[[ -z "$pattern" || "$pattern" == \\#* ]]`로 빈 줄과 `#`으로 시작하는 줄을
    거른다. 여기서 `strip(" \\t\\r")`을 쓰는 것이 그 한 벌이다 — **파이썬의 맨
    `strip()`을 쓰면 안 된다.** 그쪽은 유니코드 공백까지 떼어 bash보다 많이 다듬고,
    그러면 파이썬만 제외한 파일이 레포에는 남아 표식 없이 push된다.

    다듬지 않던 초판은 CRLF 편집기가 쓴 `.syncignore` 한 줄에서 **양쪽이 함께**
    빗나갔다(패턴이 `skills/secret-tool\\r`이 되어 매치 0건). 두 구현은 일치했지만
    사용자는 제외했다고 믿은 파일이 그대로 push되는 것을 신호 하나 없이 겪는다 —
    일치는 목적이 아니라 수단이라, 함께 틀리는 자리를 남기지 않는다.

    파일을 못 읽는 그 밖의 OSError와 UnicodeDecodeError는 **전파한다.** 여기서 삼키면
    제외 목록이 통째로 빈 것으로 읽혀, 사용자가 걸렀다고 믿은 파일의 해시가 그대로
    푸시된다 — 조용히 새는 것보다 시끄럽게 서는 것이 싸다.

    **바이너리로 읽고 `utf-8-sig`로 푼다**(lib/의 공통 계약). BOM을 남기면 첫 패턴에
    보이지 않는 글자가 붙어 매치 0건이 된다. 여기가 4단계 bash와 갈리는 **유일한**
    자리다 — bash의 `read -r`은 BOM을 첫 패턴에 그대로 담아 아무것도 제외하지 못한다.
    갈리는 방향이 "파이썬 쪽이 더 많이 제외한다"이므로 누수가 아니다.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return []
    text = raw.decode("utf-8-sig")
    patterns = (line.strip(" \t\r") for line in text.split("\n"))
    return [p for p in patterns if p and not p.startswith("#")]


def is_excluded(rel, patterns):
    """레포 루트 기준 상대 경로 `rel`이 4단계에서 지워지는가.

    자기 자신뿐 아니라 **모든 조상 디렉토리 경로**를 대조한다 — find가 디렉토리를
    매치하면 `rm -rf`가 그 아래를 전부 지우기 때문이다.
    """
    parts = rel.split("/")
    candidates = ["/".join(parts[:i + 1]) for i in range(len(parts))]
    return any(fnmatch.fnmatchcase(c, p) for p in patterns for c in candidates)


def filter_relpaths(rels, patterns):
    """제외되지 않은 상대 경로만 남긴다(입력 순서 보존)."""
    return [rel for rel in rels if not is_excluded(rel, patterns)]
