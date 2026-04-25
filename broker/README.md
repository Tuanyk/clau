# clau-broker

Sidecar HTTP broker that holds long-lived API credentials so they never
enter the Claude/Codex container. Claude calls the broker over plain HTTP
without auth; the broker injects provider credentials and forwards.

## When does it run?

Automatically. The launcher (`clau`) detects `secrets/<project>/broker/`
and, if present, brings up `broker-<project>` on a dedicated docker
network (`clau-net-<project>`) before starting the Claude container.

## Per-project credentials

```
secrets/<project>/broker/
  meta.env            # META_ACCESS_TOKEN=..., META_AD_ACCOUNT_ID=...
  google-ads.env      # GOOGLE_ADS_DEVELOPER_TOKEN=..., refresh_token, client_id/secret, login_customer_id
  gcp-sa.json         # service account JSON for GA4 + GSC
```

Every `*.env` under that directory is loaded as dotenv data by the broker
process at startup. `gcp-sa.json` (or `service-account.json` /
`gcp.json`) auto-sets `GOOGLE_APPLICATION_CREDENTIALS`.

The directory is mounted **read-only at `/run/broker-secrets`** in the
broker container and **never** mounted into the Claude container.

## Endpoints

```
GET  /health                     -> {"ok": true, "providers": [...]}

POST /meta/insights              -> {ad_account_id, fields, params, max_pages}
POST /meta/campaigns             -> {ad_account_id, fields, params}
GET  /meta/ad-accounts

POST /ga4/run-report             -> {property_id, dimensions, metrics, date_ranges, ...}

GET  /gsc/sites
POST /gsc/search-analytics       -> {site_url, start_date, end_date, dimensions, ...}

GET  /gtm/accounts
GET  /gtm/accounts/{id}/containers
GET  /gtm/accounts/{id}/containers/{cid}/workspaces
GET  /gtm/workspaces/{id}/{cid}/{wid}/tags

POST /google-ads/query           -> {customer_id, gaql_query, page_size}
GET  /google-ads/customers

ANY  /passthrough/meta/<path>    -> arbitrary Graph API call, token injected
```

OpenAPI docs live at `/docs` (reachable from inside the docker network).

## Provider opt-in

A provider router returns **HTTP 503** if its credentials are missing.
That means a project can use only Meta (set `META_ACCESS_TOKEN`) without
also configuring Google Ads, etc.

`GET /health` reports which providers are currently configured.

## Allowlist

The broker enforces its own firewall (default-deny) using the same
`init-firewall.sh` as the Claude container. Hosts it can reach come from:

- `allowlists/broker.txt` (shared baseline: graph.facebook.com,
  googleads.googleapis.com, analyticsdata.googleapis.com, …)
- `allowlists/<project>-broker.txt` (per-project additions, optional)

## Adding a new endpoint

1. Pick a router file (or add one under `broker/app/routes/`).
2. Add a Pydantic request model + handler that calls the upstream SDK.
3. Mount it in `broker/app/main.py`.
4. Rebuild image: `./install.sh`.
5. `docker stop broker-<project>` so the launcher recreates it next run.

## Logging

The broker logs only `method path -> status (Xms)`. Request and response
bodies are **never** logged — they may contain credential-equivalent
data (PII, internal IDs, sensitive ad performance figures).
