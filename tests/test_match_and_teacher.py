"""Tests for match/round controls + teacher endpoints + safe-mode."""

import json
import os

from fastapi.testclient import TestClient

from server.game_state import GameState
from server.main import create_app


GOOD = {
    "characterName": "Tester", "color": "red", "size": 24,
    "speed": 200, "maxHealth": 100,
    "powers": [{
        "name": "Bolt", "key": "space", "cooldownMs": 600,
        "cast": {
            "kind": "projectile", "color": "red",
            "speed": 500, "radius": 8, "lifetimeMs": 1500,
            "count": 1, "spreadDeg": 0, "pierce": False,
            "onHit": [{"effect": "damage", "amount": 20}],
        },
    }],
}


def app_with_token():
    os.environ["TEACHER_TOKEN"] = "test-token"
    return create_app(GameState())


def test_round_lifecycle_and_scoreboard():
    app = app_with_token()
    with TestClient(app) as c:
        h = {"X-Teacher-Token": "test-token"}
        r = c.post("/api/teacher/start_round", headers=h, json={"durationSec": 30})
        assert r.status_code == 200
        m = r.json()["match"]
        assert m["status"] == "running"
        assert m["remaining"] > 0

        r = c.post("/api/teacher/end_round", headers=h, json={})
        assert r.status_code == 200

        s = c.get("/api/teacher/state", headers=h).json()
        assert s["match"]["status"] == "ended"


def test_teacher_endpoints_require_token():
    app = app_with_token()
    with TestClient(app) as c:
        r = c.post("/api/teacher/start_round", json={})
        assert r.status_code == 401
        r2 = c.post("/api/teacher/start_round",
                    headers={"X-Teacher-Token": "wrong"}, json={})
        assert r2.status_code == 401


def test_safe_mode_parks_join_until_approved():
    app = app_with_token()
    with TestClient(app) as c:
        h = {"X-Teacher-Token": "test-token"}
        c.post("/api/teacher/safe_mode", headers=h, json={"enabled": True})

        with c.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({
                "type": "join",
                "payload": {"username": "ada", "manifest": GOOD},
            }))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "pending"
            pending_id = msg["pendingId"]

            r = c.get("/api/teacher/state", headers=h).json()
            assert any(p["pendingId"] == pending_id for p in r["pending"])

            c.post("/api/teacher/approve", headers=h,
                   json={"pendingId": pending_id, "approved": True})

            # Drain until welcome arrives.
            for _ in range(10):
                m = json.loads(ws.receive_text())
                if m["type"] == "welcome":
                    break
            assert m["type"] == "welcome"


def test_overbudget_manifest_rejected_by_validate_endpoint():
    app = app_with_token()
    with TestClient(app) as c:
        bad = {
            "characterName": "OP", "color": "red", "size": 8,
            "speed": 400, "maxHealth": 300,
            "powers": [
                {"name": f"P{i}", "key": k, "cooldownMs": 200,
                 "cast": {
                     "kind": "projectile", "color": "red",
                     "speed": 900, "radius": 30, "lifetimeMs": 5000,
                     "count": 6, "spreadDeg": 60, "pierce": True,
                     "onHit": [{"effect": "damage", "amount": 60}],
                 }}
                for i, k in enumerate(["space", "e", "q", "f"])
            ],
        }
        r = c.post("/api/validate", json=bad)
        assert r.status_code == 400
        j = r.json()
        assert "budget" in (j["error"] or "").lower()
        # Report should still be returned so the student can see why.
        assert j.get("report") and j["report"]["total"] > 100


def test_overbudget_join_via_websocket_rejected():
    app = app_with_token()
    with TestClient(app) as c:
        op = dict(GOOD)
        op["maxHealth"] = 300
        op["speed"] = 400
        op["powers"] = [{
            "name": "Spam", "key": "space", "cooldownMs": 200,
            "cast": {
                "kind": "projectile", "color": "red",
                "speed": 900, "radius": 30, "lifetimeMs": 5000,
                "count": 6, "spreadDeg": 60, "pierce": True,
                "onHit": [{"effect": "damage", "amount": 60}],
            },
        }]
        with c.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({
                "type": "join",
                "payload": {"username": "op", "manifest": op},
            }))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "join_error"
            assert "budget" in msg["error"].lower()


def test_balance_endpoint_returns_report_for_any_valid_schema():
    """Even if over budget, /api/balance still returns the breakdown so the
    editor can show the cost report."""
    app = app_with_token()
    with TestClient(app) as c:
        r = c.post("/api/balance", json=GOOD)
        assert r.status_code == 200
        j = r.json()
        assert j["ok"] is True
        assert "total" in j["report"]
