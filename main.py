# Memory Tree — FastAPI Hauptanwendung

import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, List

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import extract, func, inspect as sa_inspect, text
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password
from config import CATEGORY_CONFIG, settings
from database import Base, SessionLocal, engine, get_db
from middleware import (
    CSRFMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TokenRefreshMiddleware,
)
from models import CoupleSettings, Memory, Milestone, Photo, Place, User

from routers.auth import router as auth_router
from routers.memories import router as memories_router
from routers.photos import router as photos_router
from routers.milestones import router as milestones_router
from routers.settings import router as settings_router


# ── Jubiläums-Helper ──────────────────────────────────────────────────────

def _next_anniversary(partner_since: date, today: date) -> tuple[date, int, int]:
    """Berechnet das nächste Jubiläumsdatum (Schaltjahr-sicher).

    Gibt (datum, jahre, tage_bis) zurück. Wenn der Jahrestag heute oder in
    Zukunft liegt, wird dieses Jahr verwendet, sonst das nächste.
    """
    def _safe_date(year: int, month: int, day: int) -> date:
        try:
            return date(year, month, day)
        except ValueError:
            # Schaltjahr-Sonderfall: 29. Feb → 28. Feb
            return date(year, month, day - 1)

    anniv_this_year = _safe_date(today.year, partner_since.month, partner_since.day)
    if anniv_this_year < today:
        anniv_next = _safe_date(today.year + 1, partner_since.month, partner_since.day)
    else:
        anniv_next = anniv_this_year
    tage_bis = (anniv_next - today).days
    jahre = anniv_next.year - partner_since.year
    return anniv_next, jahre, tage_bis


# ── Structured Logging ───────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """JSON-Logformat für strukturiertes Logging via docker logs."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Extra-Felder hinzufügen (Request-ID etc.)
        for key in ("request_id", "method", "path", "status", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                log_data[key] = val
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


def _setup_logging() -> None:
    """Logging konfigurieren: JSON auf stdout in Production, lesbar in Dev."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Vorhandene Handler entfernen
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if settings.is_production:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
        ))
    root.addHandler(handler)

    # Externe Libraries leiser stellen
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


_setup_logging()
logger = logging.getLogger(__name__)


# ── Lifespan: Startup / Shutdown ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: DB initialisieren, Verzeichnisse erstellen. Shutdown: aufräumen."""
    # Startup
    _init_database()
    _ensure_directories()
    logger.info("Memory Tree gestartet (env=%s)", settings.APP_ENV)
    yield
    # Shutdown
    logger.info("Memory Tree wird beendet")


def _ensure_directories() -> None:
    """Upload- und Daten-Verzeichnisse erstellen."""
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.UPLOAD_DIR, "thumbs").mkdir(parents=True, exist_ok=True)
    # DB-Verzeichnis aus DATABASE_URL extrahieren
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def _init_database() -> None:
    """DB-Tabellen erstellen und bei Bedarf Spalten nachrüsten."""
    Base.metadata.create_all(bind=engine)
    logger.info("Datenbank initialisiert")

    # Pragmatische SQLite-Migration: Spalten nachrüsten
    inspector = sa_inspect(engine)
    try:
        columns = [c["name"] for c in inspector.get_columns("memories")]
    except Exception:
        columns = []

    if columns and "is_favorite" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE memories ADD COLUMN is_favorite BOOLEAN DEFAULT 0 NOT NULL"))
        logger.info("Spalte 'is_favorite' zu memories hinzugefügt")
    if columns and "tree_pos_top" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE memories ADD COLUMN tree_pos_top VARCHAR(10)"))
            conn.execute(text("ALTER TABLE memories ADD COLUMN tree_pos_left VARCHAR(10)"))
        logger.info("Spalten 'tree_pos_top/left' zu memories hinzugefügt")
    if columns and "sort_order" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE memories ADD COLUMN sort_order INTEGER DEFAULT 0 NOT NULL"))
        logger.info("Spalte 'sort_order' zu memories hinzugefügt")

    # Initiale Benutzer nur in Development erstellen.
    # Doppel-Gate: zusätzlich DEBUG=True, damit ein fehlkonfiguriertes
    # APP_ENV allein nicht reicht, um Dev-Passwörter zu aktivieren.
    if not settings.is_production and settings.DEBUG:
        logger.warning(
            "DEV-MODUS: Erstelle Standard-Benutzer partner_a / partner_b "
            "mit bekanntem Passwort. NIEMALS in Production!"
        )
        _create_dev_users()

    # Paar-Einstellungen (Singleton)
    # SCHUTZLOGIK: partner_since wird hier NICHT gesetzt.
    # Es darf ausschließlich über POST /settings geändert werden.
    db: Session = SessionLocal()
    try:
        cs: CoupleSettings | None = db.query(CoupleSettings).first()
        if cs is None:
            cs = CoupleSettings(
                partner_a_name="Partner A",
                partner_b_name="Partner B",
            )
            db.add(cs)
            db.commit()
            logger.info("Paar-Einstellungen erstellt (ohne Datum — wird über Einstellungen gesetzt)")
    finally:
        db.close()


def _create_dev_users() -> None:
    """Test-Benutzer nur in der Entwicklungsumgebung erstellen."""
    db: Session = SessionLocal()
    try:
        existing_a = db.query(User).filter(User.username == "partner_a").first()
        existing_b = db.query(User).filter(User.username == "partner_b").first()

        # SCHUTZLOGIK: Dev-User werden OHNE partner_since erstellt.
        # Das Beziehungsdatum wird ausschließlich über couple_settings verwaltet.
        if not existing_a:
            db.add(User(
                name="Partner A",
                username="partner_a",
                hashed_password=hash_password("test1234"),
            ))
        if not existing_b:
            db.add(User(
                name="Partner B",
                username="partner_b",
                hashed_password=hash_password("test1234"),
            ))
        if not existing_a or not existing_b:
            db.commit()
            logger.info("Dev-Benutzer erstellt")
    finally:
        db.close()


# ── FastAPI App erstellen ────────────────────────────────────────────────────

app = FastAPI(
    title="Memory Tree",
    description="Privates digitales Erinnerungsbuch für Paare",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

# ── Middleware (Reihenfolge: letzter add = äußerste Schicht = zuerst ausgeführt) ──

app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(TokenRefreshMiddleware)

# ── Statische Dateien & Templates ───────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")

# Uploads separat mounten (data/uploads → /uploads/)
_upload_path = Path(settings.UPLOAD_DIR)
_upload_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_upload_path)), name="uploads")

from template_engine import templates

# ── Router einbinden ────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(memories_router)
app.include_router(photos_router)
app.include_router(milestones_router)
app.include_router(settings_router)


# ── Health Endpoint ──────────────────────────────────────────────────────────

@app.get("/health")
def health_check() -> dict[str, str]:
    """Einfacher Health-Check für Docker und Monitoring."""
    return {"status": "ok"}


# ── Exception-Handler: 401 → Login-Redirect ─────────────────────────────────

@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Bei 401 automatisch zur Login-Seite weiterleiten."""
    if exc.status_code == 401:
        return RedirectResponse(url="/auth/login", status_code=303)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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

    # Länder: distinct countries aus places, Fallback auf distinct locations
    laender_count: int = (
        db.query(func.count(func.distinct(Place.country)))
        .filter(Place.country.isnot(None), Place.country != "")
        .scalar()
        or 0
    )
    if laender_count == 0:
        laender_count = (
            db.query(func.count(func.distinct(Memory.location)))
            .filter(Memory.location.isnot(None), Memory.location != "")
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

    # Partnername ermitteln (der jeweils andere)
    partner: User | None = db.query(User).filter(User.id != current_user.id).first()
    partner_name: str | None = partner.name if partner else None

    # Nächstes Jubiläum berechnen
    naechstes_jubilaeum: str | None = None
    if partner_since:
        anniv_next, jahre, tage_bis = _next_anniversary(partner_since, today)
        naechstes_jubilaeum = (
            f"{jahre}. Jahrestag in {tage_bis} Tagen "
            f"({anniv_next.strftime('%d.%m.%Y')})"
        )

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
            "partner_name": partner_name,
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
    category_config = CATEGORY_CONFIG

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
        db.query(Memory).order_by(Memory.date.desc(), Memory.sort_order.asc()).all()
    )

    # Anzahl gepinnter Erinnerungen
    total_pinned: int = (
        db.query(func.count(Memory.id))
        .filter(Memory.is_favorite == True)
        .scalar() or 0
    )

    # Kategorie-Konfig
    category_config = CATEGORY_CONFIG

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
        anniv_next, jahre, tage_bis = _next_anniversary(partner_since, today)
        naechstes_jubilaeum = {
            "jahre": jahre,
            "tage_bis": tage_bis,
            "datum": anniv_next.strftime("%d.%m.%Y"),
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
    category_config = CATEGORY_CONFIG

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
    category_config = CATEGORY_CONFIG

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
