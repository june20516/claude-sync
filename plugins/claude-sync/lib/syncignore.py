#!/usr/bin/env python3
"""`.syncignore` 매칭 규칙 한 벌. sync-backup/SKILL.md 4단계의 `find -path`와 같다.

**왜 여기 있는가.** 4단계는 레포 작업 트리에서 `find … | rm -rf`로 파일을 지우는데,
7단계의 generate_metadata.py는 `~/.claude`를 **직접 걷는다.** 필터가 없으면 사용자가
제외한 파일의 **이름과 sha256이 푸시되는 `sync-metadata.json`에 남는다** — 걸렀다고
믿은 채로 푸시하는 조용한 fail-open이다. 두 곳이 각자 매칭을 만들면 그 어긋남이
다시 조용해지므로 규칙을 이 파일 하나에 둔다.

**bash 쪽은 이 함수를 부를 수 없다**(`find`다). 그래서 대응이 깨지는 것을 잡는 것은
test_script_root.py의 `test_python_syncignore_matches_the_skill_bash`다 — 같은 픽스처에
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
5·6단계가 다시 생성하므로 `.syncignore`로 제외할 수 없다. 그 둘의 민감 값은 어댑터의
마스킹이 담당한다(sync-backup/SKILL.md 「보안」절에 적혀 있다).
"""
import fnmatch
import os

DEFAULT_RELPATH = ".syncignore"


def default_path(claude_dir):
    """`~/.claude` 역할 디렉토리 안의 `.syncignore` 경로."""
    return os.path.join(claude_dir, DEFAULT_RELPATH)


def load_patterns(path):
    """`.syncignore`의 패턴 목록. 파일이 없으면 빈 목록.

    4단계 bash와 같은 규칙이다 — **줄을 다듬지 않는다.** bash 쪽은
    `[[ -z "$pattern" || "$pattern" == \\#* ]]`로 **빈 줄과 `#`으로 시작하는 줄만**
    거르고 나머지는 원문 그대로 `find`에 넘긴다. 여기서 strip()을 하면 앞뒤 공백이
    붙은 줄에서 두 구현의 판정이 갈린다.

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
    return [line for line in text.split("\n") if line and not line.startswith("#")]


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
