@echo off
rem Creates .venv with Python 3.10+ and installs the requirements.
rem Never trusts the first "python" on PATH (an old Python may come first):
rem every candidate is checked with sys.version_info before it is used.
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "CHECK=import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
set "PY="

rem 1. The Windows Python launcher, asking for specific versions
for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "!CHECK!" >nul 2>&1 && set "PY=py -%%V"
    )
)

rem 2. Standard install locations
for %%V in (313 312 311 310) do (
    for %%P in ("%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" "%ProgramFiles%\Python%%V\python.exe") do (
        if not defined PY if exist %%P (
            %%P -c "!CHECK!" >nul 2>&1 && set PY=%%P
        )
    )
)

rem 3. Whatever "python" is on PATH, but only if it is new enough
if not defined PY (
    python -c "!CHECK!" >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo.
    echo  No Python 3.10 or newer was found.
    echo  Install one, e.g.:  winget install -e --id Python.Python.3.12 --scope user
    echo  or download it from https://www.python.org/downloads/ and run setup.bat again.
    exit /b 1
)

echo Using: !PY!
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    !PY! -m venv .venv || exit /b 1
)
".venv\Scripts\python.exe" -c "!CHECK!" || (
    echo .venv was made with an old Python. Delete the .venv folder and run setup.bat again.
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || exit /b 1
echo.
echo Setup complete. Start the game with run.bat
exit /b 0
