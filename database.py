# Datenbankverbindung und Session-Management

import logging
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from config import settings

logger = logging.getLogger(__name__)

def _normalize_database_url(url: str) -> str:
    """Postgres-URLs auf den psycopg-3-Treiber festnageln.

    Neon/Vercel liefern ``postgres://`` bzw. ``postgresql://``. SQLAlchemy
    würde daraus psycopg2 ableiten, das hier bewusst nicht installiert ist —
    ohne diese Normalisierung schlägt der Verbindungsaufbau mit einem
    "ModuleNotFoundError: psycopg2" fehl.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL: str = _normalize_database_url(settings.DATABASE_URL)

IS_SQLITE: bool = DATABASE_URL.startswith("sqlite")
IS_POSTGRES: bool = DATABASE_URL.startswith("postgresql")

# Engine-Konfiguration je nach Backend:
# - SQLite (Pi/Dev): check_same_thread=False, langlebiger Pool.
# - Postgres/serverless (Vercel): NullPool. Jede Function-Instanz ist kurzlebig
#   und würde sonst Verbindungen halten, die Neon/Postgres-Limits sprengen —
#   das eigentliche Pooling übernimmt Neons PgBouncer im "-pooler"-Host.
_connect_args: dict = {}
_engine_kwargs: dict = {"pool_pre_ping": True}

if IS_SQLITE:
    _connect_args = {"check_same_thread": False}
elif IS_POSTGRES and settings.is_serverless:
    _engine_kwargs["poolclass"] = NullPool
    # Kein pool_pre_ping: NullPool baut ohnehin für jeden Checkout eine frische
    # Verbindung auf, die gar nicht abgestanden sein kann. Der Ping wäre ein
    # zusätzliches "SELECT 1" pro Request — bei Neon über Netz ein voller
    # Round-Trip, den wir uns hier sparen.
    _engine_kwargs["pool_pre_ping"] = False

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)


# ── SQLite PRAGMAs für Produktionsbetrieb ────────────────────────────────────

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """SQLite-PRAGMAs für Stabilität und Performance setzen."""
    if not IS_SQLITE:
        return
    cursor = dbapi_connection.cursor()
    # WAL-Modus: bessere Lese-Performance, sicherer bei Crashes
    cursor.execute("PRAGMA journal_mode=WAL")
    # Foreign Keys aktivieren (SQLite Default: aus)
    cursor.execute("PRAGMA foreign_keys=ON")
    # NORMAL ist sicher genug für WAL-Modus, deutlich schneller als FULL
    cursor.execute("PRAGMA synchronous=NORMAL")
    # 5 Sekunden warten bei gesperrter DB (2 User + 1 Worker = selten)
    cursor.execute("PRAGMA busy_timeout=5000")
    # Temp-Daten im RAM statt auf Disk
    cursor.execute("PRAGMA temp_store=MEMORY")
    # Cache-Größe: 2000 Pages ≈ 8 MB, sinnvoll für Pi mit 512 MB
    cursor.execute("PRAGMA cache_size=-8000")
    cursor.close()
    logger.debug("SQLite PRAGMAs gesetzt")


SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI-Abhängigkeit: liefert eine Datenbank-Session und schließt sie danach."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
