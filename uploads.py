# Zentrale Upload-Verarbeitung: Validierung, Sicherheit, Bildoptimierung

import logging
import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from config import settings
from models import Photo

logger = logging.getLogger(__name__)

# ── Konfiguration ───────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

# Magic Bytes zur Validierung des Dateityps
_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".webp": [b"RIFF"],  # RIFF....WEBP
}

_UPLOAD_DIR = Path(settings.UPLOAD_DIR).resolve()
_THUMBNAIL_DIR = _UPLOAD_DIR / "thumbs"


def _ensure_dirs() -> None:
    """Upload- und Thumbnail-Verzeichnisse erstellen."""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)


def validate_image_magic_bytes(data: bytes, extension: str) -> bool:
    """Prüft die Magic Bytes einer Datei gegen die erwartete Erweiterung."""
    signatures = _MAGIC_BYTES.get(extension.lower(), [])
    if not signatures:
        return False
    for sig in signatures:
        if data[:len(sig)] == sig:
            # Zusätzliche Prüfung für WEBP: RIFF....WEBP
            if extension.lower() == ".webp":
                return len(data) >= 12 and data[8:12] == b"WEBP"
            return True
    return False


def _sanitize_and_save_image(data: bytes, extension: str) -> tuple[str, str]:
    """
    Bild sicher speichern:
    - UUID-basierter Dateiname
    - Neu-Encodierung über Pillow (entfernt EXIF, neutralisiert manipulierte Dateien)
    - EXIF-Orientierung anwenden
    - Größenbegrenzung
    - Thumbnail erzeugen
    Gibt (hauptbild_pfad, thumbnail_pfad) zurück.
    """
    _ensure_dirs()

    unique_name = uuid.uuid4().hex
    # Einheitlich als JPEG oder WEBP speichern
    save_ext = ".webp" if extension.lower() == ".webp" else ".jpg"
    save_format = "WEBP" if save_ext == ".webp" else "JPEG"

    main_filename = f"{unique_name}{save_ext}"
    thumb_filename = f"{unique_name}_thumb{save_ext}"
    main_path = _UPLOAD_DIR / main_filename
    thumb_path = _THUMBNAIL_DIR / thumb_filename

    # Bild mit Pillow öffnen → EXIF-Orientierung anwenden → neu encodieren
    from io import BytesIO
    with Image.open(BytesIO(data)) as img:
        # EXIF-Orientierung automatisch korrigieren
        img = ImageOps.exif_transpose(img) or img

        # In RGB konvertieren (für JPEG nötig, PNG mit Alpha → RGB)
        if img.mode in ("RGBA", "P"):
            if save_format == "JPEG":
                img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Hauptbild: max Dimension begrenzen
        max_dim = settings.MAX_IMAGE_SIZE
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        # Speichern ohne EXIF-Daten (Pillow schreibt standardmäßig keine)
        save_kwargs = {"quality": 85, "optimize": True}
        if save_format == "WEBP":
            save_kwargs["method"] = 4  # Kompressionsqualität
        img.save(str(main_path), format=save_format, **save_kwargs)

        # Thumbnail erzeugen
        thumb_size = settings.THUMBNAIL_SIZE
        img.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
        img.save(str(thumb_path), format=save_format, **save_kwargs)

    return str(main_path), str(thumb_path)


def process_upload(file: UploadFile) -> tuple[str, str] | None:
    """
    Einzelne Datei validieren und verarbeiten.
    Gibt (hauptbild_pfad, thumbnail_pfad) zurück oder None bei Fehler.
    """
    if not file.filename or file.size == 0:
        return None

    # Extension prüfen
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("Upload abgelehnt: ungültige Erweiterung '%s'", ext)
        return None

    # Datei einlesen
    data = file.file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        logger.warning("Upload abgelehnt: zu groß (%d bytes)", len(data))
        return None

    if len(data) == 0:
        return None

    # Magic Bytes prüfen
    if not validate_image_magic_bytes(data, ext):
        logger.warning("Upload abgelehnt: Magic Bytes stimmen nicht mit Erweiterung '%s' überein", ext)
        return None

    # Pillow-Validierung: Kann das Bild überhaupt geöffnet werden?
    from io import BytesIO
    try:
        with Image.open(BytesIO(data)) as test_img:
            test_img.verify()
    except Exception:
        logger.warning("Upload abgelehnt: Pillow konnte Bild nicht verifizieren")
        return None

    # Sicher speichern und verarbeiten
    try:
        return _sanitize_and_save_image(data, ext)
    except Exception:
        logger.exception("Fehler beim Verarbeiten des Uploads")
        return None


def save_uploaded_photos(
    files: list[UploadFile],
    memory_id: int,
    db: Session,
) -> int:
    """Mehrere Fotos validieren, speichern und in die DB einfügen. Gibt Anzahl erfolgreicher Uploads zurück."""
    count = 0
    for file in files:
        result = process_upload(file)
        if result is None:
            continue
        main_path, thumb_path = result

        # Relativen Pfad für DB speichern (relativ zum Projektverzeichnis)
        rel_main = os.path.relpath(main_path, start=".")
        photo = Photo(
            memory_id=memory_id,
            filepath=rel_main,
        )
        db.add(photo)
        count += 1

    if count > 0:
        db.flush()
    return count


def safe_remove(filepath: str) -> None:
    """Datei sicher entfernen — validiert, dass Pfad innerhalb UPLOAD_DIR liegt."""
    if not filepath:
        return
    # Aus dem DB-Pfad den absoluten Pfad rekonstruieren
    abs_path = Path(filepath).resolve()
    # Sicherheitsprüfung: Pfad muss innerhalb UPLOAD_DIR liegen
    try:
        abs_path.relative_to(_UPLOAD_DIR)
    except ValueError:
        logger.warning("Versuch, Datei außerhalb von UPLOAD_DIR zu löschen: %s", filepath)
        return

    if abs_path.is_file():
        abs_path.unlink()

    # Auch Thumbnail löschen falls vorhanden
    thumb_name = abs_path.stem + "_thumb" + abs_path.suffix
    thumb_path = _THUMBNAIL_DIR / thumb_name
    if thumb_path.is_file():
        thumb_path.unlink()
