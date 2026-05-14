"""
ClassMatcher – Auto-Update
Prüft die Schul-Homepage auf eine neuere Version und lädt sie herunter.
Reines stdlib, keine zusätzliche Dependency. Jeder Netz-Fehler ist gnädig:
der Check liefert dann einfach "kein Update", die App läuft normal weiter.

Das sys.frozen-Gate (kein Updater wenn aus dem Quellcode gestartet) sitzt
bewusst in der Flask-Route, damit dieses Modul rein + testbar bleibt.
"""
import json
import platform
import urllib.request
from pathlib import Path

MANIFEST_URL = "https://schiller-offenburg.de/classmatcher/version.json"
_CONFIG_PATH = Path.home() / ".classmatcher.cfg"
_TIMEOUT = 4            # Sekunden – Manifest-Check
_DOWNLOAD_TIMEOUT = 60  # Sekunden pro Lese-Block beim Binary-Download


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


def download_update(download_url: str, *, _config=_read_local_config) -> dict:
    """Lädt das Binary nach ~/Downloads/. Liefert {ok: True, path} bzw.
    bei jedem Fehler {ok: False, fallback_url} (→ Browser-Fallback im UI)."""
    try:
        cfg = _config()
        filename = download_url.rsplit("/", 1)[-1] or "ClassMatcher-Update"
        target_dir = Path.home() / "Downloads"
        target_dir.mkdir(parents=True, exist_ok=True)
        final = target_dir / filename
        part = final.parent / (final.name + ".part")
        with _opener(cfg).open(download_url, timeout=_DOWNLOAD_TIMEOUT) as resp, \
                open(part, "wb") as fh:
            while chunk := resp.read(65536):
                fh.write(chunk)
        part.replace(final)
        return {"ok": True, "path": str(final)}
    except Exception:
        return {"ok": False, "fallback_url": download_url}
