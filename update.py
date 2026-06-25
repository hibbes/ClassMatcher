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
import hashlib
import json
import platform
import shutil
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# certifi bundlet ein Mozilla-CA-Bundle und ist Pflicht im PyInstaller-Build:
# der gebuendelte Python hat sonst keine erreichbaren System-CAs (auf Mac/Win
# greift PyInstaller die Plattform-Trust-Stores nicht automatisch ab), und
# HTTPS-Requests scheitern still mit CERTIFICATE_VERIFY_FAILED. Im Source-
# Mode ohne installiertes certifi fallen wir auf den System-Default zurueck.
try:
    import certifi
    _CA_FILE = certifi.where()
except Exception:
    _CA_FILE = None

# Wichtig: `www.`-Subdomain verwenden, sonst macht Mittwald 301 von
# https://schiller-offenburg.de/... auf http://www.schiller-offenburg.de/...
# (HTTPS->HTTP-Downgrade), den Python's urllib unter PyInstaller-Bundle
# nicht zulaesst. Mit `www.` 200 OK direkt ohne Redirect.
MANIFEST_URL = "https://www.schiller-offenburg.de/classmatcher/version.json"
# Download-URLs aus dem Manifest duerfen ausschliesslich von hier kommen:
# HTTPS auf die Schul-Homepage. Das verhindert, dass eine manipulierte
# Antwort (oder ein vom Client untergeschobener Wert) das Binary von einem
# fremden Host oder ueber unverschluesseltes HTTP zieht.
_ALLOWED_SCHEMES = ("https",)
_ALLOWED_HOSTS = (urlparse(MANIFEST_URL).hostname,)  # ("www.schiller-offenburg.de",)
_CONFIG_PATH = Path.home() / ".classmatcher.cfg"
# Diagnose-Log plattformuebergreifend: tempfile.gettempdir() liefert /tmp auf
# Unix und %TEMP% (existierend + schreibbar) auf Windows. Frueher war /tmp
# hartkodiert, das es auf Windows (der Zielplattform fuer Auto-Update) nicht
# gibt, weshalb dort nie ein Log entstand und die Schul-PC-Fehler blind blieben.
_LOG_PATH = Path(tempfile.gettempdir()) / "classmatcher-update.log"
_TIMEOUT = 12           # Sekunden, Manifest-Check (grosszuegig fuer langsame/Proxy-Schulnetze; Download nutzt _DOWNLOAD_TIMEOUT)
_DOWNLOAD_TIMEOUT = 60  # Sekunden Socket-Idle-Timeout beim Binary-Download


def url_is_allowed(url) -> bool:
    """True, wenn url HTTPS ist und auf einen freigegebenen Host zeigt.
    Verteidigt gegen HTTP-Downgrade und Download von fremden Hosts."""
    try:
        parsed = urlparse(str(url))
    except (ValueError, AttributeError):
        return False
    return (parsed.scheme in _ALLOWED_SCHEMES
            and parsed.hostname in _ALLOWED_HOSTS)


def _log_update(msg: str) -> None:
    """Best-effort-Diagnose-Log nach _LOG_PATH (System-Temp, plattformueberg.);
    jeder Fehler wird verschluckt."""
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(msg.rstrip("\n") + "\n")
    except Exception:
        pass


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
    """urllib-Opener mit explizitem CA-Bundle + Proxy-Behandlung.

    SSL-Context nutzt certifi's CA-Bundle (sofern verfuegbar), damit
    HTTPS-Verifizierung im PyInstaller-Bundle funktioniert. Proxy
    kommt aus der Config oder vom System (ProxyHandler() ohne Args
    nutzt urllib.request.getproxies())."""
    if _CA_FILE:
        ctx = ssl.create_default_context(cafile=_CA_FILE)
    else:
        ctx = ssl.create_default_context()
    https_handler = urllib.request.HTTPSHandler(context=ctx)
    proxy = cfg.get("proxy")
    proxy_handler = (urllib.request.ProxyHandler({"http": proxy, "https": proxy})
                     if proxy else urllib.request.ProxyHandler())
    return urllib.request.build_opener(proxy_handler, https_handler)


def _fetch_manifest(cfg: dict) -> dict:
    """Holt + parst version.json. Wirft bei jedem Problem (Netz, JSON, Proxy)."""
    with _opener(cfg).open(MANIFEST_URL, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(current_version: str, *,
                     _fetcher=_fetch_manifest,
                     _config=_read_local_config) -> dict:
    """Prüft auf eine neuere Version. Liefert IMMER ein dict, wirft nie.

    Rückgabe: {update_available, current, latest, download_url, notes, sha256}.
    Bei deaktiviertem Check oder jedem Fehler: update_available=False.
    Die Unterstrich-Parameter sind Test-Nahtstellen.
    """
    result = {"update_available": False, "current": current_version,
              "latest": None, "download_url": None, "notes": None,
              "sha256": None}

    cfg = _config()
    if cfg.get("update_check", "").lower() in ("off", "false", "0", "no"):
        return result

    try:
        manifest = _fetcher(cfg)
        latest = str(manifest["version"])
        url = manifest["mac_url" if platform.system() == "Darwin" else "win_url"]
    except Exception as _e:
        # Diagnose-Log (best-effort): wird gebraucht, solange Auto-Update auf
        # manchen Schul-PCs noch nicht klappt. Schreibt nach _LOG_PATH (System-
        # Temp, damit es auch auf Windows entsteht).
        import traceback as _tb
        _log_update(f"[check_for_update] FEHLER {type(_e).__name__}: {_e}\n"
                    f"{_tb.format_exc()}---")
        return result  # offline, Proxy, 404, kaputtes JSON, fehlender Key -> gnaedig

    result["latest"] = latest
    result["notes"] = manifest.get("notes")

    cur, new = _parse_version(current_version), _parse_version(latest)
    if cur and new and new > cur:
        result["update_available"] = True
        result["download_url"] = url
        # Optionaler Integritaets-Hash aus dem Manifest (gegen den die
        # heruntergeladene Datei vor dem EXE-Tausch geprueft wird).
        # Plattform-korrekten Hash waehlen, KEIN Fallback auf den jeweils
        # anderen: der Windows-sha256 ist nie ein gueltiger DMG-Hash (und
        # umgekehrt). Fehlt der passende Hash, bleibt sha256=None und
        # download_update warnt + uebernimmt ohne Integritaetspruefung.
        sha_key = "mac_sha256" if platform.system() == "Darwin" else "sha256"
        sha = manifest.get(sha_key)
        result["sha256"] = str(sha) if sha else None
    # Erfolgs-Heartbeat: macht auf Schul-PCs sichtbar, dass ueberhaupt geprueft
    # wurde und welche Versionen verglichen wurden (current vs latest).
    _log_update(f"[check_for_update] ok: current={current_version} "
                f"latest={latest} update_available={result['update_available']}")
    return result


def download_update(download_url: str, *,
                    expected_sha256: str | None = None,
                    _config=_read_local_config,
                    _opener_factory=_opener,
                    _target_dir=None,
                    _installer=None) -> dict:
    """Lädt das Binary nach ~/Downloads/ und installiert es auf Windows
    direkt am laufenden EXE-Pfad (Rename-Tausch). Auf Mac bleibt es bei
    "Datei liegt in Downloads, User zieht App in /Applications".

    expected_sha256: optionaler Hex-Digest aus dem Manifest. Ist er gesetzt,
    wird die heruntergeladene Datei vor dem EXE-Tausch dagegen geprueft und
    der Tausch bei Abweichung abgebrochen. Fehlt er, wird eine deutliche
    Warnung geloggt (kein stiller Skip).

    Rückgabe:
      {ok: True, path: str, installed: bool}
        - installed=True  → laufende EXE wurde getauscht, neue ist beim
          nächsten Start aktiv (Windows-Pfad)
        - installed=False → Datei in Downloads, manueller Schritt
          erwartet (Mac-Pfad oder Windows ohne sys.frozen oder Rename-
          Fehler)
      {ok: False, fallback_url} bei Netz-/IO-Fehler im Download oder
        Hash-Mismatch

    Die Unterstrich-Parameter sind Test-Nahtstellen."""
    part = None
    try:
        cfg = _config()
        # Dateinamen aus der URL strikt auf den Basename reduzieren –
        # verhindert Pfad-Traversal (z.B. "../../etc/...") aus einer
        # manipulierten URL/Manifest-Antwort.
        raw_name = download_url.rsplit("/", 1)[-1] or "ClassMatcher-Update"
        filename = Path(raw_name).name or "ClassMatcher-Update"
        target_dir = Path(_target_dir) if _target_dir is not None else Path.home() / "Downloads"
        target_dir.mkdir(parents=True, exist_ok=True)
        final = target_dir / filename
        part = final.parent / (final.name + ".part")
        hasher = hashlib.sha256()
        with _opener_factory(cfg).open(download_url, timeout=_DOWNLOAD_TIMEOUT) as resp, \
                open(part, "wb") as fh:
            while chunk := resp.read(65536):
                fh.write(chunk)
                hasher.update(chunk)

        # Integritaets-Pruefung VOR dem EXE-Tausch.
        if expected_sha256:
            actual = hasher.hexdigest()
            if actual.lower() != str(expected_sha256).strip().lower():
                _log_update(
                    f"[download_update] SHA-256-Mismatch: erwartet "
                    f"{expected_sha256}, war {actual} – Tausch abgebrochen.")
                part.unlink(missing_ok=True)
                return {"ok": False, "fallback_url": download_url,
                        "error": "Prüfsumme stimmt nicht – Download verworfen."}
        else:
            _log_update("[download_update] WARNUNG: kein sha256 im Manifest – "
                        "Download wird OHNE Integritaetspruefung uebernommen.")

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
    current = Path(sys.executable).resolve()
    old = current.with_suffix(".exe.old")
    # Restliche .old-Reste aus früherem Update aufräumen (best-effort).
    try:
        old.unlink(missing_ok=True)
    except OSError:
        pass
    renamed = False
    try:
        # Windows lässt das Umbenennen der eigenen laufenden EXE zu.
        current.rename(old)
        renamed = True
        # Neue EXE an exakt den Pfad legen, an dem die alte war.
        shutil.move(str(new_path), str(current))
        return True
    except Exception:
        # Rollback: die alte EXE war schon weggebenannt, der move der neuen
        # scheiterte aber (AV-Lock, abgebrochener Cross-Volume-Copy). Einen
        # eventuellen Teil-Rest entfernen und die alte zurueckholen, sonst
        # bliebe KEINE startbare EXE am Pfad zurueck (App nicht mehr startbar).
        if renamed:
            try:
                if current.exists():
                    current.unlink()
            except Exception:
                pass
            try:
                old.rename(current)
            except Exception:
                pass
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
