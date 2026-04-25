# clau

Run Claude Code and OpenAI Codex inside a Docker container. Per-project firewall, persistent auth, persistent shell history, and shared tool/package volumes so AI-installed tools survive across sessions.

## Install

```bash
./install.sh        # builds the image, symlinks `clau`, `clau-login`, `codex-login`
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

The project name is the lowercased basename of the cwd — so `~/work/my-app` and `~/personal/my-app` share `secrets/`, `allowlists/`, container, and history. To disambiguate, override with `CLAU_PROJECT_NAME`:

```bash
cd ~/personal/my-app && CLAU_PROJECT_NAME=my-app-personal clau
```

Then `secrets/my-app-personal/`, `allowlists/my-app-personal.txt`, container `clau-my-app-personal`, etc.

Claude and Codex credentials are intentionally separate:

```text
claude-auth -> /home/dev/.claude
codex-auth  -> /home/dev/.codex
```

This keeps OAuth/session credentials inside Docker volumes instead of using your host API keys. The launcher intentionally blanks `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` for the container, even if they exist on the host or in an env file, so Claude/Codex do not inherit long-lived API keys.

Codex models can differ by auth mode and rollout. `gpt-5.5` is available in
Codex only when it appears for the signed-in ChatGPT account; API-key auth
does not expose it. If it does not appear yet, use `gpt-5.4` and rebuild later
with `./install.sh` to pick up the newest Codex CLI.

## Secrets / API keys / credentials

### Recommended layout: one directory per project

```text
secrets/
  my-app/
    .env          # API keys, connection strings — key=value
    gcp.json      # service account JSON
    id_ed25519    # SSH key
    kubeconfig    # K8s config
```

`<project-name>` is the lowercased basename of your project dir (`~/work/my-app` → `my-app`). The `secrets/` root is gitignored.

On every `clau` run, for project `my-app`:

1. `secrets/my-app/.env` is loaded into the container as env vars (`APP_API_KEY=sk-...` etc.).
2. `secrets/my-app/` is mounted read-only at `/run/clau-secrets/` in the container.
3. **Every file in that dir (except `.env`) gets its path auto-injected as an env var** — uppercase, non-alphanumerics become `_`:

   | File in `secrets/my-app/` | Auto-injected env var |
   |---|---|
   | `gcp.json` | `GCP_JSON=/run/clau-secrets/gcp.json` **and** `GOOGLE_APPLICATION_CREDENTIALS=/run/clau-secrets/gcp.json` |
   | `kubeconfig` | `KUBECONFIG=/run/clau-secrets/kubeconfig` |
   | `id_ed25519` | `ID_ED25519=/run/clau-secrets/id_ed25519` |
   | `api-key.txt` | `API_KEY_TXT=/run/clau-secrets/api-key.txt` |

   Well-known filenames (`gcp.json`, `service-account.json`, `gcp-*.json`, `*-gcp.json`, `kubeconfig*`) also set the SDK-expected name so `google.cloud.*` and `kubectl` work out of the box without touching `.env`. You can always override by setting the same variable in your own `.env`.

On entry you'll see a line like:
```
🔑 File secrets: .../secrets/my-app → /run/clau-secrets (ro)
   Injected env vars: GCP_JSON GOOGLE_APPLICATION_CREDENTIALS KUBECONFIG
```

### Legacy layout (still supported)

Earlier clau versions used two separate paths — they both still work and are loaded in addition to the directory layout:

- `secrets/<project-name>.env` — env vars only (flat file)
- `<project>/.env` — the project's own `.env` in its root (auto-mounted)

If multiple are present, load order is: `secrets/<project>.env` → `secrets/<project>/.env` → `<project>/.env` → `-e` injected vars. Later values win on conflicts, so the project's own `.env` has the final say.

### What the AI can do with credential files

- ✅ reference them **by env-var name** in code — `os.environ["GOOGLE_APPLICATION_CREDENTIALS"]`, `process.env.KUBECONFIG`, etc. SDKs open the file.
- ❌ `cat /run/clau-secrets/...` or `Read(/run/clau-secrets/**)` — blocked by `permissions.deny` + `hooks/secrets-guard.py`.

Treat the values as opaque; the path/name is the only thing the AI should touch.

### Alternative: credentials inside the project

If you'd rather keep credentials inside the project (at a gitignored path like `.secrets/gcp.json`) than in clau's `secrets/`, that works too — the project is mounted at the same absolute path inside the container as on the host. Set `GOOGLE_APPLICATION_CREDENTIALS=/home/me/work/my-app/.secrets/gcp.json` in the project `.env`. Useful when credentials are shared with host tooling that also reads from the same spot.

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

**How it works.** Drop credentials under `secrets/<project>/broker/`
instead of `secrets/<project>/`. On `clau` start:

1. A `broker-<project>` container comes up on a private docker network
   (`clau-net-<project>`) and reads creds from `/run/broker-secrets/`.
2. The Claude container joins the same network and gets `BROKER_URL=http://broker:8080`.
   It does **not** receive the API keys themselves.
3. Claude's firewall removes Meta / Google Ads / Analytics / Search
   Console hosts; only the broker IP and the standard dev hosts are
   reachable. The broker has its own firewall (`allowlists/broker.txt`)
   that allows only the provider APIs.
4. Claude calls `POST http://broker:8080/meta/insights` etc. The broker
   injects the access token, talks to graph.facebook.com, returns the
   JSON. The token never appears in any tool result.

```
secrets/
  client-foo/
    .env              # ← visible to Claude (DB url, app secrets)
    broker/           # ← visible to broker only
      meta.env        # META_ACCESS_TOKEN=…, META_AD_ACCOUNT_ID=…
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
POST /ga4/run-report             {property_id, dimensions, metrics, date_ranges}
POST /gsc/search-analytics       {site_url, start_date, end_date, dimensions}
POST /google-ads/query           {customer_id, gaql_query}
ANY  /passthrough/meta/<path>    arbitrary Graph API call
```

**Opt-in**: if `secrets/<project>/broker/` doesn't exist, nothing
changes — the broker isn't started, behavior is identical to before.

**Lifecycle**: the broker container stays up after `clau` exits so
re-attach is fast. Stop it explicitly with `docker stop broker-<project>`.

## Defense-in-depth: secrets guard

Two layers run inside every `clau` container to catch obvious secret-reading attempts:

**Layer 1 — `permissions.deny`** in `claude-settings.json`. Mounted read-only at `/etc/claude-code/managed-settings.json` inside the container — Claude Code's "managed" scope, which overrides user/project settings and cannot be disabled by the AI. Pattern-blocks tool calls like `Read(/root/**)`, `Bash(printenv)`, `Bash(env)`, `Bash(cat:/run/secrets/**)`, etc. User preferences (theme, model, effort) still save normally to `~/.claude/settings.json`.

**Layer 2 — `PreToolUse` hook** at `hooks/secrets-guard.py`. Inspects every Bash/Read/Write/Edit call, blocks patterns like `cat /root/...`, dynamic DNS lookups (`nslookup $X`), POSTing env vars to external hosts, writing PEM blocks to disk. Logs all blocks to `/var/log/clau/secrets-guard.log` (root-owned, AI cannot read).

To tune the rules, edit `hooks/secrets-guard.py` (host side); changes take effect on next `clau` start. To disable temporarily for debugging, comment out the `hooks` block in `claude-settings.json`.

**Important**: this is *defense-in-depth*, not primary security. A determined AI can bypass these (encode the secret, use indirection, write a script). The real boundaries are: (1) sidecar broker so long-lived creds never enter the container, (2) firewall allowlist so exfil paths are blocked. The hook + deny rules raise the bar against accidental leaks and shallow attempts.

## Firewall allowlist

- Default: `allowlist.txt` (clau install root)
- Per-project override: `allowlists/<project-name>.txt`

One domain per line. The container can only reach hosts on the allowlist (plus DNS).

## Volumes

| Volume | Purpose | Scope |
|---|---|---|
| `claude-auth` | Claude OAuth session | global |
| `codex-auth` | Codex ChatGPT/API auth and Codex config | global |
| `clau-pip` | pip-installed Python packages | global, all projects |
| `clau-tools` | dev tools (Headroom, Caveman, ...) | global, all projects |
| `clau-history-<project>` | bash history | per-project |
| `clau-net-<project>` | docker network shared by `clau-<project>` + `broker-<project>` | per-project (only when broker is enabled) |
