"""
ClassMatcher – Flask-Backend
Läuft lokal auf http://localhost:5001
"""
import os
import traceback
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static")

# ──────────────────────────────────────────────────────────────────────────────
# Anwendungs-Zustand (In-Memory)
# ──────────────────────────────────────────────────────────────────────────────

_state: dict = {
    "students":        [],
    "resolved_wishes": {},   # {student_id: [matched_ids]}
    "pending_wishes":  {},   # {student_id: [{token, candidates}]}
    "dont_be_with":    [],   # [{a: id, b: id, label: str}]
    "locked_students": {},   # {student_id: class_id}  ← Drag-&-Drop-Locks
    "class_names":     {},   # {class_id: custom_name}
    "last_assignment": {},   # {classes: […], stats: […]}  ← zuletzt berechnete Zuweisung
    "params": {
        "maxClassSize":           30,
        "weightFriendWish":        5,
        "weightGenderBalance":     3,
        "weightMusicSplit":       50,   # 0..100 – Musikzug auf 2 Klassen verteilt
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────────────────────────────────────

def _student_map():
    return {s["id"]: s for s in _state["students"]}


# ──────────────────────────────────────────────────────────────────────────────
# Statische Dateien
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


# ──────────────────────────────────────────────────────────────────────────────
# CSV-Upload
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    from matcher import parse_csv, process_wishes

    if "file" not in request.files:
        return jsonify({"error": "Keine Datei angegeben"}), 400

    f = request.files["file"]
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Nur CSV-Dateien werden unterstützt"}), 400

    try:
        content  = f.read().decode("utf-8-sig")
        students = parse_csv(content)
        if not students:
            return jsonify({"error": "Keine Schüler gefunden – bitte CSV prüfen"}), 400

        _state["students"]        = students
        _state["resolved_wishes"], _state["pending_wishes"] = process_wishes(students)
        _state["locked_students"] = {}
        _state["class_names"]     = {}
        _state["dont_be_with"]    = []

        pending_count = sum(1 for v in _state["pending_wishes"].values() if v)

        return jsonify({
            "count":        len(students),
            "pendingCount": pending_count,
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

    pending_count = sum(1 for v in _state["pending_wishes"].values() if v)
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

@app.route("/api/assign", methods=["POST"])
def assign():
    from matcher import calculate_classes, calculate_stats

    if not _state["students"]:
        return jsonify({"error": "Keine Schüler geladen"}), 400

    try:
        data   = request.json or {}
        locked = data.get("lockedStudents", _state["locked_students"])

        classes = calculate_classes(
            _state["students"],
            _state["params"],
            _state["resolved_wishes"],
            _state["dont_be_with"],
            locked_students=locked,
        )

        # Standard-Klassennamen, sofern nicht manuell umbenannt
        _DEFAULT_NAMES = {"5y": "Bili-Klasse"}
        for cls in classes:
            if cls["id"] in _state["class_names"]:
                cls["name"] = _state["class_names"][cls["id"]]
            elif cls["id"] in _DEFAULT_NAMES:
                cls["name"] = _DEFAULT_NAMES[cls["id"]]

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

        # Rückwärts-Maps für Wish-Info
        sid_to_cls_id   = {}
        sid_to_cls_name = {}
        for cls in response_classes:
            for s in cls["students"]:
                sid_to_cls_id[s["id"]]   = cls["id"]
                sid_to_cls_name[s["id"]] = cls["name"]

        # Freundeswunsch-Status zu jedem Schüler hinzufügen
        for cls in response_classes:
            for s in cls["students"]:
                wish_info = []
                for fid in _state["resolved_wishes"].get(s["id"], []):
                    if fid not in sm:
                        continue
                    f_cls_id   = sid_to_cls_id.get(fid)
                    fulfilled  = (f_cls_id == cls["id"])
                    wish_info.append({
                        "friendId":    fid,
                        "friendName":  sm[fid]["displayName"],
                        "fulfilled":   fulfilled,
                        "friendClass": None if fulfilled else sid_to_cls_name.get(fid),
                    })
                s["wishInfo"] = wish_info

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
        "version":         1,
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
    _DEFAULT_NAMES = {"5y": "Bili-Klasse"}
    for cls in saved_classes:
        if cls["id"] in _state["class_names"]:
            cls["name"] = _state["class_names"][cls["id"]]
        elif cls["id"] in _DEFAULT_NAMES and cls["id"] not in _state["class_names"]:
            cls["name"] = _DEFAULT_NAMES[cls["id"]]

    # Rückwärts-Maps für Wish-Info
    sid_to_cls_id   = {}
    sid_to_cls_name = {}
    for cls in saved_classes:
        for s in cls["students"]:
            sid_to_cls_id[s["id"]]   = cls["id"]
            sid_to_cls_name[s["id"]] = cls["name"]

    # Freundeswunsch-Status neu berechnen
    for cls in saved_classes:
        for s in cls["students"]:
            wish_info = []
            for fid in _state["resolved_wishes"].get(s["id"], []):
                if fid not in sm:
                    continue
                f_cls_id  = sid_to_cls_id.get(fid)
                fulfilled = (f_cls_id == cls["id"])
                wish_info.append({
                    "friendId":    fid,
                    "friendName":  sm[fid]["displayName"],
                    "fulfilled":   fulfilled,
                    "friendClass": None if fulfilled else sid_to_cls_name.get(fid),
                })
            s["wishInfo"] = wish_info

    stats = calculate_stats(
        [{"id": c["id"], "students": [s["id"] for s in c["students"]]}
         for c in saved_classes],
        sm,
        _state["resolved_wishes"],
        _state["dont_be_with"],
    )

    _state["last_assignment"] = {"classes": saved_classes, "stats": stats}

    pending_count = sum(1 for v in _state["pending_wishes"].values() if v)

    return jsonify({
        "classes":      saved_classes,
        "stats":        stats,
        "count":        len(_state["students"]),
        "pendingCount": pending_count,
    })


# ──────────────────────────────────────────────────────────────────────────────
# Start
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="127.0.0.1", port=port, debug=False)
