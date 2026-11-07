@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend\validacaoBiometricaFront"
set "SERVIDORES=%BACKEND%\scripts\iniciar_servidores.ps1"

rem Ajusta o Python incluido no ambiente quando o projeto muda de pasta.
call :etapa "[AMBIENTE] Verificando o Python e o ambiente virtual..."
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SERVIDORES%" -PrepararPython
if errorlevel 1 exit /b 1

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

if exist "%ROOT%.venv" (
    echo A .venv da raiz existe, mas nao funciona neste Windows. Revise o ambiente antes de continuar.
    exit /b 1
)
call :selecionar_python_base
if errorlevel 1 (
    echo Python 3.12 com suporte a venv nao encontrado. Confira a instalacao do Python.
    exit /b 1
)

call :etapa "[AMBIENTE] Criando o ambiente virtual .venv na raiz do projeto..."
"%PYTHON_BASE%" %PYTHON_ARGUMENTOS% -m venv "%ROOT%.venv"
if errorlevel 1 (
    echo Falha ao criar a .venv. Confira as permissoes da pasta e a instalacao do Python.
    exit /b 1
)
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
"%PYTHON%" -c "import sys; sys.exit(sys.prefix == sys.base_prefix)" >nul 2>&1
if errorlevel 1 (
    echo A criacao da .venv nao produziu um ambiente Python funcional.
    exit /b 1
)

:ambiente_pronto
"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo O ambiente virtual esta sem pip. Confira o suporte a venv e ensurepip do Python instalado.
    exit /b 1
)
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

call :etapa "[1/6] Dependencias do backend (requirements.txt) | Instalando..."
set "ERRO=Falha na instalacao das dependencias do backend."
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :falha_preparacao

call :etapa "[2/6] Modelos faciais (arquivos ONNX) | Verificando e baixando os modelos ausentes..."
set "ERRO=Falha na preparacao dos modelos faciais."
"%PYTHON%" scripts\preparar_modelos.py
if errorlevel 1 goto :falha_preparacao

call :etapa "[3/6] Banco MySQL | Preparando o banco de dados e as tabelas..."
set "ERRO=Falha na preparacao do MySQL. Confira o servico e backend\.env."
"%PYTHON%" -m app.inicializar
if errorlevel 1 goto :falha_preparacao

popd
pushd "%FRONTEND%"
if errorlevel 1 exit /b 1

call :etapa "[4/6] Dependencias do frontend (npm) | Instalando..."
set "ERRO=Falha na instalacao das dependencias npm."
call npm.cmd install
if errorlevel 1 goto :falha_preparacao

popd

rem O auxiliar inicia os servidores, abre a pagina e cuida dos logs e do encerramento.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SERVIDORES%" -Python "%PYTHON%"
exit /b %ERRORLEVEL%

:falha_preparacao
popd
echo %ERRO%
exit /b 1

:etapa
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SERVIDORES%" -Etapa "%~1"
exit /b 0

:selecionar_python_base
py.exe -3.12 -c "import sys, venv, ensurepip; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_BASE=py.exe"
    set "PYTHON_ARGUMENTOS=-3.12"
    exit /b 0
)
for /f "delims=" %%P in ('where python.exe python3.exe 2^>nul') do (
    call :validar_python_base "%%P"
    if not errorlevel 1 (
        set "PYTHON_BASE=%%P"
        set "PYTHON_ARGUMENTOS="
        exit /b 0
    )
)
exit /b 1

:validar_python_base
set "PYTHON_CANDIDATO=%~1"
if /i not "%PYTHON_CANDIDATO:WindowsApps=%"=="%PYTHON_CANDIDATO%" exit /b 1
"%PYTHON_CANDIDATO%" -c "import sys, venv, ensurepip; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>&1
exit /b %ERRORLEVEL%
