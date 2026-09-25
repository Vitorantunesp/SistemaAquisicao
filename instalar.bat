@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python nao foi encontrado. Instale Python 3.11 ou mais recente em python.org.
  echo Durante a instalacao, marque a opcao para adicionar o Python ao PATH.
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto :erro
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :erro
echo.
echo Instalacao concluida. Use iniciar.bat para abrir o programa.
pause
exit /b 0
:erro
echo.
echo A instalacao falhou. Verifique a mensagem acima.
pause
exit /b 1
