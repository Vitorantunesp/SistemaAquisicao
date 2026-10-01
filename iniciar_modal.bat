@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python nao encontrado. Execute instalar.bat primeiro.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" analise_modal.py
if errorlevel 1 pause
