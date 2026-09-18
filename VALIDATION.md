# Validation

## Aiven Runtime and Cloudflare R2 — 18 September 2026

Validated deployed commit `0181d788b19cf1507618af413a459566f2f37917` with the worker Runtime setting `LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL=false`. The worker Dockerfile now supplies the same default for future fresh deployments; that template update remains for user review and push.

### Passed

- Built and scanned both pinned Langfuse v4.38.0 images on Runtime. Web exposes HTTP 8080; worker has an empty public port list and logs a loopback-only listener on 3030.
- Provisioned PostgreSQL 17 (`startup-4`), ClickHouse 26.3 (`startup-8`, single shard), Valkey 8.1 (`startup-2`, noeviction and RDB persistence) and two Runtime apps (`startup-200-4096`, 4 GiB each).
- Native web startup completed PostgreSQL and ClickHouse schema migrations; the dedicated Replicated ClickHouse database initially contained 13 tables. Web health returned HTTP 200 and version 4.38.0.
- Correct native account credentials produced an authenticated session; an incorrect password did not. Invalid project API keys returned HTTP 401 on the v4 observation endpoint. The native login page rendered without public signup controls.
- Created a private R2 Standard bucket in Western Europe. Verified S3 write/read/delete and list access; removed the disposable connectivity-check object. Public bucket access remains disabled. CORS allows only the deployed web origin, GET/HEAD/PUT, and ETag exposure.
- Sent a synthetic OTLP trace with `x-langfuse-ingestion-version: 4`. Confirmed its raw event object in R2 and the worker-processed observation through `/api/public/v2/observations` filtered by trace ID. No LLM calls or provider keys were used.
- Powered both Runtime apps off and back on. Verified account login and the first observation persisted, then sent and retrieved a second processed trace. New process IDs and worker startup logs confirmed the restart.
- Eleven Python tests passed, including URL/secrets validation, TLS configuration, migration credential encoding, S3 prefixes, private worker binding, OTLP payload and fail-closed upstream migration patch checks. Both Compose manifests were previously parsed successfully.

### Compatibility findings

- **Valkey trust:** the service uses a public Let's Encrypt certificate. An explicit project-only Redis CA replaces Node's public roots and failed certificate verification. The fixed starter supplies a combined system/project CA bundle. A live Node check reproduced the old failure and verified the corrected connection. Certificate and hostname verification stay enabled.
- **Fresh v4 installations only:** Langfuse's optional historic backfill attempted `SYSTEM STOP MERGES`, which Aiven does not grant to the service administrator. Verified that the legacy `traces`, `observations` and `dataset_run_items_rmt` tables were empty, then disabled the historic backfill using its supported environment gate. Normal schema migrations and unrelated background migrations remain enabled. Earlier failed attempts remain recorded in PostgreSQL; they are dormant, not falsely marked completed. After restart, the worker reports no background migrations to run.
- **Runtime health checks:** Runtime's OCI build ignores Dockerfile HEALTHCHECK directives. Verification used the external web health endpoint, startup logs and end-to-end ingestion rather than relying on image health checks.
- **v4 API:** deprecated `/api/public/traces` routes return 404 in v4. Use `/api/public/v2/observations` to retrieve spans and filter by trace ID.

### Costs and remaining scope

The tested stack's base price in AWS eu-west-1 is approximately $0.66971/hour ($16.07/day), excluding variable Aiven storage and R2 overage. This is a demo sizing reference, not a tested production minimum.

Not validated: authenticated observation rendering in the browser, browser media upload/download, Console Compose scanner provisioning, local Docker Compose startup, representative load, backups/restores, database outages, multi-replica operation or migration of existing v3 data. The login page was inspected in-browser; account/session and observation checks used HTTP APIs. Batch exports are disabled. Do not treat this demo as a validated upgrade path or production deployment.
