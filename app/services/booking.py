"""
app/services/booking.py

Booking logic. Validates a requested slot (working hours, grid
alignment, not in the past, not within the booking lead time), then
attempts to book it inside a single DB transaction.

Concurrency safety has two layers, deliberately:

1. SELECT ... FOR UPDATE on any existing row at this (doctor_id,
   slot_time) — this serializes concurrent requests for the SAME slot
   so the second one waits, then sees the first one's committed
   result, instead of both racing past a plain SELECT.
2. The partial unique DB constraint (see models/appointment.py) is
   the actual backstop: even if the locking above were removed or
   buggy, the constraint makes a duplicate booked row impossible.
   An IntegrityError from the constraint is caught and translated
   into the same "slot taken" error as the pre-check, so the API
   behaves identically either way.

"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, Doctor
from app.services.availability import is_slot_on_grid


class BookingError(Exception):
    """Base class for booking validation/conflict errors."""


class SlotOutsideWorkingHoursError(BookingError):
    pass


class SlotNotOnGridError(BookingError):
    pass


class SlotInPastError(BookingError):
    pass


class SlotTooSoonError(BookingError):
    pass


class SlotAlreadyBookedError(BookingError):
    pass


class DoctorNotFoundError(BookingError):
    pass


class AppointmentNotFoundError(BookingError):
    pass


class AppointmentAlreadyCancelledError(BookingError):
    pass


class NotAppointmentOwnerError(BookingError):
    pass


@dataclass
class BookingRequest:
    doctor_id: object  # uuid.UUID
    patient_id: object  # uuid.UUID
    slot_time: datetime


def _validate_slot(
    doctor: Doctor,
    slot_time: datetime,
    slot_duration_minutes: int,
    booking_lead_time_minutes: int,
    now: datetime,
) -> None:
    """Raise the appropriate BookingError if slot_time is not bookable, independent of taken/free state."""
    if not is_slot_on_grid(slot_time, doctor.work_start, doctor.work_end, slot_duration_minutes):
        # Distinguish "off grid" from "outside working hours" for a clearer error message.
        slot_local_time = slot_time.timetz()
        if slot_local_time < doctor.work_start.replace(tzinfo=slot_local_time.tzinfo) or (
            slot_time + timedelta(minutes=slot_duration_minutes)
        ).timetz() > doctor.work_end.replace(tzinfo=slot_local_time.tzinfo):
            raise SlotOutsideWorkingHoursError(
                f"Slot {slot_time.isoformat()} is outside doctor's working hours "
                f"({doctor.work_start}–{doctor.work_end})."
            )
        raise SlotNotOnGridError(
            f"Slot {slot_time.isoformat()} does not align with the {slot_duration_minutes}-minute booking grid."
        )

    if slot_time < now:
        raise SlotInPastError(f"Slot {slot_time.isoformat()} is in the past.")

    if slot_time < now + timedelta(minutes=booking_lead_time_minutes):
        raise SlotTooSoonError(
            f"Slot {slot_time.isoformat()} is within the {booking_lead_time_minutes}-minute booking lead time."
        )


async def book_appointment(
    db: AsyncSession,
    request: BookingRequest,
    slot_duration_minutes: int,
    booking_lead_time_minutes: int,
) -> Appointment:
    """Book a slot for a patient. Raises a BookingError subclass on any validation/conflict failure."""
    now = datetime.now(timezone.utc)

    doctor = await db.get(Doctor, request.doctor_id)
    if doctor is None:
        await db.rollback()
        raise DoctorNotFoundError(f"Doctor {request.doctor_id} not found.")

    try:
        _validate_slot(doctor, request.slot_time, slot_duration_minutes, booking_lead_time_minutes, now)
    except BookingError:
        await db.rollback()
        raise

    # Lock any existing row at this (doctor_id, slot_time), regardless of
    # status, so concurrent requests serialize on this specific slot rather
    # than racing past an unlocked SELECT. Note: FOR UPDATE only locks rows
    # that already exist — if no row exists yet, multiple concurrent
    # transactions can all pass this check simultaneously. The partial
    # unique DB constraint below is what actually prevents a double-booking
    # in that case; this lock is what serializes the *common* case (a slot
    # someone already holds) so most conflicts are caught here rather than
    # via a constraint-violation exception.
    existing = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == request.doctor_id, Appointment.slot_time == request.slot_time)
        .with_for_update()
    )
    existing_row = existing.scalar_one_or_none()

    if existing_row is not None and existing_row.status == AppointmentStatus.BOOKED:
        await db.rollback()
        raise SlotAlreadyBookedError(
            f"Slot {request.slot_time.isoformat()} for doctor {request.doctor_id} is already booked."
        )

    appointment = Appointment(
        doctor_id=request.doctor_id,
        patient_id=request.patient_id,
        slot_time=request.slot_time,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appointment)

    try:
        # commit (not just flush) — this is what actually persists the row
        # and releases the row lock, which is what lets a waiting concurrent
        # transaction proceed to see it.
        await db.commit()
    except IntegrityError as exc:
        # Backstop: the DB constraint caught a race the row lock didn't
        # (the "no existing row to lock" case described above). Translate
        # to the same domain error the pre-check would raise.
        await db.rollback()
        raise SlotAlreadyBookedError(
            f"Slot {request.slot_time.isoformat()} for doctor {request.doctor_id} is already booked."
        ) from exc

    await db.refresh(appointment)
    return appointment


async def cancel_appointment(
    db: AsyncSession, appointment_id: object, patient_id: object, reason: str
) -> Appointment:
    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        await db.rollback()
        raise AppointmentNotFoundError(f"Appointment {appointment_id} not found.")
    if appointment.patient_id != patient_id:
        await db.rollback()
        raise NotAppointmentOwnerError("You do not have permission to cancel this appointment.")
    if appointment.status == AppointmentStatus.CANCELLED:
        await db.rollback()
        raise AppointmentAlreadyCancelledError(f"Appointment {appointment_id} is already cancelled.")

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = reason
    await db.commit()
    await db.refresh(appointment)
    return appointment


async def reschedule_appointment(
    db: AsyncSession,
    appointment_id: object,
    patient_id: object,
    new_slot_time: datetime,
    slot_duration_minutes: int,
    booking_lead_time_minutes: int,
) -> Appointment:
    """
    Atomically move an appointment to a new slot. The old appointment
    is only marked cancelled once the new slot has been successfully
    validated and locked — so a failed reschedule never loses the
    patient's original booking.
    """
    now = datetime.now(timezone.utc)

    appointment = await db.get(Appointment, appointment_id)
    if appointment is None:
        await db.rollback()
        raise AppointmentNotFoundError(f"Appointment {appointment_id} not found.")
    if appointment.patient_id != patient_id:
        await db.rollback()
        raise NotAppointmentOwnerError("You do not have permission to reschedule this appointment.")
    if appointment.status == AppointmentStatus.CANCELLED:
        await db.rollback()
        raise AppointmentAlreadyCancelledError(
            f"Appointment {appointment_id} is cancelled and cannot be rescheduled."
        )

    doctor = await db.get(Doctor, appointment.doctor_id)
    if doctor is None:
        await db.rollback()
        raise DoctorNotFoundError(f"Doctor {appointment.doctor_id} not found.")
    doctor_id = doctor.id  # captured as a plain value — see book_appointment for why

    try:
        _validate_slot(doctor, new_slot_time, slot_duration_minutes, booking_lead_time_minutes, now)
    except BookingError:
        await db.rollback()
        raise

    existing = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == doctor_id, Appointment.slot_time == new_slot_time)
        .with_for_update()
    )
    existing_row = existing.scalar_one_or_none()

    if existing_row is not None and existing_row.status == AppointmentStatus.BOOKED:
        # New slot unavailable — original appointment is untouched
        # since we haven't modified it yet.
        await db.rollback()
        raise SlotAlreadyBookedError(
            f"Slot {new_slot_time.isoformat()} for doctor {doctor_id} is already booked."
        )

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = "rescheduled"

    new_appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        slot_time=new_slot_time,
        status=AppointmentStatus.BOOKED,
    )
    db.add(new_appointment)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise SlotAlreadyBookedError(
            f"Slot {new_slot_time.isoformat()} for doctor {doctor_id} is already booked."
        ) from exc

    await db.refresh(new_appointment)
    return new_appointment