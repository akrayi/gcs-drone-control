# Run only when ready to modify the selected Kubernetes cluster.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$values = @{}
Get-Content -LiteralPath (Join-Path $projectRoot '.env') | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.+)$') { $values[$matches[1]] = $matches[2] }
}
foreach ($key in @('POSTGRES_PASSWORD','GCS_DB_PASSWORD','JWT_SECRET','BOOTSTRAP_ADMIN_PASSWORD')) {
    if (-not $values[$key]) { throw "Missing $key in .env" }
}
function Apply-Secret($name, $data) {
    $manifest = @{apiVersion='v1';kind='Secret';metadata=@{name=$name;namespace='gcs'};type='Opaque';stringData=$data}
    # Pipe via standard input, not CLI arguments or temporary plaintext files.
    $manifest | ConvertTo-Json -Depth 5 | kubectl apply --server-side --field-manager=gcs-setup -f -
    if ($LASTEXITCODE -ne 0) { throw "Failed to create $name" }
}
Apply-Secret 'postgres-secret' @{POSTGRES_PASSWORD=$values.POSTGRES_PASSWORD;GCS_DB_PASSWORD=$values.GCS_DB_PASSWORD}
Apply-Secret 'backend-secret' @{JWT_SECRET=$values.JWT_SECRET;DATABASE_URL="postgresql+psycopg://gcs:$($values.GCS_DB_PASSWORD)@postgres:5432/gcs"}
Apply-Secret 'bootstrap-secret' @{BOOTSTRAP_ADMIN_PASSWORD=$values.BOOTSTRAP_ADMIN_PASSWORD}
