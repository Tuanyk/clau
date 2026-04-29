# Per-project broker secrets — copy template

This is a **template**. Don't put real credentials here.

For each clau-managed project that should use the broker, copy this tree:

```bash
PROJECT=my-app                 # whatever your project's basename is
mkdir -p ~/.clau/secrets/$PROJECT
cp -r templates/secrets-example/. ~/.clau/secrets/$PROJECT/
rm ~/.clau/secrets/$PROJECT/README.md  # optional cleanup
```

Then edit each `*.env` under `~/.clau/secrets/$PROJECT/broker/` and drop your real
`gcp-sa.json` next to them. The launcher detects that `broker/` directory
on the next `clau` run and brings up `broker-$PROJECT`.

## Resulting layout

```
~/.clau/secrets/
  my-app/
    .env                       # OPTIONAL — low-risk app runtime values
                               # (DATABASE_URL, APP_OPENAI_API_KEY, …)
                               # NOT used by the broker.
    broker/                    # Broker-only credentials
      meta.env                 # Meta Marketing API
      google-ads.env           # Google Ads (MCC or single customer)
      gcp-sa.json              # Service account for GA4 + GSC + GTM
```

Every `*.env` under `broker/` is loaded as dotenv data by the broker process
at startup; `gcp-sa.json` (or `service-account.json`) auto-sets
`GOOGLE_APPLICATION_CREDENTIALS`.

## Per-provider opt-in

A provider only activates if its credentials are present. Examples:

| You filled… | authenticated `GET $BROKER_URL/health` returns |
|---|---|
| only `meta.env` | `{"providers": ["meta"]}` |
| only `gcp-sa.json` | `{"providers": ["ga4", "gsc", "gtm"]}` |
| `meta.env` + `gcp-sa.json` | `{"providers": ["meta", "ga4", "gsc", "gtm"]}` |
| all of them | `{"providers": ["meta", "google_ads", "ga4", "gsc", "gtm"]}` |

If an endpoint returns **HTTP 503** with `"<provider> not configured"`,
the matching env vars / file are missing — open the template here for the
exact list.

## Quick verification

After populating and starting the project:

```bash
clau                                         # broker auto-starts on cold start
# inside the container:
curl -s -H "Authorization: Bearer $BROKER_AUTH_TOKEN" $BROKER_URL/health | jq
curl -s -H "Authorization: Bearer $BROKER_AUTH_TOKEN" $BROKER_URL/docs

# example calls:
curl -s -X POST $BROKER_URL/meta/insights \
  -H "Authorization: Bearer $BROKER_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"ad_account_id":"<your-id>","fields":["spend","impressions"],
       "params":{"date_preset":"last_7d"}}'

curl -s -X POST $BROKER_URL/meta/page-insights \
  -H "Authorization: Bearer $BROKER_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"page_id":"<page-id>","metrics":["page_impressions"],
       "params":{"period":"day"}}'

curl -s -H "Authorization: Bearer $BROKER_AUTH_TOKEN" $BROKER_URL/gtm/accounts | jq
curl -s -X POST $BROKER_URL/ga4/run-report \
  -H "Authorization: Bearer $BROKER_AUTH_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"property_id":"<id>","dimensions":["date"],"metrics":["sessions"]}'
```

Provider Authorization headers are injected by the broker. The broker bearer
token is a per-run guard for this local sidecar; reference it by env-var name
and do not print it.
