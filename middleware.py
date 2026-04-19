# Security-Middleware: Headers, CSRF, Request-ID, Token-Refresh

import logging
import secrets
import time
from typing import Callable
from urllib.parse import parse_qs

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings

logger = logging.getLogger(__name__)


# ── CSRF-Token Hilfsfunktionen ───────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Erzeugt ein CSRF-Token (double-submit pattern)."""
    return secrets.token_urlsafe(32)


def get_csrf_token(request: Request) -> str:
    """CSRF-Token aus dem Cookie oder request.state lesen."""
    # request.state hat Vorrang (frisch generiertes Token für die aktuelle Response)
    token = getattr(request.state, "csrf_token", None)
    if token:
        return token
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
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.tailwindcss.com",
            "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://*.tile.openstreetmap.de https://unpkg.com",
            "font-src 'self' data:",
            "connect-src 'self' https://nominatim.openstreetmap.org https://*.tile.openstreetmap.org https://*.tile.openstreetmap.de",
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


class CSRFMiddleware:
    """
    Double-Submit Cookie CSRF-Schutz als reines ASGI-Middleware.

    Implementiert als ASGI-Middleware statt BaseHTTPMiddleware, um das Problem
    der Body-Konsumierung zu vermeiden: BaseHTTPMiddleware + request.form()
    konsumiert den Body-Stream, sodass FastAPIs Form()-Parameter leer bleiben.

    Diese Middleware puffert den Body für POST-Requests, extrahiert das CSRF-Token
    daraus und stellt den Body dann für die Route wieder bereit.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        method = request.method
        path = request.url.path

        # ── Sichere Methoden: Cookie setzen falls nicht vorhanden ──
        if method in _CSRF_SAFE_METHODS:
            need_csrf_cookie = "csrf_token" not in request.cookies

            if not need_csrf_cookie:
                await self.app(scope, receive, send)
                return

            # CSRF-Cookie in die Response injizieren
            token = generate_csrf_token()
            # Token in request.state speichern, damit get_csrf_token() es
            # während des Template-Renderings lesen kann (Cookie ist erst
            # im nächsten Request verfügbar).
            request.state.csrf_token = token
            csrf_cookie_header = _build_csrf_set_cookie(token)

            async def send_with_csrf(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append(csrf_cookie_header)
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, send_with_csrf)
            return

        # ── Exempt-Pfade ──
        if path in _CSRF_EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # ── JSON-API: CSRF nicht erforderlich (SameSite-Cookies schützen) ──
        content_type = _get_header(scope, b"content-type")
        if b"application/json" in content_type:
            await self.app(scope, receive, send)
            return

        # ── Form-Submissions: Double-Submit prüfen ──
        cookie_token = request.cookies.get("csrf_token", "")
        if not cookie_token:
            logger.warning("CSRF: Kein Cookie-Token für %s %s", method, path)
            await _send_plain(send, 403, "CSRF-Validierung fehlgeschlagen")
            return

        # Body puffern, damit er nach der Prüfung erneut gelesen werden kann
        body = await _buffer_body(receive)

        # CSRF-Token aus dem Body extrahieren (ohne request.form() aufzurufen)
        form_token = _extract_csrf_from_body(body, content_type)

        # Fallback: Header
        if not form_token:
            form_token = _get_header(scope, b"x-csrf-token").decode("latin-1", errors="replace")

        if not form_token or not secrets.compare_digest(cookie_token, form_token):
            logger.warning("CSRF: Token-Mismatch für %s %s", method, path)
            await _send_plain(send, 403, "CSRF-Validierung fehlgeschlagen")
            return

        # Body als gepuffertes receive weiterreichen
        async def receive_cached() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, receive_cached, send)


def _build_csrf_set_cookie(token: str) -> tuple[bytes, bytes]:
    """Baut ein Set-Cookie-Header-Tuple für das CSRF-Token."""
    parts = [f"csrf_token={token}", "Path=/", "SameSite=Lax"]
    if settings.is_production:
        parts.append("Secure")
    return (b"set-cookie", "; ".join(parts).encode("latin-1"))


def _get_header(scope: Scope, name: bytes) -> bytes:
    """Header-Wert aus dem ASGI-Scope lesen."""
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value
    return b""


async def _buffer_body(receive: Receive) -> bytes:
    """Gesamten Request-Body puffern."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunk = message.get("body", b"")
        if chunk:
            chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _extract_csrf_from_body(body: bytes, content_type: bytes) -> str:
    """CSRF-Token aus URL-encoded oder Multipart-Body extrahieren."""
    ct = content_type.decode("latin-1", errors="replace").lower()

    if "application/x-www-form-urlencoded" in ct:
        parsed = parse_qs(body.decode("utf-8", errors="replace"))
        values = parsed.get("csrf_token", [])
        return values[0] if values else ""

    if "multipart/form-data" in ct:
        # Boundary aus Content-Type extrahieren
        boundary = _extract_boundary(ct)
        if not boundary:
            return ""
        return _parse_multipart_csrf(body, boundary)

    return ""


def _extract_boundary(content_type: str) -> str:
    """Boundary-String aus dem Content-Type-Header extrahieren."""
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[len("boundary="):]
            return boundary.strip('"')
    return ""


def _parse_multipart_csrf(body: bytes, boundary: str) -> str:
    """csrf_token-Feld aus einem Multipart-Body extrahieren.

    Sucht nach dem csrf_token-Feld via Byte-Pattern-Match statt
    striktem boundary-Splitting, um Encoding-/Dash-Varianten robust
    zu handhaben.
    """
    # Pattern: name="csrf_token" gefolgt von \r\n\r\n<VALUE>\r\n
    marker = b'name="csrf_token"'
    idx = body.find(marker)
    if idx == -1:
        marker = b"name='csrf_token'"
        idx = body.find(marker)
    if idx == -1:
        return ""

    # Wert beginnt nach \r\n\r\n
    value_start = body.find(b"\r\n\r\n", idx)
    if value_start == -1:
        return ""
    value_start += 4  # Länge von \r\n\r\n

    # Wert endet bei nächstem \r\n
    value_end = body.find(b"\r\n", value_start)
    if value_end == -1:
        value_end = len(body)

    return body[value_start:value_end].decode("utf-8", errors="replace").strip()


async def _send_plain(send: Send, status: int, text: str) -> None:
    """Einfache Plaintext-Response senden."""
    body = text.encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
    })


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
