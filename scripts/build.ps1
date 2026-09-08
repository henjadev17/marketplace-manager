$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment missing. Run scripts/setup.ps1 first."
}
. (Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1")
Push-Location $ProjectRoot
try {
    # Build artifacts stay in the checkout. Never clean or bundle user data.
    & $VenvPython -m PyInstaller --noconfirm --windowed --onedir `
        --name MarketplaceManager --paths $ProjectRoot `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build") `
        --specpath $ProjectRoot app/main.py
    if ($LASTEXITCODE -ne 0) { throw "Build failed with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
