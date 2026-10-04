"""Manual end-to-end check against a running server.
Start the server, then from backend/:  python scripts/smoke.py [base_url]"""
import sys
import time

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
client = httpx.Client(base_url=base, timeout=180)
body = {"placements": [
    {"id": "bag-1", "type": "bag", "coordinates": [-140.6, 32.4]},
    {"id": "bottle-1", "type": "bottle", "coordinates": [-140.2, 32.1]},
    {"id": "collector-1", "type": "collector", "coordinates": [-140.1, 32.1]},
], "durationDays": 7}

health = client.get("/api/health").json()
print("health:", health)
assert health["db"] is True, "database not connected"

started = time.monotonic()
compared = client.post("/api/compare", json=body).json()
print(f"compare: {time.monotonic() - started:.1f}s  delta {compared['delta']}")
run = compared["with"]
print("source:", [s["source"] for s in run["snapshots"]], " persisted:", run["persisted"])
assert run["persisted"] is True, "run was not stored"
assert all(s["source"] == "copernicus" for s in run["snapshots"]), "fell back to synthetic currents"

replay = client.get(f"/api/runs/{run['runId']}").json()
assert replay == run, "replay from Tiger differs from the original run"

timeline = client.get(f"/api/runs/{run['runId']}/timeline").json()
assert len(timeline["buckets"]) == 7 * 24 + 1, f"expected 169 hourly buckets, got {len(timeline['buckets'])}"
assert all(sum(b[k] for k in ("floating", "captured", "beached", "outside")) == 2 for b in timeline["buckets"])

started = time.monotonic()
client.post("/api/simulate", json=body)
print(f"second run (snapshots cached): {time.monotonic() - started:.1f}s")
print("PASS")
