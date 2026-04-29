#!/bin/bash
set -e

if [ "$(id -u)" = "0" ]; then
  # Symlink ~/.claude.json so Claude state persists with the mounted .claude volume.
  mkdir -p /home/dev/.claude /home/dev/.codex /home/dev/.history-store /home/dev/.npm /home/dev/.pip-user /var/log/clau
  if [ ! -L /home/dev/.claude.json ]; then
    rm -f /home/dev/.claude.json
    ln -s /home/dev/.claude/claude.json /home/dev/.claude.json
  fi
  chown -R dev:dev /home/dev/.claude /home/dev/.codex /home/dev/.history-store /home/dev/.npm /home/dev/.pip-user /var/log/clau 2>/dev/null || true
else
  mkdir -p /home/dev/.claude /home/dev/.codex
fi

# Setup firewall nếu có allowlist được mount. BROKER_IP/PORT pass dạng positional
# vì argv vẫn qua được nguyên vẹn.
# CLAU_INBOUND_PORTS = published container ports that need INPUT ACCEPT so
# `docker -p host:container` actually reaches the dev server.
if [ -f /etc/allowlist.txt ] && [ -n "${CLAU_FIREWALL:-}" ]; then
  if [ "$(id -u)" != "0" ]; then
    sudo /usr/local/bin/init-firewall.sh /etc/allowlist.txt "${BROKER_IP:-}" "${BROKER_PORT:-}" "${CLAU_INBOUND_PORTS:-}"
  else
    /usr/local/bin/init-firewall.sh /etc/allowlist.txt "${BROKER_IP:-}" "${BROKER_PORT:-}" "${CLAU_INBOUND_PORTS:-}"
  fi
fi

# Traffic log (debug mode): sniff DNS queries, append unique-ish hostnames.
# Enabled bằng CLAU_TRAFFIC_LOG=<path>. Thường đi kèm --no-firewall để biết
# app cần gì mà add vào allowlist sau.
if [ -n "${CLAU_TRAFFIC_LOG:-}" ]; then
  mkdir -p "$(dirname "$CLAU_TRAFFIC_LOG")" 2>/dev/null || true
  : > "$CLAU_TRAFFIC_LOG" 2>/dev/null || { touch "$CLAU_TRAFFIC_LOG"; chown dev:dev "$CLAU_TRAFFIC_LOG"; }
  (
    if [ "$(id -u)" = "0" ]; then
      tcpdump -l -p -n -i any 'udp and port 53' 2>/dev/null
    else
      sudo tcpdump -l -p -n -i any 'udp and port 53' 2>/dev/null
    fi \
      | grep --line-buffered -oP ' (A|AAAA)\? \K[^ ]+' \
      | sed -u 's/\.$//' \
      >> "$CLAU_TRAFFIC_LOG"
  ) &
  echo "📝 DNS log: $CLAU_TRAFFIC_LOG  (xem: sort -u $CLAU_TRAFFIC_LOG)"
fi

if [ "$(id -u)" = "0" ]; then
  export HOME=/home/dev
  export USER=dev
  export LOGNAME=dev
  export SHELL=/bin/bash
  if command -v gosu >/dev/null 2>&1; then
    exec gosu dev "$@"
  fi
  exec runuser -u dev -- "$@"
fi

exec "$@"
