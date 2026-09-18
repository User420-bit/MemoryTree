# Demo-Inhalte für den Gastzugang und für scripts/seed_demo_data.py.
#
# Reine Daten, bewusst ohne DB- oder Config-Import: das Modul wird auf Vercel
# im Request-Pfad geladen (Gast-Paar anlegen) und soll dort nichts kosten.
#
# FOTOS: alle Gast-Paare teilen sich dieselben Dateien unter ``static/demo/``.
# Die Referenz beginnt mit ``static/demo/`` — der ``upload_url``-Filter macht
# daraus eine /static/-URL mit Content-Hash (sonst hielte der einjährige
# immutable-Cache ausgetauschte Bilder fest), und ``uploads.safe_remove`` fasst
# sie nicht an (nur ``c<Ziffern>``-Verzeichnisse unter UPLOAD_DIR). Löscht ein Gast
# ein Foto, verschwindet also nur seine DB-Zeile, nie die geteilte Datei.
# Die Bilder sind KI-generierte Fotos ohne erkennbare Gesichter, eingespielt
# mit scripts/import_demo_photos.py; scripts/make_demo_images.py zeichnet nur
# noch Platzhalter für Dateinamen, zu denen kein Bild existiert. Thumbnails
# liegen nach der üblichen Konvention unter
# ``static/demo/thumbs/<name>_thumb.jpg``. Bildunterschrift und Motiv gehören
# zusammen — wer eine Caption ändert, prüft, ob das Foto noch dazu passt.

import datetime
from typing import Any

DEMO_PHOTO_DIR = "static/demo"

DEMO_COUPLE_NAME = "Lena & Max (Demo)"
DEMO_PARTNER_A = "Lena"
DEMO_PARTNER_B = "Max"
DEMO_PARTNER_SINCE = datetime.date(2022, 2, 14)


def demo_photo_ref(filename: str) -> str:
    """DB-Referenz für ein mitgeliefertes Demo-Foto."""
    return f"{DEMO_PHOTO_DIR}/{filename}"


# Schlüssel, die nicht direkt auf Memory-Spalten abbilden, sondern eigene
# Zeilen ergeben. ``memory_columns()`` filtert sie heraus.
_RELATED_KEYS = ("photos", "places")


def memory_columns(entry: dict[str, Any]) -> dict[str, Any]:
    """Nur die Felder eines Eintrags, die Spalten von ``Memory`` sind."""
    return {k: v for k, v in entry.items() if k not in _RELATED_KEYS}


# ``photos``: Liste aus (Dateiname, Bildunterschrift).
# ``places``: Liste aus dicts mit name/country/lat/lng.
# ``is_favorite`` ohne tree_pos_*: der Baum verteilt gepinnte Erinnerungen dann
# auf seine festen Ankerpunkte, der Gast kann sie von dort aus verschieben.
DEMO_MEMORIES: list[dict[str, Any]] = [
    dict(
        title="Erster gemeinsamer Urlaub",
        date=datetime.date(2022, 7, 15),
        category="Urlaub",
        mood="🏖️",
        location="Mallorca, Spanien",
        lat=39.6953,
        lng=3.0176,
        description=(
            "Eine Woche Cala Millor: morgens Kaffee auf dem Balkon, mittags "
            "Buchten suchen, abends Tapas. Am dritten Tag haben wir den "
            "Mietwagen-Schlüssel im Sand verloren — und wiedergefunden."
        ),
        is_favorite=True,
        photos=[
            ("demo_mallorca_1.jpg", "Sonnenuntergang an der Cala"),
            ("demo_mallorca_2.jpg", "Unsere Lieblingsbucht"),
        ],
        places=[dict(name="Cala Millor", country="Spanien", lat=39.5960, lng=3.3830)],
    ),
    dict(
        title="Unser erstes gemeinsames Konzert",
        date=datetime.date(2022, 9, 3),
        category="Feier",
        mood="🎵",
        location="Hamburg",
        lat=53.5511,
        lng=9.9937,
        description="Zweite Reihe, viel zu laut, genau richtig. Max kann seitdem den Refrain nicht mehr hören.",
        photos=[("demo_konzert_1.jpg", "Kurz vor der Zugabe")],
    ),
    dict(
        title="Silvester in Berlin",
        date=datetime.date(2022, 12, 31),
        category="Feier",
        mood="🎉",
        location="Berlin",
        lat=52.5200,
        lng=13.4050,
        description="Dachterrasse in Kreuzberg, Raclette für zwölf Leute und um Mitternacht die ganze Stadt unter uns.",
        is_favorite=True,
        photos=[("demo_berlin_1.jpg", "Mitternacht über den Dächern")],
    ),
    dict(
        title="Unser erster Jahrestag",
        date=datetime.date(2023, 2, 14),
        category="Meilenstein",
        mood="❤️",
        location="München",
        lat=48.1351,
        lng=11.5820,
        description="Dasselbe Restaurant wie beim ersten Date, derselbe Tisch. Diesmal hat Lena nicht den Wein umgestoßen.",
        is_favorite=True,
        photos=[("demo_dinner_1.jpg", "Tisch Nummer sieben")],
    ),
    dict(
        title="Wanderung im Allgäu",
        date=datetime.date(2023, 4, 22),
        category="Abenteuer",
        mood="🏔️",
        location="Allgäu, Bayern",
        lat=47.5596,
        lng=10.2200,
        description="1.200 Höhenmeter, ein Gipfelkreuz und die beste Brotzeit unseres Lebens.",
        is_favorite=True,
        photos=[
            ("demo_allgaeu_1.jpg", "Blick vom Gipfel"),
            ("demo_allgaeu_2.jpg", "Abstieg im Abendlicht"),
        ],
        places=[dict(name="Nebelhorn", country="Deutschland", lat=47.4210, lng=10.3420)],
    ),
    dict(
        title="Zusammengezogen",
        date=datetime.date(2023, 6, 1),
        category="Meilenstein",
        mood="🏠",
        location="München",
        lat=48.1500,
        lng=11.5600,
        description="47 Kartons, ein Sofa, das nicht durchs Treppenhaus passte, und die erste Nacht auf der Matratze am Boden.",
    ),
    dict(
        title="Wochenende in Wien",
        date=datetime.date(2023, 8, 11),
        category="Urlaub",
        mood="🏙️",
        location="Wien, Österreich",
        lat=48.2082,
        lng=16.3738,
        description="Sachertorte-Vergleichstest in drei Kaffeehäusern. Ergebnis: unentschieden, Wiederholung nötig.",
        photos=[("demo_wien_1.jpg", "Abends am Donaukanal")],
        places=[dict(name="Prater", country="Österreich", lat=48.2167, lng=16.3958)],
    ),
    dict(
        title="Gemeinsames Kochen — Erstes Dinner",
        date=datetime.date(2023, 11, 5),
        category="Alltag",
        mood="🍝",
        location="Zuhause",
        description="Selbstgemachte Pasta. Die Küche sah danach aus wie nach einem Mehl-Unfall, geschmeckt hat es trotzdem.",
        photos=[("demo_dinner_2.jpg", "Pasta Nummer eins")],
    ),
    dict(
        title="Skiurlaub in den Alpen",
        date=datetime.date(2024, 1, 20),
        category="Abenteuer",
        mood="⛷️",
        location="Innsbruck, Österreich",
        lat=47.2692,
        lng=11.4041,
        description="Max' erste rote Piste. Lena hat alles gefilmt, inklusive Sturz.",
        is_favorite=True,
        photos=[("demo_ski_1.jpg", "Erste Gondel am Morgen")],
        places=[dict(name="Axamer Lizum", country="Österreich", lat=47.1950, lng=11.3020)],
    ),
    dict(
        title="Zweiter Jahrestag",
        date=datetime.date(2024, 2, 14),
        category="Meilenstein",
        mood="💑",
        location="Paris, Frankreich",
        lat=48.8566,
        lng=2.3522,
        description="Überraschungsreise. Lena wusste bis zum Gate nicht, wohin es geht.",
        is_favorite=True,
        photos=[
            ("demo_paris_1.jpg", "Blaue Stunde an der Seine"),
            ("demo_paris_2.jpg", "Montmartre am Morgen"),
        ],
        places=[dict(name="Montmartre", country="Frankreich", lat=48.8867, lng=2.3431)],
    ),
    dict(
        title="Sommerkonzert Open Air",
        date=datetime.date(2024, 7, 8),
        category="Feier",
        mood="🎶",
        location="Frankfurt am Main",
        lat=50.1109,
        lng=8.6821,
        description="Picknickdecke, Gewitter nach dem dritten Lied, weitergetanzt haben wir trotzdem.",
        photos=[("demo_konzert_2.jpg", "Bevor der Regen kam")],
    ),
    dict(
        title="Roadtrip an die Amalfiküste",
        date=datetime.date(2024, 9, 14),
        category="Urlaub",
        mood="🚗",
        location="Amalfi, Italien",
        lat=40.6340,
        lng=14.6027,
        description="Ein Fiat 500, 1.400 Kilometer und Serpentinen, bei denen nur eine von uns fahren wollte.",
        photos=[("demo_amalfi_1.jpg", "Die Küstenstraße")],
        places=[
            dict(name="Positano", country="Italien", lat=40.6281, lng=14.4850),
            dict(name="Ravello", country="Italien", lat=40.6492, lng=14.6117),
        ],
    ),
    dict(
        title="Überraschungsparty zum 30.",
        date=datetime.date(2025, 3, 22),
        category="Besonderes",
        mood="🎂",
        location="München",
        lat=48.1351,
        lng=11.5820,
        description="Sechs Wochen Geheimhaltung, 25 Gäste hinter dem Sofa — und Max hat wirklich nichts geahnt.",
    ),
    # Versteckt: zeigt den Verwaltungsbereich in den Einstellungen.
    dict(
        title="Geschenkidee — noch geheim",
        date=datetime.date(2025, 5, 2),
        category="Besonderes",
        mood="🎁",
        location="Zuhause",
        description="Versteckte Erinnerungen tauchen in keiner Ansicht auf, nur in den Einstellungen.",
        is_hidden=True,
    ),
]

DEMO_MILESTONES: list[dict[str, Any]] = [
    dict(
        title="Erstes Date",
        date=datetime.date(2022, 2, 14),
        icon="❤️",
        description="Der Anfang von allem.",
        is_anniversary=True,
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
    dict(
        title="Zweiter Jahrestag in Paris",
        date=datetime.date(2024, 2, 14),
        icon="🗼",
        description="Überraschungsreise mit Blick auf die Seine.",
    ),
    dict(
        title="1000 Tage zusammen",
        date=datetime.date(2024, 11, 10),
        icon="🌟",
        description="Tausend Tage, gefühlt ein Wimpernschlag.",
    ),
]


def demo_photo_filenames() -> list[str]:
    """Alle referenzierten Foto-Dateinamen — die Demo-Bild-Skripte prüfen dagegen."""
    return [name for m in DEMO_MEMORIES for name, _caption in m.get("photos", [])]
