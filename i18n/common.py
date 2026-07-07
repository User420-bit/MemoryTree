# Übersetzungen für templates/base.html (Navbar, Footer — auf jeder Seite sichtbar)

STRINGS: dict[str, dict[str, str]] = {
    "nav_dashboard": {"de": "Dashboard", "en": "Dashboard"},
    "nav_tree": {"de": "Baum", "en": "Tree"},
    "nav_timeline": {"de": "Zeitstrahl", "en": "Timeline"},
    "nav_map": {"de": "Karte", "en": "Map"},
    "nav_gallery": {"de": "Galerie", "en": "Gallery"},
    "nav_milestones": {"de": "Meilensteine", "en": "Milestones"},
    "settings_title": {"de": "Einstellungen", "en": "Settings"},
    "logout": {"de": "Abmelden", "en": "Log out"},
    "menu_open_label": {"de": "Menü öffnen", "en": "Open menu"},
    "logged_in_as": {"de": "Angemeldet als", "en": "Logged in as"},
    "footer_tagline": {"de": "Euer gemeinsames Erinnerungsbuch", "en": "Your shared memory book"},

    # Für static/js/pin-animation.js (statische Datei, kann kein Jinja rendern —
    # Strings werden per window.PIN_STR aus tree.html/timeline.html injiziert)
    "pin_to_tree_title": {"de": "An den Baum pinnen", "en": "Pin to the tree"},
    "unpin_from_tree_title": {"de": "Vom Baum lösen", "en": "Unpin from the tree"},
    "max_pinned_alert": {
        "de": "Maximal 8 Erinnerungen können an den Baum gepinnt werden.",
        "en": "A maximum of 8 memories can be pinned to the tree.",
    },

    # Für static/js/hide-memory.js (statische Datei, kann kein Jinja rendern —
    # Strings werden per window.HIDE_STR aus base.html injiziert)
    "toast_close_label": {"de": "Schließen", "en": "Close"},
    "toast_memory_restored": {"de": "Erinnerung wiederhergestellt", "en": "Memory restored"},
    "toast_restore_failed": {"de": "Wiederherstellen fehlgeschlagen", "en": "Restore failed"},
    "toast_memory_hidden": {"de": "Erinnerung verschoben", "en": "Memory hidden"},
    "toast_undo": {"de": "Rückgängig", "en": "Undo"},
    "toast_memory_visible_again": {"de": "Erinnerung wieder sichtbar", "en": "Memory visible again"},
    "toast_hide_failed": {"de": "Fehler beim Verstecken", "en": "Failed to hide"},
    "toast_restore_error": {"de": "Fehler beim Wiederherstellen", "en": "Failed to restore"},
}
