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
