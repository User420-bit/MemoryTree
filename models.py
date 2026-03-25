# SQLAlchemy-Datenmodelle für Memory Tree

import enum
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship, Mapped

from database import Base


# ---------- Enums ----------

class CategoryEnum(str, enum.Enum):
    """Kategorien für Erinnerungen."""

    urlaub = "Urlaub"
    meilenstein = "Meilenstein"
    feier = "Feier"
    alltag = "Alltag"
    abenteuer = "Abenteuer"
    besonderes = "Besonderes"


# ---------- Modelle ----------

class User(Base):
    """Benutzer-Modell (Partner A / Partner B)."""

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    name: str = Column(String(100), nullable=False)
    username: str = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password: str = Column(String(255), nullable=False)
    avatar_path: Optional[str] = Column(String(500), nullable=True)
    partner_since: Optional[date] = Column(Date, nullable=True)

    memories: Mapped[List["Memory"]] = relationship("Memory", back_populates="creator")


class Memory(Base):
    """Eine gemeinsame Erinnerung."""

    __tablename__ = "memories"

    id: int = Column(Integer, primary_key=True, index=True)
    title: str = Column(String(200), nullable=False)
    date: date = Column(Date, nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    location: Optional[str] = Column(String(200), nullable=True)
    lat: Optional[float] = Column(Float, nullable=True)
    lng: Optional[float] = Column(Float, nullable=True)
    mood: Optional[str] = Column(String(50), nullable=True)
    category: str = Column(String(50), nullable=False, default=CategoryEnum.alltag.value)
    is_favorite: bool = Column(Boolean, default=False, nullable=False)
    created_by: int = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    creator: Mapped["User"] = relationship("User", back_populates="memories")
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="memory")
    places: Mapped[List["Place"]] = relationship("Place", back_populates="memory")


class Photo(Base):
    """Ein Foto, das einer Erinnerung zugeordnet ist."""

    __tablename__ = "photos"

    id: int = Column(Integer, primary_key=True, index=True)
    memory_id: int = Column(
        Integer, ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    filepath: str = Column(String(500), nullable=False)
    caption: Optional[str] = Column(String(500), nullable=True)
    uploaded_at: datetime = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    memory: Mapped["Memory"] = relationship("Memory", back_populates="photos")


class Milestone(Base):
    """Ein Meilenstein (z. B. Jahrestag, besonderes Ereignis)."""

    __tablename__ = "milestones"

    id: int = Column(Integer, primary_key=True, index=True)
    title: str = Column(String(200), nullable=False)
    date: date = Column(Date, nullable=False)
    icon: str = Column(String(50), default="🌟")
    description: Optional[str] = Column(Text, nullable=True)
    is_anniversary: bool = Column(Boolean, default=False)


class Place(Base):
    """Ein Ort, der einer Erinnerung zugeordnet ist."""

    __tablename__ = "places"

    id: int = Column(Integer, primary_key=True, index=True)
    memory_id: int = Column(
        Integer, ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    name: str = Column(String(200), nullable=False)
    country: Optional[str] = Column(String(100), nullable=True)
    lat: float = Column(Float, nullable=False)
    lng: float = Column(Float, nullable=False)

    memory: Mapped["Memory"] = relationship("Memory", back_populates="places")


class CoupleSettings(Base):
    """Gemeinsame Paar-Einstellungen (genau ein Datensatz)."""

    __tablename__ = "couple_settings"

    id: int = Column(Integer, primary_key=True, index=True)
    partner_since: Optional[date] = Column(Date, nullable=True)
    partner_a_name: str = Column(String(100), nullable=False, default="Partner A")
    partner_b_name: str = Column(String(100), nullable=False, default="Partner B")
