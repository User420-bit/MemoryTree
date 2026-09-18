# Authentifizierungs-Routen: Login, Logout, Refresh, Registrierung per Invite

import logging
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import (
    _check_rate_limit,
    _clear_login_attempts,
    _record_login_attempt,
    clear_auth_cookies,
    get_user_from_refresh_token,
    hash_password,
    set_auth_cookies,
    username_from_access_token,
    verify_password,
)
from config import settings
from database import get_db
from i18n import t
from middleware import LANG_COOKIE
from models import CoupleSettings, Invite, User
from template_engine import templates
from tenancy import create_demo_couple, delete_demo_couple

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

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,50}$")
_REGISTER_TEMPLATE = "register.html"


def _get_client_ip(request: Request) -> str:
    """Client-IP ermitteln.

    X-Forwarded-For wird NUR ausgewertet, wenn TRUST_PROXY_HEADERS=true
    (App läuft hinter vertrauenswürdigem Reverse Proxy). Bei direkter
    Erreichbarkeit könnte der Header sonst pro Request gespooft werden
    und das Login-Rate-Limit aushebeln.
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/login")
def login_page(request: Request) -> Response:
    """Login-Seite anzeigen."""
    return templates.TemplateResponse(request, "login.html", {"request": request})


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Anmeldedaten prüfen, JWT-Cookies setzen und zum Dashboard weiterleiten."""
    client_ip = _get_client_ip(request)
    # Zwei Zähler: die IP bremst einen einzelnen Angreifer, das Konto bremst
    # verteiltes Raten gegen einen bestimmten Benutzer.
    rate_keys = (f"ip:{client_ip}", f"user:{username.strip().lower()}")

    # Rate Limiting prüfen
    _check_rate_limit(*rate_keys)

    user: User | None = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.hashed_password):
        _record_login_attempt(*rate_keys)
        # Username absichtlich NICHT loggen — verhindert Enumeration via Logs.
        logger.warning("Fehlgeschlagener Login-Versuch von %s", client_ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": t(request, "login.invalid_credentials")},
            status_code=401,
        )

    _clear_login_attempts(*rate_keys)
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
    _check_rate_limit(f"ip:{client_ip}")

    user = get_user_from_refresh_token(request, db)
    if user is None:
        _record_login_attempt(f"ip:{client_ip}")
        return RedirectResponse(url="/auth/login", status_code=303)

    # Strikte Whitelist: `next_url` stammt *nie* aus der Anfrage, sondern
    # wird aus einer geschlossenen Menge konstanter Strings ausgewählt.
    # Damit ist keine Taint-Flow mehr möglich.
    raw_next = request.query_params.get("next", _DEFAULT_NEXT_URL)
    next_url = raw_next if raw_next in _SAFE_NEXT_PATHS else _DEFAULT_NEXT_URL

    response = RedirectResponse(url=next_url, status_code=303)
    # Gäste behalten Session-Cookies, sonst würde der erste stille Refresh
    # ihre Sitzung in eine 7-Tage-Sitzung verwandeln.
    set_auth_cookies(response, user.username, session_only=user.couple.is_demo)
    return response


# ── Registrierung per Einladungscode ────────────────────────────────────────

def _find_usable_invite(db: Session, code: str) -> Invite | None:
    """Einladungscode auflösen, sofern er noch eingelöst werden darf.

    Liefert None für "existiert nicht", "abgelaufen" und "aufgebraucht" —
    der Aufrufer darf diese Fälle nach außen nicht unterscheiden, sonst wird
    die Seite zum Orakel für gültige Codes.
    """
    if not code:
        return None

    invite: Invite | None = db.query(Invite).filter(Invite.code == code).first()
    if invite is None:
        return None
    if invite.used_count >= invite.max_uses:
        return None
    if invite.expires_at is not None:
        expires_at = invite.expires_at
        # SQLite liefert naive Datetimes zurück — als UTC interpretieren,
        # sonst scheitert der Vergleich mit einem aware "jetzt".
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None
    return invite


def _register_error(request: Request, error_key: str, code: str) -> Response:
    """Registrierungsformular mit Fehlermeldung erneut anzeigen."""
    return templates.TemplateResponse(
        request,
        _REGISTER_TEMPLATE,
        {
            "request": request,
            "error": t(request, f"register.{error_key}"),
            # Code zurückspiegeln, damit der Nutzer ihn nicht neu eintippen
            # muss. Jinja2 escaped den Wert beim Rendern.
            "code": code,
        },
        status_code=400,
    )


@router.get("/register")
def register_page(request: Request) -> Response:
    """Registrierungsseite anzeigen (Code darf per ?code= vorbelegt werden)."""
    return templates.TemplateResponse(
        request,
        _REGISTER_TEMPLATE,
        {"request": request, "code": request.query_params.get("code", "")},
    )


@router.post("/register")
def register(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    code: Annotated[str, Form(...)],
    name: Annotated[str, Form(...)],
    username: Annotated[str, Form(...)],
    password: Annotated[str, Form(...)],
    password_repeat: Annotated[str, Form(...)],
) -> Response:
    """Neues Konto über einen Einladungscode anlegen.

    Es gibt bewusst keine offene Registrierung: der Code entscheidet, zu
    welchem Paar das Konto gehört, und wird per scripts/create_invite.py
    erzeugt. Der erste Einlöser wird Partner A des Paars, der zweite Partner B.
    """
    client_ip = _get_client_ip(request)
    # Registrierungsversuche teilen sich den IP-Zähler mit dem Login, damit
    # Codes nicht durchprobiert werden können.
    _check_rate_limit(f"ip:{client_ip}")

    code_clean = code.strip()
    username_clean = username.strip()
    name_clean = name.strip()

    if not _USERNAME_PATTERN.match(username_clean):
        return _register_error(request, "invalid_username", code_clean)
    if not name_clean or len(name_clean) > 100:
        return _register_error(request, "invalid_name", code_clean)
    if password != password_repeat:
        return _register_error(request, "password_mismatch", code_clean)
    if len(password) < 8 or len(password) > 128:
        return _register_error(request, "password_length", code_clean)

    invite = _find_usable_invite(db, code_clean)
    if invite is None:
        _record_login_attempt(f"ip:{client_ip}")
        logger.warning("Registrierung mit ungültigem Code von %s", client_ip)
        return _register_error(request, "invalid_code", code_clean)

    # Benutzernamen sind global eindeutig — der Login löst sie ohne
    # Paar-Kontext auf.
    if db.query(User).filter(User.username == username_clean).first() is not None:
        return _register_error(request, "username_taken", code_clean)

    couple_id: int = invite.couple_id

    # Einlösung als bedingtes UPDATE statt als Lese-dann-Schreib-Sequenz:
    # zwei gleichzeitige Registrierungen mit demselben Code könnten sonst
    # beide die Prüfung oben passieren und max_uses überschreiten.
    claimed = (
        db.query(Invite)
        .filter(Invite.id == invite.id, Invite.used_count < Invite.max_uses)
        .update({Invite.used_count: Invite.used_count + 1}, synchronize_session=False)
    )
    if claimed == 0:
        db.rollback()
        return _register_error(request, "invalid_code", code_clean)

    db.refresh(invite)
    used_count: int = invite.used_count

    user = User(
        couple_id=couple_id,
        name=name_clean,
        username=username_clean,
        hashed_password=hash_password(password),
    )
    db.add(user)

    # Einstellungen des Paars anlegen bzw. den Anzeigenamen eintragen.
    cs: CoupleSettings | None = (
        db.query(CoupleSettings).filter(CoupleSettings.couple_id == couple_id).first()
    )
    if cs is None:
        cs = CoupleSettings(
            couple_id=couple_id,
            partner_a_name=name_clean,
            partner_b_name="Partner B",
        )
        db.add(cs)
    elif used_count == 1:
        cs.partner_a_name = name_clean
    else:
        cs.partner_b_name = name_clean

    db.commit()
    logger.info(
        "Neues Konto registriert für Paar #%d (Einlösung %d/%d)",
        couple_id, used_count, invite.max_uses,
    )

    response = RedirectResponse(url="/", status_code=303)
    set_auth_cookies(response, username_clean)
    return response


# ── Gastzugang ──────────────────────────────────────────────────────────────

def _drop_guest_couple(request: Request, db: Session) -> None:
    """Demo-Paar der aktuellen Sitzung löschen, falls sie einem Gast gehört.

    Für Reset und Logout: wer geht oder neu anfängt, soll sein Wegwerf-Paar
    nicht bis zum Ablaufdatum in der Datenbank liegen lassen. Bei echten
    Konten und anonymen Requests passiert nichts — ``delete_demo_couple``
    weigert sich ohnehin bei allem, was kein Demo-Paar ist.
    """
    username = username_from_access_token(request)
    if username is None:
        return
    user: User | None = db.query(User).filter(User.username == username).first()
    if user is not None and delete_demo_couple(db, user.couple_id):
        db.commit()


@router.post("/demo")
def demo_login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Als Gast einsteigen: frisches Demo-Paar anlegen und anmelden.

    Derselbe Endpunkt ist auch das "Zurücksetzen" im Demo-Banner — ein Gast,
    der ihn erneut aufruft, bekommt ein neues Paar und das alte wird gelöscht.

    Bewusst POST und CSRF-geschützt: ein GET-Link würde von Crawlern und
    Link-Vorschauen ausgelöst und jedes Mal ein Paar in die Datenbank legen.
    """
    if not settings.DEMO_ENABLED:
        raise HTTPException(status_code=404)

    # Eigener Zähler, damit Demo-Klicks niemandem den Login sperren. Anders
    # als beim Login zählt hier jeder Aufruf, nicht nur der fehlgeschlagene —
    # jeder einzelne kostet Zeilen in der Datenbank.
    rate_key = f"demo:{_get_client_ip(request)}"
    _check_rate_limit(rate_key)
    _record_login_attempt(rate_key)

    _drop_guest_couple(request, db)
    guest = create_demo_couple(db)
    logger.info("Gastzugang: Demo-Paar #%s angelegt", guest.couple_id)

    response = RedirectResponse(url="/", status_code=303)
    # Sprach-Cache des Vorgängers am selben Browser nicht erben.
    response.delete_cookie(key=LANG_COOKIE, path="/")
    set_auth_cookies(response, guest.username, session_only=True)
    return response


@router.get("/logout")
def logout(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Beide Cookies löschen und zur Login-Seite weiterleiten."""
    _drop_guest_couple(request, db)
    response = RedirectResponse(url="/auth/login", status_code=303)
    clear_auth_cookies(response)
    return response
