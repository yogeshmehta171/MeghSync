"""Live check of the RUNNING backend: calm at 0 rain, staged flooding at 90 mm/hr, forecast, reset, blocked-node routing.

Start the backend first (uvicorn app.main:app --port 8000), then in another window:

    python live_model_test.py --user YOUR_ADMIN_ID

It asks for the password. Takes about 4 minutes. It leaves the system reset with rain 0 and no block added by this test.
Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import getpass
import json
import math
import sys
import time
import urllib.error
import urllib.request

FLOOD_M = 0.15            # same 15 cm line the app uses for "street is flooded"
results: list[tuple[str, str, str]] = []


def say(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""), flush=True)


class Api:
    def __init__(self, base: str):
        self.base, self.token = base.rstrip("/"), None

    def call(self, method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode()).get("detail", e.reason)
            except Exception:
                detail = e.reason
            raise RuntimeError(f"{method} {path} -> {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach {self.base} ({e.reason}). Is the backend running?")

    def overview(self):
        return self.call("GET", "/api/admin/overview")["data"]

    def nodes(self, hours=0):
        return self.call("GET", f"/api/admin/nodes?hours={hours}")["data"]


def flooded(nodes) -> int:
    return sum(1 for n in nodes if not n.get("blocked") and n["depth"] >= FLOOD_M)


def seg_dist_m(p, a, b) -> float:
    """Distance in metres from point p to segment a-b. All points are (lat, lon)."""
    k = math.cos(math.radians(p[0])) * 111320.0
    ax, ay, bx, by = (a[1] - p[1]) * k, (a[0] - p[0]) * 110540.0, (b[1] - p[1]) * k, (b[0] - p[0]) * 110540.0
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def path_dist_m(p, path) -> float:
    return min(seg_dist_m(p, path[i], path[i + 1]) for i in range(len(path) - 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", help="omit to be asked (safer)")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between samples")
    ap.add_argument("--calm-seconds", type=float, default=60.0)
    ap.add_argument("--rain-seconds", type=float, default=120.0)
    a = ap.parse_args()
    api = Api(a.url)
    pw = a.password or getpass.getpass("Password: ")

    try:
        api.token = api.call("POST", "/api/auth/login", {"municipality_id": a.user, "password": pw})["token"]
        print("Logged in.\n")
        api.call("POST", "/api/admin/reset", {"clear_blocks": False})
        api.call("POST", "/api/admin/rain", {"rain_mm_hr": 0})
        time.sleep(8)

        # 1 ---------------------------------------------------------------- calm
        print("1. Rain 0: the map should stay calm")
        worst, worst_n = 0.0, 0
        t_end = time.time() + a.calm_seconds
        while time.time() < t_end:
            o = api.overview()
            worst, worst_n = max(worst, o["maxFloodM"]), max(worst_n, o["floodedNodes"])
            time.sleep(a.interval)
        say("PASS" if worst < 0.05 and worst_n == 0 else "FAIL", "calm at 0 mm/hr",
            f"deepest flood {worst:.3f} m, most flooded nodes {worst_n} over {a.calm_seconds:.0f} s")

        # 2 ---------------------------------------------------------------- staged flooding
        print("\n2. Rain 90 mm/hr: flooding should build in stages")
        api.call("POST", "/api/admin/rain", {"rain_mm_hr": 90})
        series, t_end = [], time.time() + a.rain_seconds
        while time.time() < t_end:
            time.sleep(a.interval)
            o = api.overview()
            series.append((o["floodedNodes"], o["maxFloodM"]))
            print(f"     {len(series) * a.interval:5.0f} s: flooded nodes {o['floodedNodes']:4d}, deepest {o['maxFloodM']:.2f} m", flush=True)
        counts = [c for c, _ in series]
        final = counts[-1]
        rising = all(counts[i + 1] >= counts[i] - 5 for i in range(len(counts) - 1))
        say("PASS" if final > 0 and rising and counts[0] < 0.9 * final else "FAIL" if final == 0 else "CHECK",
            "floods in stages", f"{counts[0]} nodes after first sample -> {final} at the end (rising={rising})")

        # 3 ---------------------------------------------------------------- forecast
        print("\n3. Forecast scrubber (+1h, +2h, +3h)")
        now_n = flooded(api.nodes(0))
        per = {h: flooded(api.nodes(h)) for h in (1, 2, 3)}
        o = api.overview()
        say("PASS" if len(set(per.values()) | {now_n}) > 1 else "FAIL", "forecast differs from now",
            f"flooded nodes now {now_n}, +1h {per[1]}, +2h {per[2]}, +3h {per[3]}")
        print("     deepest flood per horizon: " + ", ".join(f"+{f['hours']}h {f['maxFloodM']:.2f} m" for f in o["forecast"]))

        # 4 ---------------------------------------------------------------- reset
        print("\n4. Reset: rain and flooding should clear")
        api.call("POST", "/api/admin/reset", {"clear_blocks": False})
        api.call("POST", "/api/admin/rain", {"rain_mm_hr": 0})
        left = None
        for _ in range(8):
            time.sleep(5)
            left = api.overview()["floodedNodes"]
            if left == 0:
                break
        say("PASS" if left == 0 else "FAIL", "flooding cleared after reset", f"flooded nodes now {left}")

        # 5 ---------------------------------------------------------------- block + route
        print("\n5. Block a node on the route, then route again")
        nodes = api.nodes(0)
        free = [n for n in nodes if not n.get("blocked")]
        s, d = min(free, key=lambda n: n["coordinates"][0]), max(free, key=lambda n: n["coordinates"][0])
        body = {"start": {"lat": s["coordinates"][0], "lon": s["coordinates"][1]},
                "destination": {"lat": d["coordinates"][0], "lon": d["coordinates"][1]}}
        r1 = api.call("POST", "/api/route", body)
        path1 = r1["safe"]["path"]
        mid = path1[len(path1) // 2]
        cand = [n for n in free if n["id"] not in (s["id"], d["id"])]
        target = min(cand, key=lambda n: (n["coordinates"][0] - mid[0]) ** 2 + (n["coordinates"][1] - mid[1]) ** 2)
        tp = tuple(target["coordinates"])
        before = path_dist_m(tp, path1)
        print(f"     route {s['id']} -> {d['id']}: {r1['safe']['lengthM']:.0f} m; blocking {target['id']} ({before:.0f} m from the route)")
        blocked_here = False
        try:
            api.call("POST", "/api/admin/blocks", {"node_id": target["id"]})
            blocked_here = True
            time.sleep(7)
            r2 = api.call("POST", "/api/route", body)
            after = path_dist_m(tp, r2["safe"]["path"])
            changed = r2["safe"]["path"] != path1
            if after > before + 10 or (changed and after > 20):
                say("PASS", "route avoids the blocked node", f"distance to node {before:.0f} m -> {after:.0f} m; length {r1['safe']['lengthM']:.0f} -> {r2['safe']['lengthM']:.0f} m")
            else:
                say("CHECK", "route did not move away", f"still {after:.0f} m from the node; that street may have no alternative. Try the check by hand on a busier junction")
        finally:
            if blocked_here:
                api.call("DELETE", f"/api/admin/blocks/{target['id']}")
                print(f"     released {target['id']} again")
    except RuntimeError as e:
        say("FAIL", "test stopped", str(e))
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        try:
            api.call("POST", "/api/admin/rain", {"rain_mm_hr": 0})
        except Exception:
            pass

    bad = [r for r in results if r[0] == "FAIL"]
    chk = [r for r in results if r[0] == "CHECK"]
    print("\nRESULT: " + ("all checks passed" if not bad and not chk else f"{len(bad)} failed, {len(chk)} need a look"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
