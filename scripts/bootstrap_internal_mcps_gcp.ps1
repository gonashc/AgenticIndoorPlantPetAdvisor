param(
    [string]$ProjectId = "indoorplantpetadvisor",
    [string]$InstanceName = "advisor-postgres",
    [string]$GcloudPath = "gcloud"
)

$ErrorActionPreference = "Continue"
$serviceAccounts = @(
    @{
        Name = "advisor-catalog-mcp"
        DisplayName = "Advisor catalog MCP runtime"
        Database = $true
    },
    @{
        Name = "advisor-care-plan-mcp"
        DisplayName = "Advisor care-plan MCP runtime"
        Database = $true
    },
    @{
        Name = "advisor-regulations-mcp"
        DisplayName = "Advisor regulations MCP runtime"
        Database = $false
    },
    @{
        Name = "advisor-commerce-mcp"
        DisplayName = "Advisor commerce MCP runtime"
        Database = $false
    }
)

& $GcloudPath services enable `
    run.googleapis.com `
    sqladmin.googleapis.com `
    --project=$ProjectId `
    --quiet
if ($LASTEXITCODE -ne 0) { throw "Failed to enable internal MCP service APIs." }

$databaseUsers = @(
    & $GcloudPath sql users list `
        --project=$ProjectId `
        --instance=$InstanceName `
        --format="value(name)"
)
if ($LASTEXITCODE -ne 0) { throw "Failed to list Cloud SQL users." }

foreach ($service in $serviceAccounts) {
    $serviceAccount = "$($service.Name)@$ProjectId.iam.gserviceaccount.com"
    & $GcloudPath iam service-accounts describe $serviceAccount `
        --project=$ProjectId `
        --quiet 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $GcloudPath iam service-accounts create $service.Name `
            --project=$ProjectId `
            --display-name="$($service.DisplayName)" `
            --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create service account $serviceAccount."
        }
    }

    if ($service.Database) {
        foreach ($role in @("roles/cloudsql.client", "roles/cloudsql.instanceUser")) {
            & $GcloudPath projects add-iam-policy-binding $ProjectId `
                --member="serviceAccount:$serviceAccount" `
                --role=$role `
                --condition=None `
                --quiet | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to grant $role to $serviceAccount."
            }
        }

        $databaseUser = "$($service.Name)@$ProjectId.iam"
        if ($databaseUsers -notcontains $databaseUser) {
            & $GcloudPath sql users create $databaseUser `
                --project=$ProjectId `
                --instance=$InstanceName `
                --type=cloud_iam_service_account `
                --quiet
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create Cloud SQL IAM user for $serviceAccount."
            }
            $databaseUsers += $databaseUser
        }
    }
}

"Internal MCP GCP prerequisites are ready."
