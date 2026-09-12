param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$ProjectNumber = "201638055698",
    [string]$Region = "us-east1",
    [string]$InstanceName = "advisor-postgres",
    [string]$Repository = "advisor",
    [string]$ImageTag = "",
    [string]$GcloudPath = "gcloud"
)

. (Join-Path $PSScriptRoot "gcloud_dictionary.ps1")

$ErrorActionPreference = "Continue"
if (-not $ImageTag) {
    $ImageTag = (& git rev-parse --short=12 HEAD).Trim()
}
if ($ImageTag -notmatch '^[a-zA-Z0-9_.-]+$') {
    throw "ImageTag contains unsupported characters."
}

$apiServiceAccount = "advisor-api@$ProjectId.iam.gserviceaccount.com"
$migrationServiceAccount = "advisor-migrations@$ProjectId.iam.gserviceaccount.com"
$instanceConnectionName = "$ProjectId`:$Region`:$InstanceName"
$catalogDatabaseUser = "advisor-catalog-mcp@$ProjectId.iam"
$carePlanDatabaseUser = "advisor-care-plan-mcp@$ProjectId.iam"
$iapAudience = "/projects/$ProjectNumber/locations/$Region/services/advisor-api"

$services = @(
    @{
        Key = "catalog"
        ServiceName = "advisor-catalog-mcp"
        Config = "services/catalog_mcp/cloudbuild.yaml"
        RuntimeAccount = "advisor-catalog-mcp@$ProjectId.iam.gserviceaccount.com"
    },
    @{
        Key = "regulations"
        ServiceName = "advisor-regulations-mcp"
        Config = "services/regulations_mcp/cloudbuild.yaml"
        RuntimeAccount = "advisor-regulations-mcp@$ProjectId.iam.gserviceaccount.com"
    },
    @{
        Key = "commerce"
        ServiceName = "advisor-commerce-mcp"
        Config = "services/commerce_mcp/cloudbuild.yaml"
        RuntimeAccount = "advisor-commerce-mcp@$ProjectId.iam.gserviceaccount.com"
    },
    @{
        Key = "care-plan"
        ServiceName = "advisor-care-plan-mcp"
        Config = "services/care_plan_mcp/cloudbuild.yaml"
        RuntimeAccount = "advisor-care-plan-mcp@$ProjectId.iam.gserviceaccount.com"
    }
)

foreach ($service in $services) {
    & $GcloudPath iam service-accounts describe $service.RuntimeAccount `
        --project=$ProjectId `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Missing $($service.RuntimeAccount). Run bootstrap_internal_mcps_gcp.ps1 first."
    }
    $service.Image = "$Region-docker.pkg.dev/$ProjectId/$Repository/$($service.Key)-mcp:$ImageTag"
    & $GcloudPath builds submit `
        --project=$ProjectId `
        --region=$Region `
        --config="$($service.Config)" `
        --substitutions="_IMAGE=$($service.Image)" `
        .
    if ($LASTEXITCODE -ne 0) { throw "$($service.ServiceName) image build failed." }
}

$catalogImage = ($services | Where-Object { $_.Key -eq "catalog" }).Image
$grantSettings = @(
    "APP_ENV=test",
    "DATABASE_MODE=cloud_sql",
    "INSTANCE_CONNECTION_NAME=$instanceConnectionName",
    "DB_USER=advisor-migrations@$ProjectId.iam",
    "DB_NAME=advisor",
    "CLOUD_SQL_ENABLE_IAM_AUTH=true",
    "CLOUD_SQL_IP_TYPE=PRIVATE",
    "DB_POOL_SIZE=2",
    "DB_MAX_OVERFLOW=0",
    "CATALOG_MCP_DATABASE_USER=$catalogDatabaseUser",
    "CARE_PLAN_MCP_DATABASE_USER=$carePlanDatabaseUser"
) -join ','

& $GcloudPath run jobs deploy advisor-mcp-db-grants `
    --project=$ProjectId `
    --region=$Region `
    --image=$catalogImage `
    --service-account=$migrationServiceAccount `
    --network=default `
    --subnet=default `
    --vpc-egress=private-ranges-only `
    --set-env-vars=$grantSettings `
    --command=python `
    --args=scripts/grant_mcp_database_access.py `
    --max-retries=0 `
    --task-timeout=5m `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to configure the MCP database grant job." }

& $GcloudPath run jobs execute advisor-mcp-db-grants `
    --project=$ProjectId `
    --region=$Region `
    --wait `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "MCP database grants failed." }

foreach ($service in $services) {
    $provisionalAudience = "https://$($service.ServiceName)-$ProjectNumber.$Region.run.app"
    $provisionalHost = ([Uri]$provisionalAudience).Host
    $runtimeSettings = @(
        "APP_ENV=production",
        "ENABLED_CATEGORIES=PLANT,DOG,CAT",
        "MCP_ALLOWED_HOSTS=$provisionalHost"
    )
    $networkArguments = @()
    $labelArguments = @()
    if ($service.Key -eq "catalog") {
        $runtimeSettings += @(
            "DATABASE_MODE=cloud_sql",
            "INSTANCE_CONNECTION_NAME=$instanceConnectionName",
            "DB_USER=$catalogDatabaseUser",
            "DB_NAME=advisor",
            "CLOUD_SQL_ENABLE_IAM_AUTH=true",
            "CLOUD_SQL_IP_TYPE=PRIVATE"
        )
        $networkArguments = @(
            "--network=default",
            "--subnet=default",
            "--vpc-egress=private-ranges-only"
        )
    }
    elseif ($service.Key -eq "care-plan") {
        $runtimeSettings += @(
            "AUTH_MODE=google_iap",
            "IAP_AUDIENCE=$iapAudience",
            "DATABASE_MODE=cloud_sql",
            "INSTANCE_CONNECTION_NAME=$instanceConnectionName",
            "DB_USER=$carePlanDatabaseUser",
            "DB_NAME=advisor",
            "CLOUD_SQL_ENABLE_IAM_AUTH=true",
            "CLOUD_SQL_IP_TYPE=PRIVATE"
        )
        $networkArguments = @(
            "--network=default",
            "--subnet=default",
            "--vpc-egress=private-ranges-only"
        )
        $labelArguments = @("--update-labels=advisor-care-plan-contract=v1")
    }
    elseif ($service.Key -eq "regulations") {
        $runtimeSettings += "REGULATIONS_PROVIDER=disabled"
    }
    elseif ($service.Key -eq "commerce") {
        $runtimeSettings += "COMMERCE_PROVIDER=disabled"
    }
    $runtimeSettings = ConvertTo-GcloudDictionaryArgument -Entry $runtimeSettings

    & $GcloudPath run deploy $service.ServiceName `
        --project=$ProjectId `
        --region=$Region `
        --image="$($service.Image)" `
        --service-account="$($service.RuntimeAccount)" `
        @networkArguments `
        @labelArguments `
        --set-env-vars=$runtimeSettings `
        --no-allow-unauthenticated `
        --no-iap `
        --max=3 `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "$($service.ServiceName) deployment failed." }

    $audience = (& $GcloudPath run services describe $service.ServiceName `
        --project=$ProjectId `
        --region=$Region `
        --format="value(status.url)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $audience.StartsWith("https://")) {
        throw "Could not read the $($service.ServiceName) URL."
    }
    $canonicalHost = ([Uri]$audience).Host
    if ($canonicalHost -ne $provisionalHost) {
        & $GcloudPath run services update $service.ServiceName `
            --project=$ProjectId `
            --region=$Region `
            --update-env-vars="MCP_ALLOWED_HOSTS=$canonicalHost" `
            --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to set the canonical host for $($service.ServiceName)."
        }
    }

    & $GcloudPath run services add-iam-policy-binding $service.ServiceName `
        --project=$ProjectId `
        --region=$Region `
        --member="serviceAccount:$apiServiceAccount" `
        --role=roles/run.invoker `
        --quiet | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to grant API invocation of $($service.ServiceName)."
    }
}

& $GcloudPath run services list `
    --project=$ProjectId `
    --region=$Region `
    --filter="metadata.name:advisor AND metadata.name:mcp" `
    --format="table(metadata.name,status.url,status.latestReadyRevisionName)"
