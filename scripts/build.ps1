$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
$icon = Join-Path $project 'build\nwake.ico'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Create .venv and install requirements-dev.txt first. See docs/development.md.'
}

Push-Location -LiteralPath $project
$priorPath = $env:Path
$priorCache = $env:PYINSTALLER_CONFIG_DIR
try {
    # Don't let DLLs from unrelated software on PATH enter the bundle.
    $env:Path = @((Split-Path -Parent $python), "$env:SystemRoot\System32", $env:SystemRoot) -join ';'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $project 'build\pyinstaller-cache'
    & $python -c "import platform, sys; sys.exit(0 if sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64') else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Build Nwake with Windows x64 Python.' }
    & $python -m scripts.make_icon $icon
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate the app icon.' }
    & $python -m PyInstaller --clean --noconfirm --onefile --windowed --noupx --name Nwake `
        --workpath 'build/pyinstaller' --specpath 'build' --distpath 'dist' `
        --paths $project --icon $icon 'nwake/__main__.py'
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    $exe = Get-Item -LiteralPath 'dist/Nwake.exe'
    Write-Output "Built $($exe.FullName) ($([math]::Round($exe.Length / 1MB, 1)) MiB)"
} finally {
    $env:Path = $priorPath
    $env:PYINSTALLER_CONFIG_DIR = $priorCache
    Pop-Location
}
