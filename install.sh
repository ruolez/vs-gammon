#!/usr/bin/env bash
# VS Gammon installer for macOS (Docker Desktop).
#
#   curl -fsSL https://raw.githubusercontent.com/ruolez/vs-gammon/refs/heads/main/install.sh | bash
#   ~/vs-gammon/install.sh [install|update|start|stop|status|backup|restore FILE|shortcut|uninstall] [--yes]
#
# Installs into ~/vs-gammon (override with VSG_HOME), keeps matches and settings in ~/vs-gammon/data,
# and puts a "VS Gammon" shortcut on the Desktop that starts the server when needed.
# Written for the bash 3.2 that ships with macOS.

set -euo pipefail

APP_NAME="VS Gammon"
REPO_URL="${VSG_REPO:-https://github.com/ruolez/vs-gammon.git}"
BRANCH="${VSG_BRANCH:-main}"
INSTALL_DIR="${VSG_HOME:-$HOME/vs-gammon}"
DEFAULT_PORT=5563
SHORTCUT="$HOME/Desktop/$APP_NAME.app"
LEGACY_CONTAINERS="vs-gammon gammon-analyzer"
LEGACY_IMAGES="gammon-analyzer:latest gammon-spike:latest"
ASSUME_YES="${VSG_YES:-0}"
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

for arg in "$@"; do
  [ "$arg" = "--yes" ] || [ "$arg" = "-y" ] && ASSUME_YES=1
done

# A running bash script must not be rewritten under its own feet: when this file lives inside
# the install folder (which update replaces), run from a temporary copy instead.
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ] && [ -z "${VSG_REEXEC:-}" ]; then
  case "$(cd "$(dirname "$SELF")" && pwd)" in
    "$INSTALL_DIR" | "$INSTALL_DIR"/*)
      TMP_SELF="$(mktemp -t vs-gammon-install)"
      cp "$SELF" "$TMP_SELF"
      VSG_REEXEC=1 exec bash "$TMP_SELF" "$@"
      ;;
  esac
fi

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
info() { printf '  \033[34m›\033[0m %s\n' "$*"; }
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die() { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

has_tty() { [ -r /dev/tty ] && [ -w /dev/tty ] && (exec < /dev/tty) 2>/dev/null; }

ask() {
  local prompt="$1" default="$2" answer=""
  if [ "$ASSUME_YES" = "1" ] || ! has_tty; then
    echo "$default"
    return
  fi
  read -r -p "  $prompt " answer < /dev/tty || true
  echo "${answer:-$default}"
}

confirm() {
  local default="${2:-n}" hint="[y/N]" answer
  [ "$default" = "y" ] && hint="[Y/n]"
  answer="$(ask "$1 $hint" "$default")"
  case "$answer" in y | Y | yes | YES) return 0 ;; *) return 1 ;; esac
}

compose() { (cd "$INSTALL_DIR" && docker compose "$@"); }

env_value() {
  grep "^$1=" "$INSTALL_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2-
}

set_env() {
  local key="$1" value="$2" file="$INSTALL_DIR/.env"
  touch "$file"
  if grep -q "^${key}=" "$file"; then
    sed -i '' "s|^${key}=.*|${key}=${value}|" "$file"
  else
    echo "${key}=${value}" >> "$file"
  fi
}

port() {
  local p
  p="$(env_value APP_PORT)"
  echo "${p:-$DEFAULT_PORT}"
}

app_url() { echo "http://localhost:$(port)"; }

host_timezone() {
  local link
  link="$(readlink /etc/localtime 2>/dev/null || true)"
  case "$link" in
    *zoneinfo/*) echo "${link##*zoneinfo/}" ;;
    *) echo "UTC" ;;
  esac
}

# ---------- prerequisites ----------

check_macos() {
  [ "$(uname -s)" = "Darwin" ] || warn "This installer is written for macOS; continuing anyway."
}

ensure_git() {
  if ! git --version >/dev/null 2>&1; then
    xcode-select --install >/dev/null 2>&1 || true
    die "git is missing. macOS is installing the Command Line Tools now; run this installer again when that finishes."
  fi
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    warn "Docker Desktop is not installed."
    if command -v brew >/dev/null 2>&1 && confirm "Install Docker Desktop with Homebrew now?" y; then
      brew install --cask docker
    else
      die "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and run this installer again."
    fi
  fi
  if ! docker info >/dev/null 2>&1; then
    info "Starting Docker Desktop…"
    open -a Docker >/dev/null 2>&1 || die "Docker Desktop could not be opened. Start it by hand and run this again."
    local waited=0
    until docker info >/dev/null 2>&1; do
      sleep 3
      waited=$((waited + 3))
      [ "$waited" -lt 240 ] || die "Docker Desktop did not start within 4 minutes."
    done
  fi
  docker compose version >/dev/null 2>&1 || die "This Docker has no 'docker compose'. Update Docker Desktop."
  ok "Docker is running"
}

# ---------- source ----------

fetch_source() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    info "Fetching the latest version from GitHub…"
    git -C "$INSTALL_DIR" fetch --prune --quiet origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard --quiet "origin/$BRANCH"
    # Remove files that are no longer part of the app; matches, exports, backups and settings stay.
    git -C "$INSTALL_DIR" clean -ffdxq -e data/ -e exports/ -e backups/ -e .env
  elif [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    die "$INSTALL_DIR exists but is not a VS Gammon install. Move it away, or set VSG_HOME to another folder."
  else
    info "Downloading VS Gammon into ${INSTALL_DIR}…"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  fi
  chmod +x "$INSTALL_DIR/install.sh" "$INSTALL_DIR/scripts/launch.sh" 2>/dev/null || true
  ok "Source at $(git -C "$INSTALL_DIR" rev-parse --short HEAD) ($(git -C "$INSTALL_DIR" log -1 --format=%cd --date=short))"
}

host_settings() {
  set_env TZ "$(host_timezone)"
  set_env HOST_HOME "$HOME"
}

port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

choose_port() {
  local p
  p="$(port)"
  while port_in_use "$p" && ! curl -fsS --max-time 2 "http://localhost:$p/health" 2>/dev/null | grep -q '"status"'; do
    warn "Port $p is used by another program."
    p="$(ask "Port for VS Gammon:" "$((p + 1))")"
    case "$p" in '' | *[!0-9]*) p=$((DEFAULT_PORT + 1)) ;; esac
  done
  set_env APP_PORT "$p"
}

# ---------- earlier installs ----------

data_mount_of() {
  docker inspect -f '{{range .Mounts}}{{if eq .Destination "/srv/data"}}{{.Source}}{{end}}{{end}}' "$1" 2>/dev/null || true
}

adopt_earlier_installs() {
  local name source
  for name in $LEGACY_CONTAINERS; do
    docker inspect "$name" >/dev/null 2>&1 || continue
    source="$(data_mount_of "$name")"
    [ "$source" = "$INSTALL_DIR/data" ] && continue
    info "Found an earlier VS Gammon container ($name) using ${source:-no data folder}."
    docker stop "$name" >/dev/null 2>&1 || true
    if [ -n "$source" ] && [ -f "$source/app.db" ] && [ ! -f "$INSTALL_DIR/data/app.db" ]; then
      if confirm "Copy its matches, practice history and settings into $INSTALL_DIR/data?" y; then
        mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/exports"
        cp -R "$source/." "$INSTALL_DIR/data/"
        [ -d "$(dirname "$source")/exports" ] && cp -R "$(dirname "$source")/exports/." "$INSTALL_DIR/exports/" 2>/dev/null || true
        rm -rf "$INSTALL_DIR/data/no-home" "$INSTALL_DIR/data/watch-test"
        ok "Copied the earlier data"
      fi
    fi
    docker rm "$name" >/dev/null 2>&1 || true
  done
}

# ---------- run ----------

build_and_start() {
  mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/exports"
  info "Building the app (the first build downloads GNU Backgammon and takes a few minutes)…"
  compose build --pull --quiet
  compose up -d --remove-orphans
  info "Removing old images…"
  docker image prune -f --filter label=app=vs-gammon >/dev/null 2>&1 || true
  local image
  for image in $LEGACY_IMAGES; do docker image rm "$image" >/dev/null 2>&1 || true; done
}

wait_healthy() {
  local waited=0
  info "Waiting for the server on $(app_url)…"
  until curl -fsS --max-time 2 "$(app_url)/health" >/dev/null 2>&1; do
    sleep 2
    waited=$((waited + 2))
    if [ "$waited" -ge 180 ]; then
      compose logs --tail 40 || true
      die "The server did not answer within 3 minutes (logs above)."
    fi
  done
  ok "Server is up at $(app_url)"
}

backup_data() {
  [ -f "$INSTALL_DIR/data/app.db" ] || { info "No data to back up yet."; return; }
  mkdir -p "$INSTALL_DIR/backups"
  local file
  file="$INSTALL_DIR/backups/data-$(date +%Y%m%d-%H%M%S).tgz"
  tar -czf "$file" -C "$INSTALL_DIR" data
  ok "Backed up your data to $file"
  ls -1t "$INSTALL_DIR"/backups/data-*.tgz 2>/dev/null | tail -n +11 | while read -r old; do rm -f "$old"; done
}

# ---------- desktop shortcut ----------

make_icon() {
  local resources="$1" svg="$INSTALL_DIR/assets/icon.svg" work png size
  [ -f "$svg" ] || return 0
  work="$(mktemp -d -t vs-gammon-icon)"
  qlmanage -t -s 1024 -o "$work" "$svg" >/dev/null 2>&1 || true
  png="$work/icon.svg.png"
  [ -f "$png" ] || { rm -rf "$work"; return 0; }
  mkdir -p "$work/icon.iconset"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$png" --out "$work/icon.iconset/icon_${size}x${size}.png" >/dev/null 2>&1
    sips -z $((size * 2)) $((size * 2)) "$png" --out "$work/icon.iconset/icon_${size}x${size}@2x.png" >/dev/null 2>&1
  done
  iconutil -c icns "$work/icon.iconset" -o "$resources/icon.icns" >/dev/null 2>&1 || true
  rm -rf "$work"
}

make_shortcut() {
  local work app version
  work="$(mktemp -d -t vs-gammon-app)"
  app="$work/$APP_NAME.app"
  version="$(git -C "$INSTALL_DIR" rev-parse --short HEAD 2>/dev/null || echo dev)"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cat > "$app/Contents/MacOS/vs-gammon" <<EOF
#!/bin/bash
exec "$INSTALL_DIR/scripts/launch.sh"
EOF
  chmod +x "$app/Contents/MacOS/vs-gammon"
  cat > "$app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.ruolez.vs-gammon</string>
  <key>CFBundleExecutable</key><string>vs-gammon</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$version</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
EOF
  make_icon "$app/Contents/Resources"
  rm -rf "$SHORTCUT"
  mkdir -p "$(dirname "$SHORTCUT")"
  mv "$app" "$SHORTCUT"
  rm -rf "$work"
  xattr -cr "$SHORTCUT" 2>/dev/null || true
  touch "$SHORTCUT"
  ok "Desktop shortcut: $SHORTCUT"
}

# ---------- commands ----------

require_install() {
  [ -d "$INSTALL_DIR/.git" ] || die "VS Gammon is not installed in $INSTALL_DIR. Run: install.sh install"
}

do_install() {
  bold "Installing $APP_NAME"
  check_macos
  ensure_git
  ensure_docker
  fetch_source
  host_settings
  adopt_earlier_installs
  choose_port
  build_and_start
  wait_healthy
  make_shortcut
  bold "Done. Double-click \"$APP_NAME\" on your Desktop any time; it starts the server when needed."
  open "$(app_url)" >/dev/null 2>&1 || true
}

do_update() {
  bold "Updating $APP_NAME"
  require_install
  ensure_git
  ensure_docker
  backup_data
  local before after
  before="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
  fetch_source
  after="$(git -C "$INSTALL_DIR" rev-parse HEAD)"
  host_settings
  adopt_earlier_installs
  build_and_start
  wait_healthy
  make_shortcut
  if [ "$before" = "$after" ]; then
    ok "Already on the latest version"
  else
    info "What changed:"
    git -C "$INSTALL_DIR" log --format='    %s' "$before..$after" | head -20
  fi
}

do_start() {
  require_install
  "$INSTALL_DIR/scripts/launch.sh"
}

do_stop() {
  require_install
  compose stop
  ok "Stopped. The desktop shortcut starts it again."
}

do_status() {
  bold "$APP_NAME status"
  if [ ! -d "$INSTALL_DIR/.git" ]; then
    warn "Not installed in $INSTALL_DIR"
    return
  fi
  info "Folder:  $INSTALL_DIR"
  info "Version: $(git -C "$INSTALL_DIR" log -1 --format='%h, %cd' --date=short)"
  if docker info >/dev/null 2>&1; then
    compose ps
  else
    warn "Docker Desktop is not running"
  fi
  if curl -fsS --max-time 2 "$(app_url)/health" >/dev/null 2>&1; then
    ok "Running at $(app_url)"
  else
    warn "Not answering on $(app_url)"
  fi
  [ -d "$SHORTCUT" ] && ok "Desktop shortcut present" || warn "No desktop shortcut (run: install.sh shortcut)"
}

do_restore() {
  local file="${1:-}"
  require_install
  [ -f "$file" ] || die "Give the backup file to restore, e.g. install.sh restore ~/Desktop/data-20261110-120000.tgz"
  confirm "Replace the current data with $file? (a backup of the current data is made first)" n || exit 0
  ensure_docker
  backup_data
  compose stop >/dev/null 2>&1 || true
  rm -rf "$INSTALL_DIR/data"
  tar -xzf "$file" -C "$INSTALL_DIR"
  compose up -d
  wait_healthy
  ok "Restored $file"
}

do_uninstall() {
  bold "Uninstalling $APP_NAME"
  if docker info >/dev/null 2>&1 && [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
    compose down --rmi local --remove-orphans >/dev/null 2>&1 || true
    docker image prune -f --filter label=app=vs-gammon >/dev/null 2>&1 || true
    ok "Container and images removed"
  fi
  rm -rf "$SHORTCUT"
  ok "Desktop shortcut removed"
  [ -d "$INSTALL_DIR" ] || return 0
  if [ -f "$INSTALL_DIR/data/app.db" ] && confirm "Delete your matches, practice history and settings too?" n; then
    local keep="$HOME/Desktop/vs-gammon-data-$(date +%Y%m%d-%H%M%S).tgz"
    tar -czf "$keep" -C "$INSTALL_DIR" data
    rm -rf "$INSTALL_DIR"
    ok "Removed $INSTALL_DIR (a last backup of your data is at $keep)"
  else
    find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name data ! -name exports ! -name backups -exec rm -rf {} +
    ok "App removed; your data stays in $INSTALL_DIR/data (install again to pick it up)"
  fi
}

menu() {
  bold "$APP_NAME"
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "  Installed in $INSTALL_DIR"
  else
    echo "  Not installed yet (will install into $INSTALL_DIR)"
  fi
  echo
  echo "  1) Install or repair"
  echo "  2) Update from GitHub (keeps your data)"
  echo "  3) Start and open"
  echo "  4) Stop"
  echo "  5) Status"
  echo "  6) Back up data"
  echo "  7) Recreate the desktop shortcut"
  echo "  8) Uninstall"
  echo "  q) Quit"
  case "$(ask "Choose:" q)" in
    1) do_install ;;
    2) do_update ;;
    3) do_start ;;
    4) do_stop ;;
    5) do_status ;;
    6) require_install; backup_data ;;
    7) require_install; make_shortcut ;;
    8) do_uninstall ;;
    *) exit 0 ;;
  esac
}

COMMAND="${1:-}"
[ "$COMMAND" = "--yes" ] || [ "$COMMAND" = "-y" ] && COMMAND="${2:-}"
case "$COMMAND" in
  install) do_install ;;
  update) do_update ;;
  start) do_start ;;
  stop) do_stop ;;
  status) do_status ;;
  backup) require_install; backup_data ;;
  restore) do_restore "${2:-}" ;;
  shortcut) require_install; make_shortcut ;;
  uninstall | remove) do_uninstall ;;
  "")
    if has_tty; then menu; elif [ -d "$INSTALL_DIR/.git" ]; then do_update; else do_install; fi
    ;;
  *) die "Unknown command '$COMMAND'. Use install, update, start, stop, status, backup, restore FILE, shortcut or uninstall." ;;
esac
