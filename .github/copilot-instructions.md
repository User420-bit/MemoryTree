# Memory Tree — Copilot Instructions

## Project Overview

Memory Tree is a private, password-protected web app for two partners (a couple). It allows them to capture shared memories — vacations, milestones, photos, and experiences — visualized as a growing interactive tree.

**Language**: German (Deutschsprachige Oberfläche — all UI text in German)

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Templating**: Jinja2
- **Styling**: Tailwind CSS 3.x (CDN)
- **JS**: Vanilla JS, Leaflet.js 1.9.x (CDN) — D3.js removed from tree view
- **Database**: SQLite via SQLAlchemy 2.0+ ORM
- **Auth**: JWT (python-jose 3.3+), bcrypt (passlib 1.7+)
- **Image processing**: Pillow 10+
- **Server**: Uvicorn 0.29+

## Project Structure

```
memory-tree/
├── main.py                  # FastAPI entry point
├── models.py                # SQLAlchemy data models
├── database.py              # DB connection & session
├── auth.py                  # JWT auth & middleware
├── config.py                # App configuration
├── routers/
│   ├── memories.py          # CRUD memories
│   ├── milestones.py        # Milestones
│   ├── photos.py            # Photo upload & management
│   ├── map.py               # Geodata & places
│   └── auth.py              # Login/Logout routes
├── static/
│   ├── uploads/             # Uploaded images
│   ├── css/tailwind.css
│   ├── js/
│   │   ├── tree.js          # Tree page: minimal applyDataStyles helper
│   │   ├── timeline.js      # Timeline: category filters + pin toggle
│   │   ├── map.js           # Leaflet.js map
│   │   └── gallery.js       # Gallery & Lightbox
│   └── img/                 # App assets
├── templates/
│   ├── base.html            # Base layout (shared nav, footer, head)
│   ├── dashboard.html
│   ├── tree.html
│   ├── timeline.html
│   ├── milestones.html
│   ├── map.html
│   ├── gallery.html
│   ├── memory_detail.html
│   ├── memory_form.html
│   └── settings.html
├── requirements.txt
├── .env
└── README.md
```

## Key Architecture Decisions

- **Two-user system only**: Partner A and Partner B, no registration flow needed
- **Server-rendered pages**: Jinja2 templates with Tailwind, not an SPA
- **JWT stored in HTTP-only cookies**: not localStorage
- **SQLite**: single file DB, no external DB server needed
- **File uploads**: saved to `static/uploads/`, images auto-resized to max 1920px
- **All API routes except `/auth/login` require valid JWT**
- **Tree page = meditative display only**: SVG tree + max 8 pinned favorites, no card grid or filtering
- **Timeline page = main memories hub**: chronological cards, category filters, pin-to-tree toggle (max 8)
- **Pin-to-tree**: `is_favorite` field = "pinned to tree", max 8 enforced server-side
- **Data-attribute pattern**: Use `data-bg-color`, `data-pos-top`, etc. applied via JS `applyDataStyles()` to avoid Jinja2 in inline styles

## Database Tables

- `users`: id, name, username, password_hash, avatar_path, partner_since
- `memories`: id, title, date, description, location, lat, lng, mood, category, created_by
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

## PRD Reference

The full PRD is at [docs/PRD.md](../docs/PRD.md).
