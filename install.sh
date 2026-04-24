#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINK_DIR="$HOME/.local/bin"

echo "📦 Build image..."
docker build \
  --build-arg USER_UID=$(id -u) \
  --build-arg USER_GID=$(id -g) \
  -t claude-base \
  "$SCRIPT_DIR"

mkdir -p "$LINK_DIR" "$SCRIPT_DIR/secrets" "$SCRIPT_DIR/allowlists"
chmod +x "$SCRIPT_DIR/clau" "$SCRIPT_DIR/clau-login" "$SCRIPT_DIR/codex-login" \
         "$SCRIPT_DIR/entrypoint.sh" "$SCRIPT_DIR/init-firewall.sh"
ln -sf "$SCRIPT_DIR/clau" "$LINK_DIR/clau"
ln -sf "$SCRIPT_DIR/clau-login" "$LINK_DIR/clau-login"
ln -sf "$SCRIPT_DIR/codex-login" "$LINK_DIR/codex-login"

if [[ ":$PATH:" != *":$LINK_DIR:"* ]]; then
  echo ""
  echo "⚠️  Thêm vào shell config:"
  echo '   export PATH="$HOME/.local/bin:$PATH"'
fi

cat <<EOF

✓ Xong. Tiếp theo:
   1. clau-login                  # Claude login (1 lần)
   2. codex-login                 # Codex ChatGPT login (1 lần)
   3. cd ~/work/du-an && clau     # chạy shell (mặc định có firewall)
   4. clau --codex                # mở Codex trực tiếp trong container
   5. clau --yolo                 # Claude + --dangerously-skip-permissions
   6. clau --codex --yolo         # Codex + bypass sandbox/approvals trong container
   7. clau --no-firewall          # tắt firewall (debug)

Allowlist mặc định: $SCRIPT_DIR/allowlist.txt
Override theo dự án: $SCRIPT_DIR/allowlists/<ten-du-an>.txt
EOF
