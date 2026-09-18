# Memory Tree — Deployment & Host-Hardening Guide

Dieses Dokument beschreibt das Deployment auf einem **Raspberry Pi Zero 2 W** (ARM64, 512 MB RAM) mit **Ubuntu 24.04** und **Docker Compose**.

---

## 1. Host-Vorbereitung (Ubuntu 24.04 / Pi)

### 1.1 SSH absichern

```bash
# SSH-Key auf dem lokalen Rechner erstellen (falls noch nicht vorhanden)
ssh-keygen -t ed25519 -C "pi-memory-tree"

# Key auf den Pi kopieren
ssh-copy-id -i ~/.ssh/id_ed25519.pub pi@<PI_IP>

# SSH-Konfiguration auf dem Pi absichern
sudo nano /etc/ssh/sshd_config
```

Folgende Einstellungen setzen:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
```

```bash
sudo systemctl restart sshd
```

### 1.2 Firewall (UFW)

```bash
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS
sudo ufw enable
sudo ufw status
```

### 1.3 Fail2ban

```bash
sudo apt install -y fail2ban
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo nano /etc/fail2ban/jail.local
```

Mindestens SSH-Schutz aktivieren:
```ini
[sshd]
enabled = true
port = 22
maxretry = 3
bantime = 3600
```

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 1.4 Automatische Sicherheitsupdates

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 1.5 Docker installieren (ARM64)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Ausloggen und wieder einloggen
```

> **Wichtig:** Den Docker-Socket (`/var/run/docker.sock`) NICHT exponieren oder an nicht-vertrauenswürdige Container mounten.

---

## 2. App-Deployment

### 2.1 Repository klonen

```bash
cd /home/pi
git clone <REPO_URL> memory-tree
cd memory-tree
```

### 2.2 Konfiguration

```bash
cp .env.example .env
nano .env
```

**Wichtige Einstellungen:**

```bash
# PFLICHT: Sicheren Key generieren
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# Ausgabe in .env als SECRET_KEY= eintragen

APP_ENV=production
DEBUG=false
SECRET_KEY=<GENERIERTER_KEY>
DATABASE_URL=sqlite:///./data/memory_tree.db
UPLOAD_DIR=data/uploads
LOG_LEVEL=INFO
```

### 2.3 Docker Image bauen und starten

```bash
docker compose build
docker compose up -d
```

### 2.4 Benutzer erstellen (erstmaliges Setup)

```bash
docker compose exec app python3 scripts/create_users.py
```

Das legt die beiden Konten des Standard-Paars (#1) an.

### 2.4b Weitere Paare einladen

Neue Nutzer registrieren sich nicht selbst — sie brauchen einen Code, den du
erzeugst. Ein Aufruf legt Paar, Einstellungen und Code in einem Schritt an:

```bash
docker compose exec app python3 scripts/create_invite.py --name "Anna & Ben"
docker compose exec app python3 scripts/create_invite.py --list
```

Das Skript druckt einen Link der Form `/auth/register?code=…`. Der Code ist
standardmäßig zweimal einlösbar (die zwei Partner) und 30 Tage gültig; der
erste Einlöser wird Partner A, der zweite Partner B. Den Code über einen
vertrauenswürdigen Kanal weitergeben — wer ihn hat, kann ein Konto in diesem
Paar anlegen.

### 2.5 Status prüfen

```bash
docker compose ps
docker compose logs --tail 50
curl -s http://localhost/health
```

---

## 3. Backup & Restore

### 3.1 Manuelles Backup

```bash
./scripts/backup.sh
# Backup wird in ./backups/ erstellt
```

### 3.2 Automatisches Backup (Crontab)

```bash
crontab -e
# Täglich um 3:00 Uhr:
0 3 * * * /home/pi/memory-tree/scripts/backup.sh >> /var/log/memory-tree-backup.log 2>&1
```

### 3.3 Offsite-Backup (optional)

Im Backup-Script sind Zeilen für rsync/rclone/S3 vorbereitet. Kommentiere die passende Zeile ein:

```bash
# rsync -avz ./backups/ user@remote:/backups/memory-tree/
# rclone copy ./backups/memory-tree-LATEST.tar.gz remote:backups/
```

### 3.4 Restore

```bash
# App stoppen
docker compose down

# Backup entpacken
tar -xzf backups/memory-tree-YYYYMMDD_HHMMSS.tar.gz -C /tmp/restore

# Datenbank wiederherstellen
docker volume inspect memorytree_app-data --format '{{ .Mountpoint }}'
# DB-Datei und Uploads in das Volume kopieren
sudo cp /tmp/restore/YYYYMMDD_HHMMSS/memory_tree.db <VOLUME_PATH>/memory_tree.db
sudo cp -a /tmp/restore/YYYYMMDD_HHMMSS/uploads/ <VOLUME_PATH>/uploads/

# App starten
docker compose up -d
```

---

## 4. Updates

```bash
cd /home/pi/memory-tree
git pull

# Backup vor Update
./scripts/backup.sh

# Neu bauen und starten
docker compose build
docker compose up -d

# Migrationen ausführen (falls nötig)
docker compose exec app alembic upgrade head

# Logs prüfen
docker compose logs --tail 20
```

### 4.1 Einmalig: Upgrade auf die Mandantentrennung

Die Revision `b1f4a7c9e230` führt `couples`/`invites` ein und hängt allen
vorhandenen Bestand an ein Standard-Paar (`couples.id = 1`). Es gehen keine
Daten verloren, aber **vorher Backup ziehen** (`./scripts/backup.sh`).

```bash
docker compose exec app alembic upgrade head
```

Stammt die Datenbank aus der Zeit vor Alembic (kein `alembic_version`-Table,
Fehler „table users already exists"), zuerst auf die Ausgangsrevision stempeln:

```bash
docker compose exec app alembic stamp d85c3a73c2a2
docker compose exec app alembic upgrade head
```

Bestehende Foto-Dateien bleiben unter `data/uploads/` liegen und werden weiter
gefunden; erst neue Uploads landen unter `data/uploads/c<paar-id>/`.

---

## 5. Healthcheck

- **Endpoint:** `GET /health` → `{"status": "ok"}`
- **Docker Healthcheck:** Integriert im Dockerfile (alle 30s)
- **Caddy Health-Probe:** Prüft `/health` alle 30s

```bash
# Manuell prüfen
curl http://localhost/health

# Docker Health-Status
docker inspect --format='{{.State.Health.Status}}' memory-tree-app
```

---

## 6. Troubleshooting

### Logs ansehen
```bash
docker compose logs -f app      # App-Logs (JSON)
docker compose logs -f caddy    # Reverse-Proxy-Logs
```

### Container neustarten
```bash
docker compose restart app
```

### DB-Integrität prüfen
```bash
docker compose exec app sqlite3 /app/data/memory_tree.db "PRAGMA integrity_check;"
```

### RAM-Verbrauch prüfen
```bash
docker stats --no-stream
```

---

## 7. Architektur-Übersicht

```
Internet/LAN
     │
     ▼
┌─────────┐
│  Caddy   │  :80/:443 — Static Assets, HTTPS, Reverse Proxy
└────┬─────┘
     │ :8000
     ▼
┌─────────┐
│  App     │  Gunicorn (1 Worker) + Uvicorn + FastAPI
│          │  SQLite (WAL) + Pillow
└────┬─────┘
     │
     ▼
┌─────────┐
│  Volume  │  data/memory_tree.db + data/uploads/
└──────────┘
```

---

## 8. Hinweise für Tailscale/VPN-Betrieb

Falls die App nur über Tailscale erreichbar ist:
- HTTPS über Caddy ist optional (Tailscale verschlüsselt bereits)
- HSTS-Header deaktiviert lassen
- `Secure`-Flag auf Cookies kann problematisch sein ohne HTTPS — wird über `APP_ENV` gesteuert
- UFW-Regeln können auf Port 22 + Tailscale beschränkt werden

---

## 9. Deployment ohne Docker (7-Phasen-Plan)

Für ein leichtgewichtiges Setup direkt auf dem Pi (ohne Docker-Overhead).

### Phase 1: Pi vorbereiten

```bash
# SSH auf dem Pi aktivieren (falls noch nicht geschehen)
sudo systemctl enable ssh
sudo systemctl start ssh

# IP-Adresse herausfinden
hostname -I
```

### Phase 2: Mac → Pi verbinden

```bash
# Vom Mac aus:
ssh pi@<PI_IP>
```

### Phase 3: Pi-System einrichten

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip git sqlite3 libjpeg-dev zlib1g-dev libwebp-dev
```

### Phase 4: Code übertragen

```bash
# Vom Mac aus (NICHT .venv, .env, data/, __pycache__):
rsync -avz --exclude '.venv' --exclude '.env' --exclude 'data/' \
  --exclude '__pycache__' --exclude '.git' --exclude '.claude/' \
  --exclude 'node_modules' --exclude '*.pyc' --exclude '.DS_Store' \
  /pfad/zu/MemoryTree/ pi@<PI_IP>:/home/pi/memory-tree/
```

### Phase 5: App konfigurieren

```bash
ssh pi@<PI_IP>
cd /home/pi/memory-tree

# Virtuelle Umgebung erstellen
python3.11 -m venv .venv
source .venv/bin/activate

# Abhängigkeiten installieren
pip install --upgrade pip
pip install -r requirements.txt

# .env anlegen
cp .env.example .env
nano .env
# SECRET_KEY generieren:
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# Ausgabe als SECRET_KEY= in .env eintragen

# Datenverzeichnisse erstellen
mkdir -p data/uploads/thumbs

# Benutzer erstellen
python3 scripts/create_users.py
```

### Phase 6: App starten & Auto-Start

```bash
# Teststart
source .venv/bin/activate
gunicorn -c gunicorn.conf.py main:app
# → http://<PI_IP>:8000 im Browser testen, dann CTRL+C

# systemd-Service installieren
sudo cp scripts/memory-tree.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable memory-tree
sudo systemctl start memory-tree

# Status prüfen
sudo systemctl status memory-tree
curl -s http://localhost:8000/health
```

### Phase 7: Vom Handy testen

1. Handy im gleichen WLAN wie der Pi
2. Browser öffnen: `http://<PI_IP>:8000`
3. Login mit den erstellten Zugangsdaten prüfen
4. Erinnerung anlegen, Foto hochladen, Baum prüfen

> **Hinweis:** Ohne HTTPS sind Cookies nicht mit `Secure`-Flag gesetzt (`APP_ENV=production` + kein HTTPS = `Secure=False`). Das ist im privaten LAN akzeptabel. Für Zugriff über das Internet Caddy mit HTTPS vorschalten oder Tailscale verwenden.

---

## 10. Host-Hardening Checkliste

### Zusammenfassung der Sicherheitsmaßnahmen

| Maßnahme | Status | Abschnitt |
|---|---|---|
| SSH Key-Only | ✅ | 1.1 |
| PasswordAuthentication no | ✅ | 1.1 |
| PermitRootLogin no | ✅ | 1.1 |
| UFW Firewall (22/80/443) | ✅ | 1.2 |
| Fail2ban für SSH | ✅ | 1.3 |
| unattended-upgrades | ✅ | 1.4 |
| Docker non-root User | ✅ | Dockerfile |
| Docker-Socket nicht exponieren | ✅ | 1.5 |
| SECRET_KEY aus .env | ✅ | config.py |
| JWT in HttpOnly Cookies | ✅ | auth.py |
| CSRF Double-Submit | ✅ | middleware.py |
| Rate Limiting (Login) | ✅ | auth.py |
| CSP / Security Headers | ✅ | middleware.py |
| Upload Magic-Byte-Validierung | ✅ | uploads.py |
| SQLite WAL + Hardening | ✅ | database.py |
| Backup-Script | ✅ | scripts/backup.sh |

### Regelmäßige Wartung

```bash
# Backups testen (monatlich Restore-Test empfohlen)
./scripts/backup.sh
tar -tzf backups/memory-tree-*.tar.gz | head

# Disk-Auslastung prüfen
df -h

# Docker-Images aufräumen
docker system prune -f

# SQLite-Integrität prüfen
sqlite3 data/memory_tree.db "PRAGMA integrity_check;"
```

---

## 11. Sicherheits-Notizen (Audit Juli 2026)

### 11.1 /uploads ist bewusst ohne Auth erreichbar — Revisit-Pflicht

Der Static-Mount `/uploads` liefert Fotos ohne Login aus. Das ist eine
**bewusste Entscheidung** für den aktuellen Betrieb (nur LAN/Tailscale,
nicht öffentlich erreichbar), abgesichert durch nicht erratbare
UUID-Dateinamen.

**MUSS neu bewertet werden, sobald sich das Deployment-Modell ändert** —
z. B. öffentlicher Server (Hetzner o. ä.), Portfreigabe oder Cloudflare
Tunnel. Dann: auth-geschützte FileResponse-Route statt Static-Mount.

### 11.2 Nach dem Git-History-Rewrite (Juli 2026)

Private Fotos und SQLite-WAL-Dateien lagen bis Juli 2026 in der
Git-History und wurden per `git filter-repo` entfernt (Force-Push nötig).
Als Defense-in-Depth danach:

1. **Beide Partner ändern ihr Passwort** über Einstellungen → Konto
   (die bcrypt-Hashes waren in der WAL-Datei im Repo).
2. Alte Clones des Repos (andere Rechner) löschen und frisch klonen —
   sie enthalten die alte History weiterhin.

### 11.3 Proxy-Header

`TRUST_PROXY_HEADERS` in `.env` nur auf `true` setzen, wenn die App
hinter einem vertrauenswürdigen Reverse Proxy (Caddy/Traefik) läuft.
Direkt erreichbar → `false`, sonst ist das Login-Rate-Limit per
gespooftem `X-Forwarded-For` umgehbar.

---

### 11.4 Mandantentrennung (seit August 2026)

Die App bedient jetzt mehrere Paare. Die Trennung ist rein anwendungsseitig:
jede Zeile trägt eine `couple_id`, und jeder Zugriff läuft über die Helfer in
[tenancy.py](tenancy.py). Es gibt **keine** Row-Level-Security in der Datenbank
— eine vergessene Filterung wäre unmittelbar ein Datenleck zwischen Paaren.

Deshalb nach jeder Änderung an Query-Code prüfen:

```bash
grep -rn 'db\.query(\(Memory\|Milestone\|Photo\|Place\|CoupleSettings\)' \
  --include='*.py' main.py routers/ middleware.py
```

Treffer außerhalb von `tenancy.py` sind erklärungsbedürftig. Zugriff auf eine
fremde ID muss 404 liefern, nie 403 — sonst verrät der Statuscode die Existenz
fremder Datensätze.

Die Uploads liegen pro Paar unter `data/uploads/c<paar-id>/` bzw. mit
demselben Blob-Präfix. Das ist Ordnung, **kein Zugriffsschutz** — die URLs
bleiben ohne Login abrufbar (siehe 11.1 und 12.6). Mit mehr Nutzern wächst
diese Angriffsfläche entsprechend.

## 12. Deployment auf Vercel (Alternative zum Pi)

Vercel ist serverless: das Dateisystem ist read-only und jede Anfrage kann in
einer frischen, kurzlebigen Function-Instanz landen. Die App unterstützt
deshalb zwei Betriebsmodi, die über Umgebungsvariablen umgeschaltet werden:

| | Raspberry Pi | Vercel |
|---|---|---|
| Datenbank | SQLite-Datei | Neon Postgres |
| Uploads | `data/uploads/` | Vercel Blob |
| Prozess | Gunicorn (dauerhaft) | Function pro Request |
| Schema | `alembic upgrade head` | `alembic upgrade head` (lokal, gegen Neon) |

Der Code wählt automatisch: `DATABASE_URL` bestimmt die Datenbank,
`BLOB_READ_WRITE_TOKEN` bestimmt den Upload-Storage. Der Pi-Betrieb bleibt
unverändert funktionsfähig.

### 12.1 Ressourcen anlegen

1. Im Vercel-Dashboard → Storage → **Neon Postgres** anlegen und mit dem
   Projekt verbinden. Den **pooled** Connection String verwenden (Host mit
   `-pooler`); die App setzt für Postgres bewusst `NullPool`, das Pooling
   übernimmt Neons PgBouncer.
2. Storage → **Blob Store** anlegen und mit dem Projekt verbinden.
   `BLOB_READ_WRITE_TOKEN` wird danach automatisch injiziert.

### 12.2 Umgebungsvariablen (Project Settings → Environment Variables)

```
APP_ENV=production
DEBUG=false
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(64))">
DATABASE_URL=postgresql://…-pooler….neon.tech/neondb?sslmode=require
ALLOWED_HOSTS=<projekt>.vercel.app,<eigene-domain>
TRUST_PROXY_HEADERS=true
FORCE_SECURE_COOKIES=true
```

`TRUST_PROXY_HEADERS=true` ist hier korrekt: auf Vercel läuft **jeder**
Request über den Vercel-Proxy, `X-Forwarded-For` ist also vertrauenswürdig.
`BLOB_READ_WRITE_TOKEN` kommt von der Blob-Integration und wird nicht
manuell gesetzt.

### 12.3 Schema und Daten einspielen (lokal ausführen)

```bash
export DATABASE_URL='postgresql://…-pooler….neon.tech/neondb?sslmode=require'
export BLOB_READ_WRITE_TOKEN='vercel_blob_rw_…'
export APP_ENV=production SECRET_KEY='<derselbe Key wie auf Vercel>'

# 1. Schema anlegen
alembic upgrade head

# 2a. Bestehende Pi-Daten übernehmen (Bilder → Blob, Zeilen → Postgres)
python3 scripts/migrate_to_vercel.py --dry-run   # erst ansehen
python3 scripts/migrate_to_vercel.py

# 2b. ODER: leer starten
python3 scripts/seed.py            # Paar-Einstellungen
python3 scripts/create_users.py    # Accounts + Passwörter
```

Die Migration bricht ab, wenn die Zieltabellen nicht leer sind (`--force`
überschreibt diese Sicherung). IDs bleiben erhalten, danach werden die
Postgres-Sequenzen auf `max(id)` gesetzt.

### 12.4 Deployen

```bash
npx vercel            # Preview-Deployment
npx vercel --prod     # Production
```

`vercel.json` leitet alle Routen auf die ASGI-Function in
[api/index.py](api/index.py). Statische Dateien und Templates werden über
`includeFiles` mitgebündelt; `.vercelignore` hält `data/`, `.env` und das
Pi-/Docker-Setup aus dem Bundle heraus.

**Wichtig:** Beim App-Start läuft keinerlei Schema-Initialisierung mehr
(früher `main._init_database`). Nach jeder Änderung an `models.py` gilt:
`alembic revision --autogenerate` + `alembic upgrade head` gegen Neon
ausführen, **bevor** deployt wird.

### 12.5 Rate-Limiting

Der Login-Rate-Limiter in [auth.py](auth.py) hält seinen Zustand im Prozess.
Serverless greift er nur innerhalb einer warmen Instanz und ist damit keine
verlässliche Schranke mehr. Ergänzend im Vercel-Dashboard unter
**Firewall → Rate Limiting** eine Regel auf `POST /auth/login` einrichten
(z. B. 10 Anfragen/Minute pro IP).

Ist der Gastzugang eingeschaltet (12.7), braucht `POST /auth/demo` dieselbe
Regel — dort ist sie wichtiger als beim Login: der Endpunkt ist anonym
erreichbar und jeder Aufruf legt rund 60 Zeilen in der Datenbank an.

### 12.6 Sicherheits-Tradeoff: öffentliche Blob-URLs

Vercel Blob kennt derzeit nur `access: public`. Die Foto-URLs sind damit —
wie zuvor der `/uploads`-Mount — **ohne Login abrufbar**, geschützt allein
durch nicht erratbare UUID-Dateinamen.

Der Unterschied zum Pi: dort lagen die Dateien im privaten LAN, auf Vercel
stehen sie im öffentlichen Internet. Wer eine URL kennt oder mitliest (z. B.
über einen geteilten Link oder Browser-Verlauf), sieht das Foto dauerhaft,
auch ohne Account. Für zwei Personen mit privaten Erinnerungsfotos ist das
ein bewusst akzeptierter Tradeoff — siehe auch Abschnitt 11.1.

Wenn das nicht akzeptabel ist: Bilder nicht direkt aus dem Blob-Store
verlinken, sondern über eine auth-geschützte Proxy-Route in FastAPI streamen
(`/uploads/{name}` → `get_current_user` → Blob-Fetch → `StreamingResponse`).
Kostet pro Bild eine Function-Invocation und ist bewusst nicht umgesetzt.

### 12.7 Gastzugang (Demo)

Für eine öffentliche Schau-Instanz: auf der Login-Seite erscheint "Als Gast
ansehen". Jeder Gast bekommt ein **eigenes Wegwerf-Paar** mit Beispieldaten
aus [demo_data.py](demo_data.py). Dadurch trennt dieselbe
`couple_id`-Filterung, die echte Paare schützt, auch die Gäste voneinander:
was ein Gast ändert, sieht kein anderer. Das Paar verschwindet beim Logout,
beim "Zurücksetzen" im Demo-Banner oder spätestens nach `DEMO_TTL_MINUTES`.

Standardmäßig aus. Auf dem Pi aus lassen — der bleibt privat.

**Einschalten (Vercel → Environment Variables):**

```
DEMO_ENABLED=true
DEMO_TTL_MINUTES=120
MAX_DEMO_COUPLES=200
CRON_SECRET=<python3 -c "import secrets; print(secrets.token_urlsafe(32))">
```

Vorher `alembic upgrade head` gegen die Produktions-DB laufen lassen
(Revision `c7e2d4a91b56` bringt `couples.is_demo` und `couples.expires_at`).
Ein Seed ist nicht nötig, die Demo-Bilder liegen als statische Dateien unter
`static/demo/` im Repo.

**Was ein Gast nicht darf:** Bilder hochladen (Foto, Avatar) sowie
Benutzername und Passwort ändern. Anonyme Uploads ins öffentliche Internet
hießen Blob-Kosten und fremde Inhalte unter unserer Domain. Gast-Konten
tragen außerdem keinen gültigen Passwort-Hash und sind per Login nicht
erreichbar — der einzige Weg hinein ist `POST /auth/demo`.

**Drei Schranken gegen Missbrauch — alle drei einrichten:**

1. **Firewall-Regel** auf `POST /auth/demo` (siehe 12.5). Der In-Process-
   Limiter (5 Einstiege / 5 Min pro IP) greift serverless nur innerhalb einer
   warmen Instanz.
2. **`MAX_DEMO_COUPLES`** deckelt den Bestand hart. Ist das Kontingent voll,
   wird das älteste Demo-Paar verdrängt, der neue Gast kommt trotzdem hinein.
   200 Paare entsprechen rund 12.000 Zeilen.
3. **Aufräumen:** jeder Demo-Einstieg löscht vorab bis zu 20 abgelaufene
   Paare. Zusätzlich ruft der Cron aus [vercel.json](vercel.json) einmal
   täglich `GET /internal/demo-sweep` auf, für den Fall, dass länger niemand
   kommt. Vercel schickt `CRON_SECRET` von selbst als
   `Authorization: Bearer …`. Ohne gesetztes Secret antwortet der Endpunkt
   mit 404, ist also nie offen. Der Hobby-Plan erlaubt nur tägliche Crons; ab
   Pro lässt sich der Zeitplan in `vercel.json` auf stündlich (`0 * * * *`)
   stellen.

**Prüfen nach dem Deploy:**

```bash
# Muss 404 liefern (kein Secret mitgeschickt)
curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/internal/demo-sweep

# Muss {"deleted": <n>} liefern
curl -s -H "Authorization: Bearer $CRON_SECRET" https://<domain>/internal/demo-sweep
```

**Rest-Risiko:** ein Gast kann einem Formular von Hand eine Datei anhängen.
Der Server verwirft sie, liest aber vorher bis zu 10 MB Request-Body. Das
kostet Bandbreite und Function-Zeit, gespeichert wird nichts — die
Firewall-Regel aus Punkt 1 begrenzt auch das.

**Demo-Inhalte ändern:** Texte in [demo_data.py](demo_data.py) anpassen. Die
Bilder unter `static/demo/` sind KI-generierte Fotos (Higgsfield, Modell
`nano_banana`), angelegt als unperfekte Handyfotos und ohne erkennbare
Gesichter — „Lena & Max“ gibt es nicht. Für ein neues Bild den Dateinamen in
`demo_data.py` eintragen, die Quelldatei (3:2, Motiv mittig, weil Galerie und
Baum quadratisch beschneiden) unter demselben Stamm in einen Ordner legen und
einspielen:

```bash
python scripts/import_demo_photos.py <quellordner>
```

Das Skript bringt jedes Bild auf 1200×800 JPEG, entfernt Metadaten und legt
das Thumbnail unter `static/demo/thumbs/<name>_thumb.jpg` an. Danach
`static/demo/` committen.
[scripts/make_demo_images.py](scripts/make_demo_images.py) ist nur noch der
Fallback: es zeichnet eine einfache Szene für Dateinamen, zu denen kein Bild
existiert (dafür dort eine Szene ergänzen), und lässt vorhandene Dateien in
Ruhe — `--force` überschreibt alle Fotos mit den gezeichneten Szenen. Nur
Bilder verwenden, die öffentlich sein dürfen — `/static/` ist ohne Login
abrufbar.
