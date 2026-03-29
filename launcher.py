"""
Schiller-Klassen-Mixer – PyInstaller-Einstiegspunkt
Startet den Flask-Server im Hintergrund, öffnet den Browser.
Läuft auf macOS (Dock) und Windows (Taskleiste / Tray).
"""
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import webbrowser

PORT = 5001
SYSTEM = platform.system()  # "Darwin" | "Windows" | "Linux"

# Arbeitsverzeichnis = Verzeichnis mit app.py / static/
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)


def _run_flask():
    import app as flask_app
    flask_app.app.run(
        host="127.0.0.1", port=PORT, debug=False, use_reloader=False
    )


def _wait_for_server(timeout: int = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _notify(msg: str):
    """Kurze System-Benachrichtigung (nicht-blockierend, optional)."""
    try:
        if SYSTEM == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{msg}" with title "Schiller-Klassen-Mixer"'],
                capture_output=True
            )
        # Windows: keine native API ohne Drittbibliothek – stillschweigend ignorieren
    except Exception:
        pass


def _alert(title: str, msg: str):
    """Blockierender Fehler-Dialog."""
    try:
        if SYSTEM == "Darwin":
            subprocess.run(
                ["osascript", "-e",
                 f'display alert "{title}" message "{msg}" as critical'
                 f' with title "Schiller-Klassen-Mixer"'],
                capture_output=True
            )
        elif SYSTEM == "Windows":
            import ctypes
            # MB_OK | MB_ICONERROR = 0x10
            ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
        else:
            print(f"[FEHLER] {title}: {msg}", file=sys.stderr)
    except Exception:
        print(f"[FEHLER] {title}: {msg}", file=sys.stderr)


if __name__ == "__main__":
    # Flask-Server im Daemon-Thread starten
    threading.Thread(target=_run_flask, daemon=True).start()

    if not _wait_for_server():
        _alert("Startfehler", "Der Server konnte nicht gestartet werden.")
        sys.exit(1)

    webbrowser.open(f"http://localhost:{PORT}")
    _notify("Bereit – zum Beenden das Programm schließen.")

    # Hauptthread blockieren (hält den Daemon-Thread am Leben)
    threading.Event().wait()
