param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ProjectNumber = "201638055698",
    [string]$Region = "us-east1",
    [string]$ServiceName = "advisor-you-mcp",
    [string]$Repository = "advisor",
    [string]$SecretName = "you-api-key",
    [string]$ImageTag = "",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
if (-not $ImageTag) { $ImageTag = (& git rev-parse --short=12 HEAD).Trim() }
if ($ImageTag -notmatch '^[a-zA-Z0-9_.-]+$') { throw "ImageTag is invalid." }

$mcpServiceAccount = "advisor-you-mcp@$ProjectId.iam.gserviceaccount.com"
$apiServiceAccount = "advisor-api@$ProjectId.iam.gserviceaccount.com"
$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/you-mcp:$ImageTag"
$provisionalAudience = "https://$ServiceName-$ProjectNumber.$Region.run.app"
$provisionalHost = ([Uri]$provisionalAudience).Host

& $GcloudPath iam service-accounts describe $mcpServiceAccount --project=$ProjectId --quiet |
    Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "You MCP service account does not exist. Run bootstrap_you_mcp_gcp.ps1 first."
}

& $GcloudPath secrets describe $SecretName --project=$ProjectId --quiet | Out-Null
if ($LASTEXITCODE -ne 0) { throw "You.com secret $SecretName does not exist." }

& $GcloudPath builds submit --project=$ProjectId --region=$Region `
    --config=services/you_mcp/cloudbuild.yaml --substitutions="_IMAGE=$image" .
if ($LASTEXITCODE -ne 0) { throw "You MCP image build failed." }

& $GcloudPath run deploy $ServiceName `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --service-account=$mcpServiceAccount `
    --set-env-vars="APP_ENV=production,YOU_PROVIDER=api,MCP_ALLOWED_HOSTS=$provisionalHost" `
    --set-secrets="YOU_API_KEY=$SecretName`:latest" `
    --no-allow-unauthenticated `
    --no-iap `
    --max=3 `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "You MCP deployment failed." }

$audience = (& $GcloudPath run services describe $ServiceName --project=$ProjectId `
    --region=$Region --format="value(status.url)").Trim()
if ($LASTEXITCODE -ne 0 -or -not $audience.StartsWith("https://")) {
    throw "Could not read the You MCP URL."
}
$canonicalHost = ([Uri]$audience).Host
if ($canonicalHost -ne $provisionalHost) {
    & $GcloudPath run services update $ServiceName --project=$ProjectId --region=$Region `
        --update-env-vars="MCP_ALLOWED_HOSTS=$canonicalHost" --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to update the You MCP host allowlist." }
}

& $GcloudPath run services add-iam-policy-binding $ServiceName `
    --project=$ProjectId --region=$Region `
    --member="serviceAccount:$apiServiceAccount" --role=roles/run.invoker --quiet | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to grant API invocation of You MCP." }

& $GcloudPath run services describe $ServiceName --project=$ProjectId --region=$Region `
    --format="yaml(status.url,status.latestReadyRevisionName)"
