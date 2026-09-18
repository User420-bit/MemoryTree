#!/usr/bin/env python3
"""Mandantentrennung end-to-end prüfen.

Die Trennung zwischen Paaren ist rein anwendungsseitig (kein Row-Level-Security
in der Datenbank), deshalb ist eine vergessene ``couple_id``-Filterung sofort
ein Datenleck. Dieses Skript baut eine Wegwerf-Datenbank mit zwei Paaren auf,
meldet sich als beide an und prüft, dass keine Seite und kein Direktzugriff
fremde Daten preisgibt. Zusätzlich wird der Einladungs-/Registrierungsfluss
abgedeckt.

Wie tests/test_responsive.py ist das ein eigenständiges Skript, kein pytest:

    python3 tests/test_tenancy.py

Es braucht keinen laufenden Server (FastAPI-TestClient) und fasst die echte
Datenbank der App nicht an — die Test-DB liegt in einem temporären Verzeichnis.
Benötigt zusätzlich ``httpx`` (Abhängigkeit des TestClients).

Exit-Code 0 = alle Prüfungen bestanden, 1 = mindestens ein Fehler.
"""

import datetime
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Muss VOR dem Import von config/database gesetzt sein — beide lesen die
# Umgebung beim Import und legen die Engine sofort an.
_TMPDIR = tempfile.TemporaryDirectory(prefix="memorytree-tenancy-")
_DB_PATH = Path(_TMPDIR.name) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ALLOWED_HOSTS", "*")
os.environ.setdefault("LOG_LEVEL", "ERROR")
# Fest statt setdefault: eine lokale .env mit DEMO_ENABLED=true darf den
# Ausgangszustand nicht kippen — pruefe_gastzugang() schaltet selbst um.
os.environ["DEMO_ENABLED"] = "false"
# Uploads der Gegenprobe landen im Temp-Verzeichnis, nie in data/uploads/.
os.environ["UPLOAD_DIR"] = str(Path(_TMPDIR.name) / "uploads")
os.environ["BLOB_READ_WRITE_TOKEN"] = ""

subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=PROJECT_ROOT, check=True, capture_output=True,
)

from fastapi.testclient import TestClient  # noqa: E402

from auth import hash_password  # noqa: E402
from database import SessionLocal  # noqa: E402
from main import app  # noqa: E402
from models import (  # noqa: E402
    Couple, CoupleSettings, Invite, Memory, Milestone, Photo, Place, User,
)

# ── Prüfprotokoll ───────────────────────────────────────────────────────────

_fails: list[str] = []
_checks = 0


def check(name: str, bedingung: object, detail: str = "") -> None:
    """Eine Prüfung festhalten. Fehler werden gesammelt, nicht sofort geworfen."""
    global _checks
    _checks += 1
    if not bedingung:
        _fails.append(f"{name}: {detail}" if detail else name)


# ── Testdaten ───────────────────────────────────────────────────────────────

FREMDE_MARKER = ["GEHEIM-Paar Zwei", "MEILENSTEIN-Paar Zwei", "Stadt2", "Land2"]
EIGENER_MARKER = "GEHEIM-Paar Eins"
SEITEN = [
    "/", "/tree", "/timeline", "/milestones", "/gallery", "/map",
    "/settings", "/memories", "/memories/locations", "/api/milestones",
]


def baue_testdaten() -> None:
    """Zwei Paare mit je eigenen Erinnerungen, Fotos, Orten, Meilensteinen."""
    db = SessionLocal()
    try:
        for idx, (paarname, username, sprache) in enumerate(
            [("Paar Eins", "alice", "de"), ("Paar Zwei", "bob", "en")], start=1
        ):
            couple = Couple(name=paarname)
            db.add(couple)
            db.flush()
            db.add(CoupleSettings(
                couple_id=couple.id, partner_a_name=f"A{idx}",
                partner_b_name=f"B{idx}", language=sprache,
                partner_since=datetime.date(2020, 1, 1),
            ))
            user = User(couple_id=couple.id, name=f"A{idx}", username=username,
                        hashed_password=hash_password("test1234"))
            db.add(user)
            db.flush()
            memory = Memory(
                couple_id=couple.id, title=f"GEHEIM-{paarname}",
                date=datetime.date(2023, 5, idx), location=f"Stadt{idx}",
                lat=48.0 + idx, lng=11.0 + idx, category="Urlaub",
                created_by=user.id,
            )
            db.add(memory)
            db.flush()
            db.add(Photo(memory_id=memory.id,
                         filepath=f"data/uploads/c{couple.id}/foto{idx}.jpg"))
            db.add(Place(memory_id=memory.id, name=f"Stadt{idx}",
                         country=f"Land{idx}", lat=48.0 + idx, lng=11.0 + idx))
            db.add(Milestone(couple_id=couple.id, title=f"MEILENSTEIN-{paarname}",
                             date=datetime.date(2021, 3, idx)))

        # Codes für den Registrierungsteil
        couple = Couple(name="Neues Paar")
        db.add(couple)
        db.flush()
        db.add(Invite(code="GUELTIG", couple_id=couple.id, max_uses=2, used_count=0))
        db.add(Invite(code="AUFGEBRAUCHT", couple_id=couple.id, max_uses=1, used_count=1))
        db.add(Invite(code="ABGELAUFEN", couple_id=couple.id, max_uses=2, used_count=0,
                      expires_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)))
        db.commit()
        globals()["NEUES_PAAR_ID"] = couple.id
    finally:
        db.close()


# ── Prüfungen ───────────────────────────────────────────────────────────────

def pruefe_isolation() -> None:
    """Alice (Paar 1) darf nirgends Daten von Bob (Paar 2) sehen."""
    with TestClient(app) as client:
        r = client.post("/auth/login", data={"username": "alice", "password": "test1234"},
                        follow_redirects=False)
        check("Login alice", r.status_code == 303, f"status {r.status_code}")

        for pfad in SEITEN:
            r = client.get(pfad)
            check(f"GET {pfad}", r.status_code == 200, f"status {r.status_code}")
            for marker in FREMDE_MARKER:
                check(f"GET {pfad} ohne {marker!r}", marker not in r.text,
                      "FREMDDATEN SICHTBAR")

        # Gegenprobe: zu scharfe Filterung wäre genauso kaputt.
        check("eigene Erinnerung sichtbar",
              EIGENER_MARKER in client.get("/timeline").text, "eigene Daten fehlen")

        # Direktzugriff auf fremde IDs — 404, niemals 403 (kein Existenz-Leak).
        fremde_zugriffe = [
            ("GET", "/memories/2"),
            ("GET", "/memories/2/edit"),
            ("POST", "/memories/2/toggle-favorite"),
            ("POST", "/memories/2/toggle-hidden"),
            ("POST", "/memories/2/delete"),
            ("DELETE", "/memories/2"),
            ("PUT", "/api/milestones/2"),
            ("DELETE", "/api/milestones/2"),
            ("DELETE", "/photos/2"),
        ]
        for methode, pfad in fremde_zugriffe:
            kwargs: dict = {
                "follow_redirects": False,
                "headers": {"Content-Type": "application/json",
                            "Origin": "http://testserver"},
            }
            if methode == "PUT":
                kwargs["json"] = {"title": "uebernommen"}
            r = client.request(methode, pfad, **kwargs)
            check(f"{methode} {pfad} → 404", r.status_code == 404,
                  f"war {r.status_code}")

        check("eigene ID weiterhin erreichbar",
              client.get("/memories/1").status_code == 200)

        # Sprache kommt aus dem eigenen Paar, nicht aus einer beliebigen Zeile.
        check("Sprache de für Alice", 'lang="de"' in client.get("/timeline").text)

        # Neuanlage landet im eigenen Paar.
        r = client.post("/memories/new",
                        data={"title": "Neu von Alice", "date": "2024-01-01",
                              "category": "Alltag",
                              "csrf_token": client.cookies.get("csrf_token")},
                        follow_redirects=False)
        check("POST /memories/new", r.status_code == 303, f"status {r.status_code}")

    with TestClient(app) as client:
        r = client.post("/auth/login", data={"username": "bob", "password": "test1234"},
                        follow_redirects=False)
        check("Login bob", r.status_code == 303, f"status {r.status_code}")
        text = client.get("/timeline").text
        check("bob ohne Alices Bestand", EIGENER_MARKER not in text)
        check("bob ohne Alices Neuanlage", "Neu von Alice" not in text)
        check("bob sieht eigene Erinnerung", "GEHEIM-Paar Zwei" in text)
        check("Sprache en für Bob", 'lang="en"' in text)

    db = SessionLocal()
    try:
        # Paar-IDs nicht hartkodieren: die Migration legt bereits ein
        # Standard-Paar an, die Testpaare bekommen daher höhere IDs.
        alice = db.query(User).filter(User.username == "alice").first()
        neu = db.query(Memory).filter(Memory.title == "Neu von Alice").first()
        check("Neuanlage trägt Alices couple_id",
              neu is not None and alice is not None and neu.couple_id == alice.couple_id,
              f"memory={getattr(neu, 'couple_id', None)} "
              f"alice={getattr(alice, 'couple_id', None)}")
    finally:
        db.close()


def _registriere(client: TestClient, code: str, username: str,
                 name: str = "Test", pw: str = "test1234",
                 pw2: str | None = None):
    """Registrierungsformular abschicken (holt vorher das CSRF-Cookie)."""
    client.get("/auth/register")
    return client.post("/auth/register", data={
        "code": code, "name": name, "username": username,
        "password": pw, "password_repeat": pw2 if pw2 is not None else pw,
        "csrf_token": client.cookies.get("csrf_token"),
    }, follow_redirects=False)


def _fehlertext(html: str) -> str | None:
    treffer = re.search(r"<span>(.*?)</span>", html, re.S)
    return treffer.group(1).strip() if treffer else None


def pruefe_registrierung() -> None:
    """Einladungscodes: Ablehnungsfälle, erfolgreicher Fluss, Obergrenze."""
    with TestClient(app) as client:
        check("GET /auth/register", client.get("/auth/register").status_code == 200)

        # Reflektierter Code darf kein HTML einschleusen.
        r = client.get("/auth/register", params={"code": '"><script>alert(1)</script>'})
        check("kein XSS über ?code=", "<script>alert(1)</script>" not in r.text)

        ablehnungen = [
            ("unbekannter Code", dict(code="GIBTSNICHT", username="x1")),
            ("aufgebrauchter Code", dict(code="AUFGEBRAUCHT", username="x2")),
            ("abgelaufener Code", dict(code="ABGELAUFEN", username="x3")),
            ("zu kurzes Passwort", dict(code="GUELTIG", username="x4", pw="kurz")),
            ("Passwörter ungleich", dict(code="GUELTIG", username="x5", pw2="anders12")),
            ("ungültiger Username", dict(code="GUELTIG", username="a b!")),
            ("belegter Username", dict(code="GUELTIG", username="alice")),
        ]
        for label, kwargs in ablehnungen:
            r = _registriere(client, **kwargs)
            check(f"abgelehnt: {label}", r.status_code == 400, f"status {r.status_code}")

        # Die drei Code-Fälle dürfen nicht unterscheidbar sein, sonst wird die
        # Seite zum Orakel für gültige Codes.
        texte = [
            _fehlertext(_registriere(client, code, f"y{i}").text)
            for i, code in enumerate(("GIBTSNICHT", "AUFGEBRAUCHT", "ABGELAUFEN"))
        ]
        check("Fehlermeldung für alle Code-Fälle identisch",
              texte[0] and len(set(texte)) == 1, " / ".join(map(repr, texte)))

    with TestClient(app) as client:
        r = _registriere(client, "GUELTIG", "carla", name="Carla")
        check("erste Einlösung", r.status_code == 303, f"status {r.status_code}")
        check("danach angemeldet", client.get("/").status_code == 200)
        text = client.get("/timeline").text
        check("neues Konto ohne Fremddaten",
              EIGENER_MARKER not in text and "GEHEIM-Paar Zwei" not in text)

    with TestClient(app) as client:
        r = _registriere(client, "GUELTIG", "dieter", name="Dieter")
        check("zweite Einlösung", r.status_code == 303, f"status {r.status_code}")

    with TestClient(app) as client:
        r = _registriere(client, "GUELTIG", "erik", name="Erik")
        check("dritte Einlösung abgelehnt", r.status_code == 400, f"status {r.status_code}")

    db = SessionLocal()
    try:
        neu_id = globals()["NEUES_PAAR_ID"]
        carla = db.query(User).filter(User.username == "carla").first()
        dieter = db.query(User).filter(User.username == "dieter").first()
        check("Carla im eingeladenen Paar", carla is not None and carla.couple_id == neu_id)
        check("Dieter im selben Paar", dieter is not None and dieter.couple_id == neu_id)
        check("Erik nicht angelegt",
              db.query(User).filter(User.username == "erik").first() is None)
        cs = db.query(CoupleSettings).filter(CoupleSettings.couple_id == neu_id).first()
        check("Partner A = Carla", cs is not None and cs.partner_a_name == "Carla",
              f"a={getattr(cs, 'partner_a_name', None)}")
        check("Partner B = Dieter", cs is not None and cs.partner_b_name == "Dieter",
              f"b={getattr(cs, 'partner_b_name', None)}")
        invite = db.query(Invite).filter(Invite.code == "GUELTIG").first()
        check("Code aufgebraucht", invite.used_count == 2, f"used_count={invite.used_count}")
    finally:
        db.close()


def _bestand(db, couple_id: int) -> tuple[int, int, int, int]:
    """(Erinnerungen, Fotos, Orte, Meilensteine) eines Paars — roh gezählt."""
    ids = db.query(Memory.id).filter(Memory.couple_id == couple_id)
    return (
        ids.count(),
        db.query(Photo).filter(Photo.memory_id.in_(ids)).count(),
        db.query(Place).filter(Place.memory_id.in_(ids)).count(),
        db.query(Milestone).filter(Milestone.couple_id == couple_id).count(),
    )


def pruefe_demo_paare() -> None:
    """Lebenszyklus der Gast-Paare: anlegen, trennen, aufräumen, deckeln."""
    from config import settings
    from demo_data import DEMO_MEMORIES, DEMO_MILESTONES
    from tenancy import (
        create_demo_couple, delete_demo_couple, sweep_expired_demo_couples,
    )

    db = SessionLocal()
    try:
        echte_paare = {c.id: _bestand(db, c.id) for c in db.query(Couple).all()}
        benutzer_vorher = db.query(User).count()

        gast_a = create_demo_couple(db)
        gast_b = create_demo_couple(db)
        check("zwei Gäste, zwei Paare", gast_a.couple_id != gast_b.couple_id)
        check("Gast-Benutzernamen verschieden", gast_a.username != gast_b.username)

        paar_a = db.get(Couple, gast_a.couple_id)
        check("Demo-Paar markiert", paar_a.is_demo is True)
        check("Demo-Paar hat Ablaufdatum", paar_a.expires_at is not None)

        soll = (
            len(DEMO_MEMORIES),
            sum(len(m.get("photos", [])) for m in DEMO_MEMORIES),
            sum(len(m.get("places", [])) for m in DEMO_MEMORIES),
            len(DEMO_MILESTONES),
        )
        check("Demo-Bestand vollständig", _bestand(db, gast_a.couple_id) == soll,
              f"{_bestand(db, gast_a.couple_id)} != {soll}")
        check("Demo-Fotos liegen im Repo", all(
            (PROJECT_ROOT / p.filepath).is_file()
            for p in db.query(Photo).join(Memory)
            .filter(Memory.couple_id == gast_a.couple_id)
        ))

        # Änderung bei Gast A darf Gast B nicht erreichen.
        erste = (
            db.query(Memory).filter(Memory.couple_id == gast_a.couple_id)
            .order_by(Memory.id).first()
        )
        erste.title = "NUR-GAST-A"
        db.commit()
        check("Gast B ohne Änderung von Gast A",
              db.query(Memory).filter(Memory.couple_id == gast_b.couple_id,
                                      Memory.title == "NUR-GAST-A").count() == 0)

        # Gast-Konto ist per Login nicht erreichbar — und wirft dabei nicht.
        with TestClient(app, follow_redirects=False) as client:
            r = client.post("/auth/login",
                            data={"username": gast_a.username, "password": "!"})
            check("Gast-Login abgelehnt (401, nicht 500)", r.status_code == 401,
                  f"status {r.status_code}")

        # Löschen verweigert echte Paare.
        echtes_id = next(iter(echte_paare))
        check("delete_demo_couple verweigert echtes Paar",
              delete_demo_couple(db, echtes_id) is False)
        db.commit()
        check("echtes Paar unversehrt", _bestand(db, echtes_id) == echte_paare[echtes_id])

        # Aufräumlauf: nur abgelaufene Demo-Paare.
        check("Sweep ohne abgelaufene Paare", sweep_expired_demo_couples(db) == 0)
        paar_a.expires_at = datetime.datetime.now(datetime.timezone.utc) \
            - datetime.timedelta(minutes=1)
        db.commit()
        id_a, id_b = gast_a.couple_id, gast_b.couple_id
        check("Sweep löscht abgelaufenes Paar", sweep_expired_demo_couples(db) == 1)
        check("abgelaufenes Paar restlos weg",
              db.get(Couple, id_a) is None and _bestand(db, id_a) == (0, 0, 0, 0)
              and db.query(User).filter(User.couple_id == id_a).count() == 0
              and db.query(CoupleSettings)
              .filter(CoupleSettings.couple_id == id_a).count() == 0)
        check("laufendes Demo-Paar bleibt", _bestand(db, id_b) == soll)

        # Obergrenze: das älteste Paar wird verdrängt.
        grenze_vorher = settings.MAX_DEMO_COUPLES
        settings.MAX_DEMO_COUPLES = 2
        try:
            gast_c = create_demo_couple(db)
            gast_d = create_demo_couple(db)
            demo_ids = {c.id for c in db.query(Couple).filter(Couple.is_demo == True)}  # noqa: E712
            check("Obergrenze eingehalten", len(demo_ids) == 2, f"{len(demo_ids)} Paare")
            check("ältestes Demo-Paar verdrängt",
                  demo_ids == {gast_c.couple_id, gast_d.couple_id}, str(demo_ids))
        finally:
            settings.MAX_DEMO_COUPLES = grenze_vorher

        for couple_id in demo_ids:
            delete_demo_couple(db, couple_id)
        db.commit()
        check("alle Gast-Konten entfernt", db.query(User).count() == benutzer_vorher)
        check("echte Paare durchgehend unversehrt",
              {c.id: _bestand(db, c.id) for c in db.query(Couple).all()} == echte_paare)
    finally:
        db.close()


def _csrf(client: TestClient, pfad: str) -> str:
    """CSRF-Token holen, wie es ein Browser täte: Seite laden, Cookie lesen."""
    client.get(pfad)
    return client.cookies.get("csrf_token", "")


def _mini_jpeg() -> bytes:
    """Gültiges JPEG — muss die Magic-Byte-Prüfung in uploads.py bestehen."""
    import io
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(puffer, "JPEG")
    return puffer.getvalue()


def _upload_dateien() -> set[str]:
    from config import settings
    wurzel = Path(settings.UPLOAD_DIR)
    return {str(p) for p in wurzel.rglob("*") if p.is_file()} if wurzel.exists() else set()


def pruefe_gast_sperren(gast: TestClient) -> None:
    """Was ein Gast nicht darf: Dateien speichern, Login-Daten ändern.

    Geprüft wird jeder der fünf Wege, auf denen eine Datei ins System kommt —
    und zwar am Ergebnis (keine Datei, keine Foto-Zeile), nicht nur am
    Statuscode: die Formular-Routen antworten bewusst mit Erfolg und verwerfen
    den Anhang.
    """
    jpeg = _mini_jpeg()
    dateien_vorher = _upload_dateien()
    csrf = gast.cookies.get("csrf_token", "")

    db = SessionLocal()
    try:
        gast_paare = [c.id for c in db.query(Couple).filter(Couple.is_demo == True)]  # noqa: E712
    finally:
        db.close()

    def fremde_fotos() -> int:
        """Foto-Zeilen in Demo-Paaren, die nicht auf static/demo/ zeigen."""
        db = SessionLocal()
        try:
            return (
                db.query(Photo).join(Memory)
                .filter(Memory.couple_id.in_(gast_paare),
                        ~Photo.filepath.startswith("static/demo/")).count()
            )
        finally:
            db.close()

    seite = gast.get("/memories/new").text
    check("Gast: Formular ohne Dateifeld", 'type="file"' not in seite)
    seite = gast.get("/settings").text
    check("Gast: Einstellungen ohne Dateifeld", 'type="file"' not in seite)
    check("Gast: keine Login-Daten-Formulare",
          "/settings/change-username" not in seite
          and "/settings/change-password" not in seite)

    # 1) Erinnerung anlegen mit Anhang → Erinnerung ja, Foto nein
    r = gast.post("/memories/new",
                  data={"csrf_token": csrf, "title": "GAST-MIT-ANHANG",
                        "date": "2025-02-02", "category": "Alltag"},
                  files={"photos": ("a.jpg", jpeg, "image/jpeg")})
    check("Gast: Erinnerung mit Anhang wird angelegt", r.status_code == 303,
          f"status {r.status_code}")

    db = SessionLocal()
    try:
        neu = db.query(Memory).filter(Memory.title == "GAST-MIT-ANHANG").first()
        check("Gast: Anhang verworfen", neu is not None and len(neu.photos) == 0)
        memory_id = neu.id
    finally:
        db.close()

    # 2) Erinnerung bearbeiten mit Anhang
    r = gast.post(f"/memories/{memory_id}/edit",
                  data={"csrf_token": csrf, "title": "GAST-MIT-ANHANG",
                        "date": "2025-02-02", "category": "Alltag"},
                  files={"photos": ("b.jpg", jpeg, "image/jpeg")})
    check("Gast: Bearbeiten mit Anhang", r.status_code == 303, f"status {r.status_code}")

    # 3) Foto-API
    r = gast.post(f"/memories/{memory_id}/photos",
                  data={"csrf_token": csrf},
                  files={"file": ("c.jpg", jpeg, "image/jpeg")})
    check("Gast: Foto-Upload → 403", r.status_code == 403, f"status {r.status_code}")

    # 4) Avatar — übrige Einstellungen werden trotzdem gespeichert
    r = gast.post("/settings",
                  data={"csrf_token": csrf, "partner_a_name": "GastA",
                        "partner_b_name": "GastB"},
                  files={"avatar": ("d.jpg", jpeg, "image/jpeg")})
    check("Gast: Einstellungen speichern", r.status_code == 303, f"status {r.status_code}")
    db = SessionLocal()
    try:
        gast_user = db.query(User).filter(User.couple_id.in_(gast_paare),
                                          User.avatar_path != None).count()  # noqa: E711
        check("Gast: Avatar verworfen", gast_user == 0)
        check("Gast: Namen gespeichert",
              db.query(CoupleSettings).filter(CoupleSettings.partner_a_name == "GastA").count() == 1)
    finally:
        db.close()

    # 5) Login-Daten
    for pfad, daten in [
        ("/settings/change-username", {"new_username": "uebernommen", "current_password": "!"}),
        ("/settings/change-password", {"current_password": "!", "new_password": "neuesPW123",
                                       "new_password_repeat": "neuesPW123"}),
    ]:
        r = gast.post(pfad, data={"csrf_token": csrf, **daten})
        check(f"Gast: POST {pfad} → 403", r.status_code == 403, f"status {r.status_code}")
    db = SessionLocal()
    try:
        check("Gast: Benutzername unverändert",
              db.query(User).filter(User.username == "uebernommen").count() == 0)
        check("Gast: Passwort-Platzhalter unverändert",
              db.query(User).filter(User.couple_id.in_(gast_paare),
                                    User.hashed_password != "!").count() == 0)
    finally:
        db.close()

    check("Gast: keine Foto-Zeile außerhalb static/demo/", fremde_fotos() == 0,
          f"{fremde_fotos()} Zeilen")
    check("Gast: keine Datei im Upload-Verzeichnis entstanden",
          _upload_dateien() == dateien_vorher,
          str(_upload_dateien() - dateien_vorher))

    # Gegenprobe: bei einem echten Konto funktioniert derselbe Upload.
    import auth as auth_modul
    with TestClient(app, follow_redirects=False) as alice:
        auth_modul._login_attempts.clear()
        alice.post("/auth/login", data={"username": "alice", "password": "test1234"})
        alice.get("/")
        db = SessionLocal()
        try:
            alice_memory = (
                db.query(Memory).join(User, Memory.created_by == User.id)
                .filter(User.username == "alice").first().id
            )
        finally:
            db.close()
        r = alice.post(f"/memories/{alice_memory}/photos",
                       data={"csrf_token": alice.cookies.get("csrf_token", "")},
                       files={"file": ("e.jpg", jpeg, "image/jpeg")})
        check("Gegenprobe: echter Nutzer lädt hoch", r.status_code == 201,
              f"status {r.status_code}")
        neue = _upload_dateien() - dateien_vorher
        check("Gegenprobe: Datei entstanden", len(neue) >= 1)
        if r.status_code == 201:
            alice.delete(f"/photos/{r.json()['id']}")


def pruefe_gastzugang() -> None:
    """Demo-Einstieg über HTTP: Schalter, CSRF, Trennung, Reset, Logout."""
    from config import settings
    import auth as auth_modul

    def demo_paare() -> set[int]:
        db = SessionLocal()
        try:
            return {c.id for c in db.query(Couple).filter(Couple.is_demo == True)}  # noqa: E712
        finally:
            db.close()

    with TestClient(app, follow_redirects=False) as client:
        token = _csrf(client, "/auth/login")
        check("Button aus, solange DEMO_ENABLED=false",
              "/auth/demo" not in client.get("/auth/login").text)
        r = client.post("/auth/demo", data={"csrf_token": token})
        check("POST /auth/demo aus → 404", r.status_code == 404, f"status {r.status_code}")
        check("kein Demo-Paar bei abgeschaltetem Zugang", demo_paare() == set())

    settings.DEMO_ENABLED = True
    try:
        with TestClient(app, follow_redirects=False) as gast1, \
                TestClient(app, follow_redirects=False) as gast2:
            check("Button sichtbar bei DEMO_ENABLED=true",
                  "/auth/demo" in gast1.get("/auth/login").text)
            check("GET /auth/demo legt nichts an",
                  gast1.get("/auth/demo").status_code == 405 and demo_paare() == set())
            r = gast1.post("/auth/demo", data={})
            check("ohne CSRF-Token → 403", r.status_code == 403, f"status {r.status_code}")

            r = gast1.post("/auth/demo", data={"csrf_token": _csrf(gast1, "/auth/login")})
            check("Gast 1 eingestiegen", r.status_code == 303, f"status {r.status_code}")
            cookies = r.headers.get_list("set-cookie")
            check("Gast bekommt Session-Cookies (kein Max-Age)",
                  all("max-age" not in c.lower() for c in cookies
                      if c.startswith(("access_token=", "refresh_token="))), str(cookies))
            check("Auth-Cookies HttpOnly",
                  all("httponly" in c.lower() for c in cookies
                      if c.startswith(("access_token=", "refresh_token="))))
            r = gast2.post("/auth/demo", data={"csrf_token": _csrf(gast2, "/auth/login")})
            check("Gast 2 eingestiegen", r.status_code == 303, f"status {r.status_code}")
            check("zwei Demo-Paare", len(demo_paare()) == 2, str(demo_paare()))

            for pfad in SEITEN:
                r = gast1.get(pfad)
                check(f"Gast GET {pfad}", r.status_code == 200, f"status {r.status_code}")
                if "text/html" in r.headers.get("content-type", ""):
                    check(f"Gast GET {pfad} mit Demo-Banner", "/auth/demo" in r.text)
                for marker in (EIGENER_MARKER, *FREMDE_MARKER):
                    check(f"Gast GET {pfad} ohne {marker!r}", marker not in r.text)
            check("Gast sieht Demo-Daten", "Silvester in Berlin" in gast1.get("/timeline").text)

            # Änderung von Gast 1 erreicht Gast 2 nicht.
            r = gast1.post("/memories/new", data={
                "csrf_token": gast1.cookies.get("csrf_token", ""),
                "title": "NUR-GAST-EINS", "date": "2025-01-01", "category": "Alltag",
            })
            check("Gast legt Erinnerung an", r.status_code == 303, f"status {r.status_code}")
            check("Gast 1 sieht eigene Änderung", "NUR-GAST-EINS" in gast1.get("/timeline").text)
            check("Gast 2 sieht sie nicht", "NUR-GAST-EINS" not in gast2.get("/timeline").text)

            pruefe_gast_sperren(gast1)

            # Reset: neues Paar, altes weg, Änderung weg.
            vorher = demo_paare()
            r = gast1.post("/auth/demo",
                           data={"csrf_token": gast1.cookies.get("csrf_token", "")})
            check("Reset", r.status_code == 303, f"status {r.status_code}")
            nachher = demo_paare()
            check("Reset ersetzt das Paar statt eines dazuzulegen",
                  len(nachher) == 2 and len(nachher - vorher) == 1, f"{vorher} → {nachher}")
            text = gast1.get("/timeline").text
            check("Reset verwirft Änderungen",
                  "NUR-GAST-EINS" not in text and "Silvester in Berlin" in text)

            # Logout räumt das Paar des Gasts ab.
            gast1.get("/auth/logout")
            check("Logout löscht Demo-Paar", len(demo_paare()) == 1, str(demo_paare()))
            check("nach Logout abgemeldet", gast1.get("/").status_code in (303, 401))

            # Echter Nutzer: Logout löscht nichts, kein Banner.
            with TestClient(app, follow_redirects=False) as alice:
                auth_modul._login_attempts.clear()
                alice.post("/auth/login", data={"username": "alice", "password": "test1234"})
                check("echter Nutzer ohne Demo-Banner",
                      'action="/auth/demo"' not in alice.get("/").text)
                alice.get("/auth/logout")
            db = SessionLocal()
            try:
                check("Logout eines echten Nutzers löscht sein Paar nicht",
                      db.query(User).filter(User.username == "alice").count() == 1
                      and db.query(Memory).filter(Memory.title.contains("GEHEIM")).count() >= 2)
            finally:
                db.close()

            # Rate-Limit pro IP auf dem eigenen Zähler.
            auth_modul._login_attempts.clear()
            codes = [
                gast2.post("/auth/demo",
                           data={"csrf_token": gast2.cookies.get("csrf_token", "")}).status_code
                for _ in range(settings.LOGIN_RATE_LIMIT_MAX + 1)
            ]
            check("Rate-Limit greift nach LOGIN_RATE_LIMIT_MAX Einstiegen",
                  codes[-1] == 429 and codes[:-1] == [303] * settings.LOGIN_RATE_LIMIT_MAX,
                  str(codes))
            check("Demo-Zähler sperrt den Login nicht",
                  not any(k.startswith("ip:") for k in auth_modul._login_attempts))
    finally:
        settings.DEMO_ENABLED = False
        auth_modul._login_attempts.clear()


def pruefe_sweep_endpunkt() -> None:
    """GET /internal/demo-sweep: nur mit Secret, löscht nur Abgelaufenes."""
    from config import settings
    from tenancy import create_demo_couple

    pfad = "/internal/demo-sweep"
    settings.DEMO_ENABLED = True
    db = SessionLocal()
    try:
        abgelaufen = create_demo_couple(db).couple_id
        laufend = create_demo_couple(db).couple_id
        db.get(Couple, abgelaufen).expires_at = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
        )
        db.commit()

        with TestClient(app, follow_redirects=False) as client:
            richtig = {"Authorization": "Bearer geheim-123"}

            settings.CRON_SECRET = ""
            check("Sweep ohne konfiguriertes Secret → 404",
                  client.get(pfad, headers={"Authorization": "Bearer "}).status_code == 404)

            settings.CRON_SECRET = "geheim-123"
            check("Sweep ohne Header → 404", client.get(pfad).status_code == 404)
            check("Sweep mit falschem Secret → 404",
                  client.get(pfad, headers={"Authorization": "Bearer falsch"}).status_code == 404)
            check("Sweep mit Secret ohne Bearer-Präfix → 404",
                  client.get(pfad, headers={"Authorization": "geheim-123"}).status_code == 404)
            db.expire_all()
            check("abgelehnte Aufrufe löschen nichts", db.get(Couple, abgelaufen) is not None)

            settings.DEMO_ENABLED = False
            check("Sweep bei abgeschalteter Demo → 404",
                  client.get(pfad, headers=richtig).status_code == 404)
            settings.DEMO_ENABLED = True

            r = client.get(pfad, headers=richtig)
            check("Sweep mit Secret → 200", r.status_code == 200, f"status {r.status_code}")
            check("Sweep meldet ein gelöschtes Paar", r.json() == {"deleted": 1}, r.text)
            db.expire_all()
            check("abgelaufenes Paar weg", db.get(Couple, abgelaufen) is None)
            check("laufendes Paar bleibt", db.get(Couple, laufend) is not None)
            check("echte Paare bleiben",
                  db.query(Couple).filter(Couple.is_demo == False).count() >= 2)  # noqa: E712
            check("zweiter Lauf ist ein No-op",
                  client.get(pfad, headers=richtig).json() == {"deleted": 0})
    finally:
        settings.CRON_SECRET = ""
        settings.DEMO_ENABLED = False
        db.close()


def main() -> int:
    baue_testdaten()
    pruefe_isolation()
    pruefe_registrierung()
    pruefe_demo_paare()
    pruefe_gastzugang()
    pruefe_sweep_endpunkt()

    print(f"{_checks} Prüfungen, {len(_fails)} Fehler")
    for fehler in _fails:
        print("  FEHLER:", fehler)
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
