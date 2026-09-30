@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-ponte\Scripts\python.exe" (
  ".venv-ponte\Scripts\python.exe" monitorar_ponte.py
  if errorlevel 1 pause
  exit /b
)
if not exist ".venv\Scripts\python.exe" (
  echo Execute instalar_ponte.bat antes de iniciar.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" monitorar_ponte.py
if errorlevel 1 pause
