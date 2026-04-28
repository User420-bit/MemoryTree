# CRUD-Routen für Erinnerungen (JSON-API + HTML-Formulare)

import logging
import re
from datetime import date
from typing import Annotated, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from database import get_db
from models import Memory, Photo, Place, User
from schemas import MemoryCreate, MemoryRead, MemoryUpdate
from template_engine import templates
from uploads import safe_remove, save_uploaded_photos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memories", tags=["Erinnerungen"])

_NOT_FOUND = "Erinnerung nicht gefunden"
_MEMORY_FORM_TEMPLATE = "memory_form.html"



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
        save_uploaded_photos(photos, memory.id, db)

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
        save_uploaded_photos(photos, memory.id, db)

    db.commit()
    logger.info("Erinnerung #%d aktualisiert von User #%d", memory.id, current_user.id)
    redirect_url = f"/memories/{int(memory.id)}?success=updated"
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post(
    "/{memory_id}/toggle-favorite",
    response_model=None,
    responses={404: {"description": _NOT_FOUND}},
)
def toggle_favorite(
    memory_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Favoriten-Status einer Erinnerung umschalten (max 8 Pins am Baum)."""
    from sqlalchemy import func

    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    # Pinning: max 8 erlaubt (versteckte zählen nicht mit)
    if not memory.is_favorite:
        total_pinned: int = (
            db.query(func.count(Memory.id))
            .filter(Memory.is_favorite == True, Memory.is_hidden == False)
            .scalar() or 0
        )
        if total_pinned >= 8:
            return JSONResponse(
                {"is_favorite": False, "total_pinned": total_pinned, "error": "max_reached"},
                status_code=200,
            )

    memory.is_favorite = not memory.is_favorite
    db.commit()

    total_pinned_after: int = (
        db.query(func.count(Memory.id))
        .filter(Memory.is_favorite == True, Memory.is_hidden == False)
        .scalar() or 0
    )

    logger.info(
        "Erinnerung #%d Favorit=%s von User #%d (total_pinned=%d)",
        memory.id, memory.is_favorite, current_user.id, total_pinned_after,
    )
    return JSONResponse({"is_favorite": memory.is_favorite, "total_pinned": total_pinned_after})


@router.post(
    "/{memory_id}/toggle-hidden",
    response_model=None,
    responses={404: {"description": _NOT_FOUND}},
)
def toggle_hidden(
    memory_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Sichtbarkeit einer Erinnerung umschalten.

    Versteckte Erinnerungen erscheinen nirgendwo in der App, außer im
    Verwaltungsbereich auf der Einstellungsseite. Wird eine Erinnerung
    versteckt, wird sie zusätzlich automatisch vom Baum entpinnt.
    """
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    memory.is_hidden = not memory.is_hidden
    if memory.is_hidden and memory.is_favorite:
        memory.is_favorite = False

    db.commit()

    logger.info(
        "Erinnerung #%d is_hidden=%s is_favorite=%s von User #%d",
        memory.id, memory.is_hidden, memory.is_favorite, current_user.id,
    )
    return JSONResponse({
        "is_hidden": memory.is_hidden,
        "is_favorite": memory.is_favorite,
    })


@router.post(
    "/{memory_id}/update-tree-position",
    response_model=None,
    responses={
        400: {"description": "Nur gepinnte Erinnerungen können positioniert werden"},
        404: {"description": _NOT_FOUND},
        422: {"description": "Ungültiges Positionsformat"},
    },
)
def update_tree_position(
    memory_id: int,
    request_body: dict,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Position einer Erinnerung im Baum aktualisieren (Drag & Drop)."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    if not memory.is_favorite:
        raise HTTPException(status_code=400, detail="Nur gepinnte Erinnerungen können positioniert werden")

    top = request_body.get("top", "")
    left = request_body.get("left", "")

    # Validate percentage format (e.g. "22.5%" or "45%")
    pct_pattern = re.compile(r"^\d{1,3}(\.\d{1,2})?%$")
    if not pct_pattern.match(top) or not pct_pattern.match(left):
        raise HTTPException(status_code=422, detail="Ungültiges Positionsformat (erwartet z.B. '22%')")

    # Validate range 0-100
    top_val = float(top.rstrip("%"))
    left_val = float(left.rstrip("%"))
    if not (0 <= top_val <= 100) or not (0 <= left_val <= 100):
        raise HTTPException(status_code=422, detail="Position muss zwischen 0% und 100% liegen")

    memory.tree_pos_top = top
    memory.tree_pos_left = left
    db.commit()

    logger.info("Erinnerung #%d Position aktualisiert: top=%s left=%s", memory.id, top, left)
    return JSONResponse({"ok": True})


@router.post(
    "/reorder",
    response_model=None,
    responses={400: {"description": "Ungültige Reorder-Daten"}},
)
async def reorder_memories(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Reihenfolge von Erinnerungen innerhalb eines Datums aktualisieren."""
    data = await request.json()
    order_list = data.get("order", [])

    if not isinstance(order_list, list) or len(order_list) > 100:
        raise HTTPException(status_code=400, detail="Ungültige Daten")

    for item in order_list:
        memory_id = item.get("id")
        sort_val = item.get("sort_order")
        if not isinstance(memory_id, int) or not isinstance(sort_val, int):
            continue
        if sort_val < 0 or sort_val > 999:
            continue
        memory = db.query(Memory).filter(Memory.id == memory_id).first()
        if memory:
            memory.sort_order = sort_val

    db.commit()
    logger.info("Reihenfolge aktualisiert von User #%d (%d Einträge)", current_user.id, len(order_list))
    return JSONResponse({"status": "ok"})


@router.get("/locations", response_model=None)
def list_saved_locations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> JSONResponse:
    """Alle gespeicherten Orte als Autocomplete-Vorschläge zurückgeben."""
    from sqlalchemy import distinct

    # Orte aus memories (location + lat/lng)
    locations: list[dict] = []
    seen: set[str] = set()

    rows = (
        db.query(Memory.location, Memory.lat, Memory.lng)
        .filter(Memory.location.isnot(None), Memory.location != "")
        .distinct()
        .order_by(Memory.location)
        .all()
    )
    for loc, lat, lng in rows:
        key = loc.strip().lower()
        if key not in seen:
            seen.add(key)
            locations.append({"name": loc, "lat": lat, "lng": lng})

    # Orte aus places Tabelle (name + country + lat/lng)
    place_rows = (
        db.query(Place.name, Place.country, Place.lat, Place.lng)
        .distinct()
        .order_by(Place.name)
        .all()
    )
    for name, country, lat, lng in place_rows:
        display = f"{name}, {country}" if country else name
        key = display.strip().lower()
        if key not in seen:
            seen.add(key)
            locations.append({"name": display, "lat": lat, "lng": lng})

    return JSONResponse(locations)


@router.get("", response_model=list[MemoryRead])
def list_memories(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    category: str | None = None,
    year: int | None = None,
    favorites_only: bool = False,
) -> list[Memory]:
    """Alle sichtbaren Erinnerungen abfragen, optional nach Kategorie, Jahr und Favoriten gefiltert."""
    query = db.query(Memory).filter(Memory.is_hidden == False)

    if category is not None:
        query = query.filter(Memory.category == category)

    if year is not None:
        from sqlalchemy import extract
        query = query.filter(extract("year", Memory.date) == year)

    if favorites_only:
        query = query.filter(Memory.is_favorite == True)

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


@router.get(
    "/{memory_id}",
    response_class=HTMLResponse,
    responses={404: {"description": _NOT_FOUND}},
)
def memory_detail(
    memory_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HTMLResponse:
    """Detailseite einer Erinnerung anzeigen."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    creator: User | None = db.query(User).filter(User.id == memory.created_by).first()

    return templates.TemplateResponse(
        "memory_detail.html",
        {"request": request, "user": current_user, "memory": memory, "creator": creator},
    )


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


@router.post(
    "/{memory_id}/delete",
    response_class=HTMLResponse,
    response_model=None,
    responses={404: {"description": _NOT_FOUND}},
)
def delete_memory_form(
    memory_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> RedirectResponse:
    """Erinnerung über HTML-Formular löschen und zum Dashboard weiterleiten."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    # Zugehörige Foto-Dateien vom Dateisystem entfernen
    for photo in memory.photos:
        try:
            safe_remove(photo.filepath)
        except OSError as exc:
            logger.warning("Foto-Datei konnte nicht gelöscht werden (%s): %s", photo.filepath, exc)

    db.delete(memory)
    db.commit()
    logger.info("Erinnerung #%d gelöscht von User #%d", memory_id, current_user.id)
    return RedirectResponse(url="/?success=deleted", status_code=303)


@router.delete("/{memory_id}", responses={404: {"description": _NOT_FOUND}})
def delete_memory(
    memory_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Erinnerung löschen (JSON-API)."""
    memory: Memory | None = db.query(Memory).filter(Memory.id == memory_id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    for photo in memory.photos:
        try:
            safe_remove(photo.filepath)
        except OSError as exc:
            logger.warning("Foto-Datei konnte nicht gelöscht werden (%s): %s", photo.filepath, exc)

    db.delete(memory)
    db.commit()
    return {"detail": "Erinnerung gelöscht"}
