# Einstellungen-Routen: Paar-Profil und App-Konfiguration

import logging
import os
from datetime import date as date_cls
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import CoupleSettings, User
from template_engine import templates
from uploads import process_upload, safe_remove

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Einstellungen"])


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

    SCHUTZLOGIK: Synchronisiert NUR die Namen, NICHT partner_since.
    partner_since wird ausschließlich in couple_settings gespeichert
    und von dort gelesen. Die User-Tabelle wird nicht angefasst.
    """
    for username, name in [
        ("partner_a", cs.partner_a_name),
        ("partner_b", cs.partner_b_name),
    ]:
        user: User | None = db.query(User).filter(User.username == username).first()
        if user is None:
            continue
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
    rel_path = os.path.relpath(main_path, start=".")

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

        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "user": current_user,
                "couple": cs,
                "partner_a": partner_a,
                "partner_b": partner_b,
                "success": request.query_params.get("success"),
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
