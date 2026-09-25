# Salon — Appointment App

FastAPI + Flutter salon booking (India — ₹, Asia/Kolkata, 15-min slots) with **50% online advance** via Razorpay, guest checkout, and an owner **admin panel**.

## Stack

| Piece | Tech |
|---|---|
| API | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, JWT |
| Mobile | Flutter, Riverpod, dio, razorpay_flutter |
| Admin panel | Static SPA at `/panel` (same origin as API) |
| Payments | Razorpay (mock mode for local/demo) |

## Quick start (Docker)

```bash
cp deploy/.env.example .env   # set POSTGRES_PASSWORD, JWT_SECRET, ADMIN_*
docker compose up -d --build
curl -f http://localhost:8000/health
```

- **API:** http://localhost:8000  
- **Admin login:** http://localhost:8000/panel/login  
- **Swagger:** http://localhost:8000/docs  

Seed admin comes from `ADMIN_PHONE` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` in `.env`.

## Public demo hostname

Cloudflare tunnel (local stack): **`https://salonapp.unonomercysound.online`**

- Panel: `https://salonapp.unonomercysound.online/panel/login`
- Health: `https://salonapp.unonomercysound.online/health`

## Flutter

```bash
cd mobile
flutter pub get
flutter run \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
  --dart-define=USE_MOCK_API=false \
  --dart-define=PAYMENT_MOCK=true
```

For a real device / internet API use `API_BASE_URL=https://salonapp.unonomercysound.online`.

## Tests

```bash
cd backend && pip install -r requirements.txt && pytest   # 156 passed
cd mobile && flutter analyze && flutter test
```

## Docs

- `docs/CONTRACT.md` — API source of truth  
- `docs/PHASES.md` — build status board  
- `docs/shop-guide.pdf` — printable shop guide  
- `deploy/NOTES.md` — VPS / Render / HTTPS / Razorpay webhook  

## iOS (CI)

GitHub Actions workflow builds an IPA on `macos` runners — see `.github/workflows/`. Signing requires Apple secrets in the repo settings (see workflow comments).
