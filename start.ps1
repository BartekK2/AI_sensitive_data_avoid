$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = $null
foreach ($name in @("python", "py", "python3")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
        $py = $cmd.Source
        break
    }
}
if (-not $py) {
    Write-Error "Zainstaluj Python 3.10+ i uruchom ponownie:  python start.py"
    exit 1
}
& $py start.py @args
exit $LASTEXITCODE
