#!/usr/bin/env bash
# Builds the app and writes dist/release/: VS-Gammon-<version>.dmg for first installs,
# VS-Gammon-<version>.zip + .sig for in-app updates. Upload all three to a GitHub release tagged v<version>.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
OUT="$ROOT/dist/release"
TOOL="$HERE/build/release-key"
[[ -f "$HOME/.config/vs-gammon/release.key" ]] || { echo "no release key: run make-release-key.sh once" >&2; exit 1; }
"$HERE/build-app.sh"
swiftc -O -o "$TOOL" "$HERE/tools/release-key.swift"
mkdir -p "$OUT"
ZIP="$OUT/VS-Gammon-$VERSION.zip"
DMG="$OUT/VS-Gammon-$VERSION.dmg"
rm -f "$ZIP" "$ZIP.sig" "$DMG"
ditto -c -k --keepParent "$ROOT/dist/VS Gammon.app" "$ZIP"
"$TOOL" sign "$ZIP"

stage="$(mktemp -d)"
cp -R "$ROOT/dist/VS Gammon.app" "$stage/"
ln -s /Applications "$stage/Applications"
cat > "$stage/About the engine.txt" <<NOTE
VS Gammon includes GNU Backgammon 1.08.003, free software under the GNU General Public License version 3.
Its unmodified source code: https://ftp.gnu.org/gnu/gnubg/gnubg-release-1.08.003-sources.tar.gz
How it is built here: https://github.com/ruolez/vs-gammon/tree/main/packaging/macos
NOTE
hdiutil create -quiet -volname "VS Gammon" -srcfolder "$stage" -format UDZO "$DMG"
rm -rf "$stage"
ls -la "$OUT"
