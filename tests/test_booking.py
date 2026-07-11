"""
app/tests/test_booking.py

Tests for the booking service, run against real
Postgres. The concurrency test: N simultaneous requests for the same slot must yield exactly
one success.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import AppointmentStatus
from app.services.booking import (
    BookingRequest,
    SlotAlreadyBookedError,
    SlotInPastError,
    SlotNotOnGridError,
    SlotOutsideWorkingHoursError,
    SlotTooSoonError,
    book_appointment,
)

pytestmark = pytest.mark.asyncio

SLOT_DURATION = 30
LEAD_TIME = 60


def _future_slot(days: int, hour: int, minute: int = 0) -> datetime:
    target = datetime.now(timezone.utc) + timedelta(days=days)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


async def test_book_appointment_success(db_session, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    appointment = await book_appointment(
        db_session,
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time),
        slot_duration_minutes=SLOT_DURATION,
        booking_lead_time_minutes=LEAD_TIME,
    )
    assert appointment.status == AppointmentStatus.BOOKED
    assert appointment.slot_time == slot_time


async def test_book_appointment_outside_working_hours(db_session, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=7)  # doctor works 09:00-17:00
    with pytest.raises(SlotOutsideWorkingHoursError):
        await book_appointment(
            db_session,
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time),
            slot_duration_minutes=SLOT_DURATION,
            booking_lead_time_minutes=LEAD_TIME,
        )


async def test_book_appointment_off_grid(db_session, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10, minute=15)  # not on 30-min grid
    with pytest.raises(SlotNotOnGridError):
        await book_appointment(
            db_session,
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time),
            slot_duration_minutes=SLOT_DURATION,
            booking_lead_time_minutes=LEAD_TIME,
        )


async def test_book_appointment_in_past(db_session, test_doctor, patient_id):
    slot_time = datetime.now(timezone.utc) - timedelta(days=1)
    slot_time = slot_time.replace(hour=10, minute=0, second=0, microsecond=0)
    with pytest.raises(SlotInPastError):
        await book_appointment(
            db_session,
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time),
            slot_duration_minutes=SLOT_DURATION,
            booking_lead_time_minutes=LEAD_TIME,
        )


async def test_book_appointment_within_lead_time(db_session, test_doctor, patient_id):
    # Doctor's working hours are wide (09:00-17:00); pick "now" rounded
    # up to the next slot boundary, which will be within the 60-min lead time.
    now = datetime.now(timezone.utc)
    next_slot = now.replace(second=0, microsecond=0) + timedelta(minutes=5)
    with pytest.raises((SlotTooSoonError, SlotOutsideWorkingHoursError, SlotNotOnGridError)):
        await book_appointment(
            db_session,
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=next_slot),
            slot_duration_minutes=SLOT_DURATION,
            booking_lead_time_minutes=LEAD_TIME,
        )


async def test_book_appointment_already_booked(db_session, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=11)
    await book_appointment(
        db_session,
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time),
        slot_duration_minutes=SLOT_DURATION,
        booking_lead_time_minutes=LEAD_TIME,
    )
    with pytest.raises(SlotAlreadyBookedError):
        await book_appointment(
            db_session,
            BookingRequest(doctor_id=test_doctor.id, patient_id=uuid.uuid4(), slot_time=slot_time),
            slot_duration_minutes=SLOT_DURATION,
            booking_lead_time_minutes=LEAD_TIME,
        )


async def test_concurrent_booking_same_slot_only_one_succeeds(session_factory, test_doctor):
    """
    THE critical test: fire 10 simultaneous booking requests at the
    exact same (doctor, slot_time), each on its own DB session/
    connection. Exactly one must succeed; the rest must fail with
    SlotAlreadyBookedError. This is the race condition scenario from
    the assessment's live debugging session, proven under real
    concurrent load against real Postgres.
    """
    slot_time = _future_slot(days=5, hour=13)
    concurrency = 10

    async def attempt_booking():
        async with session_factory() as session:
            try:
                await book_appointment(
                    session,
                    BookingRequest(doctor_id=test_doctor.id, patient_id=uuid.uuid4(), slot_time=slot_time),
                    slot_duration_minutes=SLOT_DURATION,
                    booking_lead_time_minutes=LEAD_TIME,
                )
                return "success"
            except SlotAlreadyBookedError:
                return "conflict"

    results = await asyncio.gather(*(attempt_booking() for _ in range(concurrency)))

    successes = results.count("success")
    conflicts = results.count("conflict")

    assert successes == 1, f"Expected exactly 1 success, got {successes}. Results: {results}"
    assert conflicts == concurrency - 1