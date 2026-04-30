#!/usr/bin/env bash

# Host-browser bridge for Dockerized CLI tools.
#
# The container receives BROWSER=/host-browser/host-browser and an xdg-open shim
# on PATH. When a tool tries to open an http(s) URL, the shim appends it to a
# bind-mounted log. The host wrapper polls that log and opens the URL locally.

CLAU_BROWSER_BRIDGE_DIR=""
CLAU_BROWSER_BRIDGE_READER_PID=""
CLAU_BROWSER_BRIDGE_DOCKER_ARGS=()
CLAU_BROWSER_BRIDGE_ENV=()
CLAU_BROWSER_CONTAINER_PATH="/host-browser:/opt/clau-tools/bin:/home/dev/.pip-user/bin:/home/dev/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

clau_host_open_url() {
  local url="$1"
  local os
  os="$(uname 2>/dev/null || true)"

  case "$os" in
    Darwin)
      if command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 && return 0
      fi
      ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 && return 0
      fi
      if command -v gio >/dev/null 2>&1; then
        gio open "$url" >/dev/null 2>&1 && return 0
      fi
      if command -v wslview >/dev/null 2>&1; then
        wslview "$url" >/dev/null 2>&1 && return 0
      fi
      ;;
  esac

  echo "🌐 Open this URL in your browser:"
  echo "   $url"
  return 1
}

clau_browser_bridge_start() {
  local label="${1:-container}"
  local opener url_log

  [[ -n "$CLAU_BROWSER_BRIDGE_DIR" ]] && return 0

  if ! command -v mktemp >/dev/null 2>&1; then
    echo "❌ Cannot enable browser bridge: mktemp is not available."
    return 1
  fi

  CLAU_BROWSER_BRIDGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/clau-browser.XXXXXX")" || {
    echo "❌ Cannot enable browser bridge: failed to create temp dir."
    return 1
  }
  opener="$CLAU_BROWSER_BRIDGE_DIR/host-browser"
  url_log="$CLAU_BROWSER_BRIDGE_DIR/open-url.log"
  : > "$url_log"

  cat > "$opener" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

bridge_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for arg in "$@"; do
  case "$arg" in
    http://*|https://*)
      printf '%s\n' "$arg" >> "$bridge_dir/open-url.log"
      ;;
  esac
done
EOF
  chmod +x "$opener"
  ln -s host-browser "$CLAU_BROWSER_BRIDGE_DIR/xdg-open"
  ln -s host-browser "$CLAU_BROWSER_BRIDGE_DIR/sensible-browser"
  ln -s host-browser "$CLAU_BROWSER_BRIDGE_DIR/www-browser"

  (
    seen=0
    while :; do
      if [[ -f "$url_log" ]]; then
        total="$(wc -l < "$url_log" 2>/dev/null || printf '0')"
        [[ "$total" =~ ^[0-9]+$ ]] || total=0
        if (( total > seen )); then
          while IFS= read -r url; do
            [[ -z "$url" ]] && continue
            case "$url" in
              http://*|https://*)
                echo "🌐 Opening URL in host browser."
                clau_host_open_url "$url" || true
                ;;
            esac
          done < <(sed -n "$((seen + 1)),${total}p" "$url_log" 2>/dev/null || true)
          seen="$total"
        fi
      fi
      sleep 0.4
    done
  ) &
  CLAU_BROWSER_BRIDGE_READER_PID="$!"

  CLAU_BROWSER_BRIDGE_DOCKER_ARGS=(-v "$CLAU_BROWSER_BRIDGE_DIR:/host-browser")
  CLAU_BROWSER_BRIDGE_ENV=(
    -e "BROWSER=/host-browser/host-browser"
    -e "GIT_BROWSER=/host-browser/host-browser"
    -e "PATH=$CLAU_BROWSER_CONTAINER_PATH"
  )

  echo "🌐 Host browser bridge enabled for $label"
}

clau_browser_bridge_stop() {
  if [[ -n "${CLAU_BROWSER_BRIDGE_READER_PID:-}" ]]; then
    kill "$CLAU_BROWSER_BRIDGE_READER_PID" 2>/dev/null || true
    wait "$CLAU_BROWSER_BRIDGE_READER_PID" 2>/dev/null || true
  fi
  if [[ -n "${CLAU_BROWSER_BRIDGE_DIR:-}" ]]; then
    rm -rf "$CLAU_BROWSER_BRIDGE_DIR"
  fi
  CLAU_BROWSER_BRIDGE_DIR=""
  CLAU_BROWSER_BRIDGE_READER_PID=""
  CLAU_BROWSER_BRIDGE_DOCKER_ARGS=()
  CLAU_BROWSER_BRIDGE_ENV=()
}
