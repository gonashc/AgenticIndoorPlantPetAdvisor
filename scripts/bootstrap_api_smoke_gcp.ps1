param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$apiServiceAccount = "advisor-api@$ProjectId.iam.gserviceaccount.com"

& $GcloudPath services enable iamcredentials.googleapis.com --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable the IAM Credentials API." }

& $GcloudPath iam service-accounts describe $apiServiceAccount `
    --project=$ProjectId `
    --quiet | Out-Null
if ($LASTEXITCODE -ne 0) { throw "The API service account does not exist." }

& $GcloudPath iam service-accounts add-iam-policy-binding $apiServiceAccount `
    --project=$ProjectId `
    --member="serviceAccount:$apiServiceAccount" `
    --role=roles/iam.serviceAccountTokenCreator `
    --condition=None `
    --quiet | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Failed to grant resource-scoped JWT signing to the API smoke identity."
}

"Authenticated API smoke prerequisites are ready."
