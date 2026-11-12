#!/usr/bin/env bash
# Builds VS Gammon for Windows 11 ARM64 on this Mac:
# dist/windows/VS Gammon/ (run VS Gammon.exe) and dist/release/VS-Gammon-<version>-windows-arm64.zip.
# The engine is cross-compiled in Docker (llvm-mingw); Python is python-build-standalone for aarch64-pc-windows-msvc.
# Needs packaging/macos/build (build-deps.sh, build-gnubg.sh) for the source archives, engine data and a host Python.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
source "$HERE/versions.env"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
MAC="$ROOT/packaging/macos/build"
BUILD="$HERE/build"
OUT="$ROOT/dist/windows/VS Gammon"
ZIP="$ROOT/dist/release/VS-Gammon-$VERSION-windows-arm64.zip"
HOST_PY="$MAC/python/bin/python3"
IMAGE=vs-gammon-wincross
[[ -x "$HOST_PY" && -f "$MAC/engine/share/gnubg/gnubg.wd" ]] || { echo "run packaging/macos/build-deps.sh and build-gnubg.sh first" >&2; exit 1; }
mkdir -p "$BUILD" "$ROOT/dist/release"

docker build -q -t "$IMAGE" "$HERE" >/dev/null
in_docker() {
  docker run --rm -v "$BUILD:/work" -v "$BUILD/python:/python:ro" -v "$MAC/src:/src:ro" \
    -v "$ROOT/packaging/macos/versions.env:/scripts/macos-versions.env:ro" -v "$HERE:/scripts-win:ro" \
    -v "$HERE/build-engine.sh:/scripts/build-engine.sh:ro" -v "$HERE/cross-arm64.ini:/scripts/cross-arm64.ini:ro" \
    -w /work "$IMAGE" "$@"
}

if [[ ! -f "$BUILD/python/python.exe" ]]; then
  archive="$BUILD/python-win.tar.gz"
  curl -fsSL -o "$archive" "$PYTHON_WIN_URL"
  echo "$PYTHON_WIN_SHA256  $archive" | shasum -a 256 -c - >/dev/null
  tar xzf "$archive" -C "$BUILD"
fi
[[ -f "$BUILD/engine/bin/gnubg.exe" && "${1:-}" != "--engine" ]] || in_docker bash /scripts/build-engine.sh > "$BUILD/engine.log" 2>&1 \
  || { tail -30 "$BUILD/engine.log"; exit 1; }

rm -rf "$BUILD/site-packages"
"$HOST_PY" -m pip install --quiet --disable-pip-version-check --target "$BUILD/site-packages" \
  --platform win_arm64 --python-version 3.13 --implementation cp --abi cp313 --only-binary=:all: \
  -r "$ROOT/packaging/macos/requirements.txt"

work="$(mktemp -d)"
qlmanage -t -s 1024 -o "$work" "$ROOT/assets/icon.svg" >/dev/null 2>&1
"$HOST_PY" -c "from PIL import Image; Image.open('$work/icon.svg.png').save('$BUILD/vs-gammon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
rm -rf "$work"
IFS=. read -r major minor patch <<< "$VERSION"
in_docker bash -c "cp /scripts-win/launcher.c /scripts-win/launcher.rc . && \
  aarch64-w64-mingw32-windres -DVER_MAJOR=$major -DVER_MINOR=$minor -DVER_PATCH=$patch -DVER_TEXT='\\\"$VERSION\\\"' launcher.rc -O coff -o launcher.res.o && \
  aarch64-w64-mingw32-clang -O2 -municode -mwindows -Wall -o launcher.exe launcher.c launcher.res.o -lws2_32 -lshell32 -ladvapi32 && \
  aarch64-w64-mingw32-strip launcher.exe"

rm -rf "$OUT"
mkdir -p "$OUT/engine/bin" "$OUT/engine/share/gnubg"
cp "$BUILD/launcher.exe" "$OUT/VS Gammon.exe"
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
(cd "$ROOT/dist/windows" && ditto -c -k --keepParent "VS Gammon" "$ZIP")
du -sh "$OUT" "$ZIP"
echo "built $OUT"
