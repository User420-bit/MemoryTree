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

    # X-Forwarded-For nur auswerten, wenn die App hinter einem
    # vertrauenswürdigen Reverse Proxy läuft (Caddy/Traefik). Bei direkter
    # Erreichbarkeit kann der Header sonst gespooft werden und hebelt das
    # Login-Rate-Limit aus (jeder Request = neue "IP").
    TRUST_PROXY_HEADERS: bool = False

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

    # ── Transport-Security ───────────────────────────────────────────────
    # Muss explizit auf true gesetzt werden, wenn die App ausschließlich
    # über HTTPS erreichbar ist (z. B. Cloudflare Tunnel, Tailscale+HTTPS,
    # Reverse-Proxy mit TLS). Bei HTTP im LAN muss dieser Wert false bleiben,
    # sonst verwirft der Browser die Auth-Cookies komplett.
    FORCE_SECURE_COOKIES: bool = False

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def allowed_hosts_list(self) -> list[str]:
        """ALLOWED_HOSTS als Liste für die TrustedHostMiddleware."""
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()] or ["*"]

    @property
    def use_secure_cookies(self) -> bool:
        """Secure-Flag nur aktivieren, wenn explizit per .env gesetzt.

        Production != HTTPS: die App läuft auf dem Pi per HTTP im LAN,
        ist aber trotzdem APP_ENV=production. Daher wird das Secure-Flag
        an einen eigenen Schalter gebunden.
        """
        return self.FORCE_SECURE_COOKIES

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

# SECRET_KEY-Längen-Guard: auch für gesetzte Keys minimum 32 Zeichen
if settings.is_production and len(settings.SECRET_KEY) < 32:
    print(
        f"FATAL: SECRET_KEY ist zu kurz ({len(settings.SECRET_KEY)} Zeichen). "
        "Mindestens 32 Zeichen erforderlich.",
        file=sys.stderr,
    )
    sys.exit(1)

# Hinweis wenn Production ohne Secure-Cookies läuft (bewusst per .env, aber warnen).
if settings.is_production and not settings.FORCE_SECURE_COOKIES:
    print(
        "HINWEIS: APP_ENV=production aber FORCE_SECURE_COOKIES=false. "
        "Cookies laufen unverschlüsselt — nur OK wenn die App ausschließlich "
        "über HTTP im vertrauenswürdigen LAN erreichbar ist.",
        file=sys.stderr,
    )


# ── Gemeinsame Konstanten ───────────────────────────────────────────────────

# Max. gleichzeitig am Baum gepinnte Erinnerungen
MAX_PINNED_MEMORIES: int = 8

# Emoji + Farbe pro Kategorie (wird in mehreren Views verwendet).
# Zentral hier, damit Tree/Timeline/Gallery/Map einheitlich bleiben.
CATEGORY_CONFIG: dict[str, dict[str, str]] = {
    "Urlaub":      {"emoji": "\U0001f3d6\ufe0f", "color": "#0891b2"},
    "Meilenstein": {"emoji": "\U0001f31f",       "color": "#d97706"},
    "Feier":       {"emoji": "\U0001f389",       "color": "#7c3aed"},
    "Alltag":      {"emoji": "\U0001f4f8",       "color": "#16a34a"},
    "Abenteuer":   {"emoji": "\U0001f32f",       "color": "#ea580c"},
    "Besonderes":  {"emoji": "\u2764\ufe0f",     "color": "#e11d48"},
}
