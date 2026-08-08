# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Memory Tree is a private, password-protected web app for exactly two partners (a couple) to record shared memories, photos, and milestones, visualized as a growing interactive tree. There is **no multi-tenant or registration system** — only two fixed accounts (`partner_a` / `partner_b`). All UI text is in **German**.

There are **two supported deployment targets**, and the code must keep working on both:

- **Raspberry Pi Zero 2 W** (ARM64, 512MB RAM) via Docker — SQLite + local uploads + Gunicorn. Keep code low-memory and low-complexity.
- **Vercel** (serverless) — Neon Postgres + Vercel Blob, one ASGI function. Read-only filesystem, no persistent process.

The switch is by environment variable, not by branch: `DATABASE_URL` selects the DB (`database.py` normalizes Postgres URLs onto the psycopg 3 driver and uses `NullPool` when serverless), and `BLOB_READ_WRITE_TOKEN` selects the upload backend (`settings.storage_backend` → `"blob"` or `"disk"`). `settings.is_serverless` reflects Vercel's `VERCEL` env var. See DEPLOYMENT.md section 12.

## Commands

```bash
# Run the dev server (creates .venv, installs deps, starts uvicorn with --reload)
./start.sh

# Stop it
./stop.sh
# or Ctrl+C in the terminal running it

# Manual run without the helper script
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Create the schema — REQUIRED on a fresh database, nothing happens at app startup
alembic upgrade head

# Seed base data: CoupleSettings singleton + (only if APP_ENV!=production and
# DEBUG=true) the partner_a/partner_b dev accounts
python scripts/seed.py

# Create/reset production user accounts (interactive)
python scripts/create_users.py

# Load demo data (destructive — wipes existing memories/milestones/photos)
python scripts/seed_demo_data.py

# Alembic migration after a models.py change
alembic revision --autogenerate -m "description"
alembic upgrade head

# Docker (local dev — Windows-friendly)
docker compose -f docker-compose.yml up --build
# compose.yaml (no -f docker-compose.yml) is the Raspberry Pi production variant with Caddy

# Vercel
npx vercel          # preview deploy
npx vercel --prod   # production
python scripts/migrate_to_vercel.py --dry-run   # one-off SQLite+disk → Postgres+Blob
```

**On exFAT volumes** (this repo lives on one): macOS writes `._*` AppleDouble
shadow files. Alembic tries to import `alembic/versions/._*.py` as migrations and
dies with "source code string cannot contain null bytes". Fix:
`find . -name "._*" -not -path "./.venv/*" -not -path "./.git/*" -delete`

Dev login (only seeded when `DEBUG=true`): `partner_a` / `partner_b`, password `test1234`.

### Tests

There is no pytest suite. `tests/test_responsive.py` is a Playwright script that checks all pages for horizontal overflow/layout collisions across a viewport matrix — it requires a running server and real login credentials via env vars, it is not run via `pytest`:

```bash
export MT_TEST_BASE_URL=http://localhost:8000   # optional, this is the default
export MT_TEST_USERNAME=partner_a
export MT_TEST_PASSWORD=...                      # required, no default in source
python tests/test_responsive.py
```

## Architecture

- **Backend**: FastAPI (Python 3.11+), server-rendered with Jinja2 + Tailwind CSS (CDN) — not an SPA.
- **DB**: SQLAlchemy 2.0 ORM over SQLite (Pi/dev — WAL mode + `foreign_keys=ON` + busy_timeout PRAGMAs in [database.py](database.py)) or Neon Postgres (Vercel). **Alembic is the only source of schema truth** — nothing is created at app startup. `main.py` used to run `create_all` plus ad-hoc `ALTER TABLE` migrations in its lifespan; that was removed for Vercel (read-only FS, cold start per request) and replaced by `alembic upgrade head` + [scripts/seed.py](scripts/seed.py). A fresh DB is empty until you run both. `render_as_batch` is enabled only for SQLite.
- **Auth**: JWT (python-jose), bcrypt password hashing, access token (30 min) + refresh token (7 days), both in **HttpOnly cookies** (never localStorage). Silent renewal via `/auth/refresh`, handled by `TokenRefreshMiddleware`. Rate limiting on `/auth/login` (5 attempts / 5 min, IP-based — only trusts `X-Forwarded-For` when `TRUST_PROXY_HEADERS=true`). That limiter keeps state **in-process**, so on Vercel it only applies within a warm instance — the real limit there is a Vercel Firewall rule (DEPLOYMENT.md 12.5).
- **Middleware stack** ([middleware.py](middleware.py)), registered in `main.py` in this order (last `add_middleware` call = outermost = runs first): `RequestIDMiddleware` → `SecurityHeadersMiddleware` → `CSRFMiddleware` → `TokenRefreshMiddleware` → `TrustedHostMiddleware` (outermost, enforces `ALLOWED_HOSTS`).
- **CSRF**: double-submit cookie pattern; exempt routes are `/auth/login`, `/health`, and JSON-content-type requests. All state-changing HTML forms must include a `csrf_token` hidden input.
- **Uploads**: centralized in [uploads.py](uploads.py) — magic-byte content validation (not extension-based), EXIF stripping, re-encoding and thumbnailing via Pillow. Pillow always encodes into `BytesIO`; a storage layer in the same module then writes either to `data/uploads/` (disk) or to Vercel Blob. `process_upload()` returns DB-ready **references**: a relative POSIX path on disk, an absolute `https://` Blob URL on Vercel. Thumbnails are never stored in the DB — derive them with `thumbnail_ref()` (convention: `<dir>/thumbs/<name>_thumb.<ext>`, identical for both backends). The `/uploads` static mount only exists in disk mode and is **intentionally unauthenticated**; on Vercel, Blob URLs are public-but-unguessable, which is a bigger exposure since the app is on the public internet (DEPLOYMENT.md 12.6). Never reference uploaded images directly — always go through the `{{ filepath|upload_url }}` Jinja2 filter, which passes absolute URLs through and still handles the legacy `static/uploads/` format.
- **Config**: [config.py](config.py) is a `pydantic-settings` `Settings` object loaded from `.env` (on Vercel: from real env vars, there is no `.env`). It raises `RuntimeError` at import time in production (`APP_ENV=production`) if `SECRET_KEY` is missing/default/short, so anything importing `config` in a script needs a valid `.env` or `APP_ENV != production`. `use_secure_cookies` is forced on when serverless. `MAX_PINNED_MEMORIES` and `CATEGORY_CONFIG` (emoji/color per memory category, shared across Tree/Timeline/Gallery/Map) also live here.
- **Routers** ([routers/](routers/)): `auth`, `memories`, `photos`, `milestones`, `settings` — each included in [main.py](main.py). Page routes for `/`, `/tree`, `/timeline`, `/milestones`, `/gallery`, `/map` are defined directly in `main.py` rather than a router.
- **Data model** ([models.py](models.py)): `User`, `Memory` (has `is_favorite` = "pinned to tree", capped server-side at `MAX_PINNED_MEMORIES`; `is_hidden`; `tree_pos_top`/`tree_pos_left`; `sort_order`), `Photo`, `Milestone`, `Place`, `CoupleSettings` (singleton row holding `partner_since` — only ever mutated via `POST /settings`, never at DB-init time).
- **Frontend patterns**: no D3 (removed) — the tree view is SVG-based; map view uses Leaflet.js. Inline-style values driven by DB data (positions, colors) are passed as `data-*` attributes and applied via a small JS helper (`applyDataStyles()`) rather than interpolated into `style=` with Jinja2, to avoid template-driven CSS injection surface.
- **i18n**: [i18n/](i18n/) exists but the UI standard today is hardcoded German strings in templates/Python — check current usage before assuming a translation layer is wired up everywhere.

## Security constraints (non-negotiable, see [Copilot Security Instructions .md](Copilot%20Security%20Instructions%20.md))

- Never store JWTs anywhere JS-readable; cookies stay HttpOnly (+ Secure/SameSite per `settings.use_secure_cookies`).
- Never render untrusted content with Jinja2 `|safe`; sanitize any rich text with an allowlist.
- SQLAlchemy ORM / parameterized queries only — never string-built SQL.
- Validate uploads by content (magic bytes), never by extension alone; never trust user-supplied filenames/paths; never write uploads into `static/`.
- Don't log secrets, passwords, raw cookies, or JWTs.
- Don't weaken CSP/security headers/cookie flags without calling out the tradeoff explicitly.
- Keep resource usage Pi-Zero-2-W-appropriate: SQLite stays the DB, 1 Gunicorn worker (`gunicorn.conf.py`) by default, no heavy added services.

## Conventions

- Type hints on all Python functions.
- DB sessions and current-user auth go through FastAPI `Depends()`.
- Upload handling always goes through [uploads.py](uploads.py), never inlined in a router.
- Any `models.py` change needs a matching Alembic migration (`alembic revision --autogenerate`).
