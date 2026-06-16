# Design: Schüler:in manuell hinzufügen

- **Datum:** 2026-06-16
- **Projekt:** ClassMatcher (Schiller-Klassen-Mixer)
- **Status:** Genehmigt (Brainstorming abgeschlossen)

## 1. Kontext und Ziel

Der Klassen-Mixer lädt Schülerdaten ausschließlich per CSV-Import. Geht eine
Anmeldung erst nach dem Import ein (typisch: spät registrierte 5. Klässler), gibt
es keinen Weg, einen einzelnen Schüler nachzutragen, ohne die CSV extern zu
bearbeiten und neu zu importieren (was alle manuellen Verschiebungen, geklärten
Wünsche und Umbenennungen verwirft).

**Ziel:** Ein Button in der linken Sidebar öffnet ein Formular, über das eine
einzelne Schülerin oder ein einzelner Schüler angelegt wird. Nach dem Speichern
wird die Person sofort automatisch in die Klassen einsortiert (Neuzuweisung),
wobei bereits fixierte (🔒) Schüler an ihrem Platz bleiben.

## 2. Anwendungsfall

Die Stufenleitung hat die Klassen bereits gemischt (eventuell mit manuellen
Locks und geklärten Freundeswünschen). Eine Nachmeldung trifft ein. Sie öffnet
das Formular, trägt die Daten ein, speichert, und die neue Person erscheint
optimal einsortiert auf dem Board. Vorhandene Locks und geklärte Wünsche bleiben
erhalten.

## 3. Nicht-Ziele (out of scope)

- Bearbeiten oder Löschen manuell angelegter Schüler:innen. Ein Versehen wird
  über „Startseite / CSV neu laden" zurückgesetzt. (Möglicher Follow-up.)
- Bulk-Import mehrerer Schüler über das Formular (dafür bleibt der CSV-Import).
- Persistenz: Wie der Rest der App bleibt der Zustand In-Memory. Wer den Stand
  sichern will, nutzt den bestehenden „↓ Speichern"-Export.

## 4. Architektur-Entscheidung

**Variante A (gewählt): Eigener Endpoint `POST /api/add-student`, der intern
direkt neu zuweist.**

Der Endpoint hängt den Schüler an den State an, aktualisiert die Freundeswünsche
inkrementell und führt anschließend denselben Zuweisungs- und Antwort-Block aus
wie `/api/assign`. Ein Round-Trip, das Board aktualisiert sich sofort, die
Validierung hat einen klaren eigenen Ort, und der Endpoint ist isoliert testbar.

Verworfen: Variante B (zwei Calls vom Frontend, zwei Round-Trips, Zwischenzustand)
und Variante C (`/api/assign` mit optionalem `newStudent`-Parameter überladen,
vermischt Validierung).

## 5. Frontend / UX

### 5.1 Sidebar-Button

Neue Sektion ganz oben in `#sidebar` (über „Klassengröße"), analog zum
bestehenden Muster der Sektion „Nicht zusammen" mit ihrem `+ Paar hinzufügen`-Button:

```
┌─ Schüler:in ──────────────┐
│ [ + Schüler:in hinzufügen ] │
└───────────────────────────┘
```

Die Sidebar ist ohnehin erst sichtbar, sobald ein Board geladen ist; daher
braucht der Button keine zusätzliche Sichtbarkeitslogik über die der Sidebar
hinaus.

### 5.2 Modal

Der Button öffnet ein neues Modal `#add-student-modal`, gebaut aus demselben
Modal-Baustein wie `#pair-modal` (Overlay, `.modal`, Header mit Schließen-X,
Body, Footer mit Abbrechen / Speichern). Nach erfolgreichem Speichern: Modal
schließt, das Board re-rendert mit der frischen Zuweisung über dieselbe
Render-Funktion wie nach „Neu zuweisen", und der `⚠ Wünsche klären`-Badge wird
anhand des zurückgegebenen `pendingCount` aktualisiert.

### 5.3 Felder, modus-adaptiv

Das Modal liest den aktiven Modus (`_state["mode"]`, dem Frontend bereits
bekannt) und zeigt die passenden Felder.

| Feld | Klasse 5 | Klasse 8 | Pflicht | Hinweis |
|------|:--------:|:--------:|:-------:|---------|
| Vorname | ✓ | ✓ | ✓ | |
| Nachname | ✓ | ✓ | ✓ | |
| Rufname | ✓ | (leer) | nein | nur Klasse 5 |
| Geschlecht | ✓ | ✓ | ✓ | Auswahl: Junge (m) / Mädchen (w) / divers-unbekannt (leer); ohne Vorauswahl, muss gesetzt werden |
| Profil | ✓ | ✓ | ✓ | Dropdown, befüllt aus den im Datensatz vorhandenen `profil`-Werten |
| 2. Fremdsprache | ✓ | ✓ | nein | Auswahl: Französisch (F) / Latein (L). Default F |
| Freundeswünsche | ✓ | ✓ | nein | Freitext, identisch zur CSV-Spalte „Klassenpartner" |
| Religionsunterricht (RU) | ✓ | (leer) | nein | nur Klasse 5, ein optionales Feld → `ru`. `religion` wird serverseitig auf `""` gesetzt |
| Bili-Zug | (leer) | ✓ | nein | Checkbox, nur Klasse 8 |
| hätte IMP gewählt | (leer) | ✓ | nein | Checkbox, nur Klasse 8 (`imp_alternativ`) |

Das Profil-Dropdown wird aus den tatsächlich im aktuellen Datensatz vorhandenen
`profil`-Werten befüllt (per `/api/students` oder aus dem bereits geladenen
Board-State). Das garantiert gültige Buckets, die der Klassifizierer kennt, und
vermeidet hartkodierte Magic-Strings, die zwischen den Modi abweichen.

Der Speichern-Button bleibt deaktiviert, bis Vorname, Nachname, Geschlecht und
Profil gesetzt sind.

## 6. Backend: `POST /api/add-student`

### 6.1 Request (JSON)

Der Modus ist implizit aus `_state["mode"]`. Gesendet werden nur die für den
Modus relevanten Felder:

```jsonc
{
  "vorname":        "Lena",        // Pflicht
  "name":           "Müller",      // Pflicht (Nachname)
  "rufname":        "",            // optional, nur Klasse 5
  "geschlecht":     "w",           // "m" | "w" | "" (Pflicht: muss bewusst gesetzt werden)
  "profil":         "5z",          // Pflicht, nicht leer
  "fremdsprache2":  "F",           // "F" | "L", Default "F"
  "klassenpartner": "Mia, Anna B.",// optional, Freitext
  "ru":             "",            // optional, nur Klasse 5 (Religionsunterricht)
  "bili":           false,         // optional, nur Klasse 8
  "imp_alternativ": false          // optional, nur Klasse 8
}
```

### 6.2 Ablauf

1. **Vorbedingung:** Wenn `_state["students"]` leer ist, `400` („Keine Schüler
   geladen"). Der Button erscheint ohnehin nur bei geladenem Board.
2. **Validierung:** Pflichtfelder (`vorname`, `name`, `profil`) nicht leer nach
   `strip()`; `geschlecht` in {`m`, `w`, ``}; `fremdsprache2` in {`F`, `L`}.
   Alle String-Felder trimmen und auf eine sinnvolle Maximallänge begrenzen
   (z. B. 200 Zeichen) gegen Missbrauch. Bei Verstoß `400` mit Klartext-Meldung.
3. **ID generieren:** `manual-<normalize(vorname)>-<normalize(name)>`; bei
   Kollision mit einer vorhandenen ID `-2`, `-3`, … anhängen. Das Präfix
   `manual-` macht angelegte Datensätze erkennbar (nützlich für einen späteren
   Lösch-Follow-up) und kollidiert nicht mit CSV- oder Klasse-8-IDs.
4. **Schüler-Dict bauen, schlüsselgleich zur jeweiligen Parser-Ausgabe:**
   - **Klasse 5** (wie `parse_csv`): Schlüssel `id, name, vorname, rufname,
     displayName, geschlecht, profil, klassenpartner, vorhKlasse,
     abgebendeSchule, geburtsdatum, fremdsprache2, ru, religion`. Nicht
     gesetzte Felder als `""`. `displayName = f"{rufname or vorname} {name}".strip()`.
   - **Klasse 8** (wie `parse_csv_klasse8`): Schlüssel `id, name, vorname,
     rufname, displayName, geschlecht, profil, klassenpartner, vorhKlasse,
     abgebendeSchule, geburtsdatum, fremdsprache2, bili, latein, imp_alternativ`.
     `rufname = ""`, `displayName = f"{vorname} {name}"`, `latein = (fremdsprache2 == "L")`,
     `bili`/`imp_alternativ` aus den Checkboxen.
   - Schlüsselgleichheit ist zwingend, damit der gesamte nachgelagerte Code
     (Zuweisung, Scoring, Rendering, Druck) unverändert funktioniert.
5. **Anhängen** an `_state["students"]`.
6. **Inkrementelles Wunsch-Update** (siehe 6.3).
7. **Neuzuweisung:** Denselben Block wie `/api/assign` ausführen (Locks aus
   `_state["locked_students"]` bleiben aktiv, der neue Schüler ist nicht
   gelockt und wird daher frei einsortiert).
8. **Response:** Wie `/api/assign` (`{classes, stats}`, plus optional `warning`),
   ergänzt um `pendingCount`, damit das Frontend den `⚠`-Badge aktualisieren kann.

### 6.3 Inkrementelles Wunsch-Update (kritisch)

Ein kompletter `process_wishes`-Neulauf über alle Schüler würde bereits **manuell
geklärte** Fuzzy-Wünsche (`resolved_wishes` / `pending_wishes`, via
`/api/resolve-wish` gesetzt) überschreiben. Das ist nicht zulässig. Stattdessen
rein additiv:

1. **Neuer Schüler:** Seine `klassenpartner` tokenisieren und gegen die
   bestehenden Schüler matchen (Logik wie in `process_wishes`: Treffer
   ≥ `AUTO_THRESHOLD` nach `resolved[new_id]`, sonst Kandidaten nach
   `pending[new_id]`). `resolved`/`pending` für die neue ID neu anlegen (es gibt
   keinen Vorzustand, der zerstört werden könnte).
2. **Bestehende Schüler gegen den Neuen:** Für jeden bestehenden Schüler dessen
   Wunsch-Tokens **nur gegen den neuen Schüler** matchen. Treffer
   ≥ `AUTO_THRESHOLD` und noch nicht in `resolved[existing_id]` → ergänzen.
   Treffer im Vorschlagsbereich → als Kandidat zu `pending[existing_id]`
   ergänzen (Dubletten vermeiden). Alle anderen vorhandenen Einträge bleiben
   unangetastet.

So entstehen genau die neuen Verbindungen zur hinzugefügten Person, während jede
zuvor getroffene manuelle Entscheidung erhalten bleibt.

## 7. Randfälle

- **Namensdublette** (z. B. Zwillinge): erlaubt, kein harter Block; die ID-Logik
  vergibt eine eindeutige ID.
- **Neuer Schüler ohne Lock:** wird vom Algorithmus frei platziert (= „sofort
  einsortieren").
- **Unvollständige Zuweisung:** Der bestehende Vollständigkeits-Check in
  `/api/assign` (Summe der Klassengrößen vs. Anzahl SuS) greift unverändert und
  liefert bei Abweichung das `warning`-Feld.
- **Profil, das im Datensatz nicht vorkommt:** Da das Dropdown aus vorhandenen
  Werten gespeist wird, praktisch ausgeschlossen. Das Backend akzeptiert
  jeden nicht-leeren `profil`-String, verlässt sich also nicht allein auf das UI.

## 8. Tests (pytest, bestehendes `tests/`)

- `POST /api/add-student` im Modus Klasse 5: Schüler erscheint in der Antwort und
  in `_state["students"]`; Dict hat alle Klasse-5-Schlüssel.
- Dasselbe im Modus Klasse 8: Dict hat `bili`/`latein`/`imp_alternativ`,
  `latein` korrekt aus `fremdsprache2` abgeleitet.
- **ID-Eindeutigkeit:** zweimal denselben Namen anlegen → zwei verschiedene IDs.
- **Wunsch-Update zerstört nichts:** vorab einen Wunsch manuell klären
  (`resolved_wishes` setzen), dann Schüler hinzufügen → der geklärte Wunsch ist
  unverändert vorhanden; ein neuer Wunsch, der den Hinzugefügten nennt, taucht
  korrekt auf.
- **Validierung:** fehlender Vorname / Nachname / Profil → `400`.
- **Vorbedingung:** Hinzufügen ohne geladene SuS → `400`.

## 9. Repo, Versionierung, CI

- Remote: `https://github.com/hibbes/ClassMatcher.git`, Branch `main`.
- Vor der Arbeit `git pull --rebase`, nach jedem Commit `git push`.
- `APP_VERSION` (in `index.html` / `update.py`) wird mit dem Feature gebumpt,
  damit die bestehende CI-Release-Kette (SHA-256 der Binaries in `version.json`)
  konsistent bleibt.
- Keine Secrets oder echte PII in Tests: Test-Fixtures nutzen klar fiktive Namen.

## 10. Betroffene Dateien (Überblick)

- `static/index.html`: Sidebar-Sektion + `#add-student-modal`.
- `static/style.css`: ggf. kleine Ergänzungen (Formular-Reihen), meist Reuse.
- `static/app.js`: Button-/Modal-Verdrahtung, modus-adaptives Rendern der Felder,
  Profil-Dropdown-Befüllung, `fetch` auf `/api/add-student`, Board-Re-Render.
- `app.py`: Route `add-student`, Validierung, Dict-Bau, inkrementelles
  Wunsch-Update, Reuse des Assign-Blocks.
- `tests/`: neue Testfälle.
