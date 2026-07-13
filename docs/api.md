# API Reference

Interactive docs (Swagger UI) are available at `/docs` on any running instance — this page is a
quick-reference summary; `/docs` is authoritative for request/response schemas.

## Endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health` | Liveness check | none |
| GET | `/doctors/{id}/availability?date=YYYY-MM-DD` | Free 30-min slots for a doctor on a date | none |
| POST | `/appointments` | Book a slot. Body: `{doctor_id, slot_time}` | bearer token |
| PATCH | `/appointments/{id}/cancel` | Cancel. Body: `{reason}` | bearer token, owner only |
| PATCH | `/appointments/{id}/reschedule` | Move to a new slot. Body: `{new_slot_time}` | bearer token, owner only |
| GET | `/patients/{id}/appointments` | Upcoming appointments, sorted ascending (bonus) | bearer token, owner only |

## Status Codes

| Code | Meaning |
|---|---|
| `200` | Success (cancel, reschedule, list, availability) |
| `201` | Appointment created |
| `400` | Validation failure — outside working hours, off the 30-min grid, in the past, or within the 1-hour booking lead time |
| `401` | Missing or invalid bearer token |
| `403` | Authenticated, but not the resource owner |
| `404` | Doctor or appointment not found |
| `409` | Slot conflict (already booked) or appointment already cancelled |
| `422` | Malformed request body (schema validation) |

## Validation Rules (POST /appointments and reschedule)

A slot is only bookable if **all** of the following hold:

1. It falls within the doctor's working hours (`work_start`–`work_end`).
2. It aligns with the 30-minute grid (e.g. `10:00`, `10:30` — not `10:15`).
3. It is not in the past.
4. It is not within 1 hour of the current time (bonus lead-time rule).
5. It is not already booked by another non-cancelled appointment.

Reschedule validates the **new** slot exactly as a fresh booking would, and additionally
requires the appointment being rescheduled to not already be cancelled.

## Auth

Bearer-token scheme: `token = "<patient_id>.<hmac_signature>"`. The token's `patient_id` is the
only source of truth for "who is making this request" — request bodies never carry
`patient_id`, so a caller cannot book, cancel, or reschedule on behalf of another patient by
supplying a different id in the JSON body.

See [getting-started.md](getting-started.md#auth-for-local-testing) for how to generate a
token locally.