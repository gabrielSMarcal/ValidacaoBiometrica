param(
    [string]$Python,
    [switch]$VerificarPortas,
    [switch]$PrepararPython,
    [string]$Etapa
)

$ErrorActionPreference = 'Stop'
$Backend = Split-Path -Parent $PSScriptRoot
$Root = Split-Path -Parent $Backend
$Frontend = Join-Path $Root 'frontend\validacaoBiometricaFront'
$Runtime = Join-Path $Backend '.runtime'

function Write-Stage([string]$Message) {
    Write-Host ''
    if (-not $env:NO_COLOR -and $env:TERM -ne 'dumb' -and -not [Console]::IsOutputRedirected) {
        Write-Host $Message -ForegroundColor Blue
    } else {
        Write-Host $Message
    }
}

if ($Etapa) {
    Write-Stage $Etapa
    exit 0
}

if ($PrepararPython) {
    $ambiente = Join-Path $Root '.venv'
    $basePython = Join-Path $ambiente 'python312'
    if (Test-Path -LiteralPath (Join-Path $basePython 'python.exe')) {
        $configuracao = @(
            "home = $basePython",
            'include-system-site-packages = false',
            'version = 3.12.10',
            "executable = $basePython\python.exe"
        ) -join "`r`n"
        [IO.File]::WriteAllText((Join-Path $ambiente 'pyvenv.cfg'), $configuracao,
            (New-Object Text.UTF8Encoding($false)))
    }
    exit 0
}

function Assert-FreePort($HostName, $Port) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $client.Connect($HostName, $Port)
    } catch {
        return
    } finally {
        $client.Dispose()
    }

    throw "A porta $Port esta ocupada. Encerre a instancia anterior antes de iniciar o projeto."
}

function Assert-FreePorts {
    Assert-FreePort '127.0.0.1' 8000
    Assert-FreePort '127.0.0.1' 4200
    Assert-FreePort '::1' 4200
}

function Stop-OwnedProcess($Process) {
    try {
        if ($null -ne $Process -and -not $Process.HasExited) {
            & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
        }
    } catch {
        # O processo pode ter encerrado entre a verificacao e o taskkill.
    }
}

function Start-Server($Executable, $Arguments, $Directory, $LogName) {
    $options = @{
        FilePath = $Executable
        ArgumentList = $Arguments
        WorkingDirectory = $Directory
        WindowStyle = 'Hidden'
        RedirectStandardOutput = Join-Path $Runtime "$LogName.log"
        RedirectStandardError = Join-Path $Runtime "$LogName-error.log"
        PassThru = $true
    }
    $process = Start-Process @options
    # Preserva o codigo de saida mesmo se o processo encerrar rapidamente.
    $null = $process.Handle
    return $process
}

function Wait-ApiReady($Process, $ErrorLog) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($Process.HasExited) {
            throw "A API encerrou antes de iniciar. Consulte: $ErrorLog"
        }

        try {
            $response = Invoke-WebRequest -UseBasicParsing `
                -Uri 'http://127.0.0.1:8000/api/saude' -TimeoutSec 1
        } catch {
            $response = $null
        }

        if ($response -and $response.StatusCode -eq 200 -and -not $Process.HasExited) {
            return
        }
        Start-Sleep -Seconds 1
    }

    throw "A API nao respondeu no tempo esperado. Consulte: $ErrorLog"
}

if ($VerificarPortas) {
    try {
        Assert-FreePorts
        exit 0
    } catch {
        Write-Host "Erro: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

$api = $null
$front = $null
$exitCode = 1

try {
    if (-not $Python) {
        throw 'Informe o Python do ambiente virtual pelo iniciar.bat da raiz.'
    }

    Assert-FreePorts
    New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
    $apiError = Join-Path $Runtime 'api-error.log'
    $frontError = Join-Path $Runtime 'frontend-error.log'

    Write-Stage '[5/6] API local | Iniciando o servidor...'
    $api = Start-Server -Executable $Python -Directory $Backend -LogName 'api' `
        -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000')
    Write-Stage '[API] Aguardando o servidor responder...'
    Wait-ApiReady -Process $api -ErrorLog $apiError

    Write-Stage '[6/6] Frontend | Iniciando a compilacao e o servidor Angular...'
    $front = Start-Server -Executable $env:ComSpec -Directory $Frontend -LogName 'frontend' `
        -Arguments @('/d', '/c', 'npm.cmd', 'start', '--', '--host', 'localhost', '--port', '4200', '--open')

    Write-Host ''
    Write-Host 'API: http://localhost:8000/docs'
    Write-Host 'Frontend: http://localhost:4200 (abrira no navegador apos a compilacao)'
    Write-Host "Logs: $Runtime"
    Write-Host 'Mantenha este terminal aberto. Pressione Ctrl+C para encerrar os dois servidores.'

    while (-not $front.HasExited) {
        if ($api.HasExited) {
            throw "A API encerrou. Consulte: $apiError"
        }
        Start-Sleep -Milliseconds 250
    }

    $front.WaitForExit()
    $exitCode = $front.ExitCode
    if ($null -eq $exitCode) {
        throw "Nao foi possivel obter o resultado do frontend. Consulte: $frontError"
    }
    if ($exitCode -ne 0) {
        Write-Host "O frontend encerrou com erro. Consulte: $frontError"
    }
} catch {
    Write-Host "Erro: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
} finally {
    Stop-OwnedProcess $front
    Stop-OwnedProcess $api
}

exit $exitCode
