# Anwendungskonfiguration – lädt Einstellungen aus der .env-Datei

import secrets
import sys
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Zentrale Konfigurationsklasse für Memory Tree."""

    # ── Umgebung ─────────────────────────────────────────────────────────
    APP_ENV: str = "production"
    DEBUG: bool = False

    # ── Sicherheit ───────────────────────────────────────────────────────
    SECRET_KEY: str = ""
    ALLOWED_HOSTS: str = "*"

    # ── JWT-Konfiguration ────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Datenbank ────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./data/memory_tree.db"

    # ── Uploads ──────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "data/uploads"
    MAX_IMAGE_SIZE: int = 1920
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MB
    THUMBNAIL_SIZE: int = 400

    # ── Logging ──────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── Rate Limiting (Login) ────────────────────────────────────────────
    LOGIN_RATE_LIMIT_MAX: int = 5       # max Versuche
    LOGIN_RATE_LIMIT_WINDOW: int = 300  # Fenster in Sekunden (5 Min)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()

# SECRET_KEY-Validierung: in Production muss ein echter Key gesetzt sein
if not settings.SECRET_KEY or settings.SECRET_KEY == "dein-geheimer-schluessel-hier-aendern":
    if settings.is_production:
        print(
            "FATAL: SECRET_KEY ist nicht gesetzt oder unsicher. "
            "Bitte einen sicheren Wert in .env setzen: "
            f"SECRET_KEY={secrets.token_urlsafe(64)}",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        # Dev-Modus: temporären Key generieren und warnen
        settings.SECRET_KEY = secrets.token_urlsafe(64)
        print("WARNUNG: Kein SECRET_KEY gesetzt – temporärer Key wird verwendet (nur für Entwicklung).", file=sys.stderr)
