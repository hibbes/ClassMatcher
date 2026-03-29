#!/bin/bash
set -e
cd "$(dirname "$0")"

# Virtual Environment anlegen falls nicht vorhanden
if [ ! -d ".venv" ]; then
    echo "Erstelle Virtual Environment…"
    python3 -m venv .venv
fi

# Aktivieren
source .venv/bin/activate

# Flask installieren falls nicht vorhanden
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installiere Flask…"
    pip install -q flask
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        ClassMatcher startet          ║"
echo "╠══════════════════════════════════════╣"
echo "║  → http://localhost:5001             ║"
echo "║  Browser öffnet sich gleich          ║"
echo "║  Beenden mit Ctrl+C                  ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Browser öffnen (nach kurzer Verzögerung)
(sleep 1.2 && open "http://localhost:5001") &

python3 app.py
