# Einstellungen-Routen: Paar-Profil und App-Konfiguration

import logging
import re
from datetime import date as date_cls
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from auth import (
    clear_auth_cookies,
    get_current_user,
    hash_password,
    set_auth_cookies,
    verify_password,
)
from database import get_db
from models import CoupleSettings, Memory, User
from template_engine import templates
from uploads import _to_posix_relpath, process_upload, safe_remove

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Einstellungen"])

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,50}$")


def _get_or_create_couple_settings(db: Session) -> CoupleSettings:
    """Singleton-Zugriff auf die Paar-Einstellungen.

    SCHUTZLOGIK: partner_since wird hier NICHT gesetzt.
    Es darf ausschließlich über POST /settings geändert werden.
    """
    cs: CoupleSettings | None = db.query(CoupleSettings).first()
    if cs is None:
        cs = CoupleSettings(partner_a_name="Partner A", partner_b_name="Partner B")
        db.add(cs)
        db.commit()
        db.refresh(cs)
    return cs


def _parse_and_validate_partner_since(raw_value: str | None) -> date_cls | None:
    """Datums-String parsen und validieren.

    Returns None bei leerem/ungültigem Wert.
    Lehnt unrealistische Datumswerte ab (vor 1950 oder in der Zukunft).
    """
    if not raw_value:
        return None
    try:
        parsed = date_cls.fromisoformat(raw_value)
    except ValueError:
        logger.warning("Ungültiges Datumsformat ignoriert: %s", raw_value)
        return None

    if parsed.year < 1950:
        logger.warning("Unrealistisches Datum abgelehnt (vor 1950): %s", parsed)
        return None
    if parsed > date_cls.today():
        logger.warning("Datum in der Zukunft abgelehnt: %s", parsed)
        return None

    return parsed


def _sync_partner_names(
    db: Session,
    cs: CoupleSettings,
) -> None:
    """User-Tabelle mit den aktuellen Namen synchronisieren.

    Stabil per User-ID: Erster User (kleinste ID) = Partner A,
    zweiter User = Partner B. Der Login-Username darf vom Nutzer
    geändert werden, ohne dass die Zuordnung bricht.
    """
    users: list[User] = db.query(User).order_by(User.id.asc()).limit(2).all()
    names = [cs.partner_a_name, cs.partner_b_name]
    for user, name in zip(users, names):
        user.name = name


def _handle_avatar_upload(
    avatar: UploadFile,
    current_user: User,
) -> None:
    """Avatar-Bild validieren, speichern und altes Bild entfernen."""
    result = process_upload(avatar)
    if result is None:
        return

    main_path, _ = result
    rel_path = _to_posix_relpath(main_path)

    if current_user.avatar_path:
        safe_remove(current_user.avatar_path)

    current_user.avatar_path = rel_path


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Einstellungsseite anzeigen."""
    try:
        cs: CoupleSettings = _get_or_create_couple_settings(db)

        partner_a: User | None = db.query(User).filter(User.username == "partner_a").first()
        partner_b: User | None = db.query(User).filter(User.username == "partner_b").first()

        # Versteckte Erinnerungen — NUR hier laden (überall sonst ausgefiltert)
        hidden_memories: list[Memory] = (
            db.query(Memory)
            .filter(Memory.is_hidden == True)
            .order_by(Memory.date.desc())
            .all()
        )

        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "request": request,
                "user": current_user,
                "couple": cs,
                "partner_a": partner_a,
                "partner_b": partner_b,
                "hidden_memories": hidden_memories,
                "hidden_count": len(hidden_memories),
                "success": request.query_params.get("success"),
                "account_success": request.query_params.get("account"),
                "account_error": request.query_params.get("account_error"),
            },
        )
    except Exception:
        logger.exception("Fehler beim Laden der Einstellungsseite")
        raise


@router.post("/settings", response_class=HTMLResponse)
def save_settings(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    partner_a_name: Annotated[str, Form()],
    partner_b_name: Annotated[str, Form()],
    partner_since: Annotated[str | None, Form()] = None,
    avatar: Annotated[UploadFile | None, File()] = None,
) -> Response:
    """Einstellungen speichern."""
    try:
        cs: CoupleSettings = _get_or_create_couple_settings(db)

        cs.partner_a_name = partner_a_name.strip()
        cs.partner_b_name = partner_b_name.strip()

        # SCHUTZLOGIK: partner_since wird NUR geändert wenn der Nutzer
        # explizit ein gültiges Datum im Formular gesendet hat.
        # Leeres Feld → alten Wert beibehalten, NICHT überschreiben.
        parsed_date = _parse_and_validate_partner_since(partner_since)
        if parsed_date is not None:
            old_date = cs.partner_since
            cs.partner_since = parsed_date
            if old_date != parsed_date:
                logger.info(
                    "Beziehungsdatum geändert: %s → %s (von User %s)",
                    old_date, parsed_date, current_user.id,
                )

        _sync_partner_names(db, cs)

        if avatar is not None:
            _handle_avatar_upload(avatar, current_user)

        db.commit()
        return RedirectResponse(url="/settings?success=1", status_code=303)
    except Exception:
        logger.exception("Fehler beim Speichern der Einstellungen")
        db.rollback()
        raise


# ── Login-Daten ändern ──────────────────────────────────────────────────────

def _redirect_account_error(message: str) -> RedirectResponse:
    """Redirect zur Settings-Seite mit URL-encoded Fehlermeldung."""
    from urllib.parse import quote
    return RedirectResponse(
        url=f"/settings?account_error={quote(message)}",
        status_code=303,
    )


@router.post("/settings/change-username")
def change_username(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    new_username: Annotated[str, Form()],
    current_password: Annotated[str, Form()],
) -> Response:
    """Login-Username ändern. Aktuelles Passwort wird verifiziert."""
    try:
        new_username_clean = new_username.strip()

        if not _USERNAME_PATTERN.match(new_username_clean):
            return _redirect_account_error(
                "Ungültiger Benutzername (3–50 Zeichen, nur A–Z, 0–9, _ . -)."
            )

        if not verify_password(current_password, current_user.hashed_password):
            logger.warning("Falsches Passwort bei Username-Änderung (User %s)", current_user.id)
            return _redirect_account_error("Aktuelles Passwort ist falsch.")

        if new_username_clean == current_user.username:
            return _redirect_account_error("Neuer Benutzername entspricht dem aktuellen.")

        # Eindeutigkeit prüfen
        existing = db.query(User).filter(User.username == new_username_clean).first()
        if existing is not None and existing.id != current_user.id:
            return _redirect_account_error("Dieser Benutzername ist bereits vergeben.")

        old_username = current_user.username
        current_user.username = new_username_clean
        db.commit()
        logger.info("Username geändert: %s → %s (User %s)", old_username, new_username_clean, current_user.id)

        # Cookies neu setzen — JWT 'sub' enthält den Username.
        response = RedirectResponse(url="/settings?account=username", status_code=303)
        set_auth_cookies(response, new_username_clean)
        return response
    except Exception:
        logger.exception("Fehler beim Ändern des Benutzernamens")
        db.rollback()
        raise


@router.post("/settings/change-password")
def change_password(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    new_password_repeat: Annotated[str, Form()],
) -> Response:
    """Passwort ändern. Aktuelles Passwort wird verifiziert."""
    try:
        if not verify_password(current_password, current_user.hashed_password):
            logger.warning("Falsches Passwort bei Passwort-Änderung (User %s)", current_user.id)
            return _redirect_account_error("Aktuelles Passwort ist falsch.")

        if new_password != new_password_repeat:
            return _redirect_account_error("Die neuen Passwörter stimmen nicht überein.")

        if len(new_password) < 8 or len(new_password) > 128:
            return _redirect_account_error("Neues Passwort muss 8–128 Zeichen lang sein.")

        if new_password == current_password:
            return _redirect_account_error("Das neue Passwort muss sich vom alten unterscheiden.")

        current_user.hashed_password = hash_password(new_password)
        db.commit()
        logger.info("Passwort geändert (User %s)", current_user.id)

        # Cookies erneuern, damit alte Sessions ungültig wirken können
        # (Token bleibt zwar gültig bis exp, aber wir rotieren proaktiv).
        response = RedirectResponse(url="/settings?account=password", status_code=303)
        clear_auth_cookies(response)
        set_auth_cookies(response, current_user.username)
        return response
    except Exception:
        logger.exception("Fehler beim Ändern des Passworts")
        db.rollback()
        raise
