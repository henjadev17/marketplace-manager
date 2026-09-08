$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment missing. Run scripts/setup.ps1 first."
}
. (Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1")
Push-Location $ProjectRoot
try {
    & $VenvPython -m app.main
    if ($LASTEXITCODE -ne 0) { throw "Application exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
