from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dab import cli, meta, scheduler


def test_identity_comes_from_pyproject() -> None:
    project = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert meta.NAME == project["name"]
    assert meta.DESCRIPTION == project["description"]


def test_identity_is_reused_not_repeated() -> None:
    assert cli.DEFAULT_CONFIG.name == f"{meta.NAME}_config.py"
    assert cli.DEFAULT_LOG.name == f"{meta.NAME}.log"
    assert scheduler.TASK_NAME == meta.BRAND
    xml = scheduler.build_xml(scheduler.TaskSpec("c.exe", "--apply", "C:/w", "S-1-5-21"))
    assert f"<Description>{meta.DESCRIPTION}</Description>" in xml


def test_version_comes_from_pyproject_and_is_in_the_banner(capsys: pytest.CaptureFixture[str]) -> None:
    project = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == meta.VERSION
    assert cli.main([]) == 0
    assert f"{meta.NAME} {meta.VERSION}" in capsys.readouterr().out
