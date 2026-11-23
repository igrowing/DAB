from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from dab import cli, config, default_config


def test_no_arguments_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    for flag in ("--list", "--dry-run", "--apply", "--uninstall", "--config"):
        assert flag in out


def test_missing_default_config_is_created_from_the_starter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    target = tmp_path / "dab_config.py"
    monkeypatch.setattr(cli, "DEFAULT_CONFIG", target)
    assert cli.main(["--list"]) == 0
    assert target.read_text(encoding="utf-8") == default_config.TEMPLATE
    assert "created a starter" in caplog.text
    # the starter has no apps yet: the next run says so and succeeds, it must not treat that as an error
    caplog.clear()
    assert cli.main(["--list"]) == 0
    assert "no applications" in caplog.text
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    assert target.read_text(encoding="utf-8") == default_config.TEMPLATE


def test_missing_explicit_config_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "typo.py"
    assert cli.main(["--list", "--config", str(missing)]) == 2
    assert not missing.exists()


def test_starter_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "dab_config.py"
    target.write_text("# mine", encoding="utf-8")
    assert config.create_starter(target) is False
    assert target.read_text(encoding="utf-8") == "# mine"


def test_starter_is_valid_python_with_empty_apps(tmp_path: Path) -> None:
    target = tmp_path / "dab_config.py"
    config.create_starter(target)
    ns = runpy.run_path(str(target))
    assert ns["APPS"] == {}
    assert ns["PROGID_OVERRIDES"] == {}


def test_options_without_a_mode_are_still_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", "x.py"])
    assert exc.value.code == 2


class _ProtectedReg:
    def effective_prog_id(self, name: str, *, protocol: bool = False) -> str | None:
        return "Some.Prog" if name in {".pdf", "https"} else None

    def get_user_choice(self, ext: str) -> None:
        return None

    def get_legacy_choice(self, ext: str) -> None:
        return None

    def prog_id_exe(self, prog_id: str) -> None:
        return None

    def openwith_progids(self, ext: str) -> list[str]:
        return []

    def exe_prog_ids(self, exe: str) -> list[str]:
        return []

    def application_prog_id(self, exe: str) -> None:
        return None


def test_dry_run_lists_protected_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"")
    cfg_file = tmp_path / "c.py"
    cfg_file.write_text(f"APPS = {{{str(exe)!r}: ['.pdf']}}", encoding="utf-8")
    monkeypatch.setattr(cli, "Registry", _ProtectedReg)
    assert cli.main(["--dry-run", "--config", str(cfg_file)]) == 0
    section = capsys.readouterr().out.split("set by hand")[1]
    assert ".pdf" in section
    assert "https" in section
    assert "Some.Prog" in section
