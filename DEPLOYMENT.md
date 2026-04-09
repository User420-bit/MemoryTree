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
