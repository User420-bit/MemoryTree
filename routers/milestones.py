# Meilenstein-Verwaltung

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Milestone, User
from schemas import MilestoneCreate, MilestoneRead, MilestoneUpdate

router = APIRouter(prefix="/api/milestones", tags=["Meilensteine"])


@router.get("", response_model=list[MilestoneRead])
def list_milestones(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Milestone]:
    """Alle Meilensteine auflisten, nach Datum absteigend sortiert."""

    milestones: list[Milestone] = (
        db.query(Milestone).order_by(Milestone.date.desc()).all()
    )
    return milestones


@router.post("", response_model=MilestoneRead, status_code=status.HTTP_201_CREATED)
def create_milestone(
    data: MilestoneCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Milestone:
    """Einen neuen Meilenstein erstellen."""

    milestone = Milestone(**data.model_dump())
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


@router.put("/{milestone_id}", response_model=MilestoneRead)
def update_milestone(
    milestone_id: int,
    data: MilestoneUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Milestone:
    """Einen Meilenstein aktualisieren (nur übergebene Felder)."""

    milestone: Milestone | None = (
        db.query(Milestone).filter(Milestone.id == milestone_id).first()
    )
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meilenstein nicht gefunden",
        )

    update_data: dict = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(milestone, field, value)

    db.commit()
    db.refresh(milestone)
    return milestone


@router.delete("/{milestone_id}")
def delete_milestone(
    milestone_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Einen Meilenstein löschen."""

    milestone: Milestone | None = (
        db.query(Milestone).filter(Milestone.id == milestone_id).first()
    )
    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meilenstein nicht gefunden",
        )

    db.delete(milestone)
    db.commit()
    return {"detail": "Meilenstein gelöscht"}
