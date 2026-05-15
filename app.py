"""
ClassMatcher – Flask-Backend
Läuft lokal auf http://localhost:5001
"""
import os
import time
import threading
import traceback
from flask import Flask, jsonify, request, send_from_directory

APP_VERSION = "1.6.20"

app = Flask(__name__, static_folder="static")


# Verhindert, dass Browser HTML/JS/CSS cachen – bei lokalem Tool gewinnen
# wir damit, dass nach Update der EXE die alten Dateien nicht aus dem
# Browser-Cache geladen werden.
@app.after_request
def _no_cache(response):
    if request.path.startswith("/api/") or request.endpoint in (
        "index", "static_files",
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response

# ──────────────────────────────────────────────────────────────────────────────
# Anwendungs-Zustand (In-Memory)
# ──────────────────────────────────────────────────────────────────────────────

_state: dict = {
    "mode":            "klasse5",  # "klasse5" | "klasse8"
    "students":        [],
    "resolved_wishes": {},   # {student_id: [matched_ids]}
    "pending_wishes":  {},   # {student_id: [{token, candidates}]}
    "dont_be_with":    [],   # [{a: id, b: id, label: str}]
    "locked_students": {},   # {student_id: class_id}  ← Drag-&-Drop-Locks
    "class_names":     {},   # {class_id: custom_name}
    "last_assignment": {},   # {classes: […], stats: […]}  ← zuletzt berechnete Zuweisung
    "params": {
        "maxClassSize":           30,
        "minClassSize":           22,    # nur Modus klasse8 relevant
        "weightFriendWish":        7,    # höher als Gender (User-Wunsch 2026-05-11)
        "weightGenderBalance":     2,
        "weightMusicSplit":       50,    # 0..100 – Modus klasse5: Musikzug auf 2 Klassen
        "weightProfileCluster":   50,    # 0..100 – Modus klasse8: Profile zusammenhalten
        "multiStart":              5,    # Modus klasse8: Anzahl Multi-Start-SA-Läufe
        "autoRefine":              2,    # Modus klasse8: Friend-Refinement-Pässe pro Run
        # Power-User-Parameter (kein UI-Regler) – via POST /api/params oder Speicherdatei:
        "lateinMode":       "strict",    # Modus klasse8: "strict" | "musik_exception"
        "forceNumClasses":      None,    # Modus klasse8: feste Klassenzahl statt Auto
        "forceBiliSingleClass": False,   # Modus klasse8: alle Bili-SuS in genau einer Klasse
        "enforceMinOneWish":    True,    # Toggle: mind. 1 Wunsch pro SuS bevorzugen
        "enforceMusikMaxTwo":   True,    # Modus klasse5: Musikzug hart auf max 2 Klassen
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────────────────────────────────────

def _student_map():
    return {s["id"]: s for s in _state["students"]}


def _pending_count() -> int:
    """Anzahl Schüler mit noch offenen Fuzzy-Wünschen."""
    return sum(1 for v in _state["pending_wishes"].values() if v)


def _apply_class_names(classes: list) -> None:
    """Klassennamen setzen: manuelle Umbenennung gewinnt, sonst Rollen-Default.

    Modus 5 (4 Klassen):  Musik-Klassen → 5a/5b (Musikteile),
                          Bili-Klasse → 5c (Bili),
                          Lateinfreie Klasse → 5d (Französisch).
    """
    if _state["mode"] == "klasse8":
        defaults = {cls["id"]: cls["id"].upper() for cls in classes}
    else:
        defaults = _klasse5_role_names(classes)
    for cls in classes:
        if cls["id"] in _state["class_names"]:
            cls["name"] = _state["class_names"][cls["id"]]
        elif cls["id"] in defaults:
            cls["name"] = defaults[cls["id"]]


def _sort_klasse5_classes(classes: list) -> list:
    """Modus 5: Klassen alphabetisch nach Namen sortieren, damit
    5a (Musikteile) / 5b (Musikteile) / 5c (Bili) / 5d (Französisch)
    in dieser Reihenfolge erscheinen. Bei Modus 8 unveraendert."""
    if _state["mode"] != "klasse5":
        return classes
    return sorted(classes, key=lambda c: (c.get("name") or c["id"]).lower())


def _klasse5_role_names(classes: list) -> dict:
    """Default-Namen anhand der Klassen-Rollen ableiten (Modus 5).

    cls["students"] kann entweder Liste von SuS-IDs (Strings, frisch aus
    dem Matcher) oder Liste von SuS-Dicts (rekonstruierter Stand aus
    /api/load-state) sein — beides behandeln.
    """
    student_map = {s["id"]: s for s in _state["students"]}

    def _profil_of(s) -> str:
        if isinstance(s, dict):
            return s.get("profil") or ""
        return student_map.get(s, {}).get("profil") or ""

    def _fs2_of(s) -> str:
        if isinstance(s, dict):
            return s.get("fremdsprache2") or ""
        return student_map.get(s, {}).get("fremdsprache2") or ""

    music_per_cls: dict = {}
    has_bili: dict = {}
    has_latin: dict = {}
    for cls in classes:
        sids = cls.get("students", [])
        music_per_cls[cls["id"]] = sum(1 for s in sids if _profil_of(s) == "5x")
        has_bili[cls["id"]]      = any(_profil_of(s) == "5y" for s in sids)
        has_latin[cls["id"]]     = any(_fs2_of(s) == "L"   for s in sids)

    bili_id = next((cid for cid, b in has_bili.items() if b), None)
    music_ids = sorted(
        [cid for cid, n in music_per_cls.items() if n > 0 and cid != bili_id],
        key=lambda c: (-music_per_cls[c], c),
    )[:2]
    latin_free_id = next(
        (cls["id"] for cls in classes
         if cls["id"] != bili_id
         and cls["id"] not in music_ids
         and not has_latin[cls["id"]]),
        None,
    )

    names: dict = {}
    music_labels = ["5a (Musikteile)", "5b (Musikteile)"]
    for i, cid in enumerate(music_ids):
        names[cid] = music_labels[i]
    if bili_id:
        names[bili_id] = "5c (Bili)"
    if latin_free_id:
        names[latin_free_id] = "5d (Französisch)"
    return names


# ──────────────────────────────────────────────────────────────────────────────
# Statische Dateien
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/version")
def version():
    return jsonify({"version": APP_VERSION})


# ──────────────────────────────────────────────────────────────────────────────
# Heartbeat / Auto-Shutdown
# Browser sendet alle ~15s einen Heartbeat; wenn fuer eine Karenzzeit
# (HEARTBEAT_TIMEOUT) kein Heartbeat eintrudelt, beendet sich der Server selbst.
# Damit verschwindet der Hintergrund-Prozess automatisch wenn der User den
# Browser-Tab schliesst. Tab-Refresh ist kein Problem, weil der neue Tab den
# Heartbeat innerhalb 1-2s wieder aufnimmt.
# ──────────────────────────────────────────────────────────────────────────────

HEARTBEAT_TIMEOUT = 30  # Sekunden ohne Heartbeat -> Shutdown
_heartbeat_lock   = threading.Lock()
_last_heartbeat   = time.time() + 60   # 60s Initial-Karenz, falls Browser
                                       # erstmal noch laedt
_shutdown_started = False


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = time.time()
    return jsonify({"ok": True})


def _watchdog_loop():
    """Daemon-Thread: prueft alle 5s ob der Browser noch da ist."""
    global _shutdown_started
    while True:
        time.sleep(5)
        with _heartbeat_lock:
            elapsed = time.time() - _last_heartbeat
        if elapsed > HEARTBEAT_TIMEOUT and not _shutdown_started:
            _shutdown_started = True
            # Hard-Exit, damit alle Threads (inkl. Flask-Werkzeug) sicher
            # mit-beendet werden. sys.exit waere Flask-werkzeug-eaten.
            os._exit(0)


# Watchdog nur im PyInstaller-Bundle starten, NICHT im Source-Mode /
# bei Unit-Tests (sonst killen wir versehentlich Pytest-Runs).
import sys as _sys
if getattr(_sys, "frozen", False):
    threading.Thread(target=_watchdog_loop, daemon=True).start()


@app.route("/api/check-update")
def check_update():
    """Prüft die Schul-Homepage auf eine neuere Version.
    Aus dem Quellcode gestartet (nicht-frozen) → immer 'kein Update'."""
    import sys
    if not getattr(sys, "frozen", False):
        return jsonify({
            "update_available": False,
            "current": APP_VERSION,
            "latest": None,
            "download_url": None,
            "notes": None,
        })
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


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


# ──────────────────────────────────────────────────────────────────────────────
# CSV-Upload
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    from matcher import parse_csv, parse_csv_klasse8, process_wishes

    if "file" not in request.files:
        return jsonify({"error": "Keine Datei angegeben"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Nur CSV-Dateien werden unterstützt"}), 400

    mode = (request.form.get("mode") or "klasse5").strip()
    if mode not in ("klasse5", "klasse8"):
        return jsonify({"error": f"Unbekannter Modus: {mode}"}), 400

    try:
        raw = f.read()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("cp1252")
        if mode == "klasse8":
            students = parse_csv_klasse8(content)
        else:
            students = parse_csv(content)
        if not students:
            return jsonify({"error": "Keine Schüler gefunden – bitte CSV prüfen"}), 400

        _state["mode"]            = mode
        _state["students"]        = students
        _state["resolved_wishes"], _state["pending_wishes"] = process_wishes(students)
        _state["locked_students"] = {}
        _state["class_names"]     = {}
        _state["dont_be_with"]    = []

        pending_count = _pending_count()

        return jsonify({
            "count":        len(students),
            "pendingCount": pending_count,
            "mode":         mode,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Schüler-Liste
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/students")
def get_students():
    return jsonify(_state["students"])


# ──────────────────────────────────────────────────────────────────────────────
# Offene Fuzzy-Matches
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/pending-wishes")
def get_pending_wishes():
    sm = _student_map()
    result = []
    for sid, pending in _state["pending_wishes"].items():
        if not pending:
            continue
        s = sm.get(sid, {})
        result.append({
            "studentId":    sid,
            "studentName":  s.get("displayName", sid),
            "originalText": s.get("klassenpartner", ""),
            "pending":      pending,
        })
    return jsonify(result)


@app.route("/api/resolve-wish", methods=["POST"])
def resolve_wish():
    """Einen offenen Fuzzy-Match manuell auflösen."""
    data       = request.json or {}
    student_id = data.get("studentId")
    token      = data.get("token")
    matched_id = data.get("matchedId")   # None = ignorieren

    if not student_id or not token:
        return jsonify({"error": "Fehlende Parameter"}), 400

    if matched_id:
        lst = _state["resolved_wishes"].setdefault(student_id, [])
        if matched_id not in lst:
            lst.append(matched_id)

    # Aus der Pending-Liste entfernen
    if student_id in _state["pending_wishes"]:
        _state["pending_wishes"][student_id] = [
            p for p in _state["pending_wishes"][student_id]
            if p.get("token") != token
        ]

    pending_count = _pending_count()
    return jsonify({"ok": True, "pendingCount": pending_count})


# ──────────────────────────────────────────────────────────────────────────────
# Parameter
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/params", methods=["GET", "POST"])
def params():
    if request.method == "GET":
        return jsonify(_state["params"])
    _state["params"].update(request.json or {})
    return jsonify(_state["params"])


# ──────────────────────────────────────────────────────────────────────────────
# „Nicht zusammen"-Paare
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/dont-be-with", methods=["GET", "POST"])
def dont_be_with():
    if request.method == "GET":
        return jsonify(_state["dont_be_with"])
    _state["dont_be_with"] = (request.json or {}).get("pairs", [])
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────────────────────────
# Klassen-Zuweisung
# ──────────────────────────────────────────────────────────────────────────────

def _latin_free_class_id(classes: list) -> str | None:
    """Letzte Nicht-Bili-Klasse = lateinfreie Klasse (analog matcher.calculate_classes)."""
    fill_ids = [c["id"] for c in classes if c["id"] != "5y"]
    return fill_ids[-1] if len(fill_ids) >= 2 else None


def _klasse8_role_classes(response_classes: list, students_list: list) -> tuple:
    """Aus aktuellem Board ableiten, welche Klassen Bili/Latein/Musik tragen.

    Liefert (bili_classes, latein_classes, musik_class) — robust gegen
    manuelle Verschiebungen.
    """
    bili_set:   set = set()
    latein_set: set = set()
    musik_set:  set = set()
    from matcher import PROFIL_MUSIK
    for cls in response_classes:
        for s in cls["students"]:
            cid = cls["id"]
            if s.get("bili"):
                bili_set.add(cid)
            if s.get("latein"):
                latein_set.add(cid)
            if s.get("profil") == PROFIL_MUSIK and not s.get("bili"):
                musik_set.add(cid)
    bili_classes   = sorted(bili_set)
    latein_classes = sorted(latein_set)
    musik_class    = next(iter(sorted(musik_set)), None)
    return bili_classes, latein_classes, musik_class


def _attach_wish_info(response_classes: list, sm: dict) -> None:
    """Erfüllt-Status + Trennungsgrund zu jedem Schüler in response_classes hängen."""
    from matcher import wish_reason, wish_reason_klasse8

    sid_to_cls_id   = {}
    sid_to_cls_name = {}
    for cls in response_classes:
        for s in cls["students"]:
            sid_to_cls_id[s["id"]]   = cls["id"]
            sid_to_cls_name[s["id"]] = cls["name"]

    resolved = _state["resolved_wishes"]

    if _state["mode"] == "klasse8":
        bili_cls, latein_cls, musik_cls = _klasse8_role_classes(
            response_classes, _state["students"]
        )

        def reason_fn(s, friend, s_cid, f_cid):
            return wish_reason_klasse8(
                s, friend, s_cid, f_cid,
                bili_cls, latein_cls, musik_cls, resolved,
            )
    else:
        latin_free = _latin_free_class_id(response_classes)

        def reason_fn(s, friend, s_cid, f_cid):
            return wish_reason(s, friend, s_cid, f_cid, latin_free, resolved)

    for cls in response_classes:
        for s in cls["students"]:
            wish_info = []
            for fid in resolved.get(s["id"], []):
                if fid not in sm:
                    continue
                f_cls_id  = sid_to_cls_id.get(fid)
                fulfilled = (f_cls_id == cls["id"])
                entry = {
                    "friendId":    fid,
                    "friendName":  sm[fid]["displayName"],
                    "fulfilled":   fulfilled,
                    "friendClass": None if fulfilled else sid_to_cls_name.get(fid),
                }
                if not fulfilled:
                    entry["reason"] = reason_fn(s, sm[fid], cls["id"], f_cls_id)
                wish_info.append(entry)
            s["wishInfo"] = wish_info


@app.route("/api/assign", methods=["POST"])
def assign():
    from matcher import calculate_classes, calculate_classes_klasse8, calculate_stats

    if not _state["students"]:
        return jsonify({"error": "Keine Schüler geladen"}), 400

    try:
        data   = request.json or {}
        locked = data.get("lockedStudents", _state["locked_students"])

        if _state["mode"] == "klasse8":
            classes = calculate_classes_klasse8(
                _state["students"],
                _state["params"],
                _state["resolved_wishes"],
                _state["dont_be_with"],
                locked_students=locked,
            )
        else:
            classes = calculate_classes(
                _state["students"],
                _state["params"],
                _state["resolved_wishes"],
                _state["dont_be_with"],
                locked_students=locked,
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

        return jsonify({"classes": response_classes, "stats": stats})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────────────────────────────────────
# Klasse umbenennen
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/refine-friends", methods=["POST"])
def refine_friends():
    """SA-Refinement vom aktuellen Stand, fokussiert nur auf Freundeswünsche.

    Hard-Constraints und Locks bleiben aktiv. Klassengrößen ändern sich
    nicht (nur Swaps). Antwort wie /api/assign.
    """
    from matcher import (
        refine_friends_klasse8, refine_friends_klasse5, calculate_stats,
    )

    if not _state["students"] or not _state.get("last_assignment", {}).get("classes"):
        return jsonify({"error": "Keine Zuweisung zum Verfeinern vorhanden"}), 400

    try:
        current_classes = [
            {"id": c["id"], "students": [s["id"] for s in c["students"]]}
            for c in _state["last_assignment"]["classes"]
        ]

        # 3 Refinement-Pässe hintereinander – meist konvergiert es nach 1-2.
        refiner = refine_friends_klasse8 if _state["mode"] == "klasse8" else refine_friends_klasse5
        classes = current_classes
        for _ in range(3):
            classes = refiner(
                _state["students"],
                [{"id": c["id"], "students": list(c["students"])} for c in classes],
                _state["params"],
                _state["resolved_wishes"], _state["dont_be_with"],
                locked_students=_state["locked_students"],
            )
        _apply_class_names(classes)

        sm = _student_map()
        response_classes = [
            {"id": cls["id"], "name": cls.get("name", cls["id"]),
             "track": cls["track"],
             "students": [sm[sid] for sid in cls["students"] if sid in sm]}
            for cls in classes
        ]
        response_classes = _sort_klasse5_classes(response_classes)
        _attach_wish_info(response_classes, sm)
        stats = calculate_stats(
            [{"id": c["id"], "students": [s["id"] for s in c["students"]]}
             for c in response_classes],
            sm, _state["resolved_wishes"], _state["dont_be_with"],
        )
        _state["last_assignment"] = {"classes": response_classes, "stats": stats}

        return jsonify({"classes": response_classes, "stats": stats})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/rename-class", methods=["POST"])
def rename_class():
    data     = request.json or {}
    class_id = data.get("classId")
    name     = data.get("name", class_id)
    if class_id:
        _state["class_names"][class_id] = name
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────────────────────────
# Drag-&-Drop: Schüler manuell verschieben
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/move-student", methods=["POST"])
def move_student():
    data       = request.json or {}
    student_id = data.get("studentId")
    class_id   = data.get("classId")
    if student_id and class_id:
        _state["locked_students"][student_id] = class_id
    return jsonify({"ok": True})


@app.route("/api/unlock-student", methods=["POST"])
def unlock_student():
    sid = (request.json or {}).get("studentId")
    _state["locked_students"].pop(sid, None)
    return jsonify({"ok": True})


@app.route("/api/clear-locks", methods=["POST"])
def clear_locks():
    _state["locked_students"] = {}
    return jsonify({"ok": True})


# ──────────────────────────────────────────────────────────────────────────────
# Stand speichern / laden
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/save-state")
def save_state():
    """Aktuellen Stand als JSON zurückgeben (zum Download)."""
    return jsonify({
        "version":         2,
        "mode":            _state["mode"],
        "students":        _state["students"],
        "resolved_wishes": _state["resolved_wishes"],
        "pending_wishes":  _state["pending_wishes"],
        "dont_be_with":    _state["dont_be_with"],
        "locked_students": _state["locked_students"],
        "class_names":     _state["class_names"],
        "params":          _state["params"],
        "last_assignment": _state.get("last_assignment", {}),
    })


@app.route("/api/load-state", methods=["POST"])
def load_state():
    """Gespeicherten Stand wiederherstellen."""
    from matcher import calculate_stats

    data = request.json or {}

    mode = data.get("mode", "klasse5")
    if mode not in ("klasse5", "klasse8"):
        return jsonify({"error": "Ungültige Speicherdatei (unbekannter Modus)"}), 400
    _state["mode"]            = mode
    _state["students"]        = data.get("students", [])
    _state["resolved_wishes"] = data.get("resolved_wishes", {})
    _state["pending_wishes"]  = data.get("pending_wishes", {})
    _state["dont_be_with"]    = data.get("dont_be_with", [])
    _state["locked_students"] = data.get("locked_students", {})
    _state["class_names"]     = data.get("class_names", {})
    _state["params"].update(data.get("params", {}))

    saved = data.get("last_assignment", {})
    saved_classes = saved.get("classes", [])

    if not saved_classes or not _state["students"]:
        return jsonify({"error": "Ungültige Speicherdatei"}), 400

    sm = _student_map()

    # Klassenname aus class_names anwenden (analog zu assign())
    _apply_class_names(saved_classes)
    saved_classes = _sort_klasse5_classes(saved_classes)

    _attach_wish_info(saved_classes, sm)

    stats = calculate_stats(
        [{"id": c["id"], "students": [s["id"] for s in c["students"]]}
         for c in saved_classes],
        sm,
        _state["resolved_wishes"],
        _state["dont_be_with"],
    )

    _state["last_assignment"] = {"classes": saved_classes, "stats": stats}

    pending_count = _pending_count()

    return jsonify({
        "classes":      saved_classes,
        "stats":        stats,
        "count":        len(_state["students"]),
        "pendingCount": pending_count,
        "mode":         _state["mode"],
    })


# ──────────────────────────────────────────────────────────────────────────────
# Start
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="127.0.0.1", port=port, debug=False)
