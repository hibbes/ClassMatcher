# Nachname zuerst anzeigen + lange Namen lesbar machen

Datum: 2026-06-25
Status: Approved (brainstormed)

## Problem

Auf den Schülerkarten im Board steht der Name als „Vorname Nachname" und wird in einer
Zeile mit `text-overflow: ellipsis` abgeschnitten. Bei der Klasseneinteilung sucht die
Stufenleitung Schüler nach Nachnamen (amtliche Listen sind nach Nachname sortiert, die
Sortierung im Tool ist es bereits). Dadurch ist der relevante Namensteil oft nicht oder
nur abgeschnitten („Müller, Maxim…") sichtbar.

## Ziel

1. Name auf den Karten als **„Nachname, Vorname"** (Rufname wie bisher statt Vorname, falls gesetzt).
2. **Möglichst der ganze Name sichtbar**, statt mit „…" abgeschnitten.

## Entscheidungen (gebrainstormt)

- **Format:** `"Nachname, Vorname"` (mit Komma, konsistent mit der bestehenden Druckansicht).
- **Scope:** **beide Modi** (Modus 5 „5. Klassen" und Modus 8 „8. Klassen"), einheitliche Anzeige.
- **Lesbarkeit:** Name **umbricht** auf 2 Zeilen statt abgeschnitten zu werden, Kartenschrift
  `13px → 12px`. Spaltenbreite bleibt `260px` (kein zusätzliches Quer-Scrollen).

## Änderungen

### Backend `matcher.py`

`displayName` wird zentral genutzt (Karten, Liste offener Wünsche, Such-Dropdown beim
manuellen Hinzufügen), daher die Umstellung an der Quelle:

- Neue öffentliche Modul-Helper-Funktion `display_name(nachname, vorname)`, die `"Nachname, Vorname"`
  baut und **robust gegen leere Felder** ist (kein hängendes/führendes Komma). Öffentlich, weil auch
  `app.py` sie nutzt (siehe Reload unten).
- Eingesetzt an allen **vier** `displayName`-Konstruktionsstellen:
  - Modus-5-CSV-Parser (`parse_csv`), `display_first = rufname or vorname`
  - beide manuellen-Hinzufügen-Pfade (`build_manual_student`, klasse5 + klasse8)
  - Modus-8-CSV-Parser (`parse_csv_klasse8`)

Die **Zuweisungslogik bleibt unberührt**: Der Algorithmus rechnet mit `name`/`vorname`/Wünschen,
nicht mit `displayName`. Klasseneinteilungen ändern sich nicht.

### Backend `app.py` (gespeicherte Stände / Reload)

Exportierte `klassen-stand-*.json` enthalten `displayName` bereits (im alten Format), und
`load_state` übernahm das 1:1: ein geladener Stand hätte nach dem Update weiter „Vorname Nachname"
gezeigt. Fix: nach dem Setzen von `_state["students"]` wird `displayName` je Schüler aus `name` +
(`rufname` oder `vorname`) per `display_name()` neu abgeleitet (einheitlich für beide Modi; bei
klasse8 ist `rufname` leer → fällt auf `vorname`). So bekommt auch jeder bereits exportierte Stand
sofort das neue Format. Verifiziert mit einer echten 116-Schüler-Datei: nach `/api/load-state`
116/116 im neuen Format.

### Frontend `static/style.css`

- `.student-card` Schrift `13px → 12px` (`:619`).
- `.student-name` (`:652`): `white-space: nowrap` + `text-overflow: ellipsis` entfernen,
  stattdessen `white-space: normal; overflow-wrap: anywhere;` (umbrechen statt abschneiden).
- `.student-name-row` (`:645`): `align-items: center → flex-start`, damit Profil-/Zug-Badges
  beim Umbruch sauber neben der ersten Namenszeile oben stehen.

### Tests

- `tests/run_golden.py` (**ohne** `--update`): muss unverändert grün bleiben. Der Golden-Snapshot
  erfasst nur Klassen-IDs und Aggregate, **kein `displayName`** (siehe `snapshot()` in `run_golden.py`).
  Die reine Anzeige-Umstellung darf ihn also gar nicht verändern. Grün = Beweis, dass die Zuweisung
  unberührt ist. (Ursprünglich war hier `--update` geplant, das ist nicht nötig und wäre irreführend.)
- `tests/test_add_student.py` nachziehen, falls es `displayName` asserted.
- Kleiner Unit-Test für `display_name` inkl. Edge-Cases (leerer Vorname / leerer Nachname).

## Nicht-Ziele (YAGNI)

- Keine Spaltenverbreiterung, kein konfigurierbares Anzeigeformat, kein Umschalter.
- Keine Änderung an Fuzzy-Matching, CSV-Parsing-Spalten oder Algorithmus.

## Verifikation

- Golden-Master bleibt ohne `--update` grün (Zuweisung unberührt).
- Alle Tests grün (`run_golden.py`, `test_update.py`, `test_add_student.py`).
- Sichtprüfung im Browser: langer Name bricht um statt „…", Badges bleiben sichtbar.
