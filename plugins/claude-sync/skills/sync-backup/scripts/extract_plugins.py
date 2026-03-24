#!/usr/bin/env python3
"""settings.json에서 플러그인/마켓플레이스 목록만 추출하여 plugins.json으로 저장한다."""
import json, os, sys

settings_path = os.path.expanduser("~/.claude/settings.json")
output_path = sys.argv[1] if len(sys.argv) > 1 else "plugins.json"

with open(settings_path) as f:
    data = json.load(f)

result = {}
if "enabledPlugins" in data:
    result["enabledPlugins"] = data["enabledPlugins"]
if "extraKnownMarketplaces" in data:
    result["extraKnownMarketplaces"] = data["extraKnownMarketplaces"]

with open(output_path, "w") as f:
    json.dump(result, f, indent=2)
    f.write("\n")
