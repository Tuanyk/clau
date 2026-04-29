# clau

Run Claude Code and OpenAI Codex inside a Docker container. Per-project firewall, persistent auth, persistent shell history, and shared tool/package volumes so AI-installed tools survive across sessions.

## Install

```bash
./install.sh        # builds the image, symlinks `clau`, `clau-login`, `codex-login`, `clau-restore`
clau-login          # one-time Claude OAuth login (stored in `claude-auth`)
codex-login         # one-time Codex ChatGPT login (stored in `codex-auth`)
```

## Run

```bash
cd ~/path/to/project
clau                # shell in the container; run `claude` or `codex`
clau --codex        # open Codex directly
clau --yolo         # open Claude with --dangerously-skip-permissions
clau --codex --yolo # open Codex with --dangerously-bypass-approvals-and-sandbox
clau --no-firewall  # debug mode
clau --help         # show options, env vars, secret paths, and allowlists
```

On Linux, `clau` starts the Docker container with
`--security-opt seccomp=unconfined --security-opt apparmor=unconfined` so
Codex's bubblewrap sandbox can create its nested namespaces inside Docker. To
turn those Docker options off for debugging:

```bash
CLAU_BWRAP_OPTS=0 clau
```

By default, `clau` maps the first free host port starting at `13000` to port
`3000` inside the container. Next.js can still listen on `3000`; open the host
port printed by `clau`, for example `http://localhost:13000`.

```bash
CLAU_PORTS=auto:3000 clau          # first free host port from 13000 -> container 3000
CLAU_PORTS=3001:3000 clau          # fixed host localhost:3001 -> container 3000
CLAU_PORTS=auto:3000,auto:5173 clau
CLAU_DEFAULT_HOST_PORT=14000 clau  # change the auto-search starting point
CLAU_PORTS="" clau                 # no forwarded ports
```

`clau` prints the resolved project name + path on startup:

```
📁 Project: my-app  (/home/you/work/my-app)
```

The project name is the lowercased basename of the cwd — so `~/work/my-app` and `~/personal/my-app` share `~/.clau/secrets/`, `~/.clau/allowlists/`, container, and history. To disambiguate, override with `CLAU_PROJECT_NAME`:

```bash
cd ~/personal/my-app && CLAU_PROJECT_NAME=my-app-personal clau
```

Then `~/.clau/secrets/my-app-personal/`, `~/.clau/allowlists/my-app-personal.txt`, container `clau-my-app-personal`, etc.

Claude and Codex credentials are intentionally separate:

```text
claude-auth -> /home/dev/.claude
codex-auth  -> /home/dev/.codex
```

This keeps OAuth/session credentials inside Docker volumes instead of using your host API keys. The launcher intentionally blanks `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` for the container, even if they exist on the host or in an env file, so Claude/Codex do not inherit long-lived API keys.

By default, a normal shell/Claude run mounts only `claude-auth`; `clau --codex`
mounts only `codex-auth`. Set `CLAU_WITH_CODEX_AUTH=1` if you explicitly need
Codex auth in a normal shell, or `CLAU_WITHOUT_AUTH=1` for a shell with neither
auth volume mounted.

Codex models can differ by auth mode and rollout. `gpt-5.5` is available in
Codex only when it appears for the signed-in ChatGPT account; API-key auth
does not expose it. If it does not appear yet, use `gpt-5.4` and rebuild later
with `./install.sh` to pick up the newest Codex CLI.

## Snapshots and recovery

The project directory is bind-mounted live into the container, so anything the AI deletes or overwrites hits host disk immediately. To make accidents recoverable, every fresh `clau` run tars the working directory into a host-side snapshot **before** starting the container.

```text
~/.clau/snapshots/<project>/<UTC-timestamp>.tar.gz
```

Defaults: keep the **3 most recent** snapshots per project, auto-prune anything **older than 3 days**. The snapshot dir lives outside any bind mount, so a runaway agent inside the container cannot reach it.

Default excludes (reproducible from package files): `node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `dist/`, `build/`, `.next/`, `target/`, `.cache/`. Drop a `.clau-snapshot-ignore` file in the project root (gitignore-style, one pattern per line) to add more.

Snapshots are taken only on a fresh container start — `clau` re-attaching to a running container skips the snapshot.

To list / restore:

```bash
clau-restore           # list snapshots for the cwd's project
clau-restore 2         # extract snapshot #2 to ~/.clau/restored/<project>-<timestamp>/
```

`clau-restore` never overwrites the live project — it extracts to a sibling dir under `~/.clau/restored/` so you can `diff -r` and copy back what you need.

Tunables (env vars):

```bash
CLAU_SKIP_SNAPSHOT=1 clau          # disable for this run (huge repos / CI)
CLAU_SNAPSHOT_KEEP=5 clau          # keep last 5 instead of 3
CLAU_SNAPSHOT_TTL_DAYS=7 clau      # prune after 7 days instead of 3
CLAU_SNAPSHOT_DIR=/mnt/backup/clau # store somewhere other than ~/.clau/snapshots
```

## Secrets / API keys / credentials

> **Where they live**: `~/.clau/secrets/<project>/` on the host (outside the clau repo, so opening the clau project in any editor / agent doesn't expose them). Override with `CLAU_SECRETS_DIR=/some/path clau`. For backward compat, an in-tree `secrets/` directory is still picked up if it exists.

### Recommended layout: one directory per project

```text
~/.clau/secrets/
  my-app/
    .env          # low-risk app runtime values — key=value
    gcp.json      # service account JSON
    id_ed25519    # SSH key
    kubeconfig    # K8s config
```

`<project-name>` is the lowercased basename of your project dir (`~/work/my-app` → `my-app`). The `~/.clau/secrets/` root lives outside any git repo — never enters version control.

On every `clau` run, for project `my-app`:

1. `~/.clau/secrets/my-app/.env` is loaded into the container as env vars.
2. Top-level files in `~/.clau/secrets/my-app/` are mounted read-only under `/run/clau-secrets/`.
3. **Every top-level file in that dir (except `.env`) gets its path auto-injected as an env var** — uppercase, non-alphanumerics become `_`:

   | File in `~/.clau/secrets/my-app/` | Auto-injected env var |
   |---|---|
   | `gcp.json` | `GCP_JSON=/run/clau-secrets/gcp.json` **and** `GOOGLE_APPLICATION_CREDENTIALS=/run/clau-secrets/gcp.json` |
   | `kubeconfig` | `KUBECONFIG=/run/clau-secrets/kubeconfig` |
   | `id_ed25519` | `ID_ED25519=/run/clau-secrets/id_ed25519` |
   | `api-key.txt` | `API_KEY_TXT=/run/clau-secrets/api-key.txt` |

   Well-known filenames (`gcp.json`, `service-account.json`, `gcp-*.json`, `*-gcp.json`, `kubeconfig*`) also set the SDK-expected name so `google.cloud.*` and `kubectl` work out of the box without touching `.env`. You can always override by setting the same variable in your own `.env`.

Directories are not mounted into `/run/clau-secrets`; `broker/` is reserved for
the broker sidecar and is not mounted into the AI container.

On entry you'll see a line like:
```
🔑 File secrets: top-level files in /home/you/.clau/secrets/my-app → /run/clau-secrets (ro)
   Injected env vars: GCP_JSON GOOGLE_APPLICATION_CREDENTIALS KUBECONFIG
```

### Legacy layout (still supported)

Earlier clau versions used two separate paths — they both still work and are loaded in addition to the directory layout:

- `~/.clau/secrets/<project-name>.env` — env vars only (flat file)
- `<project>/.env` — the project's own `.env` in its root. It is no longer auto-loaded by default because the workspace is mounted live and the file is AI-readable.

If multiple are present, default load order is: `~/.clau/secrets/<project>.env` → `~/.clau/secrets/<project>/.env` → `-e` injected vars. Set `CLAU_LOAD_PROJECT_ENV=1` to restore legacy project `.env` loading for a run; later values win on conflicts.

### What the AI can do with credential files

- ✅ reference them **by env-var name** in code — `os.environ["GOOGLE_APPLICATION_CREDENTIALS"]`, `process.env.KUBECONFIG`, etc. SDKs open the file.
- ❌ `cat /run/clau-secrets/...` or `Read(/run/clau-secrets/**)` — blocked by `permissions.deny` + `hooks/secrets-guard.py`.

Treat the values as opaque; the path/name is the only thing the AI should touch.

### Alternative: credentials inside the project

Keeping credentials inside the project (for example `.secrets/gcp.json` or
`.env`) means the AI container can read them because the project is bind-mounted.
Use this only for low-risk or throwaway credentials. Put long-lived provider
credentials under `~/.clau/secrets/<project>/broker/`.

## Auto-seeded AI instructions (`CLAUDE.md` / `AGENTS.md`)

On every `clau` run, the project root's `CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex) are checked for a `clau:seed-v1` marker:

| Project state | What clau does |
|---|---|
| File missing | Copy the full template into the project |
| File exists, marker present | Skip the full template; backfill the broker section if an older seeded file is missing it |
| File exists, no marker | Append the template content to the end |

The appended section tells the AI:

- Reference secrets **by name** in code, never print/log/cat their values.
- The container is firewalled — domains not in `allowlist.txt` will fail.
- If `BROKER_URL` is set, call the sidecar broker instead of provider APIs directly.
- pip and `/opt/clau-tools/bin` persist across sessions.

To customize, edit `templates/CLAUDE.md` and `templates/AGENTS.md` in the clau install dir (affects future projects) or the file inside the project (that project only). **Keep the `<!-- clau:seed-v1 -->` marker comment** — deleting it will cause clau to append the section again on the next run. To disable seeding entirely, `export CLAU_SKIP_AUTO_DOCS=1`.

You'll usually want to add a per-project **Secrets** section that names the env vars available. For example:

```markdown
## Secrets

- `APP_OPENAI_API_KEY` — app-scoped OpenAI API key
- `DATABASE_URL` — Postgres connection string
- `GOOGLE_APPLICATION_CREDENTIALS` — path to GCP service account JSON
```

That tells the AI (1) what's available, (2) the exact variable names to use, and (3) not to leak the values into the chat or logs.

## Python packages persist

`pip install <anything>` inside the container goes into the shared `clau-pip` Docker volume (mounted at `/home/dev/.pip-user`). Packages survive container restarts and are shared across all projects.

To wipe and start fresh:

```bash
docker volume rm clau-pip
```

## Adding tools later (Headroom, Caveman, etc.)

A shared `clau-tools` volume is mounted at `/opt/clau-tools` and on `PATH`. Install once, available in every project, no rebuild needed.

```bash
clau                                                # enter container
curl -fsSL https://example.com/install.sh \
  | PREFIX=/opt/clau-tools bash                     # install into the volume
which headroom                                      # /opt/clau-tools/bin/headroom

# remove a single tool
rm -rf /opt/clau-tools/bin/headroom /opt/clau-tools/share/headroom

# nuclear: wipe all tools
docker volume rm clau-tools
```

Once a tool is proven, "promote" it by adding the install command to the `Dockerfile` and rebuilding.

## Sidecar broker (keep API keys out of Claude's container)

For long-lived third-party credentials — Meta access tokens, Google
service-account JSON, Google Ads developer/refresh tokens — the
defense-in-depth layers below are *not enough*. Anything that lives in
Claude's address space can theoretically be encoded and exfiltrated. The
broker sidecar moves those secrets out of Claude's container entirely.

**How it works.** Drop credentials under `~/.clau/secrets/<project>/broker/`
instead of `~/.clau/secrets/<project>/`. On `clau` start:

1. A `broker-<project>` container comes up on a private docker network
   (`clau-net-<project>`) and reads creds from `/run/broker-secrets/`.
2. The AI container joins the same network and gets `BROKER_URL=http://broker:8080`
   plus a per-run `BROKER_AUTH_TOKEN`. It does **not** receive the provider API keys themselves.
3. Claude's firewall removes Meta / Google Ads / Analytics / Search
   Console hosts; only the broker IP and the standard dev hosts are
   reachable. The broker has its own firewall (`~/.clau/allowlists/broker.txt`)
   that allows only the provider APIs.
4. The AI calls `POST http://broker:8080/meta/insights` etc. with
   `Authorization: Bearer $BROKER_AUTH_TOKEN`. The broker injects the provider
   access token, talks to graph.facebook.com, returns the JSON. The provider
   token never appears in any tool result.

```
~/.clau/secrets/
  client-foo/
    .env              # ← visible to the AI container as env vars
    broker/           # ← visible to broker only
      meta.env        # META_ACCESS_TOKEN=…, META_AD_ACCOUNT_ID=…
                      # META_PAGE_ACCESS_TOKEN=…, META_PAGE_ID=… for Page APIs
                      # META_INSTAGRAM_BUSINESS_ACCOUNT_ID=… for IG APIs
      google-ads.env  # GOOGLE_ADS_DEVELOPER_TOKEN=…, refresh token, login customer id
      gcp-sa.json     # service account JSON (GA4 + GSC)
  client-bar/
    broker/           # different keys for a different client — full isolation
      meta.env
      gcp-sa.json
```

**Multi-project**: each project pairs 1:1 with its own broker
(`broker-<project>`) on its own docker network. Project A's Claude
container can't reach project B's broker — they're on different
networks with different credentials.

**Endpoints** — see `broker/README.md` for the full list. Common ones:

```
POST /meta/insights              {ad_account_id, fields, params}
GET  /meta/pages                 list pages, page tokens redacted
GET  /meta/pages/{page_id}       page profile fields
POST /meta/page-insights         {page_id, metrics, params}
POST /ga4/run-report             {property_id, dimensions, metrics, date_ranges}
POST /gsc/search-analytics       {site_url, start_date, end_date, dimensions}
POST /google-ads/query           {customer_id, gaql_query}
GET/POST /passthrough/meta/<path> arbitrary Graph API call
GET/POST /passthrough/meta-page/<path> arbitrary Page Graph call
```

All endpoints require:

```bash
-H "Authorization: Bearer $BROKER_AUTH_TOKEN"
```

**Opt-in**: if `~/.clau/secrets/<project>/broker/` doesn't exist, nothing
changes — the broker isn't started, behavior is identical to before.

**Dashboard**: host publishing is disabled by default. Set
`CLAU_BROKER_DASHBOARD=1` to publish the broker on `127.0.0.1`; the dashboard
still requires the bearer token.

**Lifecycle**: each fresh `clau` run recreates the broker container so changed
credentials and the per-run auth token stay in sync. If broker startup fails,
the stopped container is kept so you can inspect it:
`docker logs --tail 80 broker-<project>`. To print those logs during launcher
startup, run `CLAU_BROKER_SHOW_LOGS=1 clau`.

## Defense-in-depth: secrets guard

Two layers run inside every `clau` container to catch obvious secret-reading attempts:

**Layer 1 — `permissions.deny`** in `claude-settings.json`. Mounted read-only at `/etc/claude-code/managed-settings.json` inside the container — Claude Code's "managed" scope, which overrides user/project settings and cannot be disabled by the AI. Pattern-blocks tool calls like `Read(/root/**)`, `Bash(printenv)`, `Bash(env)`, `Bash(cat:/run/secrets/**)`, etc. User preferences (theme, model, effort) still save normally to `~/.claude/settings.json`.

**Layer 2 — `PreToolUse` hook** at `hooks/secrets-guard.py`. Inspects every Bash/Read/Write/Edit call, blocks patterns like `cat /root/...`, dynamic DNS lookups (`nslookup $X`), POSTing env vars to external hosts, writing PEM blocks to disk. Block logging is disabled by default; set `CLAU_SECRETS_GUARD_LOG=1` to opt in to minimal logs that exclude full tool input.

To tune the rules, edit `hooks/secrets-guard.py` (host side); changes take effect on next `clau` start. To disable temporarily for debugging, comment out the `hooks` block in `claude-settings.json`.

**Important**: this is *defense-in-depth*, not primary security. A determined AI can bypass hooks and policy rules if the secret is already present. The strongest boundary is the sidecar broker: long-lived provider credentials should never enter the AI container.

## Firewall allowlist

- Default: `allowlist.txt` (clau install root)
- Per-project override: `~/.clau/allowlists/<project-name>.txt` (override location with `CLAU_ALLOWLISTS_DIR`)

One domain per line. The container can only reach hosts on the allowlist for HTTP/S traffic. DNS is still required for resolution, so do not treat the firewall as the only protection for secrets that are already inside the container.

## Volumes

| Volume | Purpose | Scope |
|---|---|---|
| `claude-auth` | Claude OAuth session | global |
| `codex-auth` | Codex ChatGPT/API auth and Codex config | global |
| `clau-pip` | pip-installed Python packages | global, all projects |
| `clau-tools` | dev tools (Headroom, Caveman, ...) | global, all projects |
| `clau-history-<project>` | bash history | per-project |
| `clau-net-<project>` | docker network shared by `clau-<project>` + `broker-<project>` | per-project (only when broker is enabled) |
