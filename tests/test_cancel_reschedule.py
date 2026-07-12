"""
app/tests/test_cancel_reschedule.py

Tests for BookingService.cancel_appointment / .reschedule_appointment, 
run against real Postgres. Covers: a failed reschedule must never 
lose the patient's original slot, and two concurrent reschedules 
targeting the same new slot must not both succeed.

"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
    NotAppointmentOwnerError,
    SlotAlreadyBookedError,
    SlotOutsideWorkingHoursError,
)
from app.models import AppointmentStatus
from app.services.booking import BookingRequest
from tests.conftest import make_booking_service

pytestmark = pytest.mark.asyncio


def _future_slot(days: int, hour: int, minute: int = 0) -> datetime:
    target = datetime.now(timezone.utc) + timedelta(days=days)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ---------- cancel ----------


async def test_cancel_appointment_success(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    appointment = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
    )
    cancelled = await booking_service.cancel_appointment(appointment.id, patient_id, reason="patient request")
    assert cancelled.status == AppointmentStatus.CANCELLED
    assert cancelled.cancellation_reason == "patient request"


async def test_cancel_already_cancelled_returns_409_error(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    appointment = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
    )
    await booking_service.cancel_appointment(appointment.id, patient_id, reason="first cancel")
    with pytest.raises(AppointmentAlreadyCancelledError):
        await booking_service.cancel_appointment(appointment.id, patient_id, reason="second cancel")


async def test_cancel_by_non_owner_forbidden(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    appointment = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
    )
    other_patient = uuid.uuid4()
    with pytest.raises(NotAppointmentOwnerError):
        await booking_service.cancel_appointment(appointment.id, other_patient, reason="not mine")


async def test_cancel_unknown_appointment(booking_service, patient_id):
    with pytest.raises(AppointmentNotFoundError):
        await booking_service.cancel_appointment(uuid.uuid4(), patient_id, reason="doesn't exist")


async def test_cancelled_slot_becomes_bookable_again(booking_service, test_doctor, patient_id):
    slot_time = _future_slot(days=3, hour=10)
    appointment = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=slot_time)
    )
    await booking_service.cancel_appointment(appointment.id, patient_id, reason="freeing slot")

    # Same slot, different patient, should now succeed.
    new_patient = uuid.uuid4()
    rebooked = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=new_patient, slot_time=slot_time)
    )
    assert rebooked.status == AppointmentStatus.BOOKED
    assert rebooked.slot_time == slot_time


# ---------- reschedule ----------


async def test_reschedule_success_frees_old_slot_and_books_new(booking_service, test_doctor, patient_id):
    old_slot = _future_slot(days=3, hour=10)
    new_slot = _future_slot(days=3, hour=11)

    original = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=old_slot)
    )
    rescheduled = await booking_service.reschedule_appointment(original.id, patient_id, new_slot)
    assert rescheduled.status == AppointmentStatus.BOOKED
    assert rescheduled.slot_time == new_slot

    # Old slot must be free again — book it with a different patient.
    other_patient = uuid.uuid4()
    rebooked_old_slot = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=other_patient, slot_time=old_slot)
    )
    assert rebooked_old_slot.slot_time == old_slot


async def test_reschedule_to_taken_slot_leaves_original_untouched(booking_service, test_doctor, patient_id):
    """
    The specific scenario the reviewer notes flag: if the new slot is
    taken by the time the reschedule is processed, the patient must
    NOT lose their original slot.
    """
    old_slot = _future_slot(days=3, hour=10)
    contested_slot = _future_slot(days=3, hour=11)

    original = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=old_slot)
    )
    original_id = original.id  # captured before the conflict — the repository's
    # internal rollback on SlotConflictError expires ORM objects in this session

    # Someone else takes the target slot first.
    other_patient = uuid.uuid4()
    await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=other_patient, slot_time=contested_slot)
    )

    with pytest.raises(SlotAlreadyBookedError):
        await booking_service.reschedule_appointment(original_id, patient_id, contested_slot)

    # Original appointment must still be BOOKED at the old slot.
    refreshed = await booking_service._repository.get_appointment(original_id)  # noqa: SLF001
    assert refreshed.status == AppointmentStatus.BOOKED
    assert refreshed.slot_time == old_slot


async def test_reschedule_cancelled_appointment_fails(booking_service, test_doctor, patient_id):
    old_slot = _future_slot(days=3, hour=10)
    new_slot = _future_slot(days=3, hour=11)

    original = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=old_slot)
    )
    await booking_service.cancel_appointment(original.id, patient_id, reason="no longer needed")

    with pytest.raises(AppointmentAlreadyCancelledError):
        await booking_service.reschedule_appointment(original.id, patient_id, new_slot)


async def test_reschedule_unknown_appointment(booking_service, patient_id):
    new_slot = _future_slot(days=3, hour=11)
    with pytest.raises(AppointmentNotFoundError):
        await booking_service.reschedule_appointment(uuid.uuid4(), patient_id, new_slot)


async def test_reschedule_by_non_owner_forbidden(booking_service, test_doctor, patient_id):
    old_slot = _future_slot(days=3, hour=10)
    new_slot = _future_slot(days=3, hour=11)

    original = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=old_slot)
    )
    other_patient = uuid.uuid4()
    with pytest.raises(NotAppointmentOwnerError):
        await booking_service.reschedule_appointment(original.id, other_patient, new_slot)


async def test_reschedule_outside_working_hours(booking_service, test_doctor, patient_id):
    old_slot = _future_slot(days=3, hour=10)
    invalid_new_slot = _future_slot(days=3, hour=20)  # doctor works 09:00-17:00

    original = await booking_service.book_appointment(
        BookingRequest(doctor_id=test_doctor.id, patient_id=patient_id, slot_time=old_slot)
    )
    with pytest.raises(SlotOutsideWorkingHoursError):
        await booking_service.reschedule_appointment(original.id, patient_id, invalid_new_slot)

    # Original must remain untouched.
    refreshed = await booking_service._repository.get_appointment(original.id)  # noqa: SLF001
    assert refreshed.status == AppointmentStatus.BOOKED
    assert refreshed.slot_time == old_slot


async def test_concurrent_reschedule_same_new_slot_only_one_succeeds(session_factory, test_doctor):
    """
    Two different patients, each with their own existing appointment,
    both try to reschedule into the SAME new slot at the same time.
    Exactly one should succeed; the loser must keep their original
    appointment intact.
    """
    slot_a = _future_slot(days=6, hour=9)
    slot_b = _future_slot(days=6, hour=9, minute=30)
    contested_slot = _future_slot(days=6, hour=14)

    patient_a, patient_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as setup_session:
        setup_service = make_booking_service(setup_session)
        appt_a = await setup_service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_a, slot_time=slot_a)
        )
        appt_b = await setup_service.book_appointment(
            BookingRequest(doctor_id=test_doctor.id, patient_id=patient_b, slot_time=slot_b)
        )
        appt_a_id, appt_b_id = appt_a.id, appt_b.id

    async def attempt_reschedule(appointment_id, patient):
        async with session_factory() as session:
            service = make_booking_service(session)
            try:
                await service.reschedule_appointment(appointment_id, patient, contested_slot)
                return "success"
            except SlotAlreadyBookedError:
                return "conflict"

    results = await asyncio.gather(
        attempt_reschedule(appt_a_id, patient_a),
        attempt_reschedule(appt_b_id, patient_b),
    )

    assert results.count("success") == 1
    assert results.count("conflict") == 1

    # Whoever lost must still have their ORIGINAL appointment intact.
    async with session_factory() as check_session:
        refreshed_a = await check_session.get(type(appt_a), appt_a_id)
        refreshed_b = await check_session.get(type(appt_b), appt_b_id)

        if results[0] == "conflict":
            assert refreshed_a.status == AppointmentStatus.BOOKED
            assert refreshed_a.slot_time == slot_a
        if results[1] == "conflict":
            assert refreshed_b.status == AppointmentStatus.BOOKED
            assert refreshed_b.slot_time == slot_b