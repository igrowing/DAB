# DAB - Default Apps Back

Windows 11 keeps resetting your default apps to its own (Photos, Media Player, ...). DAB puts your choices back:
you list which application should open which file extensions, and DAB restores them, by itself after every sign-in.

* One self-contained `dab.exe` plus a plain-text config file. No Python needed on the target PC.
* No administrator rights. Everything is written under your own user (HKCU).
* Safe to run repeatedly: it only touches extensions that are wrong, and checks with Windows that each change took.

## Quick start

1. Put `dab.exe` in a folder of your choice and run it once: `dab.exe --list`.
   It creates a starter `dab_config.py` next to itself and stops (exit code 2) so you can fill it in.
2. Edit `dab_config.py` (see below).
3. Look before you change: `dab.exe --dry-run`.
4. `dab.exe --apply`. It restores the associations **and** registers a scheduled task that repeats this after every
   sign-in. That is the whole setup.

To stop the automation: `dab.exe --uninstall`.

## Commands

| Command | What it does |
|---|---|
| `dab.exe` (no arguments) | prints the help |
| `--list` | current association of every configured extension, `ok` or `DIFFER` |
| `--dry-run` | what `--apply` would change; changes nothing |
| `--apply` | restores the configuration; logs to `dab.log`; exit code 1 if any extension failed |
| `--uninstall` | removes the scheduled task and exits |
| `--config FILE`, `--log FILE` | use another config or log file (an explicit `--config` is never auto-created) |

`--list` and `--dry-run` are read-only and never touch the Task Scheduler.

## The config file

`dab_config.py` lives next to `dab.exe` (or in the project folder when run from source). It is plain Python, read on
every run, so editing it needs no rebuild:

```python
APPS = {
    r"C:\Program Files\IrfanView\i_view64.exe": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"],
    r"C:\portable\xmplay\xmplay.exe": [".mp3", ".flac", ".ogg", ".wav", ".m4a"],
    r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe": [".avi", ".mkv", ".mp4"],
}

PROGID_OVERRIDES = {}   # optional: {".ext": "Some.ProgId"} to force a specific ProgId
```

* If the default config is missing, DAB writes the starter above (all examples commented out) and exits with code 2.
* An extension listed under several apps goes to the **last** one, with a warning in the log.
* A listed exe that does not exist, or a malformed extension, is reported as a config error (exit code 2).

## Automatic runs

`--apply` keeps a Task Scheduler task named `DAB` registered. On each `--apply` it checks that the task exists, is
enabled, has a delayed *at logon* trigger (1 minute after you sign in) and runs this very exe with the same
arguments. If not, because it is missing or you moved the exe, it creates or repairs it. A failure to do so is logged
as a warning and never stops the apply.

The trigger is "at logon, delayed", not "at boot": associations live in your user registry, and a boot-time task has no
signed-in user to write them for. The task runs as you, without elevation. A console window flashes briefly when it runs.

## How the ProgId is chosen

Windows stores a *ProgId* per extension, not an exe path. For each extension DAB takes the first match of:

1. your `PROGID_OVERRIDES` entry;
2. the ProgId you used before, if it already runs the app;
3. an existing ProgId of the app named for the extension (`IrfanView.jpg`);
4. one of the app's ProgIds already offered for the extension;
5. Windows' generic `Applications\<exe name>` ProgId;
6. otherwise a new per-user ProgId `DAB.<exe name>` that DAB creates.

An extension is left alone when its current ProgId already runs the configured app.

## How it works, and what can break

Windows only honors a choice that carries a valid hash, and it checks it. DAB computes the hash the way Windows does:

* **`UserChoiceLatest`** (Windows 11 24H2 and later): the hash covers the extension, your SID, the ProgId, the machine
  id and a timestamp. Windows ignores the old key on such systems, so this is the one that matters. DAB also writes the
  classic `UserChoice` as a fallback.
* **classic `UserChoice`**: used on machines that have not switched to the new scheme.

After every write DAB asks Windows itself (`IApplicationAssociationRegistration`) which app now opens the extension and
reports a failure if it is not the intended one. The tests also recompute every hash Windows has stored on the machine
they run on, so a Windows update that changes the algorithm shows up as a failing test and as a clear `--apply` error,
never as silent nothing.

Limits:

* `.pdf`, `.htm`, `.html`, `http` and `https` are additionally guarded by Windows (UCPD driver) and writes are refused.
  `--dry-run` flags them; set those few by hand in Settings.
* The algorithms are undocumented and reverse-engineered (credits in `NOTICE`); any Windows update can change them.

## Build and develop

```
python -m dab --list                        # run from source
python -m pytest                            # tests (some read your real registry, read-only)
ruff check .
set PYTHON=C:\path\to\python.exe            # needs: pip install pyinstaller
build.cmd                                   # produces dist\dab.exe and a copy of the config next to it
```

Layout: `dab/cli.py` (commands), `config.py` + `default_config.py` (config and starter), `planner.py` (what to change),
`registry.py` (all registry/COM access), `hashing.py` + `latest_hash.py` (the two hashes), `scheduler.py` (Task
Scheduler). `latest_hash.py` and `uchash_tables.inc` are vendored from upstream; keep them diffable.
