param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ProjectNumber = "201638055698",
    [string]$Region = "us-east1",
    [string]$ServiceName = "advisor-adoption-mcp",
    [string]$PlacesServiceName = "advisor-places-mcp",
    [string]$ApiServiceName = "advisor-api",
    [string]$Repository = "advisor",
    [string]$SecretName = "rescuegroups-api-key",
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

$mcpServiceAccount = "advisor-adoption-mcp@$ProjectId.iam.gserviceaccount.com"
$apiServiceAccount = "advisor-api@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/adoption-mcp:$ImageTag"

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Secret $SecretName does not exist. Bootstrap the RescueGroups key first."
}

$provisionalAudience = "https://$ServiceName-$ProjectNumber.$Region.run.app"
$provisionalHost = ([Uri]$provisionalAudience).Host
$runtimeSettings = (
    "APP_ENV=production,MCP_ALLOWED_HOSTS=$provisionalHost," +
    "ADOPTION_ALLOWED_LINK_HOSTS=rescuegroups.org"
)

& $GcloudPath builds submit `
    --project=$ProjectId `
    --region=$Region `
    --config=services/adoption_mcp/cloudbuild.yaml `
    --substitutions="_IMAGE=$image" `
    .
if ($LASTEXITCODE -ne 0) { throw "Adoption MCP image build failed." }

& $GcloudPath run deploy $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --service-account=$mcpServiceAccount `
    --set-env-vars=$runtimeSettings `
    --set-secrets="RESCUEGROUPS_API_KEY=$SecretName`:latest" `
    --no-allow-unauthenticated `
    --no-iap `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Adoption MCP deployment failed." }

$mcpAudience = (& $GcloudPath run services describe $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="value(status.url)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $mcpAudience.StartsWith("https://")) {
    throw "Could not read the adoption MCP service URL."
}
$mcpHost = ([Uri]$mcpAudience).Host
$mcpUrl = "$mcpAudience/mcp"
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
if ($LASTEXITCODE -ne 0) { throw "Failed to grant the API access to the adoption MCP service." }

$placesAudience = (& $GcloudPath run services describe $PlacesServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="value(status.url)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $placesAudience.StartsWith("https://")) {
    throw "The deployed Places MCP service is required before connecting Adoption MCP."
}

& (Join-Path $PSScriptRoot "deploy_current.ps1") `
    -ProjectId $ProjectId `
    -ProjectNumber $ProjectNumber `
    -Region $Region `
    -ServiceName $ApiServiceName `
    -Repository $Repository `
    -ImageTag $ImageTag `
    -IapMember $IapMember `
    -McpMode remote `
    -McpPlacesUrl "$placesAudience/mcp" `
    -McpPlacesAudience $placesAudience `
    -McpAdoptionUrl $mcpUrl `
    -McpAdoptionAudience $mcpAudience `
    -GcloudPath $GcloudPath
if (-not $?) { throw "API deployment with adoption MCP failed." }

& $GcloudPath run services describe $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="yaml(status.url,status.latestReadyRevisionName)"
