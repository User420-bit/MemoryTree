# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Memory Tree is a private, password-protected web app for couples to record shared memories, photos, and milestones, visualized as a growing interactive tree. All UI text is in **German** (with an English translation available via `CoupleSettings.language`).

It is **multi-tenant by couple**: a `Couple` row is the tenant, two user accounts belong to it, and every memory, photo, place, milestone and settings row hangs off exactly one couple. There is **no open registration** — new accounts are created only by redeeming an invite code that you generate with `scripts/create_invite.py`. See "Tenancy" below; that boundary is the app's central security property.

The one exception to "no open access" is the **guest demo** (`DEMO_ENABLED`, off by default): `POST /auth/demo` gives an anonymous visitor a throwaway couple of their own, filled from [demo_data.py](demo_data.py). See "Guest demo" below.

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

# Create/reset the two accounts of a couple (interactive)
python scripts/create_users.py                 # couple #1
python scripts/create_users.py --couple-id 3

# Invite a new couple: creates Couple + CoupleSettings + code, prints the link
python scripts/create_invite.py --name "Anna & Ben"
python scripts/create_invite.py --couple-id 3   # extra code for an existing couple
python scripts/create_invite.py --list          # show open codes

# Load demo data (destructive — wipes that couple's memories/milestones/photos)
python scripts/seed_demo_data.py                # couple #1
python scripts/seed_demo_data.py --couple-id 3

# Guest-demo photos under static/demo/ (committed). They are AI-generated
# photos; import new ones from a folder of source files named like the entries
# in demo_data.py — crops to 3:2, 1200x800 JPEG, strips metadata, writes thumbs
python scripts/import_demo_photos.py <source-dir>

# Fallback: draws a procedural placeholder for any demo filename that has no
# image yet. Skips existing files; --force overwrites ALL real photos
python scripts/make_demo_images.py

# Alembic migration after a models.py change
alembic revision --autogenerate -m "description"
alembic upgrade head

# Rebuild the Tailwind stylesheet (only after adding NEW utility classes to a
# template or to static/js — the generated static/css/app.css is committed)
npx tailwindcss@3 -i static/css/tailwind-input.css -o static/css/app.css --minify

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

There is no pytest suite; the two test files are standalone scripts.

`tests/test_tenancy.py` is the regression guard for the couple isolation boundary — run it after touching query code, routers, auth, or the tenancy helpers. It builds a throwaway SQLite DB in a temp dir (never touches `data/`), runs `alembic upgrade head` against it, and drives the real ASGI stack via FastAPI's `TestClient`, checking that neither page output nor direct-ID access leaks across couples and that the invite flow behaves. Needs `httpx` (TestClient dependency, not in `requirements.txt`):

```bash
python tests/test_tenancy.py
```

The same script covers the guest demo: isolation between two guests, reset, logout cleanup, the sweep endpoint, and every path by which a guest could get a file stored. It pins `DEMO_ENABLED=false` and points `UPLOAD_DIR` at the temp dir, so a local `.env` can't change its starting state and it never writes to `data/uploads/`.

`tests/test_responsive.py` is a Playwright script that checks all pages for horizontal overflow/layout collisions across a viewport matrix — it requires a running server and real login credentials via env vars, it is not run via `pytest`:

```bash
export MT_TEST_BASE_URL=http://localhost:8000   # optional, this is the default
export MT_TEST_USERNAME=partner_a
export MT_TEST_PASSWORD=...                      # required, no default in source
python tests/test_responsive.py
```

## Architecture

- **Backend**: FastAPI (Python 3.11+), server-rendered with Jinja2 + Tailwind CSS (CDN) — not an SPA.
- **DB**: SQLAlchemy 2.0 ORM over SQLite (Pi/dev — WAL mode + `foreign_keys=ON` + busy_timeout PRAGMAs in [database.py](database.py)) or Neon Postgres (Vercel). **Alembic is the only source of schema truth** — nothing is created at app startup. `main.py` used to run `create_all` plus ad-hoc `ALTER TABLE` migrations in its lifespan; that was removed for Vercel (read-only FS, cold start per request) and replaced by `alembic upgrade head` + [scripts/seed.py](scripts/seed.py). A fresh DB is empty until you run both. `render_as_batch` is enabled only for SQLite.
- **Auth**: JWT (python-jose), bcrypt password hashing, access token (30 min) + refresh token (7 days), both in **HttpOnly cookies** (never localStorage). Silent renewal via `/auth/refresh`, handled by `TokenRefreshMiddleware`. Rate limiting on `/auth/login` and `/auth/register` (5 attempts / 5 min) against two counters — `ip:<addr>` and `user:<name>` — so that rotating usernames still hits the IP limit and distributed guessing against one account still hits the account limit. `X-Forwarded-For` is only trusted when `TRUST_PROXY_HEADERS=true`. That limiter keeps state **in-process**, so on Vercel it only applies within a warm instance — the real limit there is a Vercel Firewall rule (DEPLOYMENT.md 12.5).
- **Registration**: `GET`/`POST /auth/register` redeems an invite code. The code decides which couple the account joins; first redeemer becomes partner A, second partner B. Redemption is a conditional `UPDATE … WHERE used_count < max_uses` so two concurrent signups can't exceed the limit. All "code unusable" cases (unknown, expired, exhausted) return the *same* message — otherwise the page becomes an oracle for valid codes. The form is CSRF-protected like any other (it is deliberately **not** in the exempt list).
- **Middleware stack** ([middleware.py](middleware.py)), registered in `main.py` in this order (last `add_middleware` call = outermost = runs first): `RequestIDMiddleware` → `SecurityHeadersMiddleware` → `CSRFMiddleware` → `TokenRefreshMiddleware` → `TrustedHostMiddleware` (outermost, enforces `ALLOWED_HOSTS`).
- **CSRF**: double-submit cookie pattern; exempt routes are `/auth/login`, `/health`, and JSON-content-type requests. All state-changing HTML forms must include a `csrf_token` hidden input.
- **Uploads**: centralized in [uploads.py](uploads.py) — magic-byte content validation (not extension-based), EXIF stripping, re-encoding and thumbnailing via Pillow. Pillow always encodes into `BytesIO`; a storage layer in the same module then writes either to `data/uploads/` (disk) or to Vercel Blob. `process_upload(file, couple_id)` returns DB-ready **references**: a relative POSIX path on disk, an absolute `https://` Blob URL on Vercel. Files are filed under a per-couple prefix `uploads/c<couple_id>/` — that is tidiness and migratability, **not** access control; the real protection is the `couple_id` filtering in `tenancy.py`. `safe_remove()` accepts only a directory segment matching `c<digits>` from a stored reference, so a tampered DB row still can't escape `UPLOAD_DIR`; legacy references without a prefix keep working. Thumbnails are never stored in the DB — derive them with `thumbnail_ref()` (convention: `<dir>/thumbs/<name>_thumb.<ext>`, identical for both backends). The `/uploads` static mount only exists in disk mode and is **intentionally unauthenticated**; on Vercel, Blob URLs are public-but-unguessable, which is a bigger exposure since the app is on the public internet (DEPLOYMENT.md 12.6). Never reference uploaded images directly — always go through the `{{ filepath|upload_url }}` Jinja2 filter, which passes absolute URLs through and still handles the legacy `static/uploads/` format.
- **Config**: [config.py](config.py) is a `pydantic-settings` `Settings` object loaded from `.env` (on Vercel: from real env vars, there is no `.env`). It raises `RuntimeError` at import time in production (`APP_ENV=production`) if `SECRET_KEY` is missing/default/short, so anything importing `config` in a script needs a valid `.env` or `APP_ENV != production`. `use_secure_cookies` is forced on when serverless. `MAX_PINNED_MEMORIES` and `CATEGORY_CONFIG` (emoji/color per memory category, shared across Tree/Timeline/Gallery/Map) also live here.
- **Routers** ([routers/](routers/)): `auth`, `memories`, `photos`, `milestones`, `settings` — each included in [main.py](main.py). Page routes for `/`, `/tree`, `/timeline`, `/milestones`, `/gallery`, `/map` are defined directly in `main.py` rather than a router.
- **Data model** ([models.py](models.py)): `Couple` (the tenant), `Invite`, `User` (has `couple_id`), `Memory` (has `couple_id`; `is_favorite` = "pinned to tree", capped per couple at `MAX_PINNED_MEMORIES`; `is_hidden`; `tree_pos_top`/`tree_pos_left`; `sort_order`), `Photo`, `Milestone` (has `couple_id`), `Place`, `CoupleSettings` (one row per couple via a unique `couple_id`, holding `partner_since` — only ever mutated via `POST /settings`, never at DB-init time). `Photo` and `Place` deliberately have no `couple_id`; they inherit tenancy through `memory_id`.
- **Tenancy** ([tenancy.py](tenancy.py)) — **the security boundary**: every read and write of `Memory`, `Milestone`, `Photo`, `Place` and `CoupleSettings` must go through this module. `get_current_couple_id` is a FastAPI dependency (aliased as `CoupleId`) that resolves the couple from the logged-in `User` row, not from a JWT claim, so a stale token can't carry stale membership. Use `scoped_memories`/`visible_memories`/`scoped_milestones`/`scoped_photos`/`scoped_places`/`scoped_users` for lists and `get_owned_memory`/`get_owned_milestone`/`get_owned_photo` for single-ID access — the latter raise **404, never 403**, so a differing status code can't reveal that an ID exists in another couple. Page routes in `main.py` pass `current_user.couple_id` directly since they already depend on the user. A `db.query(Memory|Milestone|Photo|Place|CoupleSettings)` anywhere outside `tenancy.py` is a bug; grep for it after touching query code. Looking up `User` by username (login, uniqueness checks) is the one legitimate unscoped query — usernames are globally unique because login resolves them without a couple context.
- **Guest demo** ([tenancy.py](tenancy.py), [routers/auth.py](routers/auth.py), [demo_data.py](demo_data.py)): a guest is **not** a shared read-only account — each one gets their own `Couple` (`is_demo=True`, `expires_at`), so the existing `couple_id` filtering isolates guests from each other and from real couples with no extra code path. `create_demo_couple` builds it; `delete_demo_couple` is the only code that removes a whole tenant and **refuses anything that isn't a demo couple**. `POST /auth/demo` is both entry and "reset" (a guest calling it again gets a fresh couple, the old one is deleted); it is POST + CSRF on purpose so crawlers and link previews can't create couples, and it has its own `demo:<ip>` rate-limit counter so demo clicks never lock anyone out of login. Guests get session cookies (`set_auth_cookies(..., session_only=True)`, preserved by `/auth/refresh`), and `GET /auth/logout` deletes their couple. Guest accounts carry `hashed_password="!"` — not a bcrypt hash, so `verify_password` returns False (it catches bcrypt's `ValueError` for exactly this) and the account is unreachable via login. Growth is bounded three ways: TTL sweep on every demo entry, `MAX_DEMO_COUPLES` evicting the oldest, and `GET /internal/demo-sweep` for Vercel Cron, which answers 404 unless `Authorization: Bearer $CRON_SECRET` matches. `get_current_user` joined-loads `User.couple` because `base.html` reads `user.couple.is_demo` on every page — as a lazy load that would be a second round-trip per page view. Demo photos are static files (`static/demo/` — AI-generated, deliberately phone-snapshot-looking and without recognizable faces since "Lena & Max" don't exist; imported via `scripts/import_demo_photos.py`, with `scripts/make_demo_images.py` as a placeholder fallback that never overwrites without `--force`) referenced as `static/demo/<name>`: `upload_url` routes that prefix through `static_url` so the URL carries a content hash (without it the one-year `immutable` cache on `/static/` pins a replaced photo in every browser that saw the old one), and `safe_remove` won't touch it, so a guest deleting a photo only removes their own DB row, never the shared file.
- **Frontend patterns**: no D3 (removed) — the tree view is SVG-based; map view uses Leaflet.js. **Tailwind is a prebuilt, committed stylesheet** (`static/css/app.css`, Tailwind 3.x via `tailwind.config.js`), not the `cdn.tailwindcss.com` JIT script — that script recompiled the CSS in the browser on every page load. Adding a utility class that no template used before means rebuilding the CSS (see Commands) and committing the result; `tailwind.config.js` scans `templates/**` *and* `static/js/**` because `pin-animation.js`/`timeline-sort.js` add classes at runtime. Reference static assets via `{{ static_url('js/foo.js') }}` ([template_engine.py](template_engine.py)), never a bare `/static/...` path: it appends a content hash, which is what makes the one-year `immutable` `Cache-Control` on `/static/` safe. That header is set **twice on purpose** — in `SecurityHeadersMiddleware` for the deployments where Starlette's `StaticFiles` actually serves (Pi/Docker/local), and in the `headers` block of [vercel.json](vercel.json) because on Vercel `/static/` is served by the edge and never enters the function at all (verified: its `x-vercel-id` carries no function segment). Changing one without the other silently fixes caching on only one target. Inline-style values driven by DB data (positions, colors) are passed as `data-*` attributes and applied via a small JS helper (`applyDataStyles()`) rather than interpolated into `style=` with Jinja2, to avoid template-driven CSS injection surface.
- **i18n**: [i18n/](i18n/) provides `t()`/`category_label()`, wired into Jinja2 globals in [template_engine.py](template_engine.py) and used across all templates (`de`/`en`). `LanguageMiddleware` ([middleware.py](middleware.py)) puts the language of the *logged-in user's* couple into `request.state.lang`; it runs before the auth dependency and therefore resolves the username from the access-token cookie itself (`auth.username_from_access_token`), falling back to `de` when anonymous. The result is cached in a `lang` cookie so the common path costs **no** DB query — the lookup used to open a second `SessionLocal()` on every single request, which under `NullPool` meant a second Neon connection per page view. The cookie only ever selects `de`/`en` (anything else is discarded), `POST /settings` refreshes it via `set_language_cookie`, and `clear_auth_cookies` drops it on logout so a shared browser doesn't inherit the previous user's language. Adding a new user-facing string means adding a key to `i18n/`, not hardcoding it.

## Security constraints (non-negotiable, see [Copilot Security Instructions .md](Copilot%20Security%20Instructions%20.md))

- Never store JWTs anywhere JS-readable; cookies stay HttpOnly (+ Secure/SameSite per `settings.use_secure_cookies`).
- Never render untrusted content with Jinja2 `|safe`; sanitize any rich text with an allowlist.
- SQLAlchemy ORM / parameterized queries only — never string-built SQL.
- Validate uploads by content (magic bytes), never by extension alone; never trust user-supplied filenames/paths; never write uploads into `static/`.
- Never load a tenant-owned model without a `couple_id` filter — always go through [tenancy.py](tenancy.py). Unauthorized single-record access returns 404, never 403.
- Guests must never get a file stored or change login data. A new route that accepts an upload or edits credentials needs `Depends(require_non_demo)` (403) — or, for a form guests should still be able to submit, an `is_demo_user()` check that drops the attachment. Add the path to `pruefe_gast_sperren` in `tests/test_tenancy.py`, which asserts on the outcome (no `Photo` row outside `static/demo/`, no new file), not just the status code.
- Don't log secrets, passwords, raw cookies, or JWTs — and don't log usernames or invite codes on failed login/registration (enables enumeration via logs).
- Don't weaken CSP/security headers/cookie flags without calling out the tradeoff explicitly.
- Keep resource usage Pi-Zero-2-W-appropriate: SQLite stays the DB, 1 Gunicorn worker (`gunicorn.conf.py`) by default, no heavy added services.

## Conventions

- Type hints on all Python functions.
- DB sessions and current-user auth go through FastAPI `Depends()`.
- Upload handling always goes through [uploads.py](uploads.py), never inlined in a router.
- Any `models.py` change needs a matching Alembic migration (`alembic revision --autogenerate`).
- A new tenant-owned table also needs a line in `tenancy.delete_demo_couple` (FK order matters — nothing cascades from `couples` except `couple_settings` and `invites`), otherwise deleting a guest's couple fails on the foreign key.
- A new tenant-owned table needs a `couple_id` FK plus index, a scoping helper in [tenancy.py](tenancy.py), and a migration that backfills before setting `NOT NULL`.
