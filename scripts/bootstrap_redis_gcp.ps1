param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$Region = "us-east1",
    [string]$InstanceName = "advisor-cache",
    [int]$SizeGb = 1,
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
& $GcloudPath services enable redis.googleapis.com --project=$ProjectId --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable the Memorystore for Redis API." }

& $GcloudPath redis instances describe $InstanceName --project=$ProjectId `
    --region=$Region --quiet 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    & $GcloudPath redis instances create $InstanceName `
        --project=$ProjectId `
        --region=$Region `
        --size=$SizeGb `
        --tier=basic `
        --redis-version=redis_7_2 `
        --network=default `
        --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the Redis instance." }
}

$host = (& $GcloudPath redis instances describe $InstanceName --project=$ProjectId `
    --region=$Region --format="value(host)").Trim()
$port = (& $GcloudPath redis instances describe $InstanceName --project=$ProjectId `
    --region=$Region --format="value(port)").Trim()
if (-not $host -or -not $port) { throw "Could not read the Redis endpoint." }

"RedisUrl=redis://$host`:$port"
