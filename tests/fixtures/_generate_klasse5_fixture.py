#!/usr/bin/env python3
"""Erzeugt eine SYNTHETISCHE Anmeldungen.csv (Klasse-5-Beispiel- und Testdaten).

Ersetzt die fruehere Datei, die echte Schuelerdaten enthielt. Alle Namen,
Adressen und Kontaktdaten hier sind frei erfunden (Muster*/Beispiel*,
@example.invalid). Der Spaltenaufbau entspricht dem Export der
Schulverwaltungssoftware, damit die Datei weiter als Format-Beispiel taugt.

Die erzeugte Anmeldungen.csv (Repo-Wurzel) ist die Source of Truth und wird
committet. Nach Aenderungen das Golden-Master mit run_golden.py --update
neu erfassen.
"""
import csv
from pathlib import Path

COLUMNS = [
    "ID", "Eintrags_ID", "Klasse", "Name", "Vorname", "Rufname", "Geburtstag",
    "Geburtsort", "Geburtsland", "Geschlecht", "Religion", "RU", "Land", "Land2",
    "Strasse", "HausNr", "PLZ", "Ort", "Teilort", "Muttersprache",
    "Schuleintrittam", "Erz1Name", "Erz1Vorname", "Erz1Geschlecht", "Erz1Strasse",
    "Erz1HausNr", "Erz1PLZ", "Erz1Ort", "Erz1Teilort", "Erz1Telefon1",
    "Erz1Telefon2", "Erz1Handy", "Erz1Email", "Erz2Name", "Erz2Vorname",
    "Erz2Geschlecht", "Erz2Strasse", "Erz2HausNr", "Erz2PLZ", "Erz2Ort",
    "Erz2Teilort", "Erz2Telefon1", "Erz2Telefon2", "Erz2Handy", "Erz2Email",
    "Profil1", "Profil1von", "Profil1bis", "AbgebendeSchule", "SonstigeSchule",
    "Sprachwahl", "Fremdsprache1", "Fremdsprache2", "Foto_Einw", "Geschwister",
    "Klassenpartner", "vorhKlasse", "erz2sorgerecht", "erz2auskunftsrecht",
    "reinw", "schwimmen", "impfung",
]

VORNAMEN_M = ["Leon", "Paul", "Finn", "Luca", "Noah", "Elias", "Ben", "Jonas",
              "Felix", "Max", "Tim", "Niklas", "Lukas", "Jan", "David", "Moritz",
              "Julian", "Tom", "Philipp", "Simon", "Erik", "Jakob", "Anton", "Emil"]
VORNAMEN_W = ["Mia", "Emma", "Hanna", "Lena", "Lea", "Marie", "Sophie", "Lina",
              "Clara", "Laura", "Anna", "Emily", "Nele", "Sarah", "Johanna", "Ida",
              "Maja", "Frieda", "Pia", "Greta", "Lily", "Mara", "Nora", "Zoe"]
NACHNAMEN = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer",
             "Wagner", "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer",
             "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz",
             "Zimmermann", "Braun", "Krüger", "Hofmann", "Hartmann", "Lange",
             "Schmitt", "Werner", "Krause", "Meier", "Lehmann", "Schmid",
             "Schulze", "Maier", "Köhler", "Herrmann", "König", "Walter", "Mayer",
             "Huber", "Kaiser", "Fuchs", "Peters", "Lang", "Scholz", "Möller",
             "Weiß", "Jung", "Hahn"]

N = 115


def _vorname(i):
    """(Vorname, Geschlecht) deterministisch, m/w abwechselnd."""
    if i % 2 == 0:
        return VORNAMEN_M[(i // 2) % len(VORNAMEN_M)], "m"
    return VORNAMEN_W[(i // 2) % len(VORNAMEN_W)], "w"


def _nachname(i):
    return NACHNAMEN[(i * 17 + 5) % len(NACHNAMEN)]


def _displayname(i):
    vn, _ = _vorname(i)
    return f"{vn} {_nachname(i)}"


def build_row(i):
    vn, gesch = _vorname(i)
    nn = _nachname(i)
    # Profil-Mix: Bili ~1/7, Musikzug ~1/9 (versetzt), sonst Normalzug.
    if i % 7 == 0:
        profil = "5y"
    elif i % 9 == 3:
        profil = "5x"
    else:
        profil = "5z"
    fs2 = "L" if i % 3 == 0 else "F"
    # Freundeswuensche per Klarnamen; manche leer, einer leicht vertippt.
    if i % 10 == 3:
        wunsch = ""
    else:
        names = [_displayname((i + 1) % N), _displayname((i * 3 + 7) % N)]
        if i % 23 == 5:
            names[0] = names[0].replace("a", "aa", 1)
        wunsch = ", ".join(names)
    haus = str((i % 80) + 1)
    return {
        "ID": str(1000 + i), "Eintrags_ID": str(50000 + i), "Klasse": "5",
        "Name": nn, "Vorname": vn, "Rufname": vn if i % 4 == 0 else "",
        "Geburtstag": f"{(i % 28) + 1:02d}.{(i % 12) + 1:02d}.{2015 + i % 2}",
        "Geburtsort": "Beispielstadt", "Geburtsland": "D", "Geschlecht": gesch,
        "Religion": ["rk", "ev", ""][i % 3], "RU": ["RK", "EV", "KEIN"][i % 3],
        "Land": "D", "Land2": "",
        "Strasse": "Musterstraße", "HausNr": haus, "PLZ": "77654",
        "Ort": "Beispielstadt", "Teilort": "", "Muttersprache": "deutsch",
        "Schuleintrittam": "2022",
        "Erz1Name": nn, "Erz1Vorname": "Elternteil A", "Erz1Geschlecht": "w",
        "Erz1Strasse": "Musterstraße", "Erz1HausNr": haus, "Erz1PLZ": "77654",
        "Erz1Ort": "Beispielstadt", "Erz1Teilort": "",
        "Erz1Telefon1": "00000 000000", "Erz1Telefon2": "",
        "Erz1Handy": "0000 0000000", "Erz1Email": f"familie{i:03d}@example.invalid",
        "Erz2Name": nn, "Erz2Vorname": "Elternteil B", "Erz2Geschlecht": "m",
        "Erz2Strasse": "Musterstraße", "Erz2HausNr": haus, "Erz2PLZ": "77654",
        "Erz2Ort": "Beispielstadt", "Erz2Teilort": "", "Erz2Telefon1": "",
        "Erz2Telefon2": "", "Erz2Handy": "0000 0000000",
        "Erz2Email": f"familie{i:03d}.b@example.invalid",
        "Profil1": profil, "Profil1von": "", "Profil1bis": "",
        "AbgebendeSchule": f"GS-{i % 6:02d}", "SonstigeSchule": "",
        "Sprachwahl": "E", "Fremdsprache1": "E", "Fremdsprache2": fs2,
        "Foto_Einw": "Ja" if i % 2 == 0 else "Nein", "Geschwister": "",
        "Klassenpartner": wunsch, "vorhKlasse": f"4{'abcd'[i % 4]}",
        "erz2sorgerecht": "Ja", "erz2auskunftsrecht": "Ja",
        "reinw": "Ja" if i % 5 else "Nein", "schwimmen": "Ja",
        "impfung": "Ja" if i % 3 else "Nein",
    }


def main():
    out = Path(__file__).resolve().parent.parent.parent / "Anmeldungen.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for i in range(N):
            writer.writerow(build_row(i))
    print(f"geschrieben: {out}  ({N} Zeilen, synthetisch)")


if __name__ == "__main__":
    main()
