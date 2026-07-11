"""
app/tests/conftest.py

Fixtures for booking-service tests. These run against a real Postgres
instance (DATABASE_URL) rather than SQLite, because the concurrency
guarantees under test (SELECT ... FOR UPDATE, partial unique
constraint) are Postgres-specific behavior that SQLite cannot
faithfully emulate.
"""

import uuid
from datetime import time

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Appointment, Doctor

settings = get_settings()


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(settings.database_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def session_factory(db_engine):
    """Factory for creating independent sessions, used by concurrency tests
    that need separate DB connections racing against each other."""
    return async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def test_doctor(db_session: AsyncSession):
    """A doctor with predictable 09:00-17:00 hours, cleaned up after the test."""
    doctor = Doctor(full_name=f"Test Doctor {uuid.uuid4()}", work_start=time(9, 0), work_end=time(17, 0))
    db_session.add(doctor)
    await db_session.commit()
    await db_session.refresh(doctor)
    doctor_id = doctor.id  # captured as a plain value — service calls in the
    # test may roll back this session, which expires ORM objects; touching
    # doctor.id afterwards outside an async context raises MissingGreenlet.

    yield doctor

    await db_session.rollback()  # clear any dangling transaction state before cleanup
    await db_session.execute(delete(Appointment).where(Appointment.doctor_id == doctor_id))
    await db_session.execute(delete(Doctor).where(Doctor.id == doctor_id))
    await db_session.commit()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()