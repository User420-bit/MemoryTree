# Datenbankverbindung und Session-Management

import logging
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

# Engine erstellen – SQLite benötigt check_same_thread=False
connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine: Engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# ── SQLite PRAGMAs für Produktionsbetrieb ────────────────────────────────────

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """SQLite-PRAGMAs für Stabilität und Performance setzen."""
    if not settings.DATABASE_URL.startswith("sqlite"):
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
