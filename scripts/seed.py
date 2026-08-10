#!/usr/bin/env python3
"""Memory Tree — Basisdaten anlegen (idempotent)

Ersetzt die frühere Startup-Initialisierung aus ``main._init_database``:
seit der Vercel-Migration läuft beim App-Start keine DDL und kein Seeding
mehr (jede serverlose Function-Instanz würde das sonst erneut tun).

Nutzung — zuerst das Schema anlegen, dann seeden:

    alembic upgrade head
    python3 scripts/seed.py

Legt an, falls nicht vorhanden:
  - das Standard-Paar (id 1) samt CoupleSettings (OHNE partner_since — das
    Datum wird ausschließlich über POST /settings gesetzt)
  - die Dev-Benutzer partner_a / partner_b in diesem Paar, aber NUR wenn
    APP_ENV != production UND DEBUG=true (Doppel-Gate wie zuvor).
    Für Production: scripts/create_users.py verwenden.

Weitere Paare werden nicht hier, sondern über scripts/create_invite.py
angelegt — dort entsteht Paar plus Einladungscode in einem Schritt.
"""

import sys
from pathlib import Path

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from auth import hash_password  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Couple, CoupleSettings, User  # noqa: E402

DEV_PASSWORD = "test1234"

# Das Paar, an das die Migration allen Altbestand gehängt hat.
DEFAULT_COUPLE_ID = 1


def seed_default_couple(db: Session) -> Couple:
    """Standard-Paar sicherstellen (die Migration legt es normalerweise an)."""
    couple = db.query(Couple).filter(Couple.id == DEFAULT_COUPLE_ID).first()
    if couple is None:
        couple = Couple(id=DEFAULT_COUPLE_ID, name="Standard")
        db.add(couple)
        db.flush()
    return couple


def seed_couple_settings(db: Session, couple_id: int) -> bool:
    """Paar-Einstellungen anlegen, falls für dieses Paar noch keine existieren."""
    existing = (
        db.query(CoupleSettings)
        .filter(CoupleSettings.couple_id == couple_id)
        .first()
    )
    if existing is not None:
        return False
    db.add(CoupleSettings(
        couple_id=couple_id,
        partner_a_name="Partner A",
        partner_b_name="Partner B",
    ))
    return True


def seed_dev_users(db: Session, couple_id: int) -> int:
    """Dev-Benutzer anlegen. Gibt die Anzahl neuer Benutzer zurück."""
    created = 0
    for username, name in (("partner_a", "Partner A"), ("partner_b", "Partner B")):
        if db.query(User).filter(User.username == username).first() is not None:
            continue
        # SCHUTZLOGIK: ohne partner_since — das Beziehungsdatum lebt
        # ausschließlich in couple_settings.
        db.add(User(
            couple_id=couple_id,
            name=name,
            username=username,
            hashed_password=hash_password(DEV_PASSWORD),
        ))
        created += 1
    return created


def main() -> None:
    print("=== Memory Tree — Basisdaten anlegen ===\n")

    db: Session = SessionLocal()
    try:
        couple = seed_default_couple(db)
        print(f"· Standard-Paar #{couple.id} ({couple.name})")

        if seed_couple_settings(db, couple.id):
            print("✓ Paar-Einstellungen erstellt (ohne Datum)")
        else:
            print("· Paar-Einstellungen existieren bereits")

        if not settings.is_production and settings.DEBUG:
            print(
                "\nDEV-MODUS: Erstelle Standard-Benutzer mit bekanntem "
                "Passwort. NIEMALS in Production!"
            )
            created = seed_dev_users(db, couple.id)
            print(f"✓ {created} Dev-Benutzer erstellt" if created
                  else "· Dev-Benutzer existieren bereits")
        else:
            user_count = db.query(User).count()
            if user_count == 0:
                print(
                    "\n! Keine Benutzer vorhanden. Konten anlegen mit:\n"
                    "    python3 scripts/create_users.py    (direkt, für das Standard-Paar)\n"
                    "    python3 scripts/create_invite.py   (Einladungscode für ein neues Paar)"
                )
            else:
                print(f"· {user_count} Benutzer vorhanden")

        db.commit()
        print("\nFertig.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
