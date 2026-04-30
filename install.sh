#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINK_DIR="$HOME/.local/bin"

echo "📦 Build image: claude-base..."
DOCKER_BUILDKIT=1 docker build \
  --build-arg USER_UID=$(id -u) \
  --build-arg USER_GID=$(id -g) \
  -t claude-base \
  "$SCRIPT_DIR"

# Broker sidecar image (holds API creds outside the Claude container).
# Build context = repo root so the Dockerfile can COPY init-firewall.sh.
echo "📦 Build image: clau-broker..."
DOCKER_BUILDKIT=1 docker build \
  -t clau-broker \
  -f "$SCRIPT_DIR/broker/Dockerfile" \
  "$SCRIPT_DIR"

mkdir -p "$LINK_DIR" "$HOME/.clau/secrets" "$HOME/.clau/allowlists"
chmod +x "$SCRIPT_DIR/clau" "$SCRIPT_DIR/clau-login" "$SCRIPT_DIR/codex-login" \
         "$SCRIPT_DIR/clau-restore" \
         "$SCRIPT_DIR/entrypoint.sh" "$SCRIPT_DIR/init-firewall.sh" \
         "$SCRIPT_DIR/broker/entrypoint.sh"
ln -sf "$SCRIPT_DIR/clau" "$LINK_DIR/clau"
ln -sf "$SCRIPT_DIR/clau-login" "$LINK_DIR/clau-login"
ln -sf "$SCRIPT_DIR/codex-login" "$LINK_DIR/codex-login"
ln -sf "$SCRIPT_DIR/clau-restore" "$LINK_DIR/clau-restore"

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
   4. clau --claude               # mở Claude trực tiếp trong container
   5. clau --codex                # mở Codex trực tiếp trong container
   6. clau --claude --yolo        # Claude + --dangerously-skip-permissions
   7. clau --codex --yolo         # Codex + bypass sandbox/approvals trong container
   8. clau --no-firewall          # tắt firewall (debug)

Allowlist mặc định: $SCRIPT_DIR/allowlist.txt
Override theo dự án: $HOME/.clau/allowlists/<ten-du-an>.txt
Secrets per-project:  $HOME/.clau/secrets/<ten-du-an>/   (.env + credential files)
Override paths:       CLAU_SECRETS_DIR / CLAU_ALLOWLISTS_DIR
EOF
