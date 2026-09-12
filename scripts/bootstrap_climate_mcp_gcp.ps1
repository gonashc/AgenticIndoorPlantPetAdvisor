param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ServiceAccountName = "advisor-climate-mcp",
    [string]$ApiKeyDisplayName = "advisor-climate-geocoding-runtime",
    [string]$ApiKeyId = "advisor-climate-geocoding-runtime",
    [string]$SecretName = "google-geocoding-api-key",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable `
    apikeys.googleapis.com `
    geocoding-backend.googleapis.com `
    run.googleapis.com `
    secretmanager.googleapis.com `
    --project=$ProjectId `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable the Cloud Run API." }

& $GcloudPath iam service-accounts describe $serviceAccount --project=$ProjectId --quiet 2>$null |
    Out-Null
if ($LASTEXITCODE -ne 0) {
    & $GcloudPath iam service-accounts create $ServiceAccountName `
        --project=$ProjectId `
        --display-name="Advisor climate MCP runtime" `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the climate MCP service account." }
}

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    & $GcloudPath alpha services api-keys create `
        --project=$ProjectId `
        --display-name=$ApiKeyDisplayName `
        --key-id=$ApiKeyId `
        --api-target="service=geocoding-backend.googleapis.com" `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the restricted geocoding API key." }
    $keyResource = (& $GcloudPath alpha services api-keys list `
        --project=$ProjectId `
        --filter="displayName=$ApiKeyDisplayName" `
        --format="value(name)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $keyResource) {
        throw "Could not identify the restricted geocoding API key."
    }
    $keyString = (& $GcloudPath alpha services api-keys get-key-string $keyResource `
        --project=$ProjectId `
        --format="value(keyString)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $keyString) {
        throw "Could not retrieve the restricted geocoding API key."
    }
    $keyString | & $GcloudPath secrets create $SecretName `
        --project=$ProjectId `
        --replication-policy=automatic `
        --data-file=- `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to store the geocoding key." }
    $keyString = $null
}

& $GcloudPath secrets add-iam-policy-binding $SecretName `
    --project=$ProjectId `
    --member="serviceAccount:$serviceAccount" `
    --role=roles/secretmanager.secretAccessor `
    --quiet | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to grant access to the geocoding key." }

"Climate MCP GCP prerequisites are ready."
