# Zentrale Jinja2-Template-Konfiguration
# Alle Router importieren ihre Templates von hier, damit Filter und Globals
# einheitlich verfügbar sind.

from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi.templating import Jinja2Templates

from i18n import category_label, t
from middleware import get_csrf_token

# Am Projektverzeichnis ankern statt am CWD — auf Vercel ist das
# Arbeitsverzeichnis der Function nicht garantiert das Repo-Root.
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

# ── Globale Template-Funktionen ──────────────────────────────────────────────

templates.env.globals["now"] = datetime.now
templates.env.globals["get_csrf_token"] = get_csrf_token
templates.env.globals["t"] = t
templates.env.globals["category_label"] = category_label


# ── Sicherer interner Redirect ───────────────────────────────────────────────

# Whitelist: nur diese Pfad-Präfixe sind als `from`/return_to-Ziel erlaubt.
# Verhindert Open-Redirect-Angriffe via manipulierte ?from=https://evil.tld
_ALLOWED_RETURN_PREFIXES: tuple[str, ...] = (
    "/", "/timeline", "/gallery", "/map", "/tree",
    "/milestones", "/settings", "/memories",
)


def safe_internal_url(url: str | None, default: str = "/") -> str:
    """Validiert eine return_to/from-URL und gibt ein sicheres internes Ziel zurück.

    Akzeptiert nur Pfade, die mit einem einzelnen ``/`` beginnen und nicht mit
    ``//`` (protokollrelativ). Pfad-Präfix muss in der Whitelist enthalten
    sein (oder exakt ``/`` lauten). Bei jeder Verletzung wird ``default``
    zurückgegeben. Optionaler Query-/Fragment-Anteil bleibt erhalten.
    """
    if not url or not isinstance(url, str):
        return default
    # Schutz: keine externen URLs, keine protokollrelativen Pfade, kein Schema
    if not url.startswith("/") or url.startswith("//"):
        return default
    if "://" in url or url.lower().startswith(("javascript:", "data:", "vbscript:")):
        return default
    # Pfad-Anteil extrahieren und gegen Whitelist prüfen
    path = url.split("?", 1)[0].split("#", 1)[0]
    if path == "/":
        return url
    if not any(path == p or path.startswith(p + "/") or path.startswith(p + "?")
               for p in _ALLOWED_RETURN_PREFIXES):
        return default
    return url


templates.env.globals["safe_internal_url"] = safe_internal_url


# ── Filter ───────────────────────────────────────────────────────────────────

def _upload_url(filepath: str) -> str:
    """Wandelt DB-Dateipfad in URL um.

    Unterstützt Vercel-Blob-URLs (absolut, unverändert durchgereicht) sowie die
    lokalen Formate static/uploads/ (alt) und data/uploads/ (neu).
    """
    if not filepath:
        return ""
    # Vercel Blob: bereits eine vollständige URL
    if filepath.startswith(("http://", "https://")):
        return filepath
    # Altes Format: static/uploads/xxx.jpg → /static/uploads/xxx.jpg
    if filepath.startswith("static/"):
        return f"/{filepath}"
    # Neues Format: data/uploads/xxx.jpg → /uploads/xxx.jpg
    if filepath.startswith("data/uploads/"):
        return filepath.replace("data/uploads/", "/uploads/", 1)
    # Absoluter Pfad (Legacy) oder Backslash-Pfad (Windows-Altdaten):
    # nur Dateiname extrahieren. PurePosixPath nach Slash-Normalisierung.
    basename = PurePosixPath(filepath.replace("\\", "/")).name
    return f"/uploads/{basename}"


templates.env.filters["upload_url"] = _upload_url
