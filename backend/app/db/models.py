"""
Job and BuildingCache models for the zone-insurer async workflow.

- Job: one row per submitted zone-assessment request (async model).
- BuildingCache: de-dup cache keyed by normalized BAN address label.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "zone_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String, default="processing")  # processing | done | error
    address: Mapped[str] = mapped_column(String)
    radius_m: Mapped[float] = mapped_column(Float)

    total_buildings: Mapped[int] = mapped_column(Integer, default=0)
    processed_buildings: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String, default="queued")

    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BuildingCache(Base):
    __tablename__ = "zone_building_cache"

    address_label: Mapped[str] = mapped_column(String, primary_key=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)

    building_data: Mapped[dict] = mapped_column(JSON)
    risk_scores: Mapped[dict] = mapped_column(JSON)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
