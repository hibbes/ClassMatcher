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


def test_add_student_wishes_suggest_range_adds_candidate_without_mutating():
    # Token 'Yas' scores 0.571 against Yara Neuling: in [SUGGEST_THRESHOLD=0.45, AUTO_THRESHOLD=0.75)
    new = {"id": "y", "displayName": "Yara Neuling", "vorname": "Yara",
           "rufname": "", "name": "Neuling", "klassenpartner": ""}
    existing = [{"id": "x", "displayName": "Xaver Test", "vorname": "Xaver",
                 "rufname": "", "name": "Test", "klassenpartner": "Yas"}]
    orig_candidates = []
    resolved = {"x": []}
    pending  = {"x": [{"token": "Yas", "candidates": orig_candidates}]}
    matcher.add_student_wishes(new, existing, resolved, pending)
    # Suggest-Treffer: Token bleibt offen, neuer Kandidat ergaenzt, kein Auto-Resolve
    assert len(pending["x"]) == 1
    assert pending["x"][0]["token"] == "Yas"
    assert any(c["id"] == "y" for c in pending["x"][0]["candidates"])
    assert "y" not in resolved["x"]
    # additiv ohne Mutation der urspruenglichen Kandidatenliste
    assert orig_candidates == []


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
    assert s["displayName"] == "Muster, Mia"
    assert s["id"].startswith("manual-")
    assert s["religion"] == ""
    assert s["ru"] == "rk"


def test_build_manual_student_klasse5_rufname_wins_in_display():
    s = matcher.build_manual_student("klasse5", {
        "vorname": "Maximilian", "name": "Muster", "rufname": "Max",
        "profil": "5z", "geschlecht": "m", "fremdsprache2": "L",
        "klassenpartner": "", "ru": "",
    }, set())
    assert s["displayName"] == "Muster, Max"


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
    assert s["displayName"] == "Beispiel, Ben"


def test_build_manual_student_unique_ids():
    ids = set()
    fields = {"vorname": "Mia", "name": "Muster", "rufname": "", "profil": "5z",
              "geschlecht": "w", "fremdsprache2": "F", "klassenpartner": "", "ru": ""}
    s1 = matcher.build_manual_student("klasse5", fields, ids); ids.add(s1["id"])
    s2 = matcher.build_manual_student("klasse5", fields, ids); ids.add(s2["id"])
    assert s1["id"] != s2["id"]
    assert s1["id"].startswith("manual-") and s2["id"].startswith("manual-")


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
    assert c.post("/api/add-student", json={
        "vorname": "X", "name": "Y", "profil": "5z", "geschlecht": "w",
        "fremdsprache2": "X"}).status_code == 400


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
    # Simuliere eine zuvor manuell geklaerte Aufloesung:
    app._state["resolved_wishes"]["1"] = ["2"]
    app._state["pending_wishes"]["1"] = []
    r = c.post("/api/add-student", json={
        "vorname": "Tom", "name": "Test", "profil": "5z", "geschlecht": "m"})
    assert r.status_code == 200
    assert app._state["resolved_wishes"]["1"] == ["2"]
    tom = [s for s in app._state["students"] if s["id"].startswith("manual-")][0]
    assert tom["fremdsprache2"] == "F"


def test_add_student_rolls_back_on_assignment_failure(monkeypatch):
    c = _client()
    _upload_k5(c)
    before = len(app._state["students"])
    monkeypatch.setattr(
        app, "_assignment_payload",
        lambda locked: (_ for _ in ()).throw(RuntimeError("boom")))
    r = c.post("/api/add-student", json={
        "vorname": "Rollback", "name": "Test", "profil": "5z", "geschlecht": "m"})
    assert r.status_code == 500
    # Schueler wurde zurueckgerollt, kein halb-integrierter Zustand:
    assert len(app._state["students"]) == before
    assert not any(s["id"].startswith("manual-") for s in app._state["students"])
    assert not any(k.startswith("manual-") for k in app._state["resolved_wishes"])


# ── matcher._display_name ─────────────────────────────────────────────────

def test_display_name_nachname_zuerst():
    assert matcher._display_name("Muster", "Mia") == "Muster, Mia"


def test_display_name_robust_bei_leeren_teilen():
    assert matcher._display_name("Muster", "") == "Muster"
    assert matcher._display_name("", "Mia") == "Mia"
    assert matcher._display_name("", "") == ""
    assert matcher._display_name("  Muster  ", "  Mia  ") == "Muster, Mia"
