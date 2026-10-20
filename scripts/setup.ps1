$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envPath) { throw '.env already exists; refusing to replace credentials.' }
function New-Secret {
    $buffer = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    return ([BitConverter]::ToString($buffer)).Replace('-', '').ToLowerInvariant()
}
$lines = @(
    "POSTGRES_PASSWORD=$(New-Secret)",
    "GCS_DB_PASSWORD=$(New-Secret)",
    "JWT_SECRET=$(New-Secret)",
    "BOOTSTRAP_ADMIN_PASSWORD=$(New-Secret)"
)
[IO.File]::WriteAllLines($envPath, $lines, (New-Object Text.UTF8Encoding $false))
Write-Host 'Created .env with random credentials. Admin username: admin.'
Write-Host 'Read BOOTSTRAP_ADMIN_PASSWORD in .env locally. Do not commit or share this file.'
