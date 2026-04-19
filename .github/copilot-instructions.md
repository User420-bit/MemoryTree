# Memory Tree — Copilot Instructions

## Project Overview

Memory Tree is a private, password-protected web app for two partners (a couple). It allows them to capture shared memories — vacations, milestones, photos, and experiences — visualized as a growing interactive tree.

**Language**: German (Deutschsprachige Oberfläche — all UI text in German)

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Templating**: Jinja2
- **Styling**: Tailwind CSS 3.x (CDN)
- **JS**: Vanilla JS, Leaflet.js 1.9.x (CDN) — D3.js removed from tree view
- **Database**: SQLite via SQLAlchemy 2.0+ ORM (WAL mode, PRAGMAs in database.py)
- **Auth**: JWT (python-jose 3.3+), bcrypt 12 rounds, access tokens (30min) + refresh tokens (7 days) in HttpOnly cookies
- **Image processing**: Pillow 10+ (EXIF stripping, magic byte validation, thumbnails)
- **Server**: Gunicorn 22+ with UvicornWorker (1 worker for Pi constraints)
- **Migrations**: Alembic with render_as_batch=True (SQLite)
- **Deployment**: Docker multi-stage build + Caddy reverse proxy (compose.yaml)
- **Target hardware**: Raspberry Pi Zero 2 W (ARM64, 512MB RAM)

## Project Structure

```
memory-tree/
├── main.py                  # FastAPI entry point, lifespan, middleware stack
├── models.py                # SQLAlchemy data models
├── database.py              # DB connection, session, SQLite PRAGMAs
├── auth.py                  # JWT (access+refresh), bcrypt, rate limiting
├── config.py                # Pydantic Settings from .env
├── middleware.py             # SecurityHeaders, CSRF, RequestID, TokenRefresh
├── uploads.py               # Centralized upload: magic bytes, EXIF, thumbnails
├── schemas.py               # Pydantic validation with Field constraints
├── gunicorn.conf.py         # Gunicorn config (1 worker, UvicornWorker)
├── Dockerfile               # Multi-stage build, ARM64 compatible
├── compose.yaml             # app + caddy services
├── Caddyfile                # Reverse proxy, static serving, caching
├── .dockerignore
├── routers/
│   ├── memories.py          # CRUD memories
│   ├── milestones.py        # Milestones
│   ├── photos.py            # Photo upload & management
│   ├── settings.py          # Couple settings, avatar upload
│   └── auth.py              # Login/Logout/Refresh routes
├── static/
│   ├── css/tailwind.css
│   ├── js/
│   │   ├── tree.js          # Tree page: minimal applyDataStyles helper
│   │   ├── timeline.js      # Timeline: category filters + pin toggle
│   │   ├── pin-animation.js # Unpin fall animation
│   │   └── gallery.js       # Gallery & Lightbox
│   └── img/                 # App assets
├── data/
│   └── uploads/             # Uploaded images (outside static/, served via /uploads mount)
│       └── thumbs/          # Auto-generated thumbnails
├── templates/
│   ├── base.html            # Base layout (nav, footer, idle-logout)
│   ├── dashboard.html
│   ├── tree.html
│   ├── timeline.html
│   ├── milestones.html
│   ├── map.html
│   ├── gallery.html
│   ├── memory_detail.html
│   ├── memory_form.html
│   ├── settings.html
│   └── login.html
├── scripts/
│   ├── backup.sh            # SQLite online backup + rotation
│   └── create_users.py      # Production user creation
├── alembic/                 # DB migrations
├── requirements.txt
├── .env / .env.example
├── DEPLOYMENT.md
└── README.md
```

## Key Architecture Decisions

- **Two-user system only**: Partner A and Partner B, no registration flow needed
- **Server-rendered pages**: Jinja2 templates with Tailwind, not an SPA
- **JWT stored in HTTP-only cookies**: not localStorage, with Secure flag in production
- **Access + refresh tokens**: 30min access, 7 days refresh, silent renewal via `/auth/refresh`
- **SQLite**: single file DB, WAL mode, foreign_keys=ON, busy_timeout=5000ms
- **File uploads**: saved to `data/uploads/` (outside static/), served via `/uploads` mount; magic byte validation, EXIF stripping, re-encoding via Pillow
- **All API routes except `/auth/login` and `/health` require valid JWT**
- **CSRF protection**: Double-submit cookie pattern via CSRFMiddleware; exempt: /auth/login, /health, JSON content-type
- **Security headers**: CSP, X-Frame-Options DENY, X-Content-Type-Options nosniff, HSTS in production
- **Rate limiting**: IP-based on /auth/login (5 attempts per 5 min window)
- **Tree page = meditative display only**: SVG tree + max 8 pinned favorites, no card grid or filtering
- **Timeline page = main memories hub**: chronological cards, category filters, pin-to-tree toggle (max 8)
- **Pin-to-tree**: `is_favorite` field = "pinned to tree", max 8 enforced server-side
- **Data-attribute pattern**: Use `data-bg-color`, `data-pos-top`, etc. applied via JS `applyDataStyles()` to avoid Jinja2 in inline styles
- **Upload URL filter**: `{{ filepath|upload_url }}` Jinja2 filter converts DB paths to URLs (supports old `static/uploads/` and new `data/uploads/` formats)
- **Idle logout**: 30 min inactivity timeout via JS in base.html

## Database Tables

- `users`: id, name, username, password_hash, avatar_path, partner_since
- `memories`: id, title, date, description, location, lat, lng, mood, category, is_favorite, tree_pos_top, tree_pos_left, sort_order, created_by, created_at
- `photos`: id, memory_id, filepath, caption, uploaded_at
- `milestones`: id, title, date, icon, description, is_anniversary
- `places`: id, memory_id, name, country, lat, lng

## Coding Conventions

- Use type hints on all Python functions
- All UI strings in German
- Use FastAPI dependency injection for DB sessions and auth
- Structured logging at key boundaries
- Route handlers in `routers/` directory, imported in `main.py`
- Configuration via `.env` file loaded through `config.py`
- Upload processing via centralized `uploads.py` module (never inline)
- Image references in templates must use `|upload_url` filter
- POST forms must include `csrf_token` hidden input
- Alembic migrations on all model changes (`alembic revision --autogenerate`)

## PRD Reference

The full PRD is at [docs/PRD.md](../docs/PRD.md).
