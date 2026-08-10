# Übersetzungen für templates/register.html + Registrierungs-Fehlermeldungen
# (routers/auth.py). Es gibt bewusst keine offene Registrierung — die Seite
# funktioniert nur mit einem gültigen Einladungscode.

STRINGS: dict[str, dict[str, str]] = {
    "title": {"de": "Registrieren", "en": "Sign up"},
    "heading": {"de": "Konto einrichten", "en": "Create your account"},
    "intro": {
        "de": "Du brauchst einen Einladungscode, um mitzumachen.",
        "en": "You need an invitation code to join.",
    },
    "code_label": {"de": "Einladungscode", "en": "Invitation code"},
    "code_placeholder": {"de": "Code eingeben", "en": "Enter code"},
    "name_label": {"de": "Anzeigename", "en": "Display name"},
    "name_placeholder": {"de": "Wie sollen wir dich nennen?", "en": "What should we call you?"},
    "username_label": {"de": "Benutzername", "en": "Username"},
    "username_placeholder": {"de": "Benutzername wählen", "en": "Choose a username"},
    "password_label": {"de": "Passwort", "en": "Password"},
    "password_placeholder": {"de": "Mindestens 8 Zeichen", "en": "At least 8 characters"},
    "password_repeat_label": {"de": "Passwort wiederholen", "en": "Repeat password"},
    "submit_button": {"de": "Konto erstellen", "en": "Create account"},
    "back_to_login": {"de": "Zurück zur Anmeldung", "en": "Back to sign in"},

    # Fehlermeldungen. Der Code-Fehler ist bewusst unspezifisch: ob ein Code
    # nicht existiert, abgelaufen oder aufgebraucht ist, darf ein Fremder
    # nicht unterscheiden können.
    "invalid_code": {
        "de": "Dieser Einladungscode ist ungültig oder nicht mehr nutzbar.",
        "en": "This invitation code is invalid or no longer usable.",
    },
    "invalid_username": {
        "de": "Ungültiger Benutzername (3–50 Zeichen, nur A–Z, 0–9, _ . -).",
        "en": "Invalid username (3–50 characters, only A–Z, 0–9, _ . -).",
    },
    "username_taken": {
        "de": "Dieser Benutzername ist bereits vergeben.",
        "en": "This username is already taken.",
    },
    "invalid_name": {
        "de": "Bitte einen Anzeigenamen angeben (1–100 Zeichen).",
        "en": "Please provide a display name (1–100 characters).",
    },
    "password_mismatch": {
        "de": "Die Passwörter stimmen nicht überein.",
        "en": "The passwords do not match.",
    },
    "password_length": {
        "de": "Passwort muss 8–128 Zeichen lang sein.",
        "en": "Password must be 8–128 characters long.",
    },
}
