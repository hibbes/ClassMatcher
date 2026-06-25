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


@case
def test_log_path_is_under_system_tempdir():
    """Diagnose-Log muss plattformuebergreifend schreibbar sein. Frueher war
    /tmp hartkodiert, das es auf Windows (der Zielplattform) nicht gibt -> Log
    entstand dort nie. tempfile.gettempdir() liefert ueberall ein schreibbares
    Verzeichnis."""
    assert update._LOG_PATH == Path(tempfile.gettempdir()) / "classmatcher-update.log"


@case
def test_log_update_writes_to_log_path():
    """_log_update schreibt nach _LOG_PATH (hier auf eine Temp-Datei umgebogen)."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "u.log"
        orig = update._LOG_PATH
        update._LOG_PATH = p
        try:
            update._log_update("hallo-welt")
        finally:
            update._LOG_PATH = orig
        assert p.exists()
        assert "hallo-welt" in p.read_text(encoding="utf-8")


@case
def test_check_for_update_logs_success_heartbeat():
    """Auch der Erfolgsfall hinterlaesst eine Log-Zeile (current + latest), damit
    auf Schul-PCs sichtbar ist, dass ueberhaupt geprueft wurde."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "u.log"
        orig = update._LOG_PATH
        update._LOG_PATH = p
        try:
            update.check_for_update(
                "1.5.5",
                _fetcher=lambda cfg: {"version": "1.6.0", "win_url": "u", "mac_url": "u"},
                _config=lambda: {})
        finally:
            update._LOG_PATH = orig
        text = p.read_text(encoding="utf-8")
        assert "1.6.0" in text and "1.5.5" in text


@case
def test_check_for_update_mac_uses_no_windows_sha_fallback():
    orig = update.platform.system
    update.platform.system = lambda: "Darwin"
    try:
        res = update.check_for_update("1.0.0", _config=lambda: {},
            _fetcher=lambda c: {"version": "9.9.9",
                "win_url": "https://www.schiller-offenburg.de/c/win.exe",
                "mac_url": "https://www.schiller-offenburg.de/c/mac.dmg",
                "sha256": "deadbeefwindowshash"})
    finally:
        update.platform.system = orig
    assert res["update_available"] is True
    assert res["sha256"] is None  # darf NICHT den Windows-sha256 erben


@case
def test_install_windows_swaps_in_place_and_keeps_backup():
    import tempfile
    from pathlib import Path
    o_sys = update.platform.system
    o_exe = update.sys.executable
    o_frozen = getattr(update.sys, "frozen", None)
    with tempfile.TemporaryDirectory() as td:
        cur = Path(td) / "App.exe"; cur.write_bytes(b"OLD")
        new = Path(td) / "dl" / "App-new.exe"; new.parent.mkdir(); new.write_bytes(b"NEW")
        update.platform.system = lambda: "Windows"
        update.sys.frozen = True
        update.sys.executable = str(cur)
        try:
            ok = update.install_windows(new)
        finally:
            update.platform.system = o_sys
            update.sys.executable = o_exe
            if o_frozen is None:
                try: del update.sys.frozen
                except Exception: pass
            else:
                update.sys.frozen = o_frozen
        assert ok is True
        assert cur.read_bytes() == b"NEW"
        assert (Path(td) / "App.exe.old").read_bytes() == b"OLD"


@case
def test_install_windows_rolls_back_on_move_failure():
    import tempfile
    from pathlib import Path
    o_sys = update.platform.system
    o_exe = update.sys.executable
    o_frozen = getattr(update.sys, "frozen", None)
    o_move = update.shutil.move
    with tempfile.TemporaryDirectory() as td:
        cur = Path(td) / "App.exe"; cur.write_bytes(b"OLD")
        new = Path(td) / "dl" / "App-new.exe"; new.parent.mkdir(); new.write_bytes(b"NEW")
        update.platform.system = lambda: "Windows"
        update.sys.frozen = True
        update.sys.executable = str(cur)
        def boom(*a, **k): raise OSError("AV lock")
        update.shutil.move = boom
        try:
            ok = update.install_windows(new)
        finally:
            update.platform.system = o_sys
            update.sys.executable = o_exe
            update.shutil.move = o_move
            if o_frozen is None:
                try: del update.sys.frozen
                except Exception: pass
            else:
                update.sys.frozen = o_frozen
        assert ok is False
        assert cur.exists(), "App-EXE muss nach Rollback noch da sein (kein Bricking)"
        assert cur.read_bytes() == b"OLD"


@case
def test_download_update_rejects_on_sha_mismatch_and_cleans_part():
    class Op:
        def open(self, u, timeout=None): return io.BytesIO(b"TAMPERED-BYTES")
    with tempfile.TemporaryDirectory() as td:
        res = update.download_update("https://x/win.exe",
            expected_sha256="deadbeef", _config=lambda: {},
            _opener_factory=lambda c: Op(), _target_dir=td)
        leftover = sorted(p.name for p in Path(td).iterdir())
    assert res["ok"] is False
    assert "fallback_url" in res
    assert leftover == [], f"kein .part-Rest erwartet, fand: {leftover}"


@case
def test_url_is_allowed_rules():
    assert update.url_is_allowed("https://www.schiller-offenburg.de/classmatcher/x.exe") is True
    assert update.url_is_allowed("http://www.schiller-offenburg.de/classmatcher/x.exe") is False   # HTTP-Downgrade
    assert update.url_is_allowed("https://evil.example.com/x.exe") is False                         # fremder Host
    assert update.url_is_allowed("not-a-url") is False
    assert update.url_is_allowed(None) is False


@case
def test_download_update_strips_path_traversal_to_basename():
    class Op:
        def open(self, u, timeout=None): return io.BytesIO(b"X")
    with tempfile.TemporaryDirectory() as td:
        res = update.download_update("https://x/a/b/../../../../etc/evilname",
            _config=lambda: {}, _opener_factory=lambda c: Op(), _target_dir=td)
        files = sorted(p.name for p in Path(td).iterdir())
    assert res["ok"] is True
    # Datei landet als reiner Basename im Zielordner, kein Ausbruch:
    assert files == ["evilname"], files
    assert Path(res["path"]).parent == Path(td)


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
