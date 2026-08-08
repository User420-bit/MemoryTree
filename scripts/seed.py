#!/usr/bin/env python3
"""Memory Tree — Basisdaten anlegen (idempotent)

Ersetzt die frühere Startup-Initialisierung aus ``main._init_database``:
seit der Vercel-Migration läuft beim App-Start keine DDL und kein Seeding
mehr (jede serverlose Function-Instanz würde das sonst erneut tun).

Nutzung — zuerst das Schema anlegen, dann seeden:

    alembic upgrade head
    python3 scripts/seed.py

Legt an, falls nicht vorhanden:
  - den CoupleSettings-Singleton (OHNE partner_since — das Datum wird
    ausschließlich über POST /settings gesetzt)
  - die Dev-Benutzer partner_a / partner_b, aber NUR wenn
    APP_ENV != production UND DEBUG=true (Doppel-Gate wie zuvor).
    Für Production: scripts/create_users.py verwenden.
"""

import sys
from pathlib import Path

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from auth import hash_password  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import CoupleSettings, User  # noqa: E402

DEV_PASSWORD = "test1234"


def seed_couple_settings(db: Session) -> bool:
    """Paar-Einstellungen anlegen, falls noch keine existieren."""
    if db.query(CoupleSettings).first() is not None:
        return False
    db.add(CoupleSettings(partner_a_name="Partner A", partner_b_name="Partner B"))
    return True


def seed_dev_users(db: Session) -> int:
    """Dev-Benutzer anlegen. Gibt die Anzahl neuer Benutzer zurück."""
    created = 0
    for username, name in (("partner_a", "Partner A"), ("partner_b", "Partner B")):
        if db.query(User).filter(User.username == username).first() is not None:
            continue
        # SCHUTZLOGIK: ohne partner_since — das Beziehungsdatum lebt
        # ausschließlich in couple_settings.
        db.add(User(
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
        if seed_couple_settings(db):
            print("✓ Paar-Einstellungen erstellt (ohne Datum)")
        else:
            print("· Paar-Einstellungen existieren bereits")

        if not settings.is_production and settings.DEBUG:
            print(
                "\nDEV-MODUS: Erstelle Standard-Benutzer mit bekanntem "
                "Passwort. NIEMALS in Production!"
            )
            created = seed_dev_users(db)
            print(f"✓ {created} Dev-Benutzer erstellt" if created
                  else "· Dev-Benutzer existieren bereits")
        else:
            user_count = db.query(User).count()
            if user_count == 0:
                print(
                    "\n! Keine Benutzer vorhanden. Production-Accounts anlegen mit:\n"
                    "    python3 scripts/create_users.py"
                )
            else:
                print(f"· {user_count} Benutzer vorhanden")

        db.commit()
        print("\nFertig.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
