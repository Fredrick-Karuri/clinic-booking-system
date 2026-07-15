# Testing the API by Hand

A step-by-step script for demoing or manually exercising the full booking flow — locally or
against the deployed URL. Auth here is intentionally minimal (see
[architecture.md](architecture.md#non-goals-explicit-out-of-scope) — there's no registration
endpoint), so generating a token requires `AUTH_TOKEN_SEED`, which only exists locally or on
the deployed instance itself.
## 1. Get a Bearer Token

Every write endpoint needs one (see [api.md](api.md#auth)):

```bash
make token                                                    # random patient_id
make token PATIENT_ID=11111111-1111-1111-1111-111111111111    # fixed patient_id — useful for
                                                               # testing 403 ownership checks
                                                               # across two sessions
```

Copy the printed token.

## 2. Get a Doctor ID

You need a real `doctor_id` to check availability or book. If you don't already have one:

**Local (Docker Compose):**
```bash
make psql
```
```sql
SELECT id, full_name FROM doctors LIMIT 5;
```
`\q` to exit.

**Deployed (Railway):**
```bash
make railway-psql
```
Same query as above. This uses Railway's *public* Postgres proxy — see
[deployment.md](deployment.md#internal-vs-public-postgres-hostname) for why the public
connection is required for anything running outside Railway's network.

## 3. Open Swagger and Authorize

Local: `http://localhost:8000/docs`
Deployed: `https://clinic-booking.up.railway.app/docs`

Click **Authorize** (top right, padlock icon) and paste in the token from step 1.

## 4. Walk the Flow

1. **`GET /doctors/{id}/availability?date=YYYY-MM-DD`** — use the doctor id from step 2 and a
   near-future date. No auth needed for this one. Confirms the doctor exists and shows free
   slots — copy one of the returned `slot_time` values exactly for the next step.

2. **`POST /appointments`** — body: `{"doctor_id": "...", "slot_time": "..."}` (from step 4.1).
   Expect `201` with the new appointment's `id`.

3. **Repeat the same `POST /appointments`** with the identical `doctor_id`/`slot_time` — expect
   `409` (slot already booked). This is the core invariant the whole system protects.

4. **`PATCH /appointments/{id}/cancel`** — body: `{"reason": "test"}`, using the `id` from
   step 4.2. Expect `200`.

5. **Repeat the cancel** — expect `409` (already cancelled).

6. **Book a fresh appointment**, then **`PATCH /appointments/{id}/reschedule`** — body:
   `{"new_slot_time": "..."}` with a different valid slot. Expect `200`, old slot freed, new
   slot booked.

7. **`GET /patients/{patient_id}/appointments`** — use the `patient_id` your token was issued
   for (the UUID you passed to `make token`, or the random one it printed). Expect your booked/
   rescheduled appointments, sorted ascending, cancelled ones excluded.

## 5. Verify Ownership Enforcement

Generate a second token for a different `patient_id` (`make token PATIENT_ID=<different-uuid>`),
re-Authorize in Swagger with it, then:

- Try `PATCH /appointments/{id}/cancel` or `/reschedule` on an appointment booked under the
  *first* token — expect `403`.
- Try `GET /patients/{other_patient_id}/appointments` using a patient id that isn't your
  token's own — expect `403`.

## Watching It Happen Live

Tail structured logs while you run through the flow above — every step above produces a
matching log line (see [observability.md](observability.md)):

```bash
make logs             # local, docker-compose logs -f
make railway-logs      # deployed, tails the Railway service
```