$ErrorActionPreference = "Stop"
# Proxy tylko w tym procesie — nie w całym Windowsie.
$env:HTTP_PROXY = "http://127.0.0.1:8888"
$env:HTTPS_PROXY = "http://127.0.0.1:8888"
$env:http_proxy = $env:HTTP_PROXY
$env:https_proxy = $env:HTTPS_PROXY
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = $env:NO_PROXY
$exe = "$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe"
if (-not (Test-Path $exe)) {
    throw "Nie mam Antigravity.exe w $exe"
}
Get-Process -Name "Antigravity" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-Process $exe
Write-Host "Antigravity odpalony z proxy 127.0.0.1:8888 (tylko ten proces)."
