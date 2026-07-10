"""
app/scripts/seed.py

Populates the database with 5 doctors, each with distinct working
hours, for local development and demo purposes. Idempotent: running it
twice does not create duplicates (matched by full_name).

Run with: python -m app.scripts.seed  (or `make seed`)
"""

import asyncio
from datetime import time

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Doctor

SEED_DOCTORS = [
    {"full_name": "Dr. Amina Yusuf", "work_start": time(8, 0), "work_end": time(16, 0)},
    {"full_name": "Dr. Brian Otieno", "work_start": time(9, 0), "work_end": time(17, 0)},
    {"full_name": "Dr. Carol Mwangi", "work_start": time(10, 0), "work_end": time(18, 0)},
    {"full_name": "Dr. David Kimani", "work_start": time(8, 30), "work_end": time(15, 30)},
    {"full_name": "Dr. Esther Njeri", "work_start": time(9, 30), "work_end": time(17, 30)},
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for doctor_data in SEED_DOCTORS:
            existing = await session.execute(
                select(Doctor).where(Doctor.full_name == doctor_data["full_name"])
            )
            if existing.scalar_one_or_none() is not None:
                print(f"Skipping (already exists): {doctor_data['full_name']}")
                continue

            doctor = Doctor(**doctor_data)
            session.add(doctor)
            print(f"Created: {doctor_data['full_name']}")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())