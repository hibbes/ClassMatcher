#!/usr/bin/env python3
"""Golden-Master-Regressionstests fuer den ClassMatcher-Algorithmus.

Der Matcher ist bei multiStart >= 2 deterministisch: calculate_classes /
calculate_classes_klasse8 reseeden das random-Modul vor jedem Lauf mit einem
festen Seed. Dieser Harness friert das aktuelle Verhalten als Golden-Master
ein, damit Refactorings am Simulated-Annealing-Optimierer verifizierbar
verhaltensgleich bleiben (byte-identische Zuweisung).

Benutzung:
  .venv/bin/python tests/run_golden.py            # gegen Golden-Master pruefen
  .venv/bin/python tests/run_golden.py --update   # Golden-Master neu erfassen

Exit 0 = alle Szenarien gruen, 1 = Abweichung oder Invariantenbruch.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import matcher  # noqa: E402

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
GOLDEN = TESTS / "golden"

# multiStart >= 2 ist Pflicht, sonst ist der Matcher nicht deterministisch.
BASE_PARAMS = {
    "maxClassSize": 30, "minClassSize": 22,
    "weightFriendWish": 7, "weightGenderBalance": 2,
    "weightMusicSplit": 50, "weightProfileCluster": 50,
    "multiStart": 3, "autoRefine": 2,
}


def _k5_students():
    return matcher.parse_csv((ROOT / "Anmeldungen.csv").read_text(encoding="utf-8-sig"))


def _k8_students():
    return matcher.parse_csv_klasse8(
        (FIXTURES / "profilwahl_klasse8.csv").read_text(encoding="utf-8-sig"))


def run_matcher(mode, students, params, dont_be_with, locked):
    resolved, _pending = matcher.process_wishes(students)
    if mode == "klasse8":
        classes = matcher.calculate_classes_klasse8(
            students, params, resolved, dont_be_with, locked)
    else:
        classes = matcher.calculate_classes(
            students, params, resolved, dont_be_with, locked)
    sm = {s["id"]: s for s in students}
    stats = matcher.calculate_stats(
        [{"id": c["id"], "students": c["students"]} for c in classes],
        sm, resolved, dont_be_with)
    return classes, stats, resolved


def snapshot(classes, stats, resolved):
    """Kanonischer, JSON-serialisierbarer Schnappschuss eines Matcher-Laufs.

    `assignment` ist die strikte byte-identische Pruefung; der Rest sind
    billige Quer-Checks.
    """
    return {
        "assignment": {c["id"]: sorted(c["students"]) for c in classes},
        "tracks": [[c["id"], c["track"]] for c in classes],
        "class_sizes": [[c["id"], len(c["students"])] for c in classes],
        "fulfilled_total": sum(st["fulfilled_wishes"] for st in stats),
        "violations_total": sum(st["violations"] for st in stats),
        "n_resolved_wishes": sum(len(v) for v in resolved.values()),
    }


def build_scenarios():
    """Liefert [(name, mode, students, params, dont_be_with, locked), ...]."""
    s5 = _k5_students()
    s8 = _k8_students()
    out = [("k5_default", "klasse5", s5, BASE_PARAMS, [], {})]

    dbw5 = [{"a": s5[0]["id"], "b": s5[3]["id"], "label": "p1"},
            {"a": s5[7]["id"], "b": s5[11]["id"], "label": "p2"}]
    out.append(("k5_dontbewith", "klasse5", s5, BASE_PARAMS, dbw5, {}))

    # Locked: Klassen-IDs aus einem Vorablauf bestimmen, dann 3 verschiebbare
    # (Profil 5z) SuS fixieren. Der Vorablauf ist exakt das k5_default-Szenario,
    # bleibt also stabil, solange k5_default byte-identisch bleibt.
    base_classes, _, _ = run_matcher("klasse5", s5, BASE_PARAMS, [], {})
    cids5 = [c["id"] for c in base_classes]
    fill5 = [s for s in s5 if s["profil"] == "5z"]
    locked5 = {fill5[2]["id"]: cids5[0],
               fill5[9]["id"]: cids5[2],
               fill5[17]["id"]: cids5[3]}
    out.append(("k5_locked", "klasse5", s5, BASE_PARAMS, [], locked5))

    p8_strict = dict(BASE_PARAMS, lateinMode="strict")
    p8_musik = dict(BASE_PARAMS, lateinMode="musik_exception")
    out.append(("k8_strict", "klasse8", s8, p8_strict, [], {}))
    out.append(("k8_musik_exception", "klasse8", s8, p8_musik, [], {}))

    dbw8 = [{"a": s8[1]["id"], "b": s8[2]["id"], "label": "q1"},
            {"a": s8[10]["id"], "b": s8[20]["id"], "label": "q2"}]
    out.append(("k8_dontbewith", "klasse8", s8, p8_strict, dbw8, {}))
    return out


def check_invariants(mode, students, locked, snap):
    """Harte Invarianten, die unabhaengig vom Golden-Master immer gelten."""
    errs = []
    ids = {s["id"] for s in students}
    assigned = [sid for sids in snap["assignment"].values() for sid in sids]
    if len(assigned) != len(set(assigned)):
        errs.append("SuS doppelt zugewiesen")
    if not set(assigned) <= ids:
        errs.append("unbekannte SuS-IDs in der Zuweisung")
    if mode == "klasse8" and set(assigned) != ids:
        errs.append(f"SuS verloren: {len(ids) - len(set(assigned))} fehlen "
                    "(Overflow-statt-Drop verletzt)")
    cls_of = {sid: cid for cid, sids in snap["assignment"].items() for sid in sids}
    for sid, cid in locked.items():
        if sid in ids and cls_of.get(sid) != cid:
            errs.append(f"Lock verletzt: {sid} ist in {cls_of.get(sid)} statt {cid}")
    if mode == "klasse8":
        # Hard-Constraint: Musik-Profil und Bili-Zug sind klassendisjunkt.
        sm = {s["id"]: s for s in students}
        for cid, sids in snap["assignment"].items():
            has_bili = any(sm.get(sid, {}).get("bili") for sid in sids)
            has_pure_musik = any(
                sm.get(sid, {}).get("profil") == matcher.PROFIL_MUSIK
                and not sm.get(sid, {}).get("bili")
                for sid in sids
            )
            if has_bili and has_pure_musik:
                errs.append(f"Klasse {cid}: Bili- und reine Musik-SuS gemischt "
                            "(Disjunktheit verletzt)")
    return errs


def diff_snapshot(golden, current):
    """Kurze, lesbare Beschreibung der Abweichung, oder None wenn identisch."""
    if golden == current:
        return None
    lines = []
    g_asg, c_asg = golden.get("assignment", {}), current.get("assignment", {})
    if g_asg != c_asg:
        g_pos = {sid: cid for cid, sids in g_asg.items() for sid in sids}
        c_pos = {sid: cid for cid, sids in c_asg.items() for sid in sids}
        moved = [(sid, g_pos.get(sid), c_pos.get(sid))
                 for sid in sorted(set(g_pos) | set(c_pos))
                 if g_pos.get(sid) != c_pos.get(sid)]
        lines.append(f"    Zuweisung: {len(moved)} SuS in anderer Klasse")
        for sid, g, c in moved[:6]:
            lines.append(f"      {sid}: {g} -> {c}")
        if len(moved) > 6:
            lines.append(f"      ... und {len(moved) - 6} weitere")
    for key in ("fulfilled_total", "violations_total", "n_resolved_wishes",
                "tracks", "class_sizes"):
        if golden.get(key) != current.get(key):
            lines.append(f"    {key}: {golden.get(key)} -> {current.get(key)}")
    return "\n".join(lines)


def main():
    update = "--update" in sys.argv
    GOLDEN.mkdir(exist_ok=True)
    scenarios = build_scenarios()
    failed = 0
    print(f"ClassMatcher Golden-Master  ({len(scenarios)} Szenarien, "
          f"{'ERFASSEN' if update else 'PRUEFEN'})")
    for name, mode, students, params, dbw, locked in scenarios:
        classes, stats, resolved = run_matcher(mode, students, params, dbw, locked)
        snap = snapshot(classes, stats, resolved)
        inv = check_invariants(mode, students, locked, snap)
        gfile = GOLDEN / f"{name}.json"

        if update:
            gfile.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
            print(f"  [{'INVARIANTE!' if inv else 'erfasst'}] {name}: "
                  f"{snap['n_resolved_wishes']} Wuensche, {snap['fulfilled_total']} "
                  f"erfuellt, {len(classes)} Klassen")
            for e in inv:
                print(f"      ! {e}")
            failed += bool(inv)
            continue

        if not gfile.exists():
            print(f"  [FEHLT]  {name}: kein Golden-Master vorhanden (erst --update)")
            failed += 1
            continue
        golden = json.loads(gfile.read_text(encoding="utf-8"))
        d = diff_snapshot(golden, snap)
        if inv:
            print(f"  [FAIL]   {name}: Invariantenbruch")
            for e in inv:
                print(f"      ! {e}")
            failed += 1
        elif d:
            print(f"  [FAIL]   {name}: weicht vom Golden-Master ab")
            print(d)
            failed += 1
        else:
            print(f"  [ok]     {name}: {snap['fulfilled_total']} Wuensche erfuellt, "
                  f"{len(classes)} Klassen, {snap['violations_total']} Verstoesse")

    print()
    if failed:
        print(f"FAIL: {failed}/{len(scenarios)} Szenarien rot")
        return 1
    print(f"PASS: {len(scenarios)}/{len(scenarios)} Szenarien gruen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
