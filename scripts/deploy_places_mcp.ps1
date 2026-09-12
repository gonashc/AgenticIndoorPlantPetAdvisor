param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ProjectNumber = "201638055698",
    [string]$Region = "us-east1",
    [string]$ServiceName = "advisor-places-mcp",
    [string]$ApiServiceName = "advisor-api",
    [string]$Repository = "advisor",
    [string]$SecretName = "google-places-api-key",
    [string]$ImageTag = "",
    [string]$IapMember = "user:gonashc@gmail.com",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
if (-not $ImageTag) {
    $ImageTag = (& git rev-parse --short=12 HEAD).Trim()
}
if ($ImageTag -notmatch '^[a-zA-Z0-9_.-]+$') {
    throw "ImageTag contains unsupported characters."
}

$mcpServiceAccount = "advisor-mcp@$ProjectId.iam.gserviceaccount.com"
$apiServiceAccount = "advisor-api@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/places-mcp:$ImageTag"

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Secret $SecretName does not exist. Bootstrap the restricted Google Places key first."
}

$apiUrl = (& $GcloudPath run services describe $ApiServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="value(status.url)").Trim()
$apiUrlPrefix = "https://$ApiServiceName-"
if ($LASTEXITCODE -ne 0 -or -not $apiUrl.StartsWith($apiUrlPrefix)) {
    throw "Could not derive the Cloud Run hostname from $ApiServiceName."
}
$mcpAudience = "https://$ServiceName-$($apiUrl.Substring($apiUrlPrefix.Length))"
$mcpHost = ([Uri]$mcpAudience).Host
$mcpUrl = "$mcpAudience/mcp"

& $GcloudPath builds submit `
    --project=$ProjectId `
    --region=$Region `
    --config=services/places_mcp/cloudbuild.yaml `
    --substitutions="_IMAGE=$image" `
    .
if ($LASTEXITCODE -ne 0) { throw "Plant-location MCP image build failed." }

& $GcloudPath run deploy $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --service-account=$mcpServiceAccount `
    --set-env-vars="APP_ENV=production,MCP_ALLOWED_HOSTS=$mcpHost" `
    --set-secrets="GOOGLE_PLACES_API_KEY=$SecretName`:latest" `
    --no-allow-unauthenticated `
    --no-iap `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Plant-location MCP deployment failed." }

& $GcloudPath run services add-iam-policy-binding $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --member="serviceAccount:$apiServiceAccount" `
    --role=roles/run.invoker `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to grant the API access to the MCP service." }

& (Join-Path $PSScriptRoot "deploy_current.ps1") `
    -ProjectId $ProjectId `
    -ProjectNumber $ProjectNumber `
    -Region $Region `
    -ServiceName $ApiServiceName `
    -Repository $Repository `
    -ImageTag $ImageTag `
    -IapMember $IapMember `
    -McpMode remote `
    -McpPlacesUrl $mcpUrl `
    -McpPlacesAudience $mcpAudience `
    -GcloudPath $GcloudPath
if (-not $?) { throw "API deployment with plant-location MCP failed." }

& $GcloudPath run services describe $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="yaml(status.url,status.latestReadyRevisionName)"
