"""
ClassMatcher – Algorithmus-Modul
CSV-Parsing, Fuzzy-Matching von Freundeswünschen, Klassen-Zuweisung per Simulated Annealing
"""
import csv
import difflib
import io
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict


# ──────────────────────────────────────────────────────────────────────────────
# Name-Normalisierung
# ──────────────────────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Kleinschreibung, ß→ss, Umlaute→ae/oe/ue, Akzente entfernen."""
    if not name:
        return ""
    s = name.lower().strip()
    s = s.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


# ──────────────────────────────────────────────────────────────────────────────
# CSV-Parsing
# ──────────────────────────────────────────────────────────────────────────────

def parse_csv(content: str) -> list:
    """CSV-Inhalt parsen und Liste von Schüler-Dicts zurückgeben."""
    content = content.lstrip("\ufeff")  # BOM entfernen
    reader = csv.DictReader(io.StringIO(content))
    students = []

    for row in reader:
        profil = (row.get("Profil1") or "").strip()
        if not profil or profil.upper() == "NULL":
            profil = "5z"

        vorname = (row.get("Vorname") or "").strip()
        rufname = (row.get("Rufname") or "").strip()
        name    = (row.get("Name")    or "").strip()

        display_first = rufname or vorname
        students.append({
            "id":             (row.get("ID") or "").strip(),
            "name":           name,
            "vorname":        vorname,
            "rufname":        rufname,
            "displayName":    f"{display_first} {name}".strip(),
            "geschlecht":     (row.get("Geschlecht") or "").strip().lower(),
            "profil":         profil,
            "klassenpartner": (row.get("Klassenpartner") or "").strip(),
            "vorhKlasse":     (row.get("vorhKlasse") or "").strip(),
            "abgebendeSchule":(row.get("AbgebendeSchule") or "").strip(),
            "geburtsdatum":   (row.get("Geburtstag") or "").strip(),
            "fremdsprache2":  (row.get("Fremdsprache2") or "").strip().upper(),
        })

    return students


# ──────────────────────────────────────────────────────────────────────────────
# Fuzzy-Matching der Freundeswünsche
# ──────────────────────────────────────────────────────────────────────────────

# Tokens, die keine Namen sind → überspringen
_SKIP = {
    "klasse", "frau", "herr", "schule", "unbekannt", "kein", "keine",
    "nein", "leider", "schüler", "kinder", "jungs", "madchen", "mädchen",
    "fessenbacher", "weingarten", "zell", "weierbach", "grundschule",
    "bitte", "auch", "oder", "und", "freund", "freundin",
    "falls", "moeglich", "möglichst", "egal", "irgendwen", "jemand",
    "streicherklasse", "streicher", "möglich",
}


def tokenize_wishes(text: str) -> list:
    """Freitext in einzelne Namen-Tokens aufteilen."""
    if not text:
        return []
    # Klammern-Inhalte entfernen  (z.B. "(Kinder aus Zell-Weierbach)")
    text = re.sub(r"\([^)]*\)", "", text)
    # Punkt vor Großbuchstabe = Trennzeichen
    text = re.sub(r"\.(\s+)([A-ZÜÄÖA-Z])", r",\1\2", text)
    # Weitere Trennzeichen normieren
    text = text.replace(";", ",").replace(" und ", ",").replace(" and ", ",")

    tokens = []
    for raw in text.split(","):
        t = raw.strip().strip(".")
        if len(t) < 3:
            continue
        t_norm = normalize(t)
        # Skip wenn Zahl-dominiert
        if sum(c.isdigit() for c in t) > len(t) / 2:
            continue
        # Skip-Wörter
        words = set(t_norm.split())
        if words & _SKIP:
            continue
        tokens.append(t)

    return tokens


def _candidate_strings(student: dict) -> list:
    """Alle sinnvollen Namens-Varianten eines Schülers."""
    parts = [
        f"{student['vorname']} {student['name']}",
        f"{student['rufname']} {student['name']}" if student["rufname"] else "",
        student["name"],
        student["vorname"],
        student["rufname"],
        f"{student['name']} {student['vorname']}",
    ]
    return [p for p in parts if p.strip()]


def match_name(token: str, students: list) -> list:
    """Token gegen Schülerliste matchen.
    Gibt [(student, score), …] absteigend nach Score zurück."""
    tok_norm  = normalize(token)
    tok_words = tok_norm.split()

    results = []
    for s in students:
        best = 0.0
        for candidate in _candidate_strings(s):
            cand_norm  = normalize(candidate)
            cand_words = cand_norm.split()

            # Gesamt-Ähnlichkeit
            score = difflib.SequenceMatcher(None, tok_norm, cand_norm).ratio()
            best  = max(best, score)

            # Wort-für-Wort-Vergleich
            for tw in tok_words:
                if len(tw) < 2:
                    continue
                for cw in cand_words:
                    ws = difflib.SequenceMatcher(None, tw, cw).ratio()
                    if ws >= 0.82:
                        best = max(best, 0.55 + ws * 0.35)

        if best > 0.30:
            results.append((s, round(best, 3)))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:5]


AUTO_THRESHOLD    = 0.75   # automatisch zuordnen
SUGGEST_THRESHOLD = 0.45   # als Kandidat vorschlagen


def process_wishes(students: list) -> tuple:
    """Alle Freundeswünsche verarbeiten.

    Rückgabe:
        resolved: {student_id: [matched_student_ids]}   – automatisch erkannt
        pending:  {student_id: [{token, candidates}]}   – manuell klären
    """
    resolved: dict = {}
    pending:  dict = {}

    for student in students:
        sid   = student["id"]
        tokens = tokenize_wishes(student["klassenpartner"])
        others = [s for s in students if s["id"] != sid]

        resolved[sid] = []
        pending[sid]  = []

        for token in tokens:
            matches = match_name(token, others)

            if not matches:
                pending[sid].append({"token": token, "candidates": []})

            elif matches[0][1] >= AUTO_THRESHOLD:
                # Eindeutig – direkt übernehmen
                mid = matches[0][0]["id"]
                if mid not in resolved[sid]:
                    resolved[sid].append(mid)

            else:
                # Ambig – zur manuellen Klärung
                good = [(s, sc) for s, sc in matches if sc >= SUGGEST_THRESHOLD]
                pending[sid].append({
                    "token": token,
                    "candidates": [
                        {"id": s["id"], "name": s["displayName"], "score": sc}
                        for s, sc in good[:3]
                    ],
                })

    return resolved, pending


# ──────────────────────────────────────────────────────────────────────────────
# Bewertungsfunktion
# ──────────────────────────────────────────────────────────────────────────────

def score_assignment(
    assignment:      dict,   # {class_id: [student_id, …]}
    resolved_wishes: dict,
    dont_be_with:    list,
    w_friend:        float,
    w_gender:        float,
    student_map:     dict,
) -> float:
    sc = 0.0

    # Rückwärts-Map: student_id → class_id
    sid2cls: dict = {}
    for cid, sids in assignment.items():
        for sid in sids:
            sid2cls[sid] = cid

    # Freundeswünsche erfüllt
    if w_friend > 0:
        for sid, friends in resolved_wishes.items():
            if sid not in sid2cls:
                continue
            for fid in friends:
                if sid2cls.get(fid) == sid2cls[sid]:
                    sc += w_friend

    # "Nicht zusammen"-Verstöße (harte Strafe)
    for pair in dont_be_with:
        a, b = pair.get("a"), pair.get("b")
        if a and b and sid2cls.get(a) and sid2cls.get(a) == sid2cls.get(b):
            sc -= 10_000

    # Geschlechterbalance
    if w_gender > 0:
        for cid, sids in assignment.items():
            cls_students = [student_map[s] for s in sids if s in student_map]
            boys  = sum(1 for s in cls_students if s["geschlecht"] == "m")
            girls = sum(1 for s in cls_students if s["geschlecht"] == "w")
            total = boys + girls
            if total:
                balance = 1.0 - abs(boys - girls) / total
                sc += w_gender * balance * 10

    return sc


# ──────────────────────────────────────────────────────────────────────────────
# Simulated-Annealing-Optimierung
# ──────────────────────────────────────────────────────────────────────────────

def _interleave_genders(students: list) -> list:
    """Schüler:innen gender-abwechselnd sortieren für eine ausgeglichene Startbelegung."""
    boys  = [s for s in students if s["geschlecht"] == "m"]
    girls = [s for s in students if s["geschlecht"] == "w"]
    rest  = [s for s in students if s["geschlecht"] not in ("m", "w")]
    random.shuffle(boys); random.shuffle(girls); random.shuffle(rest)
    merged = []
    while boys or girls:
        if boys:  merged.append(boys.pop())
        if girls: merged.append(girls.pop())
    merged.extend(rest)
    return merged


def optimize_mixed_assignment(
    fill_students:    list,   # Schüler, die auf alle Klassen verteilt werden (5z)
    class_ids:        list,   # alle Klassen-IDs
    fixed:            dict,   # {class_id: [student_ids]} – fest zugeordnete Schüler (5x, 5y)
    capacities:       dict,   # {class_id: max_additional} – noch verfügbare Plätze pro Klasse
    locked:           dict,   # {student_id: class_id} – manuell gesperrte fill-Schüler
    resolved_wishes:  dict,
    dont_be_with:     list,
    w_friend:         float,
    w_gender:         float,
    student_map:      dict,
    latin_free_class: str | None = None,  # diese Klasse bekommt nie Latein-Schüler
) -> dict:
    """Simulated Annealing für gemischte Klassen.

    Nur fill_students (Normalzug) werden verschoben.
    fixed-Schüler (Musik-/Bili-Zug) bleiben in ihrer Klasse.
    Wenn latin_free_class gesetzt ist, kommen dort nie Latein-Schüler hin.
    """
    if not fill_students:
        return {cid: [] for cid in class_ids}

    locked_ids = set(locked.keys())
    free       = [s for s in fill_students if s["id"] not in locked_ids]

    # Latein-Status für schnellen Lookup
    is_latin = {s["id"]: s.get("fremdsprache2") == "L" for s in fill_students}

    # ── Startbelegung ────────────────────────────────────────────
    z_asgn: dict = {cid: [] for cid in class_ids}
    rem_cap = dict(capacities)

    # 1) Gesperrte fill-Schüler zuerst einsetzen
    for sid, cid in locked.items():
        if cid in z_asgn and rem_cap.get(cid, 0) > 0:
            z_asgn[cid].append(sid)
            rem_cap[cid] -= 1

    # 2) Freie fill-Schüler: Latein-Schüler nie in latin_free_class
    interleaved = _interleave_genders(free)

    if latin_free_class:
        non_lf_ids  = [c for c in class_ids if c != latin_free_class]
        latin_free  = [s for s in interleaved if is_latin[s["id"]]]
        non_latin   = [s for s in interleaved if not is_latin[s["id"]]]

        def _place(students, allowed):
            cap_order = sorted(allowed, key=lambda c: -rem_cap.get(c, 0))
            idx = 0
            rounds = 0
            while idx < len(students):
                placed = False
                for cid in cap_order:
                    if rem_cap.get(cid, 0) > 0 and idx < len(students):
                        z_asgn[cid].append(students[idx]["id"])
                        rem_cap[cid] -= 1
                        idx += 1
                        placed = True
                if not placed:
                    break
                rounds += 1
                if rounds > len(students) + len(allowed) + 1:
                    break

        _place(latin_free, non_lf_ids)   # Latein: nur nicht-lateinfreie Klassen
        _place(non_latin,  class_ids)    # Rest: alle Klassen
    else:
        cap_order = sorted(class_ids, key=lambda c: -rem_cap.get(c, 0))
        s_idx = 0
        rounds = 0
        while s_idx < len(interleaved):
            placed = False
            for cid in cap_order:
                if rem_cap.get(cid, 0) > 0 and s_idx < len(interleaved):
                    z_asgn[cid].append(interleaved[s_idx]["id"])
                    rem_cap[cid] -= 1
                    s_idx += 1
                    placed = True
            if not placed:
                break
            rounds += 1
            if rounds > len(interleaved) + len(class_ids):
                break

    # ── Scoring-Funktion ─────────────────────────────────────────
    def full(z):
        return {cid: fixed.get(cid, []) + z[cid] for cid in class_ids}

    def score(z):
        return score_assignment(full(z), resolved_wishes, dont_be_with,
                                w_friend, w_gender, student_map)

    cur_score  = score(z_asgn)
    best_asgn  = {k: list(v) for k, v in z_asgn.items()}
    best_score = cur_score

    if len(class_ids) < 2 or not free:
        return best_asgn

    # ── Simulated Annealing ──────────────────────────────────────
    free_ids   = {s["id"] for s in free}
    iterations = max(5_000, len(free) * 70)
    T          = 60.0
    T_min      = 0.05
    cool       = (T_min / T) ** (1.0 / iterations)

    for _ in range(iterations):
        c1, c2 = random.sample(class_ids, 2)
        pool1  = [i for i, sid in enumerate(z_asgn[c1]) if sid in free_ids]
        pool2  = [i for i, sid in enumerate(z_asgn[c2]) if sid in free_ids]
        if not pool1 or not pool2:
            T = max(T_min, T * cool)
            continue

        i1, i2 = random.choice(pool1), random.choice(pool2)

        # Latein-Constraint: kein Latein-Schüler in latin_free_class
        if latin_free_class:
            sid1, sid2 = z_asgn[c1][i1], z_asgn[c2][i2]
            if (is_latin.get(sid1) and c2 == latin_free_class) or \
               (is_latin.get(sid2) and c1 == latin_free_class):
                T = max(T_min, T * cool)
                continue

        z_asgn[c1][i1], z_asgn[c2][i2] = z_asgn[c2][i2], z_asgn[c1][i1]

        new_score = score(z_asgn)
        delta     = new_score - cur_score

        if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
            cur_score = new_score
            if cur_score > best_score:
                best_score = cur_score
                best_asgn  = {k: list(v) for k, v in z_asgn.items()}
        else:
            z_asgn[c1][i1], z_asgn[c2][i2] = z_asgn[c2][i2], z_asgn[c1][i1]

        T = max(T_min, T * cool)

    return best_asgn


# ──────────────────────────────────────────────────────────────────────────────
# Haupt-Einstiegspunkt: Klassen berechnen
# ──────────────────────────────────────────────────────────────────────────────

# Welcher Zug füllt die anderen Klassen auf?
FILL_TRACK = "5z"


def calculate_classes(
    students:        list,
    params:          dict,
    resolved_wishes: dict,
    dont_be_with:    list,
    locked_students: dict = None,
) -> list:
    """Klassen berechnen.

    5x- und 5y-Schüler sind fix in ihrer jeweiligen Klasse.
    5z-Schüler werden auf alle Klassen verteilt, sodass 5x/5y auf
    Zielgröße aufgefüllt werden. locked_students bleibt erhalten.
    """
    max_size = params.get("maxClassSize",           30)
    w_friend = params.get("weightFriendWish",        5)
    w_gender = params.get("weightGenderBalance",     3)
    locked   = locked_students or {}

    by_profil: dict = defaultdict(list)
    for s in students:
        by_profil[s["profil"]].append(s)

    student_map = {s["id"]: s for s in students}
    total = len(students)

    # Sonder-Züge (je eine Klasse) und Füll-Zug (5z)
    special_tracks = sorted(t for t in by_profil if t != FILL_TRACK)
    fill_students  = by_profil.get(FILL_TRACK, [])

    num_special    = len(special_tracks)
    num_total      = max(num_special + (1 if fill_students else 0),
                         math.ceil(total / max_size))
    num_fill_cls   = max(1, num_total - num_special)

    # Klassen-IDs
    fill_cls_ids = (
        [FILL_TRACK] if num_fill_cls == 1
        else [f"{FILL_TRACK}-{i+1}" for i in range(num_fill_cls)]
    )
    class_ids = special_tracks + fill_cls_ids

    # Fixe Schüler pro Klasse (5x, 5y bleiben in ihrer Klasse)
    fixed: dict = {t: [s["id"] for s in by_profil[t]] for t in special_tracks}
    for cid in fill_cls_ids:
        fixed[cid] = []

    # Verfügbare Plätze pro Klasse für fill-Schüler
    capacities = {cid: max_size - len(fixed[cid]) for cid in class_ids}

    # Gesperrte fill-Schüler (Drag & Drop)
    fill_ids    = {s["id"] for s in fill_students}
    locked_fill = {
        sid: cid for sid, cid in locked.items()
        if sid in fill_ids and cid in class_ids
    }

    # Immer eine lateinfreie Normalzug-Klasse (letzte fill-Klasse).
    # Manuelle Locks (Drag & Drop) werden auch für Latein-Schüler respektiert.
    latin_free_class = fill_cls_ids[-1] if len(fill_cls_ids) >= 2 else None

    z_asgn = optimize_mixed_assignment(
        fill_students, class_ids, fixed, capacities, locked_fill,
        resolved_wishes, dont_be_with,
        w_friend, w_gender,
        student_map,
        latin_free_class=latin_free_class,
    )

    def _track_of(cid):
        return cid.rsplit("-", 1)[0] if "-" in cid else cid

    return [
        {
            "id":       cid,
            "name":     cid,
            "track":    _track_of(cid),
            "students": fixed[cid] + z_asgn.get(cid, []),
        }
        for cid in class_ids
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Statistiken
# ──────────────────────────────────────────────────────────────────────────────

def calculate_stats(
    classes:         list,   # [{id, students: [sid, …]}, …]
    student_map:     dict,
    resolved_wishes: dict,
    dont_be_with:    list,
) -> list:
    sid2cls: dict = {}
    for cls in classes:
        for sid in cls["students"]:
            sid2cls[sid] = cls["id"]

    stats = []
    for cls in classes:
        cls_students = [student_map[sid] for sid in cls["students"] if sid in student_map]
        boys  = sum(1 for s in cls_students if s["geschlecht"] == "m")
        girls = sum(1 for s in cls_students if s["geschlecht"] == "w")

        fulfilled = 0
        total_wishes = 0
        for s in cls_students:
            for fid in resolved_wishes.get(s["id"], []):
                total_wishes += 1
                if sid2cls.get(fid) == cls["id"]:
                    fulfilled += 1

        violations = sum(
            1 for pair in dont_be_with
            if (pair.get("a") and pair.get("b") and
                sid2cls.get(pair["a"]) == cls["id"] and
                sid2cls.get(pair["b"]) == cls["id"])
        )

        stats.append({
            "classId":          cls["id"],
            "total":            len(cls["students"]),
            "boys":             boys,
            "girls":            girls,
            "fulfilled_wishes": fulfilled,
            "total_wishes":     total_wishes,
            "violations":       violations,
        })

    return stats
