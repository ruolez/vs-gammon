#!/usr/bin/env bash
# Builds VS Gammon for Windows on this Mac: build.sh arm64|x64 [--engine]
# dist/windows/<arch>/VS Gammon/ (run VS Gammon.exe) and dist/release/VS-Gammon-<version>-windows-<arch>.zip.
# The engine is cross-compiled in Docker (llvm-mingw); Python is python-build-standalone's Windows build.
# Needs packaging/macos/build (build-deps.sh, build-gnubg.sh) for the source archives, engine data and a host Python.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
source "$HERE/versions.env"
ARCH="${1:-}"
case "$ARCH" in
  arm64) HOST=aarch64-w64-mingw32; PIP_PLATFORM=win_arm64; PYTHON_WIN_URL="$PYTHON_WIN_ARM64_URL"; PYTHON_WIN_SHA256="$PYTHON_WIN_ARM64_SHA256" ;;
  x64) HOST=x86_64-w64-mingw32; PIP_PLATFORM=win_amd64; PYTHON_WIN_URL="$PYTHON_WIN_X64_URL"; PYTHON_WIN_SHA256="$PYTHON_WIN_X64_SHA256" ;;
  *) echo "usage: build.sh arm64|x64 [--engine]" >&2; exit 1 ;;
esac
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
MAC="$ROOT/packaging/macos/build"
BUILD="$HERE/build/$ARCH"
OUT="$ROOT/dist/windows/$ARCH/VS Gammon"
ZIP="$ROOT/dist/release/VS-Gammon-$VERSION-windows-$ARCH.zip"
HOST_PY="$MAC/python/bin/python3"
IMAGE=vs-gammon-wincross
[[ -x "$HOST_PY" && -f "$MAC/engine/share/gnubg/gnubg.wd" ]] || { echo "run packaging/macos/build-deps.sh and build-gnubg.sh first" >&2; exit 1; }
mkdir -p "$BUILD" "$ROOT/dist/release"

docker build -q -t "$IMAGE" "$HERE" >/dev/null
in_docker() {
  docker run --rm -e ARCH="$ARCH" -v "$BUILD:/work" -v "$BUILD/python:/python:ro" -v "$MAC/src:/src:ro" \
    -v "$ROOT/packaging/macos/versions.env:/scripts/macos-versions.env:ro" -v "$HERE:/scripts-win:ro" \
    -v "$HERE/build-engine.sh:/scripts/build-engine.sh:ro" -v "$HERE/cross-$ARCH.ini:/scripts/cross.ini:ro" \
    -w /work "$IMAGE" "$@"
}

if [[ ! -f "$BUILD/python/python.exe" ]]; then
  archive="$BUILD/python-win.tar.gz"
  curl -fsSL -o "$archive" "$PYTHON_WIN_URL"
  echo "$PYTHON_WIN_SHA256  $archive" | shasum -a 256 -c - >/dev/null
  tar xzf "$archive" -C "$BUILD"
fi
WEBVIEW2="$HERE/build/webview2"
if [[ ! -f "$WEBVIEW2/pkg/LICENSE.txt" ]]; then
  mkdir -p "$WEBVIEW2"
  curl -fsSL -o "$WEBVIEW2/webview2.nupkg" "$WEBVIEW2_URL"
  echo "$WEBVIEW2_SHA256  $WEBVIEW2/webview2.nupkg" | shasum -a 256 -c - >/dev/null
  rm -rf "$WEBVIEW2/pkg" && unzip -q "$WEBVIEW2/webview2.nupkg" -d "$WEBVIEW2/pkg"
fi
# The header asks for EventToken.h; the mingw header is eventtoken.h and Linux file names are case-sensitive.
sed 's/"EventToken.h"/<eventtoken.h>/' "$WEBVIEW2/pkg/build/native/include/WebView2.h" > "$BUILD/WebView2.h"

[[ -f "$BUILD/engine/bin/gnubg.exe" && "${2:-}" != "--engine" ]] || in_docker bash /scripts/build-engine.sh > "$BUILD/engine.log" 2>&1 \
  || { tail -30 "$BUILD/engine.log"; exit 1; }

rm -rf "$BUILD/site-packages"
"$HOST_PY" -m pip install --quiet --disable-pip-version-check --target "$BUILD/site-packages" \
  --platform $PIP_PLATFORM --python-version 3.13 --implementation cp --abi cp313 --only-binary=:all: \
  -r "$ROOT/packaging/macos/requirements.txt"

work="$(mktemp -d)"
qlmanage -t -s 1024 -o "$work" "$ROOT/assets/icon.svg" >/dev/null 2>&1
"$HOST_PY" -c "from PIL import Image; Image.open('$work/icon.svg.png').save('$BUILD/vs-gammon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
rm -rf "$work"
IFS=. read -r major minor patch <<< "$VERSION"
in_docker bash -c "cp /scripts-win/launcher.c /scripts-win/launcher.rc . && \
  $HOST-windres -DVER_MAJOR=$major -DVER_MINOR=$minor -DVER_PATCH=$patch -DVER_TEXT='\\\"$VERSION\\\"' launcher.rc -O coff -o launcher.res.o && \
  $HOST-clang -O2 -municode -mwindows -Wall -Wno-unknown-pragmas -I. -o launcher.exe launcher.c launcher.res.o -lws2_32 -lshell32 -ladvapi32 -lole32 -luuid -ldwmapi -lcrypt32 && \
  $HOST-strip launcher.exe"

rm -rf "$OUT"
mkdir -p "$OUT/engine/bin" "$OUT/engine/share/gnubg"
cp "$BUILD/launcher.exe" "$OUT/VS Gammon.exe"
mkdir -p "$OUT/licenses"
cp "$WEBVIEW2/pkg/build/native/$ARCH/WebView2Loader.dll" "$OUT/"
cp "$WEBVIEW2/pkg/LICENSE.txt" "$OUT/licenses/WebView2.txt"
cp "$HERE/starting.html" "$OUT/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'Lib/test' --exclude 'Lib/idlelib' --exclude 'Lib/tkinter' --exclude 'Lib/turtledemo' \
  --exclude 'Lib/ensurepip' --exclude 'Lib/site-packages/pip*' --exclude 'tcl' --exclude 'include' --exclude 'libs' \
  --exclude 'Scripts' --exclude 'DLLs/_tkinter.pyd' --exclude 'DLLs/tcl*' --exclude 'DLLs/tk*' \
  "$BUILD/python/" "$OUT/python/"
rsync -a --exclude '__pycache__' --exclude '*.dist-info' --exclude 'bin' "$BUILD/site-packages/" "$OUT/python/Lib/site-packages/"
rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/app" "$OUT/"
cp "$BUILD/engine/bin/gnubg.exe" "$OUT/engine/bin/"
for item in gnubg.wd gnubg_os0.bd gnubg_ts0.bd met; do cp -R "$MAC/engine/share/gnubg/$item" "$OUT/engine/share/gnubg/"; done
"$HOST_PY" -m compileall -q --invalidation-mode unchecked-hash "$OUT/python/Lib" "$OUT/app" >/dev/null || true
cat > "$OUT/About the engine.txt" <<NOTE
VS Gammon includes GNU Backgammon 1.08.003, free software under the GNU General Public License version 3.
Its unmodified source code: https://ftp.gnu.org/gnu/gnubg/gnubg-release-1.08.003-sources.tar.gz
How it is built here: https://github.com/ruolez/vs-gammon/tree/main/packaging/windows
NOTE

rm -f "$ZIP"
(cd "$ROOT/dist/windows/$ARCH" && ditto -c -k --keepParent "VS Gammon" "$ZIP")
du -sh "$OUT" "$ZIP"
echo "built $OUT"
