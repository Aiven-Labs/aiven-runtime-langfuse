"""Narrow, fail-closed patch for the pinned upstream ClickHouse migration launcher."""
from pathlib import Path
import sys


def patch(text):
    old = 'DATABASE_URL="${CLICKHOUSE_MIGRATION_URL}?username=${CLICKHOUSE_USER}&password=${CLICKHOUSE_PASSWORD}&database=${CLICKHOUSE_DB}&x-multi-statement=true"'
    new = 'DATABASE_URL="${STARTER_CLICKHOUSE_MIGRATION_URL:?Starter migration URL is required}&x-multi-statement=true"'
    if text.count(old) != 1 or text.count("&secure=true&skip_verify=true") != 1:
        raise ValueError("Upstream migration launcher changed; review the TLS patch before upgrading")
    return text.replace(old, new).replace("&secure=true&skip_verify=true", "&secure=true&skip_verify=false")


if __name__ == "__main__":
    path = Path(sys.argv[1])
    path.write_text(patch(path.read_text()))
