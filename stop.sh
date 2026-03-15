#!/usr/bin/env bash
# ──────────────────────────────────────────────
# 🌳 Memory Tree — Stop-Skript
# Beendet den laufenden Uvicorn-Prozess sauber.
# ──────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Alle Uvicorn-Prozesse auf Port 8000 finden
PIDS=$(lsof -ti:8000 2>/dev/null || true)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}⚠️  Kein laufender Memory Tree Server gefunden (Port 8000 ist frei).${NC}"
    exit 0
fi

# Prozesse sauber beenden (SIGTERM), nach 3s erzwingen (SIGKILL)
echo "$PIDS" | xargs kill -15 2>/dev/null || true
sleep 1

# Prüfen ob noch aktiv
REMAINING=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$REMAINING" ]; then
    echo "$REMAINING" | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo -e "${GREEN}✅ Memory Tree Server gestoppt.${NC}"
