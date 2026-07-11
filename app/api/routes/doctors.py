"""
app/api/routes/doctors.py

GET /doctors/{id}/availability.
"""

import uuid
from datetime import date as date_type
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.models import Appointment, AppointmentStatus, Doctor
from app.schemas.doctor import AvailabilityResponse
from app.services.availability import compute_available_slots

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("/{doctor_id}/availability", response_model=AvailabilityResponse)
async def get_doctor_availability(
    doctor_id: uuid.UUID,
    date: date_type = Query(..., description="Date to check availability for, YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AvailabilityResponse:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Doctor {doctor_id} not found."
        )

    result = await db.execute(
        select(Appointment.slot_time).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.slot_time >= datetime.combine(date, doctor.work_start, tzinfo=timezone.utc),
            Appointment.slot_time < datetime.combine(date, doctor.work_end, tzinfo=timezone.utc),
        )
    )
    taken_slot_times = set(result.scalars().all())

    free_slots = compute_available_slots(
        work_start=doctor.work_start,
        work_end=doctor.work_end,
        target_date=date,
        taken_slot_times=taken_slot_times,
        slot_duration_minutes=settings.slot_duration_minutes,
        now=datetime.now(timezone.utc),
        booking_lead_time_minutes=settings.booking_lead_time_minutes,
    )

    return AvailabilityResponse(doctor_id=doctor_id, date=date.isoformat(), available_slots=free_slots)