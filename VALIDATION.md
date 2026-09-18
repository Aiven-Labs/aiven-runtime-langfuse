# Validation

## Local checks — 18 September 2026

- Ten Python standard-library tests passed: required secrets and initial account settings, malformed URLs, credential-safe validation errors, mandatory CA validation, HTTPS requirements, PostgreSQL/Valkey TLS configuration, encoded ClickHouse migration credentials, S3 prefix separation, private worker binding, synthetic OTLP payload and fail-closed migration patch behavior.
- Verified official Langfuse web/worker v4.38.0 image manifests and pinned both registry digests.
- Inspected versioned upstream Dockerfiles, entrypoints, environment schemas, Redis TLS implementation, health routes and ClickHouse migration launcher.
- Applied the TLS/credential patch to the actual pinned upstream source and passed shell syntax validation. Both Compose manifests parsed successfully.
- Queried Aiven's current service schema: ClickHouse 26.3 is available; Runtime supports an independent `containerfile_path` and an empty public port list.

These checks validate the starter's configuration logic, not successful Langfuse operation. There is no local Docker/Podman engine. No Langfuse services, R2 bucket or Cloudflare credentials have been created by this task.

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
