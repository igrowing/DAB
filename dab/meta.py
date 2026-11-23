"""Project identity, read from pyproject.toml (through the installed metadata) so it is written down once."""
from __future__ import annotations

from importlib.metadata import metadata

# The distribution is named like its package; ``build.cmd`` ships the metadata with ``--copy-metadata``.
_META = metadata(__package__)

VERSION: str = _META["Version"]
NAME: str = _META["Name"]  # "dab": program, logger, file names, ``python -m`` target
DESCRIPTION: str = _META["Summary"]
BRAND = NAME.upper()  # how the name appears in Windows (task name, ProgId prefix)
