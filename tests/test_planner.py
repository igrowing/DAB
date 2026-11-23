from __future__ import annotations

from dab import planner
from dab.config import Config
from dab.registry import UserChoice, command_exe, normalize_exe

IRFAN = r"C:\Program Files\IrfanView\i_view64.exe"
XMPLAY = r"C:\portable\xmplay\xmplay.exe"


class FakeRegistry:
    def __init__(self) -> None:
        self.choices: dict[str, str] = {}
        self.legacy: dict[str, str] = {}
        self.prog_exes: dict[str, str] = {}
        self.openwith: dict[str, list[str]] = {}
        self.by_exe: dict[str, list[str]] = {}
        self.applications: dict[str, str] = {}

    def get_user_choice(self, ext: str) -> UserChoice | None:
        return UserChoice(self.choices[ext], "h", 0) if ext in self.choices else None

    def get_legacy_choice(self, ext: str) -> UserChoice | None:
        return UserChoice(self.legacy[ext], "h", 0) if ext in self.legacy else None

    def prog_id_exe(self, prog_id: str) -> str | None:
        return self.prog_exes.get(prog_id)

    def openwith_progids(self, ext: str) -> list[str]:
        return self.openwith.get(ext, [])

    def exe_prog_ids(self, exe: str) -> list[str]:
        return self.by_exe.get(normalize_exe(exe), [])

    def application_prog_id(self, exe: str) -> str | None:
        return self.applications.get(normalize_exe(exe))


def _cfg(**wanted: str) -> Config:
    return Config(wanted={"." + k: v for k, v in wanted.items()}, overrides={})


def test_command_exe_parsing() -> None:
    assert command_exe('"C:\\A B\\x.exe" "%1"') == normalize_exe("C:\\A B\\x.exe")
    assert command_exe('C:\\A B\\x.EXE --open "%1"') == normalize_exe("C:\\A B\\x.EXE")
    assert command_exe("nothing useful") is None


def test_already_correct_is_left_alone() -> None:
    reg = FakeRegistry()
    reg.choices[".jpg"] = "IrfanView.jpg"
    reg.prog_exes["IrfanView.jpg"] = normalize_exe(IRFAN)
    [a] = planner.plan(_cfg(jpg=IRFAN), reg)  # type: ignore[arg-type]
    assert not a.needs_change


def test_prefers_prog_id_matching_the_extension() -> None:
    reg = FakeRegistry()
    reg.choices[".jpg"] = "AppXsomething"
    reg.by_exe[normalize_exe(IRFAN)] = ["IrfanView.bmp", "IrfanView.jpg"]
    [a] = planner.plan(_cfg(jpg=IRFAN), reg)  # type: ignore[arg-type]
    assert (a.needs_change, a.target, a.create_prog_id) == (True, "IrfanView.jpg", False)


def test_reuses_the_prog_id_the_user_had_before() -> None:
    reg = FakeRegistry()
    reg.choices[".jfif"] = "AppXphotos"
    reg.legacy[".jfif"] = "IrfanView.jpg"
    reg.prog_exes["IrfanView.jpg"] = normalize_exe(IRFAN)
    reg.applications[normalize_exe(IRFAN)] = r"Applications\i_view64.exe"
    [a] = planner.plan(_cfg(jfif=IRFAN), reg)  # type: ignore[arg-type]
    assert (a.needs_change, a.target) == (True, "IrfanView.jpg")


def test_falls_back_to_openwith_then_applications_then_creates() -> None:
    reg = FakeRegistry()
    reg.by_exe[normalize_exe(IRFAN)] = ["IrfanView.bmp"]
    reg.openwith[".png"] = ["IrfanView.bmp"]
    reg.applications[normalize_exe(XMPLAY)] = r"Applications\xmplay.exe"
    actions = {a.ext: a for a in planner.plan(_cfg(png=IRFAN, mp3=XMPLAY, webp=IRFAN), reg)}  # type: ignore[arg-type]
    assert actions[".png"].target == "IrfanView.bmp"
    assert actions[".mp3"].target == r"Applications\xmplay.exe"
    assert actions[".webp"].target == "IrfanView.bmp" or actions[".webp"].create_prog_id
    reg.by_exe.clear()
    [a] = planner.plan(_cfg(webp=IRFAN), reg)  # type: ignore[arg-type]
    assert (a.target, a.create_prog_id) == ("DAB.i_view64", True)


def test_override_wins_and_protected_types_are_flagged() -> None:
    reg = FakeRegistry()
    cfg = Config(wanted={".html": IRFAN}, overrides={".html": "My.Html"})
    [a] = planner.plan(cfg, reg)  # type: ignore[arg-type]
    assert a.target == "My.Html"
    assert "protects" in a.note
