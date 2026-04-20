# Authentifizierungs-Routen: Login, Logout, Refresh

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import (
    _check_rate_limit,
    _clear_login_attempts,
    _record_login_attempt,
    clear_auth_cookies,
    get_user_from_refresh_token,
    set_auth_cookies,
    verify_password,
)
from database import get_db
from models import User
from template_engine import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentifizierung"])

# Open-Redirect-Schutz: strikte Whitelist der einzigen Zielpfade, die nach
# einem Refresh zurückgegeben werden dürfen. Alles andere → Dashboard.
# Das ist bewusst kein regex-basiertes Filtering, sondern ein geschlossener
# Satz interner Routen — so kann keine benutzer-kontrollierte Zeichenkette
# jemals unverifiziert in `RedirectResponse.url` landen.
_SAFE_NEXT_PATHS: frozenset[str] = frozenset({
    "/",
    "/tree",
    "/timeline",
    "/map",
    "/gallery",
    "/milestones",
    "/settings",
})
_DEFAULT_NEXT_URL = "/"


def _get_client_ip(request: Request) -> str:
    """Client-IP ermitteln (hinter Reverse Proxy: X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/login")
def login_page(request: Request) -> Response:
    """Login-Seite anzeigen."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Anmeldedaten prüfen, JWT-Cookies setzen und zum Dashboard weiterleiten."""
    client_ip = _get_client_ip(request)

    # Rate Limiting prüfen
    _check_rate_limit(client_ip)

    user: User | None = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.hashed_password):
        _record_login_attempt(client_ip)
        # Username absichtlich NICHT loggen — verhindert Enumeration via Logs.
        logger.warning("Fehlgeschlagener Login-Versuch von %s", client_ip)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ungültige Anmeldedaten"},
            status_code=401,
        )

    _clear_login_attempts(client_ip)
    logger.info("Erfolgreicher Login: %s von %s", username, client_ip)

    response = RedirectResponse(url="/", status_code=303)
    set_auth_cookies(response, user.username)
    return response


@router.get("/refresh")
def refresh_token(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Access Token über gültigen Refresh Token erneuern."""
    # Rate-Limit, damit ein geklauter Refresh-Token nicht beliebig oft
    # rotieren kann. Teilt sich den Zähler mit /auth/login.
    client_ip = _get_client_ip(request)
    _check_rate_limit(client_ip)

    user = get_user_from_refresh_token(request, db)
    if user is None:
        _record_login_attempt(client_ip)
        return RedirectResponse(url="/auth/login", status_code=303)

    # Strikte Whitelist: `next_url` stammt *nie* aus der Anfrage, sondern
    # wird aus einer geschlossenen Menge konstanter Strings ausgewählt.
    # Damit ist keine Taint-Flow mehr möglich.
    raw_next = request.query_params.get("next", _DEFAULT_NEXT_URL)
    next_url = raw_next if raw_next in _SAFE_NEXT_PATHS else _DEFAULT_NEXT_URL

    response = RedirectResponse(url=next_url, status_code=303)
    set_auth_cookies(response, user.username)
    return response


@router.get("/logout")
def logout() -> Response:
    """Beide Cookies löschen und zur Login-Seite weiterleiten."""
    response = RedirectResponse(url="/auth/login", status_code=303)
    clear_auth_cookies(response)
    return response
