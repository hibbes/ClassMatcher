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
    w_music_split:   float = 0.0,   # 0..100 – Gewicht: Musikzug auf 2 Klassen
    music_ids:       set | None = None,
    bili_class:      str | None = None,
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

    # Musikzug-Verteilung: Bili-Klasse hart ausgeschlossen,
    # Top-2 Nicht-Bili-Klassen sollen alle Musik-SuS möglichst gleich tragen.
    if music_ids:
        music_per_class = Counter(
            sid2cls[sid] for sid in music_ids if sid in sid2cls
        )
        if bili_class and music_per_class.get(bili_class, 0) > 0:
            sc -= 50_000 * music_per_class[bili_class]

        if w_music_split > 0:
            eligible = sorted(
                (music_per_class.get(c, 0) for c in assignment if c != bili_class),
                reverse=True,
            )
            if len(eligible) >= 2:
                top1, top2  = eligible[0], eligible[1]
                spillover   = sum(eligible[2:])
                imbalance   = abs(top1 - top2)
                penalty     = imbalance + 3 * spillover
                # Quadratisch skaliert: 25%/50%/75%/100% = 6.25/25/56.25/100
                sc -= (w_music_split * w_music_split / 100.0) * penalty

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
    fill_students:    list,   # Schüler, die auf Klassen verteilt werden (Normal + Musikzug)
    class_ids:        list,   # alle Klassen-IDs
    fixed:            dict,   # {class_id: [student_ids]} – fest zugeordnete Schüler (5y/Bili)
    capacities:       dict,   # {class_id: max_additional} – noch verfügbare Plätze pro Klasse
    locked:           dict,   # {student_id: class_id} – manuell gesperrte fill-Schüler
    resolved_wishes:  dict,
    dont_be_with:     list,
    w_friend:         float,
    w_gender:         float,
    student_map:      dict,
    latin_free_class: str | None = None,  # diese Klasse bekommt nie Latein-Schüler
    bili_class:       str | None = None,  # diese Klasse bekommt nie Musikzug-Schüler
    music_ids:        set | None = None,  # Schüler-IDs des Musikzugs
    w_music_split:    float = 0.0,        # Gewicht: Musikzug gleichmäßig auf 2 Klassen
) -> dict:
    """Simulated Annealing für gemischte Klassen.

    fill_students werden frei verschoben; fixed-Schüler (Bili) bleiben.
    Hard-Constraints: Latein-Schüler nie in latin_free_class,
    Musikzug-Schüler nie in bili_class.
    Soft-Constraint (gewichtet): Musikzug auf genau 2 Nicht-Bili-Klassen.
    """
    if not fill_students:
        return {cid: [] for cid in class_ids}

    music_ids  = music_ids or set()
    locked_ids = set(locked.keys())
    free       = [s for s in fill_students if s["id"] not in locked_ids]

    # Latein-Status für schnellen Lookup
    is_latin = {s["id"]: s.get("fremdsprache2") == "L" for s in fill_students}

    def forbidden_for(sid: str) -> set:
        f = set()
        if latin_free_class and is_latin.get(sid):
            f.add(latin_free_class)
        if bili_class and sid in music_ids:
            f.add(bili_class)
        return f

    # ── Startbelegung ────────────────────────────────────────────
    z_asgn: dict = {cid: [] for cid in class_ids}
    rem_cap = dict(capacities)

    # 1) Gesperrte fill-Schüler zuerst einsetzen
    for sid, cid in locked.items():
        if cid in z_asgn and rem_cap.get(cid, 0) > 0:
            z_asgn[cid].append(sid)
            rem_cap[cid] -= 1

    # 2) Freie fill-Schüler in absteigender Constraint-Reihenfolge platzieren
    interleaved = _interleave_genders(free)

    music_latin = [s for s in interleaved if s["id"] in music_ids and is_latin[s["id"]]]
    music_only  = [s for s in interleaved if s["id"] in music_ids and not is_latin[s["id"]]]
    latin_only  = [s for s in interleaved if s["id"] not in music_ids and is_latin[s["id"]]]
    rest        = [s for s in interleaved if s["id"] not in music_ids and not is_latin[s["id"]]]

    def _place(students, allowed):
        if not students or not allowed:
            return
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

    non_bili = [c for c in class_ids if c != bili_class]
    non_lf   = [c for c in class_ids if c != latin_free_class]
    non_both = [c for c in non_bili if c != latin_free_class]

    # Vorzugs-Targets für Musikzug: bei aktivem Slider die 2 kapazitätsstärksten
    # Nicht-Bili-Klassen (bei kombinierten Constraints zusätzlich nicht latin_free).
    if w_music_split > 0:
        candidates = non_both if non_both else non_bili
        music_targets = sorted(candidates, key=lambda c: -rem_cap.get(c, 0))[:2]
        if not music_targets:
            music_targets = non_bili
        ml_targets = [c for c in music_targets if c != latin_free_class] or music_targets
    else:
        music_targets = non_bili
        ml_targets    = non_both or non_bili

    _place(music_latin, ml_targets)         # Musik + Latein: Bili AUS, lateinfrei AUS
    _place(music_only,  music_targets)      # Musik: nur Bili AUS
    _place(latin_only,  non_lf)             # Latein: nur lateinfrei AUS
    _place(rest,        class_ids)          # Rest: alle Klassen

    # ── Scoring-Funktion ─────────────────────────────────────────
    def full(z):
        return {cid: fixed.get(cid, []) + z[cid] for cid in class_ids}

    def score(z):
        return score_assignment(
            full(z), resolved_wishes, dont_be_with,
            w_friend, w_gender, student_map,
            w_music_split=w_music_split,
            music_ids=music_ids,
            bili_class=bili_class,
        )

    cur_score  = score(z_asgn)
    best_asgn  = {k: list(v) for k, v in z_asgn.items()}
    best_score = cur_score

    if len(class_ids) < 2 or not free:
        return best_asgn

    # ── Simulated Annealing ──────────────────────────────────────
    # 25 % der Schritte: 3er-Rotation statt 2er-Swap (knackt lokale Optima).
    free_ids   = {s["id"] for s in free}
    iterations = max(5_000, len(free) * 70)
    T          = 60.0
    T_min      = 0.05
    cool       = (T_min / T) ** (1.0 / iterations)
    n_cls      = len(class_ids)

    for _ in range(iterations):
        use_rotate = (n_cls >= 3 and random.random() < 0.25)

        if use_rotate:
            c1, c2, c3 = random.sample(class_ids, 3)
            p1 = [i for i, sid in enumerate(z_asgn[c1]) if sid in free_ids]
            p2 = [i for i, sid in enumerate(z_asgn[c2]) if sid in free_ids]
            p3 = [i for i, sid in enumerate(z_asgn[c3]) if sid in free_ids]
            if not (p1 and p2 and p3):
                T = max(T_min, T * cool)
                continue
            i1, i2, i3 = random.choice(p1), random.choice(p2), random.choice(p3)
            sid1, sid2, sid3 = z_asgn[c1][i1], z_asgn[c2][i2], z_asgn[c3][i3]
            # Rotation: sid1→c2, sid2→c3, sid3→c1
            if (c2 in forbidden_for(sid1)
                or c3 in forbidden_for(sid2)
                or c1 in forbidden_for(sid3)):
                T = max(T_min, T * cool)
                continue
            z_asgn[c1][i1] = sid3
            z_asgn[c2][i2] = sid1
            z_asgn[c3][i3] = sid2
            new_score = score(z_asgn)
            delta     = new_score - cur_score
            if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
                cur_score = new_score
                if cur_score > best_score:
                    best_score = cur_score
                    best_asgn  = {k: list(v) for k, v in z_asgn.items()}
            else:
                z_asgn[c1][i1], z_asgn[c2][i2], z_asgn[c3][i3] = sid1, sid2, sid3
        else:
            c1, c2 = random.sample(class_ids, 2)
            pool1  = [i for i, sid in enumerate(z_asgn[c1]) if sid in free_ids]
            pool2  = [i for i, sid in enumerate(z_asgn[c2]) if sid in free_ids]
            if not pool1 or not pool2:
                T = max(T_min, T * cool)
                continue

            i1, i2 = random.choice(pool1), random.choice(pool2)
            sid1, sid2 = z_asgn[c1][i1], z_asgn[c2][i2]

            if c2 in forbidden_for(sid1) or c1 in forbidden_for(sid2):
                T = max(T_min, T * cool)
                continue

            z_asgn[c1][i1], z_asgn[c2][i2] = sid2, sid1

            new_score = score(z_asgn)
            delta     = new_score - cur_score

            if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
                cur_score = new_score
                if cur_score > best_score:
                    best_score = cur_score
                    best_asgn  = {k: list(v) for k, v in z_asgn.items()}
            else:
                z_asgn[c1][i1], z_asgn[c2][i2] = sid1, sid2

        T = max(T_min, T * cool)

    return best_asgn


# ──────────────────────────────────────────────────────────────────────────────
# Haupt-Einstiegspunkt: Klassen berechnen
# ──────────────────────────────────────────────────────────────────────────────

# Profil-IDs aus der CSV
MUSIC_TRACK = "5x"   # Musikzug – Schüler-Profil (keine eigene Klasse mehr)
BILI_TRACK  = "5y"   # Bili – eigene Klasse, keine Musikzug-Schüler
FILL_TRACK  = "5z"   # Normalzug – verteilt auf alle Nicht-Bili-Klassen


def calculate_classes(
    students:        list,
    params:          dict,
    resolved_wishes: dict,
    dont_be_with:    list,
    locked_students: dict = None,
) -> list:
    """Klassen berechnen.

    Bili-Schüler (Profil 5y) bleiben fix in der Bili-Klasse.
    Musikzug-Schüler (Profil 5x) werden – je nach weightMusicSplit – auf
    möglichst genau zwei Nicht-Bili-Klassen gleichmäßig verteilt.
    Normalzug-Schüler (Profil 5z) füllen alle Klassen auf.
    """
    max_size      = params.get("maxClassSize",       30)
    w_friend      = params.get("weightFriendWish",    5)
    w_gender      = params.get("weightGenderBalance", 3)
    w_music_split = params.get("weightMusicSplit",    50)
    locked        = locked_students or {}

    by_profil: dict = defaultdict(list)
    for s in students:
        by_profil[s["profil"]].append(s)

    student_map = {s["id"]: s for s in students}
    total = len(students)

    bili_students  = by_profil.get(BILI_TRACK, [])
    music_students = by_profil.get(MUSIC_TRACK, [])
    normal_students = by_profil.get(FILL_TRACK, [])
    fill_students  = music_students + normal_students
    music_ids      = {s["id"] for s in music_students}

    # Anzahl Klassen: Bili + N Füll-Klassen, sodass Gesamtkapazität reicht
    num_special  = 1 if bili_students else 0
    num_total    = max(num_special + (1 if fill_students else 0),
                       math.ceil(total / max_size))
    num_fill_cls = max(1, num_total - num_special)

    fill_cls_ids = (
        [FILL_TRACK] if num_fill_cls == 1
        else [f"{FILL_TRACK}-{i+1}" for i in range(num_fill_cls)]
    )

    # Bili an Position 2 (Index 1), wenn überhaupt Bili-SuS vorhanden
    if bili_students and fill_cls_ids:
        class_ids = [fill_cls_ids[0], BILI_TRACK] + fill_cls_ids[1:]
    elif bili_students:
        class_ids = [BILI_TRACK]
    else:
        class_ids = list(fill_cls_ids)

    # Fixe Schüler pro Klasse (nur Bili)
    fixed: dict = {cid: [] for cid in class_ids}
    if bili_students:
        fixed[BILI_TRACK] = [s["id"] for s in bili_students]

    bili_class = BILI_TRACK if bili_students else None

    # Verfügbare Plätze pro Klasse für fill-Schüler
    capacities = {cid: max_size - len(fixed[cid]) for cid in class_ids}

    # Gesperrte fill-Schüler (Drag & Drop)
    fill_ids    = {s["id"] for s in fill_students}
    locked_fill = {
        sid: cid for sid, cid in locked.items()
        if sid in fill_ids and cid in class_ids
    }

    # Eine lateinfreie Klasse: bevorzugt die letzte Fill-Klasse, die kein
    # Music-Target ist (also nicht zu den ersten 2 Nicht-Bili-Klassen gehört).
    if len(fill_cls_ids) >= 2:
        latin_free_class = fill_cls_ids[-1]
    else:
        latin_free_class = None

    z_asgn = optimize_mixed_assignment(
        fill_students, class_ids, fixed, capacities, locked_fill,
        resolved_wishes, dont_be_with,
        w_friend, w_gender,
        student_map,
        latin_free_class=latin_free_class,
        bili_class=bili_class,
        music_ids=music_ids,
        w_music_split=w_music_split,
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
# Wunsch-Trennungsgrund (für nicht erfüllte Freundeswünsche)
# ──────────────────────────────────────────────────────────────────────────────

def wish_reason(
    student:          dict,
    friend:           dict,
    student_class:    str,
    friend_class:     str,
    latin_free_class: str | None,
    resolved_wishes:  dict,
) -> str | None:
    """Strukturellen Grund für getrennte Klassen bestimmen, oder None
    wenn es 'nur' Optimierungs-Tradeoff war."""
    s_pro, f_pro = student.get("profil"), friend.get("profil")

    # Bili-Trennung: einer ist Bili-Profil, der andere nicht
    if BILI_TRACK in (s_pro, f_pro) and s_pro != f_pro:
        return "Bili-Klasse"

    # Latein-Trennung: einer Latein in lateinfreier Klasse, anderer nicht
    if latin_free_class:
        s_lat = student.get("fremdsprache2") == "L"
        f_lat = friend.get("fremdsprache2") == "L"
        if s_lat != f_lat:
            if (s_lat and friend_class == latin_free_class) or \
               (f_lat and student_class  == latin_free_class):
                return "Latein"

    # Einseitig: Freund hat den Schüler nicht (auch) als Wunsch eingetragen
    if student["id"] not in resolved_wishes.get(friend["id"], []):
        return "einseitiger Wunsch"

    return None


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


# ══════════════════════════════════════════════════════════════════════════════
# ════════════════════════ MODUS „KLASSE 8 NEU MISCHEN" ═══════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#
# Eingabe: CSV der Profilwahl in Klasse 7. Spalten (;-separiert, UTF-8 mit BOM):
#   Nachname; Vorname; Klasse/Information (z.B. 7a); Ich bin … (männlich/weiblich);
#   Ich bin im Bili - Zug (Ja/Nein);
#   Ich habe Latein als Zweitsprache (Ja/Nein);
#   Ich habe vor, das Schiller nach der 7. Klasse zu verlassen. (Ja/Nein);
#   Ich wähle folgendes Profil ab der 8. Klasse. (NWT/Spanisch/IMP/Musik);
#   Ich möchte bitte mit folgenden Freunden in eine Klasse kommen.;
#   Ich hätte IMP gewählt. (Ja/Nein)
#
# Constraints:
#   – Verlasser und Nicht-Wähler werden ignoriert
#   – Musik-Profilianten und Bili-SuS dürfen NIE gemeinsam in einer Klasse sein
#   – Bili-SuS in maximal 2 Klassen
#   – Latein-SuS in maximal 2 Klassen
#   – Klassengröße zwischen minClassSize und maxClassSize
#   – Profile (NWT/Spanisch/IMP) möglichst zusammenhalten (Soft, einstellbar)
#   – Freundeswünsche, m/w-Balance, Nicht-zusammen-Paare wie in Modus 5

PROFIL_MUSIK   = "Musik"
PROFIL_NWT     = "Naturwissenschaft und Technik (NWT)"
PROFIL_SPANISCH = "Spanisch"
PROFIL_IMP     = "IMP"


def _ja(value: str) -> bool:
    return (value or "").strip().lower() == "ja"


def parse_csv_klasse8(content: str) -> list:
    """CSV aus dem Profilwahl-Formular parsen.

    Liefert eine Liste von Schüler-Dicts mit den Feldern, die der
    Klasse-8-Algorithmus braucht. Verlasser und Nicht-Wähler werden
    übersprungen (gehen nicht in die Liste).
    """
    content = content.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(content), delimiter=";")

    bili_col     = "Ich bin im Bili - Zug"
    latein_col   = "Ich habe Latein als Zweitsprache"
    leave_col    = "Ich habe vor, das Schiller nach der 7. Klasse zu verlassen."
    profile_col  = "Ich wähle folgendes Profil ab der 8. Klasse."
    friends_col  = "Ich möchte bitte mit folgenden Freunden in eine Klasse kommen."
    klasse_col   = "Klasse/Information"
    gender_col   = "Ich bin ..."

    students = []
    seen_ids: set = set()

    for row in reader:
        name    = (row.get("Nachname") or "").strip()
        vorname = (row.get("Vorname")  or "").strip()
        if not name or not vorname:
            continue

        profil = (row.get(profile_col) or "").strip()
        if _ja(row.get(leave_col)):
            continue
        if not profil:
            continue

        gender_raw = (row.get(gender_col) or "").strip().lower()
        if gender_raw.startswith("m"):
            geschlecht = "m"
        elif gender_raw.startswith("w"):
            geschlecht = "w"
        else:
            geschlecht = ""

        # ID: Nachname-Vorname-AlteKlasse normalisiert; Kollisionen mit Index
        klasse_alt = (row.get(klasse_col) or "").strip()
        base_id = f"{normalize(name)}-{normalize(vorname)}-{klasse_alt.lower()}"
        sid = base_id
        idx = 2
        while sid in seen_ids:
            sid = f"{base_id}-{idx}"
            idx += 1
        seen_ids.add(sid)

        students.append({
            "id":             sid,
            "name":           name,
            "vorname":        vorname,
            "rufname":        "",
            "displayName":    f"{vorname} {name}",
            "geschlecht":     geschlecht,
            "profil":         profil,
            "klassenpartner": (row.get(friends_col) or "").strip(),
            "vorhKlasse":     klasse_alt,
            "abgebendeSchule":"",
            "geburtsdatum":   "",
            "fremdsprache2":  "L" if _ja(row.get(latein_col)) else "F",
            "bili":           _ja(row.get(bili_col)),
            "latein":         _ja(row.get(latein_col)),
            "imp_alternativ": _ja(row.get("Ich hätte IMP gewählt.")),
        })

    return students


# ──────────────────────────────────────────────────────────────────────────────
# Klasse 8 – Bewertungsfunktion
# ──────────────────────────────────────────────────────────────────────────────

def score_klasse8(
    assignment:       dict,
    resolved_wishes:  dict,
    dont_be_with:     list,
    w_friend:         float,
    w_gender:         float,
    w_profile:        float,
    student_map:      dict,
) -> float:
    """Score: Freundeswünsche + Gender-Balance + Profile-Cluster + Nicht-Zusammen.

    Hard-Constraints (Musik nur in Musik-Klasse, Bili nur in Bili-Klassen,
    Latein nur in Latein-Klassen) werden außerhalb in der SA-Schleife
    enforced (forbidden_for).
    """
    sc = 0.0

    sid2cls: dict = {}
    for cid, sids in assignment.items():
        for sid in sids:
            sid2cls[sid] = cid

    # Freundeswünsche
    if w_friend > 0:
        for sid, friends in resolved_wishes.items():
            if sid not in sid2cls:
                continue
            for fid in friends:
                if sid2cls.get(fid) == sid2cls[sid]:
                    sc += w_friend

    # "Nicht zusammen"-Verstöße
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

    # Profile zusammenhalten: pro Profil zählen wir, in wie vielen Klassen
    # SuS dieses Profils landen; je weniger Klassen → besser. Bonus pro
    # Klasse, in der mind. die Hälfte des Profils landet.
    if w_profile > 0:
        profile_counter: dict = defaultdict(lambda: Counter())
        for sid, cid in sid2cls.items():
            s = student_map.get(sid)
            if s is None:
                continue
            p = s.get("profil") or ""
            if p in (PROFIL_NWT, PROFIL_SPANISCH, PROFIL_IMP):
                profile_counter[p][cid] += 1

        for p, counts in profile_counter.items():
            total_p = sum(counts.values())
            if total_p == 0:
                continue
            # Konzentration: Anteil größter Cluster
            max_cluster = max(counts.values())
            concentration = max_cluster / total_p     # 0..1
            # Spread-Penalty: viele kleine Cluster sind teuer
            spread = len(counts)
            sc += (w_profile * w_profile / 100.0) * (concentration * 10 - spread)

    return sc


# ──────────────────────────────────────────────────────────────────────────────
# Klasse 8 – Simulated Annealing
# ──────────────────────────────────────────────────────────────────────────────

def optimize_klasse8_assignment(
    students:         list,
    class_ids:        list,
    capacities:       dict,
    locked:           dict,
    resolved_wishes:  dict,
    dont_be_with:     list,
    w_friend:         float,
    w_gender:         float,
    w_profile:        float,
    student_map:      dict,
    bili_classes:     list,
    latein_classes:   list,
    musik_class:      str | None,
    bili_ids:         set,
    latein_ids:       set,
    musik_ids:        set,
    latein_mode:      str = "strict",
) -> dict:
    """SA-Verteilung für Klasse 8.

    Hard-Constraints:
      – Bili-SuS nur in bili_classes
      – Latein-SuS nur in latein_classes
      – Musik-SuS nur in musik_class
    """
    if not students:
        return {cid: [] for cid in class_ids}

    locked_ids = set(locked.keys())
    free       = [s for s in students if s["id"] not in locked_ids]
    free_ids   = {s["id"] for s in free}

    def forbidden_for(sid: str) -> set:
        f: set = set()
        is_bili   = sid in bili_ids
        is_musik  = sid in musik_ids
        is_latein = sid in latein_ids
        # Bili dominiert über Musik bei Doppel-Wahl (in Praxis 0 Fälle).
        if is_bili and bili_classes:
            for c in class_ids:
                if c not in bili_classes:
                    f.add(c)
        elif is_musik and musik_class:
            for c in class_ids:
                if c != musik_class:
                    f.add(c)
        # Latein-Constraint:
        #   strict          – hart für alle Latein-SuS (inkl. Musik-Latein)
        #   musik_exception – Musik-Latein-SuS bleiben in Musik-Klasse,
        #                     auch wenn diese formal nicht Latein-Klasse ist.
        if is_latein and latein_classes:
            relax = (latein_mode == "musik_exception" and is_musik)
            if not relax:
                for c in class_ids:
                    if c not in latein_classes:
                        f.add(c)
        return f

    # ── Startbelegung ────────────────────────────────────────────
    asgn: dict = {cid: [] for cid in class_ids}
    rem_cap   = dict(capacities)

    # 1) Locked zuerst
    for sid, cid in locked.items():
        if cid in asgn and rem_cap.get(cid, 0) > 0:
            asgn[cid].append(sid)
            rem_cap[cid] -= 1

    # 2) Disjunkte Buckets in Reihenfolge mit absteigender Constraint-Strenge:
    #    Musik > Bili+Latein > Bili-only > Latein-only > Rest.
    #    Bili dominiert bei Konflikt (Bili+Musik landet im Bili-Bucket).
    music_grp   = [s for s in free
                   if s["id"] in musik_ids and s["id"] not in bili_ids]
    bili_lat    = [s for s in free
                   if s["id"] in bili_ids and s["id"] in latein_ids]
    bili_only   = [s for s in free
                   if s["id"] in bili_ids and s["id"] not in latein_ids]
    latein_only = [s for s in free
                   if s["id"] in latein_ids
                   and s["id"] not in bili_ids
                   and s["id"] not in musik_ids]
    rest        = [s for s in free
                   if s["id"] not in musik_ids
                   and s["id"] not in bili_ids
                   and s["id"] not in latein_ids]

    for grp in (music_grp, bili_lat, bili_only, latein_only, rest):
        random.shuffle(grp)

    # Profile-aware Reihenfolge im "rest": NWT/Spanisch/IMP gruppiert
    rest.sort(key=lambda s: s.get("profil") or "")

    def place(slist, allowed):
        """Verteile slist so, dass aktuell kleinste erlaubte Klasse zuerst
        wächst – Ziel: gleichmäßige Klassengrößen."""
        if not slist or not allowed:
            return
        priority = {c: i for i, c in enumerate(allowed)}   # stabile Tiebreaker
        for stud in slist:
            elig = [c for c in allowed if rem_cap.get(c, 0) > 0]
            if not elig:
                break
            elig.sort(key=lambda c: (len(asgn[c]), priority[c]))
            cid = elig[0]
            asgn[cid].append(stud["id"])
            rem_cap[cid] -= 1

    place(music_grp,   [musik_class] if musik_class else class_ids)
    place(bili_lat,    bili_classes  if bili_classes  else (latein_classes or class_ids))
    place(bili_only,   bili_classes  if bili_classes  else class_ids)
    place(latein_only, latein_classes if latein_classes else class_ids)
    # Rest darf in alle Klassen – das _place sortiert nach freier Kapazität,
    # also wird die freie Klasse (kein Bili/Musik) zuerst gefüllt.
    place(rest,        class_ids)

    def score(z):
        return score_klasse8(
            z, resolved_wishes, dont_be_with,
            w_friend, w_gender, w_profile, student_map,
        )

    cur_score  = score(asgn)
    best_asgn  = {k: list(v) for k, v in asgn.items()}
    best_score = cur_score

    if len(class_ids) < 2 or not free:
        return best_asgn

    # ── Simulated Annealing ──────────────────────────────────────
    # Bei jedem Schritt mit 25 % Wahrscheinlichkeit eine 3er-Rotation
    # (zyklischer Schub durch 3 Klassen) statt 2er-Swap – das knackt
    # lokale Optima, die einfache Tausche nicht mehr verbessern können.
    iterations = max(5_000, len(free) * 80)
    T          = 70.0
    T_min      = 0.05
    cool       = (T_min / T) ** (1.0 / iterations)

    n_cls = len(class_ids)

    for _ in range(iterations):
        use_rotate = (n_cls >= 3 and random.random() < 0.25)

        if use_rotate:
            c1, c2, c3 = random.sample(class_ids, 3)
            p1 = [i for i, sid in enumerate(asgn[c1]) if sid in free_ids]
            p2 = [i for i, sid in enumerate(asgn[c2]) if sid in free_ids]
            p3 = [i for i, sid in enumerate(asgn[c3]) if sid in free_ids]
            if not p1 or not p2 or not p3:
                T = max(T_min, T * cool)
                continue
            i1, i2, i3 = random.choice(p1), random.choice(p2), random.choice(p3)
            sid1, sid2, sid3 = asgn[c1][i1], asgn[c2][i2], asgn[c3][i3]
            # Rotation: sid1→c2, sid2→c3, sid3→c1
            if (c2 in forbidden_for(sid1)
                or c3 in forbidden_for(sid2)
                or c1 in forbidden_for(sid3)):
                T = max(T_min, T * cool)
                continue
            asgn[c1][i1] = sid3
            asgn[c2][i2] = sid1
            asgn[c3][i3] = sid2
            new_score = score(asgn)
            delta     = new_score - cur_score
            if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
                cur_score = new_score
                if cur_score > best_score:
                    best_score = cur_score
                    best_asgn  = {k: list(v) for k, v in asgn.items()}
            else:
                asgn[c1][i1], asgn[c2][i2], asgn[c3][i3] = sid1, sid2, sid3
        else:
            c1, c2 = random.sample(class_ids, 2)
            pool1 = [i for i, sid in enumerate(asgn[c1]) if sid in free_ids]
            pool2 = [i for i, sid in enumerate(asgn[c2]) if sid in free_ids]
            if not pool1 or not pool2:
                T = max(T_min, T * cool)
                continue

            i1, i2 = random.choice(pool1), random.choice(pool2)
            sid1, sid2 = asgn[c1][i1], asgn[c2][i2]

            if c2 in forbidden_for(sid1) or c1 in forbidden_for(sid2):
                T = max(T_min, T * cool)
                continue

            asgn[c1][i1], asgn[c2][i2] = sid2, sid1
            new_score = score(asgn)
            delta     = new_score - cur_score

            if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
                cur_score = new_score
                if cur_score > best_score:
                    best_score = cur_score
                    best_asgn  = {k: list(v) for k, v in asgn.items()}
            else:
                asgn[c1][i1], asgn[c2][i2] = sid1, sid2

        T = max(T_min, T * cool)

    return best_asgn


# ──────────────────────────────────────────────────────────────────────────────
# Klasse 8 – Haupt-Einstiegspunkt
# ──────────────────────────────────────────────────────────────────────────────

def _wish_score(classes: list, resolved_wishes: dict) -> int:
    sid2cls: dict = {}
    for c in classes:
        for sid in c["students"]:
            sid2cls[sid] = c["id"]
    s = 0
    for sid, friends in resolved_wishes.items():
        if sid not in sid2cls:
            continue
        for fid in friends:
            if sid2cls.get(fid) == sid2cls[sid]:
                s += 1
    return s


def calculate_classes_klasse8(
    students:        list,
    params:          dict,
    resolved_wishes: dict,
    dont_be_with:    list,
    locked_students: dict = None,
) -> list:
    """Klassen 8 mischen mit Multi-Start + automatischem Friend-Refinement.

    Params:
        multiStart  – Anzahl unabhängiger SA-Läufe mit verschiedenen Seeds
                      (default 5). Die Lösung mit den meisten erfüllten
                      Wünschen wird zurückgegeben.
        autoRefine  – Anzahl Friend-Refinement-Pässe pro Run (default 2).
    """
    multi_start = max(1, int(params.get("multiStart", 5)))
    auto_refine = max(0, int(params.get("autoRefine", 2)))

    best_classes = None
    best_score   = -1
    for run_idx in range(multi_start):
        if multi_start > 1:
            random.seed(20260511 + run_idx * 9973)
        cl = _calculate_classes_klasse8_single(
            students, params, resolved_wishes, dont_be_with, locked_students,
        )
        for _ in range(auto_refine):
            cur = [{"id": c["id"], "students": list(c["students"])} for c in cl]
            cl = refine_friends_klasse8(
                students, cur, params, resolved_wishes, dont_be_with,
                locked_students,
            )
        score = _wish_score(cl, resolved_wishes)
        if score > best_score:
            best_score   = score
            best_classes = cl
    return best_classes


def _calculate_classes_klasse8_single(
    students:        list,
    params:          dict,
    resolved_wishes: dict,
    dont_be_with:    list,
    locked_students: dict = None,
) -> list:
    """Ein einzelner SA-Lauf für Klasse-8 (ohne Multi-Start)."""
    locked     = locked_students or {}
    max_size   = int(params.get("maxClassSize", 30))
    min_size   = int(params.get("minClassSize", 22))
    w_friend   = params.get("weightFriendWish",     5)
    w_gender   = params.get("weightGenderBalance",  3)
    w_profile  = params.get("weightProfileCluster", 50)
    # "strict"           – Latein hart auf max 2 Klassen (Pflicht); falls
    #                      Musik-Latein-SuS existieren, wird die zweite
    #                      Bili-Klasse gestrichen, damit die Musik-Klasse
    #                      als 2. Latein-Klasse dienen kann.
    # "musik_exception"  – Latein auf max 2 Klassen, ABER Musik-Latein-SuS
    #                      bleiben in der Musik-Klasse (faktisch 3.
    #                      Latein-Klasse mit nur den Musik-Latein-SuS).
    latein_mode      = params.get("lateinMode", "strict")
    force_num_cls    = params.get("forceNumClasses")

    n = len(students)
    if n == 0:
        return []

    student_map = {s["id"]: s for s in students}
    bili_ids   = {s["id"] for s in students if s.get("bili")}
    latein_ids = {s["id"] for s in students if s.get("latein")}
    musik_ids  = {s["id"] for s in students if s.get("profil") == PROFIL_MUSIK}

    musik_latein_count = sum(
        1 for s in students
        if s.get("profil") == PROFIL_MUSIK and s.get("latein")
    )

    if latein_mode == "musik_exception":
        # Klassisches Modus-5-Schema: 2 Bili-Klassen erlaubt; Musik-Latein
        # bleibt in der Musik-Klasse (siehe forbidden_for unten).
        max_bili_classes = 2
    else:
        # Strict: bei Musik-Latein-SuS höchstens 1 Bili-Klasse, damit
        # Musik-Klasse als zweite Latein-Klasse fungieren kann.
        max_bili_classes = 1 if musik_latein_count > 0 else 2
        if len(bili_ids) > max_size and max_bili_classes < 2:
            max_bili_classes = 2

    # Anzahl Klassen so wählen, dass:
    #  – durchschnittliche Größe ≤ max_size
    #  – durchschnittliche Größe ≥ min_size (so weit wie möglich)
    #  – Rest-Schüler (kein Bili/Musik) passen in die Nicht-Bili/Musik-
    #    Klassen, ohne max_size zu sprengen
    bili_count   = len(bili_ids)
    musik_count  = len(musik_ids)
    rest_count   = n - bili_count - musik_count   # untere Schranke für rest

    def fits(nc):
        if nc * max_size < n:
            return False
        if min_size and nc > 1 and n / nc < min_size and nc - 1 >= 1 \
           and math.ceil(n / (nc - 1)) <= max_size:
            return False
        n_bili_cls  = min(max_bili_classes, nc) if bili_count else 0
        n_musik_cls = 1 if musik_count else 0
        normal_cls  = nc - n_bili_cls - n_musik_cls
        if normal_cls < 0:
            return False
        if normal_cls > 0 and rest_count / normal_cls > max_size:
            return False
        return True

    if force_num_cls:
        num_classes = max(1, int(force_num_cls))
    else:
        num_classes = max(1, math.ceil(n / max_size))
        while not fits(num_classes) and num_classes < n:
            num_classes += 1

    class_ids = [f"8{chr(ord('a') + i)}" for i in range(num_classes)]

    # Bili-Klassen (max 1 oder 2 je nach Musik-Latein-Lage)
    n_bili_classes = min(max_bili_classes, num_classes) if bili_ids else 0
    bili_classes   = class_ids[:n_bili_classes]

    # Musik-Klasse: erste Nicht-Bili-Klasse
    musik_class = None
    if musik_ids:
        non_bili = [c for c in class_ids if c not in bili_classes]
        musik_class = non_bili[0] if non_bili else None

    # Latein-Klassen: zuerst Bili-Klassen, ggf. Musik-Klasse als 2.
    # Insgesamt höchstens 2.
    latein_classes = list(bili_classes)
    if latein_ids:
        if musik_latein_count > 0 and musik_class \
           and musik_class not in latein_classes \
           and len(latein_classes) < 2:
            latein_classes.append(musik_class)
        # Wenn immer noch < 2 (z.B. gar keine Bili-Klasse), fülle auf
        for c in class_ids:
            if len(latein_classes) >= 2:
                break
            if c in latein_classes or c == musik_class:
                continue
            latein_classes.append(c)
        if not latein_classes:
            latein_classes = [class_ids[-1]]

    capacities = {cid: max_size for cid in class_ids}

    # Gesperrte SuS, die zu unserer aktiven Liste gehören
    active_ids = set(student_map.keys())
    locked_active = {sid: cid for sid, cid in locked.items()
                     if sid in active_ids and cid in class_ids}

    asgn = optimize_klasse8_assignment(
        students, class_ids, capacities, locked_active,
        resolved_wishes, dont_be_with,
        w_friend, w_gender, w_profile,
        student_map,
        bili_classes, latein_classes, musik_class,
        bili_ids, latein_ids, musik_ids,
        latein_mode=latein_mode,
    )

    return [
        {
            "id":       cid,
            "name":     cid,
            "track":    "8x" if cid == musik_class
                        else ("8y" if cid in bili_classes else "8z"),
            "students": asgn.get(cid, []),
        }
        for cid in class_ids
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Klasse 8 – Refinement-Lauf nur für Freundeswünsche
# ──────────────────────────────────────────────────────────────────────────────

def refine_friends_klasse8(
    students:        list,
    current_classes: list,    # [{"id": "8a", "students": [sid, …]}, …]
    params:          dict,
    resolved_wishes: dict,
    dont_be_with:    list,
    locked_students: dict = None,
) -> list:
    """SA-Refinement vom aktuellen Stand mit reiner Friend-Optimierung.

    Hard-Constraints (Bili/Latein/Musik je nach lateinMode) bleiben aktiv,
    Locks bleiben fix, alle anderen Gewichte (Gender, Profile) sind 0.
    Klassengrößen ändern sich nicht (SA-Swaps).
    """
    locked      = locked_students or {}
    latein_mode = params.get("lateinMode", "strict")
    student_map = {s["id"]: s for s in students}

    bili_ids   = {s["id"] for s in students if s.get("bili")}
    latein_ids = {s["id"] for s in students if s.get("latein")}
    musik_ids  = {s["id"] for s in students if s.get("profil") == PROFIL_MUSIK}

    class_ids = [c["id"] for c in current_classes]
    asgn      = {c["id"]: list(c["students"]) for c in current_classes}

    # Rollenklassen aus aktuellem Stand ableiten (robust gegen Drag-&-Drop)
    bili_classes   = sorted({cid for cid in class_ids
                             if any(sid in bili_ids for sid in asgn[cid])})
    latein_classes = sorted({cid for cid in class_ids
                             if any(sid in latein_ids for sid in asgn[cid])})
    musik_class    = next(
        (cid for cid in class_ids if any(sid in musik_ids for sid in asgn[cid])),
        None,
    )

    locked_ids = set(locked.keys())
    free_ids   = {sid for cid in class_ids for sid in asgn[cid]
                  if sid not in locked_ids}

    if len(class_ids) < 2 or not free_ids:
        return [
            {"id": cid, "name": cid,
             "track": "8x" if cid == musik_class
                      else ("8y" if cid in bili_classes else "8z"),
             "students": asgn[cid]}
            for cid in class_ids
        ]

    def forbidden_for(sid: str) -> set:
        f: set = set()
        is_bili   = sid in bili_ids
        is_musik  = sid in musik_ids
        is_latein = sid in latein_ids
        if is_bili and bili_classes:
            for c in class_ids:
                if c not in bili_classes:
                    f.add(c)
        elif is_musik and musik_class:
            for c in class_ids:
                if c != musik_class:
                    f.add(c)
        if is_latein and latein_classes:
            relax = (latein_mode == "musik_exception" and is_musik)
            if not relax:
                for c in class_ids:
                    if c not in latein_classes:
                        f.add(c)
        return f

    def score(z: dict) -> float:
        sid2cls: dict = {}
        for cid, sids in z.items():
            for sid in sids:
                sid2cls[sid] = cid
        sc = 0.0
        for sid, friends in resolved_wishes.items():
            if sid not in sid2cls:
                continue
            for fid in friends:
                if sid2cls.get(fid) == sid2cls[sid]:
                    sc += 1.0
        for pair in dont_be_with:
            a, b = pair.get("a"), pair.get("b")
            if a and b and sid2cls.get(a) and sid2cls.get(a) == sid2cls.get(b):
                sc -= 1_000_000  # bleibt unverletzbar
        return sc

    cur_score  = score(asgn)
    best_asgn  = {k: list(v) for k, v in asgn.items()}
    best_score = cur_score

    iterations = max(8_000, len(free_ids) * 120)
    T          = 4.0
    T_min      = 0.02
    cool       = (T_min / T) ** (1.0 / iterations)

    for _ in range(iterations):
        use_rotate = (len(class_ids) >= 3 and random.random() < 0.30)

        if use_rotate:
            c1, c2, c3 = random.sample(class_ids, 3)
            p1 = [i for i, sid in enumerate(asgn[c1]) if sid in free_ids]
            p2 = [i for i, sid in enumerate(asgn[c2]) if sid in free_ids]
            p3 = [i for i, sid in enumerate(asgn[c3]) if sid in free_ids]
            if not (p1 and p2 and p3):
                T = max(T_min, T * cool)
                continue
            i1, i2, i3 = random.choice(p1), random.choice(p2), random.choice(p3)
            sid1, sid2, sid3 = asgn[c1][i1], asgn[c2][i2], asgn[c3][i3]
            if (c2 in forbidden_for(sid1)
                or c3 in forbidden_for(sid2)
                or c1 in forbidden_for(sid3)):
                T = max(T_min, T * cool)
                continue
            asgn[c1][i1] = sid3
            asgn[c2][i2] = sid1
            asgn[c3][i3] = sid2
            new_score = score(asgn)
            delta     = new_score - cur_score
            if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
                cur_score = new_score
                if cur_score > best_score:
                    best_score = cur_score
                    best_asgn  = {k: list(v) for k, v in asgn.items()}
            else:
                asgn[c1][i1], asgn[c2][i2], asgn[c3][i3] = sid1, sid2, sid3
        else:
            c1, c2 = random.sample(class_ids, 2)
            p1 = [i for i, sid in enumerate(asgn[c1]) if sid in free_ids]
            p2 = [i for i, sid in enumerate(asgn[c2]) if sid in free_ids]
            if not p1 or not p2:
                T = max(T_min, T * cool)
                continue
            i1, i2 = random.choice(p1), random.choice(p2)
            sid1, sid2 = asgn[c1][i1], asgn[c2][i2]
            if c2 in forbidden_for(sid1) or c1 in forbidden_for(sid2):
                T = max(T_min, T * cool)
                continue
            asgn[c1][i1], asgn[c2][i2] = sid2, sid1
            new_score = score(asgn)
            delta     = new_score - cur_score
            if delta > 0 or random.random() < math.exp(max(-700, delta / T)):
                cur_score = new_score
                if cur_score > best_score:
                    best_score = cur_score
                    best_asgn  = {k: list(v) for k, v in asgn.items()}
            else:
                asgn[c1][i1], asgn[c2][i2] = sid1, sid2

        T = max(T_min, T * cool)

    return [
        {"id": cid, "name": cid,
         "track": "8x" if cid == musik_class
                  else ("8y" if cid in bili_classes else "8z"),
         "students": best_asgn[cid]}
        for cid in class_ids
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Klasse 8 – Trennungsgrund für nicht erfüllte Wünsche
# ──────────────────────────────────────────────────────────────────────────────

def wish_reason_klasse8(
    student:         dict,
    friend:          dict,
    student_class:   str,
    friend_class:    str,
    bili_classes:    list,
    latein_classes:  list,
    musik_class:     str | None,
    resolved_wishes: dict,
) -> str | None:
    """Strukturellen Grund für getrennte Klassen bestimmen."""
    s_bili = student.get("bili")
    f_bili = friend.get("bili")
    if s_bili != f_bili:
        return "Bili-Klasse"

    s_mus = student.get("profil") == PROFIL_MUSIK
    f_mus = friend.get("profil") == PROFIL_MUSIK
    if s_mus != f_mus:
        return "Musik-Profil"

    s_lat = student.get("latein")
    f_lat = friend.get("latein")
    if s_lat != f_lat:
        # Trennung nur, wenn der Latein-SuS in eine Latein-Klasse muss und der
        # andere nicht; ansonsten ist es Optimierungs-Tradeoff
        if (s_lat and student_class in latein_classes and friend_class not in latein_classes) \
           or (f_lat and friend_class in latein_classes and student_class not in latein_classes):
            return "Latein"

    # Einseitig
    if student["id"] not in resolved_wishes.get(friend["id"], []):
        return "einseitiger Wunsch"

    return None

