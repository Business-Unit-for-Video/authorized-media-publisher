[CmdletBinding()]
param(
    [string]$PythonPath = "python"
)

# Windows PowerShell 5.1 compatible; all Python packages stay in this repo's venv.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvRoot = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Executable"
    }
}

Push-Location $RepoRoot
try {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        if (Test-Path -LiteralPath $VenvRoot) {
            throw "Existing .venv is incomplete. Preserve it and select a clean project checkout."
        }
        Invoke-Checked $PythonPath @("-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer required'")
        Invoke-Checked $PythonPath @("-m", "venv", $VenvRoot)
    }
    Invoke-Checked $VenvPython @("-c", "import sys; assert sys.version_info >= (3, 11); assert sys.prefix != sys.base_prefix, 'A virtualenv is required'")
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    # Wheels prevent accidental compilation of native dependencies on Windows.
    Invoke-Checked $VenvPython @(
        "-m", "pip", "install", "--only-binary=:all:",
        "setuptools>=68", "wheel", "requests>=2.31", "rsa>=4.9,<5",
        "aiohttp==3.14.4", "multidict==6.9.1", "yt-dlp==2026.8.19"
    )
    Invoke-Checked $VenvPython @("-m", "pip", "install", "--no-build-isolation", "--no-deps", "-e", $RepoRoot)
    Invoke-Checked $VenvPython @((Join-Path $PSScriptRoot "setup_windows.py"))
    Invoke-Checked $VenvPython @("-c", "from biliup.plugins.bili_webup import BiliBili, Data; print('Bilibili pure-Python uploader import OK')")
    foreach ($CommandName in @("media-publisher", "media-publish-bilibili", "media-publish-serial")) {
        Invoke-Checked (Join-Path $VenvRoot "Scripts\$CommandName.exe") @("--help")
    }
    Write-Host "Windows environment ready: $VenvPython"
    Write-Host "No upload was started. GitHub Actions settings were not changed."
}
finally {
    Pop-Location
}
