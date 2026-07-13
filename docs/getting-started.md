# Getting Started

## Option A — Docker Compose (recommended)

```bash
cp .env.example .env
make up          # builds the app image, starts Postgres + the API
make migrate      # in a second terminal, once the DB is healthy
make seed
```

## Option B — Local Python + local Postgres

```bash
python3 -m venv .venv && source .venv/bin/activate
make install                      # installs requirements-dev.txt
cp .env.example .env              # edit DATABASE_URL to point at your local Postgres
make migrate
make seed
make run                          # http://localhost:8000
```

## Auth for Local Testing

There's no registration endpoint (out of scope). To get a valid bearer token for a given
`patient_id`, issue one with the same signing scheme the API uses:

```bash
make token                                                    # random patient_id
make token PATIENT_ID=11111111-1111-1111-1111-111111111111    # fixed patient_id — useful for
                                                               # reproducing the same identity
                                                               # across multiple terminal sessions
                                                               # (e.g. testing 403 ownership checks)
```

## Inspecting the Database Directly

```bash
make psql   # opens a psql shell into the running db container (docker-compose exec db psql -U postgres -d clinic)
```