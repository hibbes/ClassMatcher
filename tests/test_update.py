#!/usr/bin/env python3
"""Unit-Tests fuer update.py – reine Logik, kein Netz.

Deckt _parse_version, den Versionsvergleich und check_for_update mit
gestubbtem Fetcher + gestubbter Config ab (inkl. "Fehler -> still kein
Update"- und "update_check=off"-Pfad).

Benutzung:
  .venv/bin/python tests/test_update.py

Exit 0 = alle Tests gruen, 1 = Fehlschlag.
"""
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import update  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_parse_version_normal():
    assert update._parse_version("1.5.10") == (1, 5, 10)
    assert update._parse_version("1.5.9") == (1, 5, 9)


@case
def test_parse_version_compare_numeric_not_lexical():
    # "1.5.10" muss > "1.5.9" sein (Zahlen-, kein String-Vergleich)
    assert update._parse_version("1.5.10") > update._parse_version("1.5.9")


@case
def test_parse_version_broken():
    assert update._parse_version("garbage") == ()
    assert update._parse_version("") == ()
    assert update._parse_version(None) == ()


@case
def test_update_available():
    res = update.check_for_update(
        "1.5.5",
        _fetcher=lambda cfg: {
            "version": "1.5.6",
            "win_url": "https://x/win.exe",
            "mac_url": "https://x/mac.dmg",
            "notes": "neu",
        },
        _config=lambda: {},
    )
    assert res["update_available"] is True
    assert res["latest"] == "1.5.6"
    assert res["download_url"] in ("https://x/win.exe", "https://x/mac.dmg")
    assert res["notes"] == "neu"


@case
def test_no_update_when_equal():
    res = update.check_for_update(
        "1.5.6",
        _fetcher=lambda cfg: {"version": "1.5.6", "win_url": "u", "mac_url": "u"},
        _config=lambda: {},
    )
    assert res["update_available"] is False


@case
def test_no_update_when_server_is_older():
    res = update.check_for_update(
        "1.5.6",
        _fetcher=lambda cfg: {"version": "1.5.5", "win_url": "u", "mac_url": "u"},
        _config=lambda: {},
    )
    assert res["update_available"] is False


@case
def test_fetcher_error_is_graceful():
    def boom(cfg):
        raise OSError("Proxy blockt")

    res = update.check_for_update("1.5.5", _fetcher=boom, _config=lambda: {})
    assert res["update_available"] is False
    assert res["current"] == "1.5.5"


@case
def test_broken_server_version_is_graceful():
    res = update.check_for_update(
        "1.5.5",
        _fetcher=lambda cfg: {"version": "kaputt", "win_url": "u", "mac_url": "u"},
        _config=lambda: {},
    )
    assert res["update_available"] is False


@case
def test_update_check_off_disables():
    res = update.check_for_update(
        "1.5.5",
        _fetcher=lambda cfg: {"version": "9.9.9", "win_url": "u", "mac_url": "u"},
        _config=lambda: {"update_check": "off"},
    )
    assert res["update_available"] is False


@case
def test_download_update_happy_path():
    """Stubbed opener returns an in-memory BytesIO -> file written, {ok: True}."""
    class _FakeOpener:
        def open(self, url, timeout=None):
            return io.BytesIO(b"BINARY-CONTENT-OK")
    with tempfile.TemporaryDirectory() as td:
        res = update.download_update(
            "https://x/file-v1.exe",
            _config=lambda: {},
            _opener_factory=lambda cfg: _FakeOpener(),
            _target_dir=td,
        )
        files = sorted(p.name for p in Path(td).iterdir())
    assert res["ok"] is True
    assert res["path"].endswith("file-v1.exe")
    assert files == ["file-v1.exe"], f"Erwartete nur die fertige Datei, fand: {files}"


@case
def test_download_update_failure_returns_fallback_and_cleans_part():
    """Opener raises -> {ok: False, fallback_url}, kein .part-Rest im Zielordner."""
    class _BrokenOpener:
        def open(self, url, timeout=None):
            raise OSError("Proxy blockiert")
    with tempfile.TemporaryDirectory() as td:
        res = update.download_update(
            "https://x/file-v1.exe",
            _config=lambda: {},
            _opener_factory=lambda cfg: _BrokenOpener(),
            _target_dir=td,
        )
        leftover = sorted(p.name for p in Path(td).iterdir())
    assert res["ok"] is False
    assert res["fallback_url"] == "https://x/file-v1.exe"
    assert leftover == [], f"Erwartete sauberes Zielverzeichnis, fand: {leftover}"


def main() -> int:
    failed = 0
    for fn in CASES:
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {fn.__name__}: {e!r}")
    total = len(CASES)
    print(f"\n{total - failed}/{total} Tests gruen")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
