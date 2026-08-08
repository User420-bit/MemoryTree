#!/usr/bin/env python3
"""Memory Tree — Einmalige Migration von SQLite+Disk nach Postgres+Vercel Blob

Wird LOKAL ausgeführt, nicht auf Vercel. Liest die bestehende SQLite-Datenbank
und die Dateien unter UPLOAD_DIR, lädt alle Bilder in den Vercel-Blob-Store und
schreibt die Zeilen in die Ziel-Postgres-Datenbank — mit auf Blob-URLs
umgeschriebenen ``photos.filepath`` und ``users.avatar_path``.

Voraussetzungen:
    1. Ziel-Schema existiert bereits:   alembic upgrade head
    2. Umgebungsvariablen gesetzt:
         DATABASE_URL=postgresql://...        (Neon, Ziel)
         BLOB_READ_WRITE_TOKEN=vercel_blob_rw_...

Nutzung:
    python3 scripts/migrate_to_vercel.py [--source sqlite:///./data/memory_tree.db]
                                         [--dry-run] [--force]

``--dry-run`` lädt nichts hoch und schreibt nichts, zeigt aber den kompletten
Plan. ``--force`` erlaubt das Schreiben in nicht-leere Zieltabellen (Vorsicht:
kann zu doppelten Datensätzen führen).
"""

import argparse
import sys
from pathlib import Path

# Projektverzeichnis zum Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, insert, select, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from config import settings  # noqa: E402
from database import DATABASE_URL, IS_POSTGRES  # noqa: E402
from models import (  # noqa: E402, F401 — Import registriert alle Tabellen
    CoupleSettings,
    Memory,
    Milestone,
    Photo,
    Place,
    User,
)

# Reihenfolge respektiert die Fremdschlüssel (users vor memories vor photos).
TABLE_ORDER = [
    User.__table__,
    CoupleSettings.__table__,
    Milestone.__table__,
    Memory.__table__,
    Photo.__table__,
    Place.__table__,
]

BLOB_PREFIX = "uploads"
BLOB_THUMB_PREFIX = "uploads/thumbs"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Dateien ──────────────────────────────────────────────────────────────────

def _local_paths(ref: str) -> tuple[Path, Path]:
    """Lokale Pfade (Hauptbild, Thumbnail) zu einer DB-Referenz auflösen."""
    filename = Path(ref.replace("\\", "/")).name
    upload_dir = (PROJECT_ROOT / settings.UPLOAD_DIR).resolve()
    main = upload_dir / filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    thumb = upload_dir / "thumbs" / f"{stem}_thumb{suffix}"
    return main, thumb


# Content-Type leitet Vercel Blob aus der Datei-Endung ab.
# allowOverwrite, damit ein abgebrochener Lauf wiederholbar bleibt.
BLOB_OPTIONS = {
    "addRandomSuffix": "false",
    "allowOverwrite": "true",
    "cacheControlMaxAge": "31536000",
}


def upload_reference(ref: str, dry_run: bool) -> str | None:
    """Bild + Thumbnail hochladen. Gibt die neue Blob-URL zurück (oder None).

    Bereits migrierte Referenzen (absolute URLs) werden unverändert
    durchgereicht, damit ein zweiter Lauf nichts kaputt macht.
    """
    if not ref:
        return None
    if ref.startswith(("http://", "https://")):
        return ref

    main_path, thumb_path = _local_paths(ref)
    if not main_path.is_file():
        print(f"    ! Datei fehlt, Referenz wird übersprungen: {main_path}")
        return None

    if dry_run:
        extra = "" if thumb_path.is_file() else " (ohne Thumbnail)"
        print(f"    → würde hochladen: {main_path.name}{extra}")
        return f"https://example.invalid/{BLOB_PREFIX}/{main_path.name}"

    import vercel_blob

    result = vercel_blob.put(
        f"{BLOB_PREFIX}/{main_path.name}",
        main_path.read_bytes(),
        BLOB_OPTIONS,
    )
    main_url = str(result["url"])

    if thumb_path.is_file():
        vercel_blob.put(
            f"{BLOB_THUMB_PREFIX}/{thumb_path.name}",
            thumb_path.read_bytes(),
            BLOB_OPTIONS,
        )
    else:
        print(f"    ! Kein Thumbnail für {main_path.name}")

    print(f"    ✓ {main_path.name} → Blob")
    return main_url


# ── Datenbank ────────────────────────────────────────────────────────────────

def check_target_empty(target: Engine, force: bool) -> None:
    """Abbrechen, wenn im Ziel bereits Daten liegen (außer bei --force)."""
    with target.connect() as conn:
        for table in TABLE_ORDER:
            count = conn.execute(
                select(func.count()).select_from(table)
            ).scalar_one()
            if count:
                if force:
                    print(f"! Zieltabelle '{table.name}' enthält {count} Zeilen (--force)")
                else:
                    raise SystemExit(
                        f"FEHLER: Zieltabelle '{table.name}' enthält bereits "
                        f"{count} Zeilen. Migration abgebrochen. "
                        "Mit --force überschreiben/ergänzen."
                    )


def reset_sequences(target: Engine) -> None:
    """Postgres-Sequenzen auf max(id) setzen.

    Ohne diesen Schritt vergibt Postgres bei der nächsten Einfügung die ID 1
    und läuft sofort in einen Primärschlüssel-Konflikt, weil wir die IDs aus
    SQLite unverändert übernommen haben.
    """
    with target.begin() as conn:
        for table in TABLE_ORDER:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table.name}), 1), true)"
            ))
    print("✓ Sequenzen auf max(id) gesetzt")


def migrate(source_url: str, dry_run: bool, force: bool) -> None:
    source: Engine = create_engine(source_url)
    target: Engine = create_engine(DATABASE_URL)

    print(f"Quelle: {source_url}")
    print(f"Ziel:   {DATABASE_URL.split('@')[-1]}")  # ohne Zugangsdaten loggen
    print(f"Blob:   {'DRY-RUN' if dry_run else settings.storage_backend}\n")

    if not dry_run:
        check_target_empty(target, force)

    # 1) Alle Zeilen einlesen
    rows_by_table: dict[str, list[dict]] = {}
    with source.connect() as conn:
        for table in TABLE_ORDER:
            result = conn.execute(select(table))
            rows_by_table[table.name] = [dict(r) for r in result.mappings()]
            print(f"· {table.name}: {len(rows_by_table[table.name])} Zeilen gelesen")

    # 2) Bilder hochladen und Referenzen umschreiben
    print("\nBilder werden übertragen …")
    for row in rows_by_table[User.__table__.name]:
        if row.get("avatar_path"):
            print(f"  Avatar (user {row['id']}):")
            row["avatar_path"] = upload_reference(row["avatar_path"], dry_run)

    for row in rows_by_table[Photo.__table__.name]:
        print(f"  Foto {row['id']}:")
        new_ref = upload_reference(row["filepath"], dry_run)
        if new_ref is None:
            # Ohne Datei ist der Datensatz wertlos — Referenz behalten, damit
            # der Verlust in der DB sichtbar bleibt statt still zu verschwinden.
            print(f"    ! Foto {row['id']} behält alten Pfad {row['filepath']!r}")
        else:
            row["filepath"] = new_ref

    if dry_run:
        print("\nDRY-RUN: nichts geschrieben.")
        return

    # 3) Zeilen ins Ziel schreiben
    print("\nDatensätze werden geschrieben …")
    with target.begin() as conn:
        for table in TABLE_ORDER:
            rows = rows_by_table[table.name]
            if not rows:
                continue
            conn.execute(insert(table), rows)
            print(f"✓ {table.name}: {len(rows)} Zeilen")

    if IS_POSTGRES:
        reset_sequences(target)

    print("\nMigration abgeschlossen.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="sqlite:///./data/memory_tree.db",
        help="Quell-Datenbank-URL (Default: lokale SQLite-Datei)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen, nichts schreiben oder hochladen")
    parser.add_argument("--force", action="store_true",
                        help="Auch in nicht-leere Zieltabellen schreiben")
    args = parser.parse_args()

    if not IS_POSTGRES:
        raise SystemExit(
            "FEHLER: DATABASE_URL zeigt nicht auf Postgres. Ziel-URL setzen, z. B.:\n"
            "  export DATABASE_URL='postgresql://…neon.tech/neondb?sslmode=require'"
        )
    if not args.dry_run and settings.storage_backend != "blob":
        raise SystemExit(
            "FEHLER: BLOB_READ_WRITE_TOKEN ist nicht gesetzt — "
            "ohne Token können keine Bilder hochgeladen werden."
        )

    migrate(args.source, args.dry_run, args.force)


if __name__ == "__main__":
    main()
