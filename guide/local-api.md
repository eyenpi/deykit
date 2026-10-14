# Optional headless local API

Terminal commands operate directly on project files and do not require a server.
For integrations, `deykit serve` starts the headless API on `127.0.0.1:8765`.
Use `deykit serve --port 0` to choose a free port. Global `--project PATH`
registers an existing project at startup. Stop with Ctrl-C. No page is served
and no browser opens. The former `--no-open` and `demo --open` options are removed.

The API retains its exact-host, origin, bounded-body and session-capability
checks. It is a local single-user adapter, not a hosted or multi-user service.
Bootstrap with POST `/api/v1/session/bootstrap`, headers `Origin` matching the
printed address, `Content-Type: application/json`, `X-Deykit-Bootstrap: 1`, and
body `{"schema_version":1}`. Keep the returned capability private; send it in
`X-Deykit-Capability` for subsequent calls. Mutations also require the exact
Origin. Do not place capabilities or credentials in URLs or public logs.
Restarting the service revokes the session. `/` returns a structured not-found
response; interactive API documentation is disabled.

Export the implemented contracts without starting a server or opening a project:

```sh
uv run python -m deykit.api.schema --output ./api-contracts
```

User JSON crosses the API as exact source strings. The shared application
services, offline safety and immutable evidence rules also apply to this adapter.
