"""
app/schemas/appointment.py

Pydantic request/response schemas for appointment endpoints.
Note: patient_id is intentionally NOT accepted in any request body —
it is always derived from the authenticated caller (see api/deps.py).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    doctor_id: uuid.UUID
    slot_time: datetime


class AppointmentRescheduleRequest(BaseModel):
    new_slot_time: datetime


class AppointmentCancelRequest(BaseModel):
    reason: str


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doctor_id: uuid.UUID
    patient_id: uuid.UUID
    slot_time: datetime
    status: AppointmentStatus
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime