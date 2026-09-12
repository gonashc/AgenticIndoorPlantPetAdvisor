param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ServiceAccountName = "advisor-adoption-mcp",
    [string]$SecretName = "rescuegroups-api-key",
    [string]$EnvFile = ".env",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable `
    run.googleapis.com `
    secretmanager.googleapis.com `
    --project=$ProjectId `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable adoption MCP service APIs." }

& $GcloudPath iam service-accounts describe $serviceAccount --project=$ProjectId --quiet 2>$null |
    Out-Null
if ($LASTEXITCODE -ne 0) {
    & $GcloudPath iam service-accounts create $ServiceAccountName `
        --project=$ProjectId `
        --display-name="Advisor adoption MCP runtime" `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the adoption MCP service account." }
}

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        throw "Add RESCUEGROUPS_API_KEY to the ignored .env file before bootstrapping."
    }
    $apiKeyLine = Get-Content -LiteralPath $EnvFile | Where-Object {
        $_ -match '^RESCUEGROUPS_API_KEY='
    } | Select-Object -Last 1
    if (-not $apiKeyLine) {
        throw "Add RESCUEGROUPS_API_KEY to the ignored .env file before bootstrapping."
    }
    $apiKey = ($apiKeyLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
    if (-not $apiKey -or $apiKey -match '^(replace|your[-_])') {
        throw "RESCUEGROUPS_API_KEY in .env must contain the real public API key."
    }
    $apiKey | & $GcloudPath secrets create $SecretName `
        --project=$ProjectId `
        --replication-policy=automatic `
        --data-file=- `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to store the RescueGroups key." }
    $apiKey = $null
}

& $GcloudPath secrets add-iam-policy-binding $SecretName `
    --project=$ProjectId `
    --member="serviceAccount:$serviceAccount" `
    --role=roles/secretmanager.secretAccessor `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to grant the adoption runtime access to its secret." }

"Adoption MCP GCP prerequisites are ready."

