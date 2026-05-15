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


@case
def test_download_update_installer_called_with_final_path_and_records_success():
    """Wenn _installer True liefert, taucht installed=True im Ergebnis auf."""
    class _FakeOpener:
        def open(self, url, timeout=None):
            return io.BytesIO(b"NEW-EXE-BYTES")
    installed_with: list = []
    def _fake_installer(p):
        installed_with.append(p)
        return True
    with tempfile.TemporaryDirectory() as td:
        res = update.download_update(
            "https://x/file-v2.exe",
            _config=lambda: {},
            _opener_factory=lambda cfg: _FakeOpener(),
            _target_dir=td,
            _installer=_fake_installer,
        )
    assert res["ok"] is True
    assert res["installed"] is True, f"Erwartete installed=True, sah {res}"
    assert len(installed_with) == 1, f"Installer-Aufruf-Anzahl falsch: {installed_with}"
    assert installed_with[0].name == "file-v2.exe"


@case
def test_download_update_installer_failure_keeps_ok_but_installed_false():
    """Wenn _installer False liefert (kein Windows, kein frozen, ...),
    bleibt der Download trotzdem als ok stehen — User muss manuell tauschen."""
    class _FakeOpener:
        def open(self, url, timeout=None):
            return io.BytesIO(b"NEW-EXE-BYTES")
    with tempfile.TemporaryDirectory() as td:
        res = update.download_update(
            "https://x/file-v2.exe",
            _config=lambda: {},
            _opener_factory=lambda cfg: _FakeOpener(),
            _target_dir=td,
            _installer=lambda p: False,
        )
    assert res["ok"] is True
    assert res["installed"] is False


@case
def test_install_windows_skips_when_not_windows_or_not_frozen():
    """install_windows ist ein no-op (False) auf Linux/Mac und im Source-
    Mode (kein sys.frozen). Test laeuft auf Linux ohne PyInstaller-Bundle,
    deckt beide Bedingungen ab."""
    import platform, sys as _sys
    # Auf der Test-Umgebung ist sys.frozen unset und platform.system != Windows.
    assert update.install_windows("anything") is False
    # Auch mit einem existierenden Pfad: weiter False, weil Plattform/Bundle
    # nicht stimmt.
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tf:
        tf.write(b"\x4d\x5a")  # MZ header
        tmp_exe = tf.name
    try:
        assert update.install_windows(tmp_exe) is False
    finally:
        Path(tmp_exe).unlink(missing_ok=True)


@case
def test_cleanup_old_exe_is_noop_outside_windows():
    """cleanup_old_exe darf auf Linux/Mac nichts loeschen und nie werfen."""
    # Wir koennen nicht direkt etwas testen, ausser dass kein Exception fliegt.
    update.cleanup_old_exe()  # darf einfach durchlaufen


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
