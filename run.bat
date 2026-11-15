@echo off
rem Starts Teeko AI with the project's virtual environment (runs setup.bat first if needed).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    call setup.bat || (pause & exit /b 1)
)
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
