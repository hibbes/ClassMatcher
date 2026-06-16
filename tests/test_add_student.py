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
