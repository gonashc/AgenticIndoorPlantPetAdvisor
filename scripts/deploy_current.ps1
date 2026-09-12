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
    [string]$McpAdoptionUrl = "",
    [string]$McpAdoptionAudience = "",
    [string]$McpCarePlanUrl = "",
    [string]$McpCarePlanAudience = "",
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
    if (-not $McpPlacesUrl -and -not $McpAdoptionUrl -and -not $McpCarePlanUrl) {
        throw "At least one MCP endpoint is required when remote mode is enabled."
    }
    foreach ($endpoint in @($McpPlacesUrl, $McpAdoptionUrl, $McpCarePlanUrl) | Where-Object { $_ }) {
        if ($endpoint -notmatch '^https://.+/mcp$') {
            throw "Each MCP URL must be an HTTPS endpoint ending in /mcp."
        }
    }
    if ($McpPlacesUrl -and $McpPlacesAudience -notmatch '^https://[^/]+$') {
        throw "The Places MCP endpoint requires an HTTPS audience without a path."
    }
    if ($McpAdoptionUrl -and $McpAdoptionAudience -notmatch '^https://[^/]+$') {
        throw "The Adoption MCP endpoint requires an HTTPS audience without a path."
    }
    if ($McpCarePlanUrl -and $McpCarePlanAudience -notmatch '^https://[^/]+$') {
        throw "The Care Plan MCP endpoint requires an HTTPS audience without a path."
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
    # Remove malformed entries left by the original delimiter-based deployment command.
    ":APP_ENV",
    "DOG:WEB_DIST_DIR"
)
if ($McpMode -eq "remote") {
    if ($McpPlacesUrl) {
        $runtimeSettings += "MCP_PLACES_URL=$McpPlacesUrl"
        $runtimeSettings += "MCP_PLACES_AUDIENCE=$McpPlacesAudience"
    }
    else {
        $settingsToRemove += "MCP_PLACES_URL"
        $settingsToRemove += "MCP_PLACES_AUDIENCE"
    }
    if ($McpAdoptionUrl) {
        $runtimeSettings += "MCP_ADOPTION_URL=$McpAdoptionUrl"
        $runtimeSettings += "MCP_ADOPTION_AUDIENCE=$McpAdoptionAudience"
    }
    else {
        $settingsToRemove += "MCP_ADOPTION_URL"
        $settingsToRemove += "MCP_ADOPTION_AUDIENCE"
    }
    if ($McpCarePlanUrl) {
        $runtimeSettings += "MCP_CARE_PLAN_URL=$McpCarePlanUrl"
        $runtimeSettings += "MCP_CARE_PLAN_AUDIENCE=$McpCarePlanAudience"
    }
    else {
        $settingsToRemove += "MCP_CARE_PLAN_URL"
        $settingsToRemove += "MCP_CARE_PLAN_AUDIENCE"
    }
}
else {
    $settingsToRemove += "MCP_PLACES_URL"
    $settingsToRemove += "MCP_PLACES_AUDIENCE"
    $settingsToRemove += "MCP_ADOPTION_URL"
    $settingsToRemove += "MCP_ADOPTION_AUDIENCE"
    $settingsToRemove += "MCP_CARE_PLAN_URL"
    $settingsToRemove += "MCP_CARE_PLAN_AUDIENCE"
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
