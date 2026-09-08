$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath ".venv")) {
        py -3 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
    }
    . (Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1")
    & (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
} finally {
    Pop-Location
}
