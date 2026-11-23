@echo off
rem Builds dist\dab.exe, a self-contained executable (no Python needed on the target machine).
rem Needs PyInstaller in the Python that runs this script:  python -m pip install pyinstaller
rem Set PYTHON to use a specific interpreter, e.g.  set PYTHON=D:\igor\projects\sindex\.venv\Scripts\python.exe
setlocal
if "%PYTHON%"=="" set PYTHON=python
set HERE=%~dp0
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --console --name dab ^
  --add-data "%HERE%pyproject.toml;." ^
  --paths "%HERE%." ^
  --add-data "%HERE%dab\uchash_tables.inc;dab" ^
  --distpath "%HERE%dist" --workpath "%TEMP%\dab_build" --specpath "%TEMP%\dab_build" ^
  "%HERE%dab_main.py" || exit /b 1
rem dab.exe reads dab_config.py from its own folder: put a copy next to it unless one is already there.
if exist "%HERE%dab_config.py" if not exist "%HERE%dist\dab_config.py" copy "%HERE%dab_config.py" "%HERE%dist\dab_config.py" >nul
echo.
echo Built %HERE%dist\dab.exe  (config: %HERE%dist\dab_config.py)
