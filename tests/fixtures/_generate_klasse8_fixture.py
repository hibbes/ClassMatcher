#!/usr/bin/env python3
"""Erzeugt profilwahl_klasse8.csv (deterministisch, ohne random).

Die erzeugte CSV ist die eigentliche Test-Fixture (Source of Truth) und wird
committet. Dieses Skript dokumentiert nur, wie sie entstanden ist. Wenn man
die Fixture aendert, muss das Golden-Master mit `run_golden.py --update`
neu erfasst werden.

Eigenschaften der Fixture (76 Zeilen, davon 5 gedroppt):
  - 3 Verlasser (i in 13,41,68)            -> werden vom Parser gedroppt
  - 2 Nicht-Waehler ohne Profil (i 7,50)   -> werden gedroppt
  - Bili: i % 6 == 0  plus i in 3,27,51    -> 3 davon sind Bili+Musik
  - Latein: i % 5 == 0                     -> u.a. 4 Musik-Latein-Faelle
  - Profile zyklisch NWT/Spanisch/IMP/Musik
  - Freundeswuensche per Klarnamen (loesen ueber Fuzzy-Matching auf)
"""
from pathlib import Path

PROFILE = ["Naturwissenschaft und Technik (NWT)", "Spanisch", "IMP", "Musik"]
HEADER = [
    "Nachname", "Vorname", "Klasse/Information", "Ich bin ...",
    "Ich bin im Bili - Zug", "Ich habe Latein als Zweitsprache",
    "Ich habe vor, das Schiller nach der 7. Klasse zu verlassen.",
    "Ich wähle folgendes Profil ab der 8. Klasse.",
    "Ich möchte bitte mit folgenden Freunden in eine Klasse kommen.",
    "Ich hätte IMP gewählt.",
]

N = 76
LEAVERS = {13, 41, 68}
NON_CHOOSERS = {7, 50}
EXTRA_BILI = {3, 27, 51}
NO_WISH = {2, 19, 44}


def vorname(i): return f"Person{i:02d}"
def nachname(i): return f"Test{i:02d}"
def displayname(i): return f"{vorname(i)} {nachname(i)}"


def build_rows():
    rows = []
    for i in range(N):
        if i in NO_WISH:
            wish = ""
        else:
            wish = f"{displayname((i + 1) % N)}, {displayname((i * 7 + 3) % N)}"
        rows.append([
            nachname(i), vorname(i), f"7{'abcd'[i % 4]}",
            "männlich" if i % 2 == 0 else "weiblich",
            "Ja" if (i % 6 == 0 or i in EXTRA_BILI) else "Nein",
            "Ja" if i % 5 == 0 else "Nein",
            "Ja" if i in LEAVERS else "Nein",
            "" if i in NON_CHOOSERS else PROFILE[i % 4],
            wish,
            "Ja" if i % 8 == 0 else "Nein",
        ])
    return rows


def main():
    out = Path(__file__).resolve().parent / "profilwahl_klasse8.csv"
    rows = build_rows()
    lines = [";".join(HEADER)] + [";".join(r) for r in rows]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"geschrieben: {out}  ({len(rows)} Zeilen)")


if __name__ == "__main__":
    main()
