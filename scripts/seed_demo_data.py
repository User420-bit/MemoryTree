#!/usr/bin/env python3
"""
Demo-Daten für Memory Tree — für Entwicklung und öffentliche Demos.

WARNUNG: Dieses Skript löscht alle Erinnerungen, Meilensteine, Fotos und Orte
DES ZIELPAARS und ersetzt sie durch fiktive Demo-Daten. Bestehende
Benutzerkonten werden nicht gelöscht, aber ihre Anzeigenamen werden auf
"Partner A" / "Partner B" zurückgesetzt. Andere Paare bleiben unberührt.

Nutzung:
    python3 scripts/seed_demo_data.py                 # Standard-Paar (#1)
    python3 scripts/seed_demo_data.py --couple-id 3   # anderes Paar

Nur in Entwicklungsumgebungen ausführen, niemals in Production mit echten Daten.
"""

import argparse
import os
import sys

# Projekt-Root zum Python-Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from demo_data import (
    DEMO_MEMORIES,
    DEMO_MILESTONES,
    DEMO_PARTNER_A,
    DEMO_PARTNER_B,
    DEMO_PARTNER_SINCE,
    demo_photo_ref,
    memory_columns,
)
from models import Couple, CoupleSettings, Memory, Milestone, Photo, Place, User

DEFAULT_COUPLE_ID = 1


def seed(couple_id: int):
    db = SessionLocal()
    try:
        couple = db.query(Couple).filter(Couple.id == couple_id).first()
        if couple is None:
            print(f"Paar #{couple_id} existiert nicht. Abgebrochen.")
            return

        # Konten des Paars — ohne sie gibt es keinen Ersteller für die
        # Demo-Erinnerungen.
        users = (
            db.query(User)
            .filter(User.couple_id == couple_id)
            .order_by(User.id.asc())
            .all()
        )
        if not users:
            print(
                f"Paar #{couple_id} hat noch keine Benutzerkonten — bitte zuerst\n"
                "  python3 scripts/seed.py            (Dev-Konten, DEBUG=true)\n"
                "  python3 scripts/create_users.py    (Konten direkt anlegen)\n"
                "ausführen."
            )
            return

        antwort = input(
            f"⚠️  WARNUNG: Alle Erinnerungen, Meilensteine und Fotos von Paar "
            f"#{couple_id} ({couple.name}) werden gelöscht und durch Demo-Daten "
            "ersetzt.\nFortfahren? (ja/nein): "
        )
        if antwort.lower() != "ja":
            print("Abgebrochen.")
            return

        # Nur die Daten DIESES Paars löschen. Photos und Places hängen über
        # memory_id an den Erinnerungen, deshalb über deren IDs filtern.
        memory_ids = [
            m.id for m in db.query(Memory.id).filter(Memory.couple_id == couple_id)
        ]
        if memory_ids:
            db.query(Photo).filter(Photo.memory_id.in_(memory_ids)).delete(
                synchronize_session=False
            )
            db.query(Place).filter(Place.memory_id.in_(memory_ids)).delete(
                synchronize_session=False
            )
        db.query(Memory).filter(Memory.couple_id == couple_id).delete(
            synchronize_session=False
        )
        db.query(Milestone).filter(Milestone.couple_id == couple_id).delete(
            synchronize_session=False
        )

        # CoupleSettings aktualisieren
        cs = (
            db.query(CoupleSettings)
            .filter(CoupleSettings.couple_id == couple_id)
            .first()
        )
        if cs:
            cs.partner_a_name = DEMO_PARTNER_A
            cs.partner_b_name = DEMO_PARTNER_B
            cs.partner_since = DEMO_PARTNER_SINCE

        # Anzeigenamen der Konten dieses Paars anonymisieren
        for user, anzeigename in zip(users, ("Partner A", "Partner B")):
            user.name = anzeigename

        creator_id = users[0].id

        # Demo-Erinnerungen samt Fotos und Orten einfügen. Die Fotos zeigen
        # auf die mitgelieferten Dateien unter static/demo/.
        for m in DEMO_MEMORIES:
            memory = Memory(
                couple_id=couple_id, created_by=creator_id, **memory_columns(m)
            )
            memory.photos = [
                Photo(filepath=demo_photo_ref(name), caption=caption)
                for name, caption in m.get("photos", [])
            ]
            memory.places = [Place(**place) for place in m.get("places", [])]
            db.add(memory)

        # Demo-Meilensteine einfügen
        for ms in DEMO_MILESTONES:
            db.add(Milestone(couple_id=couple_id, **ms))

        db.commit()
        print(f"✅ Demo-Daten für Paar #{couple_id} eingefügt.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--couple-id", type=int, default=DEFAULT_COUPLE_ID,
                        help=f"Zielpaar (Default: {DEFAULT_COUPLE_ID})")
    seed(parser.parse_args().couple_id)
