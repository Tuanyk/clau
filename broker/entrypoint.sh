#!/bin/bash
set -e

# Broker env files are loaded by app.config via python-dotenv. Do not source
# them here: they are data files, not shell scripts, and malformed lines should
# never be executed as commands.

# Firewall (default-deny + allowlist). Broker doesn't have its own broker
# sidecar, so positional 2/3 stay empty and the broker-rule block is skipped.
if [ -f /etc/allowlist.txt ] && [ -n "${CLAU_FIREWALL:-}" ]; then
  sudo /usr/local/bin/init-firewall.sh /etc/allowlist.txt
fi

exec "$@"
