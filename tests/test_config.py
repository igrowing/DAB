from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dab import config


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "cfg.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_and_normalizes(tmp_path: Path) -> None:
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"")
    cfg = config.load(_write(tmp_path, f"APPS = {{{str(exe)!r}: ['JPG', '.Png']}}"))
    assert cfg.wanted == {".jpg": str(exe), ".png": str(exe)}


def test_missing_exe_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="application not found"):
        config.load(_write(tmp_path, "APPS = {'C:/nope/x.exe': ['.a']}"))


def test_extension_assigned_twice_last_wins_with_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    a, b = tmp_path / "a.exe", tmp_path / "b.exe"
    a.write_bytes(b"")
    b.write_bytes(b"")
    with caplog.at_level(logging.WARNING, logger="dab.config"):
        cfg = config.load(_write(tmp_path, f"APPS = {{{str(a)!r}: ['.x', '.y'], {str(b)!r}: ['.x']}}"))
    assert cfg.wanted == {".x": str(b), ".y": str(a)}
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert ".x" in record.getMessage()
    assert str(a) in record.getMessage()
    assert str(b) in record.getMessage()


def test_bad_extension_and_missing_apps(tmp_path: Path) -> None:
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"")
    with pytest.raises(config.ConfigError, match="invalid extension"):
        config.load(_write(tmp_path, f"APPS = {{{str(exe)!r}: ['.a b']}}"))
    with pytest.raises(config.ConfigError, match="APPS"):
        config.load(_write(tmp_path, "X = 1"))
    with pytest.raises(config.ConfigError, match="not found"):
        config.load(tmp_path / "missing.py")


def test_override_for_unknown_extension_is_an_error(tmp_path: Path) -> None:
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"")
    body = f"APPS = {{{str(exe)!r}: ['.a']}}\nPROGID_OVERRIDES = {{'.b': 'X'}}"
    with pytest.raises(config.ConfigError, match="not in APPS"):
        config.load(_write(tmp_path, body))
