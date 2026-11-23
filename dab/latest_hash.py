"""UserChoiceLatest hash (Windows 11 24H2+): vendored, unmodified pipeline from the reference implementation.

Source: TheSlopMachine/FileAssocManager ``tools/ref_hash.py`` (MIT), itself a port of cssxn/UserChoiceLatestHash (MIT).
The lookup tables live in ``uchash_tables.inc`` next to this file (see NOTICE). Excluded from linting on purpose,
so that the code stays diffable against upstream. Use ``latest_hash`` only.
"""
from __future__ import annotations

import base64
import hashlib
import re
import struct
from pathlib import Path

M32 = 0xFFFFFFFF
M64 = (1 << 64) - 1

# ---------------------------------------------------------------- shared helpers
def ascii_lower(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)

def u16(s):
    return [ord(c) for c in s]            # tests only use the BMP

def b64(low, high):
    return base64.b64encode(struct.pack("<II", low & M32, high & M32)).decode()

def _load_tables():
    src = Path(__file__).with_name("uchash_tables.inc").read_text(encoding="ascii")
    t = {}
    for m in re.finditer(r'static const char \*(\w+) =\s*((?:"[0-9a-fA-F]*"\s*)+);', src):
        t[m.group(1)] = bytes.fromhex("".join(re.findall(r'"([0-9a-fA-F]*)"', m.group(2))))
    return t


T = _load_tables()
TOKEN_REGION = T["kTokenRegionHex"]
LONG_REWIND = T["kLongRewindTableHex"]
FALLBACK = T["kFallbackTokenCodeTableHex"]
BYTE_CLASS = T["kByteClassTableHex"]
BITW = T["kTokenBitWidthTableHex"]
SHORT_REWIND = T["kShortRewindTableHex"]

SENTINEL = 0xFBFFFFFFFFFFFFFF
RA, RB, RC = 0xFE00000000000000, 0xFE00800000000000, 0xFF00000000000000
RD, RE = 0xFE007DFFFFFFFFFF, 0xFE00801F7FFFFFFF
SEEN_MOD = 0x2803
SEED_A = [0x69FB0000, 0x79F8A395, 0x3CE8EC25, 0x10FA9605]
SEED_B = [0x12CEB96D, 0x2B890000, 0x5B9F0000, 0x2C7C6901]


class Enc:
    def __init__(self):
        self.entries = [0]
        self.seen = [0] * 161
        self.last = SENTINEL
        self.repeat = 0
        self.total = 0

    @property
    def count(self):
        return len(self.entries)

    def test_seen(self, v):
        i = v % SEEN_MOD
        return (self.seen[i >> 6] >> (i & 63)) & 1 == 1

    def mark(self, v):
        i = v % SEEN_MOD
        self.seen[i >> 6] |= 1 << (i & 63)

    def push(self, v):
        self.entries.append(v & M64)

    def find_prev(self, v):
        if not self.test_seen(v) or self.count == 0:
            return None
        start = self.count - 0x400 if self.count > 0x400 else 0
        idx = self.count - 1
        while True:
            if self.entries[idx] == v:
                return self.count - idx
            if idx == start:
                break
            idx -= 1
        return None


def cls(ch):
    hi = ch >> 8
    return (BYTE_CLASS[hi] + 8) & 0xFF if hi else BYTE_CLASS[ch & 0xFF]


def at(inp, i, end):
    return inp[i] if i < end else 0


def build_token2(inp, cur, end):
    if cur >= end:
        return None
    remain = end - cur
    code = TOKEN_REGION[cls(inp[cur]) + 256]
    tl = TOKEN_REGION[code]
    if tl > remain:
        code = FALLBACK[remain]
        tl = TOKEN_REGION[code]
    base = 168 * code
    while True:
        pos = 0
        retry = False
        if tl != 0:
            probe = cur
            while probe < end:
                if inp[probe] >= (1 << BITW[base + pos]):
                    code += 1
                    base = 168 * code
                    tl = TOKEN_REGION[code]
                    if tl <= remain:
                        retry = True
                    break
                pos += 1
                probe += 1
                if pos >= tl:
                    break
        if not retry:
            break
    tok = (code & 0xFF) << 56
    shift = 56
    for i in range(tl & 0xFF):
        if cur + i >= end:
            break
        shift -= BITW[base + i]
        tok |= inp[cur + i] << shift
    return tok & M64, code & 0xFF, tl & 0xFF


def emit(st, cur, tok, kind):
    """Returns the new cursor."""
    if tok == st.last and st.repeat < 0xFF:
        st.repeat += 1
        return cur
    if st.repeat != 0:
        d = st.find_prev(st.last)
        if d is not None:
            rm1 = st.repeat - 1
            if d >= 0x800:
                packed = ((tok >> 17) | (rm1 << 48) | RA) & M64
                st.mark(packed)
                st.push(packed)
                entry = st.last
            else:
                entry = ((tok >> 27) | ((((d - 1) & 0x3FF) | (rm1 << 11)) << 37) | RB) & M64
            st.mark(entry)
            st.push(entry)
            st.last = SENTINEL
            st.repeat = 0
            return cur - (LONG_REWIND[kind] if d >= 0x800 else SHORT_REWIND[kind])
    st.mark(tok)
    st.push(tok)
    st.last = tok
    return cur


def flush(st):
    if st.repeat == 0:
        return
    if st.last == SENTINEL:
        entry = ((st.repeat << 48) | RD) & M64
    else:
        d = st.find_prev(st.last)
        if d is not None and d != 0:
            entry = ((((d - 1) & 0x3FF) | ((st.repeat - 1) << 11)) << 37 | RE) & M64
        else:
            rt = ((st.repeat << 48) | RD) & M64
            st.mark(rt)
            st.push(rt)
            entry = st.last
    st.mark(entry)
    st.push(entry)
    st.repeat = 0
    st.last = SENTINEL


MAX_CCH = 330   # the first pass Windows runs on longer inputs is not implemented


def encode(lowered):
    inp = u16(lowered)
    n = len(inp)
    if n > MAX_CCH:
        raise ValueError("input too long")
    st = Enc()
    cur = 0
    steps = 0
    while cur < n:
        tok, kind, tl = build_token2(inp, cur, n)
        st.total += tl
        cur += tl
        cur = emit(st, cur, tok, kind)
        steps += 1
        if steps > 100000 or cur < 0:
            raise RuntimeError("runaway")
    flush(st)
    st.entries[0] = (st.total | (st.count << 32)) & M64
    packed = []
    for v in st.entries:
        for sh in (0, 16, 32, 48):
            part = (v >> sh) & 0xFFFF
            if part:
                packed.append(part)
    packed.append(0)
    return packed


def lm(a, b):
    return (a * b) & M32


def mix_a(w, count, md5, seed):
    md0 = (md5[0] | 1) & M32
    md1 = ((md5[1] | 1) + 0x13DB0000) & M32
    s0, s1, s2, s3 = seed
    total = acc = 0
    mul = (md0 + s0) & M32
    for i in range(((count - 2) >> 1) + 1):
        acc = (acc + w[2 * i]) & M32
        x = acc
        t = (lm(x, mul) - lm(x >> 16, s3)) & M32
        s = (lm(t, s1) + lm(t >> 16, 0x689B6B9F)) & M32
        part1 = (lm(s, 0xEA970001) - lm(s >> 16, 0x3C101569)) & M32
        wv = (w[2 * i + 1] + part1) & M32
        t2 = (lm(wv, md1) - lm(wv >> 16, s2)) & M32
        temp = (lm(t2, 0x59C3AF2D) - lm(t2 >> 16, 0x2232E0F1)) & M32
        acc = (lm(temp >> 16, 0x35BD1EC9) + lm(temp, 0x1EC90001)) & M32
        total = (total + part1 + acc) & M32
    return acc, total


def mix_b(w, count, md5, seed):
    s0, s1, s2, s3 = seed
    md1 = (md5[1] | 1) & M32
    md0 = (md5[0] | 1) & M32
    total = acc = 0
    for i in range(((count - 2) >> 1) + 1):
        x = (w[2 * i] + acc) & M32
        t = lm(x, md0)
        a = (lm(t, 0xB1110000) - lm(t >> 16, 0x30674EEF)) & M32
        b = lm(a, s2)
        c = (b - lm(a >> 16, 0x78F7A461)) & M32
        c = (lm(c >> 16, s0) - lm(a >> 16, 0x164D0000) - lm(b, 0x46930000)) & M32
        d = (lm(c >> 16, 0x257E1D83) + lm(c, 0x1D830000)) & M32
        e = (w[2 * i + 1] + d) & M32
        f = lm(e, md1)
        g = (lm(f, 0x16F50000) - lm(f >> 16, 0x5D8BE90B)) & M32
        h = lm(g >> 16, s3)
        ii = (lm(g, 0x69010000) + h) & M32
        j = lm(ii, s1)
        k = (((0 - h) & M32) - lm(g, 0x69010000)) & M32
        k >>= 16
        m = (lm(k, 0x7C932B89) - j) & M32
        n = (lm(k, 0xF2310000) - lm(m >> 16, 0x405B6097)) & M32
        n = (n + lm(j, 0x60970000)) & M32
        acc = n
        total = (total + d + acc) & M32
    return acc, total


def hash_packed(units):
    data = b"".join(struct.pack("<H", u) for u in units)
    md5 = struct.unpack("<4I", hashlib.md5(data).digest())
    blen = len(data)
    mix = blen >> 2 if (blen & 4) == 0 else (blen >> 2) - 1
    words = []
    for i in range((len(units) + 1) // 2):
        lo = units[2 * i]
        hi = units[2 * i + 1] if 2 * i + 1 < len(units) else 0
        words.append(lo | (hi << 16))
    pa = pb = (0, 0)
    if mix >= 2:
        pa = mix_a(words, mix, md5, SEED_A)
        pb = mix_b(words, mix, md5, SEED_B)
    return b64(pa[0] ^ pb[0], pa[1] ^ pb[1])


def latest_hash(canonical):
    return hash_packed(encode(ascii_lower(canonical)))
