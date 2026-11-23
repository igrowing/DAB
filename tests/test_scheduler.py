from __future__ import annotations

import dataclasses

import pytest

from dab import scheduler
from dab.scheduler import TaskSpec

SPEC = TaskSpec(
    command=r"C:\Tools\DAB\dab.exe",
    arguments="--apply",
    working_dir=r"C:\Tools\DAB",
    sid="S-1-5-21-1-2-3-1001",
)


def test_generated_xml_is_recognized_as_configured() -> None:
    assert scheduler.is_configured(scheduler.build_xml(SPEC), SPEC)


def test_xml_escapes_special_characters() -> None:
    spec = dataclasses.replace(SPEC, arguments='--apply --config "C:\\a&b\\c.py"')
    assert scheduler.is_configured(scheduler.build_xml(spec), spec)


def test_path_comparison_ignores_case_and_slashes() -> None:
    other = dataclasses.replace(SPEC, command="c:/tools/dab/DAB.EXE", working_dir="c:/tools/dab/")
    assert scheduler.is_configured(scheduler.build_xml(SPEC), other)


@pytest.mark.parametrize(
    "change",
    [
        {"command": r"C:\Elsewhere\dab.exe"},
        {"arguments": "--list"},
        {"working_dir": r"C:\Elsewhere"},
    ],
)
def test_different_action_is_not_configured(change: dict[str, str]) -> None:
    other = dataclasses.replace(SPEC, **change)
    assert not scheduler.is_configured(scheduler.build_xml(SPEC), other)


def test_trigger_without_delay_is_not_configured() -> None:
    xml = scheduler.build_xml(SPEC).replace(f"<Delay>{SPEC.delay}</Delay>", "")
    assert not scheduler.is_configured(xml, SPEC)


def test_boot_trigger_instead_of_logon_is_not_configured() -> None:
    xml = scheduler.build_xml(SPEC).replace("LogonTrigger", "BootTrigger")
    assert not scheduler.is_configured(xml, SPEC)


def test_disabled_trigger_or_task_is_not_configured() -> None:
    xml = scheduler.build_xml(SPEC)
    off = "<Enabled>false</Enabled>"
    assert not scheduler.is_configured(xml.replace("<Enabled>true</Enabled>", off, 1), SPEC)  # trigger
    task_off = xml.replace("<Enabled>true</Enabled>\n  </Settings>", off + "\n  </Settings>")
    assert not scheduler.is_configured(task_off, SPEC)


def test_garbage_xml_is_not_configured() -> None:
    assert not scheduler.is_configured("not xml at all", SPEC)


def test_ensure_creates_updates_or_leaves_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, str | None] = {"xml": None}
    installed: list[TaskSpec] = []
    monkeypatch.setattr(scheduler, "query_xml", lambda name: state["xml"])

    def fake_install(spec: TaskSpec, name: str) -> None:
        installed.append(spec)
        state["xml"] = scheduler.build_xml(spec)

    monkeypatch.setattr(scheduler, "install", fake_install)
    assert scheduler.ensure(SPEC, "T") == "created"
    assert scheduler.ensure(SPEC, "T") == "ok"
    moved = dataclasses.replace(SPEC, command=r"C:\New\dab.exe")
    assert scheduler.ensure(moved, "T") == "updated"
    assert len(installed) == 2


def test_uninstall_reports_missing_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "query_xml", lambda name: None)
    assert scheduler.uninstall("T") is False
