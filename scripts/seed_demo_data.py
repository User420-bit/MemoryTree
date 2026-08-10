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
import datetime
import os
import sys

# Projekt-Root zum Python-Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import Couple, CoupleSettings, Memory, Milestone, Photo, Place, User

DEFAULT_COUPLE_ID = 1

DEMO_MEMORIES = [
    dict(
        title="Erster gemeinsamer Urlaub",
        date=datetime.date(2022, 7, 15),
        category="Urlaub",
        mood="🏖️",
        location="Mallorca, Spanien",
    ),
    dict(
        title="Unser erstes gemeinsames Konzert",
        date=datetime.date(2022, 9, 3),
        category="Feier",
        mood="🎵",
        location="Hamburg",
    ),
    dict(
        title="Silvester in Berlin",
        date=datetime.date(2022, 12, 31),
        category="Feier",
        mood="🎉",
        location="Berlin",
    ),
    dict(
        title="Wanderung im Allgäu",
        date=datetime.date(2023, 4, 22),
        category="Abenteuer",
        mood="🏔️",
        location="Allgäu, Bayern",
    ),
    dict(
        title="Unser erster Jahrestag",
        date=datetime.date(2023, 2, 14),
        category="Meilenstein",
        mood="❤️",
        location="München",
    ),
    dict(
        title="Wochenende in Wien",
        date=datetime.date(2023, 8, 11),
        category="Urlaub",
        mood="🏙️",
        location="Wien, Österreich",
    ),
    dict(
        title="Gemeinsames Kochen — Erstes Dinner",
        date=datetime.date(2023, 11, 5),
        category="Alltag",
        mood="🍝",
        location="Zuhause",
    ),
    dict(
        title="Skiurlaub in den Alpen",
        date=datetime.date(2024, 1, 20),
        category="Abenteuer",
        mood="⛷️",
        location="Innsbruck, Österreich",
    ),
    dict(
        title="Zweiter Jahrestag",
        date=datetime.date(2024, 2, 14),
        category="Meilenstein",
        mood="💑",
        location="Paris, Frankreich",
    ),
    dict(
        title="Sommerkonzert Open Air",
        date=datetime.date(2024, 7, 8),
        category="Feier",
        mood="🎶",
        location="Frankfurt am Main",
    ),
]

DEMO_MILESTONES = [
    dict(
        title="Erstes Date",
        date=datetime.date(2022, 2, 14),
        icon="❤️",
        description="Der Anfang von allem.",
    ),
    dict(
        title="Erster gemeinsamer Urlaub",
        date=datetime.date(2022, 7, 15),
        icon="✈️",
        description="Eine Woche Mallorca — unvergesslich.",
    ),
    dict(
        title="Zusammengezogen",
        date=datetime.date(2023, 6, 1),
        icon="🏠",
        description="Unser erstes gemeinsames Zuhause.",
    ),
]


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
            cs.partner_a_name = "Lena"
            cs.partner_b_name = "Max"
            cs.partner_since = datetime.date(2022, 2, 14)

        # Anzeigenamen der Konten dieses Paars anonymisieren
        for user, anzeigename in zip(users, ("Partner A", "Partner B")):
            user.name = anzeigename

        creator_id = users[0].id

        # Demo-Erinnerungen einfügen
        for m in DEMO_MEMORIES:
            db.add(Memory(couple_id=couple_id, created_by=creator_id, **m))

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
