"""
app/schemas/doctor.py

Pydantic request/response schemas for doctor-related endpoints.
"""

import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    work_start: time
    work_end: time


class AvailabilityResponse(BaseModel):
    doctor_id: uuid.UUID
    date: str
    available_slots: list[datetime]