# CRUD-Routen für Erinnerungen (JSON-API + HTML-Formulare)

import logging
import os
import uuid
from datetime import date
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from PIL import Image
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Memory, Photo, Place, User
from schemas import MemoryCreate, MemoryRead, MemoryUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["Erinnerungen"])
templates = Jinja2Templates(directory="templates")

_NOT_FOUND = "Erinnerung nicht gefunden"
_MEMORY_FORM_TEMPLATE = "memory_form.html"

ALLOWED_CONTENT_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


def _resize_image(filepath: str) -> None:
    """Bild proportional verkleinern, falls es größer als MAX_IMAGE_SIZE ist."""
    with Image.open(filepath) as img:
        max_dim: int = settings.MAX_IMAGE_SIZE
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim))
            img.save(filepath, quality=85)


def _save_uploaded_photos(
    files: list[UploadFile],
    memory_id: int,
    db: Session,
) -> None:
    """Hochgeladene Fotos validieren, speichern und als Photo-Objekte in die DB einfügen."""
    for file in files:
        if not file.filename or file.size == 0:
            continue
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            logger.warning("Ungültiger Dateityp: %s", file.content_type)
            continue
        if file.size and file.size > MAX_FILE_SIZE:
            logger.warning("Datei zu groß: %s (%d bytes)", file.filename, file.size)
            continue

        ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(settings.UPLOAD_DIR, filename)

        with open(filepath, "wb") as out:
            out.write(file.file.read())

        _resize_image(filepath)

        photo = Photo(
            memory_id=memory_id,
            filepath=f"{settings.UPLOAD_DIR}/{filename}",
        )
        db.add(photo)

    db.flush()



@router.get("/new", response_class=HTMLResponse)
def memory_form_new(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> HTMLResponse:
    """Leeres Formular für eine neue Erinnerung anzeigen."""
    return templates.TemplateResponse(
        _MEMORY_FORM_TEMPLATE,
        {"request": request, "user": current_user, "memory": None, "error": None},
    )


@router.post("/new", response_class=HTMLResponse, response_model=None)
def memory_form_create(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    title: Annotated[str, Form()],
    date_field: Annotated[str, Form(alias="date")],
    category: Annotated[str, Form()] = "Alltag",
    mood: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    lat: Annotated[str, Form()] = "",
    lng: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    photos: Annotated[List[UploadFile], File()] = [],
) -> HTMLResponse | RedirectResponse:
    """Neue Erinnerung aus dem HTML-Formular speichern."""
    try:
        parsed_date = date.fromisoformat(date_field)
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            _MEMORY_FORM_TEMPLATE,
            {"request": request, "user": current_user, "memory": None,
             "error": "Ungültiges Datum."},
            status_code=422,
        )

    lat_val: float | None = float(lat) if lat else None
    lng_val: float | None = float(lng) if lng else None

    memory = Memory(
        title=title,
        date=parsed_date,
        description=description or None,
        location=location or None,
        lat=lat_val,
        lng=lng_val,
        mood=mood or None,
        category=category,
        created_by=current_user.id,
    )
    db.add(memory)
    db.flush()

    # Ort anlegen
    if location and lat_val is not None and lng_val is not None:
        place = Place(memory_id=memory.id, name=location, lat=lat_val, lng=lng_val)
        db.add(place)

    # Fotos speichern
    if photos:
        _save_uploaded_photos(photos, memory.id, db)

    db.commit()
    logger.info("Erinnerung #%d erstellt von User #%d", memory.id, current_user.id)
    return RedirectResponse(url="/?success=created", status_code=303)


@router.get(
    "/{memory_id}/edit",
    response_class=HTMLResponse,
    responses={404: {"description": _NOT_FOUND}},
)
def memory_form_edit(
    memory_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Formular zum Bearbeiten einer bestehenden Erinnerung anzeigen."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    return templates.TemplateResponse(
        _MEMORY_FORM_TEMPLATE,
        {"request": request, "user": current_user, "memory": memory, "error": None},
    )


@router.post(
    "/{memory_id}/edit",
    response_class=HTMLResponse,
    response_model=None,
    responses={404: {"description": _NOT_FOUND}},
)
def memory_form_update(
    memory_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    title: Annotated[str, Form()],
    date_field: Annotated[str, Form(alias="date")],
    category: Annotated[str, Form()] = "Alltag",
    mood: Annotated[str, Form()] = "",
    location: Annotated[str, Form()] = "",
    lat: Annotated[str, Form()] = "",
    lng: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    photos: Annotated[List[UploadFile], File()] = [],
) -> HTMLResponse | RedirectResponse:
    """Bestehende Erinnerung über das HTML-Formular aktualisieren."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    try:
        parsed_date = date.fromisoformat(date_field)
    except (ValueError, TypeError):
        return templates.TemplateResponse(
            _MEMORY_FORM_TEMPLATE,
            {"request": request, "user": current_user, "memory": memory,
             "error": "Ungültiges Datum."},
            status_code=422,
        )

    memory.title = title
    memory.date = parsed_date
    memory.category = category
    memory.mood = mood or None
    memory.location = location or None
    memory.lat = float(lat) if lat else None
    memory.lng = float(lng) if lng else None
    memory.description = description or None

    # Neue Fotos hochladen
    if photos:
        _save_uploaded_photos(photos, memory.id, db)

    db.commit()
    logger.info("Erinnerung #%d aktualisiert von User #%d", memory.id, current_user.id)
    return RedirectResponse(url="/?success=updated", status_code=303)



@router.get("", response_model=list[MemoryRead])
def list_memories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    category: str | None = None,
    year: int | None = None,
) -> list[Memory]:
    """Alle Erinnerungen abfragen, optional nach Kategorie und Jahr gefiltert."""
    query = db.query(Memory)

    if category is not None:
        query = query.filter(Memory.category == category)

    if year is not None:
        from sqlalchemy import extract
        query = query.filter(extract("year", Memory.date) == year)

    return query.order_by(Memory.date.desc()).all()


@router.post("", response_model=MemoryRead, status_code=201)
def create_memory(
    payload: MemoryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Memory:
    """Neue Erinnerung anlegen (JSON-API). Legt ggf. auch einen Ort an."""
    memory = Memory(
        title=payload.title,
        date=payload.date,
        description=payload.description,
        location=payload.location,
        lat=payload.lat,
        lng=payload.lng,
        mood=payload.mood,
        category=payload.category,
        created_by=current_user.id,
    )
    db.add(memory)
    db.flush()

    if payload.location and payload.lat is not None and payload.lng is not None:
        place = Place(
            memory_id=memory.id,
            name=payload.location,
            lat=payload.lat,
            lng=payload.lng,
        )
        db.add(place)

    db.commit()
    db.refresh(memory)
    return memory


@router.get("/{memory_id}", response_model=MemoryRead, responses={404: {"description": _NOT_FOUND}})
def get_memory(
    memory_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Memory:
    """Einzelne Erinnerung nach ID abrufen."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return memory


@router.put("/{memory_id}", response_model=MemoryRead, responses={404: {"description": _NOT_FOUND}})
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Memory:
    """Felder einer bestehenden Erinnerung aktualisieren (nur nicht-None Werte)."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    update_data: dict = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(memory, field, value)

    db.commit()
    db.refresh(memory)
    return memory


@router.delete("/{memory_id}", responses={404: {"description": _NOT_FOUND}})
def delete_memory(
    memory_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Erinnerung löschen."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    db.delete(memory)
    db.commit()
    return {"detail": "Erinnerung gelöscht"}
