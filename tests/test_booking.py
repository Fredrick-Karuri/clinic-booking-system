"""
app/tests/test_booking.py

Tests for BookingService.book_appointment (CLINIC-006), run against
real Postgres. The concurrency test is the one the whole exercise is
built around: N simultaneous requests for the same slot must yield
exactly one success.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import (
    DoctorNotFoundError,
    SlotAlreadyBookedError,
    SlotInPastError,
    SlotNotOnGridError,
    SlotOutsideWorkingHoursError,
    SlotTooSoonError,
)
from app.models import AppointmentStatus
from app.services.booking import BookingRequest
from tests.conftest import make_booking_service

pytestmark = pytest.mark.asyncio


def _future_slot(days: int, hour: int, minute: int = 0) -> datetime:
    target = datetime.now(timezone.utc) + timedelta(days=days)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def test_book_appointment_success(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    appointment = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
    )
    assert appointment.status == AppointmentStatus.BOOKED
    assert appointment.slot_time == slot_time


async def test_book_appointment_outside_working_hours(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=7)  # doctor works 09:00-17:00
    with pytest.raises(SlotOutsideWorkingHoursError):
        await booking_service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
        )


async def test_book_appointment_off_grid(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10, minute=15)  # not on 30-min grid
    with pytest.raises(SlotNotOnGridError):
        await booking_service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
        )


async def test_book_appointment_in_past(booking_service, test_doctor, patient_id):
    slot_time = datetime.now(timezone.utc) - timedelta(days=1)
    slot_time = slot_time.replace(hour=10, minute=0, second=0, microsecond=0)
    with pytest.raises(SlotInPastError):
        await booking_service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
        )


async def test_book_appointment_within_lead_time(db_session, test_doctor, patient_id):
    # Constructs its own service with a 24h lead time to precisely
    # exercise SlotTooSoonError, independent of the shared fixture's
    # 60-min default — deliberately not reaching into private state.
    from app.repositories.appointment.postgres import PostgresAppointmentRepository
    from app.services.booking import BookingService

    service = BookingService(
        PostgresAppointmentRepository(db_session),
        slot_duration_minutes=30,
        booking_lead_time_minutes=1440,
    )

    now = datetime.now(timezone.utc)
    candidate = now.replace(minute=30 if now.minute < 30 else 0, second=0, microsecond=0)
    if now.minute >= 30:
        candidate += timedelta(hours=1)
    candidate = candidate.replace(hour=max(9, min(candidate.hour, 16)))

    with pytest.raises(SlotTooSoonError):
        await service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=candidate)
        )


async def test_book_appointment_unknown_doctor(booking_service, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    with pytest.raises(DoctorNotFoundError):
        await booking_service.book_appointment(
            BookingRequest(doctor_id=uuid.uuid4(), patient_id=patient_id, slot_time=slot_time)
        )


async def test_book_appointment_already_booked(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=11)
    await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
    )
    with pytest.raises(SlotAlreadyBookedError):
        await booking_service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=uuid.uuid4(), slot_time=slot_time)
        )


async def test_concurrent_booking_same_slot_only_one_succeeds(session_factory, test_doctor):
    """
    THE critical test: fire 10 simultaneous booking requests at the
    exact same (doctor, slot_time), each on its own DB session/
    connection/BookingService instance. Exactly one must succeed; the
    rest must fail with SlotAlreadyBookedError.
    """
    slot_time = _future_slot(days=5, hour=13)
    concurrency = 10

    async def attempt_booking():
        async with session_factory() as session:
            service = make_booking_service(session)
            try:
                await service.book_appointment(
                    BookingRequest(doctor_id=test_doctor.id, patient_id=uuid.uuid4(), slot_time=slot_time)
                )
                return "success"
            except SlotAlreadyBookedError:
                return "conflict"

    results = await asyncio.gather(*(attempt_booking() for _ in range(concurrency)))

    successes = results.count("success")
    conflicts = results.count("conflict")

    assert successes == 1, f"Expected exactly 1 success, got {successes}. Results: {results}"
    assert conflicts == concurrency - 1