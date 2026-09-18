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
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Query, Session

from auth import get_current_user
from config import settings
from database import get_db
from demo_data import (
    DEMO_COUPLE_NAME,
    DEMO_MEMORIES,
    DEMO_MILESTONES,
    DEMO_PARTNER_A,
    DEMO_PARTNER_B,
    DEMO_PARTNER_SINCE,
    demo_photo_ref,
    memory_columns,
)
from models import (
    Couple, CoupleSettings, Invite, Memory, Milestone, Photo, Place, User,
)

logger = logging.getLogger(__name__)

_MEMORY_NOT_FOUND = "Erinnerung nicht gefunden"
_MILESTONE_NOT_FOUND = "Meilenstein nicht gefunden"
_PHOTO_NOT_FOUND = "Foto nicht gefunden"
_DEMO_FORBIDDEN = "Im Demo-Modus nicht verfügbar"


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


# ── Demo-Paare (Gastzugang) ─────────────────────────────────────────────────
#
# Ein Gast bekommt kein geteiltes Schau-Konto, sondern ein eigenes Paar: damit
# trennt dieselbe couple_id-Filterung, die echte Paare schützt, auch die Gäste
# voneinander — was einer ändert, sieht kein anderer. Der Preis sind Zeilen in
# der Datenbank, die ein anonymer Besucher auslöst; deshalb Ablaufdatum,
# Aufräumlauf und eine harte Obergrenze.

# Kein bcrypt-Hash, passt also auf kein Passwort (siehe auth.verify_password).
# Spart außerdem die ~250 ms bcrypt pro Gast im Request-Pfad.
GUEST_PASSWORD_HASH = "!"

GUEST_USERNAME_PREFIX = "guest_"

# Wie viele abgelaufene Paare ein einzelner Aufruf höchstens abräumt — der
# Lauf hängt am Demo-Einstieg und darf dessen Antwortzeit nicht sprengen.
_SWEEP_BATCH = 20


def is_demo_user(user: User) -> bool:
    """Gehört das Konto zu einem Demo-Paar?

    Liest ``user.couple`` — über ``get_current_user`` ist das Paar bereits per
    JOIN geladen, der Zugriff kostet dort also keinen weiteren Roundtrip.
    """
    return user.couple.is_demo


def require_non_demo(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Dependency: Route für Gäste sperren (403).

    Für alles, was ein anonymer Besucher nicht auslösen darf: Dateien
    speichern (Blob-Kosten, fremde Inhalte auf unserer Domain) und Login-Daten
    eines Gast-Kontos ändern. 403 statt 404 ist hier richtig — es geht nicht
    um eine fremde ID, deren Existenz verborgen bleiben muss, sondern um eine
    Funktion, die es im Demo-Modus erklärtermaßen nicht gibt.
    """
    if is_demo_user(current_user):
        raise HTTPException(status_code=403, detail=_DEMO_FORBIDDEN)


def _demo_couples(db: Session) -> Query:
    return db.query(Couple).filter(Couple.is_demo == True)  # noqa: E712


def delete_demo_couple(db: Session, couple_id: int) -> bool:
    """Ein Demo-Paar mit allem, was daran hängt, löschen.

    Weigert sich bei echten Paaren: das ist die einzige Stelle im Code, die
    einen ganzen Mandanten entfernt, und sie soll durch keinen Aufrufer-Fehler
    echte Erinnerungen treffen können. ``False`` = nichts gelöscht.

    Dateien werden nicht angefasst. Gäste dürfen nichts hochladen; ihre Fotos
    zeigen auf die geteilten Bilder unter ``static/demo/``.

    Committet nicht selbst — der Aufrufer bestimmt die Transaktion.
    """
    is_demo = (
        _demo_couples(db).filter(Couple.id == couple_id).with_entities(Couple.id).first()
    )
    if is_demo is None:
        logger.warning("delete_demo_couple: Paar #%s ist kein Demo-Paar", couple_id)
        return False

    # Reihenfolge folgt den Fremdschlüsseln: users/memories/milestones
    # kaskadieren nicht von couples, memories hängt zusätzlich an users.
    memory_ids = db.query(Memory.id).filter(Memory.couple_id == couple_id)
    db.query(Photo).filter(Photo.memory_id.in_(memory_ids)).delete(
        synchronize_session=False
    )
    db.query(Place).filter(Place.memory_id.in_(memory_ids)).delete(
        synchronize_session=False
    )
    for model in (Memory, Milestone, CoupleSettings, Invite, User):
        db.query(model).filter(model.couple_id == couple_id).delete(
            synchronize_session=False
        )
    db.query(Couple).filter(Couple.id == couple_id).delete(synchronize_session=False)
    return True


def sweep_expired_demo_couples(db: Session, limit: int = _SWEEP_BATCH) -> int:
    """Abgelaufene Demo-Paare löschen, älteste zuerst. Gibt die Anzahl zurück."""
    now = datetime.now(timezone.utc)
    expired_ids = [
        row.id
        for row in _demo_couples(db)
        .filter(Couple.expires_at != None, Couple.expires_at < now)  # noqa: E711
        .order_by(Couple.expires_at.asc())
        .limit(limit)
        .with_entities(Couple.id)
    ]
    for couple_id in expired_ids:
        delete_demo_couple(db, couple_id)
    if expired_ids:
        db.commit()
    return len(expired_ids)


def _make_room_for_demo_couple(db: Session) -> None:
    """Obergrenze durchsetzen: bei vollem Kontingent das älteste Paar recyceln.

    Verdrängen statt ablehnen — ein Besucher soll die Demo immer sehen können.
    Getroffen wird, wer am längsten da ist und damit am ehesten schon weg.
    """
    overflow = _demo_couples(db).count() - settings.MAX_DEMO_COUPLES + 1
    if overflow <= 0:
        return
    oldest = (
        _demo_couples(db)
        .order_by(Couple.created_at.asc(), Couple.id.asc())
        .limit(overflow)
        .with_entities(Couple.id)
    )
    for row in oldest.all():
        delete_demo_couple(db, row.id)


def create_demo_couple(db: Session) -> User:
    """Frisches Demo-Paar samt Gast-Konto anlegen und mit Demo-Daten füllen.

    Räumt vorher auf (abgelaufene Paare, Obergrenze), damit der Bestand auch
    ohne Cron begrenzt bleibt. Gibt das Gast-Konto zurück; der Aufrufer setzt
    damit die Auth-Cookies.
    """
    sweep_expired_demo_couples(db)
    _make_room_for_demo_couple(db)

    couple = Couple(
        name=DEMO_COUPLE_NAME,
        is_demo=True,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.DEMO_TTL_MINUTES),
    )
    db.add(couple)
    db.flush()  # couple.id für die abhängigen Zeilen

    guest = User(
        couple_id=couple.id,
        name=DEMO_PARTNER_A,
        # Benutzernamen sind global eindeutig; 64 Bit Zufall statt einer
        # Zählnummer, damit sich Gast-Konten nicht durchnummerieren lassen.
        username=GUEST_USERNAME_PREFIX + secrets.token_hex(8),
        hashed_password=GUEST_PASSWORD_HASH,
    )
    db.add(guest)
    db.add(
        CoupleSettings(
            couple_id=couple.id,
            partner_a_name=DEMO_PARTNER_A,
            partner_b_name=DEMO_PARTNER_B,
            partner_since=DEMO_PARTNER_SINCE,
        )
    )
    db.flush()  # guest.id für created_by

    for entry in DEMO_MEMORIES:
        memory = Memory(
            couple_id=couple.id, created_by=guest.id, **memory_columns(entry)
        )
        memory.photos = [
            Photo(filepath=demo_photo_ref(name), caption=caption)
            for name, caption in entry.get("photos", [])
        ]
        memory.places = [Place(**place) for place in entry.get("places", [])]
        db.add(memory)
    for entry in DEMO_MILESTONES:
        db.add(Milestone(couple_id=couple.id, **entry))

    db.commit()
    db.refresh(guest)
    return guest
