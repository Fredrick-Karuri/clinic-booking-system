# CI/CD & Deployment

## CI (GitHub Actions, `.github/workflows/ci.yml`)

- Triggers on every pull request into `main`, and on push to `main`.
- Spins up a real Postgres 16 service container.
- Installs `requirements.txt`, runs `alembic upgrade head`, then `PYTHONPATH=. pytest --cov`.
- A failing test blocks the PR from being merged (branch protection enabled on `main`).

## Deployment (Railway)

**Branch:** `main` — every merge triggers an automatic build + deploy.

Railway's model is **native GitHub autodeploy**, configured in Railway's dashboard rather than
as a deploy step inside the GitHub Actions workflow:

1. Railway project connected to this repo via "Deploy from GitHub repo."
2. A Postgres plugin provisions its own `DATABASE_URL` automatically.
3. Remaining env vars set from `.env.example` (`AUTH_TOKEN_SEED` overridden with a real secret,
   not the dev default).
4. Service Settings → Source confirms `main` as the trigger branch.
5. Railway builds from the `Dockerfile`, which runs `alembic upgrade head` before starting
   `uvicorn` — migrations apply automatically on every deploy.

## What the Pipeline Does, End to End

`git push` to a PR branch → GitHub Actions spins up Postgres + runs the full test suite →
merge to `main` (only possible if tests passed) → Railway detects the push to `main` →
builds the Docker image → runs migrations → starts the new container → old container is
replaced.

## Real Deployment Issues Hit (and Fixes)

Documented honestly, since getting a deployment working end-to-end surfaced several
non-obvious platform-specific issues:

**1. `psycopg2` not installed / wrong DB driver.** Alembic's migration path resolved to the
sync `psycopg2` dialect instead of async `asyncpg` because Railway's auto-provisioned
`DATABASE_URL` came as a plain `postgresql://...` string, and SQLAlchemy defaults that prefix
to `psycopg2` (never installed in this project, since everything else uses `asyncpg`). Fixed
with a `field_validator` on `Settings.database_url` that rewrites `postgresql://` →
`postgresql+asyncpg://` regardless of what the platform provides — self-healing rather than
relying on Railway's dashboard being configured a particular way.

**2. Wrong port.** The Dockerfile correctly binds to `$PORT` at container start, but Railway's
dashboard had a mismatched target-port setting pointing at `8000` instead of the `8080` Railway
actually assigned — "Application failed to respond" with a perfectly healthy container
underneath. Fixed by correcting the target port in Railway's Networking settings.

**3. Internal vs. public Postgres hostname.** Running the seed script locally against the
production DB via `railway run` failed with `socket.gaierror` — Railway's default
`DATABASE_URL` uses an internal hostname (`postgres.railway.internal`) that only resolves
*inside* Railway's private network, not from a local machine. Fixed by using the public proxy
connection string (visible under the Postgres service's Connect tab → Public Network) for any
one-off local scripts that need to reach the production DB directly.

## Seeding Is a One-Time Bootstrap, Not a Pipeline Step

Migrations (schema) run automatically on every deploy via the Dockerfile — that's meant to be
repeatable and idempotent. Seeding (the 5 sample doctors) is a one-off action triggered manually
once against production, not wired into CI/CD — there's no ongoing need to reseed on every
deploy, and doing so automatically would risk duplicate rows if the seed script isn't
idempotent. `DATABASE_URL` for one-off local scripts against production is passed explicitly on
the command line and is never stored as a GitHub secret, since GitHub Actions never touches the
production database at all — only the ephemeral Postgres container CI spins up for itself.