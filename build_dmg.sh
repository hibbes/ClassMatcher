#!/bin/bash
# build_dmg.sh – Erstellt Schiller-Klassen-Mixer.app + DMG
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Schiller-Klassen-Mixer"
BUNDLE="$APP_NAME.app"
BUILD="/tmp/$APP_NAME-build"
STAGING="$BUILD/staging"
DMG_OUT="$(pwd)/$APP_NAME.dmg"

echo "→ Aufräumen…"
rm -rf "$BUILD" "$DMG_OUT"
mkdir -p "$STAGING/$BUNDLE/Contents/"{MacOS,Resources}

# ── Info.plist ────────────────────────────────────────────────────
cat > "$STAGING/$BUNDLE/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>               <string>Schiller-Klassen-Mixer</string>
  <key>CFBundleDisplayName</key>        <string>Schiller-Klassen-Mixer</string>
  <key>CFBundleIdentifier</key>         <string>de.schillergymnasium.klassenmixer</string>
  <key>CFBundleVersion</key>            <string>1.0.0</string>
  <key>CFBundleShortVersionString</key> <string>1.0</string>
  <key>CFBundlePackageType</key>        <string>APPL</string>
  <key>CFBundleExecutable</key>         <string>launcher</string>
  <key>CFBundleIconFile</key>           <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>     <string>12.0</string>
  <key>NSHighResolutionCapable</key>    <true/>
</dict>
</plist>
PLIST

# ── App-Icon (aus logo.png) ───────────────────────────────────────
echo "→ App-Icon erstellen…"
ICONSET="$BUILD/AppIcon.iconset"
mkdir -p "$ICONSET"
for SIZE in 16 32 128 256 512; do
    sips -z $SIZE $SIZE static/logo.png \
        --out "$ICONSET/icon_${SIZE}x${SIZE}.png"     &>/dev/null
    DOUBLE=$((SIZE * 2))
    sips -z $DOUBLE $DOUBLE static/logo.png \
        --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png"  &>/dev/null
done
iconutil -c icns "$ICONSET" \
    -o "$STAGING/$BUNDLE/Contents/Resources/AppIcon.icns"

# ── Launcher-Script ───────────────────────────────────────────────
cat > "$STAGING/$BUNDLE/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
# Schiller-Klassen-Mixer – Starter
APP_NAME="Schiller-Klassen-Mixer"
PORT=5001
SUPPORT="$HOME/Library/Application Support/$APP_NAME"
VENV="$SUPPORT/.venv"
RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"
LOG="$SUPPORT/server.log"

mkdir -p "$SUPPORT"

# ── Python prüfen ─────────────────────────────────────────────────
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -z "$PY" ]; then
    osascript -e 'display alert "Python 3 nicht gefunden" message "Bitte installieren Sie Python 3 von python.org und starten Sie das Programm erneut." as critical with title "Schiller-Klassen-Mixer"'
    exit 1
fi
# Sicherstellen dass es Python 3 ist
PY_VER=$("$PY" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
if [ "$PY_VER" != "3" ]; then
    osascript -e 'display alert "Python 3 benötigt" message "Nur Python 3 wird unterstützt. Bitte installieren Sie Python 3 von python.org." as critical with title "Schiller-Klassen-Mixer"'
    exit 1
fi

# ── Ersteinrichtung (einmalig, ca. 30 Sek.) ──────────────────────
if [ ! -f "$VENV/bin/python" ]; then
    osascript -e 'display notification "Ersteinrichtung läuft – bitte warten (ca. 30 Sekunden)…" with title "Schiller-Klassen-Mixer"'
    "$PY" -m venv "$VENV" &>>"$LOG" || {
        osascript -e 'display alert "Einrichtungsfehler" message "Die Programmumgebung konnte nicht erstellt werden.\n\nDetails: ~/Library/Application Support/Schiller-Klassen-Mixer/server.log" as critical with title "Schiller-Klassen-Mixer"'
        exit 1
    }
    "$VENV/bin/pip" install --upgrade pip --quiet &>>"$LOG"
    "$VENV/bin/pip" install flask --quiet &>>"$LOG" || {
        osascript -e 'display alert "Installationsfehler" message "Benötigte Komponenten konnten nicht installiert werden.\n\nBitte Internetverbindung prüfen und neu starten." as critical with title "Schiller-Klassen-Mixer"'
        rm -rf "$VENV"
        exit 1
    }
    osascript -e 'display notification "Einrichtung abgeschlossen." with title "Schiller-Klassen-Mixer"'
fi

# ── Laufende Instanz beenden ──────────────────────────────────────
lsof -ti:$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 0.4

# ── Server starten ────────────────────────────────────────────────
cd "$RESOURCES"
"$VENV/bin/python" app.py &>>"$LOG" &
SERVER_PID=$!

# Server beim Beenden des Launchers automatisch stoppen
trap 'kill "$SERVER_PID" 2>/dev/null; exit' EXIT INT TERM

# Warten bis Server bereit
sleep 1.5
if ! lsof -ti:$PORT &>/dev/null; then
    osascript -e 'display alert "Startfehler" message "Der Server konnte nicht gestartet werden.\n\nDetails: ~/Library/Application Support/Schiller-Klassen-Mixer/server.log" as critical with title "Schiller-Klassen-Mixer"'
    exit 1
fi

open "http://localhost:$PORT"

# ── Status-Fenster (hält den Server am Laufen) ───────────────────
while true; do
    BUTTON=$(osascript << 'OSASCRIPT'
set btn to button returned of (display dialog ¬
    "Schiller-Klassen-Mixer läuft.

Der Browser ist geöffnet. Lassen Sie dieses Fenster offen, solange Sie arbeiten.

Hinweis: Alle Daten verbleiben nur im Arbeitsspeicher – die CSV-Datei sicher aufbewahren oder mit '↓ Speichern' einen Stand sichern." ¬
    buttons {"Browser öffnen", "Programm beenden"} ¬
    default button "Browser öffnen" ¬
    with title "Schiller-Klassen-Mixer" ¬
    with icon note)
btn
OSASCRIPT
    )
    [ "$BUTTON" = "Programm beenden" ] && break
    open "http://localhost:$PORT"
done
# trap beendet den Server
LAUNCHER

chmod +x "$STAGING/$BUNDLE/Contents/MacOS/launcher"

# ── Quellcode in Resources kopieren ──────────────────────────────
echo "→ Programmdateien kopieren…"
cp app.py matcher.py "$STAGING/$BUNDLE/Contents/Resources/"
cp -r static "$STAGING/$BUNDLE/Contents/Resources/"

# ── DMG erstellen ─────────────────────────────────────────────────
echo "→ DMG erstellen…"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DMG_OUT"

rm -rf "$BUILD"

echo ""
echo "✅ Fertig: $DMG_OUT"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Wichtig für die Kollegin (einmalig, wegen fehlender Signierung):"
echo "  → Nicht doppelklicken, sondern: Rechtsklick → Öffnen → Öffnen"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
open -R "$DMG_OUT"
