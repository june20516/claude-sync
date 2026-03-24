#!/usr/bin/env python3
"""claude mcp list의 출력(stdin)과 mcp-servers.json을 비교하여 차이를 출력한다."""
import sys, json, re

mcp_json_path = sys.argv[1] if len(sys.argv) > 1 else "mcp-servers.json"

# 현재 등록된 서버 파싱
current = set()
for line in sys.stdin:
    m = re.match(r"^(.+?):\s+", line.strip())
    if m:
        current.add(m.group(1).strip())

# 백업된 서버 로드
with open(mcp_json_path) as f:
    backed = json.load(f)
backed_names = {s["name"] for s in backed}

only_repo = backed_names - current
only_local = current - backed_names

if only_repo or only_local:
    print("\nMCP 서버 차이:")
    for s in only_repo:
        print("  + 레포에만: " + s)
    for s in only_local:
        print("  - 로컬에만: " + s)
else:
    print("\nMCP 서버: 동일")
