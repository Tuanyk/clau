# clau

`clau` runs Claude Code, OpenAI Codex, and Google Gemini CLI inside a Docker
container with a project-aware launcher around them: firewall allowlists,
isolated auth profiles, persistent shell history, reusable tool/package volumes,
host-browser login support, pre-run snapshots, and an optional sidecar broker
for sensitive third-party credentials.

It is for people who want the convenience of `claude`, `codex`, and `gemini`,
but do not want every agent session to run directly in their normal host shell
with broad access to local environment variables, network egress, auth files,
and installed tools.

## Why this exists

Bare `claude` or `codex` is fast and simple, but it usually runs in the same
environment as the developer:

- The project directory is live and easy to mutate.
- Host environment variables may be inherited accidentally.
- Network access is whatever the host allows.
- Login state, tools, package installs, and shell history are mixed with the
  user's normal machine state.
- Multiple accounts or client contexts are awkward to keep separate.
- Long-lived provider credentials can end up inside the same process that is
  generating and executing commands.

`clau` was coded to put a repeatable boundary around those workflows. It does
not make AI coding risk-free, but it gives each project a more controlled
runtime and makes the safe path easier to use every day.

## Why use clau instead of bare Claude/Codex/Gemini?

| Area | Bare `claude` / `codex` / `gemini` | `clau` |
|---|---|---|
| Runtime | Runs directly on the host | Runs in a Docker container |
| Network | Host-level outbound access | HTTPS allowlist per project, plus broker-specific allowlist |
| Auth | CLI auth lives in the normal user profile | Docker volumes per tool and per profile |
| Account switching | Manual re-login or custom setup | `--profile`, `clau-login --profile`, `codex-login --profile`, `gemini-login --profile` |
| Secrets | Easy to expose through env/files if mounted | Secret paths, guard hooks, managed Claude settings, optional broker |
| Provider API keys | Usually inside the agent runtime | Optional broker sidecar keeps provider keys outside the AI container |
| Recovery | Depends on git or manual backups | Host-side snapshot before fresh container start |
| Tools/packages | Installed into host or project | Persistent shared volumes: `clau-pip`, `clau-tools`, `clau-npm` |
| Browser login | CLI decides how to open URLs | Host browser bridge for OAuth/device login |
| Project context | Manual instructions per repo | Auto-seeded `CLAUDE.md` and `AGENTS.md` guidance |

## Main features

- One command for a containerized coding shell: `clau`.
- Direct launch modes: `clau --claude`, `clau --codex`, and `clau --gemini`.
- Named auth profiles for Claude, Codex, and Gemini.
- Profile listing and deletion: `clau profiles`.
- Per-project firewall allowlist.
- Pre-run snapshots with `clau-restore`.
- Host-browser bridge for login and browser-open requests.
- Persistent pip/npm/tool volumes shared across projects.
- Optional broker sidecar for Meta, GA4, GSC, GTM, and Google Ads credentials.
- Auto-seeded `CLAUDE.md` and `AGENTS.md` instructions for each project.

## Install

```bash
./install.sh        # build images and symlink commands into ~/.local/bin
clau-update         # refresh Claude Code + Codex + Gemini CLI using cached Docker layers
clau-login          # one-time Claude OAuth login (stored in `claude-auth`)
codex-login         # one-time Codex ChatGPT login (stored in `codex-auth`)
gemini-login        # one-time Gemini login (stored in `gemini-auth`)
clau profiles       # list Claude/Codex/Gemini auth profiles
```

`clau-login`, `codex-login`, and `gemini-login` enable the host browser bridge
by default: if the CLI tries to open a login URL, your normal desktop browser
opens it. Use `--no-browser` to disable that and copy URLs manually.

`clau-update` rebuilds only the final Dockerfile tail that installs Claude Code,
Codex, and Gemini CLI. It does not rebuild the broker image and does not touch
auth, history, pip, npm, or tool volumes. Restart running `clau` containers
afterward.

## Quick start

```bash
cd ~/path/to/project
clau
```

That starts or attaches to a project container and drops you into a shell. From
there you can run `claude`, `codex`, tests, package managers, build tools, and
normal shell commands inside the container.

Common commands:

```bash
clau                         # shell in the container
clau --claude                # open Claude directly
clau --codex                 # open Codex directly
clau --gemini                # open Gemini CLI directly
clau --browser               # shell with host-browser bridge
clau --profile work --claude # use a named auth profile
clau --profile work --codex
clau --profile work --gemini
clau --claude --yolo         # Claude + --dangerously-skip-permissions
clau --codex --yolo          # Codex + bypass sandbox/approvals
clau --gemini --yolo         # Gemini + --yolo (auto-accept tool calls)
clau --no-firewall           # debug without the main AI container allowlist
clau --help                  # show all options and important env vars
```

## Auth profiles

Claude, Codex, and Gemini credentials are intentionally separate:

```text
claude-auth            -> /home/dev/.claude
codex-auth             -> /home/dev/.codex
gemini-auth            -> /home/dev/.gemini
claude-auth-<profile>  -> /home/dev/.claude
codex-auth-<profile>   -> /home/dev/.codex
gemini-auth-<profile>  -> /home/dev/.gemini
```

The default profile keeps using the original `claude-auth`, `codex-auth`, and
`gemini-auth` volumes, so existing logins continue to work. Use named profiles
to rotate between accounts or clients:

```bash
clau-login --profile work
codex-login --profile work
gemini-login --profile work
clau --profile work --claude
clau --profile work --codex
clau --profile work --gemini
CLAU_PROFILE=work clau --codex
```

List or delete auth profiles:

```bash
clau profiles
clau profiles delete work        # delete Claude + Codex + Gemini auth volumes for work
clau profiles delete work --claude
clau profiles delete work --codex
clau profiles delete work --gemini
clau profiles delete default --all --yes
```

By default, a normal shell or Claude run mounts only the selected Claude auth
volume. `clau --codex` mounts only the selected Codex auth volume; `clau
--gemini` mounts only the selected Gemini auth volume. Set
`CLAU_WITH_CODEX_AUTH=1` or `CLAU_WITH_GEMINI_AUTH=1` if you need that auth
volume alongside Claude in a normal shell, or `CLAU_WITHOUT_AUTH=1` for a shell
with no AI auth volumes mounted.

The launcher intentionally blanks `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, and `GOOGLE_API_KEY` for the AI container, even if they exist
on the host or in an env file. This keeps the CLIs on their OAuth/session auth
path instead of accidentally inheriting long-lived host API keys.

## Ports and browser bridge

By default, `clau` maps the first free host port starting at `13000` to port
`3000` inside the container. A dev server can still listen on `3000` inside the
container; open the host port printed by `clau`, for example
`http://localhost:13000`.

```bash
CLAU_PORTS=auto:3000 clau          # first free host port from 13000 -> container 3000
CLAU_PORTS=3001:3000 clau          # fixed host localhost:3001 -> container 3000
CLAU_PORTS=auto:3000,auto:5173 clau
CLAU_DEFAULT_HOST_PORT=14000 clau  # change the auto-search starting point
CLAU_PORTS="" clau                 # no forwarded ports
```

`clau --browser` does not install a GUI browser inside Docker. It sets
`BROWSER` and an `xdg-open` shim in the container, then opens requested URLs on
the host. If a project container is already running, stop it first; Docker
cannot add the browser bridge mount to an existing container.

## Project identity

`clau` prints the resolved project name + path on startup:

```
📁 Project: my-app  (/home/you/work/my-app)
```

The project name is the lowercased basename of the cwd, so `~/work/my-app` and
`~/personal/my-app` share `~/.clau/secrets/`, `~/.clau/allowlists/`, container,
and history. To disambiguate, override with `CLAU_PROJECT_NAME`:

```bash
cd ~/personal/my-app && CLAU_PROJECT_NAME=my-app-personal clau
```

Then clau uses `~/.clau/secrets/my-app-personal/`,
`~/.clau/allowlists/my-app-personal.txt`, container
`clau-my-app-personal`, and matching history/snapshot names.

## Codex compatibility on Linux

On Linux, `clau` starts the Docker container with
`--security-opt seccomp=unconfined --security-opt apparmor=unconfined` so
Codex's bubblewrap sandbox can create its nested namespaces inside Docker. To
turn those Docker options off for debugging:

```bash
CLAU_BWRAP_OPTS=0 clau
```

Codex model availability depends on the installed Codex CLI version and the
signed-in account. Run `clau-update` to refresh the CLI layer without touching
auth, history, pip, npm, or tool volumes.

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
- pip, npm cache, and `/opt/clau-tools/bin` persist across sessions.

To customize, edit `templates/CLAUDE.md` and `templates/AGENTS.md` in the clau install dir (affects future projects) or the file inside the project (that project only). **Keep the `<!-- clau:seed-v1 -->` marker comment** — deleting it will cause clau to append the section again on the next run. To disable seeding entirely, `export CLAU_SKIP_AUTO_DOCS=1`.

You'll usually want to add a per-project **Secrets** section that names the env vars available. For example:

```markdown
## Secrets

- `APP_OPENAI_API_KEY` — app-scoped OpenAI API key
- `DATABASE_URL` — Postgres connection string
- `GOOGLE_APPLICATION_CREDENTIALS` — path to GCP service account JSON
```

That tells the AI (1) what's available, (2) the exact variable names to use, and (3) not to leak the values into the chat or logs.

## Python and npm packages persist

`pip install <anything>` inside the container goes into the shared `clau-pip` Docker volume (mounted at `/home/dev/.pip-user`). Packages survive container restarts and are shared across all projects.

The container also mounts a shared `clau-npm` volume at `/home/dev/.npm`, so npm
cache data survives container restarts.

To wipe and start fresh:

```bash
docker volume rm clau-pip
docker volume rm clau-npm
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

## Sidecar broker (keep API keys out of the AI container)

For long-lived third-party credentials — Meta access tokens, Google
service-account JSON, Google Ads developer/refresh tokens — the
defense-in-depth layers below are *not enough*. Anything that lives in
the AI runtime can theoretically be encoded and exfiltrated. The broker
sidecar moves those secrets out of the AI container entirely.

**How it works.** Drop credentials under `~/.clau/secrets/<project>/broker/`
instead of `~/.clau/secrets/<project>/`. On `clau` start:

1. A `broker-<project>` container comes up on a private docker network
   (`clau-net-<project>`) and reads creds from `/run/broker-secrets/`.
2. The AI container joins the same network and gets `BROKER_URL=http://broker:8080`
   plus a per-run `BROKER_AUTH_TOKEN`. It does **not** receive the provider API keys themselves.
3. The AI container firewall removes Meta / Google Ads / Analytics / Search
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
(`broker-<project>`) on its own docker network. Project A's AI container can't
reach project B's broker — they're on different networks with different
credentials.

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
| `claude-auth`, `claude-auth-<profile>` | Claude OAuth session | global per profile |
| `codex-auth`, `codex-auth-<profile>` | Codex ChatGPT/API auth and Codex config | global per profile |
| `gemini-auth`, `gemini-auth-<profile>` | Gemini OAuth/API auth and config | global per profile |
| `clau-pip` | pip-installed Python packages | global, all projects |
| `clau-npm` | npm cache | global, all projects |
| `clau-tools` | dev tools (Headroom, Caveman, ...) | global, all projects |
| `clau-history-<project>` | bash history | per-project |
| `clau-net-<project>` | docker network shared by `clau-<project>` + `broker-<project>` | per-project (only when broker is enabled) |
