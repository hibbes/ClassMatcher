"""
ClassMatcher – Auto-Update
Prüft die Schul-Homepage auf eine neuere Version und lädt sie herunter.
Auf Windows zusätzlich: tauscht die laufende EXE direkt am Speicherort
gegen die neue aus (Windows erlaubt Umbenennen der laufenden .exe).
Reines stdlib, keine zusätzliche Dependency. Jeder Netz- oder IO-Fehler
ist gnädig: der Check liefert dann einfach "kein Update", die App läuft
normal weiter.

Das sys.frozen-Gate (kein Updater wenn aus dem Quellcode gestartet) sitzt
bewusst in der Flask-Route, damit dieses Modul rein + testbar bleibt.
"""
import json
import platform
import shutil
import sys
import urllib.request
from pathlib import Path

# Wichtig: `www.`-Subdomain verwenden, sonst macht Mittwald 301 von
# https://schiller-offenburg.de/... auf http://www.schiller-offenburg.de/...
# (HTTPS->HTTP-Downgrade), den Python's urllib unter PyInstaller-Bundle
# nicht zulaesst. Mit `www.` 200 OK direkt ohne Redirect.
MANIFEST_URL = "https://www.schiller-offenburg.de/classmatcher/version.json"
_CONFIG_PATH = Path.home() / ".classmatcher.cfg"
_TIMEOUT = 4            # Sekunden – Manifest-Check
_DOWNLOAD_TIMEOUT = 60  # Sekunden Socket-Idle-Timeout beim Binary-Download


def _read_local_config() -> dict:
    """Optionale key=value-Zeilen aus ~/.classmatcher.cfg.
    Erkannte Schlüssel: proxy, update_check. Datei fehlt → leeres dict."""
    cfg: dict = {}
    try:
        for line in _CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            cfg[key.strip().lower()] = val.strip()
    except OSError:
        pass
    return cfg


def _parse_version(s) -> tuple:
    """'1.5.10' → (1, 5, 10). Kaputte Eingabe → () (vergleicht als 'kleiner als alles')."""
    try:
        return tuple(int(p) for p in str(s).strip().split("."))
    except (ValueError, AttributeError):
        return ()


def _opener(cfg: dict):
    """urllib-Opener: expliziter Proxy aus der Config, sonst System-Proxy
    (ProxyHandler() ohne Args nutzt urllib.request.getproxies())."""
    proxy = cfg.get("proxy")
    handler = (urllib.request.ProxyHandler({"http": proxy, "https": proxy})
               if proxy else urllib.request.ProxyHandler())
    return urllib.request.build_opener(handler)


def _fetch_manifest(cfg: dict) -> dict:
    """Holt + parst version.json. Wirft bei jedem Problem (Netz, JSON, Proxy)."""
    with _opener(cfg).open(MANIFEST_URL, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(current_version: str, *,
                     _fetcher=_fetch_manifest,
                     _config=_read_local_config) -> dict:
    """Prüft auf eine neuere Version. Liefert IMMER ein dict, wirft nie.

    Rückgabe: {update_available, current, latest, download_url, notes}.
    Bei deaktiviertem Check oder jedem Fehler: update_available=False.
    Die Unterstrich-Parameter sind Test-Nahtstellen.
    """
    result = {"update_available": False, "current": current_version,
              "latest": None, "download_url": None, "notes": None}

    cfg = _config()
    if cfg.get("update_check", "").lower() in ("off", "false", "0", "no"):
        return result

    try:
        manifest = _fetcher(cfg)
        latest = str(manifest["version"])
        url = manifest["mac_url" if platform.system() == "Darwin" else "win_url"]
    except Exception:
        return result  # offline, Proxy, 404, kaputtes JSON, fehlender Key → gnädig

    result["latest"] = latest
    result["notes"] = manifest.get("notes")

    cur, new = _parse_version(current_version), _parse_version(latest)
    if cur and new and new > cur:
        result["update_available"] = True
        result["download_url"] = url
    return result


def download_update(download_url: str, *,
                    _config=_read_local_config,
                    _opener_factory=_opener,
                    _target_dir=None,
                    _installer=None) -> dict:
    """Lädt das Binary nach ~/Downloads/ und installiert es auf Windows
    direkt am laufenden EXE-Pfad (Rename-Tausch). Auf Mac bleibt es bei
    "Datei liegt in Downloads, User zieht App in /Applications".

    Rückgabe:
      {ok: True, path: str, installed: bool}
        - installed=True  → laufende EXE wurde getauscht, neue ist beim
          nächsten Start aktiv (Windows-Pfad)
        - installed=False → Datei in Downloads, manueller Schritt
          erwartet (Mac-Pfad oder Windows ohne sys.frozen oder Rename-
          Fehler)
      {ok: False, fallback_url} bei Netz-/IO-Fehler im Download

    Die Unterstrich-Parameter sind Test-Nahtstellen."""
    part = None
    try:
        cfg = _config()
        filename = download_url.rsplit("/", 1)[-1] or "ClassMatcher-Update"
        target_dir = Path(_target_dir) if _target_dir is not None else Path.home() / "Downloads"
        target_dir.mkdir(parents=True, exist_ok=True)
        final = target_dir / filename
        part = final.parent / (final.name + ".part")
        with _opener_factory(cfg).open(download_url, timeout=_DOWNLOAD_TIMEOUT) as resp, \
                open(part, "wb") as fh:
            while chunk := resp.read(65536):
                fh.write(chunk)
        part.replace(final)

        installer = _installer if _installer is not None else install_windows
        installed = bool(installer(final))
        return {"ok": True, "path": str(final), "installed": installed}
    except Exception:
        if part is not None:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
        return {"ok": False, "fallback_url": download_url}


def install_windows(new_exe_path) -> bool:
    """Tauscht die laufende EXE am sys.executable-Pfad gegen new_exe_path.
    Liefert True bei Erfolg, False bei jedem Problem (kein frozen-Bundle,
    Schreibrechte fehlen, falsche Plattform). Der Aufrufer behandelt
    False als "manueller Tausch erforderlich" und zeigt entsprechende
    UI."""
    if platform.system() != "Windows":
        return False
    if not getattr(sys, "frozen", False):
        return False  # aus Source gestartet, kein Tausch sinnvoll
    new_path = Path(new_exe_path)
    if not new_path.is_file() or new_path.suffix.lower() != ".exe":
        return False
    try:
        current = Path(sys.executable).resolve()
        old = current.with_suffix(".exe.old")
        # Restliche .old-Reste aus früherem Update aufräumen (best-effort).
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass
        # Windows lässt das Umbenennen der eigenen laufenden EXE zu.
        current.rename(old)
        # Neue EXE an exakt den Pfad legen, an dem die alte war.
        shutil.move(str(new_path), str(current))
        return True
    except Exception:
        return False


def cleanup_old_exe() -> None:
    """Beim App-Start: alte EXE-Reste vom letzten Update löschen. Best-
    effort, jeder Fehler wird stillschweigend ignoriert."""
    if platform.system() != "Windows" or not getattr(sys, "frozen", False):
        return
    try:
        old = Path(sys.executable).resolve().with_suffix(".exe.old")
        old.unlink(missing_ok=True)
    except Exception:
        pass
