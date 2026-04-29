# clau-broker

Sidecar HTTP broker that holds long-lived API credentials so they never
enter the Claude/Codex container. The paired AI container calls the broker
over plain HTTP with a per-run bearer token; the broker injects provider
credentials and forwards.

## When does it run?

Automatically. The launcher (`clau`) detects `secrets/<project>/broker/`
and, if present, brings up `broker-<project>` on a dedicated docker
network (`clau-net-<project>`) before starting the AI container. Each fresh
launcher run recreates the broker so changed credentials and the per-run auth
token stay in sync.

## Per-project credentials

```
secrets/<project>/broker/
  meta.env            # META_ACCESS_TOKEN=..., META_PAGE_ACCESS_TOKEN=...
  google-ads.env      # GOOGLE_ADS_DEVELOPER_TOKEN=..., refresh_token, client_id/secret, login_customer_id
  gcp-sa.json         # service account JSON for GA4 + GSC
```

Every `*.env` under that directory is loaded as dotenv data by the broker
process at startup. `gcp-sa.json` (or `service-account.json` /
`gcp.json`) auto-sets `GOOGLE_APPLICATION_CREDENTIALS`.

The directory is mounted **read-only at `/run/broker-secrets`** in the
broker container and **never** mounted into the AI container.
The broker firewall allows inbound TCP 8080 only from the paired Docker
network path; provider credentials remain broker-local.

## Endpoints

```
GET  /health                     -> {"ok": true, "providers": [...]}

POST /meta/insights              -> {ad_account_id, fields, params, max_pages}
POST /meta/campaigns             -> {ad_account_id, fields, params}
GET  /meta/ad-accounts
GET  /meta/pages                 -> page list, page tokens redacted
GET  /meta/pages/{page_id}       -> page profile fields
POST /meta/page-insights         -> {page_id, metrics, params, max_pages}

POST /ga4/run-report             -> {property_id, dimensions, metrics, date_ranges, ...}

GET  /gsc/sites
POST /gsc/search-analytics       -> {site_url, start_date, end_date, dimensions, ...}

GET  /gtm/accounts
GET  /gtm/accounts/{id}/containers
GET  /gtm/accounts/{id}/containers/{cid}/workspaces
GET  /gtm/workspaces/{id}/{cid}/{wid}/tags

POST /google-ads/query           -> {customer_id, gaql_query, page_size}
GET  /google-ads/customers

GET/POST /passthrough/meta/<path>      -> Graph call with META_ACCESS_TOKEN
GET/POST /passthrough/meta-page/<path> -> Graph page call with page token
```

All endpoints, including `/health`, `/docs`, and `/dashboard`, require:

```bash
-H "Authorization: Bearer $BROKER_AUTH_TOKEN"
```

OpenAPI docs live at `/docs` (reachable from inside the docker network).
Host dashboard publishing is disabled by default; set
`CLAU_BROKER_DASHBOARD=1` if you explicitly want a localhost port.

## Provider opt-in

A provider router returns **HTTP 503** if its credentials are missing.
That means a project can use only Meta without also configuring Google Ads, etc.

Meta token names:

- `META_ACCESS_TOKEN` — primary Meta token for ad-account APIs and
  `/passthrough/meta/...`.
- `META_PAGE_ACCESS_TOKEN` — page token used by page info, page insights, and
  `/passthrough/meta-page/...`.
- `META_USER_ACCESS_TOKEN` — user token used only inside the broker to resolve
  page tokens via `/me/accounts`; returned page tokens are not exposed.
- `META_PAGE_ID` — default page id for page endpoints where `page_id` is
  optional.
- `META_INSTAGRAM_BUSINESS_ACCOUNT_ID` — default Instagram professional account
  id for future Instagram Graph endpoints. `META_IG_USER_ID` is accepted as a
  shorter alias.

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
5. Run `clau` again; the launcher recreates the broker on fresh starts.

## Logging

The broker logs metadata by default: method, path, status, timing, byte counts,
and content types. Request bodies are not logged unless `BROKER_LOG_BODIES=1`
is explicitly set, and known sensitive fields are redacted in that opt-in mode.
