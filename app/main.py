"""
app/main.py

FastAPI application instantiation and router registration. Entrypoint
used by uvicorn (`uvicorn app.main:app`).
"""

from fastapi import FastAPI

from app.api.routes import appointments, doctors, patients

app = FastAPI(
    title="Clinic Booking API",
    description="Backend API for booking, cancelling, and rescheduling clinic appointments.",
    version="0.1.0",
)

app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(patients.router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Liveness check used by deployment platforms and CI smoke tests."""
    return {"status": "ok"}
