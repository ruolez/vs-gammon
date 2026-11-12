#!/usr/bin/env bash
# Runs inside the vs-gammon-wincross container (see build.sh): builds a static glib and GNU Backgammon
# without its GUI for Windows ARM64, embedding the Windows Python mounted at /python, into /work/engine.
set -euo pipefail
source /scripts/macos-versions.env
HOST=aarch64-w64-mingw32
WORK=/work
PREFIX="$WORK/prefix"
export PKG_CONFIG_LIBDIR="$PREFIX/lib/pkgconfig"
export PKG_CONFIG="pkg-config --static"
mkdir -p "$WORK/src" "$PREFIX"

if [[ ! -f "$PREFIX/lib/pkgconfig/glib-2.0.pc" ]]; then
  rm -rf "$WORK/src/glib-$GLIB_VERSION"
  tar xJf "/src/glib-$GLIB_VERSION.tar.xz" -C "$WORK/src"
  cd "$WORK/src/glib-$GLIB_VERSION"
  meson setup _build --cross-file /scripts/cross-arm64.ini --prefix="$PREFIX" --libdir=lib --buildtype=release \
    --default-library=static --wrap-mode=default \
    -Dtests=false -Dintrospection=disabled -Ddocumentation=false -Dman-pages=disabled \
    -Dnls=disabled -Dglib_debug=disabled -Dsysprof=disabled -Dlibelf=disabled \
    -Dc_args=-Dffs=__builtin_ffs
  meson install -C _build
fi

SRC="$WORK/src/gnubg-$GNUBG_VERSION"
rm -rf "$SRC" "$WORK/engine"
tar xzf "/src/gnubg-release-$GNUBG_VERSION-sources.tar.gz" -C "$WORK/src"
cd "$SRC"
./configure --host="$HOST" --prefix="$WORK/engine" --disable-shared --disable-nls \
  --without-gtk --without-gtk3 --without-board3d --without-sqlite \
  --enable-simd=neon --disable-cputest --enable-threads \
  ac_cv_lib_readline_readline=no ac_cv_lib_gmp___gmpz_import=no ax_cv_have_neon_ext=yes \
  --with-python=/usr/bin/python3 \
  PYTHON_CPPFLAGS="-I/python/include" \
  PYTHON_LIBS="/python/libs/python313.lib" \
  PYTHON_EXTRA_LIBS="-lm" \
  PYTHON_EXTRA_LDFLAGS="-Wl,-O1" \
  PYTHON_SITE_PKG="/python/Lib/site-packages" \
  CFLAGS="-O3" \
  LDFLAGS="-static-libgcc -Wl,-u,_tls_used"
make -j"$(nproc)" -C win32
make -j"$(nproc)" -C lib
make -j"$(nproc)" gnubg.exe
mkdir -p "$WORK/engine/bin"
cp gnubg.exe "$WORK/engine/bin/"
"$HOST-strip" "$WORK/engine/bin/gnubg.exe"
grep -q "^#define USE_PYTHON 1" config.h || { echo "gnubg was configured without Python" >&2; exit 1; }
echo "engine ready: $(file "$WORK/engine/bin/gnubg.exe")"
