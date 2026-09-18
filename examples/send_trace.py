"""Send one synthetic OTLP trace. No model calls or real user data."""
import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def payload(trace_id, span_id, start):
    return {"resourceSpans": [{"resource": {"attributes": [
        {"key": "service.name", "value": {"stringValue": "aiven-runtime-langfuse-starter"}}
    ]}, "scopeSpans": [{"scope": {"name": "runtime-starter"}, "spans": [{
        "traceId": trace_id, "spanId": span_id, "name": "Runtime starter demo",
        "kind": 1, "startTimeUnixNano": str(start), "endTimeUnixNano": str(start + 1_000_000),
        "status": {"code": 1}, "attributes": [
            {"key": "langfuse.observation.input", "value": {"stringValue": "Hello from Aiven Runtime"}},
            {"key": "langfuse.observation.output", "value": {"stringValue": "Synthetic trace: no model call was made"}},
        ]
    }]}]}]}


def main():
    host = os.environ["LANGFUSE_HOST"].rstrip("/")
    url = urlsplit(host)
    if (url.scheme != "https" and host != "http://localhost:8080") or url.username or url.password or url.query or url.fragment or url.path:
        raise SystemExit("LANGFUSE_HOST must be an HTTPS origin or http://localhost:8080")
    credentials = os.environ["LANGFUSE_PUBLIC_KEY"] + ":" + os.environ["LANGFUSE_SECRET_KEY"]
    trace_id = secrets.token_hex(16)
    request = urllib.request.Request(host + "/api/public/otel/v1/traces",
        data=json.dumps(payload(trace_id, secrets.token_hex(8), time.time_ns())).encode(),
        headers={"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode(),
                 "Content-Type": "application/json", "x-langfuse-ingestion-version": "4"})
    # Do not forward credentials to a redirected destination.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            result = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Ingestion failed: HTTP {exc.code}; inspect web/worker logs") from None
    partial = result.get("partialSuccess", {})
    if int(partial.get("rejectedSpans", 0)) or partial.get("errorMessage"):
        raise SystemExit("Ingestion reported partial failure; inspect web/worker logs")
    print("Accepted trace:", trace_id)
    print("Open the project's tracing view and find 'Runtime starter demo'.")
    print("Acceptance is not proof of processing; confirm it appears after the worker ingests it.")


if __name__ == "__main__":
    main()
