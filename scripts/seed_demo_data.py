#!/usr/bin/env python3
"""
Demo-Daten für Memory Tree — für Entwicklung und öffentliche Demos.

WARNUNG: Dieses Skript löscht alle bestehenden Erinnerungen, Meilensteine,
Fotos und Orte und ersetzt sie durch fiktive Demo-Daten. Bestehende
Benutzerkonten werden nicht gelöscht, aber ihre Anzeigenamen werden auf
"Partner A" / "Partner B" zurückgesetzt.

Nur in Entwicklungsumgebungen ausführen, niemals in Production mit echten Daten.
"""

import datetime
import os
import sys

# Projekt-Root zum Python-Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import CoupleSettings, Memory, Milestone, Photo, Place, User

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


def seed():
    db = SessionLocal()
    try:
        antwort = input(
            "⚠️  WARNUNG: Alle Erinnerungen, Meilensteine und Fotos werden gelöscht "
            "und durch Demo-Daten ersetzt.\nFortfahren? (ja/nein): "
        )
        if antwort.lower() != "ja":
            print("Abgebrochen.")
            return

        # Daten löschen (Reihenfolge wegen Foreign Keys)
        db.query(Photo).delete()
        db.query(Place).delete()
        db.query(Memory).delete()
        db.query(Milestone).delete()

        # CoupleSettings aktualisieren
        cs = db.query(CoupleSettings).first()
        if cs:
            cs.partner_a_name = "Lena"
            cs.partner_b_name = "Max"
            cs.partner_since = datetime.date(2022, 2, 14)

        # Anzeigenamen bestehender Nutzerkonten anonymisieren
        partner_a = db.query(User).filter(User.username == "partner_a").first()
        if partner_a:
            partner_a.name = "Partner A"
        partner_b = db.query(User).filter(User.username == "partner_b").first()
        if partner_b:
            partner_b.name = "Partner B"

        creator_id = partner_a.id if partner_a else (partner_b.id if partner_b else None)
        if creator_id is None:
            print(
                "Kein Benutzer 'partner_a'/'partner_b' gefunden — bitte zuerst "
                "die App einmal starten (main.py legt Dev-User automatisch an) "
                "oder scripts/create_users.py ausführen."
            )
            return

        # Demo-Erinnerungen einfügen
        for m in DEMO_MEMORIES:
            db.add(Memory(created_by=creator_id, **m))

        # Demo-Meilensteine einfügen
        for ms in DEMO_MILESTONES:
            db.add(Milestone(**ms))

        db.commit()
        print("✅ Demo-Daten erfolgreich eingefügt.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
