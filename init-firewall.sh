#!/bin/bash
# init-firewall.sh — setup iptables allowlist
# Yêu cầu: container chạy với --cap-add=NET_ADMIN --cap-add=NET_RAW
set -euo pipefail

ALLOWLIST_FILE="${1:-/etc/allowlist.txt}"
BROKER_IP="${2:-}"
BROKER_PORT="${3:-}"

if [[ ! -f "$ALLOWLIST_FILE" ]]; then
  echo "⚠️  Không có allowlist file — skip firewall"
  exit 0
fi

echo "🔥 Setup firewall với allowlist: $ALLOWLIST_FILE"

# Flush rules cũ
iptables -F
iptables -X
# Do not flush the nat table. On Docker user-defined networks, Docker's
# embedded DNS at 127.0.0.11 depends on nat rules inside the container
# namespace; removing them makes every allowlist lookup resolve to nothing.

# Default DROP
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# Cho phép loopback
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Cho phép DNS (cần để resolve domain trong allowlist)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT
iptables -A INPUT -p udp --sport 53 -j ACCEPT
iptables -A INPUT -p tcp --sport 53 -j ACCEPT

# Cho phép established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Tạo ipset cho các IP allowlist
ipset destroy allowed-domains 2>/dev/null || true
ipset create allowed-domains hash:ip

# Resolve mỗi domain → add vào ipset
# `|| [[ -n "$domain" ]]`: handle allowlist files without trailing newline
# (otherwise `read` returns 1 on the last line and the loop body is skipped,
# leaving the ipset empty → all HTTPS dropped → claude hangs at startup).
while IFS= read -r domain || [[ -n "$domain" ]]; do
  # Bỏ comment và dòng trống
  domain="${domain%%#*}"
  domain="$(echo "$domain" | xargs)"
  [[ -z "$domain" ]] && continue

  echo "  → Resolving $domain"
  # getent vì dig không có sẵn trong debian slim
  ips=$(getent ahosts "$domain" | awk '{print $1}' | sort -u || true)
  for ip in $ips; do
    ipset add allowed-domains "$ip" 2>/dev/null || true
  done
done < "$ALLOWLIST_FILE"

# Chỉ cho phép outbound HTTPS/HTTP tới IP trong ipset
iptables -A OUTPUT -p tcp --dport 443 -m set --match-set allowed-domains dst -j ACCEPT
iptables -A OUTPUT -p tcp --dport 80  -m set --match-set allowed-domains dst -j ACCEPT

# Sidecar broker. Claude container reaches its paired broker on the dedicated
# docker network. Launcher resolves the broker IP and passes BROKER_IP / BROKER_PORT.
if [[ -n "${BROKER_IP:-}" && -n "${BROKER_PORT:-}" ]]; then
  iptables -A OUTPUT -p tcp -d "$BROKER_IP" --dport "$BROKER_PORT" -j ACCEPT
  echo "🔗 Broker rule: $BROKER_IP:$BROKER_PORT"
fi

echo "✅ Firewall active. Allowed IPs: $(ipset list allowed-domains | grep -c '^[0-9]')"
