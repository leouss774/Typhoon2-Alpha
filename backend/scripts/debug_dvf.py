"""Debug DVF."""
import json
import sys
import urllib.request

BASE = "http://localhost:8765"

req = urllib.request.Request(
    BASE + "/diagnostic/fast",
    data=json.dumps({"adresse": "10 Promenade des Anglais, 06000 Nice", "copernicus": False}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    fast = json.loads(resp.read().decode("utf-8"))

resume = fast.get("_resume", {})
building = resume.get("building_data", {})
dvf = building.get("dvf_local")
print(f"type: {type(dvf)}, len: {len(dvf) if dvf else 0}")
if dvf:
    for tx in dvf[:3]:
        print(json.dumps(tx, ensure_ascii=False)[:300])
    types = {tx.get("type_local") for tx in dvf}
    natures = {tx.get("nature_mutation") for tx in dvf}
    print(f"types: {types}")
    print(f"natures: {natures}")

bdnb = building.get("bdnb") or {}
print(f"\nbdnb keys: {list(bdnb.keys())}")