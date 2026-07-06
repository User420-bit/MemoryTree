# i18n: einfaches Key-basiertes Übersetzungssystem (Deutsch/Englisch)
#
# Jede Seite hat ein eigenes Namespace-Modul (z.B. i18n/dashboard.py) mit
# einem STRINGS-Dict {"key": {"de": "...", "en": "..."}}. Dieses Modul
# fügt alle Namespaces zu einem flachen TRANSLATIONS-Dict zusammen
# (Schlüssel: "namespace.key") und stellt die Lookup-Funktionen bereit.

from __future__ import annotations

from typing import Mapping

from fastapi import Request

from i18n import (
    backend,
    category,
    common,
    dashboard,
    gallery,
    login,
    map_page,
    memory_detail,
    memory_form,
    milestones,
    settings_ns,
    timeline,
    tree,
)

DEFAULT_LANG = "de"
SUPPORTED_LANGS: tuple[str, ...] = ("de", "en")

_NAMESPACES: dict[str, Mapping[str, Mapping[str, str]]] = {
    "common": common.STRINGS,
    "dashboard": dashboard.STRINGS,
    "login": login.STRINGS,
    "tree": tree.STRINGS,
    "timeline": timeline.STRINGS,
    "gallery": gallery.STRINGS,
    "milestones": milestones.STRINGS,
    "memory_detail": memory_detail.STRINGS,
    "memory_form": memory_form.STRINGS,
    "settings": settings_ns.STRINGS,
    "map": map_page.STRINGS,
    "backend": backend.STRINGS,
    "category": category.STRINGS,
}


def _build_translations() -> dict[str, dict[str, str]]:
    """Alle Namespace-Dicts zu einem flachen key→{de,en}-Dict zusammenführen."""
    merged: dict[str, dict[str, str]] = {}
    for namespace, strings in _NAMESPACES.items():
        for key, value in strings.items():
            merged[f"{namespace}.{key}"] = value
    return merged


TRANSLATIONS: dict[str, dict[str, str]] = _build_translations()


def translate(key: str, lang: str, **kwargs: object) -> str:
    """Übersetzten String für `key` und `lang` liefern.

    Fällt auf Deutsch zurück, falls die Sprache fehlt, und auf den
    Schlüssel selbst, falls der Key komplett unbekannt ist (sichtbarer
    Hinweis auf einen fehlenden Eintrag statt eines Crashes).
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def current_lang(request: Request) -> str:
    """Aktuelle Sprache aus request.state lesen (von LanguageMiddleware gesetzt)."""
    lang = getattr(request.state, "lang", DEFAULT_LANG)
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def t(request: Request, key: str, **kwargs: object) -> str:
    """Jinja-Global: `{{ t(request, 'namespace.key') }}`."""
    return translate(key, current_lang(request), **kwargs)


def category_label(request: Request, category_value: str) -> str:
    """Anzeigename einer Memory-Kategorie in der aktuellen Sprache.

    Der gespeicherte Kategorie-Wert (z.B. "Urlaub") bleibt als DB-/Filter-Key
    unverändert deutsch — nur das angezeigte Label wird übersetzt.
    """
    return translate(f"category.{category_value}", current_lang(request))
