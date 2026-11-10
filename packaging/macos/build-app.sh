#!/usr/bin/env bash
# Assembles dist/VS Gammon.app from build-deps.sh and build-gnubg.sh output.
# Signs with the identity in ~/.config/vs-gammon/codesign-identity if there is one, else ad-hoc.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
source "$HERE/versions.env"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
BUILD="$HERE/build"
APP="$ROOT/dist/VS Gammon.app"
RES="$APP/Contents/Resources"

[[ -x "$BUILD/engine/bin/gnubg" ]] || { echo "run build-deps.sh and build-gnubg.sh first" >&2; exit 1; }
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/engine/bin" "$RES/engine/share/gnubg"

swiftc -O -swift-version 5 -target "arm64-apple-macos$MIN_MACOS" \
  -o "$APP/Contents/MacOS/VS Gammon" "$HERE"/shell/*.swift

UPDATE_KEY="$(tr -d '[:space:]' < "$HERE/release-public-key.txt" 2>/dev/null || true)"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@MIN_MACOS@/$MIN_MACOS/g" -e "s|@UPDATE_KEY@|$UPDATE_KEY|g" "$HERE/Info.plist.in" > "$APP/Contents/Info.plist"
plutil -lint "$APP/Contents/Info.plist" >/dev/null
printf 'APPL????' > "$APP/Contents/PkgInfo"

rsync -a --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'lib/python3.13/test' --exclude 'lib/python3.13/idlelib' --exclude 'lib/python3.13/tkinter' \
  --exclude 'lib/python3.13/turtledemo' --exclude 'lib/python3.13/ensurepip' --exclude 'lib/python3.13/lib2to3' \
  --exclude 'lib/python3.13/site-packages/pip*' --exclude 'lib/python3.13/config-*' \
  --exclude 'lib/libtcl*' --exclude 'lib/tcl*' --exclude 'lib/tk*' --exclude 'lib/itcl*' --exclude 'lib/thread*' \
  --exclude 'lib/pkgconfig' --exclude 'include' --exclude 'share' \
  "$BUILD/python/" "$RES/python/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/app" "$RES/"
cp "$BUILD/engine/bin/gnubg" "$RES/engine/bin/gnubg"
for item in gnubg.wd gnubg_os0.bd gnubg_ts0.bd met; do cp -R "$BUILD/engine/share/gnubg/$item" "$RES/engine/share/gnubg/"; done

# Unchecked pycs: fast startup, and nothing ever writes into the signed bundle.
"$RES/python/bin/python3" -m compileall -q --invalidation-mode unchecked-hash "$RES/python/lib/python3.13" "$RES/app" >/dev/null || true

work="$(mktemp -d)"
qlmanage -t -s 1024 -o "$work" "$ROOT/assets/icon.svg" >/dev/null 2>&1
mkdir "$work/AppIcon.iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$work/icon.svg.png" --out "$work/AppIcon.iconset/icon_${size}x${size}.png" >/dev/null
  sips -z $((size * 2)) $((size * 2)) "$work/icon.svg.png" --out "$work/AppIcon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$work/AppIcon.iconset" -o "$RES/AppIcon.icns"
rm -rf "$work"

IDENTITY_FILE="$HOME/.config/vs-gammon/codesign-identity"
IDENTITY="-"
[[ -f "$IDENTITY_FILE" ]] && IDENTITY="$(tr -d '[:space:]' < "$IDENTITY_FILE")"
find "$RES" -type f \( -perm -u+x -o -name '*.dylib' -o -name '*.so' \) -print0 | while IFS= read -r -d '' file; do
  if file -b "$file" | grep -q 'Mach-O'; then codesign --force --sign "$IDENTITY" "$file" 2>/dev/null; fi
done
codesign --force --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict "$APP"
du -sh "$APP"
echo "built $APP"
