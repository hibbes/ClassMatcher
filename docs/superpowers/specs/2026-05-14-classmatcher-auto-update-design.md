# Design: Auto-Update-Funktion für ClassMatcher

**Datum:** 2026-05-14
**Status:** freigegeben (Brainstorming abgeschlossen, vor Implementierungsplan)
**Projekt:** ClassMatcher / Schiller-Klassen-Mixer (`~/projects/ClassMatcher/`)
**Branch:** `feat/auto-update` von `main`

## Kontext & Ziel

ClassMatcher wird als PyInstaller-Onefile-EXE (Windows) bzw. `.app`/`.dmg` (macOS)
verteilt; Marek startet die Datei per Doppelklick, sie läuft als lokaler
Flask-Server auf `http://localhost:5001`. Neue Versionen entstehen über einen
CI-Build (Tag-Trigger) und müssen aktuell manuell verteilt und ersetzt werden.
Folge: es läuft leicht eine veraltete Version, ohne dass es jemand merkt — v1.5.1
hat extra einen Cache-Control-Fix gegen genau dieses Symptom bekommen.

**Ziel:** Die laufende App erkennt beim Start, ob eine neuere Version vorliegt,
weist im UI darauf hin und lädt die passende neue Datei automatisch herunter.
Der eigentliche Datei-Tausch (alte App schließen, neue starten) bleibt manuell —
bewusst, kein Silent-Self-Replace.

**Randbedingungen:**

- Eine laufende Onefile-EXE kann sich unter Windows nicht selbst überschreiben →
  kein In-Place-Self-Update.
- Das Code-Repo `hibbes/ClassMatcher` ist privat → ein Versions-Check gegen die
  GitHub-API bräuchte einen Token im verteilten Binary (unerwünscht).
- Die Schul-Verwaltungsrechner, auf denen die App läuft, hängen hinter einem
  Proxy → die Netz-Calls müssen proxy-robust sein.
- Die App ist bewusst In-Memory / ohne DB / DSGVO-schonend → der einzige neue
  Netz-Call ist ein GET einer Versionsnummer von der schul-eigenen Homepage; es
  verlassen keine Schülerdaten den Rechner.

## Entscheidungen (aus dem Brainstorming)

| Frage | Entscheidung |
|---|---|
| Update-Modus | Benachrichtigen **+** Datei automatisch holen (kein Silent-Self-Replace) |
| Update-Quelle | Schul-Homepage `schiller-offenburg.de` (Mittwald): öffentliche `version.json` + Binaries, per FTP von der CI bespielt |
| Client-Architektur | Approach A: Backend (Flask) macht Check + Download; Frontend zeigt nur das Banner |

## Architektur

### Publish-Seite (CI)

`.github/workflows/build.yml` bekommt einen zusätzlichen Job, der **nur bei
Tag-Push** (`v*`) läuft, nach `build-macos` + `build-windows` (`needs:`):

1. Lädt die zwei Build-Artefakte (`.exe`, `.dmg`) ein.
2. Generiert `version.json` aus `APP_VERSION`.
3. Lädt **Binaries zuerst, `version.json` zuletzt** per `curl`-Skript (FTP-Upload,
   auf dem Runner ohne Zusatz-Install verfügbar) nach
   `schiller-offenburg.de/classmatcher/`. Die „version.json zuletzt"-Reihenfolge
   verhindert, dass ein Client mitten im Upload auf ein noch fehlendes File zeigt.

Neue GitHub-Repo-Secrets: `FTP_HOST`, `FTP_USER`, `FTP_PASSWORD`. Lokale Builds
(`build_windows.bat` / `build_dmg.sh`) publishen bewusst **nicht** — nur
getaggte Releases.

`version.json`-Format:

```json
{
  "version": "1.5.6",
  "win_url": "https://schiller-offenburg.de/classmatcher/Schiller-Klassen-Mixer-v1.5.6.exe",
  "mac_url": "https://schiller-offenburg.de/classmatcher/Schiller-Klassen-Mixer-v1.5.6.dmg",
  "notes": "Kurz-Changelog, optional"
}
```

### Client-Seite (Approach A)

Neues Backend-Modul `update.py` (analog zu `matcher.py`, hält `app.py` schlank):

- `check_for_update(current_version) -> dict` — holt `version.json` per
  stdlib-`urllib`, vergleicht Versionen, liefert
  `{update_available, latest, current, download_url, notes}`. Bei **jedem**
  Fehler still `{update_available: false}`. Gated auf `sys.frozen`: aus dem
  Quellcode gestartet sofort `{update_available: false}`.
- `download_update(download_url) -> dict` — lädt das plattformrichtige Binary
  (`win_url`/`mac_url` je nach `platform.system()`) nach `~/Downloads/`, liefert
  `{ok: true, path}` bzw. bei Fehler `{ok: false, fallback_url}`.
- `_parse_version(s) -> tuple` — `"1.5.10"` → `(1, 5, 10)`, defensiv (kaputte
  Strings → kein Update statt Crash/Fehlalarm).

Zwei neue Routen in `app.py`:

- `GET /api/check-update` → `update.check_for_update(APP_VERSION)` als JSON.
- `POST /api/download-update` → Body `{download_url}` → `update.download_update(url)`.

Alles stdlib (`urllib`, `json`, `pathlib`, `platform`, `sys`) — **keine neue
Dependency**, nichts Zusätzliches im PyInstaller-Build.

Frontend (`static/`): beim Laden ein `fetch('/api/check-update')` (same-origin,
kein CORS). Bei `update_available` → schließbares Banner oben:
„🔔 Version X verfügbar (du hast Y) [Jetzt herunterladen] [×]", optional `notes`.
Klick → `POST /api/download-update`:

- Erfolg → Banner: „✓ Heruntergeladen: `<Pfad>`. Alte App schließen, neue starten."
- Fallback → Banner: „Auto-Download ging nicht (Proxy?), hier direkt laden:
  `<Link>`" — ein normaler `<a download>` aufs Homepage-File, der Browser lädt
  durch den Proxy.

### Proxy-Robustheit

Die Verwaltungsrechner hängen hinter einem Proxy. `urllib` nimmt einen einfachen
System-Proxy unter Windows via `getproxies()` automatisch mit, scheitert aber an
authentifiziertem Proxy / PAC-Datei / HTTPS-Interception. Deshalb:

- Der **Check** ist komplett gnädig: kommt `urllib` nicht durch (inkl.
  Cert-Fehler durch MITM-Proxy), gibt es einfach kein Banner, nie eine
  Fehlermeldung. Die Cert-Verifikation wird **nicht** abgeschaltet.
- Der **Download** hat einen automatischen Fallback: scheitert der
  Backend-`urllib`-Download, liefert die Route `fallback_url` und das Banner
  zeigt den Browser-Download-Link. Browser handhaben Proxy-Auth/PAC/MITM-CA nativ.
- Optionaler expliziter Override: eine kleine lokale Plain-Text-Config kann
  `proxy=http://...` setzen und mit `update_check=off` den Netz-Call ganz
  abschalten (für besonders restriktive Verwaltungsrechner). Kein UI, gleiche
  Idee wie die bestehenden Power-User-Parameter; der genaue Dateiort wird im
  Implementierungsplan festgelegt.

Damit: schöne UX auf einfachem Proxy (exakter Pfad, Ordner öffnen möglich),
funktioniert trotzdem auf garstigem Proxy via Browser-Fallback.

## Fehlerfälle & Edge Cases

- Offline / Proxy blockt / 404 (`version.json` noch nicht deployed) / Cert-Fehler
  → `{update_available: false}`, App läuft normal weiter.
- Aus dem Quellcode gestartet (`not sys.frozen`) → kein Banner.
- Download nach `.part`-Tempname, dann Rename → ein halber Download sieht nie
  fertig aus; eine bereits vorhandene Datei wird überschrieben (idempotent).
- `~/Downloads/` nicht beschreibbar → `{ok: false, fallback_url}` →
  Browser-Fallback (gleicher Mechanismus wie beim Proxy-Fehler).
- Mid-Publish-Race → durch „`version.json` zuletzt hochladen" abgedeckt.
- Der Versions-Check ist nicht-blockierend: Frontend-`fetch` async, Backend-
  `urllib` mit ~4 s Timeout. Das Banner erscheint ggf. ein paar Sekunden
  verzögert, blockiert aber nie Start oder UI.

## Tests

- Neue `tests/test_update.py` für die reine Logik: `_parse_version` + Vergleich
  (`1.5.10 > 1.5.9`, gleich = kein Update, kaputter String = kein Update) und die
  Entscheidungsfunktion mit gestubbtem Fetcher, inkl. „Fehler → still kein
  Update"-Pfad.
- Netz-I/O, FTP-Publish-Step und das Banner werden manuell über eine echte
  Test-Release-Runde (Tag) verifiziert.
- Die bestehende Golden-Master-Suite (`tests/run_golden.py`) bleibt unberührt —
  die Update-Funktion fasst den Matcher-Kern nicht an.

## Nicht im Scope

- Echtes Silent-Self-Replace (laufende Onefile-EXE ersetzt sich selbst) — bewusst
  verworfen, der Datei-Tausch bleibt manuell.
- PAC-Auswertung / NTLM-Proxy-Authentifizierung im Backend — dafür ist der
  Browser-Fallback da.
- Ein Settings-UI für `proxy=` / `update_check=off` — bleibt Plain-Text-Config.
- Auto-Update für lokal gebaute Builds — nur getaggte CI-Releases werden
  publiziert.
