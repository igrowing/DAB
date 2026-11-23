"""Command line: ``dab --list | --dry-run | --apply | --uninstall [--config FILE]``."""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from dab import config, meta, planner, scheduler
from dab.registry import Registry, RegistryError

log = logging.getLogger(meta.NAME)
FROZEN = getattr(sys, "frozen", False)  # True inside the PyInstaller executable
# Config and log live next to dab.exe, or in the project folder when run from source.
_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = _ROOT / f"{meta.NAME}_config.py"
DEFAULT_LOG = _ROOT / f"{meta.NAME}.log"
_APPLY, _CONFIG, _LOG = "--apply", "--config", "--log"  # reused to build the scheduled task's arguments


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=meta.NAME, description=meta.DESCRIPTION)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="show the current association of every configured extension")
    mode.add_argument("--dry-run", action="store_true", help=f"show what {_APPLY} would change, change nothing")
    mode.add_argument(_APPLY, action="store_true", help="restore the configured associations (and keep the "
                      "delayed-logon scheduled task registered)")  # fmt: skip
    mode.add_argument("--uninstall", action="store_true", help="remove the scheduled task and exit")
    p.add_argument(_CONFIG, type=Path, default=DEFAULT_CONFIG, help=f"config file (default: {DEFAULT_CONFIG.name})")
    p.add_argument(_LOG, type=Path, default=DEFAULT_LOG, help=f"log file written by {_APPLY}")
    return p


def _do_list(cfg: config.Config, reg: Registry) -> int:
    for a in planner.plan(cfg, reg):
        state = "ok    " if not a.needs_change else "DIFFER"
        print(f"{state} {a.ext:10} now={a.current or '-':40} wanted={Path(a.exe).name}")
    return 0


def _do_dry_run(cfg: config.Config, reg: Registry) -> int:
    todo = [a for a in planner.plan(cfg, reg) if a.needs_change]
    for a in todo:
        print(f"would set {a.ext:10} {a.current or '-'}  ->  {a.target}   [{a.note}]")
    print(f"{len(todo)} of {len(cfg.wanted)} extensions would change")
    return 0


def task_spec(args: argparse.Namespace, sid: str) -> scheduler.TaskSpec:
    """What the scheduled task has to run: this very executable (or ``python -m dab`` from source)."""
    parts = [_APPLY]
    if args.config.resolve() != DEFAULT_CONFIG.resolve():
        parts += [_CONFIG, str(args.config.resolve())]
    if args.log.resolve() != DEFAULT_LOG.resolve():
        parts += [_LOG, str(args.log.resolve())]
    if not FROZEN:
        parts = ["-m", meta.NAME, *parts]
    return scheduler.TaskSpec(
        command=str(Path(sys.executable).resolve()),
        arguments=subprocess.list2cmdline(parts),
        working_dir=str(_ROOT),
        sid=sid,
    )


def _ensure_task(args: argparse.Namespace, reg: Registry) -> None:
    """Register the delayed-logon task when it is missing or stale. Never fatal: the apply still runs."""
    try:
        outcome = scheduler.ensure(task_spec(args, reg.user_sid().upper()))
    except (scheduler.SchedulerError, RegistryError) as exc:
        log.warning("could not check or register the scheduled task: %s", exc)
        return
    if outcome == "ok":
        log.debug("scheduled task '%s' is already set up", scheduler.TASK_NAME)
    else:
        log.info("scheduled task '%s' %s: runs %s %s after you sign in", scheduler.TASK_NAME, outcome,
                 _APPLY, scheduler.DEFAULT_DELAY)  # fmt: skip


def _do_apply(cfg: config.Config, reg: Registry) -> int:
    failures = changed = 0
    for a in planner.plan(cfg, reg):
        if not a.needs_change:
            log.debug("%s already ok (%s)", a.ext, a.current)
            continue
        try:
            if a.create_prog_id:
                reg.ensure_prog_id(a.target, a.exe, a.ext)
            reg.set_user_choice(a.ext, a.target)
            effective = reg.effective_prog_id(a.ext)
            if (effective or "").lower() != a.target.lower():
                raise RegistryError(f"Windows did not accept the change for {a.ext}: it still uses {effective}")
        except RegistryError as exc:
            failures += 1
            log.error("%s: %s", a.ext, exc)
            continue
        changed += 1
        log.info("%s: %s -> %s", a.ext, a.current or "-", a.target)
    if changed:
        reg.notify_assoc_changed()
    log.info("done: %d changed, %d failed, %d already fine", changed, failures, len(cfg.wanted) - changed - failures)
    return 1 if failures else 0


def _do_uninstall() -> int:
    try:
        removed = scheduler.uninstall()
    except scheduler.SchedulerError as exc:
        print(f"cannot remove the scheduled task: {exc}", file=sys.stderr)
        return 1
    print(f"scheduled task '{scheduler.TASK_NAME}' removed" if removed else
          f"scheduled task '{scheduler.TASK_NAME}' was not installed")  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = _parser()
    print(f"{meta.NAME.upper()} {meta.VERSION}")
    if not (sys.argv[1:] if argv is None else argv):
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if args.uninstall:
        return _do_uninstall()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.apply:
        handlers.append(logging.FileHandler(args.log, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    try:
        # Only the default location is created on demand; a mistyped --config must stay an error.
        if args.config.resolve() == DEFAULT_CONFIG.resolve() and config.create_starter(args.config):
            log.warning("no config found: created a starter at %s. Add your apps there and run again.", args.config)
            return 0
        cfg = config.load(args.config)
    except config.EmptyConfigError as exc:
        log.warning("%s", exc)  # a fresh starter has no apps: say so, but it is not a failure
        return 0
    except config.ConfigError as exc:
        log.error("config error: %s", exc)
        return 2
    reg = Registry()
    try:
        if args.list:
            return _do_list(cfg, reg)
        if args.dry_run:
            return _do_dry_run(cfg, reg)
        _ensure_task(args, reg)
        return _do_apply(cfg, reg)
    except RegistryError as exc:
        log.error("%s", exc)
        return 1
