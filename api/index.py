# Vercel-Entrypoint: exportiert die FastAPI-App als Serverless Function.
# Alle Requests werden per vercel.json-Rewrite hierher geleitet.

import sys
from pathlib import Path

# Repo-Root in den Python-Pfad: die Function wird aus api/ heraus geladen,
# die Anwendungsmodule (main, config, models, ...) liegen eine Ebene höher.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402, F401 — von Vercel als ASGI-App erwartet
