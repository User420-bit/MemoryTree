# Datenbankverbindung und Session-Management

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings

# Engine erstellen – SQLite benötigt check_same_thread=False
connect_args: dict = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine: Engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

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
