#!/bin/bash
set -e

# Symlink ~/.claude.json để persist cùng volume .claude/
mkdir -p /home/dev/.claude
if [ ! -L /home/dev/.claude.json ]; then
  rm -f /home/dev/.claude.json
  ln -s /home/dev/.claude/claude.json /home/dev/.claude.json
fi

# Setup firewall nếu có allowlist được mount
if [ -f /etc/allowlist.txt ] && [ -n "${CLAU_FIREWALL:-}" ]; then
  sudo /usr/local/bin/init-firewall.sh /etc/allowlist.txt
fi

exec "$@"