"""Database persistence tests (real PostgreSQL).

These tests REQUIRE a reachable PostgreSQL instance. When none is available
they SKIP with an explicit reason so the skip is visible in test output —
they never silently pass, and completion reports must mention them.

Target database resolution order:
1. ``JARVIS_TEST_DATABASE_URL`` environment variable
2. ``DATABASE_URL`` from application settings / `.env`

Schema is created from the SQLAlchemy metadata for isolation; the Alembic
migration itself is verified separately (``alembic upgrade head``).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.db.models import Base, JobORM
from app.db.queries import upsert_jobs
from app.db.session import create_session_factory
from app.models.job import Job, Salary


def _resolve_database_url() -> str:
    override = os.environ.get("JARVIS_TEST_DATABASE_URL")
    return override or get_settings().database_url


def _safe_url(url: str) -> str:
    """URL rendered without credentials for logs/skip reasons."""
    return sa.engine.url.make_url(url).render_as_string(hide_password=True)


@pytest.fixture(scope="module")
def db_engine():
    url = _resolve_database_url()
    # Bound the probe so a firewalled/unreachable host fails fast instead
    # of hanging on OS-level TCP timeouts (libpq connect_timeout, seconds).
    connect_args = (
        {"connect_timeout": 3}
        if sa.engine.url.make_url(url).get_backend_name() == "postgresql"
        else {}
    )
    engine = sa.create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as exc:
        engine.dispose()
        pytest.skip(
            "PostgreSQL unavailable at "
            f"{_safe_url(url)} ({type(exc).__name__}): "
            "database persistence tests SKIPPED - start PostgreSQL or set "
            "JARVIS_TEST_DATABASE_URL to run them"
        )

    # Create tables only when missing (checkfirst). We deliberately never
    # drop_all here: against a migrated database that would destroy the
    # Alembic-managed schema while alembic_version still reports "head".
    # Row isolation between tests is handled by _clean_jobs_table.
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_jobs_table(db_engine):
    yield
    with db_engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM jobs"))


@pytest.fixture
def session_factory(db_engine) -> sessionmaker[Session]:
    return create_session_factory(db_engine)


def make_job(source_job_id: str = "1", **overrides) -> Job:
    defaults: dict = {
        "source": "greenhouse",
        "source_job_id": source_job_id,
        "title": f"Role {source_job_id}",
        "company": "Example Corp",
        "location": "NYC",
        "description": "<p>desc</p>",
        "job_url": f"https://boards.greenhouse.io/examplecorp/jobs/{source_job_id}",
        "apply_url": f"https://boards.greenhouse.io/examplecorp/jobs/{source_job_id}",
        "source_updated_at": datetime(2026, 8, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return Job(**defaults)


class TestUpsertJobs:
    def test_new_jobs_are_inserted_with_identity(self, session_factory) -> None:
        jobs = [make_job("1"), make_job("2")]

        with session_factory() as session:
            stats = upsert_jobs(session, jobs)

            rows = session.query(JobORM).order_by(JobORM.source_job_id).all()

        assert (stats.inserted, stats.updated, stats.unchanged) == (2, 0, 0)
        assert [row.source_job_id for row in rows] == ["1", "2"]
        assert all(row.source == "greenhouse" for row in rows)

    def test_identical_refetch_leaves_row_completely_untouched(self, session_factory) -> None:
        original = make_job("10")

        with session_factory() as session:
            upsert_jobs(session, [original])
            before = session.query(JobORM).filter_by(source_job_id="10").one()
            discovered_at, fetched_at = before.discovered_at, before.fetched_at

        later_fetch = Job(**original.model_dump(exclude={"id", "discovered_at", "fetched_at"}))
        assert later_fetch.fetched_at > fetched_at  # sanity: time moved on

        with session_factory() as session:
            stats = upsert_jobs(session, [later_fetch])
            after = session.query(JobORM).filter_by(source_job_id="10").one()

        assert (stats.inserted, stats.updated, stats.unchanged) == (0, 0, 1)
        assert after.discovered_at == discovered_at
        assert after.fetched_at == fetched_at  # untouched when nothing changed

    def test_changed_content_updates_and_preserves_discovered_at(self, session_factory) -> None:
        original = make_job("20", title="Old Title")

        with session_factory() as session:
            upsert_jobs(session, [original])
            before = session.query(JobORM).filter_by(source_job_id="20").one()
            original_discovered_at = before.discovered_at
            original_fetched_at = before.fetched_at

        changed = Job(
            **original.model_dump(
                exclude={
                    "id",
                    "discovered_at",
                    "fetched_at",
                    "title",
                    "source_updated_at",
                }
            ),
            title="New Title",
            source_updated_at=datetime(2026, 8, 10, tzinfo=UTC),
        )

        with session_factory() as session:
            stats = upsert_jobs(session, [changed])
            after = session.query(JobORM).filter_by(source_job_id="20").one()

        assert (stats.inserted, stats.updated, stats.unchanged) == (0, 1, 0)
        assert after.title == "New Title"
        assert after.source_updated_at == datetime(2026, 8, 10, tzinfo=UTC)
        assert after.discovered_at == original_discovered_at
        assert after.fetched_at > original_fetched_at

    def test_database_enforces_source_identity_uniqueness(self, session_factory) -> None:
        with session_factory() as session:
            session.add(
                JobORM(
                    id=uuid.uuid4(),
                    source="greenhouse",
                    source_job_id="dup-1",
                    title="first",
                )
            )
            session.commit()

            session.add(
                JobORM(
                    id=uuid.uuid4(),
                    source="greenhouse",
                    source_job_id="dup-1",
                    title="second",
                )
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

    def test_salary_value_object_flattens_into_columns(self, session_factory) -> None:
        job = make_job(
            "30",
            salary=Salary(
                min_amount=Decimal("100000.00"),
                max_amount=Decimal("150000.50"),
                currency="USD",
                period="year",
            ),
        )

        with session_factory() as session:
            upsert_jobs(session, [job])
            row = session.query(JobORM).filter_by(source_job_id="30").one()

        assert row.salary_min == Decimal("100000.00")
        assert row.salary_max == Decimal("150000.50")
        assert row.salary_currency == "USD"
        assert row.salary_period == "year"

    def test_extra_provenance_roundtrips_as_jsonb(self, session_factory) -> None:
        job = make_job("40", extra={"internal_job_id": 42, "is_prospect": False})

        with session_factory() as session:
            upsert_jobs(session, [job])
            row = session.query(JobORM).filter_by(source_job_id="40").one()

        assert row.extra == {"internal_job_id": 42, "is_prospect": False}
