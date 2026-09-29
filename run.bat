@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run install.ps1 in PowerShell.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
if errorlevel 1 pause

