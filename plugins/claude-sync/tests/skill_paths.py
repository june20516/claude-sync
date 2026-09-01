"""세 SKILL.md의 위치와 이름. 스킬 계약을 재는 테스트 파일들이 공유한다.

`test_script_root.py`(SKILL.md를 **실행해서** 잰다)와 `test_skill_wiring.py`(SKILL.md를
**읽어서** 잰다)가 같은 목록을 쓴다. **목록이 두 벌이면 안 된다** — 넷째 스킬이 생겼을 때
`test_skill_wiring.py`의 test_every_skill_on_disk_is_covered_by_the_contract는 디스크와
대조하므로 빨개지지만, 그것을 고치는 사람이 자기 파일의 목록만 고치면 다른 파일의
파라미터화는 그 스킬을 아무 소리 없이 빠져나간다.
"""
import os

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")
SKILLS = ["sync-backup", "sync-status", "sync-restore"]
