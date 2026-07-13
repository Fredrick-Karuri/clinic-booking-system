"""
app/repositories/appointment/postgres.py

Postgres-backed implementation of AppointmentRepository. This is
where the concurrency-safety mechanics actually live: SELECT ... FOR
UPDATE for the common case (a slot someone already holds), and the
partial unique DB constraint (see models/appointment.py) as the
backstop for the "no existing row to lock yet" case — see the module
docstring in appointment_repository.py for the contract this must
satisfy.

Each public method here is one complete, self-contained unit of work
on the session it's given: it commits on success or rolls back on
failure, and the caller (the service layer) never touches the session
or transaction directly.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentStatus, Doctor
from app.repositories.appointment.base import AppointmentRepository, SlotConflictError


class PostgresAppointmentRepository(AppointmentRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_doctor(self, doctor_id: UUID) -> Doctor | None:
        return await self._session.get(Doctor, doctor_id)

    async def get_appointment(self, appointment_id: UUID) -> Appointment | None:
        return await self._session.get(Appointment, appointment_id)

    async def create_booked_appointment(
        self, doctor_id: UUID, patient_id: UUID, slot_time: datetime
    ) -> Appointment:
        existing_row = await self._lock_slot(doctor_id, slot_time)
        if existing_row is not None and existing_row.status == AppointmentStatus.BOOKED:
            await self._session.rollback()
            raise SlotConflictError(
                f"Slot {slot_time.isoformat()} for doctor {doctor_id} is already booked."
            )

        appointment = Appointment(
            doctor_id=doctor_id, patient_id=patient_id, slot_time=slot_time, status=AppointmentStatus.BOOKED
        )
        self._session.add(appointment)

        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Backstop: the DB constraint caught a race the row lock
            # didn't (the "no existing row to lock yet" case — see
            # appointment_repository.py's module docstring).
            await self._session.rollback()
            raise SlotConflictError(
                f"Slot {slot_time.isoformat()} for doctor {doctor_id} is already booked."
            ) from exc

        await self._session.refresh(appointment)
        return appointment

    async def save_cancellation(self, appointment: Appointment, reason: str) -> Appointment:
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancellation_reason = reason
        await self._session.commit()
        await self._session.refresh(appointment)
        return appointment

    async def reschedule(self, appointment: Appointment, new_slot_time: datetime) -> Appointment:
        # Captured as plain values immediately — after any rollback below,
        # touching ORM attributes on an expired object outside an async
        # context raises MissingGreenlet.
        doctor_id = appointment.doctor_id
        patient_id = appointment.patient_id

        existing_row = await self._lock_slot(doctor_id, new_slot_time)
        if existing_row is not None and existing_row.status == AppointmentStatus.BOOKED:
            # New slot unavailable — appointment is untouched since we
            # haven't modified it yet.
            await self._session.rollback()
            raise SlotConflictError(
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
        self._session.add(new_appointment)

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise SlotConflictError(
                f"Slot {new_slot_time.isoformat()} for doctor {doctor_id} is already booked."
            ) from exc

        await self._session.refresh(new_appointment)
        return new_appointment

    async def _lock_slot(self, doctor_id: UUID, slot_time: datetime) -> Appointment | None:
        """Lock any existing row at (doctor_id, slot_time), regardless of
        status, so concurrent requests serialize on this specific slot.
        Returns None if no row exists yet — FOR UPDATE only locks rows
        that already exist, which is why the unique constraint backstop
        in the calling methods is still required."""
        result = await self._session.execute(
            select(Appointment)
            .where(Appointment.doctor_id == doctor_id, Appointment.slot_time == slot_time)
            .with_for_update()
        )
        return result.scalar_one_or_none()
