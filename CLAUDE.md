<!-- clau:seed-v1 — keep this marker so clau won't re-append this section. Edit content below freely. -->

## Secrets

API keys, tokens, and credentials are available as environment variables.

- Reference them **by name** in code (e.g. `os.environ["APP_API_KEY"]`, `process.env.APP_API_KEY`).
- Do NOT `cat`, `echo`, `printenv`, log, or otherwise print their values — treat them as opaque.
- Do not write them to disk or commit them.

If you need to know which env vars are available, ask the user — do not enumerate the environment yourself.

## Network

This project runs inside a Docker container with a firewall allowlist. Outbound HTTPS only reaches hosts in `allowlist.txt` (in the clau install dir) or `allowlists/<project>.txt`. If a request fails with "connection refused" / "no route to host", the domain likely needs adding to the allowlist.

## Python / tools

- `pip install <pkg>` persists across sessions via the shared `clau-pip` volume.
- Dev tools installed under `/opt/clau-tools/bin` persist via the `clau-tools` volume.
