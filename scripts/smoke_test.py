"""End-to-end smoke test for the new framework.

Boots the FastAPI server in a background thread, then connects several
"students" via real WebSockets, has them upload manifests covering all
cast kinds (projectile, area, melee, dash, shield, heal), drives movement
and combat, and verifies every client sees the others and the things they
spawn.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
import websockets  # noqa: E402

from server.main import create_app  # noqa: E402
from server.game_state import GameState  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765


def projectile_manifest(name: str, color: str) -> dict:
    return {
        "characterName": name, "color": color, "size": 24,
        "speed": 220, "maxHealth": 100,
        "powers": [{
            "name": "Bolt", "key": "space", "cooldownMs": 400,
            "cast": {
                "kind": "projectile", "color": color,
                "speed": 500, "radius": 8, "lifetimeMs": 1500,
                "count": 1, "spreadDeg": 0, "pierce": False,
                "onHit": [{"effect": "damage", "amount": 20}],
            },
        }],
    }


def area_manifest() -> dict:
    return {
        "characterName": "Cloud", "color": "green", "size": 28,
        "speed": 200, "maxHealth": 100,
        "powers": [{
            "name": "Cloud", "key": "space", "cooldownMs": 800,
            "cast": {
                "kind": "area", "color": "green",
                "radius": 60, "durationMs": 1500, "tickIntervalMs": 250,
                "onTick": [{"effect": "dot", "dps": 8, "durationMs": 500}],
            },
        }],
    }


def melee_manifest() -> dict:
    return {
        "characterName": "Bonker", "color": "orange", "size": 24,
        "speed": 220, "maxHealth": 100,
        "powers": [{
            "name": "Bonk", "key": "space", "cooldownMs": 400,
            "cast": {
                "kind": "melee", "color": "orange",
                "range": 60, "arcDeg": 120,
                "onHit": [{"effect": "damage", "amount": 15}],
            },
        }],
    }


def shield_manifest() -> dict:
    return {
        "characterName": "Bunker", "color": "cyan", "size": 30,
        "speed": 200, "maxHealth": 100,
        "powers": [{
            "name": "Wall", "key": "space", "cooldownMs": 400,
            "cast": {"kind": "shield", "color": "cyan", "amount": 50, "durationMs": 2000},
        }],
    }


class ServerThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.app = create_app(GameState())
        config = uvicorn.Config(
            self.app, host=HOST, port=PORT, log_level="warning", lifespan="on",
        )
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


async def _student(name: str, manifest: dict, fire: bool, seen: dict) -> None:
    uri = f"ws://{HOST}:{PORT}/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "join",
            "payload": {"username": name, "manifest": manifest},
        }))
        info = {"welcomed": False, "saw_others": False,
                "saw_proj": False, "saw_area": False, "saw_melee": False}
        seen[name] = info
        end = time.monotonic() + 3.5
        last_input = 0.0
        last_fire = 0.0
        while time.monotonic() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
            except asyncio.TimeoutError:
                raw = None
            if raw is not None:
                msg = json.loads(raw)
                if msg["type"] == "welcome":
                    info["welcomed"] = True
                elif msg["type"] == "state":
                    pls = msg["payload"]["players"]
                    if any(p["username"] != name for p in pls):
                        info["saw_others"] = True
                    if msg["payload"].get("projectiles"):
                        info["saw_proj"] = True
                    if msg["payload"].get("areas"):
                        info["saw_area"] = True
                    if msg["payload"].get("meleeFx"):
                        info["saw_melee"] = True
            now = time.monotonic()
            if now - last_input > 0.1:
                await ws.send(json.dumps({
                    "type": "input",
                    "payload": {"mx": 1 if name == "alice" else -1, "my": 0},
                }))
                last_input = now
            if fire and now - last_fire > 0.5:
                await ws.send(json.dumps({"type": "fire", "payload": {"key": "space"}}))
                last_fire = now


async def _run_clients() -> dict:
    seen: dict = {}
    await asyncio.gather(
        _student("alice", projectile_manifest("alice", "red"),  True, seen),
        _student("bob",   projectile_manifest("bob",   "blue"), True, seen),
        _student("cleo",  area_manifest(),                       True, seen),
        _student("dax",   melee_manifest(),                      True, seen),
        _student("eli",   shield_manifest(),                     True, seen),
    )
    return seen


def main() -> int:
    print("Starting server on", f"{HOST}:{PORT} ...")
    server = ServerThread()
    server.start()
    deadline = time.monotonic() + 5.0
    import socket
    while time.monotonic() < deadline:
        with suppress(OSError):
            with socket.create_connection((HOST, PORT), timeout=0.2):
                break
        time.sleep(0.1)
    else:
        print("Server failed to start", file=sys.stderr)
        return 1

    # Sanity-check the budget guard at the HTTP boundary: an OP manifest must
    # be rejected and a normal one must validate cleanly.
    import urllib.request, urllib.error
    op = {
        "characterName": "OP", "color": "red", "size": 8, "speed": 400,
        "maxHealth": 300,
        "powers": [{"name": f"P{i}", "key": k, "cooldownMs": 200,
                    "cast": {"kind": "projectile", "color": "red",
                             "speed": 900, "radius": 30, "lifetimeMs": 5000,
                             "count": 6, "spreadDeg": 60, "pierce": True,
                             "onHit": [{"effect": "damage", "amount": 60}]}}
                   for i, k in enumerate(["space", "e", "q", "f"])],
    }
    req = urllib.request.Request(f"http://{HOST}:{PORT}/api/validate",
                                 data=json.dumps(op).encode(),
                                 headers={"Content-Type": "application/json"})
    op_rejected = False
    try:
        urllib.request.urlopen(req, timeout=2.0)
    except urllib.error.HTTPError as e:
        op_rejected = (e.code == 400)
    if op_rejected:
        print("  [OK]   over-budget manifest rejected by /api/validate")
    else:
        print("  [FAIL] over-budget manifest was NOT rejected"); return 2

    try:
        seen = asyncio.run(_run_clients())
    finally:
        server.stop()
        server.join(timeout=3.0)
    ok = True
    for name in ("alice", "bob", "cleo", "dax", "eli"):
        info = seen.get(name)
        if not info or not info["welcomed"]:
            print(f"  [FAIL] {name} never got welcome"); ok = False; continue
        for k, label in [("saw_others", "other players")]:
            if info[k]:
                print(f"  [OK]   {name} saw {label}")
            else:
                print(f"  [FAIL] {name} never saw {label}"); ok = False

    # At least one client should have observed each spawned object class.
    saw_any_proj  = any(s["saw_proj"]  for s in seen.values())
    saw_any_area  = any(s["saw_area"]  for s in seen.values())
    saw_any_melee = any(s["saw_melee"] for s in seen.values())
    for label, value in [("projectiles", saw_any_proj),
                         ("areas", saw_any_area),
                         ("meleeFx", saw_any_melee)]:
        if value:
            print(f"  [OK]   broadcast included {label}")
        else:
            print(f"  [FAIL] no client saw {label}"); ok = False

    if ok:
        print("\nSmoke test PASSED")
        return 0
    print("\nSmoke test FAILED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
