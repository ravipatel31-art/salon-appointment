# Deploy notes (salon-integration — phase 7)

Artifacts in this repo:

| Path | Purpose |
|---|---|
| `docker-compose.yml` (repo root) | Postgres 16 + FastAPI api (`alembic upgrade head` → `python -m app.seed` → uvicorn), healthchecks, hold-expiry worker env |
| `deploy/Dockerfile.api` | API image (build context = **repo root**) |
| `deploy/.env.example` | Full env template — copy to `.env`, fill, **never commit** |
| `deploy/NOTES.md` | This file |

No real secrets belong in the repo — only placeholders. Keep the live `.env`
out of git: `backend/.gitignore` already ignores `backend/.env`; make sure the
**root** `.env` (read by compose) is likewise ignored before any commit.

---

## 1) Single VPS + HTTPS (recommended for India Razorpay webhooks)

Prerequisites: a VPS (Ubuntu 22.04+), Docker Engine + Compose plugin, a
domain (`api.example.com`) with an **A record** → VPS IP, ports 80/443 open.

```bash
git clone <repo-url> saloan && cd saloan
cp deploy/.env.example .env
$EDITOR .env   # POSTGRES_PASSWORD, JWT_SECRET, ADMIN_*, RAZORPAY_*

docker compose up -d --build
curl -f http://localhost:8000/health        # {"status":"ok"}
docker compose logs -f api                  # migrate + seed + serve logs
```

### TLS with Caddy (2-minute setup, auto Let's Encrypt)

```bash
sudo apt-get install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
api.example.com {
    reverse_proxy 127.0.0.1:8000
}
EOF
sudo systemctl reload caddy
curl -f https://api.example.com/health
```

nginx alternative: `proxy_pass http://127.0.0.1:8000;` + certbot certificates.
**Razorpay webhooks require a public HTTPS URL** — plain `http://IP:8000` will
not be accepted by the Razorpay dashboard.

### Razorpay dashboard

1. Settings → API Keys → generate `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`.
2. Settings → Webhooks → **Add New Webhook**
   - URL: `https://api.example.com/webhooks/razorpay`
   - Secret: same value as `RAZORPAY_WEBHOOK_SECRET` in `.env`
   - Active events: `payment.captured`, `payment.failed`, `refund.processed`
3. Restart: `docker compose up -d` (env changes require recreate).

### Upgrades / ops

```bash
git pull
docker compose up -d --build      # re-runs migrations + idempotent seed on start
docker compose ps                 # api/db healthy?
docker compose logs --tail=100 api
docker compose down               # stop (volume salon_pgdata is kept)
```

- DB data lives in the named volume `salon_pgdata` — back it up with
  `docker compose exec db pg_dump -U salon salon > backup.sql`.
- In-process hold sweeper: `HOLD_EXPIRY_WORKER=1` (default), interval
  `HOLD_EXPIRY_INTERVAL_SECONDS=30`. Webhook/create-order paths also sweep
  on read, so short API downtime never wedges slots.

---

## 2) Render (PaaS, zero-ops TLS)

1. Push the repo to GitHub/GitLab.
2. Render → **New → Web Service** → pick the repo.
   - Runtime: **Docker**
   - Dockerfile path: `deploy/Dockerfile.api` (build context = repo root —
     matches this repo's layout).
   - Health Check Path: `/health`
3. Render → **New → PostgreSQL** (or use an external PG). Copy its
   **External Database URL** into env var `DATABASE_URL`.
4. Environment (same names as `deploy/.env.example`): `JWT_SECRET`,
   `ADMIN_PHONE`/`ADMIN_PASSWORD`/`ADMIN_EMAIL`, `RAZORPAY_*`,
   `ENVIRONMENT=production`. Leave `DATABASE_URL` to Render's Postgres URL as
   provided (it is already `postgresql://…` — Render's web service accepts it;
   if the driver prefix is missing, use `postgresql+psycopg://…`).
5. Deploy — the image CMD runs `alembic upgrade head` + seed + uvicorn on
   `$PORT` (Render injects `PORT`; compose sets it to 8000).
6. Webhook URL becomes `https://<service>.onrender.com/webhooks/razorpay` —
   add it in Razorpay with secret = `RAZORPAY_WEBHOOK_SECRET`.

Notes:
- onrender.com provides HTTPS automatically; custom domains also get TLS.
- Free/starter instances sleep — expect a cold start on first request; paid
  instances keep the hold-expiry worker's 30s cadence meaningful.

---

## 3) Flutter production build (Play Store)

`API_BASE_URL` and `USE_MOCK_API` are **compile-time** `--dart-define`s
(`mobile/lib/core/config/api_config.dart`) — they must be baked into every
release artifact. Defaults target the Android emulator
(`http://10.0.2.2:8000`) + mock API, so a Play Store build **must** override.

```bash
cd mobile

# Release App Bundle for Play Console (HTTPS backend):
flutter build appbundle \
  --dart-define=USE_MOCK_API=false \
  --dart-define=API_BASE_URL=https://api.example.com
# → build/app/outputs/bundle/release/app-release.aab

# QA APK against the same backend:
flutter build apk --release \
  --dart-define=USE_MOCK_API=false \
  --dart-define=API_BASE_URL=https://api.example.com
```

Play Console upload steps (high level):
1. Create the app + track (internal testing first).
2. Signing: generate an upload keystore, place `android/key.properties` +
   `signingConfigs.release` per Flutter's official docs (mobile/ is owned by
   salon-flutter — signing config lives there).
3. Upload the `app-release.aab` produced by the command above.
4. Re-build whenever the API host changes — dart-defines are **not** runtime
   config.

Verify before uploading:
```bash
flutter analyze && flutter test
flutter build appbundle \
  --dart-define=USE_MOCK_API=false \
  --dart-define=API_BASE_URL=https://api.example.com
```

---

## 4) Secrets checklist

- [ ] `.env` exists only on the host / Render dashboard — never in git.
- [ ] `JWT_SECRET` and `POSTGRES_PASSWORD` are long random values.
- [ ] `ADMIN_PASSWORD` is strong (seed admin gets one account).
- [ ] Razorpay **live** keys in prod (`rzp_live_…`); test keys only on staging.
- [ ] `RAZORPAY_WEBHOOK_SECRET` matches the Razorpay dashboard webhook secret.
- [ ] `RAZORPAY_MOCK=0` anywhere real money can flow.
