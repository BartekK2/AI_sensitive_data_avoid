$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "Helios Net Gate — bramka + proxy + TLS MITM"
python -c "from sensitive_guard.tlsca import ensure_ca; print(ensure_ca()[0])"
$ca = Join-Path (Get-Location) "data\certs\helios-ca.pem"
certutil -user -addstore Root $ca
python -m sensitive_guard net --backend heuristic --port 8080 --proxy-port 8888
