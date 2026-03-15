# Pydantic-Schemas für Request/Response-Validierung

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── User ─────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    name: str
    username: str


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
    name: str
    country: str | None = None
    lat: float
    lng: float


class PlaceRead(PlaceBase):
    id: int
    memory_id: int

    model_config = ConfigDict(from_attributes=True)


# ── Memory ───────────────────────────────────────────────────────────────────

class MemoryBase(BaseModel):
    title: str
    date: datetime.date
    description: str | None = None
    location: str | None = None
    lat: float | None = None
    lng: float | None = None
    mood: str | None = None
    category: str = "Alltag"


class MemoryCreate(MemoryBase):
    pass


class MemoryUpdate(BaseModel):
    title: str | None = None
    date: datetime.date | None = None
    description: str | None = None
    location: str | None = None
    lat: float | None = None
    lng: float | None = None
    mood: str | None = None
    category: str | None = None


class MemoryRead(MemoryBase):
    id: int
    created_by: int
    created_at: datetime.datetime
    photos: list[PhotoRead] = []
    places: list[PlaceRead] = []

    model_config = ConfigDict(from_attributes=True)


# ── Milestone ────────────────────────────────────────────────────────────────

class MilestoneBase(BaseModel):
    title: str
    date: datetime.date
    icon: str = "🌟"
    description: str | None = None
    is_anniversary: bool = False


class MilestoneCreate(MilestoneBase):
    pass


class MilestoneUpdate(BaseModel):
    title: str | None = None
    date: datetime.date | None = None
    icon: str | None = None
    description: str | None = None
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
    partner_a_name: str | None = None
    partner_b_name: str | None = None
