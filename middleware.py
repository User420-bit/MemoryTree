# Security-Middleware: Headers, CSRF, Request-ID, Token-Refresh

import logging
import secrets
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from config import settings

logger = logging.getLogger(__name__)


# ── CSRF-Token Hilfsfunktionen ───────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Erzeugt ein CSRF-Token (double-submit pattern)."""
    return secrets.token_urlsafe(32)


def get_csrf_token(request: Request) -> str:
    """CSRF-Token aus dem Cookie lesen oder neues generieren."""
    return request.cookies.get("csrf_token", "")


# ── Security Headers Middleware ──────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Setzt Standard-Security-Header auf alle Responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        # CSP: Tailwind CDN, Leaflet CDN, Leaflet Geocoder CDN, OpenStreetMap Tiles
        # unsafe-inline für Tailwind CDN <script> und inline <style>/<script> in Templates
        csp_parts = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com https://d3js.org",
            "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.tailwindcss.com",
            "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://unpkg.com",
            "font-src 'self' data:",
            "connect-src 'self' https://nominatim.openstreetmap.org https://*.tile.openstreetmap.org",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_parts)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), payment=()"
        )

        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

        return response


# ── CSRF Middleware ──────────────────────────────────────────────────────────

_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_EXEMPT_PATHS = {"/auth/login", "/health"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-Submit Cookie CSRF-Schutz für state-changing Requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Für sichere Methoden: CSRF-Cookie setzen falls nicht vorhanden
        if request.method in _CSRF_SAFE_METHODS:
            response: Response = await call_next(request)
            if "csrf_token" not in request.cookies:
                token = generate_csrf_token()
                response.set_cookie(
                    key="csrf_token",
                    value=token,
                    httponly=False,  # JS muss es lesen können
                    secure=settings.is_production,
                    samesite="lax",
                    path="/",
                )
            return response

        # Für state-changing Methoden: CSRF prüfen
        path = request.url.path
        if path in _CSRF_EXEMPT_PATHS:
            return await call_next(request)

        # API-Endpoints (JSON) brauchen kein CSRF bei SameSite Cookies
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            return await call_next(request)

        # Form-Submissions: Double-Submit prüfen
        cookie_token = request.cookies.get("csrf_token", "")
        if not cookie_token:
            logger.warning("CSRF: Kein Cookie-Token für %s %s", request.method, path)
            return Response("CSRF-Validierung fehlgeschlagen", status_code=403)

        # Token aus Form oder Header lesen
        form_token = ""
        if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            form_token = form.get("csrf_token", "")
        if not form_token:
            form_token = request.headers.get("x-csrf-token", "")

        if not secrets.compare_digest(cookie_token, form_token):
            logger.warning("CSRF: Token-Mismatch für %s %s", request.method, path)
            return Response("CSRF-Validierung fehlgeschlagen", status_code=403)

        return await call_next(request)


# ── Request-ID Middleware ────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Fügt jeder Request eine eindeutige ID hinzu für Logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = secrets.token_hex(8)
        request.state.request_id = request_id

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        response.headers["X-Request-ID"] = request_id

        # Statische Assets nicht loggen
        path = request.url.path
        if not path.startswith("/static/") and not path.startswith("/uploads/"):
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

        return response


# ── Token-Refresh Middleware ─────────────────────────────────────────────────

class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """Versucht bei abgelaufenem Access Token einen stillen Refresh über den Refresh Token."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        # Wenn 401 und Refresh Token vorhanden → zum Refresh-Endpoint weiterleiten
        if response.status_code == 401 and request.cookies.get("refresh_token"):
            path = request.url.path
            # Nicht für Login/Logout/API-Calls
            if not path.startswith("/auth/") and not path.startswith("/api/"):
                return RedirectResponse(
                    url=f"/auth/refresh?next={path}",
                    status_code=303,
                )

        return response
