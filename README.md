# ClassMatcher – Schiller-Klassen-Mixer

Web-basiertes Tool zur **Zusammenstellung neuer 5. Klassen** am Schiller-Gymnasium Offenburg. Nimmt die CSV-Liste der Anmeldungen, wertet Freundeswünsche per Fuzzy-Matching aus und verteilt die Kinder anschließend auf Klassen – unter Beachtung von Profilen, Geschlechter­balance, Unvereinbarkeiten und manuell gesetzten Locks.

> **Zielgruppe:** Stufenleitung / Organisations­team, das einmal pro Schuljahr aus den eingegangenen Anmeldungen die neuen 5er-Klassen einteilt.

## Features

- **CSV-Import** aus dem schulinternen Anmeldesystem (Name, Profil, Geschlecht, Freundeswünsche, abgebende Schule, 2. Fremdsprache, …)
- **Fuzzy-Matching** der Freundeswünsche: `"Lena Müller"`, `"Lena M."`, `"lena mueller"` werden dem­selben Schüler zugeordnet. Unklare Fälle landen in einer Liste offener Wünsche zur manuellen Auflösung.
- **Zuweisungs-Algorithmus** per **Simulated Annealing**, gewichtet nach:
  - Freundes­wünsche erfüllen
  - Geschlechter­balance pro Klasse
  - maximale Klassen­größe einhalten
  - „darf nicht mit X in eine Klasse" (Konflikt-Liste)
  - vorhandene Profile (Streicher­klasse, Sprachprofil, …)
- **Drag & Drop** in der Oberfläche: einzelne Kinder fixieren (Lock) oder zwischen Klassen verschieben
- **Eigene Klassen­namen** frei vergeben
- **Alles In-Memory** – keine Daten­bank, keine Datenspeicherung auf dem Server. Schließen = Daten weg (deshalb der Hinweis „CSV sicher aufbewahren / Stand exportieren").

## Architektur

```
Browser (HTML + JS + Drag&Drop)
        │  fetch/JSON
        ▼
Flask-Backend (app.py)            ← REST-Endpunkte, In-Memory-State
        │
        ▼
matcher.py                        ← CSV-Parsing, Fuzzy-Matching,
                                    Simulated Annealing
```

| Datei | Zweck |
|-------|-------|
| `app.py` | Flask-Server, REST-API, hält den Anwendungszustand (`_state`) |
| `matcher.py` | CSV-Parser, Namens-Normalisierung, Fuzzy-Match, Zuweisungs-Algorithmus |
| `static/` | Frontend (HTML, CSS, JS, Logo) |
| `build_dmg.sh` | Baut ein signaturloses macOS-App-Bundle + DMG |
| `build_windows.bat` | Erstellt Windows-Standalone via PyInstaller |
| `Schiller-Klassen-Mixer.spec` | PyInstaller-Spec |

## Lokal starten (Entwicklung)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask
python app.py
# → http://localhost:5001
```

## Verteilung an Kolleginnen / Kollegen

### macOS
```bash
./build_dmg.sh
```
Erzeugt `Schiller-Klassen-Mixer.dmg`. Beim ersten Start braucht die App einmalig ca. 30 Sekunden für die Einrichtung (legt ein venv unter `~/Library/Application Support/Schiller-Klassen-Mixer/` an und installiert Flask). Danach öffnet sich der Browser automatisch unter `http://localhost:5001`.

> **Wichtig:** Die App ist **nicht signiert**. Erster Start per **Rechtsklick → Öffnen → Öffnen**, sonst blockiert Gatekeeper.

### Windows
```cmd
build_windows.bat
```

## CSV-Format

Erwartete Spalten (UTF-8, `;` oder `,` getrennt):

| Spalte | Pflicht | Beschreibung |
|--------|---------|--------------|
| `ID` | ✓ | eindeutige Schüler-ID |
| `Name`, `Vorname`, `Rufname` | ✓ | Anzeige-Name wird aus Rufname (oder Vorname) + Name gebildet |
| `Geschlecht` | ✓ | für Balance-Metrik |
| `Profil1` | – | z. B. `5a`, `5z` (Streicherklasse). `NULL` → `5z` |
| `Klassenpartner` | – | Freitextfeld, wird per Fuzzy-Matching aufgelöst |
| `vorhKlasse` | – | vorherige Grundschul­klasse |
| `AbgebendeSchule` | – | für Berichte |
| `Fremdsprache2` | – | 2. Fremdsprache (Profilzuordnung) |
| `Geburtstag` | – | Anzeige |

Die Beispieldatei `Anmeldungen.csv` im Repo zeigt das erwartete Format (anonymisiert/synthetisch).

## Datenschutz

Personen­bezogene Daten (Namen, Geburtstage, Wünsche) werden **ausschließlich im Arbeitsspeicher** des lokal laufenden Servers gehalten. Es gibt keine persistente Speicherung, keine Cloud-Anbindung, keine Analytics. Beim Beenden der Anwendung sind alle Daten weg – explizit so entworfen, damit die DSGVO-Anforderungen einer schulischen Anwendung leicht einzuhalten sind.

## Lizenz

Apache License 2.0 – siehe [`LICENSE`](LICENSE).

## Kontext

Interne Verwaltungs­hilfe für das Schiller-Gymnasium Offenburg. Löst ein jährlich wiederkehrendes Puzzle („wer kommt mit wem in welche Klasse?"), das bisher von Hand in Excel gelöst wurde.
