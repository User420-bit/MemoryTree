# Übersetzungen für Backend-Fehlermeldungen (routers/settings.py),
# die per ?account_error=<key> an settings.html weitergereicht werden.

STRINGS: dict[str, dict[str, str]] = {
    "invalid_username": {
        "de": "Ungültiger Benutzername (3–50 Zeichen, nur A–Z, 0–9, _ . -).",
        "en": "Invalid username (3–50 characters, only A–Z, 0–9, _ . -).",
    },
    "wrong_password": {
        "de": "Aktuelles Passwort ist falsch.",
        "en": "Current password is incorrect.",
    },
    "username_unchanged": {
        "de": "Neuer Benutzername entspricht dem aktuellen.",
        "en": "New username is the same as the current one.",
    },
    "username_taken": {
        "de": "Dieser Benutzername ist bereits vergeben.",
        "en": "This username is already taken.",
    },
    "password_mismatch": {
        "de": "Die neuen Passwörter stimmen nicht überein.",
        "en": "The new passwords do not match.",
    },
    "password_length": {
        "de": "Neues Passwort muss 8–128 Zeichen lang sein.",
        "en": "New password must be 8–128 characters long.",
    },
    "password_unchanged": {
        "de": "Das neue Passwort muss sich vom alten unterscheiden.",
        "en": "The new password must differ from the old one.",
    },
    "invalid_date": {
        "de": "Ungültiges Datum.",
        "en": "Invalid date.",
    },
}
