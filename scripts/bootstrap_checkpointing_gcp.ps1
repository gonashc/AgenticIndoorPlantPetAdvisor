param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ApiServiceAccountName = "advisor-api",
    [string]$SecretName = "langgraph-database-url",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccount = "$ApiServiceAccountName@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable secretmanager.googleapis.com --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable Secret Manager." }

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    $connectionString = $env:CHECKPOINT_DATABASE_URL
    if (-not $connectionString -or $connectionString -notmatch '^postgres(ql)?://') {
        throw (
            "Set CHECKPOINT_DATABASE_URL in this PowerShell process to a psycopg URL for the " +
            "dedicated checkpoint database before running this bootstrap."
        )
    }
    $connectionString | & $GcloudPath secrets create $SecretName `
        --project=$ProjectId `
        --replication-policy=automatic `
        --data-file=- `
        --quiet
    $connectionString = $null
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the checkpoint connection secret." }
}

& $GcloudPath secrets add-iam-policy-binding $SecretName `
    --project=$ProjectId `
    --member="serviceAccount:$serviceAccount" `
    --role=roles/secretmanager.secretAccessor `
    --quiet | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to grant API access to the checkpoint secret." }

"LangGraph checkpoint secret and access are ready."
