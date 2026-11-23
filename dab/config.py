"""Loading and validating the user's pure-Python config file."""
from __future__ import annotations

import logging
import re
import runpy
from dataclasses import dataclass
from pathlib import Path

from dab import default_config

log =logging.getLogger(__name__)

_EXT_RE = re.compile(r"^\.[a-z0-9_+\-]+$")


class ConfigError(Exception):
    """The config file is missing or invalid."""


class EmptyConfigError(ConfigError):
    """The config is valid but lists no applications yet (e.g. the untouched starter): nothing to do, not a fault."""


@dataclass(slots=True, frozen=True)
class Config:
    # extension (lowercase, with dot) -> application exe path
    wanted: dict[str, str]
    # extension -> ProgId forced by the user
    overrides: dict[str, str]


def normalize_ext(ext: str) -> str:
    ext = ext.strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    if not _EXT_RE.match(ext):
        raise ConfigError(f"invalid extension {ext!r}")
    return ext


def create_starter(path: Path) -> bool:
    """Write the starter config unless a file is already there. Returns True if it was created."""
    try:
        with path.open("x", encoding="utf-8") as f:  # "x": never overwrite a user's file
            f.write(default_config.TEMPLATE)
    except FileExistsError:
        return False
    except OSError as exc:
        raise ConfigError(f"cannot create the starter config {path}: {exc}") from exc
    return True


def load(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        ns = runpy.run_path(str(path))
    except Exception as exc:  # noqa: BLE001  # user code of any kind: report it as a config problem, with traceback
        raise ConfigError(f"cannot execute {path}: {exc!r}") from exc
    apps = ns.get("APPS")
    if not isinstance(apps, dict):
        raise ConfigError(f"{path}: APPS is missing; add your applications as {{exe path: [extensions]}}")
    if not apps:
        raise EmptyConfigError(f"{path}: no applications in APPS yet; add them as {{exe path: [extensions]}}")

    wanted: dict[str, str] = {}
    for exe, exts in apps.items():
        if not isinstance(exe, str) or not isinstance(exts, (list, tuple, set)):
            raise ConfigError(f"APPS entry {exe!r}: key must be a str path and value a list of extensions")
        if not Path(exe).is_file():
            raise ConfigError(f"application not found: {exe}")
        for raw in exts:
            ext = normalize_ext(raw)
            if ext in wanted and wanted[ext] != exe:
                log.warning("extension %s is assigned to both %s and %s; the last one wins (%s)",
                            ext, wanted[ext], exe, exe)  # fmt: skip
            wanted[ext] = exe

    overrides = {normalize_ext(k): v for k, v in (ns.get("PROGID_OVERRIDES") or {}).items()}
    unknown = sorted(set(overrides) - set(wanted))
    if unknown:
        raise ConfigError(f"PROGID_OVERRIDES lists extensions that are not in APPS: {unknown}")
    return Config(wanted=wanted, overrides=overrides)
