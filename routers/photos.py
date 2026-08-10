# Foto-Upload und -Verwaltung

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Photo, User
from schemas import PhotoRead
from tenancy import CoupleId, get_owned_memory, get_owned_photo
from uploads import process_upload, safe_remove

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["Fotos"])


@router.post(
    "/memories/{memory_id}/photos",
    response_model=PhotoRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_photo(
    memory_id: int,
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    couple_id: CoupleId,
    db: Annotated[Session, Depends(get_db)],
    caption: Annotated[str | None, Form()] = None,
) -> Photo:
    """Ein Foto zu einer Erinnerung hochladen."""

    # Erinnerung prüfen — fremde Erinnerungen liefern 404, nicht 403
    get_owned_memory(db, couple_id, memory_id)

    # Upload verarbeiten (Validierung, Magic Bytes, EXIF, Resize, Thumbnail)
    result = process_upload(file, couple_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Bilddatei. Nur JPEG, PNG und WEBP bis 10 MB erlaubt.",
        )

    main_ref, _thumb_ref = result

    # Datenbank-Eintrag erstellen
    photo = Photo(
        memory_id=memory_id,
        filepath=main_ref,
        caption=caption,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return photo


@router.delete("/photos/{photo_id}")
def delete_photo(
    photo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    couple_id: CoupleId,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Ein Foto löschen."""

    photo = get_owned_photo(db, couple_id, photo_id)

    # Datei vom Dateisystem entfernen
    safe_remove(photo.filepath)

    db.delete(photo)
    db.commit()
    return {"detail": "Foto gelöscht"}
