# Pydantic-Schemas für Request/Response-Validierung

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── User ─────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    username: str = Field(..., min_length=1, max_length=50)


class UserRead(UserBase):
    id: int
    avatar_path: str | None = None
    partner_since: datetime.date | None = None

    model_config = ConfigDict(from_attributes=True)


# ── Photo ────────────────────────────────────────────────────────────────────

class PhotoRead(BaseModel):
    id: int
    memory_id: int
    filepath: str
    caption: str | None = None
    uploaded_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


# ── Place ────────────────────────────────────────────────────────────────────

class PlaceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    country: str | None = Field(None, max_length=100)
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)


class PlaceRead(PlaceBase):
    id: int
    memory_id: int

    model_config = ConfigDict(from_attributes=True)


# ── Memory ───────────────────────────────────────────────────────────────────

_VALID_CATEGORIES = {"Urlaub", "Meilenstein", "Feier", "Alltag", "Abenteuer", "Besonderes"}


class MemoryBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    date: datetime.date
    description: str | None = Field(None, max_length=10000)
    location: str | None = Field(None, max_length=200)
    lat: float | None = Field(None, ge=-90.0, le=90.0)
    lng: float | None = Field(None, ge=-180.0, le=180.0)
    mood: str | None = Field(None, max_length=50)
    category: str = Field("Alltag", max_length=50)
    is_favorite: bool = False

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"Ungültige Kategorie: {v}")
        return v


class MemoryCreate(MemoryBase):
    pass


class MemoryUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    date: datetime.date | None = None
    description: str | None = Field(None, max_length=10000)
    location: str | None = Field(None, max_length=200)
    lat: float | None = Field(None, ge=-90.0, le=90.0)
    lng: float | None = Field(None, ge=-180.0, le=180.0)
    mood: str | None = Field(None, max_length=50)
    category: str | None = Field(None, max_length=50)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_CATEGORIES:
            raise ValueError(f"Ungültige Kategorie: {v}")
        return v


class MemoryRead(MemoryBase):
    id: int
    created_by: int
    created_at: datetime.datetime
    photos: list[PhotoRead] = []
    places: list[PlaceRead] = []

    model_config = ConfigDict(from_attributes=True)


# ── Milestone ────────────────────────────────────────────────────────────────

class MilestoneBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    date: datetime.date
    icon: str = Field("🌟", max_length=50)
    description: str | None = Field(None, max_length=5000)
    is_anniversary: bool = False


class MilestoneCreate(MilestoneBase):
    pass


class MilestoneUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    date: datetime.date | None = None
    icon: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=5000)
    is_anniversary: bool | None = None


class MilestoneRead(MilestoneBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ── Dashboard ────────────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    tage_zusammen: int
    erinnerungen_count: int
    fotos_count: int
    laender_count: int
    naechstes_jubilaeum: str | None = None


# ── CoupleSettings ──────────────────────────────────────────────────────────

class CoupleSettingsRead(BaseModel):
    id: int
    partner_since: datetime.date | None = None
    partner_a_name: str = "Partner A"
    partner_b_name: str = "Partner B"

    model_config = ConfigDict(from_attributes=True)


class CoupleSettingsUpdate(BaseModel):
    partner_since: datetime.date | None = None
    partner_a_name: str | None = Field(None, min_length=1, max_length=100)
    partner_b_name: str | None = Field(None, min_length=1, max_length=100)
