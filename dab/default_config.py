"""Starter config written next to dab.exe when none exists. Kept in code so the exe is the only file to ship."""
from __future__ import annotations

TEMPLATE = '''\
"""DAB (Default Apps Back) configuration. Plain Python: edit and save, no rebuild needed.

APPS maps an application's exe path to the file extensions it should open.
If an extension is listed under several apps, the last one wins (a warning goes to the log).
PROGID_OVERRIDES (optional) forces a specific ProgId for an extension; normally not needed.

Remove the leading "#" of the examples below and fix the paths to match this PC. Check them with:
    dab.exe --dry-run
"""

APPS = {
    # r"C:\\Program Files\\IrfanView\\i_view64.exe": [
    #     ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff",
    # ],
    # r"C:\\Program Files\\DAUM\\PotPlayer\\PotPlayerMini64.exe": [
    #     ".avi", ".mkv", ".mp4", ".mov", ".webm", ".wmv",
    # ],
}

PROGID_OVERRIDES: dict[str, str] = {}
'''
