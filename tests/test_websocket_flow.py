"""Integration test for the WebSocket flow."""

import json
import time

from fastapi.testclient import TestClient

from server.main import create_app
from server.game_state import GameState


GOOD_MANIFEST = {
    "characterName": "Tester",
    "color": "red",
    "size": 24,
    "speed": 200,
    "maxHealth": 100,
    "powers": [{
        "name": "Bolt", "key": "space", "cooldownMs": 300,
        "cast": {
            "kind": "projectile", "color": "red",
            "speed": 500, "radius": 8, "lifetimeMs": 1500,
            "count": 1, "spreadDeg": 0, "pierce": False,
            "onHit": [{"effect": "damage", "amount": 15}],
        },
    }],
}


def test_health_endpoint():
    app = create_app(GameState())
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True


def test_validate_endpoint_ok_and_bad():
    app = create_app(GameState())
    with TestClient(app) as c:
        r = c.post("/api/validate", json=GOOD_MANIFEST)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        bad = dict(GOOD_MANIFEST, maxHealth=999_999)
        r2 = c.post("/api/validate", json=bad)
        assert r2.status_code == 400


def test_manual_route_serves_html():
    app = create_app(GameState())
    with TestClient(app) as c:
        r = c.get("/manual")
        assert r.status_code == 200
        assert "Power Manual" in r.text


def test_ws_join_and_state_broadcast():
    app = create_app(GameState())
    with TestClient(app) as c:
        with c.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({
                "type": "join",
                "payload": {"username": "ada", "manifest": GOOD_MANIFEST},
            }))
            got_welcome = False
            got_state = False
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and not (got_welcome and got_state):
                msg = json.loads(ws.receive_text())
                if msg["type"] == "welcome":
                    got_welcome = True
                    assert msg["you"]["username"] == "ada"
                elif msg["type"] == "state":
                    got_state = True
                    pls = msg["payload"]["players"]
                    assert any(p["username"] == "ada" for p in pls)
            assert got_welcome and got_state


def test_ws_rejects_bad_join():
    app = create_app(GameState())
    with TestClient(app) as c:
        with c.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({
                "type": "join",
                "payload": {"username": "ada", "manifest": {"bad": True}},
            }))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "join_error"


def test_ws_input_and_fire_flow():
    app = create_app(GameState())
    with TestClient(app) as c:
        with c.websocket_connect("/ws") as ws_a, c.websocket_connect("/ws") as ws_b:
            ws_a.send_text(json.dumps({
                "type": "join",
                "payload": {"username": "alice", "manifest": GOOD_MANIFEST},
            }))
            ws_b.send_text(json.dumps({
                "type": "join",
                "payload": {"username": "bob", "manifest": GOOD_MANIFEST},
            }))
            for ws in (ws_a, ws_b):
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    m = json.loads(ws.receive_text())
                    if m["type"] == "welcome":
                        break

            ws_a.send_text(json.dumps({"type": "input", "payload": {"mx": 1, "my": 0}}))
            ws_a.send_text(json.dumps({"type": "fire", "payload": {"key": "space"}}))

            saw_proj = False
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and not saw_proj:
                m = json.loads(ws_b.receive_text())
                if m["type"] == "state" and m["payload"]["projectiles"]:
                    saw_proj = True
            assert saw_proj
