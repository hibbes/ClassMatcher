# ClassMatcher Auto-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die laufende ClassMatcher-App erkennt beim Start eine neuere Version, zeigt ein Banner und lädt die passende neue Datei automatisch herunter (Datei-Tausch bleibt manuell).

**Architecture:** Approach A — das Flask-Backend macht Check + Download (kein CORS, keine neue Dependency), das Frontend zeigt nur das Banner. Quelle ist eine öffentliche `version.json` + die Binaries auf `schiller-offenburg.de/classmatcher/`, von der CI bei Tag-Push per FTP bespielt. Proxy-robust: gnädiger Check, Browser-Download-Fallback.

**Tech Stack:** Python 3.12 + Flask (Backend), stdlib `urllib` (Netz, keine neue Dependency), Vanilla JS (Frontend), GitHub Actions + `curl` (CI/FTP), PyInstaller (Build).

**Spec:** `docs/superpowers/specs/2026-05-14-classmatcher-auto-update-design.md`

---

## File Structure

| Datei | Status | Verantwortung |
|---|---|---|
| `update.py` | **neu** | Reines Update-Modul: Versions-Parsing, lokale Config, `check_for_update`, `download_update`. stdlib-only, wirft nie. |
| `tests/test_update.py` | **neu** | Standalone-Test-Skript (Konvention wie `tests/run_golden.py`) für die reine Logik. |
| `app.py` | geändert | Zwei neue Routen `GET /api/check-update`, `POST /api/download-update`. Das `sys.frozen`-Gate sitzt in der Check-Route. |
| `static/index.html` | geändert | Banner-Markup `#update-banner` ganz oben; ein Satz im Hilfe-Modal. |
| `static/app.js` | geändert | `api.checkUpdate`/`api.downloadUpdate`, `checkForUpdate()`-Render-/Wire-Logik, Aufruf in `init()`. |
| `static/style.css` | geändert | `.update-banner`-Styles (nutzt bestehende `:root`-Tokens). |
| `.github/workflows/build.yml` | geändert | Neuer `publish`-Job (nur Tag-Push): version.json erzeugen + alles per FTP hochladen. |

**Hinweis zum `sys.frozen`-Gate:** Die Spec sagt „`check_for_update` ist auf `sys.frozen` gegated". Umgesetzt wird das Gate in der Flask-Route (`/api/check-update`), damit `update.py` rein und ohne `sys`-Mutation testbar bleibt — verhaltensidentisch (aus dem Quellcode gestartet → kein Banner).

---

## Voraussetzungen (User-Seite, vor dem Live-Gang)

Diese Schritte kann der Plan **nicht** automatisieren — sie sind vor dem ersten echten Release nötig:

1. **GitHub-Repo-Secrets** anlegen (`Settings → Secrets and variables → Actions`): `FTP_HOST`, `FTP_USER`, `FTP_PASSWORD` für den Mittwald-Webspace.
2. **Webspace-Ordner** `classmatcher/` im Webroot von `schiller-offenburg.de` anlegen (der CI-Job nutzt zusätzlich `--ftp-create-dirs` als Sicherheitsnetz).
3. Prüfen, ob der Mittwald-FTP **plain FTP** akzeptiert; falls nur FTPS: im CI-Job (Task 4) `curl` um `--ssl-reqd` ergänzen bzw. `ftps://` nutzen.
4. **Test-Release-Runde:** nach Merge eine `version.json` mit hoher Versionsnummer auf der Homepage ablegen und die gebaute App einmal manuell durchklicken (Banner erscheint, Download landet in `~/Downloads/`, Fallback-Link funktioniert).

---

## Task 1: `update.py`-Modul + Tests (TDD)

**Files:**
- Create: `tests/test_update.py`
- Create: `update.py`

- [ ] **Step 1: Test-Skript schreiben** — `tests/test_update.py`:

```python
#!/usr/bin/env python3
"""Unit-Tests fuer update.py – reine Logik, kein Netz.

Deckt _parse_version, den Versionsvergleich und check_for_update mit
gestubbtem Fetcher + gestubbter Config ab (inkl. "Fehler -> still kein
Update"- und "update_check=off"-Pfad).

Benutzung:
  .venv/bin/python tests/test_update.py

Exit 0 = alle Tests gruen, 1 = Fehlschlag.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import update  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_parse_version_normal():
    assert update._parse_version("1.5.10") == (1, 5, 10)
    assert update._parse_version("1.5.9") == (1, 5, 9)


@case
def test_parse_version_compare_numeric_not_lexical():
    # "1.5.10" muss > "1.5.9" sein (Zahlen-, kein String-Vergleich)
    assert update._parse_version("1.5.10") > update._parse_version("1.5.9")


@case
def test_parse_version_broken():
    assert update._parse_version("garbage") == ()
    assert update._parse_version("") == ()
    assert update._parse_version(None) == ()


@case
def test_update_available():
    res = update.check_for_update(
        "1.5.5",
        _fetcher=lambda cfg: {
            "version": "1.5.6",
            "win_url": "https://x/win.exe",
            "mac_url": "https://x/mac.dmg",
            "notes": "neu",
        },
        _config=lambda: {},
    )
    assert res["update_available"] is True
    assert res["latest"] == "1.5.6"
    assert res["download_url"] in ("https://x/win.exe", "https://x/mac.dmg")
    assert res["notes"] == "neu"


@case
def test_no_update_when_equal():
    res = update.check_for_update(
        "1.5.6",
        _fetcher=lambda cfg: {"version": "1.5.6", "win_url": "u", "mac_url": "u"},
        _config=lambda: {},
    )
    assert res["update_available"] is False


@case
def test_no_update_when_server_is_older():
    res = update.check_for_update(
        "1.5.6",
        _fetcher=lambda cfg: {"version": "1.5.5", "win_url": "u", "mac_url": "u"},
        _config=lambda: {},
    )
    assert res["update_available"] is False


@case
def test_fetcher_error_is_graceful():
    def boom(cfg):
        raise OSError("Proxy blockt")

    res = update.check_for_update("1.5.5", _fetcher=boom, _config=lambda: {})
    assert res["update_available"] is False
    assert res["current"] == "1.5.5"


@case
def test_broken_server_version_is_graceful():
    res = update.check_for_update(
        "1.5.5",
        _fetcher=lambda cfg: {"version": "kaputt", "win_url": "u", "mac_url": "u"},
        _config=lambda: {},
    )
    assert res["update_available"] is False


@case
def test_update_check_off_disables():
    res = update.check_for_update(
        "1.5.5",
        _fetcher=lambda cfg: {"version": "9.9.9", "win_url": "u", "mac_url": "u"},
        _config=lambda: {"update_check": "off"},
    )
    assert res["update_available"] is False


def main() -> int:
    failed = 0
    for fn in CASES:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {e!r}")
    total = len(CASES)
    print(f"\n{total - failed}/{total} Tests gruen")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `.venv/bin/python tests/test_update.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'update'` (das Skript bricht beim `import update` ab, bevor `main()` läuft).

- [ ] **Step 3: `update.py` schreiben** — im Repo-Wurzelverzeichnis:

```python
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
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `.venv/bin/python tests/test_update.py`
Expected: PASS — `9/9 Tests gruen`, Exit 0.

- [ ] **Step 5: Golden-Master-Suite gegenchecken** (nichts am Matcher angefasst, muss unberührt grün sein)

Run: `.venv/bin/python tests/run_golden.py`
Expected: alle Szenarien grün, Exit 0.

- [ ] **Step 6: Commit**

```bash
git add update.py tests/test_update.py
git commit -m "feat: update.py – Versions-Check + Download, stdlib-only (TDD)"
```

---

## Task 2: Flask-Routen in `app.py`

**Files:**
- Modify: `app.py` (neue Routen nach der `/api/version`-Route, ~Zeile 93)

- [ ] **Step 1: Routen einfügen** — direkt nach der bestehenden `version()`-Route (nach Zeile 93, vor der `static_files`-Route) einfügen:

```python
@app.route("/api/check-update")
def check_update():
    """Prüft die Schul-Homepage auf eine neuere Version.
    Aus dem Quellcode gestartet (nicht-frozen) → immer 'kein Update'."""
    import sys
    if not getattr(sys, "frozen", False):
        return jsonify({"update_available": False, "current": APP_VERSION,
                        "latest": None, "download_url": None, "notes": None})
    import update
    return jsonify(update.check_for_update(APP_VERSION))


@app.route("/api/download-update", methods=["POST"])
def download_update_route():
    """Lädt das neue Binary nach ~/Downloads/ (Fallback: Browser-Link)."""
    import update
    url = (request.json or {}).get("download_url")
    if not url:
        return jsonify({"ok": False, "error": "download_url fehlt"}), 400
    return jsonify(update.download_update(url))
```

(Lazy-Import von `update` innerhalb der Routen — gleiche Konvention wie `from matcher import …` im Rest der Datei.)

- [ ] **Step 2: App aus dem Quellcode starten**

Run: `cd /home/neo/projects/ClassMatcher && .venv/bin/python app.py &`
Then: `sleep 2`
Expected: Server läuft auf `127.0.0.1:5001`.

- [ ] **Step 3: Check-Route verifizieren** (nicht-frozen → kein Update)

Run: `curl -s localhost:5001/api/check-update`
Expected: `{"update_available": false, "current": "1.5.5", "latest": null, "download_url": null, "notes": null}` (Reihenfolge egal).

- [ ] **Step 4: Download-Route-Fallback verifizieren** (unerreichbare URL → gnädiger Fallback)

Run: `curl -s -X POST localhost:5001/api/download-update -H 'Content-Type: application/json' -d '{"download_url":"https://invalid.invalid/x.exe"}'`
Expected: `{"ok": false, "fallback_url": "https://invalid.invalid/x.exe"}`.

- [ ] **Step 5: Server beenden**

Run: `kill %1` (oder den `python app.py`-Prozess auf Port 5001 beenden).

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: /api/check-update + /api/download-update Routen"
```

---

## Task 3: Frontend — Update-Banner

**Files:**
- Modify: `static/index.html` (Banner-Markup)
- Modify: `static/app.js` (api-Methoden + `checkForUpdate()` + `init()`-Aufruf)
- Modify: `static/style.css` (Banner-Styles)

- [ ] **Step 1: Banner-Markup in `index.html`** — direkt nach `<body>` (Zeile 9), vor dem `<!-- HEADER -->`-Kommentar (Zeile 11) einfügen:

```html
<!-- ═══════════════════════ UPDATE-BANNER ═══════════════════════ -->
<div id="update-banner" class="hidden" role="status">
  <span id="update-banner-text"></span>
  <span id="update-banner-actions"></span>
  <button id="update-banner-close" title="Ausblenden" aria-label="Ausblenden">✕</button>
</div>
```

- [ ] **Step 2: api-Methoden in `app.js`** — im `api`-Objekt nach der `refineFriends`-Methode (nach Zeile 117, vor der schließenden `}` des `api`-Objekts) einfügen:

```javascript
  async checkUpdate() {
    const r = await fetch("/api/check-update");
    return r.json();
  },
  async downloadUpdate(downloadUrl) {
    const r = await fetch("/api/download-update", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ download_url: downloadUrl }),
    });
    return r.json();
  },
```

- [ ] **Step 3: `checkForUpdate()` in `app.js`** — als eigener Abschnitt direkt vor `// Initialisierung` (vor Zeile 954) einfügen:

```javascript
// ──────────────────────────────────────────────────────────────────
// Auto-Update-Banner
// ──────────────────────────────────────────────────────────────────

async function checkForUpdate() {
  let info;
  try {
    info = await api.checkUpdate();
  } catch {
    return;  // Netzfehler o.ä. – stillschweigend, kein Banner
  }
  if (!info || !info.update_available) return;

  const banner  = document.getElementById("update-banner");
  const textEl  = document.getElementById("update-banner-text");
  const actions = document.getElementById("update-banner-actions");

  textEl.textContent =
    `🔔 Version ${info.latest} verfügbar (du hast ${info.current}).`;
  if (info.notes) textEl.textContent += ` ${info.notes}`;

  const btn = document.createElement("button");
  btn.className = "btn btn-primary btn-sm";
  btn.textContent = "Jetzt herunterladen";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Lädt …";
    let res;
    try {
      res = await api.downloadUpdate(info.download_url);
    } catch {
      res = { ok: false, fallback_url: info.download_url };
    }
    actions.innerHTML = "";
    if (res.ok) {
      textEl.textContent =
        `✓ Heruntergeladen: ${res.path} — alte App schließen, neue Datei starten.`;
    } else {
      textEl.textContent = "Automatischer Download ging nicht (Proxy?). ";
      const link = document.createElement("a");
      link.href = res.fallback_url;
      link.textContent = "Hier direkt herunterladen";
      link.setAttribute("download", "");
      actions.appendChild(link);
    }
  });
  actions.appendChild(btn);

  document.getElementById("update-banner-close")
    .addEventListener("click", () => banner.classList.add("hidden"));

  banner.classList.remove("hidden");
}
```

- [ ] **Step 4: Aufruf in `init()`** — in `app.js`, in der `init()`-Funktion direkt nach dem `/api/version`-`fetch`-Block (nach Zeile 969, vor dem `// ── Mode-Toggle ──`-Kommentar) einfügen:

```javascript
  // Auto-Update-Check (nicht-blockierend, scheitert still)
  checkForUpdate();
```

- [ ] **Step 5: Banner-Styles in `style.css`** — ans Ende der Datei anhängen:

```css
/* ── Update-Banner ──────────────────────────────────────────────── */
#update-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--warning);
  color: #fff;
  font-size: 13px;
}
#update-banner.hidden { display: none; }  /* schlägt die #id-Spezifität */
#update-banner-text { flex: 1; }
#update-banner a { color: #fff; font-weight: 600; }
#update-banner-close {
  background: transparent;
  border: 0;
  color: #fff;
  cursor: pointer;
  font-size: 15px;
  line-height: 1;
}
```

- [ ] **Step 6: Hilfe-Modal-Notiz in `index.html`** — im Hilfe-Modal in der `<section class="help-section">` mit „9. Häufige Fragen" eine Tabellenzeile ergänzen (nach der „Werden meine Daten gespeichert?"-Zeile, vor `</table>`):

```html
          <tr>
            <td><strong>Was bedeutet das orangefarbene Banner oben?</strong></td>
            <td>Beim Start prüft das Programm einmal, ob eine neuere Version vorliegt. Falls ja, erscheint oben ein Hinweis mit Knopf „Jetzt herunterladen" — die neue Datei landet in Ihrem Downloads-Ordner. Schließen Sie dann die alte App und starten Sie die heruntergeladene Datei. Der Hinweis lässt sich mit ✕ ausblenden.</td>
          </tr>
```

- [ ] **Step 7: App aus dem Quellcode laden, Konsole prüfen**

Run: `cd /home/neo/projects/ClassMatcher && .venv/bin/python app.py &` then `sleep 2 && curl -s localhost:5001/ | head -3` then `kill %1`
Expected: `index.html` wird ausgeliefert (HTML beginnt mit `<!DOCTYPE html>`). Manuell im Browser geöffnet: keine JS-Fehler in der Konsole, `#update-banner` existiert und bleibt versteckt (aus dem Quellcode = nicht-frozen → kein Update). Die echte Banner-Sichtbarkeit wird beim manuellen Smoke-Test der gebauten App geprüft.

- [ ] **Step 8: Commit**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat: Update-Banner im Frontend (Check beim Start + Download-Knopf)"
```

---

## Task 4: CI-Publish-Job in `build.yml`

**Files:**
- Modify: `.github/workflows/build.yml` (neuer `publish`-Job am Ende)

- [ ] **Step 1: `publish`-Job anhängen** — ans Ende von `.github/workflows/build.yml` (nach dem `build-windows`-Job) einfügen:

```yaml
  # ── Publish: version.json + Binaries auf die Schul-Homepage (nur bei Tag) ──
  publish:
    needs: [build-macos, build-windows]
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - name: Version aus Tag ableiten
        id: ver
        run: echo "version=${GITHUB_REF_NAME#v}" >> "$GITHUB_OUTPUT"

      - name: Artefakte herunterladen
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: version.json erzeugen
        env:
          VERSION: ${{ steps.ver.outputs.version }}
        run: |
          cat > version.json <<EOF
          {
            "version": "${VERSION}",
            "win_url": "https://schiller-offenburg.de/classmatcher/Schiller-Klassen-Mixer-v${VERSION}.exe",
            "mac_url": "https://schiller-offenburg.de/classmatcher/Schiller-Klassen-Mixer-v${VERSION}.dmg",
            "notes": ""
          }
          EOF
          cat version.json

      - name: Upload zur Homepage (Binaries zuerst, version.json zuletzt)
        env:
          FTP_HOST: ${{ secrets.FTP_HOST }}
          FTP_USER: ${{ secrets.FTP_USER }}
          FTP_PASS: ${{ secrets.FTP_PASSWORD }}
        run: |
          EXE=$(find artifacts -name '*.exe' | head -1)
          DMG=$(find artifacts -name '*.dmg' | head -1)
          if [ -z "$EXE" ] || [ -z "$DMG" ]; then
            echo "::error::EXE oder DMG nicht in den Artefakten gefunden"; exit 1
          fi
          for f in "$EXE" "$DMG" version.json; do
            echo "Lade hoch: $f"
            curl --fail --silent --show-error --ftp-create-dirs \
                 --user "$FTP_USER:$FTP_PASS" \
                 --upload-file "$f" \
                 "ftp://$FTP_HOST/classmatcher/$(basename "$f")"
          done
          echo "Publish fertig: version.json $(grep -o '\"version\"[^,]*' version.json)"
```

Hinweise: Passwort via `--user` (keine URL-Encoding-Falle). `--ftp-create-dirs` legt `classmatcher/` an falls nötig. Falls Mittwald nur FTPS akzeptiert: `--ssl-reqd` ergänzen (siehe Voraussetzungen).

- [ ] **Step 2: YAML-Syntax prüfen**

Run: `.venv/bin/pip install -q pyyaml && .venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml')); print('YAML ok')"`
Expected: `YAML ok` (pyyaml landet nur im gitignored venv, nicht in `requirements.txt`).

- [ ] **Step 3: Job-Struktur gegen die bestehenden Jobs prüfen** — sicherstellen: `publish` ist auf gleicher Einrückungsebene wie `build-macos`/`build-windows`, `needs:` referenziert beide Job-Namen exakt, `if:` gated auf Tags.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/build.yml
git commit -m "ci: publish-Job – version.json + Binaries per FTP auf die Homepage"
```

---

## Task 5: Doku, Versions-Bump & Abschluss-Verifikation

**Files:**
- Modify: `app.py` (`APP_VERSION`)
- Modify: `README.md` (kurze Notiz)

- [ ] **Step 1: `APP_VERSION` bumpen** — in `app.py` Zeile 9:

```python
APP_VERSION = "1.6.0"
```

(Minor-Bump, weil neues Feature. Der Release-Tag `v1.6.0` wird nach dem Merge gesetzt — siehe „Voraussetzungen".)

- [ ] **Step 2: README-Notiz** — in `README.md` einen kurzen Abschnitt ergänzen (passende Stelle, z.B. nach der Feature-/Nutzungs-Beschreibung):

```markdown
## Auto-Update

Beim Start prüft die App einmalig, ob auf `schiller-offenburg.de/classmatcher/`
eine neuere Version liegt. Falls ja, erscheint oben ein Banner mit Download-Knopf;
die neue Datei landet in `~/Downloads/`, der Datei-Tausch bleibt manuell. Der Check
ist gnädig (offline/Proxy → kein Banner, nie ein Fehler) und lässt sich über
`~/.classmatcher.cfg` mit `update_check=off` abschalten; ein expliziter Proxy geht
dort via `proxy=http://host:port`.
```

- [ ] **Step 3: Volle Test-Suite**

Run: `.venv/bin/python tests/test_update.py && .venv/bin/python tests/run_golden.py`
Expected: `9/9 Tests gruen` (Exit 0) **und** Golden-Master alle Szenarien grün (Exit 0).

- [ ] **Step 4: Smoke-Check aus dem Quellcode**

Run: `cd /home/neo/projects/ClassMatcher && .venv/bin/python app.py &` then `sleep 2 && curl -s localhost:5001/api/version && echo && curl -s localhost:5001/api/check-update && echo` then `kill %1`
Expected: `/api/version` liefert `{"version": "1.6.0"}`; `/api/check-update` liefert `{"update_available": false, ...}` (nicht-frozen).

- [ ] **Step 5: Commit**

```bash
git add app.py README.md
git commit -m "docs: Auto-Update in README + Hilfe; APP_VERSION 1.6.0"
```

---

## Nach allen Tasks

- Finalen Code-Review über den gesamten Branch (`main..feat/auto-update`).
- `superpowers:finishing-a-development-branch` zum Abschluss.
- Dann die User-seitigen „Voraussetzungen" abarbeiten (GitHub-Secrets, Webspace-Ordner, FTPS-Check) und eine Test-Release-Runde fahren, bevor `v1.6.0` getaggt wird.
