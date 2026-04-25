#!/bin/bash
set -e

# Source every *.env file under /run/broker-secrets so credentials show up
# in the broker process environment. Files there are read-only, owned by
# root, only this container can see them.
if [ -d /run/broker-secrets ]; then
  for f in /run/broker-secrets/*.env; do
    [ -e "$f" ] || continue
    set -a
    # shellcheck disable=SC1090
    . "$f"
    set +a
  done
fi

# Firewall (default-deny + allowlist). Broker doesn't have its own broker
# sidecar, so positional 2/3 stay empty and the broker-rule block is skipped.
if [ -f /etc/allowlist.txt ] && [ -n "${CLAU_FIREWALL:-}" ]; then
  sudo /usr/local/bin/init-firewall.sh /etc/allowlist.txt
fi

exec "$@"
