# Schüler:in manuell hinzufügen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Button in der linken Sidebar öffnet ein modus-adaptives Formular; ein damit angelegter Schüler wird per `POST /api/add-student` angehängt, seine Freundeswünsche werden inkrementell (ohne geklärte Wünsche zu zerstören) verarbeitet und die Person wird sofort automatisch in die Klassen einsortiert.

**Architecture:** Variante A aus der Spec: ein eigener Flask-Endpoint hängt den Schüler an `_state["students"]` an, aktualisiert die Wünsche additiv und ruft denselben Zuweisungs-Block wie `/api/assign` auf (extrahiert in den Helper `_assignment_payload`). Die Dict-Konstruktion und das Wunsch-Update leben in `matcher.py` (unit-testbar ohne Flask). Das Frontend folgt exakt dem bestehenden Pair-Modal-Muster.

**Tech Stack:** Python 3 + Flask (Backend, In-Memory-State), Vanilla JS + HTML + CSS (Frontend), pytest + scriptbasierte Golden-Tests.

**Referenz-Spec:** `docs/superpowers/specs/2026-06-16-schueler-hinzufuegen-design.md`

---

## Datei-Übersicht

| Datei | Änderung | Verantwortung |
|-------|----------|---------------|
| `matcher.py` | modify | `_student_wishes` (extrahiert), `add_student_wishes` (neu), `build_manual_student` (neu) |
| `app.py` | modify | `_assignment_payload` (extrahiert), `assign` (refactor), Route `/api/add-student` (neu), `APP_VERSION`-Bump |
| `static/index.html` | modify | Sidebar-Sektion + `#add-student-modal` + Version-Span |
| `static/style.css` | modify | kleine, gescopte Formular-Styles |
| `static/app.js` | modify | `api.addStudent`, `openAddStudentModal`, Save-Handler, `init()`-Verdrahtung |
| `tests/test_add_student.py` | create | Unit- + Integrationstests |

**Konstanten (zur Referenz, schon vorhanden in `matcher.py`):** `MUSIC_TRACK="5x"`, `BILI_TRACK="5y"`, `FILL_TRACK="5z"`, `AUTO_THRESHOLD=0.75`, `SUGGEST_THRESHOLD=0.45`.

**Hinweis zum Repo:** Vor Beginn `git pull --rebase origin main`. Nach jedem Task-Commit `git push origin main` (Repo aktuell halten). Commit-Stil: Conventional Commits (`feat:`, `refactor:`, `test:`, `chore:`), deutsche Betreffzeile, keine Gedankenstriche.

---

## Task 0: Vorbereitung — venv reparieren + grüne Baseline

Der vorhandene `.venv` ist kaputt (Symlink zeigt auf das entfernte `python-exec/python3.13`, System-Python ist 3.14). Ohne lauffähigen Interpreter mit Flask/pytest läuft kein Test.

**Files:**
- Keine Quelländerung (nur Umgebung).

- [ ] **Step 1: venv neu bauen und Abhängigkeiten installieren**

```bash
cd /home/neo/projects/ClassMatcher
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install flask pytest
```

- [ ] **Step 2: Interpreter prüfen**

Run: `.venv/bin/python -c "import flask, pytest; print('flask', flask.__version__, 'pytest', pytest.__version__)"`
Expected: eine Zeile wie `flask 3.x.y pytest 8.x.y` (keine Exception).

- [ ] **Step 3: Bestehende Tests als Baseline laufen lassen**

Run: `.venv/bin/python tests/run_golden.py && .venv/bin/python -m pytest tests/ -q`
Expected: Golden-Runner endet mit Exit 0 (alle Szenarien grün), pytest meldet alle vorhandenen Tests `passed`. Falls Golden-Abweichungen auftreten, STOPP und melden — die Baseline muss grün sein, bevor refactored wird.

- [ ] **Step 4: Kein Commit** (nur Umgebung; `.venv` ist in `.gitignore`).

---

## Task 1: matcher — `_student_wishes` extrahieren, `process_wishes` refactoren (verhaltensgleich)

DRY-Vorarbeit: Die Wunsch-Logik eines einzelnen Schülers wird herausgezogen, damit `add_student_wishes` (Task 2) sie wiederverwenden kann. `process_wishes` muss byte-identisch bleiben (Golden-Master schützt das).

**Files:**
- Modify: `matcher.py` (Funktion `process_wishes`, aktuell ab Zeile 170)

- [ ] **Step 1: Golden-Baseline bestätigen (vor Änderung)**

Run: `.venv/bin/python tests/run_golden.py`
Expected: Exit 0, alle Szenarien grün.

- [ ] **Step 2: `process_wishes` ersetzen und `_student_wishes` einführen**

Ersetze die **gesamte** vorhandene Funktion `process_wishes` (von `def process_wishes(students: list) -> tuple:` bis zu ihrem `return resolved, pending`) durch die folgenden **zwei** Funktionen:

```python
def _student_wishes(student: dict, others: list) -> tuple:
    """Freundeswünsche EINES Schülers gegen `others` auflösen.

    Rückgabe: (resolved_ids: list, pending_items: list)
    Identische Schwellen/Logik wie process_wishes, nur für einen Schüler.
    """
    res: list = []
    pend: list = []

    for token in tokenize_wishes(student["klassenpartner"]):
        matches = match_name(token, others)

        if not matches:
            pend.append({"token": token, "candidates": []})

        elif matches[0][1] >= AUTO_THRESHOLD:
            mid = matches[0][0]["id"]
            if mid not in res:
                res.append(mid)

        else:
            good = [(s, sc) for s, sc in matches if sc >= SUGGEST_THRESHOLD]
            pend.append({
                "token": token,
                "candidates": [
                    {"id": s["id"], "name": s["displayName"], "score": sc}
                    for s, sc in good[:3]
                ],
            })

    return res, pend


def process_wishes(students: list) -> tuple:
    """Alle Freundeswünsche verarbeiten.

    Rückgabe:
        resolved: {student_id: [matched_student_ids]}   – automatisch erkannt
        pending:  {student_id: [{token, candidates}]}    – manuell klären
    """
    resolved: dict = {}
    pending:  dict = {}

    for student in students:
        sid    = student["id"]
        others = [s for s in students if s["id"] != sid]
        resolved[sid], pending[sid] = _student_wishes(student, others)

    return resolved, pending
```

- [ ] **Step 3: Golden-Master prüfen (Verhaltensgleichheit)**

Run: `.venv/bin/python tests/run_golden.py`
Expected: Exit 0, byte-identische Zuweisung wie in Step 1. Bei Abweichung: Refactor hat das Verhalten geändert, zurückrollen und Logik angleichen.

- [ ] **Step 4: Commit**

```bash
git add matcher.py
git commit -m "refactor(matcher): _student_wishes aus process_wishes extrahieren"
git push origin main
```

---

## Task 2: matcher — `add_student_wishes` (inkrementelles, additives Wunsch-Update)

Der kritische Teil (§6.3 der Spec). Rein additiv: neuer Schüler frisch, bestehende Schüler nur an ihren **noch offenen** Pending-Tokens gegen den Neuen nachmatchen. Bereits geklärte Wünsche werden nie angefasst (keine Wiederauferstehung).

**Files:**
- Modify: `matcher.py` (neue Funktion hinter `process_wishes`)
- Create: `tests/test_add_student.py`

- [ ] **Step 1: Failing-Test schreiben**

Erstelle `tests/test_add_student.py` mit folgendem Inhalt:

```python
#!/usr/bin/env python3
"""Tests für das manuelle Hinzufügen einzelner Schüler:innen.

  .venv/bin/python -m pytest tests/test_add_student.py -v
"""
import io
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matcher  # noqa: E402
import app      # noqa: E402


# ── matcher.add_student_wishes ────────────────────────────────────────────

def test_add_student_wishes_new_student_own_wishes():
    others = [
        {"id": "a", "displayName": "Anna Beispiel", "vorname": "Anna",
         "rufname": "", "name": "Beispiel", "klassenpartner": ""},
        {"id": "b", "displayName": "Ben Muster", "vorname": "Ben",
         "rufname": "", "name": "Muster", "klassenpartner": ""},
    ]
    resolved = {"a": [], "b": []}
    pending  = {"a": [], "b": []}
    new = {"id": "n", "displayName": "Nora Neuling", "vorname": "Nora",
           "rufname": "", "name": "Neuling", "klassenpartner": "Anna Beispiel"}
    matcher.add_student_wishes(new, others, resolved, pending)
    assert resolved["n"] == ["a"]
    assert pending["n"] == []


def test_add_student_wishes_existing_pending_autoresolves_to_new():
    existing = [{"id": "x", "displayName": "Xaver Test", "vorname": "Xaver",
                 "rufname": "", "name": "Test", "klassenpartner": "Yara Neuling"}]
    resolved = {"x": []}
    pending  = {"x": [{"token": "Yara Neuling", "candidates": []}]}
    new = {"id": "y", "displayName": "Yara Neuling", "vorname": "Yara",
           "rufname": "", "name": "Neuling", "klassenpartner": ""}
    matcher.add_student_wishes(new, existing, resolved, pending)
    assert "y" in resolved["x"]      # auto-aufgelöst auf den Neuen
    assert pending["x"] == []        # Token aus pending entfernt
    assert resolved["y"] == []       # Neuer hat keine eigenen Wünsche


def test_add_student_wishes_does_not_resurrect_resolved_wish():
    # x hat den Wunsch "Yara" früher manuell geklärt: Token aus pending raus,
    # eine ID in resolved. Das Hinzufügen von Yara darf das NICHT umstoßen.
    existing = [{"id": "x", "displayName": "Xaver Test", "vorname": "Xaver",
                 "rufname": "", "name": "Test", "klassenpartner": "Yara"}]
    resolved = {"x": ["someone-else"]}
    pending  = {"x": []}
    new = {"id": "y", "displayName": "Yara Neuling", "vorname": "Yara",
           "rufname": "", "name": "Neuling", "klassenpartner": ""}
    matcher.add_student_wishes(new, existing, resolved, pending)
    assert pending["x"] == []                  # nicht wiederauferstanden
    assert resolved["x"] == ["someone-else"]   # unangetastet
    assert "y" not in resolved["x"]


def test_add_student_wishes_unrelated_token_preserved():
    existing = [{"id": "x", "displayName": "Xaver Test", "vorname": "Xaver",
                 "rufname": "", "name": "Test", "klassenpartner": "Zelda Fern"}]
    resolved = {"x": []}
    pending  = {"x": [{"token": "Zelda Fern", "candidates": []}]}
    new = {"id": "y", "displayName": "Yara Neuling", "vorname": "Yara",
           "rufname": "", "name": "Neuling", "klassenpartner": ""}
    matcher.add_student_wishes(new, existing, resolved, pending)
    assert pending["x"] == [{"token": "Zelda Fern", "candidates": []}]
    assert "y" not in resolved.get("x", [])
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `.venv/bin/python -m pytest tests/test_add_student.py -v`
Expected: FAIL mit `AttributeError: module 'matcher' has no attribute 'add_student_wishes'`.

- [ ] **Step 3: `add_student_wishes` implementieren**

Füge in `matcher.py` direkt hinter `process_wishes` ein:

```python
def add_student_wishes(new_student: dict, existing_students: list,
                       resolved: dict, pending: dict) -> None:
    """Inkrementelles, rein additives Wunsch-Update beim Hinzufügen EINES
    Schülers. Mutiert resolved/pending in-place.

    1) Wünsche des neuen Schülers gegen die bestehenden auflösen.
    2) Bestehende Schüler nur an ihren NOCH OFFENEN (pending) Tokens gegen
       den neuen Schüler nachmatchen. Bereits (auch manuell) geklärte Wünsche
       werden nie angefasst, daher keine Wiederauferstehung.
    """
    nid = new_student["id"]

    # 1) Neuer Schüler -> bestehende
    resolved[nid], pending[nid] = _student_wishes(new_student, existing_students)

    # 2) Bestehende -> nur offene Tokens, nur gegen den Neuen
    for s in existing_students:
        sid = s["id"]
        cur = pending.get(sid)
        if not cur:
            continue
        keep: list = []
        for slot in cur:
            m = match_name(slot["token"], [new_student])
            score = m[0][1] if m else 0.0
            if score >= AUTO_THRESHOLD:
                # eindeutig -> auto-auflösen, Token aus pending entfernen
                resolved.setdefault(sid, [])
                if nid not in resolved[sid]:
                    resolved[sid].append(nid)
                continue  # nicht behalten
            if score >= SUGGEST_THRESHOLD and not any(
                c["id"] == nid for c in slot["candidates"]
            ):
                slot = {
                    "token": slot["token"],
                    "candidates": slot["candidates"] + [
                        {"id": nid, "name": new_student["displayName"],
                         "score": score}
                    ],
                }
            keep.append(slot)
        pending[sid] = keep
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `.venv/bin/python -m pytest tests/test_add_student.py -v`
Expected: alle 4 Tests `passed`.

- [ ] **Step 5: Commit**

```bash
git add matcher.py tests/test_add_student.py
git commit -m "feat(matcher): add_student_wishes für inkrementelles Wunsch-Update"
git push origin main
```

---

## Task 3: matcher — `build_manual_student` (Dict-Bau + kollisionsfreie ID)

Baut ein Schüler-Dict schlüsselgleich zur jeweiligen `parse_*`-Ausgabe und vergibt eine eindeutige `manual-`-ID.

**Files:**
- Modify: `matcher.py` (neue Funktion hinter `add_student_wishes`)
- Modify: `tests/test_add_student.py` (Tests anhängen)

- [ ] **Step 1: Failing-Tests anhängen**

Hänge an `tests/test_add_student.py` an:

```python
# ── matcher.build_manual_student ──────────────────────────────────────────

def test_build_manual_student_klasse5_keys_and_display():
    s = matcher.build_manual_student("klasse5", {
        "vorname": "Mia", "name": "Muster", "rufname": "", "profil": "5z",
        "geschlecht": "w", "fremdsprache2": "F", "klassenpartner": "", "ru": "rk",
    }, set())
    expected = {"id", "name", "vorname", "rufname", "displayName", "geschlecht",
                "profil", "klassenpartner", "vorhKlasse", "abgebendeSchule",
                "geburtsdatum", "fremdsprache2", "ru", "religion"}
    assert set(s.keys()) == expected
    assert s["displayName"] == "Mia Muster"
    assert s["id"].startswith("manual-")
    assert s["religion"] == ""
    assert s["ru"] == "rk"


def test_build_manual_student_klasse5_rufname_wins_in_display():
    s = matcher.build_manual_student("klasse5", {
        "vorname": "Maximilian", "name": "Muster", "rufname": "Max",
        "profil": "5z", "geschlecht": "m", "fremdsprache2": "L",
        "klassenpartner": "", "ru": "",
    }, set())
    assert s["displayName"] == "Max Muster"


def test_build_manual_student_klasse8_keys_and_latein():
    s = matcher.build_manual_student("klasse8", {
        "vorname": "Ben", "name": "Beispiel", "profil": "NWT",
        "geschlecht": "m", "fremdsprache2": "L", "klassenpartner": "",
        "bili": True, "imp_alternativ": False,
    }, set())
    expected = {"id", "name", "vorname", "rufname", "displayName", "geschlecht",
                "profil", "klassenpartner", "vorhKlasse", "abgebendeSchule",
                "geburtsdatum", "fremdsprache2", "bili", "latein", "imp_alternativ"}
    assert set(s.keys()) == expected
    assert s["latein"] is True       # aus fremdsprache2 == "L" abgeleitet
    assert s["bili"] is True
    assert s["displayName"] == "Ben Beispiel"


def test_build_manual_student_unique_ids():
    ids = set()
    fields = {"vorname": "Mia", "name": "Muster", "rufname": "", "profil": "5z",
              "geschlecht": "w", "fremdsprache2": "F", "klassenpartner": "", "ru": ""}
    s1 = matcher.build_manual_student("klasse5", fields, ids); ids.add(s1["id"])
    s2 = matcher.build_manual_student("klasse5", fields, ids); ids.add(s2["id"])
    assert s1["id"] != s2["id"]
    assert s1["id"].startswith("manual-") and s2["id"].startswith("manual-")
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `.venv/bin/python -m pytest tests/test_add_student.py -k build_manual_student -v`
Expected: FAIL mit `AttributeError: module 'matcher' has no attribute 'build_manual_student'`.

- [ ] **Step 3: `build_manual_student` implementieren**

Füge in `matcher.py` direkt hinter `add_student_wishes` ein:

```python
def build_manual_student(mode: str, fields: dict, existing_ids: set) -> dict:
    """Schüler-Dict aus Formularfeldern bauen, schlüsselgleich zur jeweiligen
    parse_*-Ausgabe. Vergibt eine kollisionsfreie ID mit Präfix 'manual-'.

    `fields` enthält getrimmte Strings/Booleans aus dem Request.
    `existing_ids` ist die Menge bereits vergebener IDs.
    """
    vorname = fields["vorname"]
    name    = fields["name"]

    base = f"manual-{normalize(vorname)}-{normalize(name)}".strip("-")
    sid  = base
    idx  = 2
    while sid in existing_ids:
        sid = f"{base}-{idx}"
        idx += 1

    fs2 = (fields.get("fremdsprache2") or "F").upper()

    if mode == "klasse8":
        return {
            "id":             sid,
            "name":           name,
            "vorname":        vorname,
            "rufname":        "",
            "displayName":    f"{vorname} {name}".strip(),
            "geschlecht":     fields.get("geschlecht", ""),
            "profil":         fields["profil"],
            "klassenpartner": fields.get("klassenpartner", ""),
            "vorhKlasse":     "",
            "abgebendeSchule":"",
            "geburtsdatum":   "",
            "fremdsprache2":  fs2,
            "bili":           bool(fields.get("bili", False)),
            "latein":         fs2 == "L",
            "imp_alternativ": bool(fields.get("imp_alternativ", False)),
        }

    # klasse5
    rufname       = fields.get("rufname", "")
    display_first = rufname or vorname
    return {
        "id":             sid,
        "name":           name,
        "vorname":        vorname,
        "rufname":        rufname,
        "displayName":    f"{display_first} {name}".strip(),
        "geschlecht":     fields.get("geschlecht", ""),
        "profil":         fields["profil"],
        "klassenpartner": fields.get("klassenpartner", ""),
        "vorhKlasse":     "",
        "abgebendeSchule":"",
        "geburtsdatum":   "",
        "fremdsprache2":  fs2,
        "ru":             fields.get("ru", ""),
        "religion":       "",
    }
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `.venv/bin/python -m pytest tests/test_add_student.py -v`
Expected: alle Tests (Task 2 + Task 3) `passed`.

- [ ] **Step 5: Commit**

```bash
git add matcher.py tests/test_add_student.py
git commit -m "feat(matcher): build_manual_student baut Schüler-Dict + eindeutige ID"
git push origin main
```

---

## Task 4: app — `_assignment_payload` extrahieren, `assign` refactoren (+ `pendingCount`)

DRY: Der Zuweisungs-/Antwort-Block aus `assign()` wird in einen Helper gezogen, den auch `/api/add-student` nutzt. Der Helper ergänzt `pendingCount` (rückwärtskompatibel; das Frontend ignoriert Zusatzfelder).

**Files:**
- Modify: `app.py` (Helper vor `assign()` einfügen, `assign()`-Body ersetzen)
- Modify: `tests/test_add_student.py` (Charakterisierungstest anhängen)

- [ ] **Step 1: Charakterisierungstest anhängen (rot)**

Hänge an `tests/test_add_student.py` an:

```python
# ── /api/assign liefert pendingCount (nach Refactor) ──────────────────────

K5_CSV = (
    "ID;Name;Vorname;Rufname;Geschlecht;Profil1;Klassenpartner;vorhKlasse;"
    "AbgebendeSchule;Geburtstag;Fremdsprache2;RU;Religion\n"
    "1;Apfel;Anna;;w;5z;Bernd Birne;;GS Beispiel;01.01.2014;F;rk;rk\n"
    "2;Birne;Bernd;;m;5z;Anna Apfel;;GS Beispiel;02.02.2014;F;ev;ev\n"
    "3;Clementine;Carla;;w;5x;;;GS Beispiel;03.03.2014;F;;\n"
    "4;Dattel;David;;m;5x;;;GS Beispiel;04.04.2014;L;rk;rk\n"
    "5;Erdbeere;Emma;;w;5y;;;GS Beispiel;05.05.2014;F;;\n"
    "6;Feige;Felix;;m;5y;;;GS Beispiel;06.06.2014;F;ev;ev\n"
    "7;Gurke;Greta;;w;5z;;;GS Beispiel;07.07.2014;F;;\n"
    "8;Holunder;Hans;;m;5z;;;GS Beispiel;08.08.2014;L;rk;rk\n"
)


def _client():
    app.app.config["TESTING"] = True
    return app.app.test_client()


def _upload_k5(c):
    return c.post("/api/upload", data={
        "mode": "klasse5",
        "file": (io.BytesIO(K5_CSV.encode("utf-8")), "k5.csv"),
    }, content_type="multipart/form-data")


def test_assign_returns_pendingcount():
    c = _client()
    assert _upload_k5(c).status_code == 200
    r = c.post("/api/assign", json={"lockedStudents": {}})
    assert r.status_code == 200
    body = r.get_json()
    assert "classes" in body
    assert "stats" in body
    assert "pendingCount" in body
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `.venv/bin/python -m pytest tests/test_add_student.py::test_assign_returns_pendingcount -v`
Expected: FAIL mit `assert 'pendingCount' in body` (assign liefert das Feld noch nicht).

- [ ] **Step 3: Helper `_assignment_payload` einfügen**

Füge in `app.py` **unmittelbar vor** `@app.route("/api/assign", ...)` (aktuell Zeile 494) ein:

```python
def _assignment_payload(locked: dict) -> dict:
    """Führt die Klassen-Zuweisung aus und baut die JSON-Antwort.

    Gemeinsamer Kern von /api/assign und /api/add-student. Setzt
    _state["last_assignment"] und liefert {classes, stats, pendingCount[, warning]}.
    """
    from matcher import calculate_classes, calculate_classes_klasse8, calculate_stats

    if _state["mode"] == "klasse8":
        classes = calculate_classes_klasse8(
            _state["students"], _state["params"], _state["resolved_wishes"],
            _state["dont_be_with"], locked_students=locked,
        )
    else:
        classes = calculate_classes(
            _state["students"], _state["params"], _state["resolved_wishes"],
            _state["dont_be_with"], locked_students=locked,
        )

    _apply_class_names(classes)
    sm = _student_map()

    response_classes = [
        {
            "id":       cls["id"],
            "name":     cls.get("name", cls["id"]),
            "track":    cls["track"],
            "students": [sm[sid] for sid in cls["students"] if sid in sm],
        }
        for cls in classes
    ]
    response_classes = _sort_klasse5_classes(response_classes)

    _attach_wish_info(response_classes, sm)

    stats = calculate_stats(
        [{"id": c["id"], "students": [s["id"] for s in c["students"]]}
         for c in response_classes],
        sm,
        _state["resolved_wishes"],
        _state["dont_be_with"],
    )

    _state["last_assignment"] = {"classes": response_classes, "stats": stats}

    payload = {
        "classes":      response_classes,
        "stats":        stats,
        "pendingCount": _pending_count(),
    }
    assigned_total = sum(len(c["students"]) for c in response_classes)
    expected_total = len(_state["students"])
    if assigned_total != expected_total:
        payload["warning"] = (
            f"Unvollständige Zuweisung: {assigned_total} von {expected_total} "
            f"Schüler:innen verteilt ({expected_total - assigned_total} fehlen). "
            "Bitte prüfen."
        )
    return payload
```

- [ ] **Step 4: `assign()`-Body durch Helper-Aufruf ersetzen**

Ersetze die **gesamte** vorhandene `assign`-Funktion (von `@app.route("/api/assign", methods=["POST"])` bis zu ihrem abschließenden `return jsonify(...) / except`-Block, aktuell Zeilen 494 bis 567) durch:

```python
@app.route("/api/assign", methods=["POST"])
def assign():
    if not _state["students"]:
        return jsonify({"error": "Keine Schüler geladen"}), 400
    try:
        data   = request.json or {}
        locked = data.get("lockedStudents", _state["locked_students"])
        return jsonify(_assignment_payload(locked))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 5: Charakterisierungstest grün + Golden grün**

Run: `.venv/bin/python -m pytest tests/test_add_student.py::test_assign_returns_pendingcount -v && .venv/bin/python tests/run_golden.py`
Expected: Test `passed`, Golden-Runner Exit 0 (Matcher unverändert).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_add_student.py
git commit -m "refactor(app): Zuweisungs-Antwort in _assignment_payload bündeln (+ pendingCount)"
git push origin main
```

---

## Task 5: app — Route `POST /api/add-student`

Validiert, baut das Dict, hängt an, aktualisiert Wünsche inkrementell und gibt die frische Zuweisung zurück.

**Files:**
- Modify: `app.py` (neue Route nach `assign()`)
- Modify: `tests/test_add_student.py` (Endpoint-Tests anhängen)

- [ ] **Step 1: Failing-Endpoint-Tests anhängen**

Hänge an `tests/test_add_student.py` an:

```python
# ── /api/add-student ──────────────────────────────────────────────────────

def test_add_student_requires_loaded_roster():
    app._state["students"] = []
    c = _client()
    r = c.post("/api/add-student", json={
        "vorname": "X", "name": "Y", "profil": "5z", "geschlecht": "w"})
    assert r.status_code == 400


def test_add_student_klasse5_integration():
    c = _client()
    assert _upload_k5(c).status_code == 200
    before = len(app._state["students"])
    r = c.post("/api/add-student", json={
        "vorname": "Nora", "name": "Neuling", "profil": "5z",
        "geschlecht": "w", "fremdsprache2": "F", "klassenpartner": "Anna Apfel",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert "classes" in body and "stats" in body and "pendingCount" in body
    assert len(app._state["students"]) == before + 1
    all_ids = [s["id"] for cls in body["classes"] for s in cls["students"]]
    new_ids = [s["id"] for s in app._state["students"]
               if s["id"].startswith("manual-")]
    assert new_ids and new_ids[0] in all_ids


def test_add_student_klasse5_validation():
    c = _client()
    _upload_k5(c)
    assert c.post("/api/add-student", json={
        "vorname": "", "name": "Y", "profil": "5z", "geschlecht": "w"}).status_code == 400
    assert c.post("/api/add-student", json={
        "vorname": "X", "name": "Y", "profil": "", "geschlecht": "w"}).status_code == 400
    assert c.post("/api/add-student", json={
        "vorname": "X", "name": "Y", "profil": "5z", "geschlecht": "q"}).status_code == 400


def test_add_student_klasse8_integration():
    c = _client()
    csv_bytes = (ROOT / "tests" / "fixtures" / "profilwahl_klasse8.csv").read_bytes()
    up = c.post("/api/upload", data={
        "mode": "klasse8",
        "file": (io.BytesIO(csv_bytes), "k8.csv"),
    }, content_type="multipart/form-data")
    assert up.status_code == 200
    before = len(app._state["students"])
    valid_profil = app._state["students"][0]["profil"]
    r = c.post("/api/add-student", json={
        "vorname": "Ben", "name": "Beispiel", "profil": valid_profil,
        "geschlecht": "m", "fremdsprache2": "L", "bili": True,
    })
    assert r.status_code == 200
    assert len(app._state["students"]) == before + 1
    new = [s for s in app._state["students"] if s["id"].startswith("manual-")][0]
    assert new["latein"] is True
    assert new["bili"] is True
    assert "imp_alternativ" in new


def test_add_student_preserves_resolved_wishes():
    c = _client()
    _upload_k5(c)
    # Simuliere eine zuvor manuell geklärte Auflösung:
    app._state["resolved_wishes"]["1"] = ["2"]
    app._state["pending_wishes"]["1"] = []
    r = c.post("/api/add-student", json={
        "vorname": "Tom", "name": "Test", "profil": "5z", "geschlecht": "m"})
    assert r.status_code == 200
    assert app._state["resolved_wishes"]["1"] == ["2"]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `.venv/bin/python -m pytest tests/test_add_student.py -k "add_student_requires or klasse5_integration or klasse5_validation or klasse8_integration or preserves_resolved" -v`
Expected: FAIL (Route fehlt -> `404 NOT FOUND`, Assertions auf `200` schlagen fehl).

- [ ] **Step 3: Route implementieren**

Füge in `app.py` **direkt hinter** der `assign`-Funktion (vor `@app.route("/api/refine-friends", ...)`) ein:

```python
@app.route("/api/add-student", methods=["POST"])
def add_student():
    """Einen einzelnen Schüler manuell anlegen und sofort einsortieren."""
    from matcher import build_manual_student, add_student_wishes

    if not _state["students"]:
        return jsonify({"error": "Keine Schüler geladen"}), 400

    data = request.json or {}

    def clean(key, maxlen=200):
        return str(data.get(key) or "").strip()[:maxlen]

    vorname    = clean("vorname")
    name       = clean("name")
    profil     = clean("profil")
    geschlecht = clean("geschlecht").lower()
    fs2        = (clean("fremdsprache2").upper() or "F")

    if not vorname or not name:
        return jsonify({"error": "Vorname und Nachname sind Pflicht"}), 400
    if not profil:
        return jsonify({"error": "Profil ist Pflicht"}), 400
    if geschlecht not in ("m", "w", ""):
        return jsonify({"error": "Ungültiges Geschlecht"}), 400
    if fs2 not in ("F", "L"):
        return jsonify({"error": "Ungültige 2. Fremdsprache"}), 400

    fields = {
        "vorname":        vorname,
        "name":           name,
        "profil":         profil,
        "geschlecht":     geschlecht,
        "fremdsprache2":  fs2,
        "rufname":        clean("rufname"),
        "klassenpartner": clean("klassenpartner", 1000),
        "ru":             clean("ru"),
        "bili":           bool(data.get("bili", False)),
        "imp_alternativ": bool(data.get("imp_alternativ", False)),
    }

    existing_ids      = {s["id"] for s in _state["students"]}
    existing_students = list(_state["students"])
    new_student       = build_manual_student(_state["mode"], fields, existing_ids)

    _state["students"].append(new_student)
    add_student_wishes(
        new_student, existing_students,
        _state["resolved_wishes"], _state["pending_wishes"],
    )

    try:
        return jsonify(_assignment_payload(_state["locked_students"]))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 4: Gesamte Backend-Suite grün**

Run: `.venv/bin/python -m pytest tests/test_add_student.py -v && .venv/bin/python tests/run_golden.py`
Expected: alle Tests `passed`, Golden-Runner Exit 0.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_add_student.py
git commit -m "feat(app): /api/add-student legt Schüler an und sortiert sofort ein"
git push origin main
```

---

## Task 6: Frontend — Sidebar-Sektion + Modal in `index.html`

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Sidebar-Sektion einfügen**

Füge in `static/index.html` innerhalb von `<aside id="sidebar" ...>` als **erste** Sektion (unmittelbar nach `<aside id="sidebar" class="hidden">`, vor `<section class="sidebar-section"><h3>Klassengröße</h3>`) ein:

```html
    <section class="sidebar-section">
      <h3>Schüler:in</h3>
      <button id="btn-add-student" class="btn btn-ghost btn-sm">+ Schüler:in hinzufügen</button>
    </section>

```

- [ ] **Step 2: Modal einfügen**

Füge in `static/index.html` **unmittelbar nach** dem schließenden `</div>` des `#pair-modal` (nach der Zeile mit `<!-- ═══════════════════════ PAIR MODAL ... -->` Block, vor `<!-- ═══════════════════════ HILFE MODAL ... -->`) ein:

```html
<!-- ═══════════════════ SCHÜLER-HINZUFÜGEN MODAL ════════════════════ -->
<div id="add-student-modal" class="modal-overlay hidden">
  <div class="modal modal-sm">
    <div class="modal-header">
      <h2>Schüler:in hinzufügen</h2>
      <button class="modal-close" id="add-student-close">✕</button>
    </div>
    <div class="modal-body">
      <div class="as-form">
        <label class="as-row">Vorname *
          <input type="text" id="as-vorname" autocomplete="off" />
        </label>
        <label class="as-row">Nachname *
          <input type="text" id="as-name" autocomplete="off" />
        </label>
        <label class="as-row" data-mode="klasse5">Rufname
          <input type="text" id="as-rufname" autocomplete="off" />
        </label>
        <label class="as-row">Geschlecht *
          <select id="as-geschlecht">
            <option value="" disabled selected>– bitte wählen –</option>
            <option value="m">Junge</option>
            <option value="w">Mädchen</option>
            <option value="d">divers / unbekannt</option>
          </select>
        </label>
        <label class="as-row">Profil *
          <select id="as-profil">
            <option value="" disabled selected>– bitte wählen –</option>
          </select>
        </label>
        <label class="as-row">2. Fremdsprache
          <select id="as-fremdsprache2">
            <option value="F" selected>Französisch</option>
            <option value="L">Latein</option>
          </select>
        </label>
        <label class="as-row" data-mode="klasse5">Religionsunterricht
          <input type="text" id="as-ru" autocomplete="off" placeholder="z.B. rk, ev, eth" />
        </label>
        <label class="as-check" data-mode="klasse8">
          <input type="checkbox" id="as-bili" /> <span>Bili-Zug</span>
        </label>
        <label class="as-check" data-mode="klasse8">
          <input type="checkbox" id="as-imp" /> <span>hätte IMP gewählt</span>
        </label>
        <label class="as-row">Freundeswünsche
          <textarea id="as-klassenpartner" rows="2" placeholder="Namen, durch Komma getrennt"></textarea>
        </label>
      </div>
    </div>
    <div class="modal-footer">
      <button id="add-student-cancel" class="btn btn-ghost">Abbrechen</button>
      <button id="add-student-save" class="btn btn-primary" disabled>Hinzufügen</button>
    </div>
  </div>
</div>

```

- [ ] **Step 3: Markup-Smoke-Check**

Run: `grep -c "id=\"add-student-modal\"\|id=\"btn-add-student\"\|id=\"as-vorname\"\|id=\"add-student-save\"" static/index.html`
Expected: Ausgabe `4` (alle vier IDs vorhanden).

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat(ui): Sidebar-Button und Modal für Schüler-Hinzufügen"
git push origin main
```

---

## Task 7: Frontend — gescopte Formular-Styles in `style.css`

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: CSS anhängen**

Hänge ans Ende von `static/style.css` an:

```css
/* ── Schüler-Hinzufügen-Modal ──────────────────────────────────── */
.as-form { display: flex; flex-direction: column; gap: 10px; }
.as-row { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: #334155; font-weight: 500; }
.as-row input[type="text"],
.as-row select,
.as-row textarea {
  font: inherit; padding: 7px 9px; border: 1px solid #cbd5e1;
  border-radius: 7px; background: #fff; color: #0f172a;
}
.as-row textarea { resize: vertical; }
.as-row input:focus, .as-row select:focus, .as-row textarea:focus {
  outline: none; border-color: #6366f1; box-shadow: 0 0 0 2px #6366f133;
}
.as-check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #334155; }
#add-student-save[disabled] { opacity: .5; cursor: not-allowed; }
```

- [ ] **Step 2: Commit**

```bash
git add static/style.css
git commit -m "style(ui): Formular-Styles für Schüler-Hinzufügen-Modal"
git push origin main
```

---

## Task 8: Frontend — `app.js` (API, Modal-Logik, Verdrahtung)

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: `api.addStudent` ergänzen**

Füge im `api`-Objekt (in `static/app.js`, innerhalb des `const api = { ... }`-Blocks, z.B. direkt nach der `assign`-Methode) ein:

```javascript
  async addStudent(payload) {
    const r = await fetch("/api/add-student", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    return r.json();
  },
```

- [ ] **Step 2: Modal-Funktionen ergänzen**

Füge in `static/app.js` **unmittelbar vor** `function setupStudentSearch(` ein:

```javascript
// ──────────────────────────────────────────────────────────────────
// Schüler:in hinzufügen
// ──────────────────────────────────────────────────────────────────

function validateAddStudentForm() {
  const vorname = document.getElementById("as-vorname").value.trim();
  const name    = document.getElementById("as-name").value.trim();
  const profil  = document.getElementById("as-profil").value;
  const gesch   = document.getElementById("as-geschlecht").value;
  const ok = vorname && name && profil && (gesch === "m" || gesch === "w" || gesch === "d");
  document.getElementById("add-student-save").disabled = !ok;
}

function openAddStudentModal() {
  const modal = document.getElementById("add-student-modal");

  for (const id of ["as-vorname", "as-name", "as-rufname", "as-ru", "as-klassenpartner"]) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  document.getElementById("as-geschlecht").value     = "";
  document.getElementById("as-fremdsprache2").value  = "F";
  document.getElementById("as-bili").checked         = false;
  document.getElementById("as-imp").checked          = false;

  // Profil-Dropdown aus den im Datensatz vorhandenen Werten befüllen
  const profile = [...new Set(state.students.map(s => s.profil).filter(Boolean))].sort();
  const sel = document.getElementById("as-profil");
  sel.innerHTML = '<option value="" disabled selected>– bitte wählen –</option>'
    + profile.map(p => `<option value="${escapeAttr(p)}">${escapeHtml(p)}</option>`).join("");

  // Modus-spezifische Felder zeigen/verstecken (lokal, ohne Seiteneffekt)
  modal.querySelectorAll("[data-mode]").forEach(el => {
    el.classList.toggle("hidden", el.getAttribute("data-mode") !== state.mode);
  });

  validateAddStudentForm();
  modal.classList.remove("hidden");
}

function collectAddStudentForm() {
  const gesch = document.getElementById("as-geschlecht").value;
  return {
    vorname:        document.getElementById("as-vorname").value.trim(),
    name:           document.getElementById("as-name").value.trim(),
    rufname:        document.getElementById("as-rufname").value.trim(),
    geschlecht:     (gesch === "m" || gesch === "w") ? gesch : "",
    profil:         document.getElementById("as-profil").value,
    fremdsprache2:  document.getElementById("as-fremdsprache2").value,
    klassenpartner: document.getElementById("as-klassenpartner").value.trim(),
    ru:             document.getElementById("as-ru").value.trim(),
    bili:           document.getElementById("as-bili").checked,
    imp_alternativ: document.getElementById("as-imp").checked,
  };
}
```

- [ ] **Step 3: Verdrahtung in `init()` ergänzen**

Füge in `static/app.js` innerhalb von `function init()`, direkt nach dem `// ── Paare-Modal ──`-Block (nach dem `pair-save`-Listener, vor dem `// ── Hilfe-Modal ──`-Block), ein:

```javascript
  // ── Schüler-hinzufügen-Modal ──────────────────────────────
  document.getElementById("btn-add-student").addEventListener("click", openAddStudentModal);
  document.getElementById("add-student-close").addEventListener("click", () =>
    document.getElementById("add-student-modal").classList.add("hidden")
  );
  document.getElementById("add-student-cancel").addEventListener("click", () =>
    document.getElementById("add-student-modal").classList.add("hidden")
  );
  for (const id of ["as-vorname", "as-name"]) {
    document.getElementById(id).addEventListener("input", validateAddStudentForm);
  }
  document.getElementById("as-profil").addEventListener("change", validateAddStudentForm);
  document.getElementById("as-geschlecht").addEventListener("change", validateAddStudentForm);

  document.getElementById("add-student-save").addEventListener("click", async () => {
    const saveBtn = document.getElementById("add-student-save");
    const payload = collectAddStudentForm();
    if (!payload.vorname || !payload.name || !payload.profil) return;
    saveBtn.disabled = true;
    try {
      const result = await api.addStudent(payload);
      if (result.error) { alert("Fehler: " + result.error); return; }
      // Schülerliste auffrischen (für Suche/Render), Muster wie nach Upload
      state.students = await (await fetch("/api/students")).json();
      applyAssignmentResult(result);
      updateFuzzyBadge(result.pendingCount);
      if (result.warning) alert(result.warning);
      document.getElementById("add-student-modal").classList.add("hidden");
    } catch (err) {
      alert("Verbindungsfehler: " + err.message);
    } finally {
      saveBtn.disabled = false;
    }
  });
```

- [ ] **Step 4: JS-Syntax-Check**

Run: `node --check static/app.js && echo OK`
Expected: `OK` (keine Syntaxfehler). Falls `node` fehlt, ersatzweise im Browser-Test (Task 9) prüfen.

- [ ] **Step 5: Commit**

```bash
git add static/app.js
git commit -m "feat(ui): Modal-Logik und Verdrahtung für Schüler-Hinzufügen"
git push origin main
```

---

## Task 9: Version-Bump, End-to-End-Verifikation, Abschluss

**Files:**
- Modify: `app.py` (`APP_VERSION`)
- Modify: `static/index.html` (Version-Span, kosmetisch)

- [ ] **Step 1: APP_VERSION bumpen**

In `app.py` Zeile 11: `APP_VERSION = "1.6.23"` ersetzen durch:

```python
APP_VERSION = "1.6.24"
```

In `static/index.html` den statischen Span (Zeile mit `id="app-version"`) von `v1.5.4` auf `v1.6.24` setzen (kosmetisch; JS überschreibt ihn zur Laufzeit aus `/api/version`):

```html
      <span class="logo">Schiller-Klassen-Mixer <span id="app-version" style="color:#64748b;font-size:11px;font-weight:500">v1.6.24</span></span>
```

- [ ] **Step 2: Vollständige Test-Suite grün**

Run: `.venv/bin/python -m pytest tests/ -v && .venv/bin/python tests/run_golden.py`
Expected: alle Tests `passed`, Golden-Runner Exit 0.

- [ ] **Step 3: End-to-End-Smoke gegen den laufenden Server (Backend-Wire)**

```bash
.venv/bin/python app.py &
SRV=$!
sleep 2
# Klasse-8-Fixture hochladen
curl -s -F "mode=klasse8" -F "file=@tests/fixtures/profilwahl_klasse8.csv" http://localhost:5001/api/upload
echo
# Schüler hinzufügen (Profil muss im Datensatz existieren; hier ein im Fixture vorkommendes)
curl -s -X POST http://localhost:5001/api/add-student \
  -H "Content-Type: application/json" \
  -d '{"vorname":"Testkind","name":"Beispiel","profil":"NWT","geschlecht":"m","fremdsprache2":"F"}' \
  | head -c 400
echo
kill $SRV
```

Expected: Der Upload liefert JSON mit `"count"`/`"mode":"klasse8"`. Der add-student-Call liefert JSON mit `"classes"`, `"stats"`, `"pendingCount"` (oder bei ungültigem Profil eine `"error"`-Meldung; dann ein im Fixture real vorkommendes Profil einsetzen). Kein Traceback im Server-Log.

- [ ] **Step 4: Manuelle Browser-Verifikation**

Nutze das `run`- oder `verify`-Skill bzw. starte `.venv/bin/python app.py` und öffne `http://localhost:5001`:
1. CSV laden (Modus „5. Klassen einteilen"), Board erscheint.
2. Links erscheint die Sektion „Schüler:in" mit Button „+ Schüler:in hinzufügen". Klick öffnet das Modal.
3. Modus Klasse 5: Felder Rufname + Religionsunterricht sichtbar, keine Bili/IMP-Checkboxen. Profil-Dropdown enthält die im Datensatz vorhandenen Profile.
4. „Hinzufügen" bleibt grau, bis Vorname, Nachname, Geschlecht und Profil gesetzt sind.
5. Speichern → Modal schließt, der neue Schüler taucht auf dem Board auf, der `⚠`-Badge aktualisiert sich (falls Wünsche unklar).
6. Auf „8. Klassen neu mischen" wechseln und gegentesten: im Modal erscheinen stattdessen die Checkboxen „Bili-Zug" / „hätte IMP gewählt", Rufname/Religionsunterricht sind ausgeblendet.

Erwartet: alle sechs Punkte erfüllt, keine JS-Fehler in der Browser-Konsole.

- [ ] **Step 5: Abschluss-Commit**

```bash
git add app.py static/index.html
git commit -m "chore: APP_VERSION auf 1.6.24 (Feature Schüler-Hinzufügen)"
git push origin main
```

---

## Self-Review-Notiz (Plan-Autor)

- **Spec-Abdeckung:** Sidebar-Button + Modal (Task 6/8, Spec §5), modus-adaptive Felder inkl. Profil-Dropdown aus Datensatz (Task 8, §5.3), `/api/add-student` mit Validierung/ID/Dict (Task 3/5, §6.1-6.2), inkrementelles Wunsch-Update ohne Clobbering (Task 2, §6.3), sofortige Neuzuweisung via geteiltem Helper (Task 4/5, §4+§6.2), Tests beide Modi + ID + Wunsch-Erhalt + Validierung (Task 2/3/5, §8), Repo-Aktualität + Version-Bump (alle Commits + Task 9, §9). Randfälle §7: Namensdublette (Task 3 unique-id-Test), neuer Schüler ungelockt (Route setzt keinen Lock), Vollständigkeits-Warnung (Helper übernimmt bestehende Logik).
- **Out of scope** (Spec §3): kein Bearbeiten/Löschen, kein Bulk, keine Persistenz. Nicht eingeplant — korrekt.
- **Typkonsistenz:** Funktionsnamen über Tasks hinweg stabil (`_student_wishes`, `add_student_wishes`, `build_manual_student`, `_assignment_payload`, `api.addStudent`, `openAddStudentModal`, `validateAddStudentForm`, `collectAddStudentForm`); Element-IDs konsistent (`btn-add-student`, `add-student-modal`, `as-*`, `add-student-save/cancel/close`); Antwort-Schlüssel `classes/stats/pendingCount/warning` durchgängig.
