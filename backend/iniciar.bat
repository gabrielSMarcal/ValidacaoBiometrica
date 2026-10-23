@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "HEALTH=http://127.0.0.1:8000/api/saude"

if not exist "%PYTHON%" (
    echo Ambiente virtual nao encontrado em .venv
    pause
    exit /b 1
)

cd /d "%ROOT%"

echo Preparando o banco MySQL...
"%PYTHON%" -m app.inicializar
if errorlevel 1 (
    pause
    exit /b 1
)

echo Iniciando a API local...
start "APS API" /b "%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo Aguardando a API responder...

for /l %%i in (1,1,30) do (
    curl.exe --silent --fail "%HEALTH%" >nul 2>&1

    if not errorlevel 1 (
        echo API iniciada com sucesso.
        exit /b 0
    )

    timeout /t 1 /nobreak >nul
)

echo A API nao respondeu no tempo esperado.
pause
exit /b 1
