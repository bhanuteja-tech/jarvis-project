"""SQLAlchemy persistence model.

This module is the ONLY place where the canonical domain meets the database.
The domain model (`app.models.job`) knows nothing about SQLAlchemy, and this
module never talks to HTTP or sources.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobORM(Base):
    """Persistent representation of one canonical job post.

    Identity is `(source, source_job_id)` — enforced by a database unique
    constraint. This is *source-level* identity only; cross-source
    deduplication is Phase 1 Step 6 and deliberately absent here.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),  # PostgreSQL 13+
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    company: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(100))

    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(8))
    salary_period: Mapped[str | None] = mapped_column(String(20))

    job_url: Mapped[str | None] = mapped_column(Text)
    apply_url: Mapped[str | None] = mapped_column(Text)

    source_created_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetched_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        sa.UniqueConstraint("source", "source_job_id", name="uq_jobs_source_source_job_id"),
        sa.Index("ix_jobs_discovered_at", "discovered_at"),
        sa.Index("ix_jobs_source_updated_at", "source_updated_at"),
    )
