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


def main() -> int:
    baue_testdaten()
    pruefe_isolation()
    pruefe_registrierung()

    print(f"{_checks} Prüfungen, {len(_fails)} Fehler")
    for fehler in _fails:
        print("  FEHLER:", fehler)
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
