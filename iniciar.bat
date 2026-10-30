@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend\validacaoBiometricaFront"
set "SERVIDORES=%BACKEND%\scripts\iniciar_servidores.ps1"

rem Reutiliza o ambiente da raiz ou, como alternativa, o de backend.
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if exist "%PYTHON%" (
    "%PYTHON%" --version >nul 2>&1
    if not errorlevel 1 goto :ambiente_pronto
)

set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
if exist "%PYTHON%" (
    "%PYTHON%" --version >nul 2>&1
    if not errorlevel 1 goto :ambiente_pronto
)

echo Ambiente Python funcional nao encontrado na raiz nem em backend\.venv.
echo Se ainda nao existir um ambiente, crie na raiz: py -3.12 -m venv .venv
exit /b 1

:ambiente_pronto
where node.exe >nul 2>&1
if errorlevel 1 (
    echo Node.js nao encontrado. Instale Node.js e npm antes de continuar.
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo npm nao encontrado. Confira a instalacao do Node.js.
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SERVIDORES%" -VerificarPortas
if errorlevel 1 exit /b 1

pushd "%BACKEND%"
if errorlevel 1 exit /b 1

echo Instalando as dependencias do backend...
set "ERRO=Falha na instalacao das dependencias do backend."
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :falha_preparacao

echo Preparando os modelos faciais...
set "ERRO=Falha na preparacao dos modelos faciais."
"%PYTHON%" scripts\preparar_modelos.py
if errorlevel 1 goto :falha_preparacao

echo Preparando o banco MySQL...
set "ERRO=Falha na preparacao do MySQL. Confira o servico e backend\.env."
"%PYTHON%" -m app.inicializar
if errorlevel 1 goto :falha_preparacao

popd
pushd "%FRONTEND%"
if errorlevel 1 exit /b 1

echo Instalando as dependencias do frontend...
set "ERRO=Falha na instalacao das dependencias npm."
call npm.cmd install
if errorlevel 1 goto :falha_preparacao

popd

rem O auxiliar cuida somente dos servidores, dos logs e do encerramento.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SERVIDORES%" -Python "%PYTHON%"
exit /b %ERRORLEVEL%

:falha_preparacao
popd
echo %ERRO%
exit /b 1
