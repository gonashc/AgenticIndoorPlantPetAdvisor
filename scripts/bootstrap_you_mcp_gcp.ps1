param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ServiceAccountName = "advisor-you-mcp",
    [string]$SecretName = "you-api-key",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$regulationsAccount = "advisor-regulations-mcp@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable run.googleapis.com secretmanager.googleapis.com `
    --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable You MCP service APIs." }

& $GcloudPath iam service-accounts describe $serviceAccount --project=$ProjectId --quiet 2>$null |
    Out-Null
if ($LASTEXITCODE -ne 0) {
    & $GcloudPath iam service-accounts create $ServiceAccountName `
        --project=$ProjectId `
        --display-name="Advisor You.com guidance MCP runtime" `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the You MCP service account." }
}

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Create Secret Manager secret $SecretName with the You.com API key before continuing."
}

foreach ($account in @($serviceAccount, $regulationsAccount)) {
    & $GcloudPath secrets add-iam-policy-binding $SecretName `
        --project=$ProjectId `
        --member="serviceAccount:$account" `
        --role=roles/secretmanager.secretAccessor `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to grant $account access to $SecretName." }
}

"You.com MCP GCP prerequisites are ready."
