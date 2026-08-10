#!/usr/bin/env python3
"""Memory Tree — Benutzer erstellen/zurücksetzen (für Production-Setup)

Nutzung:
    python3 scripts/create_users.py                 # Standard-Paar (#1)
    python3 scripts/create_users.py --couple-id 3   # anderes Paar

Fragt interaktiv nach Benutzernamen und Passwörtern und erstellt die beiden
Partner-Accounts des Paars bzw. setzt deren Passwörter zurück.

Für neue Freunde ist scripts/create_invite.py der bequemere Weg: dort entsteht
Paar plus Einladungscode, und die Leute vergeben ihr Passwort selbst — du musst
keine Zugangsdaten weitergeben.
"""

import argparse
import getpass
import re
import sys
from pathlib import Path

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import hash_password
from database import SessionLocal
from models import Couple, CoupleSettings, User

DEFAULT_COUPLE_ID = 1

# Gleiche Regel wie in routers/auth.py und routers/settings.py.
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,50}$")


def _get_password(prompt: str) -> str:
    """Passwort abfragen mit Bestätigung und Mindestlänge."""
    while True:
        pw = getpass.getpass(prompt)
        if len(pw) < 8:
            print("Passwort muss mindestens 8 Zeichen lang sein.")
            continue
        pw_confirm = getpass.getpass("Passwort bestätigen: ")
        if pw != pw_confirm:
            print("Passwörter stimmen nicht überein.")
            continue
        return pw


def _ask_username(default: str) -> str:
    """Benutzernamen abfragen; leere Eingabe übernimmt den Vorschlag."""
    while True:
        raw = input(f"Benutzername [{default}]: ").strip()
        username = raw or default
        if _USERNAME_PATTERN.match(username):
            return username
        print("  Ungültig: 3–50 Zeichen, nur A–Z, a–z, 0–9, _ . -")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--couple-id", type=int, default=DEFAULT_COUPLE_ID,
                        help=f"Paar, zu dem die Konten gehören (Default: {DEFAULT_COUPLE_ID})")
    args = parser.parse_args()

    print("=== Memory Tree — Benutzer einrichten ===\n")

    db = SessionLocal()
    try:
        couple = db.query(Couple).filter(Couple.id == args.couple_id).first()
        if couple is None:
            raise SystemExit(
                f"FEHLER: Paar #{args.couple_id} existiert nicht. Erst anlegen:\n"
                "    python3 scripts/create_invite.py --name 'Name des Paars'"
            )
        # Einstellungen sicherstellen, damit die App direkt startklar ist.
        if db.query(CoupleSettings).filter(
            CoupleSettings.couple_id == couple.id
        ).first() is None:
            db.add(CoupleSettings(
                couple_id=couple.id,
                partner_a_name="Partner A",
                partner_b_name="Partner B",
            ))
            db.commit()

        print(f"Paar #{couple.id} ({couple.name})\n")

        for default_username in ("partner_a", "partner_b"):
            username = _ask_username(default_username)

            # Benutzernamen sind global eindeutig. Ein Treffer aus einem
            # anderen Paar darf hier NICHT stillschweigend überschrieben
            # werden — sonst setzt ein Tippfehler das Passwort eines fremden
            # Kontos zurück.
            user = db.query(User).filter(User.username == username).first()
            if user is not None and user.couple_id != couple.id:
                print(
                    f"  ! '{username}' gehört zu Paar #{user.couple_id} — "
                    "übersprungen. Anderen Benutzernamen wählen."
                )
                continue

            if user:
                print(f"Benutzer '{username}' existiert bereits (Name: {user.name}).")
                reset = input("Passwort zurücksetzen? [j/N]: ").strip().lower()
                if reset == "j":
                    pw = _get_password(f"Neues Passwort für '{username}': ")
                    user.hashed_password = hash_password(pw)
                    db.commit()
                    print(f"  ✓ Passwort aktualisiert für '{username}'")
                continue

            name = input(f"Anzeigename für '{username}': ").strip()
            if not name:
                name = username
            pw = _get_password(f"Passwort für '{username}': ")

            user = User(
                couple_id=couple.id,
                name=name,
                username=username,
                hashed_password=hash_password(pw),
            )
            db.add(user)
            db.commit()
            print(f"  ✓ Benutzer '{username}' erstellt")

        print("\n✓ Fertig!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
