# Salon Appointment App — Agent Conventions

Single source of project rules for every agent (`salon-lead`, `salon-backend`, `salon-flutter`, `salon-integration`). Read this before any task. Operational sync files: `docs/CONTRACT.md` (API truth) and `docs/PHASES.md` (status board).

## Stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, JWT auth, Razorpay (India)
- Mobile: Flutter, Riverpod, dio, razorpay_flutter
- Region: India — currency ₹, timezone **Asia/Kolkata** for display; store datetimes **UTC** in DB/API
- Slot grid: **15 minutes**

## Folder ownership (never edit outside your folder)

| Owner | Paths |
|---|---|
| salon-lead | `docs/`, `AGENTS.md`, `opencode.json`, `.opencode/` |
| salon-backend | `backend/` **except** paths listed for salon-integration (includes `backend/app/static/panel/` admin browser dashboard) |
| salon-flutter | `mobile/` |
| salon-integration | `backend/app/services/payments.py`, `backend/app/api/webhooks*`, `backend/tests/test_payment*`, `backend/tests/test_e2e*`, `docker-compose.yml`, deploy/CI files |

Backend creates booking rows with `status=pending_payment` and a call into `services/payments.py`’s public interface (defined in `docs/CONTRACT.md`); salon-integration implements Razorpay order/verify/webhook/refund behind that interface.

## Service catalog (seed data — do not invent other prices)

| Service | Online price | Duration |
|---|---|---|
| Haircut | ₹100 | 60 min |
| Wash add-on | +₹30 | +15 min (allowed on **any** service) |
| Shaving | ₹70 | 30 min |
| Beard trim | ₹50 | 15 min |
| Head massage | (combo component) | 30 min |
| Massage + Haircut | ₹200 | 90 min |
| Shaving + Massage | ₹130 | 60 min |
| Haircut + Shaving | ₹180 | 90 min (haircut + shave) |
| Haircut + Beard trim | ₹130 | 75 min (haircut + trim) |
| Full combo (haircut + beard trim + head massage + wash) | ₹250 | 120 min |
| Hair color | **₹100 flat advance online**, actual price at center | 90 min |

## Pricing / advance rules

- Fixed services: `total = price (+30 if wash)`; `advance = 50%` online; balance in-shop.
- Hair color (`price_type=variable_advance`): `advance = ₹100` flat online; `balance = final_price_at_center − 100` set by admin on completion.
- Duration: `service.duration (+15 if wash add-on)`.

## Booking rules

- One barber, one customer at a time: overlap check on `(barber_id, [start_at, end_at))`.
- Slots generated from `barber_schedules` (weekday open/close/is_closed), 15-min step, filtered by service+addon duration and existing `pending_payment`/`confirmed` bookings; exclude past times for today.
- Unpaid hold: `pending_payment` expires in **12 minutes** (`expires_at`); Razorpay verify re-checks overlap before `confirmed`.
- Statuses: `pending_payment` → `confirmed` → `completed` | `cancelled` → `refunded` | `no_show`.
- Cancel ≥ 2h before start → auto refund advance; later → advance forfeited (policy constant in config).
- **Primary mobile flow:** barber list first → barber selection page (service + wash + date + slot) → checkout. `/services` is secondary/tab entry.
- **Guest booking (no login):** `POST /bookings` without Bearer requires `guest_name` + `guest_phone`; server find-or-creates customer by phone (`is_guest` when new) and returns `access_token` for verify/cancel/list. Do not force login at Pay. See `docs/CONTRACT.md` (2026-09-24).

## Sync protocol

1. Lead freezes `docs/CONTRACT.md` before any code fan-out.
2. Specialists read contract + this file at task start; only edit their folder.
3. Contract change → reply `CONTRACT_CHANGE: <delta>` to lead; do not edit contract sections yourself (may append an “Implemented” note under your endpoint only).
4. Phase progress → update **only your rows** in `docs/PHASES.md`.
5. Report `DONE`, `BLOCKED: <reason>`, or `CONTRACT_CHANGE` as the final message of every task.

## Verify commands

- Backend: `cd backend && pip install -r requirements.txt && pytest`
- Flutter: `cd mobile && flutter analyze && flutter test` (if SDK unavailable, note `BLOCKED: no flutter SDK`)
- Never commit; never run destructive shell (`rm -rf`, force git) without asking.

## Seed admins

One admin user created by backend seed script (env `ADMIN_PHONE` / `ADMIN_PASSWORD`); customers self-register. Barbers are data rows only (no login in MVP).
