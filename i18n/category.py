# Anzeigenamen der Memory-Kategorien (CategoryEnum in models.py).
# Die Dict-Keys sind die gespeicherten Werte (deutsch) — NICHT ändern,
# da sie als DB-/Filter-Werte verwendet werden. Nur "de"/"en" sind
# reine Anzeigetexte.

STRINGS: dict[str, dict[str, str]] = {
    "Urlaub": {"de": "Urlaub", "en": "Vacation"},
    "Meilenstein": {"de": "Meilenstein", "en": "Milestone"},
    "Feier": {"de": "Feier", "en": "Celebration"},
    "Alltag": {"de": "Alltag", "en": "Everyday"},
    "Abenteuer": {"de": "Abenteuer", "en": "Adventure"},
    "Besonderes": {"de": "Besonderes", "en": "Special"},
}
