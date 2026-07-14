"""
app/api/routes/patients.py

GET /patients/{id}/appointments (bonus). Returns the
requesting patient's upcoming (booked, future) appointments sorted by
slot_time ascending. A patient can only list their own appointments —
{id} in the path must match the authenticated patient_id.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient_id
from app.core.database import get_db_session
from app.models import Appointment, AppointmentStatus
from app.schemas.appointment import AppointmentOut

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/appointments", response_model=list[AppointmentOut])
async def list_patient_appointments(
    patient_id: uuid.UUID,
    current_patient_id=Depends(get_current_patient_id),
    db: AsyncSession = Depends(get_db_session),
) -> list[AppointmentOut]:
    if patient_id != current_patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view another patient's appointments.",
        )

    result = await db.execute(
        select(Appointment)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.slot_time >= datetime.now(timezone.utc),
        )
        .order_by(Appointment.slot_time.asc())
    )
    appointments = result.scalars().all()
    return [AppointmentOut.model_validate(appt) for appt in appointments]
