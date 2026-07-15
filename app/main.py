"""
app/main.py

FastAPI application instantiation and router registration. Entrypoint
used by uvicorn (`uvicorn app.main:app`).
"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.routes import appointments, doctors, patients
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.core.middleware import RequestLoggingMiddleware

configure_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_title,
    description=settings.app_description,
    version=settings.app_version,
)

app.add_middleware(RequestLoggingMiddleware)

app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(patients.router)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Liveness check used by deployment platforms and CI smoke tests."""
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Convenience redirect so visiting the bare deployed URL lands
    somewhere useful instead of a bare 404."""
    return RedirectResponse(url="/docs")
