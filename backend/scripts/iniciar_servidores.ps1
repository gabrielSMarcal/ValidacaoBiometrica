param(
    [string]$Python,
    [switch]$VerificarPortas
)

$ErrorActionPreference = 'Stop'
$Backend = Split-Path -Parent $PSScriptRoot
$Root = Split-Path -Parent $Backend
$Frontend = Join-Path $Root 'frontend\validacaoBiometricaFront'
$Runtime = Join-Path $Backend '.runtime'

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

    Write-Host 'Iniciando a API local...'
    $api = Start-Server -Executable $Python -Directory $Backend -LogName 'api' `
        -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000')
    Wait-ApiReady -Process $api -ErrorLog $apiError

    $front = Start-Server -Executable $env:ComSpec -Directory $Frontend -LogName 'frontend' `
        -Arguments @('/d', '/c', 'npm.cmd', 'start', '--', '--host', 'localhost', '--port', '4200')

    Write-Host 'API: http://localhost:8000/docs'
    Write-Host 'Frontend: http://localhost:4200 (aguarde a compilacao)'
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
