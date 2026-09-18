# Langfuse starter for Aiven Runtime

Standalone **Langfuse v4.38.0** with its native web UI and background worker, **Aiven PostgreSQL**, **Aiven ClickHouse**, **Aiven Valkey**, and an external **S3-compatible bucket**. Capture traces, inspect observations and manage prompts without requiring another application template or an LLM provider account.

Both official Langfuse images are pinned by version and registry digest. This is a demo deployment template for new v4 installations. Container builds, native login, R2 trace ingestion, worker processing and persistence across Runtime app restarts have been validated on Aiven. See [VALIDATION.md](VALIDATION.md).

## Architecture

```text
Browser / instrumented application
              |
            HTTPS
              |
       Runtime: Langfuse web -------- PostgreSQL (users, projects, configuration)
              |        |                    |
              |        +------ Valkey ------+--- Runtime: Langfuse worker
              |              (job queue)                  |
              +----------- S3 bucket ---------------------+
                          (raw events/media)             |
                                               ClickHouse (observations)
```

Web and worker are **two Runtime applications from the same repo**, each with one replica. They share exactly the same database services, bucket, `SALT` and `ENCRYPTION_KEY`. The web process runs migrations; the worker consumes queued ingestion events. Only web exposes HTTP port 8080. The worker binds its health server to loopback on 3030 and must have no public Runtime port.

The template uses Langfuse's native login with an initial organization, project and owner account. Public signup is disabled. No traces, provider credentials or model calls are created automatically. [examples/send_trace.py](examples/send_trace.py) sends a synthetic trace when you explicitly run it.

## Prerequisites and suggested sizes

| Component | Demo starting point | Required configuration |
| --- | --- | --- |
| Runtime web | One replica, 4 GiB RAM | Root `Dockerfile`; HTTP 8080 |
| Runtime worker | One replica, 4 GiB RAM | `Dockerfile.worker`; no public ports |
| PostgreSQL | `startup-4` or equivalent 4 GiB, version 17 | Dedicated database; UTC |
| ClickHouse | Single shard, at least 8 GiB RAM | **26.3** on Aiven; dedicated Replicated database; UTC |
| Valkey | At least 2 GiB RAM | Dedicated instance, database 0, **noeviction**, persistence enabled |
| Object storage | Private S3-compatible bucket | Read/write/list/delete access, HTTPS endpoint |

These are starting suggestions, not tested minimums or production sizing. Review available plans and pricing in the target project before provisioning. Plans are selected in Console/API, not enforced by the Compose manifests. Langfuse's upstream production guidance recommends 2 CPU/4 GiB each for web and worker, with additional sizing for the databases; load-test your expected ingestion rate before production.

**Langfuse v4 requires ClickHouse >=25.12.** Explicitly select Aiven 26.3; do not use 25.8. Other managed ClickHouse services, including Aiven, are community-supported by Langfuse. The tested fresh-install configuration and remaining limits are recorded in [VALIDATION.md](VALIDATION.md).

Create the `langfuse` ClickHouse database in Aiven Console/API before starting web. Aiven uses Replicated databases and remaps MergeTree table engines. The wrapper selects Langfuse's unclustered migration syntax (`CLICKHOUSE_CLUSTER_ENABLED=false`) so it does not assume a cluster named `default`; Aiven's database handles DDL replication. Use a **single-shard** service for this starter. Multi-shard routing is outside its scope. The ClickHouse user needs DDL/read/write permissions and access to Langfuse's required system tables; see [upstream requirements](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse). Do not disable TLS or skip failed migrations as a workaround.

This starter supports **new Langfuse v4 installations**, not upgrades with existing v3 data. The worker defaults `LANGFUSE_BACKGROUND_MIGRATION_V4_ENABLE_HISTORIC_BACKFILL=false`: Aiven does not expose the `SYSTEM MERGES` privilege required by the optional v3-to-v4 historic backfill, even when legacy tables are empty. Normal schema migrations and other background migrations stay enabled. For existing Langfuse data, use an upstream-supported migration plan; do not use this setting to skip required data conversion. If deploying the initial image before this default was added, set the variable explicitly in Runtime.

Valkey stores queues, not just a disposable cache. Set its maxmemory policy to `noeviction` and enable service-supported persistence; monitor capacity. Do not share an evicting cache instance. Connection limits, retries and ingestion throughput need review before scaling.

## Cloudflare R2 setup

R2 is the documented S3 provider for this demo; another compatible HTTPS provider can use the same settings. Langfuse documents an R2 configuration in its [blob-storage guide](https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage).

R2 **Standard** currently includes 10 GB-month storage, 1 million Class A operations and 10 million Class B operations monthly, with no egress fee. Usage above the allowance is billed. The allowance does not apply to Infrequent Access. Check [current pricing](https://developers.cloudflare.com/r2/pricing/) and your account's usage; these are account allowances, not a per-template free guarantee.

1. Enable R2 in your Cloudflare account and create a **private Standard bucket** dedicated to this deployment, for example `langfuse-runtime-demo`. Choose the appropriate location/jurisdiction for your data. Keep public access and `r2.dev` disabled.
2. Create S3 API credentials with **Object Read & Write** access scoped to this bucket. Store the access key ID and secret access key in Runtime secrets; never paste them into an issue, chat or Git. A generic Cloudflare bearer API token is not an S3 access key pair.
3. Copy the bucket/account's **S3 API endpoint** from Cloudflare. Usually it is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`; jurisdiction-specific buckets can have a different endpoint, so use the displayed value. Set `S3_REGION=auto`, `S3_FORCE_PATH_STYLE=false`, and `S3_BUCKET` to the bucket name without any path.
4. For browser media uploads, add a bucket CORS policy allowing the exact Langfuse web origin. Start with [examples/r2-cors.json](examples/r2-cors.json), replace its example origin, and apply it in R2 bucket settings. Add `http://localhost:8080` only if testing the local UI. CORS does not make the bucket public; signed URLs authorize access.
5. The wrapper uses separate `events/`, `media/` and `exports/` prefixes in this bucket. Batch exports are disabled in this starter. Use the S3 API endpoint reachable by both Runtime and browsers; do not substitute a public bucket URL or CDN domain.

No lifecycle deletion rule is applied automatically. Raw events accumulate; choose an `events/` expiration period that covers ingestion retries and recovery (upstream commonly uses 30 days). Do **not** apply an indiscriminate bucket-wide expiration rule that deletes referenced media. Retention features and licensing vary; review the selected Langfuse edition before relying on automatic trace/media cleanup. Add storage usage alerts and review retained data regularly.

## Deploy on Aiven Runtime

1. Push this repo. Provision PostgreSQL, ClickHouse and Valkey as described above and prepare the external bucket. Keep all database services in the same Aiven project/region where possible.
2. Create **web** from the repo root using `Dockerfile`, one replica, HTTP **8080**. Add PostgreSQL and Valkey credential integrations mapping their connection strings to `DATABASE_URL` and `VALKEY_URL`.
3. Add the shared and web-only settings below. Use the generated web HTTPS origin for `NEXTAUTH_URL`. It must be the web URL on **both** applications, not the worker URL. Complete settings before allowing users to sign in.
4. Wait for PostgreSQL and ClickHouse migrations to finish successfully, `/api/public/health` to respond successfully, and the web login page to load. Inspect logs for initialization errors; health alone does not prove initial account creation or ingestion readiness.
5. Create **worker** from the same commit using `Dockerfile.worker`, one replica, **no public ports**. Reuse the exact same database services, integrations and shared settings. Start worker only after web's migrations succeed.
6. Sign in with `LANGFUSE_INIT_USER_EMAIL` and `LANGFUSE_INIT_USER_PASSWORD`. In the initial project's settings, create project API keys and run the synthetic trace example. Confirm the observation actually appears in the UI; ingestion acceptance alone is insufficient.

`compose.aiven.yaml` describes both builds plus the PostgreSQL/Valkey dependencies recognized by Runtime's scanner. **ClickHouse and object storage are not scanner-provisioned dependencies.** Review detected resources to avoid creating duplicate PostgreSQL/Valkey services for the worker. If using Console's scanner, deploy web first and worker after migrations, attaching the same existing services.

For MCP/API deployment, Compose is not processed. Set `source.build_path="./"` for both apps; set `source.containerfile_path="./Dockerfile"` for web and `"./Dockerfile.worker"` for worker. Create the two credential integrations explicitly for each app. Web has `ports=[{"name":"default","port":8080,"protocol":"HTTP"}]`; worker has `ports=[]`. Runtime applications do not need an application-to-application integration: ingestion coordination uses the shared data services.

### Shared settings — web and worker

Use [.env.runtime.example](.env.runtime.example) as a reference, not a file to commit filled in.

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | PostgreSQL integration URI, including database, credentials and port |
| `VALKEY_URL` | Valkey integration URI with password and port, database 0 |
| `AIVEN_CA_CERT_BASE64` | Project CA PEM as one line: `openssl base64 -A -in ca.pem` |
| `SALT` | Independent stable random value, at least 32 characters |
| `ENCRYPTION_KEY` | Independent stable 64-character hex value: `openssl rand -hex 32` |
| `NEXTAUTH_URL` | Generated **web** HTTPS origin, no path |
| `CLICKHOUSE_URL` | Aiven's HTTPS interface origin, including its actual port |
| `CLICKHOUSE_MIGRATION_URL` | `clickhouse://HOST:NATIVE_TLS_PORT`, no credentials/path/query |
| `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` | Credentials for the pre-created ClickHouse database |
| `CLICKHOUSE_DB` | `langfuse` |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT` | Private bucket and provider settings; R2 region is `auto` |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Bucket-scoped S3 credentials |
| `S3_FORCE_PATH_STYLE` | `false` for the documented R2 configuration; provider-dependent |

Copy **actual Aiven interface ports** from service connection information; do not assume upstream ClickHouse 8443/9440 or PostgreSQL 5432. All managed database connections must trust the supplied Aiven project CA or public system roots as appropriate. Store passwords, connection strings, keys and salts as Runtime secrets.

### Web-only settings

| Variable | Value |
| --- | --- |
| `NEXTAUTH_SECRET` | Separate random session secret, at least 32 characters |
| `LANGFUSE_INIT_ORG_ID` | Stable ID, e.g. `runtime-demo-org` |
| `LANGFUSE_INIT_PROJECT_ID` | Stable ID, e.g. `runtime-demo-project` |
| `LANGFUSE_INIT_USER_EMAIL` | Initial owner's email |
| `LANGFUSE_INIT_USER_PASSWORD` | Unique password of at least 16 characters |
| `LANGFUSE_INIT_ORG_NAME`, `LANGFUSE_INIT_PROJECT_NAME` | Optional friendly names |

Generate secrets independently and preserve `SALT` and `ENCRYPTION_KEY` across restarts and restores; losing them can invalidate API access or make encrypted credentials unreadable. Initialization creates missing resources; changing the environment password is **not** a supported way to reset an existing user's password. This starter keeps initialization values for repeatable restarts. Configure SMTP/SSO and account recovery separately before shared use. Some Langfuse features require an enterprise license.

## TLS and startup behavior

- PostgreSQL uses Prisma's `sslmode=require`, `sslaccept=strict` and CA path. Supplied URI query options are replaced. `DIRECT_URL` uses the same verified connection; per-process pool size is capped at ten.
- Valkey URI credentials are decoded into native Langfuse settings. TLS verifies the certificate and hostname using system public CAs plus the project CA. URI query flags cannot disable those checks.
- ClickHouse HTTP traffic uses HTTPS plus Node's additional CA trust. A narrowly scoped, build-time patch changes the pinned upstream migration script from `skip_verify=true` to `false`; Go uses a bundle containing system CAs plus the Aiven CA. Migration credentials are URL-encoded independently of the raw HTTP password. The image build fails if the expected upstream script changes.
- Web retains Langfuse's native PostgreSQL and ClickHouse migration entrypoint; failures stop startup. Worker uses its native entrypoint after shared configuration validation. `dumb-init` forwards termination signals to the application.
- Public signup, telemetry and batch exports are disabled. Worker health is loopback-only. No model credentials are bundled.

Do not set `LOCAL_DEVELOPMENT=true` on Runtime. It is the deliberate TLS opt-out used only for local database containers. Advanced TLS bypasses and custom database URL flags are outside this starter's supported configuration.

## Local demo

Requires Docker Compose v2 and enough memory for web, worker and the databases. An **external private S3 bucket is still required**; this repo does not run an ephemeral object store.

1. Copy `.env.example` to `.env` and fill it in. Run `openssl rand -hex 32` independently for each secret. Use hexadecimal PostgreSQL passwords because local Compose embeds the value in a connection URI.
2. Supply your S3/R2 settings. Local testing writes real objects to that bucket, so use a dedicated demo bucket and watch usage.
3. Run `docker compose up --build -d`. Local Compose starts worker only after web health succeeds.
4. Open <http://localhost:8080>, sign in with the initial account and send a test trace.

Only web is exposed, on loopback. Local databases stay on the Compose network; Valkey is passwordless there with AOF enabled and `noeviction`. Named volumes persist local PostgreSQL, ClickHouse and Valkey data. `docker compose down` preserves those volumes; `docker compose down -v` permanently removes them. Neither command deletes objects from the external bucket.

## Send a synthetic trace

Create API keys in the project's settings. Export `LANGFUSE_HOST` (the web origin), `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` into your shell, then run:

```sh
python3 examples/send_trace.py
```

The standard-library example uses Langfuse v4's OTLP endpoint and ingestion-version header. It creates one synthetic observation and makes **no LLM call**. Find **Runtime starter demo** in the project's tracing view. Verify it appears, then restart worker and web and confirm it remains visible. Do not send real prompts or user data until access and retention requirements have been reviewed.

## Validation and operations

```sh
python3 -m unittest discover -s tests -v
```

Requires Python 3.10+ and OpenSSL, with no pip dependencies. See [VALIDATION.md](VALIDATION.md) for current results and live checks still needed.

This is a single-replica-per-role starter, not a high-availability deployment. Scale web and worker separately only after testing queue throughput, database connection limits and memory use. Keep versions aligned. During upgrades, stop ingestion/worker as needed, back up PostgreSQL, ClickHouse and secrets, run web migrations once, then restart compatible workers. Do not downgrade migrated databases casually.

Runtime may ignore Dockerfile HEALTHCHECK; externally verify web health and actual trace processing. Worker health does not prove S3/ClickHouse ingestion success. Backups and recovery must cover **all four stores**, not just PostgreSQL. Valkey persistence is not a substitute for an end-to-end recovery plan. Do not delete the bucket or an individual service while intending to preserve the rest of the deployment.

## References

- [Langfuse self-hosting architecture](https://langfuse.com/self-hosting)
- [Langfuse v4.38.0 release](https://github.com/langfuse/langfuse/releases/tag/v4.38.0)
- [Langfuse ClickHouse configuration](https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse)
- [Langfuse blob storage and R2](https://langfuse.com/self-hosting/deployment/infrastructure/blobstorage)
- [Initial account setup](https://langfuse.com/self-hosting/administration/headless-initialization)
- [OpenTelemetry tracing](https://langfuse.com/integrations/native/opentelemetry)
- [Aiven ClickHouse versions](https://aiven.io/docs/products/clickhouse/howto/manage-clickhouse-versions)
- [Aiven ClickHouse limitations](https://aiven.io/docs/products/clickhouse/reference/limitations)
- [Aiven Runtime Compose manifests](https://aiven.io/docs/products/runtime/manifest-files/compose-files)
