"""Site-wide password gate.

Single shared password (env: SITE_PASSWORD, default 'Nelson') protects every
page and the WebSockets. Authentication is granted via a signed HMAC cookie.
Failed login attempts are throttled per IP: 5 wrong tries -> 15 minute cooldown.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE_NAME = "iogame_auth"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
MAX_ATTEMPTS = 5
COOLDOWN_SECONDS = 15 * 60

# Routes that never require auth (login flow + static assets needed by it).
PUBLIC_PATH_PREFIXES = (
    "/login",
    "/api/login",
    "/api/health",
    "/static/",
    "/favicon",
)


def get_password() -> str:
    return os.environ.get("SITE_PASSWORD") or "Nelson"


def get_secret(app_state) -> str:
    # Reuse a per-process secret. Stored on app.state so all helpers agree.
    secret = getattr(app_state, "_auth_secret", None)
    if secret is None:
        secret = os.environ.get("SITE_AUTH_SECRET") or secrets.token_urlsafe(32)
        app_state._auth_secret = secret
    return secret


def _sign(secret: str, payload: str) -> str:
    mac = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def make_cookie_value(secret: str) -> str:
    # payload = "<issued_at>"; future revocations could bump the secret.
    return _sign(secret, str(int(time.time())))


def verify_cookie(secret: str, value: Optional[str]) -> bool:
    if not value or "." not in value:
        return False
    payload, _, sig = value.rpartition(".")
    expected = _sign(secret, payload)
    if not hmac.compare_digest(expected, value):
        return False
    try:
        issued = int(payload)
    except ValueError:
        return False
    if time.time() - issued > COOKIE_MAX_AGE:
        return False
    return True


# --- per-IP attempt tracking (in-memory; OK for single dyno) ---------------

class AttemptTracker:
    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def is_locked(self, ip: str) -> tuple[bool, float]:
        until = self._locked_until.get(ip, 0.0)
        now = time.time()
        if until > now:
            return True, until - now
        if until and until <= now:
            self._locked_until.pop(ip, None)
            self._attempts.pop(ip, None)
        return False, 0.0

    def record_failure(self, ip: str) -> tuple[int, float]:
        """Return (attempts_used, seconds_locked_for_or_0)."""
        now = time.time()
        # Drop attempts older than cooldown window.
        recent = [t for t in self._attempts.get(ip, []) if now - t < COOLDOWN_SECONDS]
        recent.append(now)
        self._attempts[ip] = recent
        if len(recent) >= MAX_ATTEMPTS:
            self._locked_until[ip] = now + COOLDOWN_SECONDS
            return len(recent), COOLDOWN_SECONDS
        return len(recent), 0.0

    def clear(self, ip: str) -> None:
        self._attempts.pop(ip, None)
        self._locked_until.pop(ip, None)


def is_public_path(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


def _gate_disabled() -> bool:
    return os.environ.get("SITE_PASSWORD_DISABLED") == "1"


class PasswordGateMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated HTTP requests to /login."""

    async def dispatch(self, request: Request, call_next):
        if _gate_disabled():
            return await call_next(request)
        path = request.url.path
        if is_public_path(path):
            return await call_next(request)
        secret = get_secret(request.app.state)
        cookie = request.cookies.get(COOKIE_NAME)
        if verify_cookie(secret, cookie):
            return await call_next(request)
        # API requests (JSON callers) get a 401, browsers a redirect.
        accept = request.headers.get("accept", "")
        if path.startswith("/api/") and "text/html" not in accept:
            return Response(status_code=401, content='{"error":"auth required"}',
                            media_type="application/json")
        return RedirectResponse(url=f"/login?next={path}", status_code=302)


def client_ip(request: Request) -> str:
    # Heroku / proxies: trust X-Forwarded-For if present (first hop).
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ws_is_authed(websocket, secret: str) -> bool:
    if _gate_disabled():
        return True
    cookie = websocket.cookies.get(COOKIE_NAME)
    return verify_cookie(secret, cookie)
