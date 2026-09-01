"""2.x가 백업 문서를 다시 만드는 방식 — 실측. 산문 가드 둘이 공유한다.

`test_skill_wiring.py`(sync-restore 2.5의 손실 표)와 `test_user_docs.py`(배포 순서 경고
다섯 벌)가 **같은 측정**을 인용한다. 두 벌로 두면 한쪽만 고친 정정이 나머지를 남긴다 —
`skill_paths.py`가 스킬 목록에서 막는 것과 같은 형태다.

**저장소 안에 기계로 대조할 원천이 없다.** 2.x의 스크립트는 `main`에만 있고 릴리즈 뒤에는
그것도 사라진다. 그래서 **값을 핀하고**, 그 이름이 오늘의 어댑터에 실재하는지만 기계로
묻는다(각 사용처의 단정). 근거는 실측이다:

- `plugins.json` — `git show main:…/scripts/extract_plugins.py`. 로컬 `settings.json`에서
  아래 두 키만 복사해 통째로 쓴다. 나머지 키는 2.x가 아예 모른다.
- `mcp-servers.json` — `git show main:…/scripts/parse_mcp.py`. 그 기기의 `claude mcp list`
  출력만으로 배열을 통째로 만든다. **키 목록이 아니라 문서 전체**가 그 기기 것으로
  대체되므로 "옮기는 키"라는 개념 자체가 없다 — 그래서 이 상수는 plugins 쪽만 다룬다.

두 문서의 공통 결과는 같다: **다른 기기에만 있는 항목이 레포에서 사라진다.**
"""

TWO_X_CARRIES = ("enabledPlugins", "extraKnownMarketplaces")
