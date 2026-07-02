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
from models import User

logger = logging.getLogger(__name__)

_AUTH_ERROR = "Nicht authentifiziert"

# ── Rate Limiting (In-Memory, für 2 User + 1 Worker ausreichend) ────────────

_login_attempts: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()


def _check_rate_limit(client_ip: str) -> None:
    """Prüft ob die IP zu viele Login-Versuche hat. Wirft 429 bei Überschreitung."""
    now = time.monotonic()
    window = settings.LOGIN_RATE_LIMIT_WINDOW
    max_attempts = settings.LOGIN_RATE_LIMIT_MAX

    with _rate_lock:
        # Sweep: komplett abgelaufene IPs entfernen, damit das Dict bei
        # vielen verschiedenen Client-IPs nicht unbegrenzt wächst.
        if len(_login_attempts) > 256:
            stale = [
                ip for ip, ts in _login_attempts.items()
                if not ts or now - ts[-1] >= window
            ]
            for ip in stale:
                del _login_attempts[ip]

        attempts = _login_attempts[client_ip]
        # Alte Einträge entfernen
        _login_attempts[client_ip] = [t for t in attempts if now - t < window]
        if len(_login_attempts[client_ip]) >= max_attempts:
            logger.warning("Rate limit erreicht für IP %s", client_ip)
            raise HTTPException(
                status_code=429,
                detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.",
            )


def _record_login_attempt(client_ip: str) -> None:
    """Zeichnet einen fehlgeschlagenen Login-Versuch auf."""
    with _rate_lock:
        _login_attempts[client_ip].append(time.monotonic())


def _clear_login_attempts(client_ip: str) -> None:
    """Löscht Login-Versuche nach erfolgreichem Login."""
    with _rate_lock:
        _login_attempts.pop(client_ip, None)


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
    """Beide Auth-Cookies aktiv löschen."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/auth/refresh")


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
