# Validation

## Local checks — 18 September 2026

- Ten Python standard-library tests passed: required secrets and initial account settings, malformed URLs, credential-safe validation errors, mandatory CA validation, HTTPS requirements, PostgreSQL/Valkey TLS configuration, encoded ClickHouse migration credentials, S3 prefix separation, private worker binding, synthetic OTLP payload and fail-closed migration patch behavior.
- Verified official Langfuse web/worker v4.38.0 image manifests and pinned both registry digests.
- Inspected versioned upstream Dockerfiles, entrypoints, environment schemas, Redis TLS implementation, health routes and ClickHouse migration launcher.
- Applied the TLS/credential patch to the actual pinned upstream source and passed shell syntax validation. Both Compose manifests parsed successfully.
- Queried Aiven's current service schema: ClickHouse 26.3 is available; Runtime supports an independent `containerfile_path` and an empty public port list.

These checks validate the starter's configuration logic, not successful Langfuse operation. There is no local Docker/Podman engine. The live deployment findings below supersede the original pre-deployment status.

## Required live validation after push and storage setup

1. Build both images on Runtime, verify image scans and the migration patch against the pinned image.
2. Provision dedicated PostgreSQL 17, ClickHouse 26.3 and Valkey with noeviction/persistence; verify connection ports, trust and credentials.
3. Pre-create the Replicated ClickHouse database. Verify all Langfuse migrations and grants against Aiven's managed table-engine/DDL behavior. Confirm UTC and a single shard. This compatibility check is still pending.
4. Confirm the private R2 bucket's write, read, list and delete permissions. Confirm prefix isolation and browser media CORS. Record actual provider/region.
5. Start web, confirm migrations and account initialization, reject public signup, and test incorrect/correct login.
6. Start worker without public ingress; verify queue consumption and health logs.
7. Send the synthetic OTLP trace; confirm API acceptance, raw event object, worker processing and the observation appearing in the UI. Test incorrect API keys.
8. Restart both Runtime apps; verify account/project state and observations persist, then ingest another trace.
9. Test media upload/download if enabled. Batch exports are disabled by default.
10. Record actual plans and prices. Validate Console Compose detection separately from API/MCP deployment.

Also pending: local Docker Compose startup, representative load, queue recovery after outages, backups/restores and multi-replica operation. Do not describe this template as production-ready or its Aiven/R2 integration as tested until these checks pass.

## First Runtime deployment — 18 September 2026

- Deployed web from commit `63e2fa22409f8c1031f2cf57be3ad11baf64ffb9` on Runtime `startup-200-4096`. Image build and scan completed; `/api/public/health` returned HTTP 200 with version 4.38.0.
- Provisioned PostgreSQL 17 (`startup-4`), ClickHouse 26.3 (`startup-8`) and Valkey 8.1 (`startup-2`, noeviction, RDB persistence). The dedicated ClickHouse database uses the Replicated engine; startup created 13 tables. Full ingestion compatibility remains pending.
- Created a private Cloudflare R2 Standard bucket in Western Europe. Verified S3 object write/read/delete and removed the test object. Configured CORS for the exact web origin with GET/HEAD/PUT and ETag exposure. Public bucket access is disabled. Browser media behavior is not yet tested.
- Found that the live Valkey endpoint uses a public Let's Encrypt certificate. An explicit project-only Redis CA replaces Node's public roots and caused `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`. Changed the starter to use its combined system/project CA bundle for Redis. A live Node TLS check reproduced the failure with the old bundle and connected successfully with the new bundle, with verification enabled.
- Eleven local tests now pass, including a regression check for both public and project roots in the Redis bundle.
- The TLS fix is staged for user review; it has not yet been committed, pushed or rebuilt on Runtime. Worker deployment, login checks, end-to-end OTLP processing, media checks and restart persistence remain pending. The web health response alone does not establish that ingestion works.
- Planned complete stack base price: approximately $0.66971/hour ($16.07/day), excluding variable storage and R2 overage. The worker is not yet provisioned.
