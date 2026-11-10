#!/usr/bin/env bash
# Builds what gnubg needs into packaging/macos/build, touching nothing outside it:
# the bundled Python, build tools in a venv, and a static glib.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/versions.env"
BUILD="$HERE/build"
SRC="$BUILD/src"
PREFIX="$BUILD/prefix"
export MACOSX_DEPLOYMENT_TARGET="$MIN_MACOS"
mkdir -p "$SRC" "$PREFIX"

fetch() {
  local url="$1" sha="$2" file="$SRC/$(basename "${1//%2B/+}")"
  [[ -f "$file" ]] || curl -fsSL -o "$file" "$url"
  echo "$sha  $file" | shasum -a 256 -c - >/dev/null
  echo "$file"
}

if [[ ! -x "$BUILD/python/bin/python3" ]]; then
  tar xzf "$(fetch "$PYTHON_URL" "$PYTHON_SHA256")" -C "$BUILD"
fi

"$BUILD/python/bin/python3" -m pip install --quiet --disable-pip-version-check -r "$HERE/requirements.txt"

if [[ ! -x "$BUILD/tools/bin/meson" ]]; then
  "$BUILD/python/bin/python3" -m venv "$BUILD/tools"
  "$BUILD/tools/bin/pip" install --quiet meson==1.9.1 ninja==1.13.0 pkgconf==2.4.3.post2
fi
export PATH="$BUILD/tools/bin:$PATH"

if [[ ! -f "$PREFIX/lib/pkgconfig/glib-2.0.pc" ]]; then
  archive="$(fetch "$GLIB_URL" "$GLIB_SHA256")"
  rm -rf "$SRC/glib-$GLIB_VERSION"
  tar xJf "$archive" -C "$SRC"
  cd "$SRC/glib-$GLIB_VERSION"
  meson setup _build --prefix="$PREFIX" --libdir=lib --buildtype=release \
    --default-library=static --wrap-mode=default \
    -Dtests=false -Dintrospection=disabled -Ddocumentation=false -Dman-pages=disabled \
    -Dnls=disabled -Dglib_debug=disabled -Dsysprof=disabled -Dlibelf=disabled \
    -Dc_args="-mmacosx-version-min=$MIN_MACOS" -Dc_link_args="-mmacosx-version-min=$MIN_MACOS"
  meson install -C _build
fi
echo "dependencies ready in $BUILD"
