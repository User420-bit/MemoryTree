#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# Memory Tree — Backup-Script
# Sichert SQLite-Datenbank (online-safe) und Uploads.
# Nutzt SQLite .backup Kommando für konsistente DB-Kopie.
#
# Nutzung:
#   ./scripts/backup.sh
#   ./scripts/backup.sh /pfad/zum/backup/ziel
#
# Crontab-Beispiel (täglich um 3:00):
#   0 3 * * * /home/pi/memory-tree/scripts/backup.sh >> /var/log/memory-tree-backup.log 2>&1
# ──────────────────────────────────────────────────────────
set -euo pipefail

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_BASE="${1:-${PROJECT_DIR}/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_BASE}/${TIMESTAMP}"

# Docker Volume Name (Standard compose.yaml)
VOLUME_NAME="memorytree_app-data"

# Quellpfade (innerhalb Docker Volume oder lokal)
DB_SOURCE="${PROJECT_DIR}/data/memory_tree.db"
UPLOADS_SOURCE="${PROJECT_DIR}/data/uploads"

# Anzahl aufbewahrter Backups
MAX_BACKUPS=7

echo "=== Memory Tree Backup: $(date) ==="

# Backup-Verzeichnis erstellen
mkdir -p "${BACKUP_DIR}"

# ── SQLite-Datenbank sicher sichern ──────────────────────────────────────────
# Methode 1: Wenn Docker läuft, über docker exec
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "memory-tree-app"; then
    echo "→ SQLite-Backup via Docker (online-safe)..."
    docker exec memory-tree-app sqlite3 /app/data/memory_tree.db ".backup '/tmp/backup.db'"
    docker cp memory-tree-app:/tmp/backup.db "${BACKUP_DIR}/memory_tree.db"
    docker exec memory-tree-app rm -f /tmp/backup.db
# Methode 2: Lokal, falls DB direkt zugänglich
elif [ -f "${DB_SOURCE}" ]; then
    echo "→ SQLite-Backup lokal (online-safe)..."
    sqlite3 "${DB_SOURCE}" ".backup '${BACKUP_DIR}/memory_tree.db'"
else
    echo "FEHLER: Datenbank nicht gefunden!"
    exit 1
fi

echo "  ✓ Datenbank gesichert"

# ── Uploads sichern ──────────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "memory-tree-app"; then
    echo "→ Uploads via Docker Volume kopieren..."
    docker run --rm \
        -v "${VOLUME_NAME}:/source:ro" \
        -v "${BACKUP_DIR}:/backup" \
        alpine sh -c "cp -a /source/uploads /backup/uploads 2>/dev/null || echo 'Keine Uploads vorhanden'"
elif [ -d "${UPLOADS_SOURCE}" ]; then
    echo "→ Uploads lokal kopieren..."
    cp -a "${UPLOADS_SOURCE}" "${BACKUP_DIR}/uploads"
else
    echo "  ⚠ Kein Upload-Verzeichnis gefunden, überspringe"
fi

echo "  ✓ Uploads gesichert"

# ── Backup komprimieren ──────────────────────────────────────────────────────
echo "→ Komprimiere Backup..."
tar -czf "${BACKUP_BASE}/memory-tree-${TIMESTAMP}.tar.gz" -C "${BACKUP_BASE}" "${TIMESTAMP}"
rm -rf "${BACKUP_DIR}"
echo "  ✓ Komprimiert: memory-tree-${TIMESTAMP}.tar.gz"

# ── Alte Backups rotieren ────────────────────────────────────────────────────
echo "→ Rotiere alte Backups (behalte letzte ${MAX_BACKUPS})..."
cd "${BACKUP_BASE}"
ls -1t memory-tree-*.tar.gz 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f
echo "  ✓ Rotation abgeschlossen"

# ── Backup-Größe anzeigen ───────────────────────────────────────────────────
SIZE=$(du -sh "${BACKUP_BASE}/memory-tree-${TIMESTAMP}.tar.gz" | cut -f1)
echo ""
echo "=== Backup abgeschlossen: ${SIZE} ==="
echo "    Datei: ${BACKUP_BASE}/memory-tree-${TIMESTAMP}.tar.gz"

# ── Offsite-Sync (optional, auskommentiert) ──────────────────────────────────
# rsync -avz "${BACKUP_BASE}/" user@remote:/backups/memory-tree/
# rclone copy "${BACKUP_BASE}/memory-tree-${TIMESTAMP}.tar.gz" remote:backups/memory-tree/
# aws s3 cp "${BACKUP_BASE}/memory-tree-${TIMESTAMP}.tar.gz" s3://my-bucket/memory-tree/
