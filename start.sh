#!/usr/bin/env bash
# ──────────────────────────────────────────────
# 🌳 Memory Tree — Start-Skript (macOS / Linux)
# Richtet beim ersten Start alles automatisch ein.
# ──────────────────────────────────────────────
set -euo pipefail

# ── Arbeitsverzeichnis = Skript-Verzeichnis ──
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# ── Farben ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}ℹ ${NC}$1"; }
ok()    { echo -e "${GREEN}✅ ${NC}$1"; }
warn()  { echo -e "${YELLOW}⚠️  ${NC}$1"; }
fail()  { echo -e "${RED}❌ ${NC}$1"; exit 1; }

# ── 1. Python-Version prüfen ──
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.11+ wird benötigt, wurde aber nicht gefunden.\n   Installiere Python: https://www.python.org/downloads/"
fi
ok "Python gefunden: $($PYTHON --version)"

# ── 2. Virtuelle Umgebung ──
if [ ! -d ".venv" ]; then
    info "Erstelle virtuelle Umgebung (.venv) ..."
    "$PYTHON" -m venv .venv
    ok "Virtuelle Umgebung erstellt"
else
    ok "Virtuelle Umgebung vorhanden"
fi

# Aktivieren
source .venv/bin/activate

# ── 3. Abhängigkeiten installieren ──
info "Prüfe Abhängigkeiten ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Alle Pakete installiert"

# ── 4. .env prüfen ──
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn "Keine .env gefunden — wurde aus .env.example erstellt."
    warn "Bitte passe SECRET_KEY in .env an, bevor du die App produktiv nutzt!"
else
    ok ".env vorhanden"
fi

# ── 5. Upload-Verzeichnis sicherstellen ──
mkdir -p static/uploads static/css static/js static/img

# ── 6. Server starten ──
echo ""
echo -e "${BOLD}┌─────────────────────────────────────┐${NC}"
echo -e "${BOLD}│  🌳 Memory Tree wird gestartet ...  │${NC}"
echo -e "${BOLD}│                                     │${NC}"
echo -e "${BOLD}│  → ${CYAN}http://localhost:8000${NC}${BOLD}             │${NC}"
echo -e "${BOLD}│  → Stoppen: ${YELLOW}CTRL+C${NC}${BOLD}                 │${NC}"
echo -e "${BOLD}│                                     │${NC}"
echo -e "${BOLD}│  Zugangsdaten (Standard):            │${NC}"
echo -e "${BOLD}│  Benutzer: ${CYAN}partner_a${NC}${BOLD} / ${CYAN}partner_b${NC}${BOLD}    │${NC}"
echo -e "${BOLD}│  Passwort: ${CYAN}test1234${NC}${BOLD}                 │${NC}"
echo -e "${BOLD}└─────────────────────────────────────┘${NC}"
echo ""

# Browser nach kurzer Verzögerung öffnen (im Hintergrund)
(sleep 2 && open "http://localhost:8000" 2>/dev/null || xdg-open "http://localhost:8000" 2>/dev/null) &

# Uvicorn starten (blockiert bis CTRL+C)
exec uvicorn main:app --reload --host 0.0.0.0 --port 8000
