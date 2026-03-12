# Foto-Upload und -Verwaltung

import os
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Memory, Photo, User
from schemas import PhotoRead

router = APIRouter(prefix="", tags=["Fotos"])

ALLOWED_CONTENT_TYPES: set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


def _resize_image(filepath: str) -> None:
    """Bild proportional verkleinern, falls es größer als MAX_IMAGE_SIZE ist."""
    with Image.open(filepath) as img:
        max_dim: int = settings.MAX_IMAGE_SIZE
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim))
            img.save(filepath, quality=85)


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

    # Dateityp prüfen
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur JPEG, PNG und WEBP Dateien erlaubt",
        )

    # Datei einlesen & Größe prüfen
    contents: bytes = file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datei zu groß (max. 10 MB)",
        )

    # Eindeutigen Dateinamen erzeugen
    extension: str = os.path.splitext(file.filename or "upload.jpg")[1].lower()
    unique_filename: str = f"{uuid.uuid4()}{extension}"
    filepath: str = os.path.join(settings.UPLOAD_DIR, unique_filename)

    # Datei speichern
    with open(filepath, "wb") as f:
        f.write(contents)

    # Bild verkleinern, falls nötig
    _resize_image(filepath)

    # Datenbank-Eintrag erstellen
    photo = Photo(
        memory_id=memory_id,
        filepath=filepath,
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
    if os.path.exists(photo.filepath):
        os.remove(photo.filepath)

    db.delete(photo)
    db.commit()
    return {"detail": "Foto gelöscht"}
