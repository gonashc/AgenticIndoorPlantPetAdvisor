param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ProjectNumber = "201638055698",
    [string]$Region = "us-east1",
    [string]$ServiceName = "advisor-api",
    [string]$Repository = "advisor",
    [string]$ImageTag = "",
    [string]$IapMember = "user:gonashc@gmail.com",
    [ValidateSet("disabled", "remote")]
    [string]$McpMode = "disabled",
    [string]$McpPlacesUrl = "",
    [string]$McpPlacesAudience = "",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
if (-not $ImageTag) {
    $ImageTag = (& git rev-parse --short=12 HEAD).Trim()
}
if ($ImageTag -notmatch '^[a-zA-Z0-9_.-]+$') {
    throw "ImageTag contains unsupported characters."
}
if ($IapMember -notmatch '^(user|group):[^@\s]+@[^@\s]+$') {
    throw "IapMember must be a user: or group: principal."
}
if ($McpMode -eq "remote") {
    if ($McpPlacesUrl -notmatch '^https://.+/mcp$') {
        throw "McpPlacesUrl must be an HTTPS MCP endpoint when remote mode is enabled."
    }
    if ($McpPlacesAudience -notmatch '^https://[^/]+$') {
        throw "McpPlacesAudience must be an HTTPS origin without a path."
    }
}

$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/api:$ImageTag"
$audience = "/projects/$ProjectNumber/locations/$Region/services/$ServiceName"
$iapServiceAgent = "serviceAccount:service-$ProjectNumber@gcp-sa-iap.iam.gserviceaccount.com"

& $GcloudPath services enable iap.googleapis.com --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable the IAP API." }

& $GcloudPath builds submit --project=$ProjectId --region=$Region --tag=$image .
if ($LASTEXITCODE -ne 0) { throw "Cloud Build failed." }

& $GcloudPath run jobs update advisor-bootstrap `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to update the migration job image." }

& $GcloudPath run jobs execute advisor-bootstrap `
    --project=$ProjectId `
    --region=$Region `
    --wait `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Database migration/bootstrap failed." }

$runtimeSettings = @(
    "APP_ENV=production",
    "AUTH_MODE=google_iap",
    "IAP_AUDIENCE=$audience",
    "WEB_DIST_DIR=/app/web",
    "LANGSMITH_TRACING=true",
    "LANGSMITH_PROJECT=IndoorPlantandPetAdvisor",
    "LANGSMITH_HIDE_INPUTS=true",
    "LANGSMITH_HIDE_OUTPUTS=true",
    "EXPLANATION_MODE=deterministic",
    "MCP_MODE=$McpMode",
    "MCP_AUTH_MODE=$(if ($McpMode -eq 'remote') { 'google_cloud_run' } else { 'none' })"
)
$settingsToRemove = @(
    "ENABLED_CATEGORIES",
    "MCP_ADOPTION_URL",
    "MCP_ADOPTION_AUDIENCE",
    # Remove malformed entries left by the original delimiter-based deployment command.
    ":APP_ENV",
    "DOG:WEB_DIST_DIR"
)
if ($McpMode -eq "remote") {
    $runtimeSettings += "MCP_PLACES_URL=$McpPlacesUrl"
    $runtimeSettings += "MCP_PLACES_AUDIENCE=$McpPlacesAudience"
}
else {
    $settingsToRemove += "MCP_PLACES_URL"
    $settingsToRemove += "MCP_PLACES_AUDIENCE"
}
$runtimeSettings = $runtimeSettings -join ','
$settingsToRemove = $settingsToRemove -join ','

& $GcloudPath run deploy $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --service-account="advisor-api@$ProjectId.iam.gserviceaccount.com" `
    --network=default `
    --subnet=default `
    --vpc-egress=private-ranges-only `
    --remove-env-vars=$settingsToRemove `
    --update-env-vars=$runtimeSettings `
    --update-secrets="LANGSMITH_API_KEY=langsmith-api-key:latest" `
    --no-allow-unauthenticated `
    --iap `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed." }

& $GcloudPath run services add-iam-policy-binding $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --member=$iapServiceAgent `
    --role=roles/run.invoker `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to grant the IAP service agent invoke access." }

$iapPolicyJson = & $GcloudPath iap web get-iam-policy `
    --project=$ProjectId `
    --region=$Region `
    --resource-type=cloud-run `
    --service=$ServiceName `
    --format=json
if ($LASTEXITCODE -ne 0) { throw "Failed to read the IAP access policy." }
$iapPolicy = $iapPolicyJson | ConvertFrom-Json
$iapBinding = @($iapPolicy.bindings) | Where-Object {
    $_.role -eq "roles/iap.httpsResourceAccessor"
}
if (-not ($iapBinding.members -contains $IapMember)) {
    & $GcloudPath iap web add-iam-policy-binding `
        --project=$ProjectId `
        --region=$Region `
        --resource-type=cloud-run `
        --service=$ServiceName `
        --member=$IapMember `
        --role=roles/iap.httpsResourceAccessor `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to grant the requested principal IAP access." }
}

& $GcloudPath run services describe $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --format="yaml(status.url,status.latestReadyRevisionName)"
