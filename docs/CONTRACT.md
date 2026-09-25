# API Contract (source of truth)

Freeze before code. Lead owns edits; specialists append only under **Implemented** lines. All bodies JSON. Auth = `Authorization: Bearer <access_token>` unless marked public. Errors: `{"detail": "..."}` with proper HTTP status. Times: RFC3339 UTC. Currency: integer paise in payment fields where noted; display amounts in rupees as numbers (e.g. `100`).

## Shared enums

**BookingStatus:** `pending_payment` | `confirmed` | `completed` | `cancelled` | `refunded` | `no_show`

**PriceType:** `fixed` | `variable_advance`

**Role:** `customer` | `admin`

## Auth (public unless noted)

| Method | Path | Body / query | Response |
|---|---|---|---|
| POST | `/auth/register` | `{name, phone, email, password}` | `{access_token, token_type:"bearer", user}` |
| POST | `/auth/login` | `{email, password}` or `{phone, password}` | same |
| GET | `/auth/me` | — | `user`: `{id, name, phone, email, role}` |

## Catalog (public)

`GET /services` →

```json
{
  "items": [
    {
      "id": 1,
      "name": "Haircut",
      "description": "",
      "duration_minutes": 60,
      "price": 100,
      "price_type": "fixed",
      "is_active": true,
      "addons": [
        {"id": "wash", "name": "Wash", "price": 30, "duration_minutes": 15}
      ]
    }
  ]
}
```

Seed rows must match AGENTS.md catalog (hair color: `price=100`, `price_type=variable_advance`).

`GET /barbers` → `{items:[{id, name, photo_url, bio, specialties, is_active}]}` (5 seeded barbers).

`GET /barbers/{id}` → single barber.

### Imagery (CONTRACT_CHANGE applied 2026-09-24 — demo polish)

- **Barber photos:** `photo_url` is an absolute **HTTPS** URL or `null`. Seed may set stable public demo portraits (no auth). Admin can PATCH later; clients must tolerate `null` and HTTP failures.
- **Services:** no `image_url` in the API (unchanged). Presentation art is **client-owned** (Flutter asset map and/or icon + brand gradient keyed by `service.id` / name). Do not invent new catalog fields without a lead contract change.
- **Client rule:** every remote image uses `errorBuilder` / placeholder → gradient + initials or themed icon so the UI stays attractive offline.

**Implemented (Flutter half):** ✅ phase 12 (salon-flutter) — `BarberAvatar`/`BarberHeroImage` (`barber_photo.dart`) with `errorBuilder` → wine/gold gradient + initials; `ServiceArt*` client-side catalog art keyed by service id/name; richer splash/cards/empty states; mock backend `photo_url`s (i.pravatar.cc). Widget tests install `test/support/fake_image_http.dart` (portrait URLs → tiny PNG, others → empty 400 per flutter_test rules). `flutter analyze` clean, **72/72** tests.

`GET /barbers/{id}/availability?date=YYYY-MM-DD&service_id=1&addons=wash` →

```json
{
  "barber_id": 1,
  "date": "2026-09-24",
  "service_id": 1,
  "duration_minutes": 75,
  "slots": [
    {"start_at": "2026-09-24T04:30:00Z", "available": true}
  ]
}
```

Slots on 15-min grid within that barber’s working hours for `date` (Asia/Kolkata calendar day), minus overlaps with `pending_payment`/`confirmed`, minus past times if date=today; last start satisfies `start + duration <= close`.

## Bookings (customer)

### Auth model (CONTRACT_CHANGE applied 2026-09-24 — guest checkout)

- **Registered customer:** `Authorization: Bearer <user access_token>` (unchanged).
- **Guest (no login):** `POST /bookings` may omit auth. Body MUST then include `guest_name` (non-empty, max 80) and `guest_phone` (India mobile, 10 digits after optional `+91`/`0`; stored normalized as 10-digit). Server find-or-creates a **`role=customer` only** user by phone:
  - If phone matches an existing **customer** → link booking to that user; do **not** overwrite profile/password; issue a guest-session token for that user (no password proof required for this booking session only — token is a normal JWT access_token).
  - If phone matches an existing **admin** (or any `role != customer`) → `400 {"detail":"guest_identity_required"}` (force that person to log in; never mint a bearer for admin/other roles from guest create).
  - If phone is new → create `User` with `name=guest_name`, `phone`, `role=customer`, `is_guest=true`, `password_hash` random unusable; `email` may be null for pure guests (relax unique email if backend already stores synthetic email — pick one scheme and keep it; contract requires only: no customer-visible password, phone unique).
- Guest create response = normal booking/payment payload **plus** top-level `"access_token"` and `"token_type":"bearer"` and `"user"` (same shape as `/auth/login`). Client stores this token for verify-payment / cancel / GET for that session (in-memory is enough for MVP).
- `POST /bookings/{id}/verify-payment`, `GET /bookings/{id}`, `POST /bookings/{id}/cancel`, `GET /bookings` accept **either** a registered access_token or a guest access_token issued at create (ownership: `booking.user_id == token.user.id`, same as today).
- Admin and webhook behavior unchanged; guest bookings appear in admin lists as normal customers.

`POST /bookings` body (auth or guest):

```json
{
  "service_id": 1,
  "addons": ["wash"],
  "barber_id": 2,
  "start_at": "2026-09-24T04:30:00Z",
  "notes": "",
  "guest_name": "Optional when unauthenticated",
  "guest_phone": "9876543210"
}
```

`guest_name` / `guest_phone` ignored when a valid Bearer token is present (or may 400 if both auth and guest fields conflict — prefer ignore).

Response `201`:

```json
{
  "booking": {
    "id": "uuid",
    "booking_ref": "SL-20260924-0042",
    "status": "pending_payment",
    "service_id": 1,
    "barber_id": 2,
    "addons": ["wash"],
    "start_at": "…Z",
    "end_at": "…Z",
    "duration_minutes": 75,
    "total_amount": 130,
    "advance_amount": 65,
    "balance_amount": 65,
    "online_amount_paid": 0,
    "expires_at": "…Z",
    "guest_name": "optional",
    "guest_phone": "optional"
  },
  "payment": {
    "razorpay_order_id": "order_xxx",
    "razorpay_amount": 6500,
    "razorpay_currency": "INR",
    "key_id": "rzp_live_xxx"
  },
  "access_token": "present only when created without prior session",
  "token_type": "bearer",
  "user": {"id": 1, "name": "…", "phone": "…", "email": null, "role": "customer"}
}
```

`access_token` / `token_type` / `user` omitted when the client already sent a valid Bearer token.

**Implemented:** ✅ phase 8 (salon-backend) — optional auth on `POST /bookings`; `get_optional_user`; `resolve_guest_user` customer-only find-or-create (admin/other role → 400 `guest_identity_required`); migration `0004_guest_users` (`is_guest`, nullable email); guest tokens accepted on verify/list/get/cancel; `guest_name`/`guest_phone` on booking payload from owner. Backend pytest 128 passed.

Advance: fixed → `ceil(total * 0.5)`; hair color → `100`. `razorpay_amount` in **paise**. Hold TTL **12 min**. Conflict → `409 {"detail":"slot_unavailable"}`. Missing guest identity when unauthenticated → `422` or `400 {"detail":"guest_identity_required"}` (prefer `400` with that detail for Flutter parity).

`POST /bookings/{id}/verify-payment` →

```json
{"razorpay_order_id":"order_xxx","razorpay_payment_id":"pay_xxx","razorpay_signature":"…"}
```

→ HMAC-SHA256 verify → re-check overlap + hold not expired → `booking.status="confirmed"`, `online_amount_paid=advance`. Fail → `400`. Auth: registered or guest token.

`GET /bookings` (token subject’s) and `GET /bookings/{id}` → booking as above + `service_name`, `barber_name`, `final_price_at_center`, `balance_due`.

`POST /bookings/{id}/cancel` → requires start ≥ now+2h → `cancelled`, enqueue refund if `online_amount_paid>0` → eventually `refunded`; else `403`. Auth: registered or guest token.

**Booking optional field (CONTRACT_CHANGE applied 2026-09-23):** booking JSON may include `"cancellation_reason": "hold_expired" | "customer" | null` (nullable in DB, optional in responses; hold-expiry sets `"hold_expired"`, customer cancel sets `"customer"`).

## Webhooks (public)

`POST /webhooks/razorpay` — raw body signature check; idempotent by `razorpay_payment_id`; marks confirmed if booking still `pending_payment` and valid.

## Payments service interface (lead freezes; integration implements)

```python
# backend/app/services/payments.py
def create_order(amount_rupees: int, receipt: str) -> dict: ...
def verify_payment(order_id: str, payment_id: str, signature: str) -> bool: ...
def refund(payment_id: str, amount_rupees: int | None = None) -> dict: ...
def verify_webhook(body: bytes, signature: str) -> bool: ...
```

**Implemented:** ✅ phase 3 (salon-integration) — `backend/app/services/payments.py`:
`create_order` → Razorpay `POST /v1/orders` (offline via `RAZORPAY_MOCK=1`), returns the payment-object keys above plus raw aliases (`id`/`amount`/`currency`/`receipt`/`status`), paise = rupees×100; `verify_payment` = HMAC-SHA256(`order_id|payment_id`, `RAZORPAY_KEY_SECRET`); `refund` = `POST /v1/payments/{id}/refund` (optional rupees→paise) + best-effort `cancelled→refunded`; `verify_webhook` = HMAC-SHA256(raw body, `RAZORPAY_WEBHOOK_SECRET`). Env: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` (+ `RAZORPAY_MOCK`, `RAZORPAY_API_BASE_URL`).
`POST /webhooks/razorpay` implemented in `backend/app/api/webhooks.py` (`router`): raw-body signature → 401 `invalid_signature`; conditional status-gated UPDATEs so replay of the same `razorpay_payment_id` returns 200 `already_processed` (single confirm); confirms only while `pending_payment` and hold unexpired; `refund.processed` → `cancelled→refunded`; on-read hold sweep first. **Wiring:** salon-backend must `app.include_router(app.api.webhooks.router)` in `app/main.py` (integration does not own `main.py`).
Hold expiry: `backend/app/services/hold_expiry.py::sweep_expired_holds` → `pending_payment` past `expires_at` → `cancelled` + `cancellation_reason="hold_expired"` **when that column exists** (CONTRACT_CHANGE proposed: add nullable `cancellation_reason` on booking + optional field in booking JSON); background worker auto-starts unless `HOLD_EXPIRY_WORKER=0`.

**Test payment bypass (CONTRACT_CHANGE applied 2026-09-24 — local/demo only):**
- Env **`RAZORPAY_MOCK=1`** (root `.env` / compose): `create_order` / `refund` stay offline as today (`order_mock_*`, `rfnd_mock_*`, `key_id` → `rzp_test_mock` when unset).
- **When `razorpay_mock` is true**, `verify_payment(order_id, payment_id, signature)` returns **`True` if all three are non-empty** (skip HMAC). When mock is false, HMAC-SHA256 behavior is unchanged (fails closed without secret). Never enable mock in production (`RAZORPAY_MOCK=0` + real keys).
- **Flutter:** compile-time `--dart-define=PAYMENT_MOCK=true` (default **false**). When true, `paymentGatewayProvider` uses **`MockPaymentGateway`** (simulate success sheet → `pay_MOCK*` / `sig_MOCK*`) even if `USE_MOCK_API=false`. Repositories stay real API when `USE_MOCK_API=false`. Production/Play builds must omit `PAYMENT_MOCK` or set `false`.
- Recommended local test run: `USE_MOCK_API=false`, `API_BASE_URL=http://10.0.2.2:8000`, `PAYMENT_MOCK=true`, API env `RAZORPAY_MOCK=1`.

**Implemented (Flutter half):** ✅ phase 10 (salon-flutter) — `ApiConfig.paymentMock` (`bool.fromEnvironment('PAYMENT_MOCK', defaultValue: false)`, never for Play Store); `paymentGatewayProvider` → `MockPaymentGateway` when `useMockApiProvider || ApiConfig.paymentMock`, else `RazorpayPaymentGateway`; repositories unchanged (`USE_MOCK_API` alone). Checkout/processing note: with both defines, sheet is mock but verify still calls the real API. `payment_gateway_provider_test.dart` pins selection + repo/gateway separation. `flutter analyze` clean, 61/61 tests (also green under `--dart-define=PAYMENT_MOCK=true`).

## Admin (role=admin)

| Method | Path | Notes |
|---|---|---|
| GET/POST/PATCH/DELETE | `/admin/services` | CRUD catalog |
| GET/POST/PATCH/DELETE | `/admin/barbers` | CRUD |
| GET/PUT | `/admin/barbers/{id}/schedule` | weekly hours `[{weekday:0-6, open_time, close_time, is_closed}]` |
| GET | `/admin/bookings?date=&barber_id=&status=` | list |
| PATCH | `/admin/bookings/{id}` | `{"action":"complete","final_price_at_center":250}` or `{"action":"no_show"}`; complete on color requires `final_price_at_center`; sets `balance_due = final - online_amount_paid` |
| GET | `/admin/dashboard` | `{date, bookings_count, confirmed_count, revenue_online, revenue_at_center}` |

### Admin browser dashboard (CONTRACT_CHANGE applied 2026-09-24 — phase 13)

- **Purpose:** owner/admin browser UI to edit **barbers** (name, photo, bio, specialties, active, weekly schedule) and the **salon plan** (services: name, price, duration, `price_type`, active) plus read bookings/dashboard. No new business APIs required beyond the Admin table above.
- **Serving:** FastAPI serves a static SPA from `backend/app/static/panel/` at **`GET /panel`** (and `GET /panel/{path:path}` SPA fallback). Assets are same-origin — browser calls `/auth/login` + `/admin/*` with `Authorization: Bearer` (no CORS config change required when opened via the API host).
- **Auth:** same `POST /auth/login` as mobile; store `access_token` in `sessionStorage`; non-admin token → show login (403 from admin routes must surface as “admin only”).
- **MVP screens (phase 13):** Login → shell with tabs **Barbers** | **Services** (plan) | **Bookings** | **Dashboard**.
  - Barbers: list/create/edit/delete; fields per `BarberPatch`; schedule editor via `GET/PUT /admin/barbers/{id}/schedule` (7 weekdays, open/close `HH:MM`, `is_closed`).
  - Services: list/create/edit/delete; fields per `ServicePatch` (₹ integer rupees in API; hair color `price_type=variable_advance` + `price=100` online advance).
  - Bookings: date/barber/status filters; `PATCH` complete (color → require `final_price_at_center`) / no_show.
  - Dashboard: date picker + aggregates from `GET /admin/dashboard`.
- **Styling:** match brand (wine `#7A2E4A` / gold `#B08D57` / cream); responsive desktop-first; no external CDN required for core UI (inline CSS/JS or local assets only).
- **Out of scope:** separate deploy host, user management beyond the single seed admin, Razorpay settings UI.

**Implemented:** ✅ phase 13 (salon-backend) — static SPA at `backend/app/static/panel/` (`index.html` + `app.css` + `app.js`, vanilla, no CDN/npm), served by `GET /panel` + `GET /panel/{path:path}` SPA fallback with path-traversal guard wired in `app/main.py::_mount_panel` (`include_in_schema=False`). Login via `POST /auth/login` (email/password) → `sessionStorage`; non-admin role and any 403 from `/admin/*` clear the session and surface “Admin only”. Tabs: Barbers (CRUD + weekly schedule GET/PUT editor, Mon=0…Sun=6), Services/plan (CRUD; hair colour hint keeps `price=100`/`variable_advance`), Bookings (date/barber/status filters; PATCH complete prompts required `final_price_at_center` for `variable_advance` services, no_show), Dashboard (IST date + 4 aggregates). Brand wine `#7A2E4A` / gold `#B08D57` / cream, desktop-first. Tests: `backend/tests/test_panel.py` (6) incl. HTML/assets/fallback/traversal; backend pytest **139 passed**.

### Panel edit routing + SQL injection hardening (CONTRACT_CHANGE applied 2026-09-24 — phase 14)

- **Full-page edit routes (no scroll-to-edit):** client hash routes open each edit as its **own view** (top of page; Back returns to list):
  - `#/barbers` → `#/barbers/new` → `#/barbers/{id}/edit` (name, photo, bio, specialties, active + weekly **Schedule** on the same page)
  - `#/services` → `#/services/new` → `#/services/{id}/edit`
  - `#/bookings`, `#/dashboard` remain tab roots
  - List **Edit** navigates to the route; modals only for delete confirms and `final_price_at_center`.
- **SQL injection policy:** all DB access via SQLAlchemy 2 ORM/Core **bound parameters** (no user-input string-built SQL). Tests probe `'; DROP TABLE users; --`, `' OR '1'='1`, `1; DELETE FROM bookings; --` on admin create/update → only 2xx/422, **row counts unchanged**, never 500. Panel keeps `esc()` on `innerHTML`; no `eval`. `/panel*` sends `X-Content-Type-Options: nosniff` + `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; frame-ancestors 'none'`.
- **No new public endpoints** for phase 14.

**Implemented:** ✅ phase 14 (salon-backend) — hash router + full-page barber/service editors in `backend/app/static/panel/` (edit/schedule modals removed; Back controls; `node --check app.js` OK); `_panel_file()` adds nosniff + CSP on `/panel*`; `backend/tests/test_admin_sqli.py` (8) + `test_panel.py` +3; static audit: no string-built SQL under `app/`. Backend pytest **150 passed**.

### Panel path routes: separate login page → dashboard page (CONTRACT_CHANGE applied 2026-09-24 — phase 15)

Owner: admin **login must be its own page**, and after sign-in the admin lands on a **different page** (dashboard), not a blended view.

- **URLs** (path routes under the existing SPA fallback `GET /panel/{path:path}` → `index.html`; no new APIs):
  | Path | Screen |
  |---|---|
  | `/panel` | If no valid session → **redirect** `/panel/login`; if session → **redirect** `/panel/dashboard` |
  | `/panel/login` | **Login page only** (no tabs/shell). Success → navigate to `/panel/dashboard` |
  | `/panel/dashboard` | Dashboard (aggregates). Post-login landing |
  | `/panel/barbers` | List |
  | `/panel/barbers/new`, `/panel/barbers/{id}/edit` | Full-page barber editors |
  | `/panel/services`, `/panel/services/new`, `/panel/services/{id}/edit` | Plan editors |
  | `/panel/bookings` | Bookings list |
- Replace hash routing (`#/…`) with **path routing** (`history.pushState` / `popstate` or link navigation). Server SPA fallback already serves `index.html` for unknown `/panel/*` file-less paths.
- Session: still `sessionStorage`; hitting a protected path while logged out → redirect `/panel/login` (client). After login always `/panel/dashboard`. **Log out** → `/panel/login`.
- Keep phase-14 security headers + SQLi posture unchanged.
- Tests: `/panel/login` and `/panel/dashboard` return 200 HTML; existing panel/SQLi suite stays green.

**Implemented:** ✅ phase 15 (salon-backend) — path router in `backend/app/static/panel/app.js` (`history.pushState` / `popstate`; `hashchange` + all `#/…` routes removed): `/panel` → client redirect to `/panel/login` or `/panel/dashboard` (the session lives in `sessionStorage`, so the server cannot choose — `GET /panel` still serves 200 HTML and the client redirects); `/panel/login` renders **login only** (shell/topbar/tabs stay hidden — no tabs on that page); sign-in always navigates to `/panel/dashboard`; unauthenticated access to any protected path (deep links included) and any 401/403 from `/admin/*` → `/panel/login`; **log out** → `/panel/login`; full-page editors at `/panel/barbers/new`, `/panel/barbers/{id}/edit`, `/panel/services/new`, `/panel/services/{id}/edit` and tab roots `/panel/{barbers,services,bookings,dashboard}` (Back/popstate re-render in place). Server unchanged: verified `GET /panel/login` + `GET /panel/dashboard` → **200 HTML** through the SPA fallback while `/panel/app.js` + `/panel/app.css` still resolve as real files, nosniff + CSP intact. Rendering fix in `panel/app.css`: `[hidden] { display: none !important; }` — author `display:flex` on `.login-view`/`.shell-view` previously outranked the UA `[hidden]` rule, so the admin shell rendered on the login page (and the login card stayed on the dashboard). Tests: `backend/tests/test_panel.py` +3 (path-route wiring, `/panel/login` + `/panel/dashboard` 200 HTML + hardening, `hidden`-wins CSS) → pytest **153 passed**; additionally verified end-to-end in headless Chrome (redirects, sign-in → dashboard, deep link `/panel/barbers/1/edit` after session restore, tab + Edit navigation, browser Back, logout, zero CSP violations).

### Panel app logo (CONTRACT_CHANGE applied 2026-09-24 — phase 16)

- Serve a static **app logo** for the admin panel: `GET /panel/logo.png` (or `.svg`) from `backend/app/static/panel/` — same-origin (allowed by CSP `img-src 'self'`).
- Show the logo on **`/panel/login`** (large, next to brand title) and in the **topbar** brand slot on authenticated pages (small). Match wine/gold brand; alt text = product name.
- Source: reuse/copy the mobile launcher icon (e.g. `mobile/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png`) or a dedicated SVG scissors mark — no new external CDN images.
- Optional favicon: `GET /panel/favicon.ico` or `<link rel="icon">` → same asset.
- Tests: logo asset returns 200 image/*; login HTML references it.

**Implemented:** ✅ phase 16 (salon-backend) — `backend/app/static/panel/logo.svg` (hand-drawn wine `#7A2E4A` / gold `#B08D57` / cream scissors roundel; the copied mobile launcher `logo.png` — `mipmap-xxxhdpi/ic_launcher.png` — is also served at `GET /panel/logo.png` but is the default Flutter blue mark, off-brand and soft at large size, so the SVG is the displayed asset) served same-origin by the existing `/panel/{path}` file branch → **200** `image/svg+xml` + `image/png` under nosniff + CSP `img-src 'self'`. `index.html`: favicon `<link rel="icon" href="/panel/logo.svg">`, large `img.login-logo` (104px) above the brand title on `/panel/login`, small `img.brand-logo` (34px) in the topbar brand slot on authenticated pages; `alt="Salon"` (product name). `app.css`: `.login-logo` / `.brand-logo` rules (kept inline-block — a flex parent dropped the text-node space and rendered “SalonAdmin”). Tests: `backend/tests/test_panel.py` +3 (logo asset 200 + `image/svg+xml`/`image/png` + brand colours + CSP, login HTML references the img/favicon with no external image hosts, CSS sizes) → pytest **156 passed**; headless-Chrome screenshots of `/panel/login` and the topbar verified visually.

## Frontend integration notes (Flutter)

- Base URL: `String.fromEnvironment("API_BASE_URL")`, default `http://10.0.2.2:8000` for Android emulator.
- **Public / internet API (CONTRACT_CHANGE applied 2026-09-25):** Cloudflare tunnel hostname **`https://salonapp.unonomercysound.online`** — use as `--dart-define=API_BASE_URL=https://salonapp.unonomercysound.online` for devices that are not on the emulator host loopback (real phones, demos). Admin panel on the same host: `https://salonapp.unonomercysound.online/panel/login`. Local stack remains `http://localhost:8000` / `http://10.0.2.2:8000`.
- Availability always refetched from API; local cache is UI hint only.
- Razorpay checkout opens with `key_id` + `razorpay_order_id` + `amount` from `POST /bookings` `payment` object; then call verify-payment.
- **Primary booking flow order (CONTRACT_CHANGE applied 2026-09-24):** splash → **barber list** (`/barbers`) → barber detail (**selection page**: service + wash add-on + date + slot) → checkout. Service catalog (`/services`) remains a tab / secondary entry (`?service_id=` preselect + optional path `/services` first step if user starts there); do not block barber-first entry on login.
- **Guest checkout:** if no session, show name + phone fields on checkout; `POST /bookings` without Bearer + `guest_name`/`guest_phone`; persist returned `access_token` for verify/cancel/list; do **not** force login dialog at Pay. Optional “Log in instead” link may still switch to registered account before create.

**Implemented:** ✅ phase 9 (salon-flutter) — splash/tab0 → `/barbers`; barber detail labeled selection page; guest card on checkout + `adoptSession` stores guest token; login wall removed. `flutter analyze` clean, 56/56 tests (mock API path).

  **Implemented:** ✅ phase 9 (salon-flutter) — barber-first routing (splash → `/barbers` shell tab 0; `/services` secondary tab with `?service_id=` preselect via `context.go`), barber detail as selection page (service + wash + date + slot), checkout guest name+phone when no token (client-validated: name ≤ 80, phone normalized to 10 digits after `+91`/`0`), `guest_name`/`guest_phone` omitted when a Bearer token exists, response `access_token`/`token_type`/`user` stored via `authTokenProvider` + `AuthController.adoptSession` before Razorpay opens, forced login dialog removed (“Log in instead” link only before create). Mock backend mirrors guest contract (`400 guest_identity_required`, find-or-create by phone, token on guest create). Verified: `flutter analyze` clean, 56/56 tests (guest payload widget test w/ recording repository + mock guest-contract unit tests); live API verify pending phase 8.
