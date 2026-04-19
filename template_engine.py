# Zentrale Jinja2-Template-Konfiguration
# Alle Router importieren ihre Templates von hier, damit Filter und Globals
# einheitlich verfügbar sind.

import os
from datetime import datetime

from fastapi.templating import Jinja2Templates

from middleware import get_csrf_token

templates = Jinja2Templates(directory="templates")

# ── Globale Template-Funktionen ──────────────────────────────────────────────

templates.env.globals["now"] = datetime.now
templates.env.globals["get_csrf_token"] = get_csrf_token


# ── Filter ───────────────────────────────────────────────────────────────────

def _upload_url(filepath: str) -> str:
    """Wandelt DB-Dateipfad in URL um. Unterstützt alte (static/uploads/) und neue (data/uploads/) Pfade."""
    if not filepath:
        return ""
    # Altes Format: static/uploads/xxx.jpg → /static/uploads/xxx.jpg
    if filepath.startswith("static/"):
        return f"/{filepath}"
    # Neues Format: data/uploads/xxx.jpg → /uploads/xxx.jpg
    if filepath.startswith("data/uploads/"):
        return filepath.replace("data/uploads/", "/uploads/", 1)
    # Absoluter Pfad (Legacy) → nur Dateiname extrahieren
    basename = os.path.basename(filepath)
    return f"/uploads/{basename}"


templates.env.filters["upload_url"] = _upload_url
