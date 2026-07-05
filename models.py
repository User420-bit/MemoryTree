# SQLAlchemy-Datenmodelle für Memory Tree

import enum
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    partner_since: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    memories: Mapped[List["Memory"]] = relationship("Memory", back_populates="creator")


class Memory(Base):
    """Eine gemeinsame Erinnerung."""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mood: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default=CategoryEnum.alltag.value)
    _is_favorite: Mapped[bool] = mapped_column(
        "is_favorite", Boolean, default=False, nullable=False
    )
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tree_pos_top: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    tree_pos_left: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    creator: Mapped["User"] = relationship("User", back_populates="memories")
    photos: Mapped[List["Photo"]] = relationship("Photo", back_populates="memory", cascade="all, delete-orphan")
    places: Mapped[List["Place"]] = relationship("Place", back_populates="memory", cascade="all, delete-orphan")

    @hybrid_property
    def is_favorite(self) -> bool:
        return self._is_favorite

    @is_favorite.setter
    def is_favorite(self, value: bool) -> None:
        """Setzt is_favorite und bereinigt tree_pos bei Entfavorisierung automatisch.

        Invariante: eine Erinnerung ohne Favorit-Status darf keine
        Tree-Position mehr besitzen — sonst hängen verwaiste Positions-
        werte in der DB, die beim erneuten Favorisieren falsch wieder
        auftauchen würden. Diese Property fasst die Invariante an einer
        Stelle zusammen, statt sie an jeder Schreibstelle zu wiederholen.
        """
        if self._is_favorite and not value:
            self.tree_pos_top = None
            self.tree_pos_left = None
        self._is_favorite = value


class Photo(Base):
    """Ein Foto, das einer Erinnerung zugeordnet ist."""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    memory_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    filepath: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    memory: Mapped["Memory"] = relationship("Memory", back_populates="photos")


class Milestone(Base):
    """Ein Meilenstein (z. B. Jahrestag, besonderes Ereignis)."""

    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), default="🌟")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_anniversary: Mapped[bool] = mapped_column(Boolean, default=False)


class Place(Base):
    """Ein Ort, der einer Erinnerung zugeordnet ist."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    memory_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)

    memory: Mapped["Memory"] = relationship("Memory", back_populates="places")


class CoupleSettings(Base):
    """Gemeinsame Paar-Einstellungen (genau ein Datensatz)."""

    __tablename__ = "couple_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    partner_since: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    partner_a_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Partner A")
    partner_b_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Partner B")
