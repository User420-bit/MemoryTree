# Zentrale Upload-Verarbeitung: Validierung, Sicherheit, Bildoptimierung
#
# Zwei Storage-Backends (Weiche über settings.storage_backend):
#   - "disk": lokales Dateisystem unter UPLOAD_DIR (Raspberry Pi / Entwicklung)
#   - "blob": Vercel Blob (serverless, read-only Dateisystem)
# Nach außen liefern alle Funktionen eine "Referenz": entweder ein relativer
# POSIX-Pfad (disk) oder eine absolute https-URL (blob). Beides ist direkt
# DB-tauglich und wird vom Jinja-Filter ``upload_url`` verstanden.

import logging
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import UploadFile
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from config import settings
from models import Photo

logger = logging.getLogger(__name__)

# ── Konfiguration ───────────────────────────────────────────────────────────

_EXT_JPG = ".jpg"
_EXT_JPEG = ".jpeg"
_EXT_PNG = ".png"
_EXT_WEBP = ".webp"

ALLOWED_EXTENSIONS: set[str] = {_EXT_JPG, _EXT_JPEG, _EXT_PNG, _EXT_WEBP}

# Magic Bytes zur Validierung des Dateityps
_MAGIC_BYTES: dict[str, list[bytes]] = {
    _EXT_JPG: [b"\xff\xd8\xff"],
    _EXT_JPEG: [b"\xff\xd8\xff"],
    _EXT_PNG: [b"\x89PNG\r\n\x1a\n"],
    _EXT_WEBP: [b"RIFF"],  # RIFF....WEBP
}

# Decompression-Bomb-Schutz: Pillow warnt ab MAX_IMAGE_PIXELS und bricht
# darunter mit einer ValueError ab, wenn der Wert deutlich überschritten wird.
# 50 Megapixel reichen für realistische Kamera-Fotos, blockiert aber
# pathologische Bilder (z. B. 100k × 100k PNG).
Image.MAX_IMAGE_PIXELS = 50_000_000

_UPLOAD_DIR = Path(settings.UPLOAD_DIR).resolve()
_THUMBNAIL_DIR = _UPLOAD_DIR / "thumbs"

# Blob-Pfadschema — bewusst deterministisch, damit die Thumbnail-Referenz
# jederzeit aus der Hauptbild-Referenz ableitbar ist und keine zusätzliche
# DB-Spalte nötig wird.
_BLOB_PREFIX = "uploads"
_BLOB_THUMB_PREFIX = "uploads/thumbs"


def _use_blob() -> bool:
    """True, wenn Uploads nach Vercel Blob statt auf die lokale Platte gehen."""
    return settings.storage_backend == "blob"


def is_remote_ref(ref: str) -> bool:
    """True, wenn die Referenz eine absolute URL (Vercel Blob) ist."""
    return ref.startswith(("http://", "https://"))


def thumbnail_ref(main_ref: str) -> str:
    """Leitet die Thumbnail-Referenz aus der Hauptbild-Referenz ab.

    Konvention (beide Backends): ``<name>.<ext>`` → ``thumbs/<name>_thumb.<ext>``.
    """
    if not main_ref:
        return ""
    normalized = main_ref.replace("\\", "/")
    base, _, filename = normalized.rpartition("/")
    if not filename:
        return ""
    stem, dot, ext = filename.rpartition(".")
    thumb_name = f"{stem}_thumb.{ext}" if dot else f"{filename}_thumb"
    if not base:
        return f"thumbs/{thumb_name}"
    return f"{base}/thumbs/{thumb_name}"


def _blob_client():
    """Vercel-Blob-Client lazy importieren (nur im Blob-Betrieb installiert)."""
    import vercel_blob  # noqa: PLC0415 — bewusst lazy, spart Import auf dem Pi

    return vercel_blob


def _store_image(pathname: str, data: bytes) -> str:
    """Bild-Bytes ablegen und die DB-taugliche Referenz zurückgeben.

    ``pathname`` ist der Blob-Pfad (z. B. ``uploads/abc.jpg``); im Disk-Modus
    wird daraus der Pfad unterhalb von UPLOAD_DIR. Den Content-Type leitet
    Vercel Blob aus der Endung von ``pathname`` ab — die Endung entspricht
    immer dem tatsächlich encodierten Format (siehe _sanitize_and_save_image).
    """
    if _use_blob():
        result = _blob_client().put(
            pathname,
            data,
            {
                # Kein Zufalls-Suffix: der UUID-Dateiname ist bereits nicht
                # erratbar und die Thumb-Konvention muss vorhersagbar bleiben.
                "addRandomSuffix": "false",
                "cacheControlMaxAge": "31536000",
            },
        )
        return str(result["url"])

    # Disk-Modus: pathname ist relativ zum Upload-Verzeichnis
    relative = PurePosixPath(pathname)
    if relative.parts and relative.parts[0] == _BLOB_PREFIX:
        relative = PurePosixPath(*relative.parts[1:])
    target = _UPLOAD_DIR / Path(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return _to_posix_relpath(target)


def _delete_stored(ref: str) -> None:
    """Hauptbild und zugehöriges Thumbnail entfernen (Blob-Variante)."""
    thumb = thumbnail_ref(ref)
    urls = [u for u in (ref, thumb) if u]
    try:
        _blob_client().delete(urls)
    except Exception:
        # Verwaiste Blobs sind unkritisch — der DB-Eintrag verschwindet ohnehin.
        logger.warning("Blob konnte nicht gelöscht werden: %s", ref, exc_info=True)


def _to_posix_relpath(absolute_path: str | Path) -> str:
    """Pfad relativ zum Projekt-CWD als POSIX-String (mit '/').

    Wichtig f\u00fcr Cross-Platform: ``os.path.relpath`` liefert auf Windows
    Backslashes, die dann via DB in URLs landen und alles zerschie\u00dfen.
    Wir berechnen relativ und erzwingen POSIX-Separatoren.
    """
    abs_p = Path(absolute_path).resolve()
    cwd = Path.cwd().resolve()
    try:
        rel = abs_p.relative_to(cwd)
    except ValueError:
        # Pfad liegt au\u00dferhalb des Projekt-CWD \u2014 nur Dateinamen behalten,
        # Aufrufer ist daf\u00fcr verantwortlich, das einzuordnen.
        return abs_p.name
    return rel.as_posix()


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
            if extension.lower() == _EXT_WEBP:
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
    Gibt (hauptbild_referenz, thumbnail_referenz) zurück — relative Pfade im
    Disk-Modus, absolute Blob-URLs im Vercel-Betrieb.
    """
    if not _use_blob():
        _ensure_dirs()

    unique_name = uuid.uuid4().hex
    # Einheitlich als JPEG oder WEBP speichern
    save_ext = _EXT_WEBP if extension.lower() == _EXT_WEBP else _EXT_JPG
    save_format = "WEBP" if save_ext == _EXT_WEBP else "JPEG"

    main_filename = f"{unique_name}{save_ext}"
    thumb_filename = f"{unique_name}_thumb{save_ext}"
    main_pathname = f"{_BLOB_PREFIX}/{main_filename}"
    thumb_pathname = f"{_BLOB_THUMB_PREFIX}/{thumb_filename}"

    # Bild mit Pillow öffnen → EXIF-Orientierung anwenden → neu encodieren
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
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # Speichern ohne EXIF-Daten (Pillow schreibt standardmäßig keine).
        # In den Speicher encodieren, damit derselbe Code beide Backends bedient.
        save_kwargs = {"quality": 85, "optimize": True}
        if save_format == "WEBP":
            save_kwargs["method"] = 4  # Kompressionsqualität

        main_buffer = BytesIO()
        img.save(main_buffer, format=save_format, **save_kwargs)

        # Thumbnail erzeugen
        thumb_size = settings.THUMBNAIL_SIZE
        img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
        thumb_buffer = BytesIO()
        img.save(thumb_buffer, format=save_format, **save_kwargs)

    main_ref = _store_image(main_pathname, main_buffer.getvalue())
    thumb_ref = _store_image(thumb_pathname, thumb_buffer.getvalue())
    return main_ref, thumb_ref


def process_upload(file: UploadFile) -> tuple[str, str] | None:
    """
    Einzelne Datei validieren und verarbeiten.
    Gibt (hauptbild_referenz, thumbnail_referenz) zurück oder None bei Fehler.
    Die Hauptbild-Referenz ist direkt DB-tauglich (relativer Pfad oder Blob-URL).
    """
    if not file.filename or file.size == 0:
        return None

    # Extension prüfen (Path arbeitet plattformunabhängig)
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.warning("Upload abgelehnt: ungültige Erweiterung '%s'", ext)
        return None

    # Datei einlesen — Size-Check zuerst, um große Uploads früh abzubrechen.
    # file.size ist aus dem Content-Length verfügbar (Starlette liest ihn).
    if file.size is not None and file.size > settings.MAX_UPLOAD_BYTES:
        logger.warning("Upload abgelehnt: zu groß laut Content-Length (%d bytes)", file.size)
        return None

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
    try:
        with Image.open(BytesIO(data)) as test_img:
            test_img.verify()
    except (OSError, Image.UnidentifiedImageError, Image.DecompressionBombError):
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
        main_ref, _thumb_ref = result

        photo = Photo(
            memory_id=memory_id,
            filepath=main_ref,
        )
        db.add(photo)
        count += 1

    if count > 0:
        db.flush()
    return count


def safe_remove(filepath: str) -> None:
    """Datei sicher entfernen — Blob-URL oder lokale Datei innerhalb UPLOAD_DIR.

    Betrachtet den Input als UNVERTRAUENSWÜRDIG: DB-Rows könnten manipuliert
    sein oder aus alten Code-Pfaden stammen. Im Disk-Modus normalisieren wir
    deshalb auf den reinen Dateinamen und ignorieren alle Pfad-Anteile.
    """
    if not filepath:
        return

    # Blob-Referenz: Löschen geht über die API, nicht über das Dateisystem.
    # Auch im Disk-Modus möglich (migrierte Altbestände), daher vor der Weiche.
    if is_remote_ref(filepath):
        _delete_stored(filepath)
        return

    # 1) Nur den Dateinamen verwenden — Pfad-Traversal (..), absolute Pfade,
    #    Windows-Drive-Letter und Backslashes werden dadurch eliminiert.
    filename = PurePosixPath(filepath.replace("\\", "/")).name
    if not filename or filename in (".", ".."):
        logger.warning("safe_remove: Ungültiger Dateiname %r — ignoriert", filepath)
        return

    # 2) Zielpfad aufbauen und verifizieren, dass er tatsächlich innerhalb
    #    _UPLOAD_DIR liegt (z. B. gegen Symlink-Tricks).
    abs_path = (_UPLOAD_DIR / filename).resolve()
    try:
        abs_path.relative_to(_UPLOAD_DIR)
    except ValueError:
        logger.warning("safe_remove: Pfad außerhalb UPLOAD_DIR %s", abs_path)
        return

    if abs_path.is_file():
        abs_path.unlink()

    # Auch Thumbnail löschen falls vorhanden
    thumb_name = abs_path.stem + "_thumb" + abs_path.suffix
    thumb_path = (_THUMBNAIL_DIR / thumb_name).resolve()
    try:
        thumb_path.relative_to(_THUMBNAIL_DIR)
    except ValueError:
        return
    if thumb_path.is_file():
        thumb_path.unlink()
