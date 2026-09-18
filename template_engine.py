# Zentrale Jinja2-Template-Konfiguration
# Alle Router importieren ihre Templates von hier, damit Filter und Globals
# einheitlich verfügbar sind.

import hashlib
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi.templating import Jinja2Templates

from config import settings
from i18n import category_label, t
from middleware import get_csrf_token

# Am Projektverzeichnis ankern statt am CWD — auf Vercel ist das
# Arbeitsverzeichnis der Function nicht garantiert das Repo-Root.
_BASE_DIR = Path(__file__).resolve().parent
_TEMPLATE_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"

templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


# ── Statische Assets mit Cache-Buster ────────────────────────────────────────

_static_version_cache: dict[str, str] = {}


def static_url(path: str) -> str:
    """URL für eine Datei unter ``static/`` inkl. Content-Hash als Query.

    Die Assets werden mit ``Cache-Control: immutable`` und einem Jahr Lebens-
    dauer ausgeliefert — auf Pi/Docker über ``SecurityHeadersMiddleware``, auf
    Vercel über den ``headers``-Block in ``vercel.json``. Damit ein Deploy
    trotzdem sofort durchschlägt, hängt hier ein Hash des Dateiinhalts an der
    URL: ändert sich die Datei, ändert sich die URL und der alte Cache-Eintrag
    wird nie wieder angefragt.

    Bewusst der Inhalt und nicht die mtime — im Vercel-Bundle sind die
    Zeitstempel nicht verlässlich. Das Ergebnis wird pro Prozess gecacht, die
    Dateien werden also höchstens einmal pro Cold Start gelesen (die größte
    ist derzeit das gebaute app.css mit ~36 KB).
    """
    rel = path.lstrip("/")
    if rel.startswith("static/"):
        rel = rel[len("static/"):]

    version = _static_version_cache.get(rel)
    if version is None:
        try:
            data = (_STATIC_DIR / rel).read_bytes()
            version = hashlib.md5(data).hexdigest()[:8]  # noqa: S324 — nur Cache-Buster
        except OSError:
            # Fehlende Datei soll die Seite nicht sprengen; ohne Query
            # verhält sich die URL wie vorher.
            version = ""
        _static_version_cache[rel] = version

    return f"/static/{rel}?v={version}" if version else f"/static/{rel}"


# ── Globale Template-Funktionen ──────────────────────────────────────────────

templates.env.globals["now"] = datetime.now
templates.env.globals["get_csrf_token"] = get_csrf_token
templates.env.globals["t"] = t
templates.env.globals["category_label"] = category_label
templates.env.globals["static_url"] = static_url
# Steuert den "Als Gast ansehen"-Button auf der Login-Seite. Global statt
# Kontextvariable, weil login.html von mehreren Stellen gerendert wird.
templates.env.globals["demo_enabled"] = lambda: settings.DEMO_ENABLED


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
