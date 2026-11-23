"""Task Scheduler registration through schtasks.exe (no extra dependencies, no admin rights needed).

The task fires a short delay after the user signs in, not at machine boot: associations live in HKCU, which a
boot-time task (no user session yet) could not write.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from xml.sax.saxutils import escape

from dab import meta

log = logging.getLogger(__name__)

TASK_NAME = meta.BRAND
DEFAULT_DELAY = "PT1M"  # ISO 8601 duration: one minute after logon
_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")


class SchedulerError(Exception):
    """schtasks.exe failed."""


@dataclass(slots=True, frozen=True)
class TaskSpec:
    command: str
    arguments: str
    working_dir: str
    sid: str
    delay: str = DEFAULT_DELAY


def build_xml(spec: TaskSpec) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{escape(meta.DESCRIPTION)}</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{escape(spec.sid)}</UserId>
      <Delay>{escape(spec.delay)}</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(spec.sid)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(spec.command)}</Command>
      <Arguments>{escape(spec.arguments)}</Arguments>
      <WorkingDirectory>{escape(spec.working_dir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _run(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    schtasks = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "schtasks.exe")
    try:
        return subprocess.run([schtasks, *args], capture_output=True, check=False, timeout=60)  # noqa: S603  # fixed system binary
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SchedulerError(f"cannot run schtasks: {exc}") from exc


def _text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("oem", errors="replace")


def query_xml(name: str = TASK_NAME) -> str | None:
    """The task's XML definition, or None when no such task exists."""
    done = _run(["/Query", "/TN", name, "/XML"])
    if done.returncode != 0:
        return None
    return _text(done.stdout)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def is_configured(xml: str, spec: TaskSpec) -> bool:
    """True when the task exists, is enabled, has a delayed logon trigger and runs exactly ``spec``."""
    try:
        root = ET.fromstring(_XML_DECL.sub("", xml, count=1))  # noqa: S314  # our own task, produced by schtasks
    except ET.ParseError:
        return False

    def text(*names: str) -> str:
        return (root.findtext("./" + "/".join(_NS + n for n in names)) or "").strip()

    trigger = root.find(f"./{_NS}Triggers/{_NS}LogonTrigger")
    if trigger is None or (trigger.findtext(f"{_NS}Enabled") or "true").strip().lower() == "false":
        return False
    if not (trigger.findtext(f"{_NS}Delay") or "").strip():
        return False
    if text("Settings", "Enabled").lower() == "false":
        return False
    return (
        _norm(text("Actions", "Exec", "Command")) == _norm(spec.command)
        and text("Actions", "Exec", "Arguments") == spec.arguments
        and _norm(text("Actions", "Exec", "WorkingDirectory")) == _norm(spec.working_dir)
    )


def install(spec: TaskSpec, name: str = TASK_NAME) -> None:
    handle, path = tempfile.mkstemp(suffix=".xml", prefix="dab_task_")
    try:
        with os.fdopen(handle, "w", encoding="utf-16") as f:
            f.write(build_xml(spec))
        done = _run(["/Create", "/TN", name, "/XML", path, "/F"])
    finally:
        os.remove(path)
    if done.returncode != 0:
        raise SchedulerError(f"schtasks /Create failed ({done.returncode}): {_text(done.stderr).strip()}")


def ensure(spec: TaskSpec, name: str = TASK_NAME) -> str:
    """Make sure the delayed-logon task exists and matches ``spec``. Returns 'ok', 'created' or 'updated'."""
    xml = query_xml(name)
    if xml is not None and is_configured(xml, spec):
        return "ok"
    install(spec, name)
    return "created" if xml is None else "updated"


def uninstall(name: str = TASK_NAME) -> bool:
    """Delete the task. Returns False when there was none."""
    if query_xml(name) is None:
        return False
    done = _run(["/Delete", "/TN", name, "/F"])
    if done.returncode != 0:
        raise SchedulerError(f"schtasks /Delete failed ({done.returncode}): {_text(done.stderr).strip()}")
    return True
