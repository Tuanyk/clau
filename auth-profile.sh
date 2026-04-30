#!/usr/bin/env bash

clau_auth_profile_normalize() {
  local raw="${1:-default}"
  local normalized

  normalized="$(printf '%s' "$raw" \
    | tr '[:upper:]' '[:lower:]' \
    | tr -c 'a-z0-9_.-' '-')"
  normalized="${normalized##[-_.]}"
  normalized="${normalized%%[-_.]}"

  if [[ -z "$normalized" ]]; then
    normalized="default"
  fi

  printf '%s\n' "$normalized"
}

clau_auth_volume_name() {
  local base="$1"
  local profile="$2"

  if [[ "$profile" == "default" ]]; then
    printf '%s\n' "$base"
  else
    printf '%s-%s\n' "$base" "$profile"
  fi
}

clau_auth_parse_profile_arg() {
  local value="${1:-}"

  if [[ -z "$value" ]]; then
    echo "❌ --profile requires a name" >&2
    return 1
  fi
  printf '%s\n' "$value"
}
