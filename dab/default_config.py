"""Starter config written next to dab.exe when none exists. Kept in code so the exe is the only file to ship."""
from __future__ import annotations

# Raw string: the Windows paths below contain backslashes (\x, \p would be invalid escapes otherwise).
TEMPLATE = r'''"""DAB (Default Apps Back) configuration. Plain Python: edit and save, no rebuild needed.

APPS maps an application's exe path to the file extensions it should open.
If an extension is listed under several apps, the last one wins (a warning goes to the log).
PROGID_OVERRIDES (optional) forces a specific ProgId for an extension; normally not needed.

Remove the leading "#" of the examples below and fix the paths to match this PC. Check them with:
    dab.exe --dry-run
"""

APPS = {
    # r"C:\Program Files\IrfanView\i_view64.exe": [
    #     ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
    # ],
    # r"C:\portable\xmplay\xmplay.exe": [
    #     ".mp3", ".flac", ".ogg", ".wav", ".m4a", ".wma", ".aac", ".opus",
    # ],
    # r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe": [
    #     ".3gp", ".asf", ".avi", ".divx", ".flv", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg",
    #     ".mts", ".ogv", ".rmvb", ".vob", ".webm", ".wmv",
    # ],
    # r"C:\Program Files\Google\Chrome\Application\chrome.exe": [
    #     ".htm", ".html", ".xhtml", ".shtml", ".xml", ".svg", ".webp",
    # ],
    # r"C:\Program Files (x86)\Foxit Software\Foxit PDF Reader\FoxitPDFReader.exe": [
    #     ".pdf",
    # ],
}

PROGID_OVERRIDES: dict[str, str] = {}
'''
