"""Project identity, read straight from pyproject.toml so it is written down once and never goes stale."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

# Installed package metadata is only a snapshot taken at ``pip install`` time and lags behind later edits of the
# version. So the file itself is read: next to the package from source, or in the bundle root inside the exe
# (``build.cmd`` adds it with --add-data).
_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
_PROJECT = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

VERSION: str = _PROJECT["version"]
NAME: str = _PROJECT["name"]  # "dab": program, logger, file names, ``python -m`` target
DESCRIPTION: str = _PROJECT["description"]
BRAND = NAME.upper()  # how the name appears in Windows (task name, ProgId prefix)
