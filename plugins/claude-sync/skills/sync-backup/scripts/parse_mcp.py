#!/usr/bin/env python3
"""claude mcp list의 출력을 stdin으로 받아 name, url, type을 추출하여 JSON으로 저장한다."""
import sys, json, re

output_path = sys.argv[1] if len(sys.argv) > 1 else "mcp-servers.json"

servers = []
for line in sys.stdin:
    line = line.strip()
    m = re.match(r"^(.+?):\s+(\S+)\s+(?:\((\w+)\)\s+)?-\s+.+$", line)
    if m:
        servers.append({
            "name": m.group(1).strip(),
            "url": m.group(2).strip(),
            "type": m.group(3) or "stdio"
        })

with open(output_path, "w") as f:
    json.dump(servers, f, indent=2)
    f.write("\n")
