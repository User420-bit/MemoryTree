# CRUD-Routen für Erinnerungen

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Memory, Place, User
from schemas import MemoryCreate, MemoryRead, MemoryUpdate

router = APIRouter(prefix="/memories", tags=["Erinnerungen"])

_NOT_FOUND = "Erinnerung nicht gefunden"


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
    """Neue Erinnerung anlegen. Legt ggf. auch einen Ort an."""
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
    db.flush()  # ID verfügbar machen

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
