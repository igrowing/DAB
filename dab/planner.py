"""Decide, per extension, what has to change. Pure logic over a ``Registry``-like object (faked in tests)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dab import meta
from dab.registry import normalize_exe

if TYPE_CHECKING:
    from dab.config import Config
    from dab.registry import Registry

# Windows' User Choice Protection Driver (UCPD) blocks other processes from writing these.
PROTECTED = frozenset({".htm", ".html", ".pdf"})


@dataclass(slots=True, frozen=True)
class Action:
    ext: str
    exe: str
    current: str | None
    target: str
    create_prog_id: bool
    needs_change: bool
    note: str


def choose_prog_id(reg: Registry, ext: str, exe: str, override: str | None) -> tuple[str, bool, str]:
    """Return (ProgId, must_create, why)."""
    if override:
        return override, False, "override from config"
    previous = reg.get_legacy_choice(ext)
    if previous and reg.prog_id_exe(previous.prog_id) == normalize_exe(exe):
        return previous.prog_id, False, "ProgId you used before for this extension"
    candidates = reg.exe_prog_ids(exe)
    suffix = "." + ext[1:]
    for prog_id in candidates:
        if prog_id.lower().endswith(suffix):
            return prog_id, False, "existing ProgId of the app for this extension"
    registered = {p.lower() for p in reg.openwith_progids(ext)}
    for prog_id in candidates:
        if prog_id.lower() in registered:
            return prog_id, False, "existing ProgId of the app, already offered for this extension"
    generic = reg.application_prog_id(exe)
    if generic:
        return generic, False, "Windows' generic 'Applications' ProgId of the app"
    stem = os.path.splitext(os.path.basename(exe))[0]
    return f"{meta.BRAND}.{stem}", True, f"new per-user ProgId created by {meta.BRAND}"


def plan(cfg: Config, reg: Registry) -> list[Action]:
    actions: list[Action] = []
    for ext in sorted(cfg.wanted):
        exe = cfg.wanted[ext]
        choice = reg.get_user_choice(ext)
        current = choice.prog_id if choice else None
        if current and reg.prog_id_exe(current) == normalize_exe(exe):
            actions.append(Action(ext, exe, current, current, create_prog_id=False, needs_change=False,
                                  note="already opens with this app"))  # fmt: skip
            continue
        target, create, why = choose_prog_id(reg, ext, exe, cfg.overrides.get(ext))
        note = why + (" (Windows protects this type; the write will probably be refused)" if ext in PROTECTED else "")
        actions.append(Action(ext, exe, current, target, create_prog_id=create, needs_change=True, note=note))
    return actions
