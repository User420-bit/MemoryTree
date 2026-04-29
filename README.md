# 🌳 Memory Tree

**Euer privates digitales Erinnerungsbuch** — eine Web-App für Paare, um gemeinsame Erinnerungen, Fotos und Meilensteine festzuhalten, visualisiert als wachsender interaktiver Baum.

---

## Schnellstart

### Voraussetzung

- **Python 3.11+** muss installiert sein → [python.org/downloads](https://www.python.org/downloads/)

### Starten (2 Schritte)

```bash
# 1. Einmalig: Skript ausführbar machen
chmod +x start.sh stop.sh

# 2. App starten (erledigt beim ersten Mal alles automatisch)
./start.sh
```

Das Skript richtet beim ersten Start **alles automatisch** ein:
- Erstellt eine virtuelle Umgebung (`.venv`)
- Installiert alle Abhängigkeiten
- Erstellt die `.env`-Konfiguration
- Startet den Server und öffnet den Browser

Ab dem zweiten Start reicht: `./start.sh`

---

## Starten unter Windows (Docker)

Unter Windows läuft Memory Tree am einfachsten in einem Docker-Container —
keine Python-Installation, kein venv, keine Pfad-Probleme.

### Voraussetzung

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** installiert und gestartet

### Starten

```powershell
# 1. Konfiguration anlegen (einmalig)
copy .env.example .env

# 2. SECRET_KEY in .env eintragen — sicheren Wert generieren mit:
docker run --rm python:3.11-slim python -c "import secrets; print(secrets.token_urlsafe(64))"

# 3. App bauen und starten
docker compose -f docker-compose.yml up --build
```

Anschließend `http://localhost:8000` im Browser öffnen.

### Erster Login (User anlegen)

```powershell
# In einem zweiten Terminal, während die App läuft:
docker compose -f docker-compose.yml exec app python scripts/create_users.py
```

### Stoppen

```powershell
# Im laufenden Terminal: Ctrl+C
# Oder aus einem anderen Terminal:
docker compose -f docker-compose.yml down
```

Die SQLite-Datenbank und alle hochgeladenen Bilder bleiben im Ordner
`./data/` auf dem Host erhalten und überstehen jeden Container-Rebuild.

> Hinweis: Die Datei `compose.yaml` ist die Production-Variante für den
> Raspberry Pi (mit Caddy als Reverse-Proxy). Für lokale Entwicklung
> unter Windows/macOS/Linux immer `docker-compose.yml` mit dem `-f`-Flag
> verwenden.

---

## App stoppen

```bash
# Option A: Im Terminal, wo der Server läuft
CTRL+C

# Option B: Aus einem anderen Terminal
./stop.sh
```

---

## Erster Login

Nach dem Start öffnet sich automatisch `http://localhost:8000`.

| Benutzer | Passwort |
|---|---|
| `partner_a` | `test1234` |
| `partner_b` | `test1234` |

> ⚠️ **Wichtig:** Ändere den `SECRET_KEY` in der `.env`-Datei, bevor du die App produktiv nutzt.

---

## VS Code Integration

### Per Shortcut starten

**⇧⌘B** (Shift+Cmd+B) → startet die App direkt aus VS Code.

Oder: **Terminal → Aufgabe ausführen → ▶ Memory Tree starten**

### Debuggen

**F5** → startet die App im Debug-Modus mit Breakpoint-Unterstützung.

---

## Projektstruktur

```
memory-tree/
├── main.py              # FastAPI Einstiegspunkt
├── models.py            # SQLAlchemy Datenmodelle
├── database.py          # DB-Verbindung & Session
├── auth.py              # JWT-Authentifizierung
├── config.py            # App-Konfiguration
├── schemas.py           # Pydantic Request/Response Schemas
├── routers/
│   ├── auth.py          # Login/Logout
│   ├── memories.py      # CRUD Erinnerungen
│   ├── photos.py        # Foto-Upload
│   └── milestones.py    # Meilensteine
├── templates/           # Jinja2 HTML-Templates
├── static/              # CSS, JS, Bilder, Uploads
├── start.sh             # App starten
├── stop.sh              # App stoppen
└── requirements.txt     # Python-Abhängigkeiten
```

---

## Tech Stack

| Komponente | Technologie |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| Datenbank | SQLite + SQLAlchemy 2.0 |
| Templates | Jinja2 + Tailwind CSS |
| Auth | JWT (python-jose) + bcrypt |
| Visualisierung | D3.js (Baum), Leaflet.js (Karte) |

---

## Konfiguration

Die App wird über die `.env`-Datei konfiguriert:

| Variable | Beschreibung | Standard |
|---|---|---|
| `SECRET_KEY` | JWT-Signaturschlüssel | `dein-geheimer-schluessel-hier-aendern` |
| `DATABASE_URL` | SQLite-Datenbankpfad | `sqlite:///./memory_tree.db` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session-Dauer in Minuten | `480` |
| `UPLOAD_DIR` | Verzeichnis für Foto-Uploads | `static/uploads` |
| `MAX_IMAGE_SIZE` | Max. Bildbreite/-höhe in Pixeln | `1920` |
