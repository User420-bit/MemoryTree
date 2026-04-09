#!/usr/bin/env python3
"""Memory Tree — Benutzer erstellen/zurücksetzen (für Production-Setup)

Nutzung:
    python3 scripts/create_users.py

Fragt interaktiv nach Benutzernamen und Passwörtern.
Erstellt die beiden Partner-Accounts oder setzt Passwörter zurück.
"""

import getpass
import sys
from pathlib import Path

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth import hash_password
from database import SessionLocal
from models import User


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


def main() -> None:
    print("=== Memory Tree — Benutzer einrichten ===\n")

    db = SessionLocal()
    try:
        for username in ("partner_a", "partner_b"):
            user = db.query(User).filter(User.username == username).first()
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
