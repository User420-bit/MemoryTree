# Memory Tree — FastAPI Hauptanwendung

import hmac
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
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user
from config import CATEGORY_CONFIG, MAX_PINNED_MEMORIES, settings
from geo_utils import country_from_coords
from database import get_db
from middleware import (
    CSRFMiddleware,
    LanguageMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TokenRefreshMiddleware,
)
from models import Memory, Milestone, Photo, User
from tenancy import (
    get_couple_settings,
    scoped_milestones,
    scoped_photos,
    scoped_users,
    visible_memories,
    sweep_expired_demo_couples,
)

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
    """Startup / Shutdown.

    Bewusst OHNE Schema-Initialisierung: das Schema wird ausschließlich über
    Alembic verwaltet (``alembic upgrade head``), Benutzer und Paar-
    Einstellungen über ``scripts/seed.py``. Auf Vercel startet pro Cold Start
    eine neue Function-Instanz — DDL an dieser Stelle würde bei jedem Start
    laufen und sich mit parallelen Instanzen ins Gehege kommen.
    """
    # Startup
    _ensure_directories()
    logger.info(
        "Memory Tree gestartet (env=%s, storage=%s)",
        settings.APP_ENV,
        settings.storage_backend,
    )
    yield
    # Shutdown
    logger.info("Memory Tree wird beendet")


def _ensure_directories() -> None:
    """Upload- und Daten-Verzeichnisse erstellen (nur im lokalen Betrieb).

    Auf Vercel ist das Dateisystem read-only und Uploads liegen im Blob-Store —
    dort gibt es nichts anzulegen.
    """
    if settings.is_serverless or settings.storage_backend == "blob":
        return

    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.UPLOAD_DIR, "thumbs").mkdir(parents=True, exist_ok=True)
    # DB-Verzeichnis aus DATABASE_URL extrahieren
    if settings.DATABASE_URL.startswith("sqlite:///"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


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
app.add_middleware(LanguageMiddleware)
# Äußerste Schicht: Host-Header-Validierung. Setzt ALLOWED_HOSTS aus .env
# durch (vorher deklariert, aber nie enforced). Stärkt zugleich den
# Origin/Referer-CSRF-Check, der gegen den Host-Header vergleicht.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)

# ── Statische Dateien & Templates ───────────────────────────────────────────

# Pfade am Projektverzeichnis ankern statt am CWD — auf Vercel ist das
# Arbeitsverzeichnis der Function nicht garantiert das Repo-Root.
BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Uploads separat mounten (data/uploads → /uploads/) — nur im Disk-Betrieb.
# BEWUSSTE ENTSCHEIDUNG (Audit 2026-07): kein Auth auf diesem Mount.
# Schutz: nicht erratbare UUID-Dateinamen + Betrieb ausschließlich im
# privaten LAN/Tailscale.
# Im Blob-Betrieb (Vercel) liefert Vercel Blob die Bilder direkt aus; auch dort
# sind die URLs öffentlich-aber-unerratbar. Da die App dann im öffentlichen
# Internet steht, ist das ein bewusst akzeptierter Tradeoff (siehe DEPLOYMENT.md).
if settings.storage_backend == "disk" and not settings.is_serverless:
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


# ── Aufräumlauf für Demo-Paare (Vercel Cron) ────────────────────────────────

# Obergrenze pro Aufruf: 10 Läufe à 20 Paare. Ein Cron-Aufruf soll nicht ins
# Function-Timeout laufen; was übrig bleibt, nimmt der nächste Lauf mit.
_SWEEP_MAX_BATCHES = 10


@app.get("/internal/demo-sweep", include_in_schema=False)
def demo_sweep(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    """Abgelaufene Demo-Paare löschen — aufgerufen vom Vercel Cron.

    Der Demo-Einstieg räumt bei jedem neuen Gast selbst auf; dieser Endpunkt
    deckt nur den Fall ab, dass länger niemand kommt und die letzten Paare
    sonst liegen blieben.

    Jede Ablehnung ist 404, nicht 401/403: der Endpunkt soll sich von einem
    nicht existierenden Pfad nicht unterscheiden lassen. (401 würde außerdem
    vom Exception-Handler unten in einen Login-Redirect verwandelt.)
    """
    secret = settings.CRON_SECRET
    supplied = request.headers.get("authorization", "")
    if (
        not settings.DEMO_ENABLED
        or not secret
        or not hmac.compare_digest(supplied.encode(), f"Bearer {secret}".encode())
    ):
        raise HTTPException(status_code=404)

    deleted = 0
    for _ in range(_SWEEP_MAX_BATCHES):
        batch = sweep_expired_demo_couples(db)
        deleted += batch
        if batch == 0:
            break
    if deleted:
        logger.info("Demo-Sweep: %d Paare gelöscht", deleted)
    return {"deleted": deleted}


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
    couple_id: int = current_user.couple_id

    # Diese Seite bestand früher aus acht Einzelabfragen (zwei Counts, Places,
    # Geo-Memories, Favoriten-Count, letzte fünf, "an diesem Tag", Settings).
    # Gegen SQLite war das gratis, gegen Neon ist jede davon ein Round-Trip
    # über Netz. Da ein Paar realistisch nur einige hundert Erinnerungen hat,
    # holen wir sie einmal samt Fotos und Orten und aggregieren in Python.
    alle_erinnerungen: List[Memory] = (
        visible_memories(db, couple_id)
        .options(selectinload(Memory.photos), selectinload(Memory.places))
        .order_by(Memory.date.desc())
        .all()
    )

    erinnerungen_count: int = len(alle_erinnerungen)
    fotos_count: int = sum(len(m.photos) for m in alle_erinnerungen)
    favoriten_count: int = sum(1 for m in alle_erinnerungen if m.is_favorite)

    # Länder ermitteln — Reihenfolge der Quellen:
    #   1) explizit gesetztes Place.country (falls vorhanden)
    #   2) Ableitung aus Memory.lat/lng via Bounding-Box (geo_utils)
    # Damit zählen Erinnerungen in derselben Stadt/Region nicht als
    # mehrere "Länder" — wie es die reine location-String-Zählung tat.
    distinct_countries: set[str] = set()
    for m in alle_erinnerungen:
        for p in m.places:
            if p.country:
                distinct_countries.add(p.country)
        if m.lat is not None and m.lng is not None:
            country = country_from_coords(m.lat, m.lng)
            if country:
                distinct_countries.add(country)

    laender_count: int = len(distinct_countries)

    # Letzte 5 Erinnerungen (Liste ist bereits absteigend nach Datum sortiert)
    letzte_erinnerungen: List[Memory] = alle_erinnerungen[:5]

    # "An diesem Tag"-Erinnerungen (gleicher Monat + Tag)
    an_diesem_tag: List[Memory] = [
        m for m in alle_erinnerungen
        if m.date.month == today.month and m.date.day == today.day
    ]

    # Paar-Einstellungen laden
    cs = get_couple_settings(db, couple_id)
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    # Tage zusammen berechnen
    tage_zusammen: int = 0
    if partner_since:
        tage_zusammen = (today - partner_since).days

    # Partnername ermitteln (der jeweils andere im selben Paar)
    partner: User | None = (
        scoped_users(db, couple_id).filter(User.id != current_user.id).first()
    )
    partner_name: str | None = partner.name if partner else None

    # Nächstes Jubiläum berechnen
    naechstes_jubilaeum: str | None = None
    if partner_since:
        anniv_next, jahre, tage_bis = _next_anniversary(partner_since, today)
        naechstes_jubilaeum = (
            f"{jahre}. Jahrestag in {tage_bis} Tagen "
            f"({anniv_next.strftime('%d.%m.%Y')})"
        )

    return templates.TemplateResponse(
        request,
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
    couple_id: int = current_user.couple_id
    cs = get_couple_settings(db, couple_id)
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    # selectinload: tree.html rendert je Favorit memory.photos[0]
    favorites: list[Memory] = (
        visible_memories(db, couple_id)
        .options(selectinload(Memory.photos))
        .filter(Memory.is_favorite == True)
        .order_by(Memory.date.desc())
        .limit(MAX_PINNED_MEMORIES)
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
    for i, mem in enumerate(favorites[:MAX_PINNED_MEMORIES]):
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
        request,
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
    couple_id: int = current_user.couple_id

    # Paar-Einstellungen laden
    cs = get_couple_settings(db, couple_id)
    partner_since: date | None = cs.partner_since if cs else current_user.partner_since

    tage_zusammen: int = 0
    partner_since_display: str = ""
    if partner_since:
        tage_zusammen = (today - partner_since).days
        partner_since_display = partner_since.strftime("%d.%m.%Y")

    # Alle sichtbaren Erinnerungen chronologisch absteigend
    # selectinload: timeline.html rendert je Eintrag memory.photos[0]
    all_memories: list[Memory] = (
        visible_memories(db, couple_id)
        .options(selectinload(Memory.photos))
        .order_by(Memory.date.desc(), Memory.sort_order.asc())
        .all()
    )

    # Anzahl gepinnter Erinnerungen — aus der bereits geladenen Liste,
    # spart einen zusätzlichen Round-Trip
    total_pinned: int = sum(1 for m in all_memories if m.is_favorite)

    # Kategorie-Konfig
    category_config = CATEGORY_CONFIG

    return templates.TemplateResponse(
        request,
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
    couple_id: int = current_user.couple_id

    milestones = (
        scoped_milestones(db, couple_id).order_by(Milestone.date.desc()).all()
    )

    # Paar-Einstellungen laden
    cs = get_couple_settings(db, couple_id)
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
        request,
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
    # selectinload: gallery.html und die Jahres-Liste unten greifen je Foto
    # auf p.memory zu — sonst eine Extra-Query pro Foto.
    all_photos: list[Photo] = (
        scoped_photos(db, current_user.couple_id)
        .options(selectinload(Photo.memory))
        .filter(Memory.is_hidden == False)
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
        request,
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
    # Erinnerungen mit Koordinaten laden (ohne versteckte)
    # selectinload: die Länder-Schleife unten liest m.places, das Template
    # zusätzlich m.photos[0] für die Popup-Vorschau.
    geo_memories: list[Memory] = (
        visible_memories(db, current_user.couple_id)
        .options(selectinload(Memory.places), selectinload(Memory.photos))
        .filter(Memory.lat.isnot(None), Memory.lng.isnot(None))
        .order_by(Memory.date.desc())
        .all()
    )

    # Statistiken — Länder primär aus Place.country, sonst aus Bounding-Box
    orte_count: int = len(geo_memories)
    laender_set: set[str] = set()
    for m in geo_memories:
        added_from_places = False
        for p in m.places:
            if p.country:
                laender_set.add(p.country)
                added_from_places = True
        if not added_from_places:
            country = country_from_coords(m.lat, m.lng)
            if country:
                laender_set.add(country)
    laender_count: int = len(laender_set)

    # Kategorie-Konfig
    category_config = CATEGORY_CONFIG

    return templates.TemplateResponse(
        request,
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
