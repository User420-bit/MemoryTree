#!/usr/bin/env python3
"""Memory Tree — Einladungscode für ein neues Paar erzeugen

Es gibt bewusst keine offene Registrierung. Neue Nutzer kommen ausschließlich
über einen Code herein, den du hier erzeugst und ihnen weitergibst.

Nutzung:
    python3 scripts/create_invite.py                      # neues Paar + Code
    python3 scripts/create_invite.py --name "Anna & Ben"  # mit Paar-Namen
    python3 scripts/create_invite.py --couple-id 3        # Code für vorhandenes Paar
    python3 scripts/create_invite.py --days 14            # kürzere Gültigkeit
    python3 scripts/create_invite.py --max-uses 1         # nur ein Konto
    python3 scripts/create_invite.py --list               # offene Codes anzeigen

Standard ist ein Code mit zwei Einlösungen (die zwei Partner) und 30 Tagen
Gültigkeit. Der erste Einlöser wird Partner A, der zweite Partner B.
"""

import argparse
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from database import SessionLocal  # noqa: E402
from models import Couple, CoupleSettings, Invite, User  # noqa: E402

DEFAULT_MAX_USES = 2
DEFAULT_VALID_DAYS = 30


def _generate_code() -> str:
    """Nicht erratbarer Einladungscode (~256 Bit Entropie)."""
    return secrets.token_urlsafe(32)


def list_invites(db: Session) -> None:
    """Alle noch einlösbaren Codes anzeigen."""
    now = datetime.now(timezone.utc)
    invites = db.query(Invite).order_by(Invite.created_at.desc()).all()

    open_invites = []
    for inv in invites:
        if inv.used_count >= inv.max_uses:
            continue
        expires_at = inv.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                continue
        open_invites.append((inv, expires_at))

    if not open_invites:
        print("Keine offenen Einladungscodes.")
        return

    print(f"{len(open_invites)} offene(r) Einladungscode(s):\n")
    for inv, expires_at in open_invites:
        couple = db.query(Couple).filter(Couple.id == inv.couple_id).first()
        couple_name = couple.name if couple else "?"
        gueltig = expires_at.strftime("%d.%m.%Y") if expires_at else "unbegrenzt"
        print(f"  Paar #{inv.couple_id} ({couple_name})")
        print(f"    Code:      {inv.code}")
        print(f"    Einlösung: {inv.used_count}/{inv.max_uses}")
        print(f"    Gültig bis: {gueltig}\n")


def create_invite(
    db: Session,
    couple_id: int | None,
    name: str,
    max_uses: int,
    valid_days: int,
) -> None:
    """Code erzeugen — für ein neues oder ein vorhandenes Paar."""
    if couple_id is None:
        couple = Couple(name=name)
        db.add(couple)
        db.flush()
        # Einstellungen direkt mitanlegen, damit das Paar auch ohne
        # abgeschlossene Registrierung eine gültige Konfiguration hat.
        db.add(CoupleSettings(
            couple_id=couple.id,
            partner_a_name="Partner A",
            partner_b_name="Partner B",
        ))
        print(f"✓ Neues Paar #{couple.id} angelegt ({couple.name})")
    else:
        couple = db.query(Couple).filter(Couple.id == couple_id).first()
        if couple is None:
            raise SystemExit(f"FEHLER: Paar #{couple_id} existiert nicht.")
        belegt = db.query(User).filter(User.couple_id == couple.id).count()
        print(f"· Vorhandenes Paar #{couple.id} ({couple.name}), {belegt} Konto/Konten")

    expires_at = datetime.now(timezone.utc) + timedelta(days=valid_days) if valid_days else None

    invite = Invite(
        code=_generate_code(),
        couple_id=couple.id,
        max_uses=max_uses,
        used_count=0,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()

    gueltig = expires_at.strftime("%d.%m.%Y") if expires_at else "unbegrenzt"
    print("\n=== Einladung ===")
    print(f"Paar:       #{couple.id} ({couple.name})")
    print(f"Code:       {invite.code}")
    print(f"Einlösbar:  {max_uses}×")
    print(f"Gültig bis: {gueltig}")
    print(f"\nLink:  https://DEINE-DOMAIN/auth/register?code={invite.code}")
    print("\n(Domain ersetzen. Den Code über einen vertrauenswürdigen Kanal teilen —")
    print(" wer ihn hat, kann ein Konto in diesem Paar anlegen.)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--couple-id", type=int, default=None,
                        help="Code für ein vorhandenes Paar statt für ein neues")
    parser.add_argument("--name", default="Paar",
                        help="Name des neuen Paars (nur zur Orientierung im Admin-Skript)")
    parser.add_argument("--max-uses", type=int, default=DEFAULT_MAX_USES,
                        help=f"Wie oft der Code einlösbar ist (Default: {DEFAULT_MAX_USES})")
    parser.add_argument("--days", type=int, default=DEFAULT_VALID_DAYS,
                        help=f"Gültigkeit in Tagen, 0 = unbegrenzt (Default: {DEFAULT_VALID_DAYS})")
    parser.add_argument("--list", action="store_true",
                        help="Nur die offenen Codes anzeigen")
    args = parser.parse_args()

    if args.max_uses < 1:
        raise SystemExit("FEHLER: --max-uses muss mindestens 1 sein.")
    if args.days < 0:
        raise SystemExit("FEHLER: --days darf nicht negativ sein.")

    db: Session = SessionLocal()
    try:
        if args.list:
            list_invites(db)
        else:
            create_invite(db, args.couple_id, args.name, args.max_uses, args.days)
    finally:
        db.close()


if __name__ == "__main__":
    main()
