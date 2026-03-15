# Einstellungen-Routen: Paar-Profil und App-Konfiguration

import logging
import os
import uuid
from datetime import date as date_cls
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import CoupleSettings, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Einstellungen"])
templates = Jinja2Templates(directory="templates")

ALLOWED_IMAGE_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
MAX_AVATAR_SIZE: int = 10 * 1024 * 1024  # 10 MB
AVATAR_MAX_DIM: int = 512


def _get_or_create_couple_settings(db: Session) -> CoupleSettings:
    """Singleton-Zugriff auf die Paar-Einstellungen."""
    cs: CoupleSettings | None = db.query(CoupleSettings).first()
    if cs is None:
        cs = CoupleSettings(partner_a_name="Partner A", partner_b_name="Partner B")
        db.add(cs)
        db.commit()
        db.refresh(cs)
    return cs


def _parse_partner_since(raw_value: str | None) -> date_cls | None:
    """Datums-String parsen. Gibt None zurück bei ungültigem/leerem Wert."""
    if not raw_value:
        return None
    try:
        return date_cls.fromisoformat(raw_value)
    except ValueError:
        logger.warning("Ungültiges Datum ignoriert: %s", raw_value)
        return None


def _sync_partner_users(
    db: Session,
    cs: CoupleSettings,
) -> None:
    """User-Tabelle mit den aktuellen CoupleSettings-Werten synchronisieren."""
    for username, name in [
        ("partner_a", cs.partner_a_name),
        ("partner_b", cs.partner_b_name),
    ]:
        user: User | None = db.query(User).filter(User.username == username).first()
        if user is None:
            continue
        user.name = name
        if cs.partner_since:
            user.partner_since = cs.partner_since


def _handle_avatar_upload(
    avatar: UploadFile,
    current_user: User,
) -> None:
    """Avatar-Bild validieren, speichern, skalieren und altes Bild entfernen."""
    if not avatar.filename or avatar.content_type not in ALLOWED_IMAGE_TYPES:
        return

    contents: bytes = avatar.file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        return

    extension: str = os.path.splitext(avatar.filename)[1].lower()
    filename: str = f"avatar_{current_user.username}_{uuid.uuid4()}{extension}"
    filepath: str = os.path.join(settings.UPLOAD_DIR, filename)

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(contents)

    with Image.open(filepath) as img:
        if img.width > AVATAR_MAX_DIM or img.height > AVATAR_MAX_DIM:
            img.thumbnail((AVATAR_MAX_DIM, AVATAR_MAX_DIM))
            img.save(filepath, quality=85)

    if current_user.avatar_path and os.path.exists(current_user.avatar_path):
        os.remove(current_user.avatar_path)

    current_user.avatar_path = filepath


@router.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Einstellungsseite anzeigen."""
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
    cs: CoupleSettings = _get_or_create_couple_settings(db)

    cs.partner_a_name = partner_a_name.strip()
    cs.partner_b_name = partner_b_name.strip()

    parsed_date = _parse_partner_since(partner_since)
    if parsed_date is not None:
        cs.partner_since = parsed_date

    _sync_partner_users(db, cs)

    if avatar is not None:
        _handle_avatar_upload(avatar, current_user)

    db.commit()
    return RedirectResponse(url="/settings?success=1", status_code=303)
