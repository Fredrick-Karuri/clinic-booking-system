"""
app/models/appointment.py

Appointment ORM model. The `uq_doctor_slot_when_booked` partial unique
index is the actual source of truth for "a slot can only be booked
once" — it is what makes the invariant hold even if application-level
locking has a bug. See services/booking.py for how it's used alongside
SELECT ... FOR UPDATE.
"""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.doctor import Doctor



class AppointmentStatus(str, enum.Enum):
    BOOKED = "booked"
    CANCELLED = "cancelled"


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    slot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        String(20), default=AppointmentStatus.BOOKED, nullable=False
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    doctor: Mapped["Doctor"] = relationship(back_populates="appointments")  # noqa: F821

    __table_args__ = (
        # The actual invariant: at most one BOOKED appointment per
        # (doctor_id, slot_time). Enforced by Postgres regardless of
        # what the application code does or doesn't check first.
        Index(
            "uq_doctor_slot_when_booked",
            "doctor_id",
            "slot_time",
            unique=True,
            postgresql_where=text(f"status = '{AppointmentStatus.BOOKED.value}'"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Appointment id={self.id} doctor_id={self.doctor_id} "
            f"slot_time={self.slot_time} status={self.status}>"
        )
