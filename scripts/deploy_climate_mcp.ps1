param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ProjectNumber = "201638055698",
    [string]$Region = "us-east1",
    [string]$ServiceName = "advisor-climate-mcp",
    [string]$Repository = "advisor",
    [string]$ImageTag = "",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
if (-not $ImageTag) {
    $ImageTag = (& git rev-parse --short=12 HEAD).Trim()
}
if ($ImageTag -notmatch '^[a-zA-Z0-9_.-]+$') {
    throw "ImageTag contains unsupported characters."
}

$mcpServiceAccount = "advisor-climate-mcp@$ProjectId.iam.gserviceaccount.com"
$apiServiceAccount = "advisor-api@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/climate-mcp:$ImageTag"
$provisionalAudience = "https://$ServiceName-$ProjectNumber.$Region.run.app"
$provisionalHost = ([Uri]$provisionalAudience).Host

& $GcloudPath iam service-accounts describe $mcpServiceAccount --project=$ProjectId --quiet |
    Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Climate MCP service account does not exist. Run its bootstrap script first."
}

& $GcloudPath builds submit `
    --project=$ProjectId `
    --region=$Region `
    --config=services/climate_mcp/cloudbuild.yaml `
    --substitutions="_IMAGE=$image" `
    .
if ($LASTEXITCODE -ne 0) { throw "Climate MCP image build failed." }

& $GcloudPath run deploy $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --service-account=$mcpServiceAccount `
    --set-env-vars="APP_ENV=production,MCP_ALLOWED_HOSTS=$provisionalHost" `
    --no-allow-unauthenticated `
    --no-iap `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Climate MCP deployment failed." }

$mcpAudience = (& $GcloudPath run services describe $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="value(status.url)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $mcpAudience.StartsWith("https://")) {
    throw "Could not read the climate MCP service URL."
}
$mcpHost = ([Uri]$mcpAudience).Host
if ($mcpHost -ne $provisionalHost) {
    & $GcloudPath run services update $ServiceName `
        --project=$ProjectId `
        --region=$Region `
        --update-env-vars="MCP_ALLOWED_HOSTS=$mcpHost" `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to set the canonical MCP hostname." }
}

& $GcloudPath run services add-iam-policy-binding $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --member="serviceAccount:$apiServiceAccount" `
    --role=roles/run.invoker `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to grant the API access to the climate MCP service." }

& $GcloudPath run services describe $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="yaml(status.url,status.latestReadyRevisionName)"

