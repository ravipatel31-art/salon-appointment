# salon_mobile

Flutter client for the salon appointment app (India — ₹, Asia/Kolkata display, 15-min slot grid).

Stack: Flutter + Riverpod + dio + go_router + `razorpay_flutter`.

## Run

```bash
# Mock mode (default) — full UI against the in-memory mock backend.
flutter run

# Real backend — swap is config-only (same repository interfaces).
flutter run \
  --dart-define=USE_MOCK_API=false \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

- `API_BASE_URL` (default `http://10.0.2.2:8000`) — Android emulator loopback for a
  host-local FastAPI.
- `USE_MOCK_API` (default `true`) — when `false`, repositories hit the real API
  via dio with the JWT bearer token stored by `AuthTokenStore`.

## Verify

```bash
flutter analyze
flutter test
```

## Screens

Splash · Login · Register · Home (services with duration/₹) · Barbers (5) ·
Barber detail (next-14-day date picker, 15-min slot chips, wash add-on
**+₹30 · +15m** toggle with live price/duration) · Checkout (summary + hold
countdown + pay advance via Razorpay using the contract `payment` object) ·
Processing / Success / Failure (409 `slot_unavailable` → snackbar + back to
picker; verify failure → retry/cancel path) · My Bookings (upcoming/past, cancel
≥2h) · Profile.

Hair color (`price_type=variable_advance`): **₹100 advance online — actual
price at center**.

## Notes

- Advance = `ceil(total * 0.5)` for fixed services; wash is +₹30 / +15 min;
  unpaid holds expire in 12 minutes (`expires_at`).
- Mock repositories implement the same interfaces as the API ones — switching
  backends only needs the dart-defines above.
