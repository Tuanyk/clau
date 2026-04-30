# Security Review: clau AI Tool Isolation

Reviewed on: 2026-04-28

## Scope

This review checks whether `clau` protects API keys, Google credentials, Meta
credentials, Google Ads credentials, and other long-lived secrets during
Claude/Codex runs.

Covered files:

- `clau`
- `Dockerfile`
- `entrypoint.sh`
- `init-firewall.sh`
- `claude-settings.json`
- `hooks/secrets-guard.py`
- `broker/`
- security-related docs and templates

No host secret directories were read, no environment values were printed, and no
real credential values were inspected.

## Current Assessment

The broker path is now the right place for production Meta, Google, Google Ads,
GA4, GSC, and similar long-lived provider credentials.

Credentials placed under:

```text
~/.clau/secrets/<project>/broker/
```

are mounted read-only into the broker at:

```text
/run/broker-secrets
```

and are no longer mounted into the AI container under `/run/clau-secrets`.

Do **not** treat ordinary environment variables, project `.env` files, or
top-level `/run/clau-secrets` files as hidden from the AI. Those are convenience
features for low-risk app runtime values and SDK file paths, not strong secret
isolation.

## Fixed Since The Previous Draft

### Broker Credentials Are No Longer Mounted Into The AI Container

The launcher now mounts only top-level files from
`~/.clau/secrets/<project>/` into `/run/clau-secrets`.

It does not mount directories, so:

```text
~/.clau/secrets/<project>/broker/
```

stays broker-only.

### Project `.env` Is Not Auto-Loaded By Default

The project root `.env` file is no longer automatically passed with
`--env-file`. It is still visible if it exists in the mounted workspace, so it
must not contain high-value production credentials.

Legacy loading is available only with:

```bash
CLAU_LOAD_PROJECT_ENV=1 clau
```

### Broker Endpoints Require A Per-Run Token

The launcher generates a per-run `BROKER_AUTH_TOKEN`, passes it to the broker
and paired AI container, and broker endpoints require:

```text
Authorization: Bearer $BROKER_AUTH_TOKEN
```

This includes `/health`, `/docs`, and `/dashboard`.

### Broker Dashboard Host Publishing Is Opt-In

The broker is no longer published to a host localhost port by default. Use:

```bash
CLAU_BROKER_DASHBOARD=1 clau
```

to publish it on `127.0.0.1`.

### Broker Logs Are Metadata-Only By Default

Broker request logs now default to metadata only: method, path, status, timing,
byte counts, and content types.

Request body logging is opt-in:

```bash
BROKER_LOG_BODIES=1
```

When enabled, known sensitive request fields are redacted.

### Passwordless Sudo Was Removed From The AI User

The main container now starts its entrypoint as root, sets up the firewall and
volumes, then drops to the unprivileged `dev` user with `gosu`. The `dev` user
no longer has blanket passwordless sudo.

The broker follows the same pattern: root entrypoint for firewall setup, then
drop to the `broker` user before starting `uvicorn`.

### Auth Volume Exposure Was Reduced

The launcher no longer mounts both Claude and Codex auth volumes by default.

- normal shell / `clau --claude`: mounts the selected Claude auth profile volume
- `clau --codex`: mounts the selected Codex auth profile volume
- default profile volumes remain `claude-auth` and `codex-auth`; named profiles
  use `claude-auth-<profile>` and `codex-auth-<profile>`
- `CLAU_WITH_CODEX_AUTH=1`: explicitly mount Codex auth in normal shell / Claude mode
- `CLAU_WITHOUT_AUTH=1`: mount neither auth volume

This does not hide a CLI's own auth credentials from that CLI process, but it
reduces unnecessary cross-tool exposure.

### Docker Build Context Is Now Filtered

A `.dockerignore` now excludes common secret and local-state paths such as
`secrets/`, `allowlists/`, `.env`, `*.env`, `.codex/`, and `.claude/`.

## Remaining Risks

### Environment Variables Are Visible To The AI Process

Anything passed through `--env-file` or `-e` is available to processes inside
the AI container. Hooks can block obvious `env` and `printenv` commands, but
they are not a hard boundary.

Use broker-only secrets for high-value provider credentials.

### Workspace Secrets Are Visible

The project directory is bind-mounted live into the container. Any `.env`,
`.secrets/`, service-account JSON, SSH key, or other credential stored in the
workspace can be read by code running in the container.

### Top-Level File Secrets Are Still AI-Visible

Top-level files under:

```text
~/.clau/secrets/<project>/
```

are intentionally mounted into `/run/clau-secrets` so SDKs can read them by
path. These should be limited to low-risk or task-required credentials. Put
long-lived Meta/Google/Google Ads credentials under `broker/` instead.

### DNS Remains A Residual Exfiltration Channel

The firewall restricts HTTP/S egress by allowlisted domains and removes the
easy sudo-based iptables bypass. DNS is still required for resolution and should
not be considered a complete protection against deliberate exfiltration of
secrets already present inside the AI container.

### Auth Volumes Remain Sensitive

Claude and Codex auth volumes are still readable by the corresponding CLI
process when mounted. This is operationally necessary for OAuth/device login,
but those accounts should be scoped with the assumption that the active tool can
use its own session.

### Codex Compatibility Relaxes Outer Container Profiles

On Linux, the launcher still relaxes the outer Docker seccomp/AppArmor profiles
by default so Codex can run its nested sandbox. This improves tool compatibility
but weakens container hardening. Set `CLAU_BWRAP_OPTS=0` to keep Docker's
default profiles when your Codex workflow does not need the relaxed mode.

## Recommended Operating Model

For production or client credentials:

1. Put Meta, Google Ads, GA4, GSC, GTM, and service-account credentials under
   `~/.clau/secrets/<project>/broker/`.
2. Use broker endpoints with `Authorization: Bearer $BROKER_AUTH_TOKEN`.
3. Keep project `.env` files free of production credentials.
4. Do not put long-lived provider credentials in top-level
   `~/.clau/secrets/<project>/` unless the AI truly needs direct file access.
5. Keep broker request body logging disabled unless debugging requires it.

## Final Assessment

After these changes, the broker sidecar provides a reasonable isolation boundary
for long-lived third-party provider credentials, as long as those credentials are
placed under the broker-only directory.

The system still cannot make secrets safe once they are placed in the AI
container environment, mounted workspace, auth volume, or top-level
`/run/clau-secrets`. Use those paths only with that visibility in mind.
