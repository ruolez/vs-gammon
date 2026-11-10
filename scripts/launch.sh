#!/bin/bash
# Run by the "VS Gammon" desktop shortcut: make sure the server is up, then open it in the browser.
set -u

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LOG="$HOME/Library/Logs/VS Gammon.log"

PORT="$(grep '^APP_PORT=' "$APP_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2)"
PORT="${PORT:-5563}"
URL="http://localhost:$PORT"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }
notify() { osascript -e "display notification \"$1\" with title \"VS Gammon\"" >/dev/null 2>&1 || true; }
fail() {
  log "ERROR: $1"
  osascript -e "display alert \"VS Gammon could not start\" message \"$1\" as critical" >/dev/null 2>&1
  exit 1
}
healthy() { curl -fsS --max-time 2 "$URL/health" >/dev/null 2>&1; }

if healthy; then
  open "$URL"
  exit 0
fi

log "server not answering on port $PORT, starting it"
command -v docker >/dev/null 2>&1 || fail "Docker Desktop is not installed. Run install.sh again to set it up."

if ! docker info >/dev/null 2>&1; then
  notify "Starting Docker Desktop…"
  open -a Docker >/dev/null 2>&1 || fail "Docker Desktop could not be opened."
  for _ in $(seq 1 90); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
  docker info >/dev/null 2>&1 || fail "Docker Desktop did not start within 3 minutes."
fi

notify "Starting VS Gammon…"
(cd "$APP_DIR" && docker compose up -d >> "$LOG" 2>&1) || fail "The server could not be started. Details are in ~/Library/Logs/VS Gammon.log."

for _ in $(seq 1 90); do
  if healthy; then
    log "server is up on port $PORT"
    open "$URL"
    exit 0
  fi
  sleep 2
done
fail "The server did not answer on $URL within 3 minutes. Details are in ~/Library/Logs/VS Gammon.log."
