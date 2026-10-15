param(
    [ValidateSet('JayChou', 'YuGang', 'XiaoDaoDaLang', 'BetterLeaf')]
    [string]$Collection = 'JayChou',
    [ValidateRange(1, 2147483647)]
    [int]$BatchSize = 1,
    [string]$VideoId = '',
    # USERPROFILE avoids MSIX LocalAppData redirection inside desktop apps.
    [string]$CookieDirectory = (Join-Path $env:USERPROFILE '.authorized-media-publisher\credentials'),
    [switch]$SyncCookies,
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
        if ($SyncCookies) {
            & $pythonExe -m scripts.sync_windows_cookies --cookie-directory $CookieDirectory
            if ($LASTEXITCODE -ne 0) {
                throw "Cookie sync stopped (exit $LASTEXITCODE). See the message above."
            }
        }
        $arguments = @('-m', 'scripts.run_windows', '--collection', $Collection,
            '--batch-size', $BatchSize.ToString(),
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
