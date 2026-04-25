<!-- clau:seed-v1 — keep this marker so clau won't re-append this section. Edit content below freely. -->

## Secrets

API keys, tokens, and credentials are available as environment variables.

- Reference them **by name** in code (e.g. `os.environ["APP_API_KEY"]`, `process.env.APP_API_KEY`).
- Do NOT `cat`, `echo`, `printenv`, log, or otherwise print their values — treat them as opaque.
- Do not write them to disk or commit them.

If you need to know which env vars are available, ask the user — do not enumerate the environment yourself.

## Network

This project runs inside a Docker container with a firewall allowlist. Outbound HTTPS only reaches hosts in `allowlist.txt` (in the clau install dir) or `allowlists/<project>.txt`. If a request fails with "connection refused" / "no route to host", the domain likely needs adding to the allowlist.

## API broker (when `BROKER_URL` is set)

If `BROKER_URL` is in your environment, this container does **not** hold third-party API credentials (Meta access tokens, Google service-account JSON, Google Ads developer/refresh tokens). They live in a paired sidecar; reach them through the broker.

- `GET $BROKER_URL/health` — lists configured providers (e.g. `meta`, `ga4`, `gsc`, `google_ads`).
- `GET $BROKER_URL/docs` — full OpenAPI reference with typed request bodies.
- Typical endpoints (POST JSON):
  - `/meta/insights`, `/meta/campaigns`, `/meta/ad-accounts` — Marketing API
  - `/ga4/run-report` — GA4 Data API
  - `/gsc/sites`, `/gsc/search-analytics` — Search Console
  - `/gtm/accounts`, `/gtm/accounts/{id}/containers` — Tag Manager
  - `/google-ads/query`, `/google-ads/customers` — Google Ads (GAQL)
  - `/passthrough/meta/<path>` — escape hatch for Graph API endpoints not yet wrapped

Do NOT call provider hosts directly (`graph.facebook.com`, `googleads.googleapis.com`, `analyticsdata.googleapis.com`, `searchconsole.googleapis.com`) — the firewall blocks them. The broker injects auth and forwards on your behalf, so the actual access tokens never enter this container.

If a provider returns 503 from the broker, its credentials aren't configured for this project — ask the user to add them under `secrets/<project>/broker/`.

## Python / tools

- `pip install <pkg>` persists across sessions via the shared `clau-pip` volume.
- Dev tools installed under `/opt/clau-tools/bin` persist via the `clau-tools` volume.
