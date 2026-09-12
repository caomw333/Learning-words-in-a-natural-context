param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$appUrl = 'http://127.0.0.1:8765'
if (-not (Test-Path -LiteralPath (Join-Path $appRoot 'dist/client/index.html'))) {
    Write-Host 'Built website is missing. Run npm run build in vocab-web first.'
    Read-Host 'Press Enter to exit'
    exit 1
}
try {
    $existingApp = Invoke-RestMethod -Uri "$appUrl/api/state" -TimeoutSec 2
    if ($existingApp.words -and $existingApp.config) {
        if (-not $NoBrowser) { Start-Process $appUrl }
        exit 0
    }
} catch { }
$bundledPython = Join-Path $appRoot 'runtime/python.exe'
if (Test-Path -LiteralPath $bundledPython) { $pythonPath = $bundledPython }
else { $pythonPath = (Get-Command python -ErrorAction Stop).Source }
$servicePath = Join-Path $appRoot 'server.py'
$localData = Join-Path $appRoot 'data'
$service = Start-Process -FilePath $pythonPath -ArgumentList @('"' + $servicePath + '"') -WorkingDirectory $appRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localData 'server.log') -RedirectStandardError (Join-Path $localData 'server-error.log')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 300
    try {
        $readyApp = Invoke-RestMethod -Uri "$appUrl/api/state" -TimeoutSec 1
        if ($readyApp.words -and $readyApp.config) {
            if (-not $NoBrowser) { Start-Process $appUrl }
            exit 0
        }
    } catch { }
    if ($service.HasExited) { break }
}
Write-Host 'The local service did not start. See vocab-web/data/server-error.log.'
Read-Host 'Press Enter to exit'
exit 1
