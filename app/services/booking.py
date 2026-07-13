"""
app/services/booking.py

Business orchestration for booking, cancelling, and rescheduling
appointments. This module owns business rules (working hours, slot
grid alignment, timing, ownership) and nothing else — no SQL, no
session, no transaction handling, no locking. All persistence and
concurrency-safety mechanics are delegated to an AppointmentRepository
implementation (see app/repositories/), so swapping the backing store
means writing a new repository, not touching this file.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.logging_config import get_logger
from app.exceptions import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
    DoctorNotFoundError,
    NotAppointmentOwnerError,
    SlotAlreadyBookedError,
    SlotInPastError,
    SlotNotOnGridError,
    SlotOutsideWorkingHoursError,
    SlotTooSoonError,
)
from app.models import Appointment, AppointmentStatus, Doctor
from app.repositories.appointment.base import AppointmentRepository, SlotConflictError
from app.services.availability import is_slot_on_grid

logger = get_logger("app.booking")

@dataclass
class BookingRequest:
    doctor_id: UUID
    patient_id: UUID
    slot_time: datetime


class BookingService:
    def __init__(
        self,
        repository: AppointmentRepository,
        slot_duration_minutes: int,
        booking_lead_time_minutes: int,
    ):
        self._repository = repository
        self._slot_duration_minutes = slot_duration_minutes
        self._booking_lead_time_minutes = booking_lead_time_minutes

    async def book_appointment(self, request: BookingRequest) -> Appointment:
        now = datetime.now(timezone.utc)

        doctor = await self._repository.get_doctor(request.doctor_id)
        if doctor is None:
            raise DoctorNotFoundError(f"Doctor {request.doctor_id} not found.")

        self._validate_slot(doctor, request.slot_time, now)

        try:
            appointment =  await self._repository.create_booked_appointment(
                request.doctor_id, request.patient_id, request.slot_time
            )
        except SlotConflictError as exc:
            logger.warning(
                "booking_conflict",
                extra={
                    "doctor_id": str(request.doctor_id),
                    "patient_id": str(request.patient_id),
                    "slot_time": request.slot_time.isoformat(),
                },
            )
            raise SlotAlreadyBookedError(str(exc)) from exc

        logger.info(
            "appointment_booked",
            extra={
                "appointment_id": str(appointment.id),
                "doctor_id": str(request.doctor_id),
                "patient_id": str(request.patient_id),
                "slot_time": request.slot_time.isoformat(),
            },
        )
        return appointment

    async def cancel_appointment(self, appointment_id: UUID, patient_id: UUID, reason: str) -> Appointment:
        appointment = await self._repository.get_appointment(appointment_id)
        if appointment is None:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found.")
        if appointment.patient_id != patient_id:
            raise NotAppointmentOwnerError("You do not have permission to cancel this appointment.")
        if appointment.status == AppointmentStatus.CANCELLED:
            raise AppointmentAlreadyCancelledError(f"Appointment {appointment_id} is already cancelled.")

        cancelled =  await self._repository.save_cancellation(appointment, reason)
        logger.info(
            "appointment_cancelled",
            extra={"appointment_id": str(appointment_id), "patient_id": str(patient_id), "reason": reason},
        )
        return cancelled

    async def reschedule_appointment(
        self, appointment_id: UUID, patient_id: UUID, new_slot_time: datetime
    ) -> Appointment:
        now = datetime.now(timezone.utc)

        appointment = await self._repository.get_appointment(appointment_id)
        if appointment is None:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found.")
        if appointment.patient_id != patient_id:
            raise NotAppointmentOwnerError("You do not have permission to reschedule this appointment.")
        if appointment.status == AppointmentStatus.CANCELLED:
            raise AppointmentAlreadyCancelledError(
                f"Appointment {appointment_id} is cancelled and cannot be rescheduled."
            )

        doctor = await self._repository.get_doctor(appointment.doctor_id)
        if doctor is None:
            raise DoctorNotFoundError(f"Doctor {appointment.doctor_id} not found.")

        self._validate_slot(doctor, new_slot_time, now)

        try:
            new_appointment = await self._repository.reschedule(appointment, new_slot_time)
        except SlotConflictError as exc:
            logger.warning(
                "reschedule_conflict",
                extra={
                    "appointment_id": str(appointment_id),
                    "patient_id": str(patient_id),
                    "new_slot_time": new_slot_time.isoformat(),
                },
            )
            raise SlotAlreadyBookedError(str(exc)) from exc
        logger.info(
            "appointment_rescheduled",
            extra={
                "old_appointment_id": str(appointment_id),
                "new_appointment_id": str(new_appointment.id),
                "patient_id": str(patient_id),
                "new_slot_time": new_slot_time.isoformat(),
            },
        )
        return new_appointment

    def _validate_slot(self, doctor: Doctor, slot_time: datetime, now: datetime) -> None:
        """Raise the appropriate BookingError if slot_time is not
        bookable, independent of whether it's actually taken — that's
        the repository's concern, checked separately."""
        if not is_slot_on_grid(slot_time, doctor.work_start, doctor.work_end, self._slot_duration_minutes):
            slot_local_time = slot_time.timetz()
            if slot_local_time < doctor.work_start.replace(tzinfo=slot_local_time.tzinfo) or (
                slot_time + timedelta(minutes=self._slot_duration_minutes)
            ).timetz() > doctor.work_end.replace(tzinfo=slot_local_time.tzinfo):
                raise SlotOutsideWorkingHoursError(
                    f"Slot {slot_time.isoformat()} is outside doctor's working hours "
                    f"({doctor.work_start}–{doctor.work_end})."
                )
            raise SlotNotOnGridError(
                f"Slot {slot_time.isoformat()} does not align with the "
                f"{self._slot_duration_minutes}-minute booking grid."
            )

        if slot_time < now:
            raise SlotInPastError(f"Slot {slot_time.isoformat()} is in the past.")

        if slot_time < now + timedelta(minutes=self._booking_lead_time_minutes):
            raise SlotTooSoonError(
                f"Slot {slot_time.isoformat()} is within the "
                f"{self._booking_lead_time_minutes}-minute booking lead time."
            )
