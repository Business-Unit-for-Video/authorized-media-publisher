param(
    [ValidateSet('JayChou', 'YuGang')]
    [string]$Collection = 'JayChou',
    [string]$VideoId = '',
    [string]$CookieDirectory = (Join-Path $env:LOCALAPPDATA 'authorized-media-publisher\credentials'),
    [switch]$Publish
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Run scripts\setup-windows.ps1 first.'
}
$previousUtf8 = $env:PYTHONUTF8
$previousUnbuffered = $env:PYTHONUNBUFFERED
try {
    $env:PYTHONUTF8 = '1'
    $env:PYTHONUNBUFFERED = '1'
    Push-Location $repoRoot
    try {
        $arguments = @('-m', 'scripts.run_windows', '--collection', $Collection,
            '--cookie-directory', $CookieDirectory)
        if ($VideoId) { $arguments += @('--video-id', $VideoId) }
        if ($Publish) { $arguments += '--publish' }
        & $pythonExe @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Local publisher stopped (exit $LASTEXITCODE). See the message above."
        }
    } finally {
        Pop-Location
    }
} finally {
    $env:PYTHONUTF8 = $previousUtf8
    $env:PYTHONUNBUFFERED = $previousUnbuffered
}
