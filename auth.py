# JWT-Authentifizierung und Passwort-Hashing für Memory Tree

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from middleware import LANG_COOKIE
from models import User

logger = logging.getLogger(__name__)

_AUTH_ERROR = "Nicht authentifiziert"

# ── Rate Limiting (In-Memory, für 2 User + 1 Worker ausreichend) ────────────

_login_attempts: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()


def _check_rate_limit(*keys: str) -> None:
    """Wirft 429, wenn EINER der Zähler sein Limit erreicht hat.

    Mehrere Schlüssel, weil IP allein bei mehr als zwei Konten nicht mehr
    reicht: ``ip:<addr>`` bremst einen einzelnen Angreifer, ``user:<name>``
    zusätzlich verteiltes Raten gegen ein bestimmtes Konto. Ein Angreifer, der
    Benutzernamen durchrotiert, läuft weiterhin ins IP-Limit.

    Der Zustand liegt im Prozess — auf dem Pi (1 Worker) ist das die echte
    Grenze, auf Vercel greift er nur innerhalb einer warmen Instanz und die
    eigentliche Grenze ist die Firewall-Regel (DEPLOYMENT.md 12.5).
    """
    now = time.monotonic()
    window = settings.LOGIN_RATE_LIMIT_WINDOW
    max_attempts = settings.LOGIN_RATE_LIMIT_MAX

    with _rate_lock:
        # Sweep: komplett abgelaufene Einträge entfernen, damit das Dict bei
        # vielen verschiedenen Client-IPs nicht unbegrenzt wächst.
        if len(_login_attempts) > 256:
            stale = [
                key for key, ts in _login_attempts.items()
                if not ts or now - ts[-1] >= window
            ]
            for key in stale:
                del _login_attempts[key]

        for key in keys:
            recent = [t for t in _login_attempts[key] if now - t < window]
            _login_attempts[key] = recent
            if len(recent) >= max_attempts:
                # Nur den Schlüsseltyp loggen, nicht den Benutzernamen —
                # sonst landet Enumeration im Logfile.
                logger.warning("Rate limit erreicht (%s)", key.split(":", 1)[0])
                raise HTTPException(
                    status_code=429,
                    detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.",
                )


def _record_login_attempt(*keys: str) -> None:
    """Zeichnet einen fehlgeschlagenen Versuch auf allen Zählern auf."""
    now = time.monotonic()
    with _rate_lock:
        for key in keys:
            _login_attempts[key].append(now)


def _clear_login_attempts(*keys: str) -> None:
    """Löscht die Zähler nach erfolgreichem Login."""
    with _rate_lock:
        for key in keys:
            _login_attempts.pop(key, None)


# ── Passwort-Hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Passwort mit bcrypt hashen."""
    password_bytes: bytes = password.encode("utf-8")
    salt: bytes = bcrypt.gensalt(rounds=12)
    hashed: bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Passwort gegen Hash prüfen."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── JWT Token-Erstellung ────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Kurzlebiger Access Token (Default: 30 Min)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(data: dict[str, Any]) -> str:
    """Langlebiger Refresh Token (Default: 7 Tage)."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def _decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Token dekodieren und Typ prüfen."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    return payload


# ── Cookie-Hilfsfunktionen ──────────────────────────────────────────────────

def set_auth_cookies(response: Response, username: str) -> None:
    """Access + Refresh Token als sichere HttpOnly Cookies setzen."""
    access_token = create_access_token(data={"sub": username})
    refresh_token = create_refresh_token(data={"sub": username})

    secure_flag = settings.use_secure_cookies

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure_flag,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure_flag,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/auth/refresh",
    )


def clear_auth_cookies(response: Response) -> None:
    """Beide Auth-Cookies aktiv löschen — plus den Sprach-Cache.

    Das ``lang``-Cookie ist nur ein Cache für die Sprache des Paars. Bliebe es
    nach dem Logout stehen, würde ein anderer Nutzer am selben Browser die
    Sprache des Vorgängers sehen, bis die DB erneut befragt wird.
    """
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/auth/refresh")
    response.delete_cookie(key=LANG_COOKIE, path="/")


# ── Token-Validierung und User-Lookup ────────────────────────────────────────

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Aktuellen User aus dem Access Token Cookie ermitteln."""
    token: str | None = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    payload = _decode_token(token, "access")
    username: str | None = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)

    user: User | None = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail=_AUTH_ERROR)
    return user


def username_from_access_token(request: Request) -> str | None:
    """Benutzername aus dem Access-Token lesen, ohne bei Fehlern zu werfen.

    Für Middleware gedacht, die vor der eigentlichen Auth läuft und einen
    fehlenden oder abgelaufenen Token als "anonym" behandeln muss statt den
    Request abzubrechen.
    """
    token: str | None = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = _decode_token(token, "access")
    except HTTPException:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


def get_user_from_refresh_token(request: Request, db: Session) -> User | None:
    """User aus Refresh Token ermitteln (für stilles Token-Refresh)."""
    token: str | None = request.cookies.get("refresh_token")
    if not token:
        return None
    try:
        payload = _decode_token(token, "refresh")
    except HTTPException:
        return None
    username: str | None = payload.get("sub")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()
