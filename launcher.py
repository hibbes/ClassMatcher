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
    # threaded=True ist Pflicht: der Auto-Update-Download laeuft synchron in
    # einem Request-Handler und blockiert sonst (Single-Thread-Werkzeug) den
    # einzigen Worker. Dann werden die 15s-Heartbeats nicht mehr beantwortet und
    # der 30s-Watchdog killt die App mitten im Download (gerade auf langsamen/
    # Proxy-Schulnetzen). Mit threaded=True laufen Heartbeat und Download neben-
    # einander.
    flask_app.app.run(
        host="127.0.0.1", port=PORT, debug=False, use_reloader=False,
        threaded=True,
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


def _try_bind_port() -> bool:
    """True wenn PORT aktuell frei und sofort gebindet werden koennte."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pid_on_port():
    """PID, der PORT belegt — oder None. Plattform-Heuristik."""
    try:
        if SYSTEM in ("Darwin", "Linux"):
            out = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{PORT}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=3,
            )
            pids = [int(x) for x in out.stdout.strip().splitlines() if x.strip().isdigit()]
            return pids[0] if pids else None
        if SYSTEM == "Windows":
            out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=3,
            )
            for line in out.stdout.splitlines():
                if f":{PORT}" in line and "LISTENING" in line.upper():
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        return int(parts[-1])
    except Exception:
        pass
    return None


def _process_is_own(pid: int) -> bool:
    """True wenn PID nach 'Schiller-Klassen-Mixer' aussieht — Pythonsuffix
    auch (Dev-Mode), damit ein vergessener python launcher.py erkannt wird."""
    try:
        if SYSTEM in ("Darwin", "Linux"):
            out = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True, text=True, timeout=2,
            )
            txt = out.stdout.lower()
            return ("klassen-mixer" in txt
                    or "schiller-klassen-mixer" in txt
                    or "launcher.py" in txt)
        if SYSTEM == "Windows":
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=2,
            )
            return "klassen-mixer" in out.stdout.lower()
    except Exception:
        pass
    return False


def _kill_pid(pid: int):
    try:
        if SYSTEM == "Windows":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=3)
        else:
            os.kill(pid, 9)
    except Exception:
        pass


def _ensure_port_free():
    """Sorgt dafuer, dass PORT frei ist. Returns (ok, reason).
    ok=False mit reason!='' = Konflikt mit fremdem Prozess (User informieren).
    ok=True = Port jetzt frei. Eigene alte Instanz wurde ggf. gekillt."""
    if _try_bind_port():
        return True, ""
    pid = _pid_on_port()
    if pid is None:
        # Port belegt, aber kein PID ermittelbar — Best-Effort: 1s warten,
        # nochmal probieren (OS-Cleanup nach Crash kann ein paar Sek dauern).
        time.sleep(1.0)
        if _try_bind_port():
            return True, ""
        return False, f"Port {PORT} ist belegt (Prozess unbekannt)."
    if _process_is_own(pid):
        _kill_pid(pid)
        for _ in range(20):  # bis zu 4s warten
            time.sleep(0.2)
            if _try_bind_port():
                return True, ""
        return False, f"Alte Instanz (PID {pid}) liess sich nicht beenden."
    return False, (f"Port {PORT} ist von einem fremden Programm belegt "
                   f"(PID {pid}). Bitte schliesse es und starte neu.")


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
    # Falls vom Auto-Update ein .exe.old vom Vorlauf-Build noch herumliegt,
    # gleich beim Start aufräumen (best-effort, schlägt nie fehl).
    try:
        import update as _update
        _update.cleanup_old_exe()
    except Exception:
        pass

    # Pre-Launch: sicherstellen, dass Port frei ist. Alte eigene Instanzen
    # werden automatisch gekillt; fremde Prozesse meldet der Alert.
    ok, reason = _ensure_port_free()
    if not ok:
        _alert("Startfehler", reason)
        sys.exit(1)

    # Flask-Server im Daemon-Thread starten
    threading.Thread(target=_run_flask, daemon=True).start()

    if not _wait_for_server():
        _alert("Startfehler", "Der Server konnte nicht gestartet werden.")
        sys.exit(1)

    webbrowser.open(f"http://localhost:{PORT}")
    _notify("Bereit – zum Beenden das Programm schließen.")

    # Hauptthread blockieren (hält den Daemon-Thread am Leben)
    threading.Event().wait()
