# Foto-Upload und -Verwaltung

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Memory, Photo, User
from schemas import PhotoRead
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
    db: Annotated[Session, Depends(get_db)],
    caption: Annotated[str | None, Form()] = None,
) -> Photo:
    """Ein Foto zu einer Erinnerung hochladen."""

    # Erinnerung prüfen
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Erinnerung nicht gefunden",
        )

    # Upload verarbeiten (Validierung, Magic Bytes, EXIF, Resize, Thumbnail)
    result = process_upload(file)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Bilddatei. Nur JPEG, PNG und WEBP bis 10 MB erlaubt.",
        )

    main_path, thumb_path = result
    rel_path = os.path.relpath(main_path, start=".")

    # Datenbank-Eintrag erstellen
    photo = Photo(
        memory_id=memory_id,
        filepath=rel_path,
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
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Ein Foto löschen."""

    photo: Photo | None = db.query(Photo).filter(Photo.id == photo_id).first()
    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Foto nicht gefunden",
        )

    # Datei vom Dateisystem entfernen
    safe_remove(photo.filepath)

    db.delete(photo)
    db.commit()
    return {"detail": "Foto gelöscht"}
