"""Entry point for the PyInstaller build (``build.cmd``); from source use ``python -m dab``."""
import sys

from dab.cli import main

sys.exit(main())
