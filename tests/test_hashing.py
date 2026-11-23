from __future__ import annotations

import winreg

import pytest

from dab import hashing, latest_hash
from dab.registry import Registry


def test_hex_datetime_truncates_to_the_minute() -> None:
    ft = 133966992675003928
    assert hashing.hex_datetime(ft) == hashing.hex_datetime(ft - ft % 600_000_000 + 599_999_999)
    assert hashing.hex_datetime(ft) != hashing.hex_datetime(ft + 600_000_000)
    assert len(hashing.hex_datetime(ft)) == 16


def test_same_minute() -> None:
    minute = 600_000_000
    assert hashing.same_minute(10 * minute, 10 * minute + minute - 1)
    assert not hashing.same_minute(10 * minute, 11 * minute)


def test_hash_depends_on_every_input() -> None:
    args = (".txt", "s-1-5-21-1", "Some.Prog", 133966992675003928, hashing.FALLBACK_EXPERIENCE)
    base = hashing.user_choice_hash(*args)
    assert len(base) == 12  # 8 bytes in base64
    assert hashing.user_choice_hash(".md", *args[1:]) != base
    assert hashing.user_choice_hash(args[0], "s-1-5-21-2", *args[2:]) != base
    assert hashing.user_choice_hash(*args[:2], "Other.Prog", *args[3:]) != base
    assert hashing.user_choice_hash(*args[:3], args[3] + 600_000_000, args[4]) != base
    assert hashing.user_choice_hash(*args) == base


def test_matches_every_userchoice_hash_stored_by_windows() -> None:
    """Windows wrote these hashes itself, so reproducing them proves the algorithm on this machine."""
    reg = Registry()
    sid, experience = reg.user_sid(), reg.experience()
    checked = 0
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts") as fe:
        for i in range(winreg.QueryInfoKey(fe)[0]):
            ext = winreg.EnumKey(fe, i)
            choice = reg.get_legacy_choice(ext)
            if choice is None:
                continue
            got = hashing.user_choice_hash(ext, sid, choice.prog_id, choice.filetime, experience)
            assert got == choice.hash, ext
            checked += 1
    if not checked:
        pytest.skip("no UserChoice entries on this machine")


def test_matches_every_userchoicelatest_hash_stored_by_windows() -> None:
    reg = Registry()
    checked = 0
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts") as fe:
        for i in range(winreg.QueryInfoKey(fe)[0]):
            ext = winreg.EnumKey(fe, i)
            choice = reg.get_latest_choice(ext)
            if choice is None:
                continue
            got = latest_hash.latest_hash(reg.latest_input(ext, choice.prog_id, choice.filetime))
            assert got == choice.hash, ext
            checked += 1
    if not checked:
        pytest.skip("no UserChoiceLatest entries on this machine")


def test_latest_hash_known_answer() -> None:
    kat = (
        "copyright (c) microsoft. all rights reserved {3822b7ca-c2f4-4889-b8cc-4ce39a8fb81c}"
        ".pdd01dcb06ea49f32a0b4deb148-0249-44c4-a8d3-5409e822c599msedgepdf"
        "s-1-5-21-673349297-2269585490-1023937497-500"
    )
    assert latest_hash.latest_hash(kat) == "JOBZ2dl4dKM="
