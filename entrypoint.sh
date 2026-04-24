#!/bin/bash
set -e

# Symlink ~/.claude.json để persist cùng volume .claude/
mkdir -p /home/dev/.claude
if [ ! -L /home/dev/.claude.json ]; then
  rm -f /home/dev/.claude.json
  ln -s /home/dev/.claude/claude.json /home/dev/.claude.json
fi

# Codex stores auth/config/history under ~/.codex; the launcher mounts this
# directory from the codex-auth Docker volume.
mkdir -p /home/dev/.codex

# Setup firewall nếu có allowlist được mount
if [ -f /etc/allowlist.txt ] && [ -n "${CLAU_FIREWALL:-}" ]; then
  sudo /usr/local/bin/init-firewall.sh /etc/allowlist.txt
fi

# Traffic log (debug mode): sniff DNS queries, append unique-ish hostnames.
# Enabled bằng CLAU_TRAFFIC_LOG=<path>. Thường đi kèm --no-firewall để biết
# app cần gì mà add vào allowlist sau.
if [ -n "${CLAU_TRAFFIC_LOG:-}" ]; then
  mkdir -p "$(dirname "$CLAU_TRAFFIC_LOG")" 2>/dev/null || true
  : > "$CLAU_TRAFFIC_LOG" 2>/dev/null || { sudo touch "$CLAU_TRAFFIC_LOG"; sudo chown dev:dev "$CLAU_TRAFFIC_LOG"; }
  (
    sudo tcpdump -l -p -n -i any 'udp and port 53' 2>/dev/null \
      | grep --line-buffered -oP ' (A|AAAA)\? \K[^ ]+' \
      | sed -u 's/\.$//' \
      >> "$CLAU_TRAFFIC_LOG"
  ) &
  echo "📝 DNS log: $CLAU_TRAFFIC_LOG  (xem: sort -u $CLAU_TRAFFIC_LOG)"
fi

exec "$@"
