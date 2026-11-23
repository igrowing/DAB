"""Windows ``UserChoice`` hash.

Windows ignores a ``UserChoice`` key whose ``Hash`` value does not match the extension, user SID, ProgId and the
key's last-write time (truncated to the minute). This is a Python port of the algorithm in PS-SFTA
(Copyright 2022 Danysys, MIT License), checked against every UserChoice entry of a Windows 11 26200 machine.
"""
from __future__ import annotations

import base64
import hashlib
import struct

_M = 0xFFFFFFFF
_MINUTE = 600_000_000  # 100 ns units

EXPERIENCE_MARKER = "User Choice set via Windows User Experience"
# Used when the string cannot be found in shell32.dll (PS-SFTA does the same).
FALLBACK_EXPERIENCE = "User Choice set via Windows User Experience {D18B6DD5-6124-4341-9318-804003BAFA0B}"


def _sr(x: int, n: int) -> int:
    return (x & _M) >> n


def _mix(base: str) -> str:
    data = base.encode("utf-16-le") + b"\0\0"
    md5 = hashlib.md5(data).digest()  # noqa: S324
    length_base = len(data)
    length = (1 if (length_base & 4) == 0 else 0) + (length_base >> 2) - 1
    assert length > 1, "base string too short"
    m1 = struct.unpack_from("<I", md5, 0)[0]
    m2 = struct.unpack_from("<I", md5, 4)[0]
    rounds = ((length - 2) >> 1) + 1

    def lng(i: int) -> int:
        return struct.unpack_from("<I", data, i)[0]

    md51 = ((m1 | 1) + 0x69FB0000) & _M
    md52 = ((m2 | 1) + 0x13DB0000) & _M
    pdata = cache = out1 = out2 = 0
    for _ in range(rounds):
        r0 = (lng(pdata) + out1) & _M
        r1_0 = lng(pdata + 4)
        pdata += 8
        r2_0 = (r0 * md51 - 0x10FA9605 * _sr(r0, 16)) & _M
        r2_1 = (0x79F8A395 * r2_0 + 0x689B6B9F * _sr(r2_0, 16)) & _M
        r3 = (0xEA970001 * r2_1 - 0x3C101569 * _sr(r2_1, 16)) & _M
        r4_0 = (r3 + r1_0) & _M
        r5_0 = (cache + r3) & _M
        r6_0 = (r4_0 * md52 - 0x3CE8EC25 * _sr(r4_0, 16)) & _M
        r6_1 = (0x59C3AF2D * r6_0 - 0x2232E0F1 * _sr(r6_0, 16)) & _M
        out1 = (0x1EC90001 * r6_1 + 0x35BD1EC9 * _sr(r6_1, 16)) & _M
        out2 = (r5_0 + out1) & _M
        cache = out2
    first = (out1, out2)

    md51 = (m1 | 1) & _M
    md52 = (m2 | 1) & _M
    pdata = cache = out1 = out2 = 0
    for _ in range(rounds):
        r0 = (lng(pdata) + out1) & _M
        pdata += 8
        r1_0 = (r0 * md51) & _M
        r1_1 = (0xB1110000 * r1_0 - 0x30674EEF * _sr(r1_0, 16)) & _M
        r2_0 = (0x5B9F0000 * r1_1 - 0x78F7A461 * _sr(r1_1, 16)) & _M
        r2_1 = (0x12CEB96D * _sr(r2_0, 16) - 0x46930000 * r2_0) & _M
        r3 = (0x1D830000 * r2_1 + 0x257E1D83 * _sr(r2_1, 16)) & _M
        r4_0 = (md52 * (r3 + lng(pdata - 4))) & _M
        r4_1 = (0x16F50000 * r4_0 - 0x5D8BE90B * _sr(r4_0, 16)) & _M
        r5_0 = (0x96FF0000 * r4_1 - 0x2C7C6901 * _sr(r4_1, 16)) & _M
        r5_1 = (0x2B890000 * r5_0 + 0x7C932B89 * _sr(r5_0, 16)) & _M
        out1 = (0x9F690000 * r5_1 - 0x405B6097 * _sr(r5_1, 16)) & _M
        out2 = (out1 + cache + r3) & _M
        cache = out2

    packed = struct.pack("<II", out1 ^ first[0], out2 ^ first[1])
    return base64.b64encode(packed).decode("ascii")


def hex_datetime(filetime: int) -> str:
    """Key last-write FILETIME truncated to the minute, as the 16-digit hex Windows uses."""
    ft = filetime - filetime % _MINUTE
    return f"{ft >> 32:08x}{ft & _M:08x}"


def same_minute(filetime_a: int, filetime_b: int) -> bool:
    return filetime_a // _MINUTE == filetime_b // _MINUTE


def user_choice_hash(ext: str, sid: str, prog_id: str, filetime: int, experience: str) -> str:
    base = f"{ext}{sid}{prog_id}{hex_datetime(filetime)}{experience}".lower()
    return _mix(base)
