$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
$url = 'http://127.0.0.1:8765'
$running = $false
try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
    $running = $response.Content.Contains('SCROLL STUDIO')
} catch {}
if (-not $running) {
    $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $venv = Join-Path $appRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venv) { $runtime = $venv }
    elseif (Test-Path -LiteralPath $bundled) { $runtime = $bundled }
    else { $runtime = (Get-Command python -ErrorAction Stop).Source }
    Start-Process -FilePath $runtime -ArgumentList @('"' + (Join-Path $appRoot 'server.py') + '"', '--no-browser') -WorkingDirectory $appRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $appRoot 'server.log') -RedirectStandardError (Join-Path $appRoot 'server-error.log')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
            if ($response.Content.Contains('SCROLL STUDIO')) { $running = $true; break }
        } catch {}
    }
}
if ($running) { Start-Process $url }
else { throw 'Startup failed. See server-error.log in this folder.' }
