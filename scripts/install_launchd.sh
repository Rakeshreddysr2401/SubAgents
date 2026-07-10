#!/bin/bash
# Install SubAgents as a launchd agent: auto-start at login, restart on crash.
#   ./scripts/install_launchd.sh          install + start
#   ./scripts/install_launchd.sh remove   stop + uninstall
set -euo pipefail

LABEL="com.subagents.server"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/launchd/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UV_BIN="$(command -v uv || true)"

if [[ "${1:-}" == "remove" ]]; then
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  rm -f "$PLIST_DST"
  echo "Removed ${LABEL}."
  exit 0
fi

if [[ -z "$UV_BIN" ]]; then
  echo "uv not found on PATH — install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

mkdir -p "$HOME/.subagents" "$HOME/Library/LaunchAgents"
sed -e "s|__UV__|${UV_BIN}|g" \
    -e "s|__REPO__|${REPO}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "$PLIST_SRC" > "$PLIST_DST"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
echo "Installed ${LABEL} — server starts at login and restarts on crash."
echo "Logs: tail -f ~/.subagents/server.log"
