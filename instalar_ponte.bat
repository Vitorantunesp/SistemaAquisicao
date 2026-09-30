@echo off
setlocal
cd /d "%~dp0"
rem Preserve the interpreter of an existing environment. Recreating it with a
rem different Python leaves incompatible binary packages in site-packages.
if exist ".venv-ponte\Scripts\python.exe" goto :dependencias
py -3.12 -c "import sys" >nul 2>nul
if errorlevel 1 (
  py -3 -m venv .venv-ponte
) else (
  py -3.12 -m venv .venv-ponte
)
if errorlevel 1 goto :erro
:dependencias
".venv-ponte\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :erro
".venv-ponte\Scripts\python.exe" -c "from PyQt6.QtWidgets import QApplication; from scipy.signal import butter, sosfilt, welch; import numpy; import pywt"
if errorlevel 1 goto :erro
echo Instalacao concluida. Abra iniciar_ponte.bat.
pause
exit /b 0
:erro
echo Falha na instalacao ou verificacao das bibliotecas. Consulte a mensagem acima.
echo Nao recrie um ambiente existente com outra versao do Python.
pause
exit /b 1
