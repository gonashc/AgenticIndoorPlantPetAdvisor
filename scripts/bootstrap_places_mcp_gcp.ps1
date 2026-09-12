param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ServiceAccountName = "advisor-mcp",
    [string]$ApiKeyDisplayName = "advisor-places-mcp-runtime",
    [string]$ApiKeyId = "advisor-places-mcp-runtime",
    [string]$SecretName = "google-places-api-key",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable `
    apikeys.googleapis.com `
    places.googleapis.com `
    run.googleapis.com `
    secretmanager.googleapis.com `
    --project=$ProjectId `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable plant-location service APIs." }

& $GcloudPath iam service-accounts describe $serviceAccount --project=$ProjectId --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    & $GcloudPath iam service-accounts create $ServiceAccountName `
        --project=$ProjectId `
        --display-name="Advisor plant-location MCP runtime" `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the MCP runtime service account." }
}

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $keyResources = @(
        (& $GcloudPath services api-keys list `
            --project=$ProjectId `
            --filter="displayName=$ApiKeyDisplayName" `
            --format="value(name)" 2>$null) | Where-Object { $_ }
    )
    if ($LASTEXITCODE -ne 0) { throw "Failed to inspect existing Google Places API keys." }
    if ($keyResources.Count -gt 1) {
        throw "Multiple API keys use display name $ApiKeyDisplayName; resolve them manually."
    }
    if ($keyResources.Count -eq 0) {
        & $GcloudPath services api-keys create `
            --project=$ProjectId `
            --display-name=$ApiKeyDisplayName `
            --key-id=$ApiKeyId `
            --api-target="service=places.googleapis.com" `
            --quiet *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create the restricted Google Places API key."
        }
        $keyResources = @(
            (& $GcloudPath services api-keys list `
                --project=$ProjectId `
                --filter="displayName=$ApiKeyDisplayName" `
                --format="value(name)" 2>$null) | Where-Object { $_ }
        )
        if ($LASTEXITCODE -ne 0 -or $keyResources.Count -ne 1) {
            throw "Could not identify the restricted Google Places API key."
        }
        $keyResource = $keyResources[0]
    }
    else {
        $keyResource = $keyResources[0]
    }

    $keyString = ""
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        $keyJson = & $GcloudPath services api-keys get-key-string $keyResource `
            --project=$ProjectId `
            --format=json `
            --quiet 2>$null
        if ($LASTEXITCODE -eq 0) {
            $keyString = ($keyJson | ConvertFrom-Json).keyString
            if ($keyString) { break }
        }
        if ($attempt -lt 12) { Start-Sleep -Seconds 5 }
    }
    if (-not $keyString) { throw "Google Places returned an empty API key." }
    $keyString | & $GcloudPath secrets create $SecretName `
        --project=$ProjectId `
        --replication-policy=automatic `
        --data-file=- `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to store the Google Places key in Secret Manager." }
    $keyString = $null
}

& $GcloudPath secrets add-iam-policy-binding $SecretName `
    --project=$ProjectId `
    --member="serviceAccount:$serviceAccount" `
    --role=roles/secretmanager.secretAccessor `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to grant the MCP runtime access to its secret." }

"Plant-location GCP prerequisites are ready."
