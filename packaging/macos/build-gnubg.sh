#!/usr/bin/env bash
# Builds GNU Backgammon without its GUI, embedding the bundled Python, into build/engine.
# Autotools can't cope with spaces in paths, so everything goes through a symlink.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/versions.env"
LINK="${TMPDIR:-/tmp}/vs-gammon-macos-build"
ln -sfn "$HERE/build" "${LINK%/}"
LINK="${LINK%/}"
export MACOSX_DEPLOYMENT_TARGET="$MIN_MACOS"
export PATH="$LINK/tools/bin:$PATH"
export PKG_CONFIG="$LINK/tools/bin/pkgconf --static --define-variable=prefix=$LINK/prefix"
export PKG_CONFIG_LIBDIR="$LINK/prefix/lib/pkgconfig"

SRC="$LINK/src/gnubg-$GNUBG_VERSION"
archive="$LINK/src/gnubg-release-$GNUBG_VERSION-sources.tar.gz"
[[ -f "$archive" ]] || curl -fsSL -o "$archive" "$GNUBG_URL"
echo "$GNUBG_SHA256  $archive" | shasum -a 256 -c - >/dev/null
rm -rf "$SRC" "$LINK/engine"
tar xzf "$archive" -C "$LINK/src"
cd "$SRC"

PY="$LINK/python"
./configure --build=aarch64-apple-darwin --prefix="$LINK/engine" --disable-shared --disable-nls \
  --without-gtk --without-gtk3 --without-board3d --without-sqlite \
  --enable-simd=neon --disable-cputest --enable-threads \
  ac_cv_lib_readline_readline=no ac_cv_lib_gmp___gmpz_import=no \
  --with-python="$PY/bin/python3" \
  PYTHON_CPPFLAGS="-I$PY/include/python3.13" \
  PYTHON_LIBS="-L$PY/lib -lpython3.13" \
  PYTHON_EXTRA_LIBS="-ldl -framework CoreFoundation" \
  PYTHON_SITE_PKG="$PY/lib/python3.13/site-packages" \
  CFLAGS="-O3 -mmacosx-version-min=$MIN_MACOS" \
  LDFLAGS="-mmacosx-version-min=$MIN_MACOS"
make -j"$(sysctl -n hw.ncpu)"
make install
install_name_tool -add_rpath "@executable_path/../../python/lib" "$LINK/engine/bin/gnubg"
codesign --force --sign - "$LINK/engine/bin/gnubg"
"$LINK/engine/bin/makebearoff" -t 6x6 -f "$LINK/engine/share/gnubg/gnubg_ts0.bd"
echo "engine ready in $HERE/build/engine"
