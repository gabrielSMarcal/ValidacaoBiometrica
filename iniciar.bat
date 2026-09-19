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

echo Executando testes basicos...
"%PYTHON%" -m pytest -q tests\test_biometria.py tests\test_seguranca.py

if errorlevel 1 (
    echo Os testes falharam. API nao sera iniciada.
    pause
    exit /b 1
)

echo Iniciando a API...
start "APS API" /b "%PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo Aguardando a API responder...

for /l %%i in (1,1,30) do (
    curl.exe --silent --fail "%HEALTH%" >nul 2>&1

    if not errorlevel 1 (
        echo API iniciada com sucesso.
        start "" "http://127.0.0.1:8000/docs"
        exit /b 0
    )

    timeout /t 1 /nobreak >nul
)

echo A API nao respondeu no tempo esperado.
pause
exit /b 1