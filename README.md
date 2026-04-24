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

Claude and Codex credentials are intentionally separate:

```text
claude-auth -> /home/dev/.claude
codex-auth  -> /home/dev/.codex
```

This keeps OAuth/session credentials inside Docker volumes instead of using your host API keys. The launcher intentionally blanks `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` for the container, even if they exist on the host or in an env file, so Claude/Codex do not inherit long-lived API keys.

## Secrets / API keys / credentials

Two ways to inject env vars into the container. Both are loaded with `--env-file`, so the AI sees them as normal environment variables.

### 1. Per-project secrets (recommended for keys you don't want in the project repo)

Drop a `.env` file at `secrets/<project-name>.env` inside the clau install dir. `<project-name>` is the lowercased basename of your project directory. Example:

```bash
# project at ~/work/my-app  →  project-name = "my-app"
cat > /path/to/clau/secrets/my-app.env <<EOF
APP_OPENAI_API_KEY=sk-...
DATABASE_URL=postgres://...
EOF
```

This directory is gitignored (see `.gitignore`).

### 2. Project `.env` (loaded if present in the project root)

If your project already has a `.env`, clau auto-mounts it. Make sure it's gitignored in the project itself.

Both files are loaded if both exist; project `.env` wins on conflicting keys.

### Credential files (not just env vars)

For things like `gcloud` credentials JSON or SSH keys, mount them as files. Easiest path: keep them inside the project at a gitignored path and reference them by path from a `.env`. The project is mounted at the same absolute path inside the container as on the host, so use the host path:

```env
# if your project is at /home/me/work/my-app
GOOGLE_APPLICATION_CREDENTIALS=/home/me/work/my-app/.secrets/gcp.json
```

Then put the JSON inside your project at `.secrets/gcp.json` (gitignored) — it's available at the same path inside the container.

## Auto-seeded AI instructions (`CLAUDE.md` / `AGENTS.md`)

On every `clau` run, the project root's `CLAUDE.md` (Claude Code) and `AGENTS.md` (Codex) are checked for a `clau:seed-v1` marker:

| Project state | What clau does |
|---|---|
| File missing | Copy the full template into the project |
| File exists, marker present | Skip (already seeded) |
| File exists, no marker | Append the template content to the end |

The appended section tells the AI:

- Reference secrets **by name** in code, never print/log/cat their values.
- The container is firewalled — domains not in `allowlist.txt` will fail.
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

## Defense-in-depth: secrets guard

Two layers run inside every `clau` container to catch obvious secret-reading attempts:

**Layer 1 — `permissions.deny`** in `claude-settings.json`. Pattern-blocks Claude Code tool calls like `Read(/root/**)`, `Bash(printenv)`, `Bash(env)`, `Bash(cat:/run/secrets/**)`, etc.

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
