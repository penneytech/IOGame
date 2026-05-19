"""FastAPI app: HTTP endpoints, static file serving, and the game WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Dict

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    AttemptTracker,
    COOKIE_NAME,
    COOKIE_MAX_AGE,
    PasswordGateMiddleware,
    client_ip,
    get_password,
    get_secret,
    make_cookie_value,
    ws_is_authed,
)
from .balance import build_report
from .bot_runner import LiveBotSwarm, set_ai_logging, get_ai_logging_status
from .game_state import GameState
from .protocol import (
    C2S_FIRE,
    C2S_INPUT,
    C2S_JOIN,
    C2S_PING,
    C2S_ROLL,
    S2C_EVENT,
    S2C_JOIN_ERROR,
    S2C_PENDING,
    S2C_PONG,
    S2C_STATE,
    S2C_WELCOME,
)
from .validation import validate_join, validate_manifest

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
LESSONS_DIR = ROOT / "lessons"

TICK_RATE = 30  # Hz
TICK_DT = 1.0 / TICK_RATE

log = logging.getLogger("classroom_io_game")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def create_app(game: GameState | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Print the teacher token exactly once at real server start.
        if not app.state.teacher_token_from_env:
            log.info("=" * 60)
            log.info("TEACHER TOKEN: %s   (use as ?token=... or X-Teacher-Token)",
                     app.state.teacher_token)
            log.info("=" * 60)
        app.state.tick_task = asyncio.create_task(_tick_loop(app))
        try:
            yield
        finally:
            t: asyncio.Task | None = app.state.tick_task
            if t is not None:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            try:
                await app.state.bot_swarm.stop()
            except Exception:
                pass

    app = FastAPI(title="Classroom IO Game", lifespan=lifespan)
    app.add_middleware(PasswordGateMiddleware)
    app.state.attempt_tracker = AttemptTracker()
    app.state.game = game or GameState()
    app.state.connections: Dict[str, WebSocket] = {}
    app.state.spectators: set[WebSocket] = set()
    app.state.tick_task = None
    # Teacher token: read from env, else generate one. Print happens in
    # lifespan startup so uvicorn --reload (which imports the module twice)
    # only logs the token once.
    token = os.environ.get("TEACHER_TOKEN") or secrets.token_urlsafe(8)
    app.state.teacher_token = token
    app.state.teacher_token_from_env = bool(os.environ.get("TEACHER_TOKEN"))
    # Map pending_id -> websocket for safe-mode approvals.
    app.state.pending_sockets: Dict[str, WebSocket] = {}
    app.state.pending_meta: Dict[str, dict] = {}
    # Optional 20-bot demo swarm (teacher dashboard button).
    app.state.bot_swarm = LiveBotSwarm(app.state.game)

    # --- HTTP routes ----------------------------------------------------

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # --- Public auth endpoints (excluded from password gate) -----------

    @app.get("/login")
    async def login_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "login.html")

    @app.post("/api/login")
    async def api_login(payload: dict, request: Request) -> JSONResponse:
        tracker: AttemptTracker = app.state.attempt_tracker
        ip = client_ip(request)
        locked, remaining = tracker.is_locked(ip)
        if locked:
            return JSONResponse(
                {"ok": False, "error": "locked", "lockedSeconds": int(remaining)},
                status_code=429,
            )
        submitted = str(payload.get("password", ""))
        if secrets.compare_digest(submitted, get_password()):
            tracker.clear(ip)
            secret = get_secret(app.state)
            resp = JSONResponse({"ok": True})
            resp.set_cookie(
                COOKIE_NAME,
                make_cookie_value(secret),
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https",
                path="/",
            )
            return resp
        used, locked_for = tracker.record_failure(ip)
        remaining_tries = max(0, 5 - used)
        if locked_for:
            return JSONResponse(
                {"ok": False, "error": "locked", "lockedSeconds": int(locked_for)},
                status_code=429,
            )
        return JSONResponse(
            {"ok": False, "error": "wrong", "attemptsRemaining": remaining_tries},
            status_code=401,
        )

    @app.post("/api/logout")
    async def api_logout() -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp

    @app.get("/teacher")
    async def teacher_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "teacher.html")

    @app.get("/student")
    async def student_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "student.html")

    @app.get("/game")
    async def game_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "game.html")

    @app.get("/manual")
    async def manual_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "manual.html")

    @app.get("/challenges")
    async def challenges_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "challenges.html")

    @app.get("/lessons")
    @app.get("/lessons/")
    async def lessons_index() -> FileResponse:
        # Serve the index as raw markdown wrapped in a tiny HTML viewer.
        return FileResponse(STATIC_DIR / "lessons.html")

    @app.get("/lessons/{name}")
    async def lesson_file(name: str):
        # Only allow plain .md filenames inside the lessons folder.
        from fastapi import HTTPException
        if "/" in name or "\\" in name or ".." in name:
            raise HTTPException(status_code=400, detail="bad name")
        if not name.endswith(".md"):
            raise HTTPException(status_code=404, detail="not found")
        path = LESSONS_DIR / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type="text/markdown; charset=utf-8")

    @app.get("/spectator")
    async def spectator_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "spectator.html")

    @app.get("/api/health")
    async def health() -> JSONResponse:
        g: GameState = app.state.game
        return JSONResponse({
            "ok": True,
            "tick": g.tick,
            "players": len(g.players),
            "projectiles": len(g.projectiles),
        })

    @app.post("/api/validate")
    async def http_validate(payload: dict) -> JSONResponse:
        ok, result = validate_manifest(payload)
        if not ok:
            # Try to also return a balance report when the failure was budget,
            # so the student sees the breakdown.
            try:
                from .models import CharacterManifest
                m = CharacterManifest.model_validate(payload)
                report = build_report(m)
            except Exception:
                report = None
            return JSONResponse(
                {"ok": False, "error": result, "report": report},
                status_code=400,
            )
        manifest, report = result
        return JSONResponse({
            "ok": True,
            "manifest": manifest.model_dump(),
            "report": report,
        })

    @app.post("/api/balance")
    async def http_balance(payload: dict) -> JSONResponse:
        """Compute a balance report without rejecting on over-budget."""
        try:
            from .models import CharacterManifest
            m = CharacterManifest.model_validate(payload)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        return JSONResponse({"ok": True, "report": build_report(m)})

    # --- Teacher controls (token-protected) ----------------------------

    def _check_token(token: str | None) -> None:
        if not token or not secrets.compare_digest(token, app.state.teacher_token):
            raise HTTPException(status_code=401, detail="bad teacher token")

    @app.post("/api/teacher/start_round")
    async def teacher_start(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        duration = float(payload.get("durationSec", 120.0))
        mode = payload.get("mode")
        lives = payload.get("lives")
        try:
            app.state.game.start_round(duration, mode=mode,
                                       lives=int(lives) if lives is not None else None)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True, "match": app.state.game._match_public(time.monotonic())}

    @app.post("/api/teacher/end_round")
    async def teacher_end(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        app.state.game.end_round()
        return {"ok": True}

    @app.post("/api/teacher/reset")
    async def teacher_reset(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        app.state.game.reset_arena()
        return {"ok": True}

    @app.post("/api/teacher/clear_projectiles")
    async def teacher_clear(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        app.state.game.clear_projectiles()
        return {"ok": True}

    @app.post("/api/teacher/kick")
    async def teacher_kick(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        pid = str(payload.get("pid", ""))
        ok = app.state.game.kick(pid)
        ws = app.state.connections.pop(pid, None)
        if ws is not None:
            try: await ws.close()
            except Exception: pass
        return {"ok": ok}

    @app.post("/api/teacher/safe_mode")
    async def teacher_safe(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        app.state.game.safe_mode = bool(payload.get("enabled", False))
        return {"ok": True, "safeMode": app.state.game.safe_mode}

    @app.post("/api/teacher/spawn_bots")
    async def teacher_spawn_bots(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        swarm: LiveBotSwarm = app.state.bot_swarm
        if swarm.running:
            return {"ok": True, "running": True, "count": swarm.count, "alreadyRunning": True}
        count = payload.get("count")
        try:
            count = int(count) if count is not None else None
        except (TypeError, ValueError):
            count = None
        # Resolve hunt target by username (case-insensitive) if provided.
        hunt_username = (payload.get("huntUsername") or "").strip().lower()
        hunt_pid = (payload.get("huntPid") or "").strip()
        game = app.state.game
        if hunt_username and not hunt_pid:
            for pl in game.players.values():
                if pl.username.lower() == hunt_username:
                    hunt_pid = pl.pid
                    break
        game.bot_hunt_pid = hunt_pid or ""
        spawned = swarm.spawn(count)
        swarm.start()
        return {"ok": True, "running": True, "count": spawned,
                "huntPid": game.bot_hunt_pid}

    @app.post("/api/teacher/stop_bots")
    async def teacher_stop_bots(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        swarm: LiveBotSwarm = app.state.bot_swarm
        removed = await swarm.stop()
        return {"ok": True, "running": False, "removed": removed}

    @app.get("/api/teacher/bots_status")
    async def teacher_bots_status(token: str | None = None,
                                  x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or token)
        swarm: LiveBotSwarm = app.state.bot_swarm
        return {"ok": True, "running": swarm.running, "count": swarm.count}

    @app.post("/api/teacher/ai_logging")
    async def teacher_ai_logging(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        info = set_ai_logging(bool(payload.get("enabled", False)))
        return {"ok": True, **info}

    @app.get("/api/teacher/ai_logging")
    async def teacher_ai_logging_status(token: str | None = None,
                                        x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or token)
        return {"ok": True, **get_ai_logging_status()}

    @app.get("/api/teacher/pending")
    async def teacher_pending(token: str | None = None,
                              x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or token)
        return {"ok": True, "pending": list(app.state.pending_meta.values())}

    @app.get("/api/teacher/state")
    async def teacher_state(token: str | None = None,
                            x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or token)
        g: GameState = app.state.game
        return {
            "ok": True,
            "match": g._match_public(time.monotonic()),
            "players": [
                {
                    "pid": p.pid, "username": p.username,
                    "characterName": p.manifest.characterName,
                    "color": p.manifest.color,
                    "kills": p.kills, "deaths": p.deaths,
                    "alive": p.alive,
                }
                for p in g.players.values()
            ],
            "pending": list(app.state.pending_meta.values()),
        }

    @app.post("/api/teacher/approve")
    async def teacher_approve(payload: dict, x_teacher_token: str | None = Header(default=None)):
        _check_token(x_teacher_token or payload.get("token"))
        pending_id = str(payload.get("pendingId", ""))
        approved = bool(payload.get("approved", False))
        meta = app.state.pending_meta.pop(pending_id, None)
        ws = app.state.pending_sockets.pop(pending_id, None)
        if ws is None or meta is None:
            return {"ok": False, "error": "unknown pendingId"}
        app.state.game.pending_joins.pop(pending_id, None)
        if not approved:
            try:
                await ws.send_json({"type": S2C_JOIN_ERROR, "error": "rejected by teacher"})
                await ws.close()
            except Exception: pass
            return {"ok": True, "approved": False}
        # Approved: spawn the player.
        username, manifest = meta["username"], meta["manifest"]
        player = app.state.game.add_player(username, manifest)
        app.state.connections[player.pid] = ws
        try:
            await ws.send_json({
                "type": S2C_WELCOME,
                "pid": player.pid,
                "world": {"width": app.state.game.width, "height": app.state.game.height},
                "you": player.to_public(time.monotonic()),
            })
        except Exception: pass
        return {"ok": True, "approved": True, "pid": player.pid}

    @app.get("/api/boilerplate/{name}")
    async def boilerplate(name: str):
        # Boilerplate removed; editor starts blank.
        return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/api/example/{slug}/{name}")
    async def example_file(slug: str, name: str):
        # Example characters removed from the public API; students build
        # their own from scratch.
        return JSONResponse({"error": "not found"}, status_code=404)

    # Static files (CSS/JS for the frontend).
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- WebSocket ------------------------------------------------------

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        if not ws_is_authed(websocket, get_secret(app.state)):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        pid: str | None = None
        game: GameState = app.state.game
        try:
            # First message MUST be a join request.
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": S2C_JOIN_ERROR, "error": "invalid JSON"})
                await websocket.close()
                return
            if msg.get("type") != C2S_JOIN:
                await websocket.send_json({
                    "type": S2C_JOIN_ERROR,
                    "error": "first message must be a join",
                })
                await websocket.close()
                return
            ok, parsed = validate_join(msg.get("payload") or {})
            if not ok:
                await websocket.send_json({"type": S2C_JOIN_ERROR, "error": parsed})
                await websocket.close()
                return
            join_req, report = parsed
            # Safe mode: park this socket until a teacher approves.
            if game.safe_mode:
                pending_id = uuid.uuid4().hex[:10]
                app.state.pending_sockets[pending_id] = websocket
                app.state.pending_meta[pending_id] = {
                    "pendingId": pending_id,
                    "username": join_req.username,
                    "manifest": join_req.manifest,
                    "manifestDump": join_req.manifest.model_dump(),
                    "report": report,
                }
                game.pending_joins[pending_id] = {"username": join_req.username}
                await websocket.send_json({
                    "type": S2C_PENDING,
                    "pendingId": pending_id,
                    "message": "waiting for teacher approval",
                })
                # Block here until socket is closed (approve handler will swap it
                # into the connections dict and send welcome).
                while pending_id in app.state.pending_sockets:
                    try:
                        await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    except WebSocketDisconnect:
                        app.state.pending_sockets.pop(pending_id, None)
                        app.state.pending_meta.pop(pending_id, None)
                        game.pending_joins.pop(pending_id, None)
                        return
                # Once approved, fall through; player is already added.
                # Find the pid we were assigned.
                pid = next((p for p, w in app.state.connections.items() if w is websocket), None)
                if pid is None:
                    return
            else:
                player = game.add_player(join_req.username, join_req.manifest)
                pid = player.pid
                app.state.connections[pid] = websocket
                await websocket.send_json({
                    "type": S2C_WELCOME,
                    "pid": pid,
                    "world": {"width": game.width, "height": game.height},
                    "you": player.to_public(time.monotonic()),
                })

            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                t = msg.get("type")
                payload = msg.get("payload") or {}
                if t == C2S_INPUT:
                    game.set_input(pid, payload.get("mx", 0), payload.get("my", 0),
                                   payload.get("ax"), payload.get("ay"),
                                   sprint=payload.get("sprint"))
                elif t == C2S_FIRE:
                    game.fire(pid, str(payload.get("key", "")))
                elif t == C2S_ROLL:
                    game.roll(pid)
                elif t == C2S_PING:
                    await websocket.send_json({"type": S2C_PONG, "t": payload.get("t")})
                # Unknown types are ignored on purpose.
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001 - network-facing boundary
            log.warning("ws error: %s", e)
        finally:
            if pid is not None:
                app.state.connections.pop(pid, None)
                game.remove_player(pid)
                try:
                    await websocket.close()
                except Exception:
                    pass

    @app.websocket("/ws/spectator")
    async def ws_spectator(websocket: WebSocket) -> None:
        """Read-only firehose for the spectator/projector view.

        No join handshake, no input accepted. Receives the same S2C_STATE +
        S2C_EVENT broadcasts as players. Sends a single welcome with world
        dimensions on connect.
        """
        if not ws_is_authed(websocket, get_secret(app.state)):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        game: GameState = app.state.game
        try:
            await websocket.send_json({
                "type": S2C_WELCOME,
                "pid": None,
                "world": {"width": game.width, "height": game.height},
                "spectator": True,
            })
            app.state.spectators.add(websocket)
            # Drain incoming (we ignore messages; this lets us detect disconnect).
            while True:
                try:
                    await websocket.receive_text()
                except WebSocketDisconnect:
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("spectator ws error: %s", e)
        finally:
            app.state.spectators.discard(websocket)
            try:
                await websocket.close()
            except Exception:
                pass

    return app


async def _tick_loop(app: FastAPI) -> None:
    game: GameState = app.state.game
    next_t = time.monotonic()
    while True:
        next_t += TICK_DT
        try:
            game.step(TICK_DT)
            snapshot = game.snapshot()
            snapshot["spectators"] = len(app.state.spectators)
            events = game.drain_events()
            payload_state = {"type": S2C_STATE, "payload": snapshot}
            payload_event = {"type": S2C_EVENT, "payload": events} if events else None
            await _broadcast(app, payload_state)
            if payload_event is not None:
                await _broadcast(app, payload_event)
        except Exception as e:  # noqa: BLE001
            log.exception("tick loop error: %s", e)
        sleep_for = next_t - time.monotonic()
        if sleep_for > 0:
            await asyncio.sleep(sleep_for)
        else:
            # We're behind; reset baseline.
            next_t = time.monotonic()


async def _broadcast(app: FastAPI, message: dict) -> None:
    text = json.dumps(message)
    # Players
    conns = list(app.state.connections.items())
    dead: list[str] = []
    for pid, ws in conns:
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(pid)
    for pid in dead:
        app.state.connections.pop(pid, None)
        app.state.game.remove_player(pid)
    # Spectators (read-only observers)
    dead_spec: list = []
    for ws in list(app.state.spectators):
        try:
            await ws.send_text(text)
        except Exception:
            dead_spec.append(ws)
    for ws in dead_spec:
        app.state.spectators.discard(ws)


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
