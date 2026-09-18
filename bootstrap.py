"""Validate the standalone starter and launch an upstream Langfuse process."""
import base64
import binascii
import os
from pathlib import Path
import re
import ssl
import sys
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit


def required(env, key, minimum=1):
    value = env.get(key, "")
    if len(value) < minimum:
        raise ValueError(f"{key} must contain at least {minimum} characters")
    return value


def parsed(raw, key):
    try:
        value = urlsplit(raw)
        _ = value.port
        if not value.hostname or value.fragment or any(c.isspace() for c in raw):
            raise ValueError()
        return value
    except ValueError:
        raise ValueError(f"{key} is not a valid connection URL") from None


def origin(raw, key, local=False):
    value = parsed(raw, key)
    if (value.scheme not in (("https", "http") if local else ("https",))
            or value.username or value.password or value.query
            or value.path not in ("", "/")):
        raise ValueError(f"{key} must be an HTTPS origin without credentials, path or query")
    return raw.rstrip("/")


def prepare(env, directory, role):
    if role not in ("web", "worker"):
        raise ValueError("Role must be web or worker")
    local_flag = env.get("LOCAL_DEVELOPMENT", "false").lower()
    if local_flag not in ("true", "false"):
        raise ValueError("LOCAL_DEVELOPMENT must be true or false")
    local = local_flag == "true"
    salt = required(env, "SALT", 32)
    encryption = required(env, "ENCRYPTION_KEY")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", encryption):
        raise ValueError("ENCRYPTION_KEY must be 64 hexadecimal characters")
    if salt == encryption:
        raise ValueError("Generate independent SALT and ENCRYPTION_KEY values")
    env["NEXTAUTH_URL"] = origin(required(env, "NEXTAUTH_URL"), "NEXTAUTH_URL", local)
    if role == "web":
        auth = required(env, "NEXTAUTH_SECRET", 32)
        if auth in (salt, encryption):
            raise ValueError("Generate NEXTAUTH_SECRET independently")
        required(env, "LANGFUSE_INIT_ORG_ID")
        required(env, "LANGFUSE_INIT_PROJECT_ID")
        email = required(env, "LANGFUSE_INIT_USER_EMAIL")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("LANGFUSE_INIT_USER_EMAIL must be an email address")
        required(env, "LANGFUSE_INIT_USER_PASSWORD", 16)
        env["AUTH_DISABLE_SIGNUP"] = "true"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    ca = directory / "aiven-ca.pem"
    if not local:
        try:
            pem = base64.b64decode(required(env, "AIVEN_CA_CERT_BASE64"), validate=True).decode("ascii")
            ssl.create_default_context(cadata=pem)
        except (ValueError, UnicodeError, binascii.Error, ssl.SSLError):
            raise ValueError("AIVEN_CA_CERT_BASE64 must encode a valid PEM CA certificate") from None
        ca.write_text(pem)
        ca.chmod(0o600)
        # Node augments its built-in public CAs. Go migrations use this combined bundle.
        env["NODE_EXTRA_CA_CERTS"] = str(ca)
        system_ca = Path(ssl.get_default_verify_paths().cafile or "/etc/ssl/certs/ca-certificates.crt")
        bundle = directory / "combined-ca.pem"
        bundle.write_text(system_ca.read_text() + "\n" + pem)
        bundle.chmod(0o600)
        env["SSL_CERT_FILE"] = str(bundle)
    if env.get("NODE_TLS_REJECT_UNAUTHORIZED") == "0":
        raise ValueError("NODE_TLS_REJECT_UNAUTHORIZED=0 is not supported")

    pg = parsed(required(env, "DATABASE_URL"), "DATABASE_URL")
    if pg.scheme not in ("postgres", "postgresql") or not pg.username or not pg.password or not pg.port or pg.path in ("", "/"):
        raise ValueError("DATABASE_URL requires PostgreSQL credentials, port and database")
    # Prisma uses require + strict, unlike libpq's verify-full setting.
    query = {"sslmode": "disable"} if local else {"sslmode": "require", "sslaccept": "strict", "sslcert": str(ca)}
    query.update(connection_limit="10", pool_timeout="30")
    env["DATABASE_URL"] = urlunsplit(("postgresql", pg.netloc, pg.path, urlencode(query), ""))
    env["DIRECT_URL"] = env["DATABASE_URL"]

    redis = parsed(required(env, "VALKEY_URL"), "VALKEY_URL")
    if redis.scheme not in ("redis", "rediss", "valkey", "valkeys") or not redis.port or redis.path not in ("", "/", "/0") or (not local and not redis.password):
        raise ValueError("VALKEY_URL requires a supported scheme, port, credentials and database 0")
    for key in ("REDIS_CONNECTION_STRING", "REDIS_TLS_CERT_PATH", "REDIS_TLS_KEY_PATH"):
        env.pop(key, None)
    env.update(REDIS_HOST=redis.hostname, REDIS_PORT=str(redis.port),
               REDIS_USERNAME=unquote(redis.username or "default"), REDIS_AUTH=unquote(redis.password or ""),
               REDIS_CLUSTER_ENABLED="false", REDIS_SENTINEL_ENABLED="false",
               REDIS_TLS_ENABLED="false" if local else "true",
               REDIS_TLS_REJECT_UNAUTHORIZED="true", REDIS_TLS_CHECK_SERVER_IDENTITY="true",
               REDIS_TLS_SERVERNAME=redis.hostname)
    if not local:
        # An explicit Redis CA replaces Node's public roots, so include both.
        env["REDIS_TLS_CA_PATH"] = str(bundle)

    env["CLICKHOUSE_URL"] = origin(required(env, "CLICKHOUSE_URL"), "CLICKHOUSE_URL", local)
    migration = parsed(required(env, "CLICKHOUSE_MIGRATION_URL"), "CLICKHOUSE_MIGRATION_URL")
    if (migration.scheme != "clickhouse" or not migration.port or migration.username or migration.password
            or migration.path not in ("", "/") or migration.query):
        raise ValueError("CLICKHOUSE_MIGRATION_URL must be clickhouse://HOST:PORT without credentials or query")
    user = required(env, "CLICKHOUSE_USER")
    password = required(env, "CLICKHOUSE_PASSWORD")
    database = required(env, "CLICKHOUSE_DB")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", database):
        raise ValueError("CLICKHOUSE_DB must be a simple database identifier")
    env["STARTER_CLICKHOUSE_MIGRATION_URL"] = env["CLICKHOUSE_MIGRATION_URL"].rstrip("/") + "?" + urlencode({
        "username": user, "password": password, "database": database,
    })
    # Aiven's Replicated database distributes DDL and remaps MergeTree engines.
    # Do not hard-code Langfuse's upstream ON CLUSTER default.
    env["CLICKHOUSE_CLUSTER_ENABLED"] = "false"
    env["CLICKHOUSE_MIGRATION_SSL"] = "false" if local else "true"
    env["CLICKHOUSE_USE_LIGHTWEIGHT_UPDATE"] = "false"

    bucket = required(env, "S3_BUCKET")
    region = required(env, "S3_REGION")
    endpoint = origin(required(env, "S3_ENDPOINT"), "S3_ENDPOINT", local)
    access = required(env, "S3_ACCESS_KEY_ID")
    secret = required(env, "S3_SECRET_ACCESS_KEY")
    style = env.get("S3_FORCE_PATH_STYLE", "false").lower()
    if style not in ("true", "false"):
        raise ValueError("S3_FORCE_PATH_STYLE must be true or false")
    for purpose, prefix in (("EVENT_UPLOAD", "events/"), ("MEDIA_UPLOAD", "media/"), ("BATCH_EXPORT", "exports/")):
        for suffix, value in {"BUCKET": bucket, "REGION": region, "ENDPOINT": endpoint,
                              "ACCESS_KEY_ID": access, "SECRET_ACCESS_KEY": secret,
                              "FORCE_PATH_STYLE": style, "PREFIX": prefix}.items():
            env[f"LANGFUSE_S3_{purpose}_{suffix}"] = value
    env["LANGFUSE_S3_BATCH_EXPORT_ENABLED"] = "false"
    env["TELEMETRY_ENABLED"] = "false"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["LANGFUSE_AUTO_POSTGRES_MIGRATION_DISABLED"] = "false"
    env["LANGFUSE_AUTO_CLICKHOUSE_MIGRATION_DISABLED"] = "false"
    env["HOSTNAME"] = "0.0.0.0" if role == "web" else "127.0.0.1"
    env["PORT"] = "8080" if role == "web" else "3030"
    env["NODE_ENV"] = "production"
    return env


def main():
    os.umask(0o077)
    role = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        prepare(os.environ, Path("/tmp/langfuse-starter"), role)
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Cannot prepare private startup files"
        print(f"Starter configuration error: {message}", file=sys.stderr)
        return 1
    command = (["./web/entrypoint.sh", "node", "./web/server.js", "--keepAliveTimeout", "110000"]
               if role == "web" else ["./worker/entrypoint.sh", "node", "worker/dist/index.js"])
    print(f"Starting Langfuse {role}.", flush=True)
    os.execvp(command[0], command)


if __name__ == "__main__":
    sys.exit(main())
