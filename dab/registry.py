"""All Windows registry / shell access. Nothing else in DAB touches winreg or ctypes."""
from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import uuid
import winreg
from ctypes import wintypes
from dataclasses import dataclass

from dab import hashing, latest_hash

log = logging.getLogger(__name__)

_FILEEXTS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts"
_CLASSES = r"Software\Classes"
_SHELL32 = r"C:\Windows\SysWOW64\shell32.dll"
_OPEN_COMMAND = r"shell\open\command"
_OPENWITH = "OpenWithProgids"
_APPLICATIONS = "Applications"
_VALUE_PROGID, _VALUE_HASH = "ProgId", "Hash"
_SQM = r"SOFTWARE\Microsoft\SQMClient"
_APPDEFAULTS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\SystemProtectedUserData\{sid}\AnyoneRead\AppDefaults"
# One salt per "machine class" (last character of the SQM machine id modulo 3); fixed strings inside Windows.
_LATEST_SALTS = (
    "Copyright (C) Microsoft. All rights reserved {3822B7CA-C2F4-4889-B8CC-4CE39A8FB81C}",
    "Copyright (C) Microsoft. All rights reserved {D185E0A1-E265-4724-AA21-3A17B038D72E}",
    "Copyright (C) Microsoft. All rights reserved {97B6BCF4-C367-4577-95BE-73BD3053A5E0}",
)
_CLSID_AAR = "591209C7-767B-42B2-9FBA-44EE4615F2C7"  # ApplicationAssociationRegistration
_IID_IAAR = "4E530B0A-E611-4C77-A3AC-9031D022281B"
_COINIT_APARTMENTTHREADED = 2
_CLSCTX_INPROC_SERVER = 1
_AT_FILEEXTENSION = 0
_AT_URLPROTOCOL = 1
_AL_EFFECTIVE = 1
_SHCNE_ASSOCCHANGED = 0x08000000
_MAX_WRITE_ATTEMPTS = 5
_WRITE_ACCESS = winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
_ERROR_NO_ASSOCIATION = 0x80070483
_E_ELEMENT_NOT_FOUND = 0x80070490


class RegistryError(Exception):
    """A registry or shell operation failed."""


@dataclass(slots=True, frozen=True)
class UserChoice:
    prog_id: str
    hash: str
    filetime: int


def normalize_exe(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(path)))


_CMD_QUOTED = re.compile(r'^\s*"([^"]+)"')
_CMD_EXE = re.compile(r"^\s*(.+?\.exe)\b", re.IGNORECASE)


def command_exe(command: str) -> str | None:
    """Executable named by a shell command line such as ``"C:\\x y\\a.exe" "%1"``."""
    m = _CMD_QUOTED.match(command) or _CMD_EXE.match(command)
    return normalize_exe(m.group(1)) if m else None


def _has_file_argument(command: str) -> bool:
    return "%1" in command or "%l" in command.lower()


def _hresult(hr: int) -> str:
    return f"0x{hr & 0xFFFFFFFF:08X}"


def _choice_key(ext: str, name: str) -> str:
    """``UserChoice`` or ``UserChoiceLatest`` key of an extension."""
    return rf"{_FILEEXTS}\{ext}\{name}"


def _guid(text: str) -> bytes:
    return uuid.UUID(text).bytes_le


class Registry:
    def __init__(self) -> None:
        self._sid: str | None = None
        self._experience: str | None = None
        self._machine_id: str | None = None
        self._exe_index: dict[str, list[str]] | None = None

    # --- identity constants for the hashes -----------------------------------------------------------------------

    def user_sid(self) -> str:
        if self._sid is None:
            out = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=False, timeout=30
            )
            fields = out.stdout.strip().split(",")
            if out.returncode != 0 or len(fields) < 2:
                raise RegistryError(f"whoami failed ({out.returncode}): {out.stderr.strip()}")
            self._sid = fields[1].strip('"').lower()
        return self._sid

    def machine_id(self) -> str:
        if self._machine_id is None:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SQM) as key:
                    raw = winreg.QueryValueEx(key, "MachineId")[0]
            except OSError as exc:
                raise RegistryError(f"cannot read the machine id from HKLM\\{_SQM}: {exc}") from exc
            self._machine_id = raw.strip("{}")
            if not self._machine_id:
                raise RegistryError("the machine id is empty")
        return self._machine_id

    def hash_version(self) -> int:
        """1 = Windows reads UserChoiceLatest and ignores UserChoice; 0 = classic UserChoice."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _APPDEFAULTS.format(sid=self.user_sid().upper())) as key:
                return int(winreg.QueryValueEx(key, "HashVersion")[0])
        except FileNotFoundError:
            return 0  # value or key absent: classic scheme

    def experience(self) -> str:
        if self._experience is None:
            self._experience = self._read_experience()
        return self._experience

    @staticmethod
    def _read_experience() -> str:
        needle = hashing.EXPERIENCE_MARKER.encode("utf-16-le")
        closing = "}".encode("utf-16-le")
        try:
            with open(_SHELL32, "rb") as f:
                data = f.read()
        except OSError as exc:
            log.warning("cannot read %s (%s); using the built-in experience string", _SHELL32, exc)
            return hashing.FALLBACK_EXPERIENCE
        pos = data.find(needle)
        while pos != -1 and pos % 2:
            pos = data.find(needle, pos + 1)
        if pos == -1:
            log.warning("experience string not found in shell32.dll; using the built-in one")
            return hashing.FALLBACK_EXPERIENCE
        end = data.find(closing, pos)
        while end != -1 and end % 2:
            end = data.find(closing, end + 1)
        if end == -1:
            return hashing.FALLBACK_EXPERIENCE
        return data[pos : end + 2].decode("utf-16-le")

    def latest_input(self, ext: str, prog_id: str, filetime: int) -> str:
        """The string hashed for UserChoiceLatest; field order depends on the machine class."""
        mid = self.machine_id()
        sid = self.user_sid()
        ft = filetime - filetime % 10_000  # 1 ms granularity, unlike the classic hash
        ts = f"{ft >> 32:08x}{ft & 0xFFFFFFFF:08x}"
        cls = ord(mid[-1]) % 3
        salt = _LATEST_SALTS[cls]
        if cls == 0:
            return f"{salt}{ext}{ts}{mid}{prog_id}{sid}"
        if cls == 1:
            return f"{salt}{ts}{ext}{sid}{mid}{prog_id}"
        return f"{sid}{ts}{salt}{ext}{mid}{prog_id}"

    # --- reading associations ------------------------------------------------------------------------------------

    def get_legacy_choice(self, ext: str) -> UserChoice | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _choice_key(ext, "UserChoice")) as key:
                prog_id = winreg.QueryValueEx(key, _VALUE_PROGID)[0]
                stored = winreg.QueryValueEx(key, _VALUE_HASH)[0]
                return UserChoice(prog_id, stored, winreg.QueryInfoKey(key)[2])
        except FileNotFoundError:
            return None

    def get_latest_choice(self, ext: str) -> UserChoice | None:
        base = _choice_key(ext, "UserChoiceLatest")
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as key:
                stored = winreg.QueryValueEx(key, _VALUE_HASH)[0]
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{base}\{_VALUE_PROGID}") as key:
                return UserChoice(winreg.QueryValueEx(key, _VALUE_PROGID)[0], stored, winreg.QueryInfoKey(key)[2])
        except FileNotFoundError:
            return None

    def get_user_choice(self, ext: str) -> UserChoice | None:
        """The stored choice the running Windows actually reads."""
        return self.get_latest_choice(ext) if self.hash_version() >= 1 else self.get_legacy_choice(ext)

    def effective_prog_id(self, name: str, *, protocol: bool = False) -> str | None:
        """Ask Windows itself which ProgId opens extension (or URL protocol) ``name``.

        This is the only reliable proof that a write was accepted."""
        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
        ole32.CoCreateInstance.argtypes = [
            ctypes.c_char_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p),
        ]  # fmt: skip
        ole32.CoCreateInstance.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None
        ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)  # S_FALSE when already initialised: fine
        obj = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            _guid(_CLSID_AAR), None, _CLSCTX_INPROC_SERVER, _guid(_IID_IAAR), ctypes.byref(obj)
        )
        if hr != 0:
            raise RegistryError(f"CoCreateInstance(ApplicationAssociationRegistration) failed: {_hresult(hr)}")
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        )  # fmt: skip
        query = proto(vtable[3])  # IApplicationAssociationRegistration::QueryCurrentDefault
        out = ctypes.c_void_p()
        hr = query(obj, name, _AT_URLPROTOCOL if protocol else _AT_FILEEXTENSION, _AL_EFFECTIVE, ctypes.byref(out))
        # The COM object is intentionally not released: one short-lived process, a few queries.
        if hr & 0xFFFFFFFF in (_ERROR_NO_ASSOCIATION, _E_ELEMENT_NOT_FOUND):
            return None
        if hr != 0:
            raise RegistryError(f"QueryCurrentDefault({name}) failed: {_hresult(hr)}")
        value = ctypes.wstring_at(out.value)
        ole32.CoTaskMemFree(out)
        return value

    def prog_id_exe(self, prog_id: str) -> str | None:
        """Executable of a ProgId's open command, or None (e.g. for packaged apps)."""
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\{_OPEN_COMMAND}") as key:
                return command_exe(winreg.QueryValueEx(key, "")[0])
        except FileNotFoundError:
            return None

    def openwith_progids(self, ext: str) -> list[str]:
        found: list[str] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, ext) as key:
                try:
                    found.append(winreg.QueryValueEx(key, "")[0])
                except FileNotFoundError:
                    pass  # extension has no default ProgId
                try:
                    with winreg.OpenKey(key, _OPENWITH) as ow:
                        for i in range(winreg.QueryInfoKey(ow)[1]):
                            found.append(winreg.EnumValue(ow, i)[0])
                except FileNotFoundError:
                    pass  # no OpenWithProgids list
        except FileNotFoundError:
            pass  # unknown extension
        return [p for p in found if p]

    def exe_prog_ids(self, exe: str) -> list[str]:
        """All top-level ProgIds whose open command runs ``exe`` and passes the file (%1)."""
        if self._exe_index is None:
            self._exe_index = self._build_exe_index()
        return list(self._exe_index.get(normalize_exe(exe), []))

    @staticmethod
    def _build_exe_index() -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                name = winreg.EnumKey(root, i)
                if name.startswith((".", "{")) or name in {"CLSID", _APPLICATIONS}:
                    continue
                try:
                    with winreg.OpenKey(root, rf"{name}\{_OPEN_COMMAND}") as key:
                        command = winreg.QueryValueEx(key, "")[0]
                except (FileNotFoundError, PermissionError):
                    continue  # most keys are not ProgIds with an open command
                exe = command_exe(command) if _has_file_argument(command) else None
                if exe:
                    index.setdefault(exe, []).append(name)
        for names in index.values():
            names.sort(key=str.lower)
        return index

    def application_prog_id(self, exe: str) -> str | None:
        """``Applications\\<exe name>`` ProgId that Windows creates for 'Open with' entries."""
        name = rf"{_APPLICATIONS}\{os.path.basename(exe)}"
        if self.prog_id_exe(name) == normalize_exe(exe):
            return name
        return None

    # --- writing -------------------------------------------------------------------------------------------------

    def ensure_prog_id(self, prog_id: str, exe: str, ext: str) -> bool:
        """Create (or repair) a per-user ProgId that opens files with ``exe``. Returns True if anything changed."""
        want_cmd = f'"{exe}" "%1"'
        base = rf"{_CLASSES}\{prog_id}"
        changed = False
        for sub, value in (("", prog_id), ("DefaultIcon", f'"{exe}",0'), (_OPEN_COMMAND, want_cmd)):
            path = rf"{base}\{sub}" if sub else base
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, _WRITE_ACCESS) as k:
                try:
                    current = winreg.QueryValueEx(k, "")[0]
                except FileNotFoundError:
                    current = None
                if current != value:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, value)
                    changed = True
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, rf"{_CLASSES}\{ext}\{_OPENWITH}", 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.SetValueEx(k, prog_id, 0, winreg.REG_NONE, b"")
        self._exe_index = None
        return changed

    @staticmethod
    def _open_for_write(path: str) -> winreg.HKEYType:
        try:
            try:
                return winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, path, 0, _WRITE_ACCESS)
            except FileNotFoundError:
                return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, _WRITE_ACCESS)
            except PermissionError:
                log.debug("%s is write-protected, recreating it", path)
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
                return winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, _WRITE_ACCESS)
        except OSError as exc:
            raise RegistryError(f"cannot open {path}: {exc} (protected by Windows?)") from exc

    def _write_latest(self, ext: str, prog_id: str) -> None:
        base = _choice_key(ext, "UserChoiceLatest")
        # The hash covers the timestamp of the ProgId subkey, so that key is written first and not touched again.
        with self._open_for_write(rf"{base}\{_VALUE_PROGID}") as sub:
            winreg.SetValueEx(sub, _VALUE_PROGID, 0, winreg.REG_SZ, prog_id)
            filetime = winreg.QueryInfoKey(sub)[2]
        new_hash = latest_hash.latest_hash(self.latest_input(ext, prog_id, filetime))
        with self._open_for_write(base) as key:
            winreg.SetValueEx(key, _VALUE_HASH, 0, winreg.REG_SZ, new_hash)
            winreg.SetValueEx(key, _VALUE_PROGID, 0, winreg.REG_SZ, prog_id)

    def _write_legacy(self, ext: str, prog_id: str) -> None:
        with self._open_for_write(_choice_key(ext, "UserChoice")) as key:
            for _ in range(_MAX_WRITE_ATTEMPTS):
                winreg.SetValueEx(key, _VALUE_PROGID, 0, winreg.REG_SZ, prog_id)
                filetime = winreg.QueryInfoKey(key)[2]
                new_hash = hashing.user_choice_hash(ext, self.user_sid(), prog_id, filetime, self.experience())
                winreg.SetValueEx(key, _VALUE_HASH, 0, winreg.REG_SZ, new_hash)
                # The classic hash covers the key's last-write minute, which our own writes just moved.
                if hashing.same_minute(filetime, winreg.QueryInfoKey(key)[2]):
                    return
        raise RegistryError(f"could not write a stable UserChoice for {ext}")

    def set_user_choice(self, ext: str, prog_id: str) -> None:
        """Write the choice in the scheme(s) this Windows reads; the caller verifies with effective_prog_id."""
        if self.hash_version() >= 1:
            self._write_latest(ext, prog_id)
            try:
                self._write_legacy(ext, prog_id)
            except RegistryError as exc:
                log.debug("%s: classic UserChoice not written (%s); UserChoiceLatest is authoritative", ext, exc)
        else:
            self._write_legacy(ext, prog_id)

    def notify_assoc_changed(self) -> None:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SHChangeNotify.argtypes = [ctypes.c_long, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p]
        shell32.SHChangeNotify.restype = None
        shell32.SHChangeNotify(_SHCNE_ASSOCCHANGED, 0, None, None)
