# Mandantentrennung: jeder Datenzugriff wird auf das Paar des angemeldeten
# Benutzers eingeschränkt.
#
# SICHERHEITSGRENZE: Router und Seiten-Routen dürfen Memory, Milestone, Photo,
# Place und CoupleSettings NIE ungefiltert laden. Alle Zugriffe laufen über die
# Helfer in diesem Modul — so gibt es genau eine Stelle, an der die Filterung
# stattfindet, statt einer Filterbedingung pro Query-Aufruf.
#
# Nicht gefundene UND fremde Datensätze liefern beide 404 (nie 403): ein
# unterschiedlicher Statuscode würde verraten, ob eine ID in einem anderen
# Paar existiert.

import logging
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Query, Session

from auth import get_current_user
from database import get_db
from models import CoupleSettings, Memory, Milestone, Photo, Place, User

logger = logging.getLogger(__name__)

_MEMORY_NOT_FOUND = "Erinnerung nicht gefunden"
_MILESTONE_NOT_FOUND = "Meilenstein nicht gefunden"
_PHOTO_NOT_FOUND = "Foto nicht gefunden"


# ── Dependency ──────────────────────────────────────────────────────────────

def get_current_couple_id(
    current_user: Annotated[User, Depends(get_current_user)],
) -> int:
    """Paar-ID des angemeldeten Benutzers.

    Bewusst aus der Datenbank (über den User) statt aus einem JWT-Claim: so
    wirkt ein Paarwechsel sofort und ein alter Token kann keine veraltete
    Zugehörigkeit mitschleppen.
    """
    return current_user.couple_id


CoupleId = Annotated[int, Depends(get_current_couple_id)]


# ── Query-Basis ─────────────────────────────────────────────────────────────

def scoped_memories(db: Session, couple_id: int) -> Query:
    """Basis-Query für Erinnerungen des Paars (inklusive versteckter)."""
    return db.query(Memory).filter(Memory.couple_id == couple_id)


def visible_memories(db: Session, couple_id: int) -> Query:
    """Wie ``scoped_memories``, aber ohne versteckte Erinnerungen.

    Das ist der Normalfall für alle Ansichten — versteckte Erinnerungen
    erscheinen ausschließlich im Verwaltungsbereich der Einstellungen.
    """
    return scoped_memories(db, couple_id).filter(Memory.is_hidden == False)  # noqa: E712


def scoped_milestones(db: Session, couple_id: int) -> Query:
    """Basis-Query für Meilensteine des Paars."""
    return db.query(Milestone).filter(Milestone.couple_id == couple_id)


def scoped_photos(db: Session, couple_id: int) -> Query:
    """Basis-Query für Fotos des Paars (über den Join auf die Erinnerung)."""
    return (
        db.query(Photo)
        .join(Memory, Photo.memory_id == Memory.id)
        .filter(Memory.couple_id == couple_id)
    )


def scoped_places(db: Session, couple_id: int) -> Query:
    """Basis-Query für Orte des Paars (über den Join auf die Erinnerung)."""
    return (
        db.query(Place)
        .join(Memory, Place.memory_id == Memory.id)
        .filter(Memory.couple_id == couple_id)
    )


def scoped_users(db: Session, couple_id: int) -> Query:
    """Basis-Query für die Benutzerkonten des Paars."""
    return db.query(User).filter(User.couple_id == couple_id)


# ── Einzelzugriff mit Besitzprüfung ─────────────────────────────────────────

def get_owned_memory(db: Session, couple_id: int, memory_id: int) -> Memory:
    """Erinnerung des Paars laden oder 404 werfen."""
    memory: Memory | None = (
        scoped_memories(db, couple_id).filter(Memory.id == memory_id).first()
    )
    if memory is None:
        raise HTTPException(status_code=404, detail=_MEMORY_NOT_FOUND)
    return memory


def get_owned_milestone(db: Session, couple_id: int, milestone_id: int) -> Milestone:
    """Meilenstein des Paars laden oder 404 werfen."""
    milestone: Milestone | None = (
        scoped_milestones(db, couple_id).filter(Milestone.id == milestone_id).first()
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail=_MILESTONE_NOT_FOUND)
    return milestone


def get_owned_photo(db: Session, couple_id: int, photo_id: int) -> Photo:
    """Foto des Paars laden oder 404 werfen."""
    photo: Photo | None = (
        scoped_photos(db, couple_id).filter(Photo.id == photo_id).first()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail=_PHOTO_NOT_FOUND)
    return photo


# ── Paar-Einstellungen ──────────────────────────────────────────────────────

def get_couple_settings(db: Session, couple_id: int) -> CoupleSettings | None:
    """Einstellungen des Paars lesen (ohne anzulegen).

    Für Lesepfade gedacht, die auch ohne Einstellungszeile funktionieren
    müssen — etwa die Sprachauflösung im Middleware-Pfad.
    """
    return (
        db.query(CoupleSettings)
        .filter(CoupleSettings.couple_id == couple_id)
        .first()
    )


def get_or_create_couple_settings(db: Session, couple_id: int) -> CoupleSettings:
    """Einstellungen des Paars lesen, bei Bedarf mit Defaults anlegen.

    SCHUTZLOGIK: ``partner_since`` wird hier NICHT gesetzt — das Beziehungs-
    datum darf ausschließlich über ``POST /settings`` geändert werden.
    """
    cs = get_couple_settings(db, couple_id)
    if cs is None:
        cs = CoupleSettings(
            couple_id=couple_id,
            partner_a_name="Partner A",
            partner_b_name="Partner B",
        )
        db.add(cs)
        db.commit()
        db.refresh(cs)
    return cs
