# Gera o pacote de entrega preservando o ambiente Python e os modelos locais.
# Execute na raiz: powershell -NoProfile -File scripts\empacotar_projeto.ps1
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\', '/')
$rootPrefix = $projectRoot + [IO.Path]::DirectorySeparatorChar
$outputPath = Join-Path $projectRoot '.runtime\entrega\APS-Leitura-Facial.zip'
$limitBytes = 500000000L
$files = [Collections.Generic.List[IO.FileInfo]]::new()
$entryNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$cacheDirectories = @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.cache')
$generatedDirectories = @('.git', '.runtime', 'node_modules', '.angular', 'dist', 'build',
    'coverage', 'htmlcov', '.tox', '.nox', 'out-tsc', 'bazel-out')

function Assert-ProjectPath([string]$Path) {
    $absolutePath = [IO.Path]::GetFullPath($Path)
    if ($absolutePath -ne $projectRoot -and
        -not $absolutePath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho fora do projeto: $Path"
    }
}

function Assert-NoLink($Item) {
    Assert-ProjectPath $Item.FullName
    # OneDrive usa ReparsePoint sem ser um link. Links reais sao recusados,
    # inclusive internos, para evitar ciclos e destinos externos indiretos.
    if ($Item.LinkType -in @('SymbolicLink', 'Junction')) {
        throw "Link encontrado; use arquivos reais dentro do projeto: $($Item.FullName)"
    }
}

function Get-EntryName([string]$Path) {
    return $Path.Substring($rootPrefix.Length).Replace('\', '/')
}

function Add-SourceDirectory([string]$Path) {
    $directory = Get-Item -LiteralPath $Path -Force
    Assert-NoLink $directory
    foreach ($item in Get-ChildItem -LiteralPath $Path -Force) {
        $entryName = Get-EntryName $item.FullName
        $inVenv = $entryName.StartsWith('.venv/', [StringComparison]::OrdinalIgnoreCase)
        if ($item.PSIsContainer) {
            if ($item.Name -in $cacheDirectories -or
                (-not $inVenv -and $item.Name -in $generatedDirectories) -or
                $entryName -eq 'backend/tests') {
                continue
            }
            Add-SourceDirectory $item.FullName
        } else {
            Add-SourceFile $item
        }
    }
}

function Add-SourceFile([IO.FileInfo]$Item) {
    $entryName = Get-EntryName $Item.FullName
    $inVenv = $entryName.StartsWith('.venv/', [StringComparison]::OrdinalIgnoreCase)
    if ($Item.Name -eq '.env' -or $Item.Name -like '.env.*' -or
        $Item.Name -like '*.spec.ts' -or $Item.Name -like '*.sqlite*' -or
        $Item.Name -in @('.DS_Store', 'Thumbs.db') -or
        $Item.Extension -in @('.pyc', '.pyo', '.key', '.db', '.log', '.part', '.tmp') -or
        ($Item.Extension -eq '.zip' -and -not $inVenv)) {
        return
    }
    Assert-NoLink $Item
    if (-not $entryNames.Add($entryName)) {
        throw "Arquivo duplicado no pacote: $entryName"
    }
    $files.Add($Item)
}

# Mantem exatamente os modelos usados pela aplicacao, sem converter os pesos.
$models = @(
    @{Name='face_detection_yunet_2023mar.onnx'; Bytes=232589L;
      Hash='8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'},
    @{Name='glintr100.onnx'; Bytes=260694151L;
      Hash='a7933ea5330113b01c9b60351d8f4c33003f145d8470ac5f0e52ee2effe25c60'}
)
foreach ($modelDirectory in @('backend', 'backend\.runtime', 'backend\.runtime\modelos')) {
    Assert-NoLink (Get-Item -LiteralPath (Join-Path $projectRoot $modelDirectory) -Force)
}
foreach ($model in $models) {
    $modelPath = Join-Path $projectRoot ('backend\.runtime\modelos\' + $model.Name)
    $modelFile = Get-Item -LiteralPath $modelPath -Force
    Assert-NoLink $modelFile
    if ($modelFile.Length -ne $model.Bytes -or
        (Get-FileHash -LiteralPath $modelPath -Algorithm SHA256).Hash -ne $model.Hash) {
        throw "Modelo ausente ou sem integridade: $($model.Name)"
    }
}

foreach ($inputDirectory in @('backend', 'frontend', 'scripts', '.venv', 'backend\.runtime\modelos')) {
    Add-SourceDirectory (Join-Path $projectRoot $inputDirectory)
}
foreach ($rootFile in @('README.md', 'iniciar.bat', 'iniciar.sh', '.gitignore', '.gitattributes')) {
    Add-SourceFile (Get-Item -LiteralPath (Join-Path $projectRoot $rootFile) -Force)
}

$requiredEntries = @('README.md', 'iniciar.bat', 'iniciar.sh', 'scripts/empacotar_projeto.ps1',
    '.venv/pyvenv.cfg', '.venv/Scripts/python.exe',
    '.venv/python312/python.exe', '.venv/python312/python312.zip', '.venv/python312/python312.dll',
    'backend/app/main.py', 'backend/app/processamento/__init__.py',
    'backend/app/processamento/sensoriamento.py', 'backend/app/processamento/pre_processamento.py',
    'backend/app/processamento/segmentacao.py', 'backend/app/processamento/extracao_caracteristicas.py',
    'backend/app/processamento/classificacao_interpretacao.py', 'backend/requirements.txt',
    'backend/scripts/preparar_modelos.py', 'backend/scripts/iniciar_servidores.ps1',
    'frontend/validacaoBiometricaFront/package.json',
    'frontend/validacaoBiometricaFront/package-lock.json',
    'frontend/validacaoBiometricaFront/angular.json',
    'frontend/validacaoBiometricaFront/tsconfig.json',
    'frontend/validacaoBiometricaFront/tsconfig.app.json',
    'frontend/validacaoBiometricaFront/src/main.ts')
foreach ($model in $models) {
    $requiredEntries += 'backend/.runtime/modelos/' + $model.Name
}
foreach ($entryName in $requiredEntries) {
    if (-not $entryNames.Contains($entryName)) {
        throw "Arquivo obrigatorio ausente no pacote: $entryName"
    }
}

# O destino e fixo e fica fora dos diretorios incluidos no pacote.
foreach ($outputItem in @('.runtime', '.runtime\entrega', '.runtime\entrega\APS-Leitura-Facial.zip')) {
    $candidatePath = Join-Path $projectRoot $outputItem
    Assert-ProjectPath $candidatePath
    if (Test-Path -LiteralPath $candidatePath) {
        Assert-NoLink (Get-Item -LiteralPath $candidatePath -Force)
    }
}
$null = New-Item -ItemType Directory -Path (Split-Path -Parent $outputPath) -Force
$outputStream = [IO.File]::Open($outputPath, [IO.FileMode]::Create, [IO.FileAccess]::Write)
$archive = $null
try {
    $archive = [IO.Compression.ZipArchive]::new($outputStream, [IO.Compression.ZipArchiveMode]::Create, $true)
    foreach ($file in $files | Sort-Object FullName) {
        $null = [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $file.FullName, (Get-EntryName $file.FullName),
            [IO.Compression.CompressionLevel]::Optimal)
    }
} finally {
    if ($null -ne $archive) { $archive.Dispose() }
    $outputStream.Dispose()
}

$zipBytes = (Get-Item -LiteralPath $outputPath).Length
$sourceBytes = ($files | Measure-Object Length -Sum).Sum
Write-Output "Pacote: $outputPath"
Write-Output "Arquivos: $($files.Count)"
Write-Output ("Originais incluidos: {0:N2} MB ({1} bytes)" -f ($sourceBytes / 1000000), $sourceBytes)
Write-Output ("ZIP: {0:N2} MB ({1} bytes); limite: 500 MB (500000000 bytes)" -f ($zipBytes / 1000000), $zipBytes)
Write-Output 'Incluidos: codigo, configuracoes, documentacao, .venv e modelos ONNX locais.'
Write-Output 'Excluidos: testes da aplicacao, specs, caches, node_modules, builds e arquivos privados.'
if ($zipBytes -gt $limitBytes) {
    throw 'O ZIP ultrapassa o limite de 500 MB. Nao envie este arquivo.'
}
