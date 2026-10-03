$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$ca = Join-Path $root "data\certs\helios-ca.pem"
if (-not (Test-Path $ca)) {
    Set-Location $root
    python -c "from sensitive_guard.tlsca import ensure_ca; print(ensure_ca()[0])"
}
certutil -user -addstore Root $ca
Write-Host "CA zainstalowane w magazynie uzytkownika. Uruchom Antigravity od nowa."
