# syntax=docker/dockerfile:1

FROM python:3.12-slim

WORKDIR /app

# System deps for asyncpg build + psql client not needed at runtime;
# keep the image lean.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway (and most PaaS) inject PORT at runtime; default to 8000 for
# local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Run migrations then start the server. Using a shell form so $PORT
# expands at container start, not build time.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}