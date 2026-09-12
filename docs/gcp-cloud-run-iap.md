# Single-environment Cloud Run deployment with IAP

The current deployment intentionally uses one GCP environment. Direct Cloud Run Identity-Aware
Proxy protects both the bundled React application and the same-origin `/api/v1` path. `/v1` remains
the canonical OpenAPI path. The application verifies every `X-Goog-IAP-JWT-Assertion` as a second
control and derives an internal UUID from the verified issuer and subject.

## One-time GitHub configuration

Configure Workload Identity Federation for the repository and add these GitHub repository variables:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOY_SERVICE_ACCOUNT`
- `IAP_MEMBER`, for example `user:owner@example.com`

The deployment service account needs only the roles required to submit builds, update the existing
Cloud Run service/job, act as their service accounts, enable IAP, and edit the two relevant IAM
policies. Do not add a service-account JSON key to GitHub.

For an external Google account or a project without an organization, the first IAP activation may
require one manual visit to Cloud Run **Security > Identity-Aware Proxy**. Open **Edit policy**, then
**Configure in IAP**, configure the OAuth consent screen with an **External** audience, and choose
**Auto generate credentials**. Return to the Cloud Run IAP policy and grant the intended account the
**IAP-secured Web App User** role. This is the only interactive setup step, and it must happen before
the deployment script can grant an out-of-organization principal.

## Release flow

Run the `Deploy current environment` workflow, or execute `scripts/deploy_current.ps1` with an
authenticated Google Cloud CLI. The script performs these operations in order:

1. builds an immutable image containing FastAPI and the React production bundle;
2. updates and executes `advisor-bootstrap`, which applies Alembic before loading demo data;
3. deploys `advisor-api` with IAP required, resets the category configuration to the image default
   (`PLANT,DOG`), uses deterministic explanations, keeps MCP disabled, and enables redacted
   LangSmith tracing;
4. grants only the IAP service agent Cloud Run invocation and the configured user/group IAP access.

The LLM and MCP flags deliberately remain off during this release. Enable each only after its
provider-specific evaluation and degradation tests pass.
