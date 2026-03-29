@echo off
REM ================================================================
REM  build_windows.bat – Schiller-Klassen-Mixer Windows-Build
REM  Voraussetzung: Python 3.10+ installiert (python.org)
REM  Ausfuehren: Doppelklick oder im Terminal: build_windows.bat
REM ================================================================
setlocal enabledelayedexpansion

set APP=Schiller-Klassen-Mixer
set OUTZIP=%APP%-Windows.zip

echo.
echo ====================================================
echo  %APP% – Windows-Build
echo ====================================================
echo.

REM ── Python pruefen ───────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python nicht gefunden.
    echo Bitte Python 3.10+ von https://www.python.org installieren.
    echo Wichtig: Beim Installieren "Add Python to PATH" aktivieren.
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [FEHLER] Python 3.10 oder neuer wird benoetigt.
    python --version
    pause
    exit /b 1
)

echo [OK] Python gefunden:
python --version

REM ── Virtuelle Umgebung ───────────────────────────────
echo.
echo [1/5] Virtuelle Umgebung erstellen...
if exist ".venv-win" rmdir /s /q ".venv-win"
python -m venv .venv-win
if errorlevel 1 (
    echo [FEHLER] Virtuelle Umgebung konnte nicht erstellt werden.
    pause
    exit /b 1
)

REM ── Abhaengigkeiten installieren ─────────────────────
echo [2/5] Abhaengigkeiten installieren (Flask, PyInstaller, Pillow)...
.venv-win\Scripts\pip install --upgrade pip --quiet
.venv-win\Scripts\pip install flask pyinstaller pillow --quiet
if errorlevel 1 (
    echo [FEHLER] Installation fehlgeschlagen. Internetverbindung pruefen.
    pause
    exit /b 1
)

REM ── Icon konvertieren (PNG -> ICO) ───────────────────
echo [3/5] App-Icon erstellen...
.venv-win\Scripts\python -c "from PIL import Image; img = Image.open('static/logo.png'); img.save('static/logo.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if errorlevel 1 (
    echo [WARNUNG] Icon-Konvertierung fehlgeschlagen – Build laeuft ohne Icon weiter.
)

REM ── PyInstaller-Build ────────────────────────────────
echo [4/5] App-Bundle erstellen (kann 1-2 Minuten dauern)...
if exist "dist\%APP%" rmdir /s /q "dist\%APP%"
if exist "build" rmdir /s /q "build"

.venv-win\Scripts\pyinstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "%APP%" ^
    --icon "static\logo.ico" ^
    --add-data "static;static" ^
    --add-data "app.py;." ^
    --add-data "matcher.py;." ^
    launcher.py

if errorlevel 1 (
    echo [FEHLER] PyInstaller-Build fehlgeschlagen.
    pause
    exit /b 1
)

REM ── ZIP erstellen ────────────────────────────────────
echo [5/5] ZIP-Archiv erstellen...
if exist "%OUTZIP%" del "%OUTZIP%"
powershell -command "Compress-Archive -Path 'dist\%APP%' -DestinationPath '%OUTZIP%'"
if errorlevel 1 (
    echo [WARNUNG] ZIP konnte nicht erstellt werden.
    echo Das fertige Programm liegt in: dist\%APP%\
) else (
    echo.
    echo ====================================================
    echo  Fertig: %OUTZIP%
    echo ====================================================
    echo.
    echo Weitergabe: ZIP-Datei entpacken, dann
    echo    %APP%\%APP%.exe  starten.
    echo.
    echo Hinweis: Beim ersten Start meldet Windows Defender
    echo moeglicherweise eine Warnung (unbekannter Herausgeber).
    echo Dann: "Weitere Informationen" -> "Trotzdem ausfuehren".
    echo ====================================================
)

REM ── Aufraeumen ───────────────────────────────────────
if exist "static\logo.ico" del "static\logo.ico"
if exist "%APP%.spec" del "%APP%.spec"

echo.
pause
