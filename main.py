# Memory Tree — FastAPI Hauptanwendung

import logging
from datetime import date, datetime
from typing import Annotated, List

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import extract, func, inspect as sa_inspect, text
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password
from database import Base, SessionLocal, engine, get_db
from models import CoupleSettings, Memory, Milestone, Photo, Place, User

from routers.auth import router as auth_router
from routers.memories import router as memories_router
from routers.photos import router as photos_router
from routers.milestones import router as milestones_router
from routers.settings import router as settings_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── FastAPI App erstellen ────────────────────────────────────────────────────

app = FastAPI(
    title="Memory Tree",
    description="Privates digitales Erinnerungsbuch für Paare",
    version="1.0.0",
)

# ── CORS Middleware ──────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Statische Dateien & Templates ───────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = datetime.now

# ── Router einbinden ────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(memories_router)
app.include_router(photos_router)
app.include_router(milestones_router)
app.include_router(settings_router)


# ── Exception-Handler: 401 → Login-Redirect ─────────────────────────────────

@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Bei 401 automatisch zur Login-Seite weiterleiten."""
    if exc.status_code == 401:
        return RedirectResponse(url="/auth/login", status_code=303)
    # Alle anderen HTTP-Fehler normal weitergeben
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# ── Startup-Event ────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    """Datenbank-Tabellen erstellen und Test-Benutzer anlegen."""
    Base.metadata.create_all(bind=engine)
    logger.info("Datenbank initialisiert")

    # Pragmatische SQLite-Migration: is_favorite Spalte nachrüsten
    inspector = sa_inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("memories")]
    if "is_favorite" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE memories ADD COLUMN is_favorite BOOLEAN DEFAULT 0 NOT NULL"))
        logger.info("Spalte 'is_favorite' zu memories hinzugefügt")
    if "tree_pos_top" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE memories ADD COLUMN tree_pos_top VARCHAR(10)"))
            conn.execute(text("ALTER TABLE memories ADD COLUMN tree_pos_left VARCHAR(10)"))
        logger.info("Spalten 'tree_pos_top/left' zu memories hinzugefügt")

    db: Session = SessionLocal()
    try:
        existing_a: User | None = db.query(User).filter(User.username == "partner_a").first()
        existing_b: User | None = db.query(User).filter(User.username == "partner_b").first()

        if not existing_a:
            user_a = User(
                name="Partner A",
                username="partner_a",
                hashed_password=hash_password("test1234"),
                partner_since=date(2024, 1, 1),
            )
            db.add(user_a)

        if not existing_b:
            user_b = User(
                name="Partner B",
                username="partner_b",
                hashed_password=hash_password("test1234"),
                partner_since=date(2024, 1, 1),
            )
            db.add(user_b)

        if not existing_a or not existing_b:
            db.commit()
            logger.info("Test-Benutzer erstellt")

        # Paar-Einstellungen anlegen (Singleton)
        cs: CoupleSettings | None = db.query(CoupleSettings).first()
        if cs is None:
            cs = CoupleSettings(
                partner_a_name="Partner A",
                partner_b_name="Partner B",
                partner_since=date(2024, 1, 1),
            )
            db.add(cs)
            db.commit()
            logger.info("Paar-Einstellungen erstellt")
    finally:
        db.close()


# ── Dashboard-Route ──────────────────────────────────────────────────────────

def _get_current_user_or_redirect(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Wrapper um get_current_user — leitet bei fehlendem Token zur Login-Seite."""
    try:
        return get_current_user(request, db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert")


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    current_user: Annotated[User, Depends(_get_current_user_or_redirect)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Dashboard-Seite mit Übersichtsstatistiken anzeigen."""
    today: date = date.today()

    # Statistiken abfragen
    erinnerungen_count: int = db.query(func.count(Memory.id)).scalar() or 0
    fotos_count: int = db.query(func.count(Photo.id)).scalar() or 0
    laender_count: int = (
        db.query(func.count(func.distinct(Place.country)))
        .filter(Place.country.isnot(None))
        .scalar()
        or 0
    )

    # Paar-Einstellungen laden
    cs: CoupleSettings | None = db.query(CoupleSettings).first()
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    # Tage zusammen berechnen
    tage_zusammen: int = 0
    if partner_since:
        tage_zusammen = (today - partner_since).days

    # Anzahl gepinnter Favoriten (für "Zum Baum"-Karte)
    favoriten_count: int = (
        db.query(func.count(Memory.id))
        .filter(Memory.is_favorite == True)
        .scalar() or 0
    )

    # Letzte 5 Erinnerungen (alle)
    letzte_erinnerungen: List[Memory] = (
        db.query(Memory).order_by(Memory.date.desc()).limit(5).all()
    )

    # Nächstes Jubiläum berechnen
    naechstes_jubilaeum: str | None = None
    if partner_since:
        ps: date = partner_since
        try:
            anniversary_this_year = date(today.year, ps.month, ps.day)
        except ValueError:
            # Schaltjahr-Sonderfall: 29. Feb → 28. Feb
            anniversary_this_year = date(today.year, ps.month, ps.day - 1)
        if anniversary_this_year < today:
            try:
                anniversary_next = date(today.year + 1, ps.month, ps.day)
            except ValueError:
                anniversary_next = date(today.year + 1, ps.month, ps.day - 1)
        else:
            anniversary_next = anniversary_this_year
        tage_bis: int = (anniversary_next - today).days
        jahre: int = anniversary_next.year - ps.year
        naechstes_jubilaeum = f"{jahre}. Jahrestag in {tage_bis} Tagen ({anniversary_next.strftime('%d.%m.%Y')})"

    # "An diesem Tag"-Erinnerungen (gleicher Monat + Tag)
    an_diesem_tag: List[Memory] = (
        db.query(Memory)
        .filter(
            extract("month", Memory.date) == today.month,
            extract("day", Memory.date) == today.day,
        )
        .all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "erinnerungen_count": erinnerungen_count,
            "fotos_count": fotos_count,
            "laender_count": laender_count,
            "tage_zusammen": tage_zusammen,
            "letzte_erinnerungen": letzte_erinnerungen,
            "favoriten_count": favoriten_count,
            "naechstes_jubilaeum": naechstes_jubilaeum,
            "an_diesem_tag": an_diesem_tag,
        },
    )


@app.get("/tree", response_class=HTMLResponse)
def tree_page(
    request: Request,
    current_user: Annotated[User, Depends(_get_current_user_or_redirect)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Memory-Tree-Seite anzeigen (nur Baum + gepinnte Favoriten)."""
    cs: CoupleSettings | None = db.query(CoupleSettings).first()
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    favorites: list[Memory] = (
        db.query(Memory)
        .filter(Memory.is_favorite == True)
        .order_by(Memory.date.desc())
        .limit(8)
        .all()
    )

    # Feste Ankerpunkte für bis zu 8 Favoriten am Baum
    anchor_positions: list[dict[str, str]] = [
        {"top": "18%", "left": "28%"},
        {"top": "14%", "left": "48%"},
        {"top": "20%", "left": "68%"},
        {"top": "28%", "left": "22%"},
        {"top": "24%", "left": "42%"},
        {"top": "30%", "left": "62%"},
        {"top": "35%", "left": "32%"},
        {"top": "32%", "left": "55%"},
    ]
    pinned: list[tuple[Memory, dict[str, str]]] = []
    for i, mem in enumerate(favorites[:8]):
        if mem.tree_pos_top and mem.tree_pos_left:
            pos = {"top": mem.tree_pos_top, "left": mem.tree_pos_left}
        else:
            pos = anchor_positions[i]
        pinned.append((mem, pos))

    # Kategorie-Konfig für Emoji-Fallback bei Fotos
    category_config: dict[str, dict[str, str]] = {
        "Urlaub": {"emoji": "\U0001f3d6\ufe0f", "color": "#0891b2"},
        "Meilenstein": {"emoji": "\U0001f31f", "color": "#d97706"},
        "Feier": {"emoji": "\U0001f389", "color": "#7c3aed"},
        "Alltag": {"emoji": "\U0001f4f8", "color": "#16a34a"},
        "Abenteuer": {"emoji": "\U0001f32f", "color": "#ea580c"},
        "Besonderes": {"emoji": "\u2764\ufe0f", "color": "#e11d48"},
    }

    partner_since_display: str = ""
    if partner_since:
        partner_since_display = partner_since.strftime("%d.%m.%Y")

    return templates.TemplateResponse(
        "tree.html",
        {
            "request": request,
            "user": current_user,
            "partner_since": partner_since_display,
            "pinned_memories": pinned,
            "category_config": category_config,
        },
    )


# ── Timeline-Route ───────────────────────────────────────────────────────────

@app.get("/timeline", response_class=HTMLResponse)
def timeline_page(
    request: Request,
    current_user: Annotated[User, Depends(_get_current_user_or_redirect)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Zeitstrahl-Seite: chronologische Ansicht aller Erinnerungen."""
    today: date = date.today()

    # Paar-Einstellungen laden
    cs: CoupleSettings | None = db.query(CoupleSettings).first()
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    tage_zusammen: int = 0
    partner_since_display: str = ""
    if partner_since:
        tage_zusammen = (today - partner_since).days
        partner_since_display = partner_since.strftime("%d.%m.%Y")

    # Alle Erinnerungen chronologisch absteigend
    all_memories: list[Memory] = (
        db.query(Memory).order_by(Memory.date.desc()).all()
    )

    # Anzahl gepinnter Erinnerungen
    total_pinned: int = (
        db.query(func.count(Memory.id))
        .filter(Memory.is_favorite == True)
        .scalar() or 0
    )

    # Kategorie-Konfig
    category_config: dict[str, dict[str, str]] = {
        "Urlaub": {"emoji": "\U0001f3d6\ufe0f", "color": "#0891b2"},
        "Meilenstein": {"emoji": "\U0001f31f", "color": "#d97706"},
        "Feier": {"emoji": "\U0001f389", "color": "#7c3aed"},
        "Alltag": {"emoji": "\U0001f4f8", "color": "#16a34a"},
        "Abenteuer": {"emoji": "\U0001f32f", "color": "#ea580c"},
        "Besonderes": {"emoji": "\u2764\ufe0f", "color": "#e11d48"},
    }

    return templates.TemplateResponse(
        "timeline.html",
        {
            "request": request,
            "user": current_user,
            "memories": all_memories,
            "category_config": category_config,
            "tage_zusammen": tage_zusammen,
            "partner_since": partner_since_display,
            "total_pinned": total_pinned,
        },
    )


# ── Meilensteine-Seite ──────────────────────────────────────────────────────

@app.get("/milestones", response_class=HTMLResponse)
def milestones_page(
    request: Request,
    current_user: Annotated[User, Depends(_get_current_user_or_redirect)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Meilensteine-Seite: vertikale Timeline besonderer Ereignisse."""
    today: date = date.today()

    milestones: list[Milestone] = (
        db.query(Milestone).order_by(Milestone.date.desc()).all()
    )

    # Paar-Einstellungen laden
    cs: CoupleSettings | None = db.query(CoupleSettings).first()
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    # Nächstes Jubiläum berechnen
    naechstes_jubilaeum: dict | None = None
    if partner_since:
        ps = partner_since
        try:
            anniversary_this_year = date(today.year, ps.month, ps.day)
        except ValueError:
            anniversary_this_year = date(today.year, ps.month, ps.day - 1)
        if anniversary_this_year < today:
            try:
                anniversary_next = date(today.year + 1, ps.month, ps.day)
            except ValueError:
                anniversary_next = date(today.year + 1, ps.month, ps.day - 1)
        else:
            anniversary_next = anniversary_this_year
        tage_bis = (anniversary_next - today).days
        jahre = anniversary_next.year - ps.year
        naechstes_jubilaeum = {
            "jahre": jahre,
            "tage_bis": tage_bis,
            "datum": anniversary_next.strftime("%d.%m.%Y"),
        }

    return templates.TemplateResponse(
        "milestones.html",
        {
            "request": request,
            "user": current_user,
            "milestones": milestones,
            "today": today,
            "naechstes_jubilaeum": naechstes_jubilaeum,
        },
    )


# ── Galerie-Seite ───────────────────────────────────────────────────────────

@app.get("/gallery", response_class=HTMLResponse)
def gallery_page(
    request: Request,
    current_user: Annotated[User, Depends(_get_current_user_or_redirect)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Galerie: Grid aller Fotos mit Filtern und Lightbox."""
    all_photos: list[Photo] = (
        db.query(Photo)
        .join(Memory, Photo.memory_id == Memory.id)
        .order_by(Memory.date.desc(), Photo.uploaded_at.desc())
        .all()
    )

    # Kategorie-Konfig
    category_config: dict[str, dict[str, str]] = {
        "Urlaub": {"emoji": "\U0001f3d6\ufe0f", "color": "#0891b2"},
        "Meilenstein": {"emoji": "\U0001f31f", "color": "#d97706"},
        "Feier": {"emoji": "\U0001f389", "color": "#7c3aed"},
        "Alltag": {"emoji": "\U0001f4f8", "color": "#16a34a"},
        "Abenteuer": {"emoji": "\U0001f32f", "color": "#ea580c"},
        "Besonderes": {"emoji": "\u2764\ufe0f", "color": "#e11d48"},
    }

    # Verfügbare Jahre extrahieren
    years: list[int] = sorted(
        {p.memory.date.year for p in all_photos if p.memory},
        reverse=True,
    )

    return templates.TemplateResponse(
        "gallery.html",
        {
            "request": request,
            "user": current_user,
            "photos": all_photos,
            "category_config": category_config,
            "years": years,
        },
    )


# ── Karten-Seite ────────────────────────────────────────────────────────────

@app.get("/map", response_class=HTMLResponse)
def map_page(
    request: Request,
    current_user: Annotated[User, Depends(_get_current_user_or_redirect)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Karten-Seite: interaktive Weltkarte aller besuchten Orte."""
    # Erinnerungen mit Koordinaten laden
    geo_memories: list[Memory] = (
        db.query(Memory)
        .filter(Memory.lat.isnot(None), Memory.lng.isnot(None))
        .order_by(Memory.date.desc())
        .all()
    )

    # Statistiken
    orte_count: int = len(geo_memories)
    laender_set: set[str] = set()
    for m in geo_memories:
        for p in m.places:
            if p.country:
                laender_set.add(p.country)
    laender_count: int = len(laender_set)

    # Kategorie-Konfig
    category_config: dict[str, dict[str, str]] = {
        "Urlaub": {"emoji": "\U0001f3d6\ufe0f", "color": "#0891b2"},
        "Meilenstein": {"emoji": "\U0001f31f", "color": "#d97706"},
        "Feier": {"emoji": "\U0001f389", "color": "#7c3aed"},
        "Alltag": {"emoji": "\U0001f4f8", "color": "#16a34a"},
        "Abenteuer": {"emoji": "\U0001f32f", "color": "#ea580c"},
        "Besonderes": {"emoji": "\u2764\ufe0f", "color": "#e11d48"},
    }

    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "user": current_user,
            "memories": geo_memories,
            "category_config": category_config,
            "orte_count": orte_count,
            "laender_count": laender_count,
        },
    )


# ── Einstiegspunkt ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
