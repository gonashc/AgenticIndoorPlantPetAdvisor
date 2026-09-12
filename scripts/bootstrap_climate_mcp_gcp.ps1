param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ServiceAccountName = "advisor-climate-mcp",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccount = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable run.googleapis.com --project=$ProjectId --quiet
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

"Climate MCP GCP prerequisites are ready."

