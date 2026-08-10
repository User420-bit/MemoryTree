# Meilenstein-Verwaltung

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Milestone, User
from schemas import MilestoneCreate, MilestoneRead, MilestoneUpdate
from tenancy import CoupleId, get_owned_milestone, scoped_milestones

router = APIRouter(prefix="/api/milestones", tags=["Meilensteine"])

# Mandantenzugehörigkeit ist nie über die API änderbar.
_GESCHUETZTE_FELDER: frozenset[str] = frozenset({"couple_id"})


@router.get("", response_model=list[MilestoneRead])
def list_milestones(
    current_user: Annotated[User, Depends(get_current_user)],
    couple_id: CoupleId,
    db: Annotated[Session, Depends(get_db)],
) -> list[Milestone]:
    """Meilensteine des Paars auflisten, nach Datum absteigend sortiert."""

    return scoped_milestones(db, couple_id).order_by(Milestone.date.desc()).all()


@router.post("", response_model=MilestoneRead, status_code=status.HTTP_201_CREATED)
def create_milestone(
    data: MilestoneCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    couple_id: CoupleId,
    db: Annotated[Session, Depends(get_db)],
) -> Milestone:
    """Einen neuen Meilenstein erstellen."""

    milestone = Milestone(couple_id=couple_id, **data.model_dump())
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.put("/{milestone_id}", response_model=MilestoneRead)
def update_milestone(
    milestone_id: int,
    data: MilestoneUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    couple_id: CoupleId,
    db: Annotated[Session, Depends(get_db)],
) -> Milestone:
    """Einen Meilenstein aktualisieren (nur übergebene Felder)."""

    milestone = get_owned_milestone(db, couple_id, milestone_id)

    update_data: dict = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _GESCHUETZTE_FELDER:
            continue
        setattr(milestone, field, value)

    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete("/{milestone_id}")
def delete_milestone(
    milestone_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    couple_id: CoupleId,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Einen Meilenstein löschen."""

    milestone = get_owned_milestone(db, couple_id, milestone_id)

    db.delete(milestone)
    db.commit()
    return {"detail": "Meilenstein gelöscht"}
