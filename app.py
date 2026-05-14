"""
ClassMatcher – Flask-Backend
Läuft lokal auf http://localhost:5001
"""
import os
import traceback
from flask import Flask, jsonify, request, send_from_directory

APP_VERSION = "1.5.4"

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
    """Klassennamen setzen: manuelle Umbenennung gewinnt, sonst Standard-Default."""
    if _state["mode"] == "klasse8":
        defaults = {cls["id"]: cls["id"].upper() for cls in classes}
    else:
        defaults = {"5y": "Bili-Klasse"}
    for cls in classes:
        if cls["id"] in _state["class_names"]:
            cls["name"] = _state["class_names"][cls["id"]]
        elif cls["id"] in defaults:
            cls["name"] = defaults[cls["id"]]


# ──────────────────────────────────────────────────────────────────────────────
# Statische Dateien
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/version")
def version():
    return jsonify({"version": APP_VERSION})

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
        content = f.read().decode("utf-8-sig")
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
